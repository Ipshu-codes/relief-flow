import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Assignment, Need, ResourceStock, User, VolunteerProfile
from app.security import get_current_user
from app.setup_local import seed_demo


@pytest.fixture()
def workspace_client(monkeypatch):
    import app.security as security

    monkeypatch.setattr(security, 'JWT_SECRET', secrets.token_urlsafe(48))
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_demo(db)
        coordinator = db.query(User).filter_by(role='coordinator').one()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: coordinator
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()
    engine.dispose()


def test_workspace_requires_login():
    with TestClient(app) as client:
        assert client.get('/workspace').status_code == 401


def test_workspace_and_cors(workspace_client):
    client, _ = workspace_client
    response = client.get('/workspace')
    assert response.status_code == 200
    assert len(response.json()['locations']) == 3
    response = client.options('/workspace', headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'GET'})
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'


def test_existing_matching_and_assignment_list(workspace_client):
    client, db = workspace_client
    need = db.query(Need).filter_by(category='technical_repair').one()
    volunteer = db.query(VolunteerProfile).one()
    response = client.post('/assignments', json={'need_id': need.id, 'volunteer_id': volunteer.id})
    assert response.status_code == 201, response.text
    assignment = response.json()
    assert assignment['status'] == 'proposed'
    assert client.get('/assignments').json()[0]['id'] == assignment['id']
    approved = client.post(f"/assignments/{assignment['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert db.get(Need, need.id).status != 'fulfilled'


def test_partial_delivery_and_retry(workspace_client):
    client, db = workspace_client
    need = db.query(Need).filter_by(category='water').one()
    stock = db.query(ResourceStock).one()
    allocation = {'need_id': need.id, 'stock_id': stock.id, 'quantity': 100, 'client_uuid': str(uuid4())}
    response = client.post('/allocations', json=allocation)
    assert response.status_code == 201, response.text
    movement_id = response.json()['id']
    assert client.post('/allocations', json=allocation).json()['id'] == movement_id
    for status in ('dispatched', 'delivered'):
        response = client.patch(f'/movements/{movement_id}/status', json={'status': status})
        assert response.status_code == 200, response.text
    confirmation = {'client_uuid': str(uuid4()), 'status': 'partial', 'quantity_received': 40}
    assert client.post(f'/movements/{movement_id}/confirm', json=confirmation).status_code == 200
    assert client.post(f'/movements/{movement_id}/confirm', json=confirmation).json()['duplicate']
    progress = client.get(f'/needs/{need.id}/progress').json()
    assert progress['confirmed'] == 40
    assert progress['remaining'] == 60
    movement = client.get('/movements').json()[0]
    assert movement['quantity_allocated'] == 100
    assert movement['quantity_dispatched'] == 100
    assert movement['quantity_received'] == 40
    assert movement['quantity_remaining'] == 60
    assert db.get(Need, need.id).status == 'partially_fulfilled'


def test_supplies_cannot_close_from_task_completion(workspace_client):
    client, db = workspace_client
    need = db.query(Need).filter_by(category='water').one()
    assignment = Assignment(need_id=need.id, volunteer_id=db.query(VolunteerProfile).one().id, status='on_site')
    db.add(assignment)
    db.commit()
    response = client.post(f'/assignments/{assignment.id}/complete', json={'completion_criteria_met': True, 'outcome_notes': 'Truck dispatched'})
    assert response.status_code == 409
    assert db.get(Need, need.id).quantity_fulfilled == 0


def test_wrong_resource_cannot_be_allocated(workspace_client):
    client, db = workspace_client
    need = db.query(Need).filter_by(category='technical_repair').one()
    stock = db.query(ResourceStock).one()
    response = client.post('/allocations', json={'need_id': need.id, 'stock_id': stock.id, 'quantity': 1})
    assert response.status_code == 409
    assert db.get(ResourceStock, stock.id).quantity_available == 1000


def test_volunteer_only_sees_own_assignments(workspace_client):
    client, db = workspace_client
    profile = db.query(VolunteerProfile).one()
    volunteer_user = db.get(User, profile.user_id)
    app.dependency_overrides[get_current_user] = lambda: volunteer_user
    assert client.get('/assignments').status_code == 200
    assert client.get('/situation?incident_id=1').status_code == 403
    assert client.post('/bottlenecks/scan?incident_id=1').status_code == 403


def test_synthetic_baseline_scan_has_evidence(workspace_client):
    client, _ = workspace_client
    response = client.post('/bottlenecks/scan?incident_id=1')
    assert response.status_code == 200, response.text
    flags = client.get('/bottlenecks?incident_id=1').json()
    assert flags
    assert all(flag['evidence'] and flag['explanation'] for flag in flags)


def test_failed_task_completion_reopens_need_and_frees_volunteer(workspace_client):
    client, db = workspace_client
    need = db.query(Need).filter_by(category='technical_repair').one()
    profile = db.query(VolunteerProfile).one()
    profile.availability_status = 'assigned'
    need.status = 'in_progress'
    assignment = Assignment(need_id=need.id, volunteer_id=profile.id, status='on_site')
    db.add(assignment)
    db.commit()
    response = client.post(f'/assignments/{assignment.id}/complete', json={'completion_criteria_met': False, 'outcome_notes': 'Further repairs required'})
    assert response.status_code == 200, response.text
    assert db.get(Need, need.id).status == 'open'
    assert db.get(VolunteerProfile, profile.id).availability_status == 'available'