import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.ai import client as ai_client
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import (
    AICallLog,
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
def assignment_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'assignment-test-secret-long-enough-to-sign-123')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'assignment-api.db'}",
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
            email='assignment-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        volunteer_user = User(
            email='assignment-volunteer@example.org',
            full_name='Volunteer',
            password_hash='test',
            role='volunteer',
        )
        origin = Location(name='Volunteer Base', location_type='settlement', latitude=27.70, longitude=85.30)
        destination = Location(name='Shelter', location_type='shelter', latitude=27.70, longitude=85.32)
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        skill = Skill(name='first_aid', category='medical')
        db.add_all([coordinator, volunteer_user, origin, destination, incident, skill])
        db.flush()
        profile = VolunteerProfile(user_id=volunteer_user.id, base_location_id=origin.id, max_travel_km=50)
        db.add(profile)
        db.flush()
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        db.add_all([
            VolunteerSkill(volunteer_id=profile.id, skill_id=skill.id, level=4, verified=True),
            AvailabilityWindow(
                volunteer_id=profile.id,
                starts_at=start - timedelta(minutes=30),
                ends_at=start + timedelta(hours=4),
            ),
        ])
        need = Need(
            incident_id=incident.id,
            location_id=destination.id,
            category='medical',
            description='First aid support needed',
            required_skills=['first_aid'],
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        db.add(need)
        db.commit()
        db.refresh(need)
        need_id, profile_id = need.id, profile.id
        task_start = start.isoformat()
        task_end = (start + timedelta(hours=1)).isoformat()
        coordinator_token = create_access_token(coordinator.id)
        volunteer_token = create_access_token(volunteer_user.id)

    main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main.app) as client:
        client.need_id = need_id
        client.profile_id = profile_id
        client.task_start = task_start
        client.task_end = task_end
        client.testing_session = testing_session
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.volunteer_headers = {'Authorization': f'Bearer {volunteer_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_assignment_proposal_approval_and_completion(assignment_client, monkeypatch):
    client = assignment_client

    class FakeOllamaClient:
        def __init__(self, host, timeout):
            pass

        async def generate(self, **kwargs):
            candidate_data = json.loads(kwargs['prompt'].split('Candidates: ', 1)[1])
            return SimpleNamespace(
                response=json.dumps(
                    {
                        'explanations': [
                            {'volunteer_id': item['volunteer_id'], 'reason': 'Verified skill and feasible route.'}
                            for item in candidate_data
                        ]
                    }
                )
            )

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', FakeOllamaClient)
    matches = client.post(
        f'/needs/{client.need_id}/match?explain=true',
        headers=client.coordinator_headers,
        json={'starts_at': client.task_start, 'ends_at': client.task_end},
    )
    assert matches.status_code == 200
    assert matches.json()['candidates'][0]['volunteer_id'] == client.profile_id
    assert matches.json()['candidates'][0]['explanation_source'] == 'ai'

    proposed = client.post(
        '/assignments',
        headers=client.coordinator_headers,
        json={
            'need_id': client.need_id,
            'volunteer_id': client.profile_id,
            'starts_at': client.task_start,
            'ends_at': client.task_end,
        },
    )
    assert proposed.status_code == 201
    assignment_id = proposed.json()['id']
    assert proposed.json()['status'] == 'proposed'
    assert proposed.json()['required_skills'] == ['first_aid']
    with client.testing_session() as db:
        db.get(Need, client.need_id).required_skills = []
        db.commit()

    approved = client.post(
        f'/assignments/{assignment_id}/approve',
        headers=client.coordinator_headers,
    )
    assert approved.status_code == 200
    assert approved.json()['status'] == 'approved'

    accepted = client.post(
        f'/assignments/{assignment_id}/accept',
        headers=client.volunteer_headers,
    )
    assert accepted.status_code == 200
    for status in ('en_route', 'on_site'):
        updated = client.patch(
            f'/assignments/{assignment_id}/status',
            headers=client.volunteer_headers,
            json={'status': status},
        )
        assert updated.status_code == 200
        assert updated.json()['status'] == status

    completed = client.post(
        f'/assignments/{assignment_id}/complete',
        headers=client.volunteer_headers,
        json={'completion_criteria_met': True, 'outcome_notes': 'Team delivered first aid.'},
    )
    assert completed.status_code == 200
    assert completed.json()['status'] == 'completed'
    assert completed.json()['completion_criteria_met'] is True

    with client.testing_session() as db:
        assert db.get(Need, client.need_id).status == 'fulfilled'
        assert check_audit_chain(db) == (True, None)


def test_assignment_rejects_infeasible_and_premature_completion(assignment_client):
    client = assignment_client
    with client.testing_session() as db:
        skill_row = db.scalar(select(VolunteerSkill).where(VolunteerSkill.volunteer_id == client.profile_id))
        skill_row.verified = False
        db.commit()

    assert client.post(
        f'/needs/{client.need_id}/match',
        headers=client.coordinator_headers,
    ).json()['candidates'] == []
    assert client.post(
        '/assignments',
        headers=client.coordinator_headers,
        json={
            'need_id': client.need_id,
            'volunteer_id': client.profile_id,
            'starts_at': client.task_start,
            'ends_at': client.task_end,
        },
    ).status_code == 409
    assert client.post(
        '/assignments/999/complete',
        headers=client.volunteer_headers,
        json={'completion_criteria_met': True},
    ).status_code == 404


def test_match_maps_unannotated_need_without_mutating_it(assignment_client, monkeypatch):
    client = assignment_client
    with client.testing_session() as db:
        need = db.get(Need, client.need_id)
        need.required_skills = []
        db.commit()

    class FakeSkillMapper:
        def __init__(self, host, timeout):
            pass

        async def generate(self, **kwargs):
            return SimpleNamespace(response='{"skills":["first_aid"]}')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', FakeSkillMapper)
    response = client.post(
        f'/needs/{client.need_id}/match',
        headers=client.coordinator_headers,
        json={'starts_at': client.task_start, 'ends_at': client.task_end},
    )

    assert response.status_code == 200
    assert response.json()['required_skills'] == ['first_aid']
    assert response.json()['skills_source'] == 'ai'
    assert response.json()['candidates'][0]['volunteer_id'] == client.profile_id
    with client.testing_session() as db:
        assert db.get(Need, client.need_id).required_skills == []
        assert db.query(AICallLog).filter_by(task='skill_mapper').count() == 1
