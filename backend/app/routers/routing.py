from datetime import datetime, timezone
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..geo.routing import EstimateRoutingClient
from ..ledger import append_audit_log
from ..models import Assignment, RoadBlockage, Route, User
from ..schemas import RoadBlockageCreate, RouteComputeRequest
from ..security import get_current_user

router = APIRouter(tags=['routing'])
routing_client = EstimateRoutingClient()


def require_coordinator(user: User) -> None:
    if user.role not in {'coordinator', 'admin'}:
        raise HTTPException(status_code=403, detail='Coordinator role required')


@router.post('/blockages', status_code=201)
def create_blockage(
    data: RoadBlockageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    blockage = RoadBlockage(
        latitude=data.latitude,
        longitude=data.longitude,
        radius_km=data.radius_km,
        reported_by=user.id,
        verified=True,
        notes=data.notes,
    )
    db.add(blockage)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='blockage_created',
        entity='road_blockage',
        entity_id=blockage.id,
        after={
            'latitude': blockage.latitude,
            'longitude': blockage.longitude,
            'radius_km': blockage.radius_km,
            'verified': True,
            'notes': blockage.notes,
        },
    )
    route_updates = recompute_active_routes(db, user.id, blockage.id)
    db.commit()
    db.refresh(blockage)
    return {**blockage_response(blockage), **route_updates}


@router.patch('/blockages/{blockage_id}/clear')
def clear_blockage(
    blockage_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    blockage = db.get(RoadBlockage, blockage_id)
    if blockage is None:
        raise HTTPException(status_code=404, detail='Blockage not found')
    if blockage.cleared_at is not None:
        raise HTTPException(status_code=409, detail='Blockage already cleared')
    blockage.cleared_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        actor_id=user.id,
        action='blockage_cleared',
        entity='road_blockage',
        entity_id=blockage.id,
        before={'cleared_at': None},
        after={'cleared_at': blockage.cleared_at.isoformat()},
    )
    route_updates = recompute_active_routes(db, user.id, blockage.id)
    db.commit()
    db.refresh(blockage)
    return {**blockage_response(blockage), **route_updates}


@router.post('/routes/compute')
def compute_route(
    data: RouteComputeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    blockages = db.scalars(
        select(RoadBlockage).where(
            RoadBlockage.verified.is_(True),
            RoadBlockage.cleared_at.is_(None),
        )
    ).all()
    result = routing_client.compute_route(
        origin=(data.from_latitude, data.from_longitude),
        destination=(data.to_latitude, data.to_longitude),
        blockages=[
            {
                'id': item.id,
                'latitude': item.latitude,
                'longitude': item.longitude,
                'radius_km': item.radius_km,
            }
            for item in blockages
        ],
    )
    route = Route(
        from_point={'latitude': data.from_latitude, 'longitude': data.from_longitude},
        to_point={'latitude': data.to_latitude, 'longitude': data.to_longitude},
        geometry=result['geometry'],
        distance_km=result['distance_km'],
        duration_min=result['duration_min'],
        blocked_segments_considered=result['blocked_segments_considered'],
        avoids_blockages=result['avoids_blockages'],
        engine=result['source'],
    )
    db.add(route)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='route_computed',
        entity='route',
        entity_id=route.id,
        after={
            'distance_km': route.distance_km,
            'duration_min': route.duration_min,
            'blocked_segments_considered': route.blocked_segments_considered,
            'avoids_blockages': route.avoids_blockages,
            'source': route.engine,
        },
    )
    db.commit()
    return {'id': route.id, **result}


def blockage_response(blockage: RoadBlockage) -> dict:
    return {
        'id': blockage.id,
        'latitude': blockage.latitude,
        'longitude': blockage.longitude,
        'radius_km': blockage.radius_km,
        'verified': blockage.verified,
        'reported_at': blockage.reported_at.isoformat(),
        'cleared_at': blockage.cleared_at.isoformat() if blockage.cleared_at else None,
        'notes': blockage.notes,
    }


def recompute_active_routes(db: Session, actor_id: int, changed_blockage_id: int) -> dict:
    blockages = db.scalars(
        select(RoadBlockage).where(
            RoadBlockage.verified.is_(True),
            RoadBlockage.cleared_at.is_(None),
        )
    ).all()
    blockage_options = [
        {
            'id': item.id,
            'latitude': item.latitude,
            'longitude': item.longitude,
            'radius_km': item.radius_km,
        }
        for item in blockages
    ]
    assignments = db.scalars(
        select(Assignment).where(
            Assignment.status.in_(('approved', 'accepted', 'en_route', 'on_site')),
            Assignment.route_id.is_not(None),
        )
    ).all()
    recomputed = []
    coordinator_action_required = []
    for assignment in assignments:
        previous_route = db.get(Route, assignment.route_id)
        if previous_route is None:
            continue
        origin = (previous_route.from_point['latitude'], previous_route.from_point['longitude'])
        destination = (previous_route.to_point['latitude'], previous_route.to_point['longitude'])
        result = routing_client.compute_route(origin, destination, blockage_options)
        affected = (
            changed_blockage_id in previous_route.blocked_segments_considered
            or changed_blockage_id in result['blocked_segments_considered']
        )
        if not affected:
            continue
        if result['avoids_blockages']:
            previous_eta = assignment.eta
            updated_route = Route(
                from_point=previous_route.from_point,
                to_point=previous_route.to_point,
                geometry=result['geometry'],
                distance_km=result['distance_km'],
                duration_min=result['duration_min'],
                blocked_segments_considered=result['blocked_segments_considered'],
                avoids_blockages=True,
                engine=result['source'],
            )
            db.add(updated_route)
            db.flush()
            assignment.route_id = updated_route.id
            assignment.eta = datetime.now(timezone.utc) + timedelta(minutes=result['duration_min'])
            append_audit_log(
                db,
                actor_id=actor_id,
                action='active_route_recomputed',
                entity='assignment',
                entity_id=assignment.id,
                before={'route_id': previous_route.id, 'eta': previous_eta.isoformat() if previous_eta else None},
                after={'route_id': updated_route.id, 'eta': assignment.eta.isoformat()},
            )
            recomputed.append({'assignment_id': assignment.id, 'route_id': updated_route.id})
        else:
            previous_blocked = previous_route.avoids_blockages
            previous_route.avoids_blockages = False
            previous_route.blocked_segments_considered = result['blocked_segments_considered']
            coordinator_action_required.append(assignment.id)
            append_audit_log(
                db,
                actor_id=actor_id,
                action='route_blocked_coordinator_action_required',
                entity='assignment',
                entity_id=assignment.id,
                before={
                    'route_id': previous_route.id,
                    'avoids_blockages': previous_blocked,
                },
                after={
                    'route_id': previous_route.id,
                    'avoids_blockages': False,
                    'blockage_id': changed_blockage_id,
                    'blocked_segments_considered': result['blocked_segments_considered'],
                    'message': 'No estimated detour avoids all verified blockages.',
                },
            )
    return {
        'recomputed_routes': recomputed,
        'coordinator_action_required': coordinator_action_required,
    }
