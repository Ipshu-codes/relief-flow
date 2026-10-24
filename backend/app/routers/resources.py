from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import (
    DeliveryConfirmation,
    Need,
    Organization,
    Resource,
    ResourceMovement,
    ResourceStock,
    User,
)
from ..schemas import (
    DeliveryConfirmationCreate,
    MovementStatusPatch,
    ResourceAllocationCreate,
    ResourceStockCreate,
)
from ..security import get_current_user

router = APIRouter(tags=['resources'])
MANAGER_ROLES = {'admin', 'coordinator'}


def can_manage_stock(user: User, organization_id: int) -> bool:
    return user.role in MANAGER_ROLES or (
        user.role == 'org_admin' and user.organization_id == organization_id
    )


def stock_response(db: Session, stock: ResourceStock) -> dict:
    resource = db.get(Resource, stock.resource_id)
    organization = db.get(Organization, stock.organization_id)
    return {
        'id': stock.id,
        'resource_id': stock.resource_id,
        'resource_type': resource.resource_type,
        'unit': resource.unit,
        'organization_id': stock.organization_id,
        'organization_name': organization.name,
        'location_id': stock.location_id,
        'quantity_available': stock.quantity_available,
        'quantity_reserved': stock.quantity_reserved,
    }


def movement_response(movement: ResourceMovement) -> dict:
    return {
        'id': movement.id,
        'need_id': movement.need_id,
        'resource_id': movement.resource_id,
        'stock_id': movement.stock_id,
        'quantity': movement.quantity,
        'quantity_confirmed': movement.quantity_confirmed,
        'status': movement.status,
        'client_uuid': movement.client_uuid,
        'dispatched_at': movement.dispatched_at.isoformat() if movement.dispatched_at else None,
        'delivered_at': movement.delivered_at.isoformat() if movement.delivered_at else None,
    }


@router.post('/resources/stock', status_code=201)
def add_stock(
    data: ResourceStockCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    organization_id = data.organization_id or user.organization_id
    if organization_id is None:
        raise HTTPException(status_code=422, detail='organization_id is required')
    if not can_manage_stock(user, organization_id):
        raise HTTPException(status_code=403, detail='Cannot manage stock for this organization')
    if db.get(Organization, organization_id) is None:
        raise HTTPException(status_code=404, detail='Organization not found')
    if db.get(Resource, data.resource_id) is None:
        raise HTTPException(status_code=404, detail='Resource type not found')

    stock = db.scalar(
        select(ResourceStock).where(
            ResourceStock.organization_id == organization_id,
            ResourceStock.resource_id == data.resource_id,
            ResourceStock.location_id == data.location_id,
        )
    )
    before_quantity = stock.quantity_available if stock else 0
    if stock is None:
        stock = ResourceStock(
            organization_id=organization_id,
            resource_id=data.resource_id,
            location_id=data.location_id,
            quantity_available=data.quantity_available,
            quantity_reserved=0,
        )
        db.add(stock)
        db.flush()
    else:
        stock.quantity_available += data.quantity_available
    append_audit_log(
        db,
        actor_id=user.id,
        action='resource_stock_added',
        entity='resource_stock',
        entity_id=stock.id,
        before={'quantity_available': before_quantity},
        after={'quantity_available': stock.quantity_available},
    )
    db.commit()
    db.refresh(stock)
    return stock_response(db, stock)


@router.get('/resources/stock')
def list_stock(
    resource_id: int | None = None,
    location_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(ResourceStock)
    if user.role in MANAGER_ROLES:
        pass
    elif user.role == 'org_admin' and user.organization_id is not None:
        statement = statement.where(ResourceStock.organization_id == user.organization_id)
    else:
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    if resource_id is not None:
        statement = statement.where(ResourceStock.resource_id == resource_id)
    if location_id is not None:
        statement = statement.where(ResourceStock.location_id == location_id)
    rows = db.scalars(statement.order_by(ResourceStock.id).offset(offset).limit(limit)).all()
    return [stock_response(db, row) for row in rows]


@router.post('/allocations', status_code=201)
def allocate_stock(
    data: ResourceAllocationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in MANAGER_ROLES | {'org_admin'}:
        raise HTTPException(status_code=403, detail='Coordinator or organization admin role required')
    client_uuid = str(data.client_uuid) if data.client_uuid else None
    if client_uuid:
        existing = db.scalar(
            select(ResourceMovement).where(ResourceMovement.client_uuid == client_uuid)
        )
        if existing is not None:
            if (
                existing.need_id != data.need_id
                or existing.stock_id != data.stock_id
                or existing.quantity != data.quantity
            ):
                raise HTTPException(status_code=409, detail='client_uuid was already used for another allocation')
            return {**movement_response(existing), 'duplicate': True}

    need = db.scalar(select(Need).where(Need.id == data.need_id).with_for_update())
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    if need.status in {'fulfilled', 'closed', 'rejected'}:
        raise HTTPException(status_code=409, detail='Need is not available for allocation')
    stock = db.scalar(select(ResourceStock).where(ResourceStock.id == data.stock_id))
    if stock is None:
        raise HTTPException(status_code=404, detail='Stock item not found')
    if not can_manage_stock(user, stock.organization_id):
        raise HTTPException(status_code=403, detail='Cannot allocate stock for this organization')
    already_allocated = db.scalar(
        select(func.coalesce(func.sum(ResourceMovement.quantity), 0.0)).where(
            ResourceMovement.need_id == need.id,
            ResourceMovement.status != 'cancelled',
        )
    ) or 0.0
    remaining = max(0.0, need.quantity_requested - need.quantity_fulfilled - already_allocated)
    if data.quantity > remaining:
        raise HTTPException(status_code=409, detail=f'Allocation exceeds remaining need ({remaining})')

    result = db.execute(
        update(ResourceStock)
        .where(
            ResourceStock.id == stock.id,
            ResourceStock.quantity_available >= data.quantity,
        )
        .values(
            quantity_available=ResourceStock.quantity_available - data.quantity,
            quantity_reserved=ResourceStock.quantity_reserved + data.quantity,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail='Insufficient unreserved stock')

    movement = ResourceMovement(
        need_id=need.id,
        resource_id=stock.resource_id,
        stock_id=stock.id,
        quantity=data.quantity,
        status='allocated',
        client_uuid=client_uuid,
        allocated_by=user.id,
    )
    db.add(movement)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='resource_allocated',
        entity='resource_movement',
        entity_id=movement.id,
        after={
            'need_id': need.id,
            'resource_id': stock.resource_id,
            'quantity': movement.quantity,
            'status': movement.status,
        },
    )
    db.commit()
    db.refresh(movement)
    return {**movement_response(movement), 'duplicate': False}


@router.patch('/movements/{movement_id}/status')
def update_movement_status(
    movement_id: int,
    data: MovementStatusPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    movement = db.get(ResourceMovement, movement_id)
    if movement is None:
        raise HTTPException(status_code=404, detail='Movement not found')
    stock = db.get(ResourceStock, movement.stock_id)
    if not can_manage_stock(user, stock.organization_id):
        raise HTTPException(status_code=403, detail='Cannot manage this movement')
    allowed = {'allocated': 'dispatched', 'dispatched': 'delivered'}
    if allowed.get(movement.status) != data.status:
        raise HTTPException(status_code=409, detail='Invalid resource movement status transition')
    before_status = movement.status
    if data.status == 'dispatched':
        result = db.execute(
            update(ResourceStock)
            .where(
                ResourceStock.id == stock.id,
                ResourceStock.quantity_reserved >= movement.quantity,
            )
            .values(
                quantity_reserved=ResourceStock.quantity_reserved - movement.quantity,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail='Reserved stock is no longer available')
        movement.dispatched_at = datetime.now(timezone.utc)
    else:
        movement.delivered_at = datetime.now(timezone.utc)
    movement.status = data.status
    append_audit_log(
        db,
        actor_id=user.id,
        action='resource_movement_status_changed',
        entity='resource_movement',
        entity_id=movement.id,
        before={'status': before_status},
        after={'status': movement.status},
    )
    db.commit()
    db.refresh(movement)
    return movement_response(movement)


@router.post('/movements/{movement_id}/confirm')
def confirm_delivery(
    movement_id: int,
    data: DeliveryConfirmationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client_uuid = str(data.client_uuid)
    existing = db.scalar(
        select(DeliveryConfirmation).where(DeliveryConfirmation.client_uuid == client_uuid)
    )
    if existing is not None:
        if existing.movement_id != movement_id:
            raise HTTPException(status_code=409, detail='client_uuid was used for another confirmation')
        return confirmation_response(existing, duplicate=True)
    movement = db.scalar(select(ResourceMovement).where(ResourceMovement.id == movement_id).with_for_update())
    if movement is None:
        raise HTTPException(status_code=404, detail='Movement not found')
    if movement.status not in {'delivered', 'confirmed'}:
        raise HTTPException(status_code=409, detail='Movement must be delivered before confirmation')
    if user.role not in MANAGER_ROLES | {'org_admin', 'community_member', 'volunteer'}:
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    stock = db.get(ResourceStock, movement.stock_id)
    if user.role == 'org_admin' and user.organization_id != stock.organization_id:
        raise HTTPException(status_code=403, detail='Cannot confirm deliveries for another organization')
    already_confirmed = movement.quantity_confirmed
    remaining_movement = movement.quantity - already_confirmed
    if data.status == 'not_received' and data.quantity_received != 0:
        raise HTTPException(status_code=422, detail='not_received confirmations must report zero quantity')
    if data.status == 'full' and data.quantity_received != remaining_movement:
        raise HTTPException(status_code=422, detail='full confirmation must report the remaining movement quantity')
    if data.status == 'partial' and not 0 < data.quantity_received < remaining_movement:
        raise HTTPException(status_code=422, detail='partial confirmation must be positive and less than the remaining movement quantity')

    before_movement = {'quantity_confirmed': movement.quantity_confirmed, 'status': movement.status}
    confirmation = DeliveryConfirmation(
        movement_id=movement.id,
        client_uuid=client_uuid,
        confirmed_by=user.id,
        status=data.status,
        quantity_received=data.quantity_received,
        notes=data.notes,
    )
    db.add(confirmation)
    movement.quantity_confirmed += data.quantity_received
    if movement.quantity_confirmed >= movement.quantity:
        movement.status = 'confirmed'
    db.flush()
    need = db.scalar(select(Need).where(Need.id == movement.need_id).with_for_update())
    previous_need = {'quantity_fulfilled': need.quantity_fulfilled, 'status': need.status}
    total_received = db.scalar(
        select(func.coalesce(func.sum(DeliveryConfirmation.quantity_received), 0.0))
        .join(ResourceMovement, ResourceMovement.id == DeliveryConfirmation.movement_id)
        .where(ResourceMovement.need_id == need.id)
    ) or 0.0
    need.quantity_fulfilled = min(need.quantity_requested, total_received)
    if need.quantity_fulfilled >= need.quantity_requested:
        need.status = 'fulfilled'
    elif need.quantity_fulfilled > 0:
        need.status = 'partially_fulfilled'
    elif need.status in {'fulfilled', 'partially_fulfilled'}:
        need.status = 'open'

    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='delivery_confirmed',
        entity='delivery_confirmation',
        entity_id=confirmation.id,
        after={
            'movement_id': movement.id,
            'client_uuid': client_uuid,
            'status': data.status,
            'quantity_received': data.quantity_received,
        },
    )
    append_audit_log(
        db,
        actor_id=user.id,
        action='delivery_progress_updated',
        entity='resource_movement',
        entity_id=movement.id,
        before=before_movement,
        after={'quantity_confirmed': movement.quantity_confirmed, 'status': movement.status},
    )
    append_audit_log(
        db,
        actor_id=user.id,
        action='need_delivery_progress_updated',
        entity='need',
        entity_id=need.id,
        before=previous_need,
        after={'quantity_fulfilled': need.quantity_fulfilled, 'status': need.status},
    )
    db.commit()
    db.refresh(confirmation)
    return confirmation_response(confirmation, duplicate=False)


@router.get('/needs/{need_id}/progress')
def need_progress(
    need_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    need = db.get(Need, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    movements = db.scalars(
        select(ResourceMovement).where(ResourceMovement.need_id == need.id)
    ).all()
    active = [movement for movement in movements if movement.status != 'cancelled']
    allocated = sum(movement.quantity for movement in active)
    dispatched = sum(
        movement.quantity
        for movement in active
        if movement.status in {'dispatched', 'delivered', 'confirmed'}
    )
    delivered = sum(
        movement.quantity
        for movement in active
        if movement.status in {'delivered', 'confirmed'}
    )
    confirmed = need.quantity_fulfilled
    return {
        'need_id': need.id,
        'quantity_requested': need.quantity_requested,
        'allocated': allocated,
        'dispatched': dispatched,
        'delivered': delivered,
        'confirmed': confirmed,
        'remaining': max(0.0, need.quantity_requested - confirmed),
        'unconfirmed_delivered': max(0.0, delivered - confirmed),
    }


def confirmation_response(confirmation: DeliveryConfirmation, duplicate: bool) -> dict:
    return {
        'id': confirmation.id,
        'movement_id': confirmation.movement_id,
        'client_uuid': confirmation.client_uuid,
        'status': confirmation.status,
        'quantity_received': confirmation.quantity_received,
        'created_at': confirmation.created_at.isoformat(),
        'duplicate': duplicate,
    }
