from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.models import (
    DeliveryConfirmation,
    Incident,
    Location,
    Need,
    Organization,
    Resource,
    ResourceMovement,
    ResourceStock,
    User,
)
from app.security import create_access_token


@pytest.fixture
def resource_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'resource-test-secret-that-is-long-enough-123')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'resources.db'}",
        connect_args={'check_same_thread': False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    with Session(engine) as db:
        organization = Organization(name='Relief NGO', organization_type='ngo')
        resource = Resource(resource_type='water', unit='litre')
        location = Location(name='Ward 2', location_type='ward')
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        coordinator = User(
            email='stock-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        community = User(
            email='stock-community@example.org',
            full_name='Community',
            password_hash='test',
        )
        db.add_all([organization, resource, location, incident, coordinator, community])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='water',
            description='Drinking water for families',
            quantity_requested=20,
            unit='litre',
            urgency=5,
        )
        db.add(need)
        db.commit()
        client_values = {
            'organization_id': organization.id,
            'resource_id': resource.id,
            'location_id': location.id,
            'need_id': need.id,
            'coordinator_token': create_access_token(coordinator.id),
            'community_token': create_access_token(community.id),
        }

    with TestClient(main.app) as client:
        for key, value in client_values.items():
            setattr(client, key, value)
        client.testing_session = testing_session
        client.coordinator_headers = {'Authorization': f"Bearer {client.coordinator_token}"}
        client.community_headers = {'Authorization': f"Bearer {client.community_token}"}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_reservation_dispatch_partial_confirmation_and_idempotency(resource_client):
    client = resource_client
    stock_response = client.post(
        '/resources/stock',
        headers=client.coordinator_headers,
        json={
            'organization_id': client.organization_id,
            'resource_id': client.resource_id,
            'location_id': client.location_id,
            'quantity_available': 10,
        },
    )
    assert stock_response.status_code == 201
    stock_id = stock_response.json()['id']

    allocation_payload = {
        'need_id': client.need_id,
        'stock_id': stock_id,
        'quantity': 7,
        'client_uuid': '123e4567-e89b-12d3-a456-426614174001',
    }
    allocation = client.post('/allocations', headers=client.coordinator_headers, json=allocation_payload)
    assert allocation.status_code == 201
    movement_id = allocation.json()['id']
    assert allocation.json()['status'] == 'allocated'

    duplicate_allocation = client.post(
        '/allocations', headers=client.coordinator_headers, json=allocation_payload
    )
    assert duplicate_allocation.json()['duplicate'] is True

    with client.testing_session() as db:
        stock = db.get(ResourceStock, stock_id)
        assert stock.quantity_available == 3
        assert stock.quantity_reserved == 7
        assert db.get(Need, client.need_id).quantity_fulfilled == 0

    dispatched = client.patch(
        f'/movements/{movement_id}/status',
        headers=client.coordinator_headers,
        json={'status': 'dispatched'},
    )
    assert dispatched.status_code == 200
    delivered = client.patch(
        f'/movements/{movement_id}/status',
        headers=client.coordinator_headers,
        json={'status': 'delivered'},
    )
    assert delivered.status_code == 200
    dispatched_progress = client.get(
        f'/needs/{client.need_id}/progress', headers=client.coordinator_headers
    ).json()
    assert dispatched_progress['delivered'] == 7
    assert dispatched_progress['confirmed'] == 0
    assert dispatched_progress['remaining'] == 20

    confirmation_payload = {
        'client_uuid': '123e4567-e89b-12d3-a456-426614174002',
        'status': 'partial',
        'quantity_received': 3,
        'notes': 'Three litres received.',
    }
    confirmed = client.post(
        f'/movements/{movement_id}/confirm',
        headers=client.community_headers,
        json=confirmation_payload,
    )
    assert confirmed.status_code == 200

    duplicate_confirmation = client.post(
        f'/movements/{movement_id}/confirm',
        headers=client.community_headers,
        json=confirmation_payload,
    )
    assert duplicate_confirmation.json()['duplicate'] is True

    with client.testing_session() as db:
        movement = db.get(ResourceMovement, movement_id)
        need = db.get(Need, client.need_id)
        assert movement.status == 'delivered'
        assert movement.quantity_confirmed == 3
        assert need.quantity_fulfilled == 3
        assert need.status == 'partially_fulfilled'
        assert db.scalar(select(DeliveryConfirmation).where(
            DeliveryConfirmation.client_uuid == confirmation_payload['client_uuid']
        )) is not None
    partial_progress = client.get(
        f'/needs/{client.need_id}/progress', headers=client.coordinator_headers
    ).json()
    assert partial_progress['remaining'] == 17
    assert partial_progress['unconfirmed_delivered'] == 4

    final_confirmation = client.post(
        f'/movements/{movement_id}/confirm',
        headers=client.community_headers,
        json={
            'client_uuid': '123e4567-e89b-12d3-a456-426614174003',
            'status': 'full',
            'quantity_received': 4,
        },
    )
    assert final_confirmation.status_code == 200
    with client.testing_session() as db:
        movement = db.get(ResourceMovement, movement_id)
        need = db.get(Need, client.need_id)
        assert movement.status == 'confirmed'
        assert movement.quantity_confirmed == 7
        assert need.quantity_fulfilled == 7
        assert need.status == 'partially_fulfilled'


def test_stock_reservation_rejects_overbooking_and_bad_confirmation(resource_client):
    client = resource_client
    assert client.post(
        '/resources/stock',
        headers=client.community_headers,
        json={'organization_id': client.organization_id, 'resource_id': client.resource_id, 'quantity_available': 5},
    ).status_code == 403
    stock = client.post(
        '/resources/stock',
        headers=client.coordinator_headers,
        json={'organization_id': client.organization_id, 'resource_id': client.resource_id, 'quantity_available': 5},
    ).json()
    result = client.post(
        '/allocations',
        headers=client.coordinator_headers,
        json={
            'need_id': client.need_id,
            'stock_id': stock['id'],
            'quantity': 6,
        },
    )
    assert result.status_code == 409
    invalid_uuid = client.post(
        '/allocations',
        headers=client.coordinator_headers,
        json={'need_id': client.need_id, 'stock_id': stock['id'], 'quantity': 1, 'client_uuid': 'not-a-uuid'},
    )
    assert invalid_uuid.status_code == 422
