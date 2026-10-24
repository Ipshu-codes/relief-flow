from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.ai.report_tasks import rule_based_report
from app.ai.schemas import ParsedReport
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import Incident, Location, Need, RawReport, User
from app.routers import reports as reports_router
from app.security import create_access_token


@pytest.fixture
def report_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'reports-test-secret-that-is-long-enough-for-jwt-123')
    engine = create_engine(f"sqlite:///{tmp_path / 'reports.db'}", connect_args={'check_same_thread': False})
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    with Session(engine) as db:
        coordinator = User(
            email='report-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        community_member = User(
            email='report-member@example.org',
            full_name='Community Member',
            password_hash='test',
            role='community_member',
        )
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        location = Location(name='Community School', location_type='shelter')
        db.add_all([coordinator, community_member, incident, location])
        db.commit()
        db.refresh(coordinator)
        db.refresh(community_member)
        db.refresh(incident)
        db.refresh(location)
        token = create_access_token(coordinator.id)
        incident_id, location_id = incident.id, location.id
        community_token = create_access_token(community_member.id)

    async def parse_with_rules(db, text, location_names):
        parsed = rule_based_report(text, [], location_names)
        return ParsedReport.model_validate(parsed), 'fallback'

    monkeypatch.setattr(reports_router, 'parse_report', parse_with_rules)
    with TestClient(main.app) as client:
        client.testing_session = testing_session
        client.incident_id = incident_id
        client.location_id = location_id
        client.coordinator_headers = {'Authorization': f'Bearer {token}'}
        client.community_headers = {'Authorization': f'Bearer {community_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_rule_parser_keeps_family_count_separate_from_need_quantities():
    parsed = rule_based_report(
        '40 families at Community School, no drinking water, elderly need medicine',
        [],
        ['Community School'],
    )

    assert parsed['families_affected'] == 40
    assert parsed['location_text'] == 'Community School'
    assert [need['category'] for need in parsed['needs']] == ['water', 'medical']
    assert all(need['quantity'] is None for need in parsed['needs'])

    quantified = rule_based_report('10 bottles of water needed at Community School', [], ['Community School'])
    assert quantified['needs'][0]['quantity'] == 10
    assert quantified['needs'][0]['unit'] == 'bottles'


def test_report_intake_creates_unverified_needs_and_is_idempotent(report_client):
    client = report_client
    payload = {
        'text': '40 families at Community School, no drinking water, elderly need medicine',
        'channel': 'web',
        'client_uuid': '123e4567-e89b-12d3-a456-426614174300',
        'incident_id': client.incident_id,
    }

    created = client.post('/reports', json=payload)
    assert created.status_code == 201
    assert created.json()['parse_status'] == 'pending'
    assert len(created.json()['needs']) == 2
    assert all(need['verification_status'] == 'unverified' for need in created.json()['needs'])
    assert all(need['confidence'] == 'low' for need in created.json()['needs'])
    assert created.json()['parsed']['location_id'] == client.location_id

    duplicate = client.post('/reports', json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()['result'] == 'duplicate'
    assert len(duplicate.json()['needs']) == 2

    listing = client.get(
        f'/needs?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert listing.status_code == 200
    assert len(listing.json()['items']) == 2
    with client.testing_session() as db:
        assert len(db.scalars(select(RawReport)).all()) == 1
        assert len(db.scalars(select(Need)).all()) == 2
        assert check_audit_chain(db) == (True, None)


def test_need_detail_and_coordinator_patch_are_audited(report_client):
    client = report_client
    created = client.post(
        '/reports',
        json={
            'text': 'Need water at Community School',
            'channel': 'web',
            'client_uuid': '123e4567-e89b-12d3-a456-426614174301',
            'incident_id': client.incident_id,
            'location_id': client.location_id,
        },
    ).json()
    need_id = created['needs'][0]['id']

    detail = client.get(f'/needs/{need_id}', headers=client.coordinator_headers)
    assert detail.status_code == 200
    assert detail.json()['confidence'] == 'low'

    forbidden = client.patch(
        f'/needs/{need_id}',
        json={'verification_status': 'verified'},
        headers=client.community_headers,
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        f'/needs/{need_id}',
        json={'verification_status': 'verified', 'confidence': 'medium'},
        headers=client.coordinator_headers,
    )
    assert updated.status_code == 200
    assert updated.json()['verification_status'] == 'verified'
    assert updated.json()['confidence'] == 'medium'
    with client.testing_session() as db:
        assert check_audit_chain(db) == (True, None)


def test_need_patch_rejects_null_and_empty_payload(report_client):
    client = report_client
    created = client.post(
        '/reports',
        json={
            'text': 'Need water at Community School',
            'channel': 'web',
            'client_uuid': '123e4567-e89b-12d3-a456-426614174302',
            'incident_id': client.incident_id,
            'location_id': client.location_id,
        },
    ).json()
    need_id = created['needs'][0]['id']
    for payload in ({}, {'description': None}):
        response = client.patch(
            f'/needs/{need_id}',
            json=payload,
            headers=client.coordinator_headers,
        )
        assert response.status_code == 422


def test_needs_list_requires_authentication(report_client):
    response = report_client.get('/needs')
    assert response.status_code == 401