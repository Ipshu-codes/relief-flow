from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.models import (
    Assignment,
    AvailabilityWindow,
    Incident,
    Location,
    Need,
    Skill,
    User,
    VolunteerProfile,
    VolunteerSkill,
)
from app.security import create_access_token


@pytest.fixture
def coverage_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'coverage-test-secret-with-at-least-32-characters')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'coverage-api.db'}",
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
            email='coverage-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        unauthorized = User(
            email='coverage-community@example.org',
            full_name='Community member',
            password_hash='test',
        )
        source = Location(name='Source Village', location_type='settlement', latitude=27.70, longitude=85.30)
        target = Location(name='Target Shelter', location_type='shelter', latitude=27.70, longitude=85.32)
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        skill = Skill(name='nurse', category='medical')
        db.add_all([coordinator, unauthorized, source, target, incident, skill])
        db.flush()

        target_need = Need(
            incident_id=incident.id,
            location_id=target.id,
            category='medical',
            description='Nurse needed at shelter',
            required_skills=['nurse'],
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        db.add(target_need)
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc) + timedelta(hours=2)
        profiles = []
        for index, willing in enumerate((True, False)):
            user = User(
                email=f'coverage-volunteer-{index}@example.org',
                full_name=f'Volunteer {index}',
                password_hash='test',
                role='volunteer',
            )
            db.add(user)
            db.flush()
            profile = VolunteerProfile(
                user_id=user.id,
                base_location_id=source.id,
                max_travel_km=50,
                willing_to_relocate=willing,
            )
            db.add(profile)
            db.flush()
            profiles.append(profile.id)
            db.add_all([
                VolunteerSkill(volunteer_id=profile.id, skill_id=skill.id, level=4, verified=True),
                AvailabilityWindow(volunteer_id=profile.id, starts_at=start, ends_at=end),
            ])
        db.commit()
        incident_id = incident.id
        coordinator_token = create_access_token(coordinator.id)
        unauthorized_token = create_access_token(unauthorized.id)

    with TestClient(main.app) as client:
        client.incident_id = incident_id
        client.testing_session = testing_session
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.unauthorized_headers = {'Authorization': f'Bearer {unauthorized_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_coverage_suggests_only_willing_buffered_reassignment(coverage_client):
    client = coverage_client
    coverage = client.get(
        f'/coverage?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert coverage.status_code == 200
    rows = coverage.json()['locations']
    source = next(row for row in rows if row['location_name'] == 'Source Village')
    target = next(row for row in rows if row['location_name'] == 'Target Shelter')
    assert source['available'] == 2
    assert source['surplus'] == 1
    assert target['shortage'] == 1

    response = client.get(
        f'/reassignment-suggestions?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert response.status_code == 200
    suggestions = response.json()['suggestions']
    assert len(suggestions) == 1
    assert suggestions[0]['tradeoff']['source_available_after'] == 1
    assert suggestions[0]['proposed_assignment']['proposed_by'] == 'coordinator'
    assert 'shortage of 1' in suggestions[0]['explanation']
    with client.testing_session() as db:
        assert db.scalar(select(Assignment.id)) is None


def test_coverage_is_coordinator_only_and_unknown_incident_is_404(coverage_client):
    client = coverage_client
    assert client.get(
        f'/coverage?incident_id={client.incident_id}',
        headers=client.unauthorized_headers,
    ).status_code == 403
    assert client.get(
        '/coverage?incident_id=999',
        headers=client.coordinator_headers,
    ).status_code == 404
