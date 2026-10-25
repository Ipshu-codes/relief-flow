from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai.road_tasks import parse_road_update
from ..db import get_db
from ..geo.routing import EstimateRoutingClient
from ..ledger import append_audit_log
from ..models import Assignment, RoadBlockage, RoadUpdateReport, Route, User
from ..schemas import (
    RoadBlockageCreate,
    RoadUpdateCreate,
    RoadUpdateVerification,
    RouteComputeRequest,
)
from ..security import get_current_user

router = APIRouter(tags=['routing'])
routing_client = EstimateRoutingClient()


def require_coordinator(user: User) -> None:
    if user.role not in {'coordinator', 'admin'}:
        raise HTTPException(status_code=403, detail='Coordinator role required')


@router.post('/road-updates', status_code=201)
async def create_road_update(
    data: RoadUpdateCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    client_uuid = str(data.client_uuid)
    existing = db.scalar(
        select(RoadUpdateReport).where(RoadUpdateReport.client_uuid == client_uuid)
    )
    if existing is not None:
        response.status_code = 200
        return road_update_response(existing)

    parsed, source = await parse_road_update(db, data.text)
    report = RoadUpdateReport(
        client_uuid=client_uuid,
        raw_text=data.text.strip(),
        parsed_json={**parsed.model_dump(mode='json'), 'source': source},
        parse_status='parsed' if source == 'ai' else 'fallback',
        review_status='pending',
        created_by=user.id,
    )
    db.add(report)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='road_update_received',
        entity='road_update_report',
        entity_id=report.id,
        after={
            'client_uuid': report.client_uuid,
            'parse_status': report.parse_status,
            'review_status': report.review_status,
            'update_count': len(parsed.updates),
            'source': source,
        },
    )
    db.commit()
    db.refresh(report)
    return road_update_response(report)


@router.get('/road-updates')
def list_road_updates(
    review_status: str = Query(default='pending', pattern='^(pending|verified|rejected)$'),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    reports = db.scalars(
        select(RoadUpdateReport)
        .where(RoadUpdateReport.review_status == review_status)
        .order_by(RoadUpdateReport.created_at.desc(), RoadUpdateReport.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        'items': [road_update_response(report) for report in reports],
        'limit': limit,
        'offset': offset,
    }


@router.post('/road-updates/{report_id}/verify')
def verify_road_update(
    report_id: int,
    data: RoadUpdateVerification,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    report = db.get(RoadUpdateReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail='Road update not found')
    if report.review_status != 'pending':
        raise HTTPException(status_code=409, detail='Road update has already been reviewed')
    parsed_updates = (report.parsed_json or {}).get('updates', [])
    selected_indexes = {item.update_index for item in data.updates}
    if not parsed_updates or selected_indexes != set(range(len(parsed_updates))):
        raise HTTPException(
            status_code=422,
            detail='Verification must provide coordinator coordinates for every parsed update',
        )

    verified_at = datetime.now(timezone.utc)
    created_blockages = []
    recomputed_routes = []
    coordinator_action_required = []
    for confirmation in data.updates:
        parsed = parsed_updates[confirmation.update_index]
        expires_at = verified_at + timedelta(hours=confirmation.expires_in_hours)
        details = ' '.join(filter(None, (
            parsed.get('road_name'),
            parsed.get('location_text'),
            parsed.get('notes'),
        )))
        blockage = RoadBlockage(
            latitude=confirmation.latitude,
            longitude=confirmation.longitude,
            radius_km=confirmation.radius_km,
            road_name=parsed.get('road_name'),
            location_text=parsed.get('location_text'),
            status=parsed['status'],
            reported_by=user.id,
            verified=True,
            reported_at=report.created_at,
            expires_at=expires_at,
            notes=(details or report.raw_text)[:1000],
        )
        db.add(blockage)
        db.flush()
        created_blockages.append(blockage)
        append_audit_log(
            db,
            actor_id=user.id,
            action='road_blockage_verified_from_update',
            entity='road_blockage',
            entity_id=blockage.id,
            after={
                'road_name': blockage.road_name,
                'location_text': blockage.location_text,
                'latitude': blockage.latitude,
                'longitude': blockage.longitude,
                'status': blockage.status,
                'expires_at': blockage.expires_at.isoformat(),
                'source_report_id': report.id,
            },
        )
        route_update = recompute_active_routes(db, user.id, blockage.id)
        recomputed_routes.extend(route_update['recomputed_routes'])
        coordinator_action_required.extend(route_update['coordinator_action_required'])

    before = {'review_status': report.review_status}
    report.review_status = 'verified'
    report.reviewed_by = user.id
    report.reviewed_at = verified_at
    append_audit_log(
        db,
        actor_id=user.id,
        action='road_update_report_verified',
        entity='road_update_report',
        entity_id=report.id,
        before=before,
        after={
            'review_status': report.review_status,
            'reviewed_by': user.id,
            'blockage_ids': [item.id for item in created_blockages],
        },
    )
    db.commit()
    for blockage in created_blockages:
        db.refresh(blockage)
    return {
        'road_update': road_update_response(report),
        'blockages': [blockage_response(item) for item in created_blockages],
        'recomputed_routes': recomputed_routes,
        'coordinator_action_required': coordinator_action_required,
    }


@router.post('/road-updates/{report_id}/reject')
def reject_road_update(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    report = db.get(RoadUpdateReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail='Road update not found')
    if report.review_status != 'pending':
        raise HTTPException(status_code=409, detail='Road update has already been reviewed')
    report.review_status = 'rejected'
    report.reviewed_by = user.id
    report.reviewed_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        actor_id=user.id,
        action='road_update_report_rejected',
        entity='road_update_report',
        entity_id=report.id,
        before={'review_status': 'pending'},
        after={'review_status': 'rejected', 'reviewed_by': user.id},
    )
    db.commit()
    return road_update_response(report)


@router.get('/blockages')
def list_blockages(
    include_cleared: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    query = select(RoadBlockage).order_by(RoadBlockage.reported_at.desc(), RoadBlockage.id.desc())
    if not include_cleared:
        query = query.where(RoadBlockage.cleared_at.is_(None))
    blockages = db.scalars(query).all()
    return {'items': [blockage_response(item) for item in blockages]}


@router.post('/blockages', status_code=201)
def create_blockage(
    data: RoadBlockageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    reported_at = datetime.now(timezone.utc)
    blockage = RoadBlockage(
        latitude=data.latitude,
        longitude=data.longitude,
        radius_km=data.radius_km,
        status='blocked',
        reported_by=user.id,
        verified=True,
        reported_at=reported_at,
        expires_at=reported_at + timedelta(hours=data.expires_in_hours),
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
            'status': blockage.status,
            'expires_at': blockage.expires_at.isoformat(),
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
            or_(RoadBlockage.expires_at.is_(None), RoadBlockage.expires_at > datetime.now(timezone.utc)),
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
    expires_at = blockage.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    stale = expires_at is not None and expires_at <= datetime.now(timezone.utc)
    return {
        'id': blockage.id,
        'latitude': blockage.latitude,
        'longitude': blockage.longitude,
        'radius_km': blockage.radius_km,
        'road_name': blockage.road_name,
        'location_text': blockage.location_text,
        'status': blockage.status,
        'verified': blockage.verified,
        'reported_at': blockage.reported_at.isoformat(),
        'expires_at': expires_at.isoformat() if expires_at else None,
        'stale': stale,
        'confidence': 'low' if stale else 'high' if blockage.verified else 'low',
        'cleared_at': blockage.cleared_at.isoformat() if blockage.cleared_at else None,
        'notes': blockage.notes,
    }


def road_update_response(report: RoadUpdateReport) -> dict:
    return {
        'id': report.id,
        'client_uuid': report.client_uuid,
        'raw_text': report.raw_text,
        'parsed': report.parsed_json,
        'parse_status': report.parse_status,
        'review_status': report.review_status,
        'created_by': report.created_by,
        'created_at': report.created_at.isoformat(),
        'reviewed_by': report.reviewed_by,
        'reviewed_at': report.reviewed_at.isoformat() if report.reviewed_at else None,
    }


def recompute_active_routes(db: Session, actor_id: int, changed_blockage_id: int) -> dict:
    blockages = db.scalars(
        select(RoadBlockage).where(
            RoadBlockage.verified.is_(True),
            RoadBlockage.cleared_at.is_(None),
            or_(RoadBlockage.expires_at.is_(None), RoadBlockage.expires_at > datetime.now(timezone.utc)),
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
