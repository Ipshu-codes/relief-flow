import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main, security
from app.db import Base, get_db
from app.models import User
from app.security import create_access_token, hash_password


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'test-secret-that-is-at-least-32-characters')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth-test.db'}",
        connect_args={'check_same_thread': False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    main.app.state.testing_session = testing_session
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    del main.app.state.testing_session
    engine.dispose()


def test_register_login_me_and_role_protection(client):
    registration = client.post(
        '/auth/register',
        json={
            'email': 'Responder@example.com',
            'full_name': 'Local Responder',
            'password': 'a-long-test-password',
            'role': 'admin',
        },
    )
    assert registration.status_code == 201
    assert registration.json()['email'] == 'responder@example.com'
    assert registration.json()['role'] == 'community_member'

    login = client.post(
        '/auth/login',
        json={'email': 'RESPONDER@example.com', 'password': 'a-long-test-password'},
    )
    assert login.status_code == 200
    token = login.json()['access_token']

    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200
    assert me.json()['role'] == 'community_member'
    assert client.get('/api/admin/queue', headers={'Authorization': f'Bearer {token}'}).status_code == 403

    with client.app.state.testing_session() as db:
        admin = User(
            email='admin@example.com',
            full_name='Administrator',
            password_hash=hash_password('another-test-password'),
            role='admin',
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        admin_token = create_access_token(admin.id)

    queue = client.get('/api/admin/queue', headers={'Authorization': f'Bearer {admin_token}'})
    assert queue.status_code == 200


def test_auth_failure_cases(client):
    payload = {
        'email': 'member@example.com',
        'full_name': 'Member',
        'password': 'a-long-test-password',
    }
    assert client.post('/auth/register', json=payload).status_code == 201
    assert client.post('/auth/register', json=payload).status_code == 409
    assert client.post(
        '/auth/login',
        json={'email': payload['email'], 'password': 'incorrect-password'},
    ).status_code == 401
    assert client.get('/auth/me').status_code == 401
