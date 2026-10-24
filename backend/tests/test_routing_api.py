import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.models import User
from app.security import create_access_token


@pytest.fixture
def routing_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'routing-test-secret-that-is-long-enough-123')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'routing-api.db'}",
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
            email='routing-coordinator@example.org',
            full_name='Routing Coordinator',
            password_hash='unused-test-hash',
            role='coordinator',
        )
        community_member = User(
            email='routing-member@example.org',
            full_name='Community Member',
            password_hash='unused-test-hash',
        )
        db.add_all([coordinator, community_member])
        db.commit()
        coordinator_token = create_access_token(coordinator.id)
        member_token = create_access_token(community_member.id)

    with TestClient(main.app) as client:
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.member_headers = {'Authorization': f'Bearer {member_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_verified_blockage_changes_persisted_route(routing_client):
    client = routing_client
    blockage = client.post(
        '/blockages',
        headers=client.coordinator_headers,
        json={'latitude': 27.70, 'longitude': 85.33},
    )
    assert blockage.status_code == 201
    assert blockage.json()['verified'] is True

    request = {
        'from_latitude': 27.70,
        'from_longitude': 85.30,
        'to_latitude': 27.70,
        'to_longitude': 85.36,
    }
    blocked_route = client.post('/routes/compute', headers=client.coordinator_headers, json=request)
    assert blocked_route.status_code == 200
    assert blocked_route.json()['source'] == 'estimate'
    assert blocked_route.json()['avoids_blockages'] is True
    assert blocked_route.json()['blocked_segments_considered'] == [blockage.json()['id']]

    cleared = client.patch(
        f"/blockages/{blockage.json()['id']}/clear",
        headers=client.coordinator_headers,
    )
    assert cleared.status_code == 200
    clear_route = client.post('/routes/compute', headers=client.coordinator_headers, json=request)
    assert clear_route.json()['blocked_segments_considered'] == []
    assert len(clear_route.json()['geometry']) == 2


def test_blockages_require_coordinator_and_validate_coordinates(routing_client):
    client = routing_client
    payload = {'latitude': 27.7, 'longitude': 85.3}
    assert client.post('/blockages', headers=client.member_headers, json=payload).status_code == 403
    assert client.post(
        '/blockages',
        headers=client.coordinator_headers,
        json={'latitude': 100, 'longitude': 85.3},
    ).status_code == 422
    assert client.post('/routes/compute', json={}).status_code == 401
