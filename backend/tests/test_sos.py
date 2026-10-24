from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.routers import sos as sos_router
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import Assignment, Gateway, Incident, Location, Need, RawReport, SOSEvent, User, VolunteerProfile
from app.security import create_access_token


@pytest.fixture
def sos_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'sos-test-secret-that-is-long-enough-for-jwt-123')
    monkeypatch.setattr(sos_router, '_recent_requests', {})
    background_ids = []

    async def record_background_task(sos_id):
        background_ids.append(sos_id)

    monkeypatch.setattr(sos_router, 'interpret_sos_event', record_background_task)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sos.db'}",
        connect_args={'check_same_thread': False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    with Session(engine) as db:
        coordinator = User(
            email='sos-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([coordinator, incident])
        db.commit()
        admin = User(
            email='sos-admin@example.org',
            full_name='Admin',
            password_hash='test',
            role='admin',
        )
        db.add_all([coordinator, admin, incident])
        db.commit()
        coordinator_token = create_access_token(coordinator.id)
        admin_token = create_access_token(admin.id)
        incident_id = incident.id

    with TestClient(main.app) as client:
        client.testing_session = testing_session
        client.background_ids = background_ids
        client.incident_id = incident_id
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.admin_headers = {'Authorization': f'Bearer {admin_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_compact_sos_intake_exact_retry_and_near_duplicate(sos_client):
    client = sos_client
    payload = {
        'client_uuid': '123e4567-e89b-12d3-a456-426614174201',
        'incident_id': client.incident_id,
        'sender_ref': 'phone-555',
        'message': 'SOS|TRAPPED|27.7172,85.3240|water rising',
        'channel': 'mesh',
    }
    created = client.post('/sos', json=payload)
    assert created.status_code == 201
    assert created.json()['result'] == 'created'
    assert created.json()['category'] == 'TRAPPED'
    assert created.json()['has_location'] is True
    assert created.json()['sender_verified'] is False
    assert created.json()['message'] == 'water rising'
    assert created.json()['id'] in client.background_ids

    exact_duplicate = client.post('/sos', json=payload)
    assert exact_duplicate.status_code == 200
    assert exact_duplicate.json()['result'] == 'duplicate'
    assert exact_duplicate.json()['id'] == created.json()['id']

    near_duplicate = client.post(
        '/sos',
        json={
            **payload,
            'client_uuid': '123e4567-e89b-12d3-a456-426614174202',
            'message': 'Water rising near home',
            'latitude': 27.718,
            'longitude': 85.3245,
        },
    )
    assert near_duplicate.status_code == 201
    assert near_duplicate.json()['duplicate_of'] == created.json()['id']

    with client.testing_session() as db:
        assert db.scalar(select(SOSEvent).where(SOSEvent.client_uuid == payload['client_uuid']))
        assert check_audit_chain(db) == (True, None)


def test_missing_zero_or_invalid_sos_location_is_never_guessed(sos_client):
    client = sos_client
    no_location = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174203',
            'message': 'Need food, no location available',
            'latitude': 0,
            'longitude': 85.3,
        },
    )
    assert no_location.status_code == 201
    assert no_location.json()['has_location'] is False
    assert no_location.json()['latitude'] is None
    assert no_location.json()['longitude'] is None

    malformed_compact = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174204',
            'message': 'SOS|FIRE|27.7,85.3|help',
        },
    )
    assert malformed_compact.status_code == 422
    assert client.post(
        '/sos',
        json={'client_uuid': 'not-a-uuid', 'message': 'Help'},
    ).status_code == 422


def test_optional_bearer_marks_sender_verified_and_invalid_incident_fails(sos_client):
    client = sos_client
    verified = client.post(
        '/sos',
        headers=client.coordinator_headers,
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174205',
            'incident_id': client.incident_id,
            'category': 'MEDICINE',
            'message': 'Medicine needed',
        },
    )
    assert verified.status_code == 201
    assert verified.json()['sender_verified'] is True

    invalid_incident = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174206',
            'incident_id': 999,
            'message': 'Help',
        },
    )
    assert invalid_incident.status_code == 404


def test_batch_sync_returns_per_item_results_and_is_idempotent(sos_client):
    client = sos_client
    first = {
        'client_uuid': '123e4567-e89b-12d3-a456-426614174207',
        'sender_ref': 'mesh-device-1',
        'message': 'SOS|MEDICINE|27.7,85.3|medicine needed',
        'channel': 'mesh',
    }
    invalid = {'client_uuid': 'not-a-uuid', 'message': 'invalid'}
    batch = {'items': [first, first, invalid]}
    response = client.post('/sync/sos-batch', headers=client.coordinator_headers, json=batch)
    assert response.status_code == 200
    assert [item['result'] for item in response.json()['results']] == ['created', 'duplicate', 'rejected']
    assert response.json()['count_new'] == 1
    assert response.json()['count_duplicate'] == 1
    assert response.json()['count_rejected'] == 1

    retried = client.post('/sync/sos-batch', headers=client.coordinator_headers, json={'items': [first]})
    assert retried.json()['results'][0]['result'] == 'duplicate'
    with client.testing_session() as db:
        assert db.query(SOSEvent).filter_by(client_uuid=first['client_uuid']).count() == 1


def test_gateway_key_is_hashed_and_authenticates_batch(sos_client):
    client = sos_client
    gateway = client.post(
        '/gateways',
        headers=client.admin_headers,
        json={'name': 'Field Gateway 1', 'gateway_type': 'meshtastic'},
    )
    assert gateway.status_code == 201
    api_key = gateway.json()['api_key']
    with client.testing_session() as db:
        stored = db.get(Gateway, gateway.json()['id'])
        assert stored.api_key_hash != api_key
        assert len(stored.api_key_hash) == 64

    response = client.post(
        '/sync/sos-batch',
        headers={'X-Gateway-Key': api_key},
        json={'items': [{
            'client_uuid': '123e4567-e89b-12d3-a456-426614174208',
            'sender_ref': 'mesh-node-2',
            'message': 'SOS|TRAPPED|27.71,85.31|water rising',
        }]},
    )
    assert response.status_code == 200
    assert response.json()['count_new'] == 1
    with client.testing_session() as db:
        event = db.scalar(select(SOSEvent).where(
            SOSEvent.client_uuid == '123e4567-e89b-12d3-a456-426614174208'
        ))
        assert event.channel == 'gateway'
        assert event.gateway_id == gateway.json()['id']
        assert event.sender_verified is True


def test_sms_webhook_maps_report_or_compact_sos_idempotently(sos_client):
    client = sos_client
    report_payload = {
        'sender_phone': '+9775551000',
        'text': 'Need drinking water near the school',
        'client_uuid': '123e4567-e89b-12d3-a456-426614174209',
        'incident_id': client.incident_id,
    }
    report = client.post('/sms/incoming', json=report_payload)
    assert report.status_code == 200
    assert report.json()['kind'] == 'raw_report'
    assert report.json()['result'] == 'created'
    duplicate_report = client.post('/sms/incoming', json=report_payload)
    assert duplicate_report.json()['result'] == 'duplicate'

    compact = client.post(
        '/sms/incoming',
        json={
            'sender_phone': '+9775552000',
            'text': 'SOS|TRAPPED|27.7,85.3|water rising',
            'client_uuid': '123e4567-e89b-12d3-a456-426614174210',
            'incident_id': client.incident_id,
        },
    )
    assert compact.status_code == 200
    assert compact.json()['kind'] == 'sos'
    assert compact.json()['category'] == 'TRAPPED'
    assert compact.json()['channel'] == 'sms'
    with client.testing_session() as db:
        raw = db.get(RawReport, report.json()['id'])
        assert raw.parse_status == 'pending'
        assert raw.channel == 'sms'


def test_coordinator_sos_list_and_poll_feed(sos_client):
    client = sos_client
    created = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174211',
            'incident_id': client.incident_id,
            'sender_ref': 'poll-device',
            'latitude': 27.7,
            'longitude': 85.3,
            'category': 'FOOD',
            'message': 'Need food',
        },
    ).json()
    listing = client.get(
        f"/sos?status=new&incident_id={client.incident_id}&latitude=27.7&longitude=85.3&within_km=2",
        headers=client.coordinator_headers,
    )
    assert listing.status_code == 200
    event = next(item for item in listing.json() if item['id'] == created['id'])
    assert event['distance_km'] < 1
    assert event['age_hours'] >= 0

    feed = client.get('/sos/feed?after_id=0', headers=client.coordinator_headers)
    assert feed.status_code == 200
    assert feed.json()['events'][0]['id'] == created['id']
    assert feed.json()['next_after_id'] >= created['id']
    assert client.get('/sos/feed').status_code == 401


def test_coordinator_ack_dispatch_and_resolve_sos(sos_client):
    client = sos_client
    acknowledged_event = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174212',
            'incident_id': client.incident_id,
            'category': 'RESCUE',
            'message': 'Need rescue support',
        },
    ).json()
    ack = client.post(
        f"/sos/{acknowledged_event['id']}/ack",
        headers=client.coordinator_headers,
    )
    assert ack.status_code == 200
    assert ack.json()['status'] == 'acknowledged'
    assert client.post(
        f"/sos/{acknowledged_event['id']}/ack",
        headers=client.coordinator_headers,
    ).status_code == 200

    with client.testing_session() as db:
        coordinator_id = db.scalar(select(User.id).where(User.role == 'coordinator'))
        location = Location(name='SOS Shelter', location_type='shelter', latitude=27.7, longitude=85.3)
        db.add(location)
        db.flush()
        need = Need(
            incident_id=client.incident_id,
            location_id=location.id,
            category='rescue',
            description='Rescue support',
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        profile = VolunteerProfile(user_id=coordinator_id, base_location_id=location.id)
        db.add_all([need, profile])
        db.flush()
        assignment = Assignment(
            need_id=need.id,
            volunteer_id=profile.id,
            status='approved',
            approved_by=coordinator_id,
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id

    dispatched_event = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174213',
            'incident_id': client.incident_id,
            'category': 'RESCUE',
            'message': 'Rescue requested',
        },
    ).json()
    dispatched = client.post(
        f"/sos/{dispatched_event['id']}/dispatch",
        headers=client.coordinator_headers,
        json={'assignment_id': assignment_id},
    )
    assert dispatched.status_code == 200
    assert dispatched.json()['status'] == 'dispatched'
    assert dispatched.json()['assignment_id'] == assignment_id

    resolved = client.post(
        f"/sos/{dispatched_event['id']}/resolve",
        headers=client.coordinator_headers,
        json={'status': 'resolved', 'notes': 'Rescue completed'},
    )
    assert resolved.status_code == 200
    assert resolved.json()['status'] == 'resolved'
    with client.testing_session() as db:
        assert check_audit_chain(db) == (True, None)


def test_sos_actions_require_coordinator(sos_client):
    client = sos_client
    event = client.post(
        '/sos',
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174214',
            'message': 'Need help',
        },
    ).json()
    assert client.post(f"/sos/{event['id']}/ack").status_code == 401
    assert client.post(
        f"/sos/{event['id']}/dispatch",
        headers=client.coordinator_headers,
        json={'assignment_id': 999},
    ).status_code == 404


def test_anonymous_sos_is_rate_limited_without_requiring_login(sos_client):
    client = sos_client
    statuses = []
    for index in range(11):
        response = client.post(
            '/sos',
            json={
                'client_uuid': f'123e4567-e89b-12d3-a456-{index:012d}',
                'message': f'Need assistance {index}',
            },
        )
        statuses.append(response.status_code)
    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429
