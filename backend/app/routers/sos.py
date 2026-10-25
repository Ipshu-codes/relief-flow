import hashlib
import hmac
import secrets
import threading
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from ai.sos_tasks import interpret_sos_event
from ..db import get_db
from .. import security
from ..ledger import append_audit_log
from ..models import Assignment, Gateway, Incident, RawReport, SOSAcknowledgement, SOSEvent, SyncBatch, User
from ..schemas import GatewayCreate, SOSBatchCreate, SOSDispatch, SOSEventCreate, SOSLocationUpdate, SOSResolve, SOSStateUpdate, SMSIncomingCreate
from ..security import get_current_user, require_role
from ..services.sos import has_valid_location, haversine_km, parse_compact_sos

router = APIRouter(tags=['offline SOS'])
optional_bearer = HTTPBearer(auto_error=False)
RATE_WINDOW = timedelta(minutes=1)
SENDER_LIMIT_PER_MINUTE = 10
GATEWAY_LIMIT_PER_MINUTE = 120
_recent_requests: dict[str, list[datetime]] = {}
_rate_lock = threading.Lock()
SOS_STATE_TRANSITIONS = {
    'new': {'received', 'acknowledged', 'cancelled'},
    'received': {'acknowledged', 'cancelled'},
    'acknowledged': {'verified', 'awaiting_dispatch', 'cancelled'},
    'verified': {'awaiting_dispatch', 'cancelled'},
    'awaiting_dispatch': {'assigned', 'cancelled'},
    'assigned': {'responding', 'cancelled'},
    'responding': {'on_scene', 'cancelled'},
    'on_scene': {'resolved', 'cancelled'},
}


def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return get_current_user(credentials, db)


def key_digest(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


def get_gateway(db: Session, raw_key: str | None) -> Gateway | None:
    if not raw_key:
        return None
    digest = key_digest(raw_key)
    gateway = db.scalar(select(Gateway).where(Gateway.api_key_hash == digest, Gateway.is_active.is_(True)))
    if gateway is None:
        raise HTTPException(status_code=401, detail='Invalid gateway key')
    if not hmac.compare_digest(gateway.api_key_hash, digest):
        raise HTTPException(status_code=401, detail='Invalid gateway key')
    gateway.last_seen_at = datetime.now(timezone.utc)
    return gateway


def rate_limited(key: str, maximum: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - RATE_WINDOW
    with _rate_lock:
        current = [timestamp for timestamp in _recent_requests.get(key, []) if timestamp > cutoff]
        if len(current) >= maximum:
            _recent_requests[key] = current
            return True
        current.append(now)
        _recent_requests[key] = current
        if len(_recent_requests) > 5000:
            for stale_key in [key for key, values in _recent_requests.items() if not values or values[-1] <= cutoff]:
                _recent_requests.pop(stale_key, None)
    return False


def normalized_event_payload(data: SOSEventCreate) -> dict:
    compact = parse_compact_sos(data.message)
    latitude = data.latitude
    longitude = data.longitude
    category = data.category.value if data.category is not None else None
    message = data.message.strip()
    if compact is not None:
        if category is not None and category != compact['category']:
            raise ValueError('Selected category conflicts with compact SOS category')
        category = compact['category']
        latitude = latitude if latitude is not None else compact['latitude']
        longitude = longitude if longitude is not None else compact['longitude']
        message = compact['message']
    valid_location = has_valid_location(latitude, longitude)
    if not valid_location:
        latitude = None
        longitude = None
    return {
        'client_uuid': str(data.client_uuid),
        'incident_id': data.incident_id,
        'sender_ref': data.sender_ref.strip() if data.sender_ref else None,
        'latitude': latitude,
        'longitude': longitude,
        'location_accuracy_m': data.location_accuracy_m,
        'has_location': valid_location,
        'category': category or 'OTHER',
        'urgency': data.urgency or 3,
        'urgency_override': data.urgency is not None,
        'message': message[:500],
        'created_at_device': data.created_at_device,
        'channel': data.channel,
        'relay_path': data.relay_path,
        'address': data.address.model_dump() if data.address is not None else None,
    }


def create_event(
    db: Session,
    *,
    data: SOSEventCreate,
    user: User | None,
    gateway: Gateway | None = None,
    force_channel: str | None = None,
    anonymous_source: str | None = None,
) -> tuple[SOSEvent, bool]:
    values = normalized_event_payload(data)
    existing = db.scalar(select(SOSEvent).where(SOSEvent.client_uuid == values['client_uuid']))
    if existing is not None:
        return existing, False

    sender_key = values['sender_ref']
    rate_key = (
        f'sender:{sender_key.casefold()}' if sender_key
        else f'ip:{anonymous_source}' if anonymous_source
        else None
    )
    if rate_key and rate_limited(rate_key, SENDER_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail='Sender rate limit exceeded')
    if gateway is not None and rate_limited(f'gateway:{gateway.id}', GATEWAY_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail='Gateway rate limit exceeded')

    duplicate_of = None
    if values['has_location'] and values['sender_ref']:
        recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent_events = db.scalars(
            select(SOSEvent).where(
                SOSEvent.sender_ref == values['sender_ref'],
                SOSEvent.has_location.is_(True),
                SOSEvent.received_at_server >= recent_cutoff,
            ).order_by(SOSEvent.received_at_server.desc()).limit(50)
        ).all()
        for candidate in recent_events:
            distance = haversine_km(
                (values['latitude'], values['longitude']),
                (candidate.latitude, candidate.longitude),
            )
            if distance <= 1.0:
                duplicate_of = candidate.id
                break

    if values['incident_id'] is not None and db.get(Incident, values['incident_id']) is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    values['channel'] = force_channel if force_channel else values['channel']
    event = SOSEvent(
        **values,
        reporter_user_id=user.id if user else None,
        sender_verified=user is not None or gateway is not None,
        gateway_id=gateway.id if gateway else None,
        duplicate_of=duplicate_of,
        status='new',
        transmission_status='received',
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        duplicate = db.scalar(select(SOSEvent).where(SOSEvent.client_uuid == values['client_uuid']))
        if duplicate is not None:
            return duplicate, False
        raise
    append_audit_log(
        db,
        actor_id=user.id if user else None,
        action='sos_received',
        entity='sos_event',
        entity_id=event.id,
        after={
            'client_uuid': event.client_uuid,
            'category': event.category,
            'has_location': event.has_location,
            'channel': event.channel,
            'sender_verified': event.sender_verified,
            'duplicate_of': event.duplicate_of,
        },
    )
    return event, True


def event_response(event: SOSEvent) -> dict:
    return {
        'id': event.id,
        'client_uuid': event.client_uuid,
        'incident_id': event.incident_id,
        'sender_ref': event.sender_ref,
        'sender_verified': event.sender_verified,
        'latitude': event.latitude,
        'longitude': event.longitude,
        'location_accuracy_m': event.location_accuracy_m,
        'address': event.address,
        'location_updated_at': event.location_updated_at.isoformat() if event.location_updated_at else None,
        'has_location': event.has_location,
        'category': event.category,
        'urgency': event.urgency,
        'urgency_override': event.urgency_override,
        'interpretation': event.parsed_json,
        'message': event.message,
        'created_at_device': event.created_at_device.isoformat() if event.created_at_device else None,
        'received_at_server': event.received_at_server.isoformat(),
        'channel': event.channel,
        'relay_path': event.relay_path,
        'transmission_status': event.transmission_status,
        'status': event.status,
        'duplicate_of': event.duplicate_of,
        'linked_need_id': event.linked_need_id,
        'assignment_id': event.assignment_id,
    }


def receipt_token(event: SOSEvent) -> str:
    if len(security.JWT_SECRET) < 32:
        raise HTTPException(status_code=503, detail='Initialize JWT_SECRET before accepting SOS receipts')
    return hmac.new(
        security.JWT_SECRET.encode(), f'sos-receipt:{event.id}:{event.client_uuid}'.encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post('/sos')
def submit_sos(
    data: SOSEventCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
    x_gateway_key: str | None = Header(default=None),
):
    gateway = get_gateway(db, x_gateway_key)
    try:
        event, created = create_event(
            db,
            data=data,
            user=user,
            gateway=gateway,
            anonymous_source=request.client.host if request.client else None,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(event)
    if created:
        background_tasks.add_task(interpret_sos_event, event.id)
    return JSONResponse(
        status_code=201 if created else 200,
        content=jsonable_encoder({
            **event_response(event), 'result': 'created' if created else 'duplicate',
            'receipt_token': receipt_token(event),
        }),
    )


@router.post('/sms/incoming')
def sms_incoming(
    data: SMSIncomingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return ingest_relay_message(data, background_tasks, db, channel='sms')


@router.post('/sms/simulate')
def simulate_relay_message(
    data: SMSIncomingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    return ingest_relay_message(data, background_tasks, db, channel=data.channel)


def ingest_relay_message(
    data: SMSIncomingCreate,
    background_tasks: BackgroundTasks,
    db: Session,
    *,
    channel: str,
):
    minute_bucket = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
    client_uuid = str(data.client_uuid or uuid5(NAMESPACE_URL, f'{data.sender_phone}:{data.text}:{data.created_at_device or minute_bucket}'))
    if data.text.strip().startswith('SOS|'):
        event_data = SOSEventCreate(
            client_uuid=client_uuid,
            incident_id=data.incident_id,
            sender_ref=data.sender_phone,
            latitude=data.latitude,
            longitude=data.longitude,
            message=data.text,
            created_at_device=data.created_at_device,
            channel=channel,
        )
        try:
            event, created = create_event(db, data=event_data, user=None, force_channel=channel)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        db.commit()
        db.refresh(event)
        if created:
            background_tasks.add_task(interpret_sos_event, event.id)
        return {'kind': 'sos', **event_response(event), 'result': 'created' if created else 'duplicate'}

    if rate_limited(f'sms:{data.sender_phone.casefold()}', SENDER_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail='SMS sender rate limit exceeded')
    if data.incident_id is not None and db.get(Incident, data.incident_id) is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    existing = db.scalar(select(RawReport).where(RawReport.client_uuid == client_uuid))
    if existing is not None:
        return {'kind': 'raw_report', 'id': existing.id, 'client_uuid': existing.client_uuid, 'result': 'duplicate'}
    report = RawReport(
        incident_id=data.incident_id,
        text=data.text,
        channel=channel,
        sender_ref=data.sender_phone,
        client_uuid=client_uuid,
        parse_status='pending',
    )
    db.add(report)
    db.flush()
    append_audit_log(
        db,
        actor_id=None,
        action='sms_report_received',
        entity='raw_report',
        entity_id=report.id,
        after={'incident_id': report.incident_id, 'channel': report.channel, 'client_uuid': client_uuid},
    )
    db.commit()
    return {'kind': 'raw_report', 'id': report.id, 'client_uuid': report.client_uuid, 'result': 'created'}


def require_coordinator(user: User) -> None:
    if user.role not in {'admin', 'coordinator'}:
        raise HTTPException(status_code=403, detail='Coordinator role required')


@router.get('/sos')
def list_sos(
    status: str | None = Query(default=None, pattern='^(new|acknowledged|dispatched|resolved|false_alarm)$'),
    since: datetime | None = None,
    incident_id: int | None = None,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    within_km: float | None = Query(default=None, gt=0, le=500),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(optional_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail='Coordinator authentication required')
    require_coordinator(user)
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail='latitude and longitude must be supplied together')
    statement = select(SOSEvent)
    if status is not None:
        statement = statement.where(SOSEvent.status == status)
    if since is not None:
        statement = statement.where(SOSEvent.received_at_server >= since)
    if incident_id is not None:
        statement = statement.where(SOSEvent.incident_id == incident_id)
    events = db.scalars(
        statement.order_by(SOSEvent.received_at_server.desc(), SOSEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    now = datetime.now(timezone.utc)
    results = []
    for event in events:
        distance = None
        if latitude is not None and event.has_location:
            distance = haversine_km((latitude, longitude), (event.latitude, event.longitude))
            if within_km is not None and distance > within_km:
                continue
        received_at = event.received_at_server
        received_at = (
            received_at.replace(tzinfo=timezone.utc)
            if received_at.tzinfo is None
            else received_at.astimezone(timezone.utc)
        )
        results.append({
            **event_response(event),
            'distance_km': distance,
            'age_hours': round((now - received_at).total_seconds() / 3600, 2),
        })
    return results


@router.get('/sos/feed')
def sos_feed(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(optional_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail='Coordinator authentication required')
    require_coordinator(user)
    events = db.scalars(
        select(SOSEvent)
        .where(SOSEvent.id > after_id)
        .order_by(SOSEvent.id)
        .limit(limit)
    ).all()
    return {
        'events': [event_response(event) for event in events],
        'next_after_id': events[-1].id if events else after_id,
    }


@router.get('/sos/{sos_id}')
def get_sos(
    sos_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(optional_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail='Coordinator authentication required')
    require_coordinator(user)
    event = db.get(SOSEvent, sos_id)
    if event is None:
        raise HTTPException(status_code=404, detail='SOS event not found')
    return event_response(event)


@router.get('/sos/{sos_id}/status')
def sos_receipt_status(
    sos_id: int,
    receipt: str = Query(alias='receipt_token', min_length=64, max_length=64),
    db: Session = Depends(get_db),
):
    event = db.get(SOSEvent, sos_id)
    if event is None or not hmac.compare_digest(receipt, receipt_token(event)):
        raise HTTPException(status_code=404, detail='SOS receipt not found')
    return {
        'id': event.id, 'status': event.status, 'transmission_status': event.transmission_status,
        'linked_need_id': event.linked_need_id, 'assignment_id': event.assignment_id,
        'received_at_server': event.received_at_server.isoformat(),
        'has_location': event.has_location,
    }


@router.patch('/sos/{sos_id}/location')
def update_sos_location(
    sos_id: int,
    data: SOSLocationUpdate,
    background_tasks: BackgroundTasks,
    receipt: str = Query(alias='receipt_token', min_length=64, max_length=64),
    db: Session = Depends(get_db),
):
    event = db.scalar(select(SOSEvent).where(SOSEvent.id == sos_id).with_for_update())
    if event is None or not hmac.compare_digest(receipt, receipt_token(event)):
        raise HTTPException(status_code=404, detail='SOS receipt not found')
    if event.status in ('resolved', 'false_alarm'):
        raise HTTPException(status_code=409, detail='This SOS is closed; its location cannot be changed')
    if not has_valid_location(data.latitude, data.longitude):
        raise HTTPException(status_code=422, detail='A valid GPS location is required')
    before = {'latitude': event.latitude, 'longitude': event.longitude}
    event.latitude = data.latitude
    event.longitude = data.longitude
    event.location_accuracy_m = data.location_accuracy_m
    event.has_location = True
    event.location_updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db, actor_id=None, action='sos_location_updated', entity='sos_event',
        entity_id=event.id, before=before,
        after={
            'latitude': event.latitude, 'longitude': event.longitude,
            'location_accuracy_m': event.location_accuracy_m,
            'reported_via': 'receipt_holder',
        },
    )
    db.commit()
    if event.linked_need_id is None:
        background_tasks.add_task(interpret_sos_event, event.id, link_location=True)
    return {'id': event.id, 'has_location': True, 'location_updated_at': event.location_updated_at.isoformat()}


@router.post('/sos/{sos_id}/ack')
def acknowledge_sos(
    sos_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    event = db.scalar(select(SOSEvent).where(SOSEvent.id == sos_id).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail='SOS event not found')
    if event.status == 'acknowledged':
        return event_response(event)
    if event.status != 'new':
        raise HTTPException(status_code=409, detail='Only new SOS events can be acknowledged')
    event.status = 'acknowledged'
    acknowledgement = SOSAcknowledgement(sos_id=event.id, by_user=user.id, action='acknowledged')
    db.add(acknowledgement)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='sos_acknowledged',
        entity='sos_event',
        entity_id=event.id,
        before={'status': 'new'},
        after={'status': 'acknowledged', 'acknowledgement_id': acknowledgement.id},
    )
    db.commit()
    db.refresh(event)
    return event_response(event)


@router.patch('/sos/{sos_id}/state')
def update_sos_state(
    sos_id: int,
    data: SOSStateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    event = db.scalar(select(SOSEvent).where(SOSEvent.id == sos_id).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail='SOS event not found')
    if event.status == data.state:
        return event_response(event)
    if data.state not in SOS_STATE_TRANSITIONS.get(event.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f'Cannot move SOS from {event.status} to {data.state}',
        )
    previous = event.status
    event.status = data.state
    acknowledgement = SOSAcknowledgement(
        sos_id=event.id,
        by_user=user.id,
        action=data.state,
    )
    db.add(acknowledgement)
    append_audit_log(
        db,
        actor_id=user.id,
        action='sos_state_changed',
        entity='sos_event',
        entity_id=event.id,
        before={'status': previous},
        after={'status': data.state, 'notes': data.notes},
    )
    db.commit()
    db.refresh(event)
    return event_response(event)


@router.post('/sos/{sos_id}/dispatch')
def dispatch_sos(
    sos_id: int,
    data: SOSDispatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    event = db.scalar(select(SOSEvent).where(SOSEvent.id == sos_id).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail='SOS event not found')
    assignment = db.get(Assignment, data.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    if event.linked_need_id is not None and assignment.need_id != event.linked_need_id:
        raise HTTPException(status_code=409, detail='Assignment must address the SOS linked need')
    if assignment.status not in {'approved', 'accepted', 'en_route', 'on_site'}:
        raise HTTPException(status_code=409, detail='SOS dispatch requires an approved assignment')
    if event.status == 'dispatched' and event.assignment_id == assignment.id:
        return event_response(event)
    if event.status not in {'new', 'acknowledged'}:
        raise HTTPException(status_code=409, detail='SOS event cannot be dispatched from its current state')
    previous = {'status': event.status, 'assignment_id': event.assignment_id}
    event.status = 'dispatched'
    event.assignment_id = assignment.id
    event.linked_need_id = assignment.need_id
    db.add(SOSAcknowledgement(sos_id=event.id, by_user=user.id, action='dispatched'))
    append_audit_log(
        db,
        actor_id=user.id,
        action='sos_dispatched',
        entity='sos_event',
        entity_id=event.id,
        before=previous,
        after={'status': event.status, 'assignment_id': assignment.id, 'linked_need_id': assignment.need_id},
    )
    db.commit()
    db.refresh(event)
    return event_response(event)


@router.post('/sos/{sos_id}/resolve')
def resolve_sos(
    sos_id: int,
    data: SOSResolve,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    event = db.scalar(select(SOSEvent).where(SOSEvent.id == sos_id).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail='SOS event not found')
    if event.status in {'resolved', 'false_alarm'}:
        if event.status == data.status:
            return event_response(event)
        raise HTTPException(status_code=409, detail='Resolved SOS status cannot be changed')
    previous = event.status
    event.status = data.status
    db.add(SOSAcknowledgement(sos_id=event.id, by_user=user.id, action=data.status))
    append_audit_log(
        db,
        actor_id=user.id,
        action='sos_resolved',
        entity='sos_event',
        entity_id=event.id,
        before={'status': previous},
        after={'status': event.status, 'notes': data.notes},
    )
    db.commit()
    db.refresh(event)
    return event_response(event)


@router.post('/gateways', status_code=201)
def create_gateway(
    data: GatewayCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role('admin')),
):
    api_key = secrets.token_urlsafe(32)
    gateway = Gateway(
        name=data.name.strip(),
        gateway_type=data.gateway_type,
        api_key_hash=key_digest(api_key),
        created_by=user.id,
        is_active=True,
    )
    db.add(gateway)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='gateway_created',
        entity='gateway',
        entity_id=gateway.id,
        after={'name': gateway.name, 'gateway_type': gateway.gateway_type},
    )
    db.commit()
    return {'id': gateway.id, 'name': gateway.name, 'gateway_type': gateway.gateway_type, 'api_key': api_key}


@router.post('/sync/sos-batch')
def sync_sos_batch(
    data: SOSBatchCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
    x_gateway_key: str | None = Header(default=None),
):
    gateway = get_gateway(db, x_gateway_key)
    if gateway is None and user is None:
        raise HTTPException(status_code=401, detail='Bearer token or gateway API key required')

    results = []
    created_event_ids = []
    created = duplicate = rejected = 0
    for index, raw_item in enumerate(data.items):
        try:
            event_data = SOSEventCreate.model_validate(raw_item)
            event, was_created = create_event(
                db,
                data=event_data,
                user=user,
                gateway=gateway,
                force_channel='gateway' if gateway else None,
                anonymous_source=request.client.host if request.client else None,
            )
            result = 'created' if was_created else 'duplicate'
            created += int(was_created)
            duplicate += int(not was_created)
            if was_created:
                created_event_ids.append(event.id)
            results.append({
                'index': index,
                'client_uuid': event.client_uuid,
                'result': result,
                'sos_id': event.id,
            })
        except (ValidationError, ValueError, HTTPException, IntegrityError) as exc:
            rejected += 1
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            results.append({'index': index, 'result': 'rejected', 'reason': str(detail)[:300]})

    batch = SyncBatch(
        gateway_id=gateway.id if gateway else None,
        count_received=len(data.items),
        count_new=created,
        count_duplicate=duplicate,
        count_rejected=rejected,
    )
    db.add(batch)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id if user else None,
        action='sos_batch_synced',
        entity='sync_batch',
        entity_id=batch.id,
        after={
            'gateway_id': batch.gateway_id,
            'count_received': batch.count_received,
            'count_new': batch.count_new,
            'count_duplicate': batch.count_duplicate,
            'count_rejected': batch.count_rejected,
        },
    )
    db.commit()
    for event_id in created_event_ids:
        background_tasks.add_task(interpret_sos_event, event_id)
    return {
        'batch_id': batch.id,
        'count_received': len(data.items),
        'count_new': created,
        'count_duplicate': duplicate,
        'count_rejected': rejected,
        'results': results,
    }
