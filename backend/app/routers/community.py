from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import HelpOffer, Need, Notification, User
from ..schemas import HelpOfferCreate
from ..security import get_current_user

router = APIRouter(prefix='/help', tags=['community help'])
MANAGER_ROLES = {'admin', 'coordinator'}


def offer_response(db: Session, offer: HelpOffer) -> dict:
    owner = db.get(User, offer.offered_by)
    claimant = db.get(User, offer.claimed_by) if offer.claimed_by else None
    target = db.get(Need, offer.need_id) if offer.need_id else None
    return {
        'id': offer.id,
        'need_id': offer.need_id,
        'incident_id': target.incident_id if target else None,
        'offered_by': offer.offered_by,
        'offered_by_name': owner.full_name if owner else 'Community member',
        'category': offer.category,
        'description': offer.description,
        'quantity': offer.quantity,
        'unit': offer.unit,
        'location_text': offer.location_text,
        'latitude': offer.latitude,
        'longitude': offer.longitude,
        'status': offer.status,
        'claimed_by': offer.claimed_by,
        'claimed_by_name': claimant.full_name if claimant else None,
        'created_at': offer.created_at.isoformat(),
    }


@router.get('/offers')
def list_offers(
    status: str = Query(default='open', pattern='^(open|claimed|fulfilled|cancelled|all)$'),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(HelpOffer).order_by(HelpOffer.created_at.desc()).limit(limit)
    if status != 'all':
        query = query.where(HelpOffer.status == status)
    return [offer_response(db, offer) for offer in db.scalars(query)]


@router.post('/offers', status_code=201)
def create_offer(
    data: HelpOfferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.need_id is not None:
        need = db.get(Need, data.need_id)
        if need is None:
            raise HTTPException(status_code=404, detail='Requested need not found')
        if need.status in {'fulfilled', 'closed'}:
            raise HTTPException(status_code=409, detail='This need is no longer open for offers')
    offer = HelpOffer(offered_by=user.id, **data.model_dump())
    db.add(offer)
    db.flush()
    recipients = db.scalars(
        select(User).where(User.role.in_(MANAGER_ROLES), User.is_active.is_(True))
    ).all()
    for recipient in recipients:
        db.add(Notification(
            user_id=recipient.id,
            kind='help_offer',
            title='New community help offer',
            message=f'{user.full_name} can provide {data.quantity:g} {data.unit} of {data.category}.',
            payload={'offer_id': offer.id, 'need_id': offer.need_id},
        ))
    append_audit_log(
        db, actor_id=user.id, action='help_offer_created',
        entity='help_offer', entity_id=offer.id, after=data.model_dump(),
    )
    db.commit()
    db.refresh(offer)
    return offer_response(db, offer)


@router.post('/offers/{offer_id}/claim')
def claim_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offer = db.get(HelpOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail='Help offer not found')
    if offer.status != 'open':
        raise HTTPException(status_code=409, detail='This offer is no longer open')
    if offer.offered_by == user.id:
        raise HTTPException(status_code=400, detail='You cannot claim your own offer')
    offer.status = 'claimed'
    offer.claimed_by = user.id
    db.add(Notification(
        user_id=offer.offered_by,
        kind='help_offer_claimed',
        title='Your help offer was claimed',
        message=f'{user.full_name} responded to your {offer.category} offer.',
        payload={'offer_id': offer.id, 'claimed_by': user.id},
    ))
    db.commit()
    db.refresh(offer)
    return offer_response(db, offer)


@router.get('/notifications')
def notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    rows = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)).all()
    return [{
        'id': row.id,
        'kind': row.kind,
        'title': row.title,
        'message': row.message,
        'payload': row.payload,
        'is_read': row.is_read,
        'created_at': row.created_at.isoformat(),
    } for row in rows]


@router.post('/notifications/{notification_id}/read')
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id
    ))
    if row is None:
        raise HTTPException(status_code=404, detail='Notification not found')
    row.is_read = True
    db.commit()
    return {'id': row.id, 'is_read': True}
