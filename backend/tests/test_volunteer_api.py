from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import Assignment, Incident, Location, Need, Organization, Skill, User, VolunteerProfile
from app.security import create_access_token


@pytest.fixture
def volunteer_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'volunteer-test-secret-with-at-least-32-chars')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'volunteer-api.db'}",
        connect_args={'check_same_thread': False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    main.app.state.testing_session = testing_session
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()
    del main.app.state.testing_session
    engine.dispose()


def add_user(client, email, role='community_member', organization_id=None):
    with client.app.state.testing_session() as db:
        user = User(
            email=email,
            full_name=email.split('@')[0],
            password_hash='unused-test-hash',
            role=role,
            organization_id=organization_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, create_access_token(user.id)


def test_volunteer_profile_skill_verification_and_availability(volunteer_client):
    client = volunteer_client
    user_id, user_token = add_user(client, 'field.worker@example.org')
    with client.app.state.testing_session() as db:
        skill = Skill(name='first_aid', category='medical')
        db.add(skill)
        db.commit()
        skill_id = skill.id

    headers = {'Authorization': f'Bearer {user_token}'}
    created = client.post('/volunteers', headers=headers, json={'max_travel_km': 35})
    assert created.status_code == 201
    profile = created.json()
    assert profile['user_id'] == user_id
    assert profile['max_travel_km'] == 35

    added = client.post(
        f"/volunteers/{profile['id']}/skills",
        headers=headers,
        json={'skill_id': skill_id, 'level': 3, 'certification_name': 'First Aid'},
    )
    assert added.status_code == 201
    assert added.json()['verified'] is False
    assert client.post(
        f"/volunteers/{profile['id']}/skills/{skill_id}/verify",
        headers=headers,
    ).status_code == 403

    coordinator_id, coordinator_token = add_user(client, 'coord@example.org', 'coordinator')
    coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
    verified = client.post(
        f"/volunteers/{profile['id']}/skills/{skill_id}/verify",
        headers=coordinator_headers,
    )
    assert verified.status_code == 200
    assert verified.json()['verified'] is True

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    updated = client.patch(
        f"/volunteers/{profile['id']}/availability",
        headers=headers,
        json={
            'status': 'available',
            'windows': [
                {'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=4)).isoformat()}
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json()['availability_status'] == 'available'

    listing = client.get(
        '/volunteers?skill=first_aid&verified_only=true',
        headers=coordinator_headers,
    )
    assert listing.status_code == 200
    assert [item['id'] for item in listing.json()] == [profile['id']]

    with client.app.state.testing_session() as db:
        assert db.get(User, coordinator_id) is not None


def test_volunteer_validation_and_duplicate_profile(volunteer_client):
    client = volunteer_client
    _, token = add_user(client, 'duplicate@example.org')
    headers = {'Authorization': f'Bearer {token}'}

    assert client.post('/volunteers', headers=headers, json={'max_travel_km': 0}).status_code == 422
    assert client.post('/volunteers', headers=headers, json={}).status_code == 201
    assert client.post('/volunteers', headers=headers, json={}).status_code == 409

    now = datetime.now(timezone.utc)
    invalid_window = client.patch(
        '/volunteers/1/availability',
        headers=headers,
        json={
            'status': 'available',
            'windows': [{'starts_at': now.isoformat(), 'ends_at': now.isoformat()}],
        },
    )
    assert invalid_window.status_code == 422


def test_org_admin_can_only_view_and_verify_own_organization(volunteer_client):
    client = volunteer_client
    with client.app.state.testing_session() as db:
        organization = Organization(name='Rescue Group', organization_type='ngo')
        other_organization = Organization(name='Medical Group', organization_type='ngo')
        db.add_all([organization, other_organization])
        db.flush()
        org_id, other_org_id = organization.id, other_organization.id
        owner = User(
            email='org-volunteer@example.org',
            full_name='Org Volunteer',
            password_hash='unused-test-hash',
            role='volunteer',
            organization_id=org_id,
        )
        skill = Skill(name='water_purification', category='technical')
        org_admin = User(
            email='org-admin@example.org',
            full_name='Org Admin',
            password_hash='unused-test-hash',
            role='org_admin',
            organization_id=org_id,
        )
        other_admin = User(
            email='other-admin@example.org',
            full_name='Other Admin',
            password_hash='unused-test-hash',
            role='org_admin',
            organization_id=other_org_id,
        )
        db.add_all([owner, skill, org_admin, other_admin])
        db.flush()
        profile = VolunteerProfile(user_id=owner.id, organization_id=org_id)
        db.add(profile)
        db.flush()
        from app.models import VolunteerSkill

        db.add(VolunteerSkill(volunteer_id=profile.id, skill_id=skill.id))
        db.commit()
        profile_id, skill_id = profile.id, skill.id
        same_org_token = create_access_token(org_admin.id)
        other_org_token = create_access_token(other_admin.id)

    same_headers = {'Authorization': f'Bearer {same_org_token}'}
    other_headers = {'Authorization': f'Bearer {other_org_token}'}
    assert client.get('/volunteers', headers=same_headers).json()[0]['id'] == profile_id
    assert client.get('/volunteers', headers=other_headers).json() == []
    assert client.post(
        f'/volunteers/{profile_id}/skills/{skill_id}/verify', headers=same_headers
    ).status_code == 200
    assert client.post(
        f'/volunteers/{profile_id}/skills/{skill_id}/verify', headers=other_headers
    ).status_code == 403


def test_unavailable_volunteer_reopens_need_and_returns_replacements(volunteer_client):
    client = volunteer_client
    _, token = add_user(client, 'unavailable@example.org')
    headers = {'Authorization': f'Bearer {token}'}
    profile_id = client.post('/volunteers', headers=headers, json={}).json()['id']

    with client.app.state.testing_session() as db:
        location = Location(name='Unmapped Shelter', location_type='shelter')
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([location, incident])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='rescue',
            description='Rescue team required',
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        db.add(need)
        db.flush()
        profile = db.get(VolunteerProfile, profile_id)
        profile.availability_status = 'assigned'
        assignment = Assignment(need_id=need.id, volunteer_id=profile.id, status='accepted')
        db.add(assignment)
        db.commit()
        need_id, assignment_id = need.id, assignment.id

    response = client.patch(
        f'/volunteers/{profile_id}/availability',
        headers=headers,
        json={'status': 'unavailable'},
    )
    assert response.status_code == 200
    assert response.json()['affected_needs'][0]['need_id'] == need_id
    with client.app.state.testing_session() as db:
        assert db.get(Need, need_id).status == 'open'
        assert db.get(Assignment, assignment_id).status == 'cancelled'
        assert db.get(VolunteerProfile, profile_id).availability_status == 'unavailable'
        assert check_audit_chain(db) == (True, None)


def test_unavailable_change_does_not_cancel_en_route_assignment(volunteer_client):
    client = volunteer_client
    _, token = add_user(client, 'enroute@example.org')
    headers = {'Authorization': f'Bearer {token}'}
    profile_id = client.post('/volunteers', headers=headers, json={}).json()['id']

    with client.app.state.testing_session() as db:
        location = Location(name='Rescue Site', location_type='settlement')
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([location, incident])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='rescue',
            description='Rescue in progress',
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        db.add(need)
        db.flush()
        profile = db.get(VolunteerProfile, profile_id)
        profile.availability_status = 'assigned'
        assignment = Assignment(need_id=need.id, volunteer_id=profile.id, status='en_route')
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id

    response = client.patch(
        f'/volunteers/{profile_id}/availability',
        headers=headers,
        json={'status': 'unavailable'},
    )
    assert response.status_code == 409
    with client.app.state.testing_session() as db:
        assert db.get(Assignment, assignment_id).status == 'en_route'
