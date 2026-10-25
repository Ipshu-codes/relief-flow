"""Command Station: coordination layer over the shared Rahat backend.

The Command Station is NOT a separate store of incident data. It reads and
writes the same SQLAlchemy/SQLite tables used by the rest of the app
(incidents, needs, assignments, resource_stock, resource_movements,
audit_log, ai_proposals, road_blockages, routes). Automatic SOS forwarding,
volunteer allocation, resource accounting and national coordination all work
through this single shared operational data layer.

Endpoints live under /api/v1 so health checks and the WebSocket stream resolve
to the same canonical backend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import (
    AIProposal,
    Assignment,
    DeliveryConfirmation,
    Incident,
    Location,
    Need,
    Resource,
    ResourceMovement,
    ResourceStock,
    RoadBlockage,
    Route,
    User,
    VolunteerProfile,
)
from ..schemas import (
    AssignmentCreate,
    AssignmentStatusUpdate,
    CoordinationRunCreate,
    MatchRequest,
    MovementStatusPatch,
    ResourceAllocationCreate,
    ResourceStockCreate,
    SOSStateUpdate,
)
from ..security import get_current_user
from ..services.coverage import coverage_by_incident
from ..services.matching import (
    ACTIVE_ASSIGNMENT_STATUSES,
    build_match_candidates,
    resolve_task_window,
)
from ai.coordinator import run_coordination_cycle


router = APIRouter(prefix='/api/v1', tags=['command station'])
MANAGER_ROLES = {'admin', 'coordinator'}

# ---------------------------------------------------------------------------
# Incident state machine
# ---------------------------------------------------------------------------

INCIDENT_STATES = {
    'received',
    'acknowledged',
    'verified',
    'awaiting_dispatch',
    'assigned',
    'responding',
    'on_scene',
    'resolved',
    'cancelled',
}

# Allowed transitions. cancelled is reachable from any non-terminal state.
INCIDENT_TRANSITIONS: dict[str, set[str]] = {
    'received': {'acknowledged', 'cancelled'},
    'acknowledged': {'verified', 'cancelled'},
    'verified': {'awaiting_dispatch', 'cancelled'},
    'awaiting_dispatch': {'assigned', 'cancelled'},
    'assigned': {'responding', 'cancelled'},
    'responding': {'on_scene', 'cancelled'},
    'on_scene': {'resolved', 'cancelled'},
    'resolved': set(),
    'cancelled': set(),
}

TERMINAL_STATES = {'resolved', 'cancelled'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def incident_transition_allowed(current: str, next_state: str) -> bool:
    if next_state == 'cancelled' and current not in TERMINAL_STATES:
        return True
    return next_state in INCIDENT_TRANSITIONS.get(current, set())


def audit_incident_transition(
    db: Session,
    *,
    actor_id: int | None,
    incident: Incident,
    previous: str,
    notes: str | None = None,
) -> None:
    append_audit_log(
        db,
        actor_id=actor_id,
        action='incident_state_transition',
        entity='incident',
        entity_id=incident.id,
        before={'status': previous},
        after={'status': incident.status, 'notes': notes},
    )


def incident_response(db: Session, incident: Incident) -> dict:
    needs = db.scalars(
        select(Need).where(Need.incident_id == incident.id).order_by(Need.urgency.desc(), Need.id)
    ).all()
    return {
        'id': incident.id,
        'incident_type': incident.incident_type,
        'status': incident.status,
        'affected_area': incident.affected_area,
        'started_at': incident.started_at.isoformat() if incident.started_at else None,
        'created_at': incident.created_at.isoformat() if incident.created_at else None,
        'needs': [
            {
                'id': n.id,
                'category': n.category,
                'description': n.description,
                'status': n.status,
                'verification_status': n.verification_status,
                'urgency': n.urgency,
                'quantity_requested': n.quantity_requested,
                'quantity_fulfilled': n.quantity_fulfilled,
                'unit': n.unit,
                'location_id': n.location_id,
            }
            for n in needs
        ],
    }


# ---------------------------------------------------------------------------
# WebSocket stream manager (real-time coordination)
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message, default=str)
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message, default=str))


manager = ConnectionManager()


@router.websocket('/ws/stream')
async def ws_stream(websocket: WebSocket, db: Session = Depends(get_db)):
    """Real-time command station stream.

    Emits incident state changes, new needs, assignment proposals and resource
    movements to connected command-station operators. No separate incident
    store is involved; all data is read from the shared backend tables.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal(
                    websocket, {'type': 'error', 'error': 'invalid_json'}
                )
                continue
            msg_type = message.get('type')
            if msg_type == 'ping':
                await manager.send_personal(
                    websocket, {'type': 'pong', 'at': _now().isoformat()}
                )
            elif msg_type == 'subscribe':
                await manager.send_personal(
                    websocket,
                    {
                        'type': 'subscribed',
                        'channel': message.get('channel', 'all'),
                        'at': _now().isoformat(),
                    },
                )
            else:
                await manager.send_personal(
                    websocket,
                    {'type': 'error', 'error': f'unknown_message_type:{msg_type}'},
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def broadcast_incident_event(*, event_type: str, payload: dict) -> None:
    await manager.broadcast({'type': event_type, 'at': _now().isoformat(), **payload})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get('/health')
def command_station_health(db: Session = Depends(get_db)):
    """Command station health check over the shared backend.

    Confirms the database is reachable and reports incident/need/assignment
    counts from the same tables the rest of the app uses.
    """
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={'status': 'error', 'database': 'unavailable'},
        )
    incident_count = db.scalar(select(func.count(Incident.id))) or 0
    need_count = db.scalar(select(func.count(Need.id))) or 0
    assignment_count = db.scalar(select(func.count(Assignment.id))) or 0
    return {
        'status': 'ok',
        'database': 'connected',
        'layer': 'command_station',
        'counts': {
            'incidents': incident_count,
            'needs': need_count,
            'assignments': assignment_count,
        },
    }


# ---------------------------------------------------------------------------
# Incidents: state machine
# ---------------------------------------------------------------------------

@router.get('/incidents')
def list_incidents(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List incidents from the shared backend, optionally filtered by state."""
    statement = select(Incident).order_by(Incident.started_at.desc(), Incident.id.desc())
    if status is not None:
        if status not in INCIDENT_STATES:
            raise HTTPException(status_code=422, detail=f'Unknown incident status: {status}')
        statement = statement.where(Incident.status == status)
    return [incident_response(db, row) for row in db.scalars(statement).all()]


@router.get('/incidents/{incident_id}')
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    return incident_response(db, incident)


@router.post('/incidents', status_code=201)
def create_incident(
    incident_type: str = Query(min_length=1, max_length=40),
    affected_area: str = Query(min_length=1, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    incident = Incident(
        incident_type=incident_type,
        affected_area=affected_area,
        started_at=_now(),
        status='received',
    )
    db.add(incident)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='incident_created',
        entity='incident',
        entity_id=incident.id,
        after={
            'incident_type': incident_type,
            'affected_area': affected_area,
            'status': 'received',
        },
    )
    db.commit()
    db.refresh(incident)
    return incident_response(db, incident)


@router.post('/incidents/{incident_id}/transition')
def transition_incident(
    incident_id: int,
    data: SOSStateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Advance an incident through the controlled state machine.

    Allowed transitions: received -> acknowledged -> verified ->
    awaiting_dispatch -> assigned -> responding -> on_scene -> resolved.
    cancelled is reachable from any non-terminal state. Every transition is
    recorded in the hash-linked audit_log.
    """
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    next_state = data.state
    if next_state not in INCIDENT_STATES:
        raise HTTPException(status_code=422, detail=f'Unknown state: {next_state}')
    if not incident_transition_allowed(incident.status, next_state):
        raise HTTPException(
            status_code=409,
            detail=(
                f'Cannot transition incident {incident_id} from '
                f'{incident.status} to {next_state}'
            ),
        )
    previous = incident.status
    incident.status = next_state
    audit_incident_transition(
        db, actor_id=user.id, incident=incident, previous=previous, notes=data.notes
    )
    db.commit()
    db.refresh(incident)
    return incident_response(db, incident)


@router.get('/incidents/{incident_id}/audit-trail')
def incident_audit_trail(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    entries = db.scalars(
        select(AIProposal)
        .where(AIProposal.incident_id == incident_id)
        .order_by(AIProposal.created_at.desc())
    ).all()
    # Also pull audit_log entries for the incident itself.
    from ..models import AuditLog  # local import to avoid circular concerns

    log_entries = db.scalars(
        select(AuditLog).where(
            AuditLog.entity == 'incident',
            AuditLog.entity_id == str(incident_id),
        ).order_by(AuditLog.created_at.desc())
    ).all()
    return {
        'incident_id': incident_id,
        'audit_log': [
            {
                'id': e.id,
                'actor_id': e.actor_id,
                'action': e.action,
                'entity': e.entity,
                'entity_id': e.entity_id,
                'before_json': e.before_json,
                'after_json': e.after_json,
                'created_at': e.created_at.isoformat() if e.created_at else None,
            }
            for e in log_entries
        ],
        'ai_proposals': [
            {
                'id': p.id,
                'batch_uuid': p.batch_uuid,
                'proposal_type': p.proposal_type,
                'status': p.status,
                'source': p.source,
                'rationale': p.rationale,
                'confidence': p.confidence,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            }
            for p in entries
        ],
    }


# ---------------------------------------------------------------------------
# Volunteer dispatch engine
# ---------------------------------------------------------------------------

@router.post('/incidents/{incident_id}/dispatch-wave')
def dispatch_wave(
    incident_id: int,
    data: MatchRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send a timed invitation wave to eligible volunteers for an incident's
    open needs.

    Eligibility: verified skills matching the need, availability window covering
    the task window, within max_travel_km, not already assigned to an active
    assignment, and availability_status == 'available'. Returns ranked
    candidates so the coordinator can invite the top candidates first.
    """
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    if incident.status in TERMINAL_STATES:
        raise HTTPException(status_code=409, detail='Cannot dispatch to a terminal incident')

    data = data or MatchRequest()
    starts_at, ends_at = resolve_task_window(data.starts_at, data.ends_at)
    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(('open', 'partially_fulfilled', 'in_progress')),
        ).order_by(Need.urgency.desc(), Need.id)
    ).all()

    waves = []
    for need in needs:
        try:
            candidates = build_match_candidates(db, need, starts_at, ends_at)
        except ValueError:
            candidates = []
        active_ids = set(
            db.scalars(
                select(Assignment.volunteer_id).where(
                    Assignment.need_id == need.id,
                    Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                )
            )
        )
        eligible = [c for c in candidates if c['volunteer_id'] not in active_ids]
        waves.append({
            'need_id': need.id,
            'need_description': need.description,
            'category': need.category,
            'urgency': need.urgency,
            'remaining_quantity': max(0, need.quantity_requested - need.quantity_fulfilled),
            'unit': need.unit,
            'wave_sent_at': _now().isoformat(),
            'eligible_volunteers': eligible[:5],
            'invite_count': len(eligible[:5]),
        })
    return {'incident_id': incident_id, 'waves': waves}


@router.post('/assignments', status_code=201)
def create_assignment(
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reserve an assignment for a volunteer (command station allocation).

    Validates the volunteer is eligible, the need is open, and no duplicate
    active assignment exists for the same need+volunteer. The assignment is
    created in 'proposed' state and requires coordinator approval to activate.
    """
    require_manager(user)
    need = db.get(Need, data.need_id)
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    if need.status in {'fulfilled', 'closed', 'rejected'}:
        raise HTTPException(status_code=409, detail='Need is not available for assignment')
    profile = db.get(VolunteerProfile, data.volunteer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail='Volunteer not found')
    if profile.availability_status != 'available':
        raise HTTPException(status_code=409, detail='Volunteer is not available')

    duplicate = db.scalars(
        select(Assignment).where(
            Assignment.need_id == data.need_id,
            Assignment.volunteer_id == data.volunteer_id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail='Volunteer already has an active assignment for this need',
        )

    starts_at, ends_at = resolve_task_window(data.starts_at, data.ends_at)
    assignment = Assignment(
        need_id=data.need_id,
        volunteer_id=data.volunteer_id,
        status='proposed',
        proposed_by='coordinator',
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(assignment)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='assignment_reserved',
        entity='assignment',
        entity_id=assignment.id,
        after={
            'need_id': data.need_id,
            'volunteer_id': data.volunteer_id,
            'status': 'proposed',
        },
    )
    db.commit()
    db.refresh(assignment)
    return {
        'id': assignment.id,
        'need_id': assignment.need_id,
        'volunteer_id': assignment.volunteer_id,
        'status': assignment.status,
        'proposed_by': assignment.proposed_by,
        'starts_at': assignment.starts_at.isoformat() if assignment.starts_at else None,
        'ends_at': assignment.ends_at.isoformat() if assignment.ends_at else None,
    }


@router.post('/assignments/{assignment_id}/confirm')
def confirm_assignment(
    assignment_id: int,
    data: AssignmentStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Volunteer confirms (accepts) or rejects a proposed assignment.

    On accept: status moves proposed -> accepted. On reject: status moves to
    cancelled and the command station can trigger automatic fallback to the
    next eligible volunteer.
    """
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    if profile is None or profile.user_id != user.id:
        raise HTTPException(status_code=403, detail='Only the assigned volunteer can confirm')
    if assignment.status != 'proposed':
        raise HTTPException(status_code=409, detail='Only proposed assignments can be confirmed')

    next_state = data.status
    if next_state not in {'en_route', 'cancelled'}:
        raise HTTPException(
            status_code=422, detail='Use en_route to accept, cancelled to reject'
        )

    previous = assignment.status
    if next_state == 'en_route':
        assignment.status = 'accepted'
    else:
        assignment.status = 'cancelled'

    append_audit_log(
        db,
        actor_id=user.id,
        action='assignment_confirmed',
        entity='assignment',
        entity_id=assignment.id,
        before={'status': previous},
        after={'status': assignment.status},
    )
    db.commit()
    db.refresh(assignment)
    return {
        'id': assignment.id,
        'status': assignment.status,
        'previous': previous,
    }


@router.post('/incidents/{incident_id}/fallback')
def automatic_fallback(
    incident_id: int,
    data: MatchRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Automatic fallback: when a volunteer does not confirm in time or
    rejects, re-run eligibility for the incident's open needs and propose the
    next best available volunteer."""
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    data = data or MatchRequest()
    starts_at, ends_at = resolve_task_window(data.starts_at, data.ends_at)
    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(('open', 'partially_fulfilled', 'in_progress')),
        ).order_by(Need.urgency.desc(), Need.id)
    ).all()

    fallbacks = []
    for need in needs:
        try:
            candidates = build_match_candidates(db, need, starts_at, ends_at)
        except ValueError:
            candidates = []
        active_ids = set(
            db.scalars(
                select(Assignment.volunteer_id).where(
                    Assignment.need_id == need.id,
                    Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                )
            )
        )
        eligible = [c for c in candidates if c['volunteer_id'] not in active_ids]
        fallbacks.append({
            'need_id': need.id,
            'fallback_volunteers': eligible[:3],
        })

    return {'incident_id': incident_id, 'fallbacks': fallbacks}


# ---------------------------------------------------------------------------
# Resource ledger
# ---------------------------------------------------------------------------

@router.get('/incidents/{incident_id}/resource-ledger')
def resource_ledger(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Resource ledger for an incident: requested quantities, pledges
    (allocations), dispatches, receipts, remaining needs, and duplicate
    allocation warnings."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    needs = db.scalars(
        select(Need).where(Need.incident_id == incident_id).order_by(Need.urgency.desc(), Need.id)
    ).all()
    ledger = []
    for need in needs:
        movements = db.scalars(
            select(ResourceMovement).where(ResourceMovement.need_id == need.id)
        ).all()
        active = [m for m in movements if m.status != 'cancelled']
        allocated = sum(m.quantity for m in active)
        dispatched = sum(
            m.quantity for m in active if m.status in {'dispatched', 'delivered', 'confirmed'}
        )
        delivered = sum(m.quantity for m in active if m.status in {'delivered', 'confirmed'})
        confirmed = need.quantity_fulfilled
        remaining = max(0.0, need.quantity_requested - confirmed)
        unconfirmed = max(0.0, delivered - confirmed)
        duplicate_warning = allocated > need.quantity_requested - need.quantity_fulfilled
        ledger.append({
            'need_id': need.id,
            'category': need.category,
            'description': need.description,
            'unit': need.unit,
            'quantity_requested': need.quantity_requested,
            'quantity_fulfilled': need.quantity_fulfilled,
            'quantity_remaining': remaining,
            'allocated': allocated,
            'dispatched': dispatched,
            'delivered': delivered,
            'confirmed_received': confirmed,
            'unconfirmed_delivered': unconfirmed,
            'status': need.status,
            'verification_status': need.verification_status,
            'duplicate_warning': duplicate_warning,
            'movements': [
                {
                    'id': m.id,
                    'resource_id': m.resource_id,
                    'stock_id': m.stock_id,
                    'quantity': m.quantity,
                    'quantity_confirmed': m.quantity_confirmed,
                    'status': m.status,
                    'dispatched_at': m.dispatched_at.isoformat() if m.dispatched_at else None,
                    'delivered_at': m.delivered_at.isoformat() if m.delivered_at else None,
                }
                for m in movements
            ],
        })
    return {
        'incident_id': incident_id,
        'incident_status': incident.status,
        'needs': ledger,
    }


@router.post('/incidents/{incident_id}/reconcile')
def reconcile_ledger(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manual reconciliation: correct quantity_fulfilled on needs based on
    confirmed deliveries and close fully met needs. Records an audit entry."""
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    needs = db.scalars(select(Need).where(Need.incident_id == incident_id)).all()
    reconciled = []
    for need in needs:
        total_received = db.scalar(
            select(func.coalesce(func.sum(DeliveryConfirmation.quantity_received), 0.0))
            .join(ResourceMovement, ResourceMovement.id == DeliveryConfirmation.movement_id)
            .where(ResourceMovement.need_id == need.id)
        ) or 0.0
        before = {'quantity_fulfilled': need.quantity_fulfilled, 'status': need.status}
        need.quantity_fulfilled = min(need.quantity_requested, total_received)
        if need.quantity_fulfilled >= need.quantity_requested:
            need.status = 'fulfilled'
        elif need.quantity_fulfilled > 0:
            need.status = 'partially_fulfilled'
        else:
            need.status = 'open'
        append_audit_log(
            db,
            actor_id=user.id,
            action='ledger_reconciled',
            entity='need',
            entity_id=need.id,
            before=before,
            after={'quantity_fulfilled': need.quantity_fulfilled, 'status': need.status},
        )
        reconciled.append({
            'need_id': need.id,
            'before': before,
            'after': {'quantity_fulfilled': need.quantity_fulfilled, 'status': need.status},
        })
    db.commit()
    return {'incident_id': incident_id, 'reconciled': reconciled}


@router.get('/incidents/{incident_id}/duplicate-warnings')
def duplicate_warnings(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Duplicate warnings: needs where active allocations exceed remaining
    need."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    warnings = []
    needs = db.scalars(select(Need).where(Need.incident_id == incident_id)).all()
    for need in needs:
        movements = db.scalars(
            select(ResourceMovement).where(ResourceMovement.need_id == need.id)
        ).all()
        active = [m for m in movements if m.status != 'cancelled']
        allocated = sum(m.quantity for m in active)
        remaining = max(0.0, need.quantity_requested - need.quantity_fulfilled)
        if allocated > remaining:
            warnings.append({
                'type': 'over_allocation',
                'need_id': need.id,
                'allocated': allocated,
                'remaining_before_allocation': remaining,
                'excess': allocated - remaining,
            })
    return {'incident_id': incident_id, 'warnings': warnings}


# ---------------------------------------------------------------------------
# Map and routing
# ---------------------------------------------------------------------------

@router.get('/road-hazards')
def list_road_hazards(
    verified_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List road hazards (blockages) with freshness labels. Verified hazards
    are command-station-confirmed obstructions; unverified are reported but
    not yet confirmed."""
    statement = select(RoadBlockage).order_by(RoadBlockage.reported_at.desc())
    if verified_only:
        statement = statement.where(RoadBlockage.verified.is_(True))
    rows = db.scalars(statement).all()
    now = _now()
    hazards = []
    for h in rows:
        age_minutes = (
            (now - h.reported_at).total_seconds() / 60 if h.reported_at else 0
        )
        freshness = (
            'fresh' if age_minutes < 60 else 'recent' if age_minutes < 360 else 'stale'
        )
        hazards.append({
            'id': h.id,
            'latitude': h.latitude,
            'longitude': h.longitude,
            'radius_km': h.radius_km,
            'road_name': h.road_name,
            'location_text': h.location_text,
            'status': h.status,
            'verified': h.verified,
            'reported_by': h.reported_by,
            'reported_at': h.reported_at.isoformat() if h.reported_at else None,
            'expires_at': h.expires_at.isoformat() if h.expires_at else None,
            'cleared_at': h.cleared_at.isoformat() if h.cleared_at else None,
            'freshness': freshness,
            'notes': h.notes,
        })
    return {'road_hazards': hazards}


@router.post('/road-hazards/{hazard_id}/verify')
def verify_road_hazard(
    hazard_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    hazard = db.get(RoadBlockage, hazard_id)
    if hazard is None:
        raise HTTPException(status_code=404, detail='Road hazard not found')
    if hazard.verified:
        return {'id': hazard.id, 'verified': True, 'message': 'Already verified'}
    hazard.verified = True
    append_audit_log(
        db,
        actor_id=user.id,
        action='road_hazard_verified',
        entity='road_blockage',
        entity_id=hazard.id,
        after={'verified': True, 'status': hazard.status},
    )
    db.commit()
    db.refresh(hazard)
    return {'id': hazard.id, 'verified': True, 'message': 'Road hazard verified'}


@router.get('/incidents/{incident_id}/routes')
def incident_routes(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Route alternatives for an incident's needs: existing computed routes
    linked to assignments, showing distance, duration, and whether blockages
    were avoided."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    assignments = db.scalars(
        select(Assignment).join(Need, Need.id == Assignment.need_id).where(
            Need.incident_id == incident_id,
        )
    ).all()
    routes = []
    for a in assignments:
        route = db.get(Route, a.route_id) if a.route_id else None
        if route:
            routes.append({
                'assignment_id': a.id,
                'need_id': a.need_id,
                'volunteer_id': a.volunteer_id,
                'route_id': route.id,
                'from_point': route.from_point,
                'to_point': route.to_point,
                'distance_km': route.distance_km,
                'duration_min': route.duration_min,
                'avoids_blockages': route.avoids_blockages,
                'engine': route.engine,
                'computed_at': route.computed_at.isoformat() if route.computed_at else None,
                'assignment_status': a.status,
            })
    return {'incident_id': incident_id, 'routes': routes}


@router.get('/incidents/{incident_id}/route-change-notifications')
def route_change_notifications(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Route-change notifications: incidents whose assigned routes pass near
    a verified road blockage, so the command station can re-route."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    hazards = db.scalars(
        select(RoadBlockage).where(RoadBlockage.verified.is_(True))
    ).all()
    assignments = db.scalars(
        select(Assignment).join(Need, Need.id == Assignment.need_id).where(
            Need.incident_id == incident_id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ).all()
    notifications = []
    for a in assignments:
        route = db.get(Route, a.route_id) if a.route_id else None
        if not route:
            continue
        for h in hazards:
            notifications.append({
                'assignment_id': a.id,
                'need_id': a.need_id,
                'volunteer_id': a.volunteer_id,
                'hazard_id': h.id,
                'hazard_location_text': h.location_text,
                'hazard_latitude': h.latitude,
                'hazard_longitude': h.longitude,
                'route_distance_km': route.distance_km,
                'avoids_blockages': route.avoids_blockages,
                'action': (
                    'review_route' if route.avoids_blockages else 'reroute_required'
                ),
            })
    return {'incident_id': incident_id, 'notifications': notifications}


# ---------------------------------------------------------------------------
# AI coordination (over the same shared backend)
# ---------------------------------------------------------------------------

@router.post('/incidents/{incident_id}/coordinate')
async def coordinate_incident(
    incident_id: int,
    data: CoordinationRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run the AI coordination cycle over the shared backend state.

    The model recommends assignments and allocations using real database
    state (needs, volunteers, skills, stock, routes). Deterministic backend
    logic enforces capacity, permissions, safety and assignments; the model
    never invents road closures, assumes SOS delivery, or confirms receipts.
    Output is a set of proposed AI proposals for human review.
    """
    require_manager(user)
    try:
        result = await run_coordination_cycle(
            db,
            actor_id=user.id,
            incident_id=incident_id,
            batch_uuid=str(data.client_uuid),
            starts_at=data.starts_at,
            ends_at=data.ends_at,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.get('/ai/status')
def ai_status():
    """Local Ollama model availability for command station AI coordination."""
    from ..config import OLLAMA_URL, OLLAMA_MODEL

    import httpx

    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f'{OLLAMA_URL}/api/tags')
            response.raise_for_status()
        payload = response.json()
        models = payload.get('models', []) if isinstance(payload, dict) else []
        model_available = any(
            isinstance(m, dict) and m.get('name') == OLLAMA_MODEL for m in models
        )
        return {
            'reachable': True,
            'model': OLLAMA_MODEL,
            'model_available': model_available,
            'fallback_active': not model_available,
        }
    except Exception:
        return {
            'reachable': False,
            'model': OLLAMA_MODEL,
            'model_available': False,
            'fallback_active': True,
        }


# ---------------------------------------------------------------------------
# Insights: coverage analytics
# ---------------------------------------------------------------------------

@router.get('/coverage')
def coverage(
    incident_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Coverage analytics: open needs by location, volunteer availability,
    and unserved gaps over the shared backend."""
    if incident_id is not None:
        return coverage_by_incident(db, incident_id)
    # Incident-agnostic summary across all open incidents.
    incidents = db.scalars(select(Incident).order_by(Incident.id.desc())).all()
    return {
        'incidents': [
            {
                'incident_id': inc.id,
                'incident_type': inc.incident_type,
                'status': inc.status,
                'coverage': coverage_by_incident(db, inc.id),
            }
            for inc in incidents
        ]
    }
