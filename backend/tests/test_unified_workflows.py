import json
from base64 import b64encode
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import AICallLog, Assignment, AuditLog, Need, SOSAcknowledgement, SOSEvent, VolunteerProfile
from app.setup_local import seed_demo


@pytest.fixture()
def system(tmp_path, monkeypatch):
    import ai.client
    import ai.sos_tasks
    from app import security
    from app.routers import sos

    monkeypatch.setattr(security, 'JWT_SECRET', secrets.token_urlsafe(48))
    engine = create_engine(f"sqlite:///{tmp_path / 'system.db'}", connect_args={'check_same_thread': False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        seed_demo(db)

    async def unavailable(*args, **kwargs):
        raise ConnectionError('Ollama intentionally offline for integration test')

    monkeypatch.setattr(ai.client.ollama.AsyncClient, 'generate', unavailable)
    monkeypatch.setattr(ai.sos_tasks, 'SessionLocal', factory)
    sos._recent_requests.clear()

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def login(client, email='coordinator@demo.rahat.org', password='RahatDemo2026!'):
    response = client.post('/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def register(client, email):
    response = client.post('/auth/register', json={
        'email': email, 'full_name': 'Test Participant', 'password': 'IntegrationPass2026!',
    })
    assert response.status_code == 201, response.text
    return login(client, email, 'IntegrationPass2026!')


def test_real_jwt_and_role_boundaries(system):
    client, _ = system
    assert client.get('/workspace').status_code == 401
    assert client.post('/auth/login', json={
        'email': 'coordinator@demo.rahat.org', 'password': 'incorrect',
    }).status_code == 401
    headers = register(client, 'community@example.org')
    assert client.get('/auth/me', headers=headers).json()['role'] == 'community_member'
    assert client.post('/assignments', headers=headers, json={'need_id': 1, 'volunteer_id': 1}).status_code == 403
    assert client.post('/auth/register', json={
        'email': 'invalid@example.org', 'full_name': '  ', 'password': 'IntegrationPass2026!',
    }).status_code == 422
    tampered = {'Authorization': headers['Authorization'] + 'corrupt'}
    assert client.get('/auth/me', headers=tampered).status_code == 401


def test_user_profile_persists_location_and_emergency_contact(system):
    client, _ = system
    headers = register(client, 'profile@example.org')
    payload = {
        'phone_number': '+977-9800000000',
        'address': {
            'district': 'Kathmandu',
            'city': 'Kathmandu Metropolitan City',
            'ward': '10',
            'road': 'Baneshwor Road',
            'landmark': 'Community hospital',
        },
        'latitude': 27.7172,
        'longitude': 85.324,
        'location_accuracy_m': 25,
        'emergency_contacts': [{
            'name': 'Trusted Neighbour',
            'relationship': 'neighbour',
            'phone': '+977-9811111111',
            'priority': 1,
            'share_location': True,
            'consent_to_notify': True,
        }],
        'profile_notes': 'Uses a wheelchair; ground-floor access is preferred.',
    }
    response = client.patch('/auth/me/profile', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['address']['ward'] == '10'
    assert response.json()['emergency_contacts'][0]['phone'] == '+977-9811111111'
    assert client.get('/auth/me/profile', headers=headers).json() == response.json()
    incomplete = client.patch('/auth/me/profile', headers=headers, json={
        'emergency_contacts': [{
            'name': 'Missing phone',
            'relationship': 'friend',
            'phone': '',
        }],
    })
    assert incomplete.status_code == 422


def test_community_help_offer_and_notifications(system):
    client, _ = system
    owner = register(client, 'helper@example.org')
    recipient = register(client, 'neighbour@example.org')
    offer = client.post('/help/offers', headers=owner, json={
        'category': 'water',
        'description': 'Sealed drinking water available for nearby families.',
        'quantity': 40,
        'unit': 'litres',
        'location_text': 'Ward 10 community hall',
    })
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()['id']
    manager = login(client)
    assert any(
        item['payload']['offer_id'] == offer_id
        for item in client.get('/help/notifications', headers=manager).json()
    )
    claimed = client.post(
        f'/help/offers/{offer_id}/claim', headers=recipient
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['status'] == 'claimed'
    assert any(
        item['payload']['offer_id'] == offer_id
        for item in client.get('/help/notifications', headers=owner).json()
    )
    assert client.post(
        f'/help/offers/{offer_id}/claim', headers=manager
    ).status_code == 409


def test_authenticated_sos_alerts_only_reporters_emergency_contact(system):
    client, _ = system
    reporter = register(client, 'reporter@example.org')
    contact = register(client, 'contact@example.org')
    contact_profile = client.patch('/auth/me/profile', headers=contact, json={
        'phone_number': '+977-9812345678',
    })
    assert contact_profile.status_code == 200
    reporter_profile = client.patch('/auth/me/profile', headers=reporter, json={
        'emergency_contacts': [{
            'name': 'Trusted contact',
            'relationship': 'friend',
            'phone': '+977-9812345678',
            'share_location': True,
            'consent_to_notify': True,
        }],
    })
    assert reporter_profile.status_code == 200
    response = client.post('/sos', headers=reporter, json={
        'client_uuid': str(uuid4()),
        'category': 'OTHER',
        'message': 'TEST: need assistance at the school shelter',
        'urgency': 5,
    })
    assert response.status_code == 201, response.text
    alerts = client.get('/help/notifications', headers=contact).json()
    assert any(alert['kind'] == 'emergency_contact_alert' for alert in alerts)


def test_organization_employees_skills_and_scope(system):
    client, _ = system
    employer = register(client, 'employer@example.org')
    org = client.post('/organizations', headers=employer, json={
        'name': 'Test Hospital', 'organization_type': 'hospital',
    })
    assert org.status_code == 201, org.text
    org_id = org.json()['id']
    assert client.get('/auth/me', headers=employer).json()['role'] == 'org_admin'
    skills = client.get('/skills', headers=employer).json()
    selected = [item['id'] for item in skills if item['name'] in ('doctor', 'nurse')]
    payload = {
        'email': 'employee@example.org', 'full_name': 'Test Employee',
        'password': 'EmployeePass2026!', 'contact_info': 'Contact via hospital desk',
        'base_location_id': 1, 'skills': [{'skill_id': sid, 'level': 4} for sid in selected],
    }
    employee = client.post(f'/organizations/{org_id}/employees', headers=employer, json=payload)
    assert employee.status_code == 201, employee.text
    profile = employee.json()
    assert profile['organization_id'] == org_id
    assert profile['contact_info'] == payload['contact_info']
    assert len(profile['skills']) == 2
    assert not any(skill['verified'] for skill in profile['skills'])
    assert client.post(f'/organizations/{org_id}/employees', headers=employer, json=payload).status_code == 409
    other = register(client, 'other@example.org')
    assert client.post(f'/organizations/{org_id}/employees', headers=other, json=payload).status_code == 403
    employee_headers = login(client, 'employee@example.org', 'EmployeePass2026!')
    assert len(client.get('/volunteers', headers=employee_headers).json()) == 1
    assert client.post(f"/volunteers/{profile['id']}/skills/{selected[0]}/verify", headers=employee_headers).status_code == 403
    assert client.post(f"/volunteers/{profile['id']}/skills/{selected[0]}/verify", headers=employer).status_code == 200
    payload.update(email='second@example.org', base_location_id=9999)
    assert client.post(f'/organizations/{org_id}/employees', headers=employer, json=payload).status_code == 404


def test_individual_volunteer_and_availability(system):
    client, _ = system
    headers = register(client, 'individual@example.org')
    created = client.post('/volunteers', headers=headers, json={
        'base_location_id': 1, 'contact_info': 'Radio call sign TEST', 'max_travel_km': 25,
    })
    assert created.status_code == 201, created.text
    assert client.get('/auth/me', headers=headers).json()['role'] == 'volunteer'
    profile_id = created.json()['id']
    window = {
        'starts_at': datetime.now(timezone.utc).isoformat(),
        'ends_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    response = client.patch(f'/volunteers/{profile_id}/availability', headers=headers, json={
        'status': 'available', 'windows': [window],
    })
    assert response.status_code == 200, response.text
    assert client.post('/volunteers', headers=headers, json={}).status_code == 409


def test_sos_persists_without_ai_and_receipt_tracks_ack(system):
    client, factory = system
    body = {
        'client_uuid': str(uuid4()), 'category': 'TRAPPED',
        'message': 'TEST: trapped at health post', 'latitude': 27.7172, 'longitude': 85.324,
        'channel': 'app',
    }
    receipt = client.post('/sos', json=body)
    assert receipt.status_code == 201, receipt.text
    data = receipt.json()
    assert data['transmission_status'] == 'received'
    token = data['receipt_token']
    repeated = client.post('/sos', json=body)
    assert repeated.status_code == 200
    assert repeated.json()['id'] == data['id']
    assert repeated.json()['receipt_token'] == token
    assert client.get('/sos').status_code == 401
    assert client.get(f"/sos/{data['id']}").status_code == 401
    status_url = f"/sos/{data['id']}/status"
    assert client.get(status_url, params={'receipt_token': '0' * 64}).status_code == 404
    status = client.get(status_url, params={'receipt_token': token}).json()
    assert 'message' not in status and 'latitude' not in status
    assert status['linked_need_id'] is not None
    coordinator = login(client)
    assert client.post(f"/sos/{data['id']}/ack", headers=coordinator).status_code == 200
    assert client.get(status_url, params={'receipt_token': token}).json()['status'] == 'acknowledged'
    with factory() as db:
        assert db.scalar(select(SOSEvent)).parsed_json['source'] == 'fallback'
        assert db.scalar(select(Need).where(Need.source == 'sos')) is not None
        assert db.scalar(select(AICallLog).where(AICallLog.fallback_used.is_(True))) is not None


def test_sos_state_machine_records_valid_transitions(system):
    client, factory = system
    coordinator = login(client)
    response = client.post('/sos', json={
        'client_uuid': str(uuid4()),
        'category': 'MEDICINE',
        'message': 'TEST: medicine needed at shelter',
    })
    assert response.status_code == 201
    sos_id = response.json()['id']
    for state in ('received', 'acknowledged', 'verified', 'awaiting_dispatch'):
        response = client.patch(
            f'/sos/{sos_id}/state',
            headers=coordinator,
            json={'state': state, 'notes': f'TEST {state}'},
        )
        assert response.status_code == 200, response.text
        assert response.json()['status'] == state
    invalid = client.patch(
        f'/sos/{sos_id}/state',
        headers=coordinator,
        json={'state': 'on_scene'},
    )
    assert invalid.status_code == 409
    with factory() as db:
        actions = [
            row.action for row in db.scalars(
                select(SOSAcknowledgement).where(SOSAcknowledgement.sos_id == sos_id)
            )
        ]
        assert actions[-4:] == ['received', 'acknowledged', 'verified', 'awaiting_dispatch']


def test_sos_missing_location_is_not_invented_and_batch_retries(system):
    client, _ = system
    receipt = client.post('/sos', json={
        'client_uuid': str(uuid4()), 'category': 'OTHER', 'message': 'TEST: location unavailable',
        'latitude': 0, 'longitude': 0,
    })
    assert receipt.status_code == 201
    assert receipt.json()['has_location'] is False
    assert receipt.json()['latitude'] is None
    coordinator = login(client)
    batch = {'items': [
        {'client_uuid': str(uuid4()), 'message': 'SOS|TRAPPED|27.7172,85.3240|TEST water rising'},
        {'client_uuid': 'not-a-uuid', 'message': 'bad input'},
    ]}
    first = client.post('/sync/sos-batch', headers=coordinator, json=batch)
    assert first.status_code == 200, first.text
    assert first.json()['count_new'] == 1
    assert first.json()['count_rejected'] == 1
    repeated = client.post('/sync/sos-batch', headers=coordinator, json=batch)
    assert repeated.json()['count_duplicate'] == 1


def test_written_address_survives_intake_batch_and_later_gps(system):
    client, factory = system
    address = {
        'district': 'Kathmandu', 'city': 'Kathmandu Metropolitan City',
        'ward': '4', 'road': 'TEST road', 'landmark': 'TEST school east gate',
    }
    body = {
        'client_uuid': str(uuid4()), 'category': 'TRAPPED',
        'message': 'TEST: trapped near school', 'address': address,
    }
    receipt = client.post('/sos', json=body)
    assert receipt.status_code == 201, receipt.text
    event = receipt.json()
    assert event['address'] == address
    assert event['has_location'] is False
    path = f"/sos/{event['id']}/location"
    fix = {'lat': 27.7172, 'lon': 85.3240, 'location_accuracy_m': 12}
    assert client.patch(path, json=fix).status_code == 422
    assert client.patch(path, json=fix, params={'receipt_token': '0' * 64}).status_code == 404
    token = {'receipt_token': event['receipt_token']}
    for invalid in [{'lat': 91, 'lon': 85}, {'lat': 0, 'lon': 0},
                    {'lat': 27, 'lon': 85, 'location_accuracy_m': -1}]:
        assert client.patch(path, json=invalid, params=token).status_code == 422
    with factory() as db:
        before_calls = len(db.scalars(select(AICallLog)).all())
    updated = client.patch(path, json=fix, params=token)
    assert updated.status_code == 200, updated.text
    assert updated.json()['has_location'] is True
    assert updated.json()['location_updated_at']
    coordinator = login(client)
    detail = client.get(f"/sos/{event['id']}", headers=coordinator).json()
    assert detail['address'] == address
    assert detail['latitude'] == fix['lat']
    assert detail['location_accuracy_m'] == 12
    assert detail['linked_need_id'] is not None
    assert client.get(f"/sos/{event['id']}/status", params=token).json()['has_location'] is True
    with factory() as db:
        assert len(db.scalars(select(AICallLog)).all()) == before_calls
        assert db.scalar(select(AuditLog).where(AuditLog.action == 'sos_location_updated'))
    body['client_uuid'] = str(uuid4())
    body['channel'] = 'mesh'
    batch = client.post('/sync/sos-batch', headers=coordinator, json={'items': [body]})
    assert batch.status_code == 200, batch.text
    assert batch.json()['count_new'] == 1
    with factory() as db:
        relayed = db.scalar(select(SOSEvent).where(SOSEvent.client_uuid == body['client_uuid']))
        assert relayed.address == address
        assert relayed.has_location is False
    closed = client.post(f"/sos/{event['id']}/resolve", headers=coordinator,
                         json={'status': 'false_alarm', 'notes': 'TEST closed'})
    assert closed.status_code == 200, closed.text
    assert client.patch(path, json=fix, params=token).status_code == 409


def test_written_address_validation(system):
    client, _ = system
    body = {'client_uuid': str(uuid4()), 'message': 'TEST help'}
    for address in [{'landmark': 'x' * 181}, {'ward': 'x' * 21}, {'unexpected': 'bad'}]:
        assert client.post('/sos', json={**body, 'address': address}).status_code == 422
    response = client.post('/sos', json={**body, 'address': {'landmark': '  TEST school  '}})
    assert response.status_code == 201
    assert response.json()['address']['landmark'] == 'TEST school'


def test_android_ble_signed_address_bridge(system):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    client, _ = system
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload = b'{"client_uuid":"11111111-1111-4111-8111-111111111111","category":"TRAPPED","message":"TEST","address":{"district":"Kathmandu","landmark":"school"}}'
    envelope = {
        'v': 1, 'ttl': 5, 'payload': b64encode(payload).decode(),
        'public_key': b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
        'signature': b64encode(key.sign(b'rahat-ble-v1:' + payload)).decode(),
    }
    assert envelope['signature'] == 'SDouWpHI14F9RBYPHKegqPryhNp6DR7J4rCWfMbM9G3L6rFMN3jBb+oJD5zZzPzJ0kNLIPWoETpjdAW/Kz5cDg=='
    result = client.post('/api/v1/ingest/ble', json=envelope)
    assert result.status_code == 200, result.text
    event = result.json()
    assert event['signature_verified'] is True
    assert event['identity_trusted'] is False
    assert event['sender_verified'] is False
    assert event['channel'] == 'mesh'
    assert event['has_location'] is False
    assert event['address']['landmark'] == 'school'
    repeated = client.post('/api/v1/ingest/ble', json=envelope)
    assert repeated.json()['id'] == event['id']
    assert repeated.json()['result'] == 'duplicate'
    changed = {**envelope, 'payload': b64encode(payload.replace(b'TEST', b'evil')).decode()}
    assert client.post('/api/v1/ingest/ble', json=changed).status_code == 400
    assert client.post('/api/v1/ingest/ble', json={**envelope, 'ttl': 7}).status_code == 422
    assert client.post('/api/v1/ingest/ble', json={**envelope, 'public_key': '!' * 44}).status_code == 400


def test_ai_draft_approval_and_volunteer_lifecycle(system):
    client, factory = system
    coordinator = login(client)
    with factory() as db:
        need_id = db.scalar(select(Need.id).where(Need.category == 'technical_repair'))
    proposal = client.post(f'/needs/{need_id}/assignment-proposal', headers=coordinator, json={})
    assert proposal.status_code == 201, proposal.text
    data = proposal.json()
    assert data['proposal']['source'] == 'fallback'
    with factory() as db:
        assignment = db.scalar(select(Assignment).where(Assignment.need_id == need_id))
        assert assignment.status == 'proposed'
        assignment_id = assignment.id
    assert client.post(f'/assignments/{assignment_id}/approve', headers=coordinator).status_code == 200
    volunteer = login(client, 'volunteer@demo.rahat.org')
    assert client.post(f'/assignments/{assignment_id}/accept', headers=volunteer).status_code == 200
    for status in ('en_route', 'on_site'):
        response = client.patch(f'/assignments/{assignment_id}/status', headers=volunteer, json={'status': status})
        assert response.status_code == 200, response.text
    completed = client.post(f'/assignments/{assignment_id}/complete', headers=volunteer, json={
        'completion_criteria_met': True, 'outcome_notes': 'TEST: Power restored and verified.',
    })
    assert completed.status_code == 200, completed.text
    with factory() as db:
        assert db.get(Need, need_id).status == 'fulfilled'
        assert db.scalar(select(VolunteerProfile)).availability_status == 'available'
        assert db.scalar(select(AuditLog.id)) is not None


@pytest.mark.asyncio
async def test_ai_schema_failure_retries_then_marks_fallback(system, monkeypatch):
    import ai.client
    from ai.schemas import SkillMapping

    _, factory = system
    calls = []

    async def invalid(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(response='{"skills":42}')

    monkeypatch.setattr(ai.client.ollama.AsyncClient, 'generate', invalid)
    with factory() as db:
        result, source = await ai.client.generate_json(
            db, task='test_validation', prompt_version='test_v1', prompt='test',
            input_summary='test', schema=SkillMapping, fallback=lambda: {'skills': ['doctor']},
        )
        db.commit()
        assert source == 'fallback' and result.skills == ['doctor']
        assert len(calls) == 2
        assert calls[0]['format'] == SkillMapping.model_json_schema()
        logs = db.scalars(select(AICallLog).where(AICallLog.task == 'test_validation')).all()
        assert len(logs) == 3 and all(log.fallback_used for log in logs)


def test_valid_ai_report_output_creates_actual_needs(system, monkeypatch):
    import ai.client

    client, _ = system
    expected = {
        'location_text': '[DEMO] Health Post', 'families_affected': 40,
        'needs': [
            {'category': 'water', 'item': 'Drinking water', 'quantity': 100, 'unit': 'litre', 'required_skills': []},
            {'category': 'medical', 'item': 'Elderly need medicine', 'quantity': None, 'unit': None, 'required_skills': ['nurse']},
        ],
        'urgency': 4, 'vulnerable_groups': ['elderly'], 'hazards': [],
        'missing_fields': ['medical quantity'], 'follow_up_questions': ['How many medicine kits?'],
        'language': 'en', 'confidence': 'medium',
    }

    async def generated(*args, **kwargs):
        return SimpleNamespace(response=json.dumps(expected))

    monkeypatch.setattr(ai.client.ollama.AsyncClient, 'generate', generated)
    body = {
        'text': '40 families at the school, no drinking water, elderly need medicine',
        'channel': 'web', 'client_uuid': str(uuid4()), 'incident_id': 1, 'location_id': 1,
    }
    response = client.post('/reports', json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['parsed']['source'] == 'ai'
    assert len(data['needs']) == 2
    assert all(need['verification_status'] == 'unverified' for need in data['needs'])
    assert client.post('/reports', json=body).json()['result'] == 'duplicate'


def test_platform_signed_packets_use_unified_sos_storage(system):
    from protocol import codec

    client, factory = system
    private, public = codec.new_keypair()
    _, packet = codec.make_sos(
        private, public, category='trapped', lat=27.7172, lon=85.324,
        text='TEST inherited packet intake',
    )
    body = {'packet': b64encode(packet).decode()}
    received = client.post('/api/v1/ingest/packet', json=body)
    assert received.status_code == 200, received.text
    assert received.json()['signature_verified'] is True
    assert received.json()['identity_trusted'] is False
    duplicate = client.post('/api/v1/ingest/packet', json=body)
    assert duplicate.json()['reason'] == 'duplicate'
    corrupted = packet[:-1] + bytes([packet[-1] ^ 1])
    assert client.post('/api/v1/ingest/packet', json={
        'packet': b64encode(corrupted).decode(),
    }).status_code == 400
    coordinator = login(client)
    assert len(client.get('/sos', headers=coordinator).json()) == 1
    with factory() as db:
        assert db.scalar(select(SOSEvent)).channel == 'mesh'


def test_mesh_simulation_queues_then_delivers_to_shared_database(system):
    from app.routers.mesh import demo

    client, _ = system
    with demo.lock:
        demo.connected = False
        demo.queue.clear()
    coordinator = login(client)
    assert client.get('/api/v1/demo/state').status_code == 401
    queued = client.post('/api/v1/demo/sos', headers=coordinator, json={
        'category': 'trapped', 'text': '[SIMULATION] Test bridge',
    })
    assert queued.status_code == 200
    assert queued.json()['delivered'] is False
    assert client.get('/sos', headers=coordinator).json() == []
    connected = client.post('/api/v1/demo/bridge/toggle', headers=coordinator)
    assert connected.status_code == 200, connected.text
    assert connected.json()['queued'] == 0
    assert len(connected.json()['delivered']) == 1
    assert len(client.get('/sos', headers=coordinator).json()) == 1


def test_migration_adopts_existing_data_idempotently(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import app.db
    from sqlalchemy import inspect, text

    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE volunteer_profiles (id INTEGER PRIMARY KEY, user_id INTEGER, notes TEXT)'
        ))
        connection.execute(text(
            "INSERT INTO volunteer_profiles (id,user_id,notes) VALUES (1,1,'Keep this record')"
        ))
        connection.execute(text('CREATE TABLE sos_events (id INTEGER PRIMARY KEY, message TEXT)'))
        connection.execute(text("INSERT INTO sos_events (id,message) VALUES (1,'Keep this SOS')"))
    monkeypatch.setattr(app.db, 'engine', engine)
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    command.upgrade(config, 'head')
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT notes FROM volunteer_profiles WHERE id=1')) == 'Keep this record'
        assert connection.scalar(text('SELECT message FROM sos_events WHERE id=1')) == 'Keep this SOS'
    assert 'contact_info' in {column['name'] for column in inspect(engine).get_columns('volunteer_profiles')}
    assert {'address', 'location_updated_at'} <= {
        column['name'] for column in inspect(engine).get_columns('sos_events')
    }
    engine.dispose()
