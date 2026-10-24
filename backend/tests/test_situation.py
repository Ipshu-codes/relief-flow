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
from app.models import (
    BaselineSettlement,
    BottleneckFlag,
    DamageAssessment,
    DeliveryConfirmation,
    HazardZone,
    Incident,
    Location,
    Need,
    Organization,
    Assignment,
    AICallLog,
    RawReport,
    Resource,
    ResourceMovement,
    ResourceStock,
    Route,
    User,
    VolunteerProfile,
)
from app.security import create_access_token


@pytest.fixture
def situation_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'situation-test-secret-long-enough-for-jwt-123')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'situation.db'}",
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
            email='situation-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        community = User(
            email='situation-community@example.org',
            full_name='Community',
            password_hash='test',
        )
        active_location = Location(
            name='School Shelter',
            location_type='shelter',
            latitude=27.7,
            longitude=85.3,
        )
        silent_location = Location(
            name='High Risk Settlement',
            location_type='settlement',
            latitude=27.8,
            longitude=85.4,
        )
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        organization = Organization(name='Water Relief', organization_type='ngo')
        resource = Resource(resource_type='water', unit='litre')
        db.add_all([coordinator, community, active_location, silent_location, incident, organization, resource])
        db.flush()
        baseline = BaselineSettlement(
            location_id=silent_location.id,
            estimated_households=100,
            estimated_population=500,
            source='census',
            confidence=0.8,
        )
        zone = HazardZone(
            name='Riverside flood zone',
            location_id=silent_location.id,
            geometry={'type': 'Polygon', 'coordinates': []},
            hazard_type='flood',
            risk_level=4,
            source='manual',
        )
        need = Need(
            incident_id=incident.id,
            location_id=active_location.id,
            category='medical',
            description='Nurse needed',
            required_skills=['nurse'],
            quantity_requested=10,
            unit='people',
            urgency=5,
            last_updated_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        blocked_need = Need(
            incident_id=incident.id,
            location_id=active_location.id,
            category='rescue',
            description='Route blocked for rescue team',
            required_skills=['boat_rescue'],
            quantity_requested=1,
            unit='team',
            urgency=5,
            status='in_progress',
        )
        profile = VolunteerProfile(user_id=coordinator.id, base_location_id=active_location.id)
        db.add_all([baseline, zone, need, blocked_need, profile])
        db.flush()
        blocked_route = Route(
            from_point={'latitude': 27.7, 'longitude': 85.3},
            to_point={'latitude': 27.71, 'longitude': 85.31},
            geometry=[{'latitude': 27.7, 'longitude': 85.3}, {'latitude': 27.71, 'longitude': 85.31}],
            distance_km=2,
            duration_min=5,
            blocked_segments_considered=[1],
            avoids_blockages=False,
            engine='estimate',
        )
        db.add(blocked_route)
        db.flush()
        db.add(
            Assignment(
                need_id=blocked_need.id,
                volunteer_id=profile.id,
                route_id=blocked_route.id,
                status='accepted',
            )
        )
        stock = ResourceStock(
            organization_id=organization.id,
            resource_id=resource.id,
            location_id=active_location.id,
            quantity_available=0,
            quantity_reserved=0,
        )
        db.add(stock)
        db.flush()
        movement = ResourceMovement(
            need_id=need.id,
            resource_id=resource.id,
            stock_id=stock.id,
            quantity=10,
            quantity_confirmed=0,
            status='delivered',
            allocated_by=coordinator.id,
            delivered_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        raw_report = RawReport(
            incident_id=incident.id,
            text='Need assistance near river',
            channel='web',
            client_uuid='123e4567-e89b-12d3-a456-426614174111',
            received_at=datetime.now(timezone.utc) - timedelta(days=3),
            parse_status='pending',
        )
        duplicate_report_a = RawReport(
            incident_id=incident.id,
            text='Need water for families at the school',
            channel='web',
            client_uuid='123e4567-e89b-12d3-a456-426614174113',
            received_at=datetime.now(timezone.utc),
            parse_status='pending',
        )
        duplicate_report_b = RawReport(
            incident_id=incident.id,
            text='Need water for families near the school',
            channel='sms',
            client_uuid='123e4567-e89b-12d3-a456-426614174114',
            received_at=datetime.now(timezone.utc),
            parse_status='pending',
        )
        damage = DamageAssessment(
            location_id=active_location.id,
            kind='post',
            verified=True,
            verified_by=coordinator.id,
            damage_level=3,
            details='School wall damaged',
        )
        db.add_all([movement, raw_report, duplicate_report_a, duplicate_report_b, damage])
        db.flush()
        db.add(
            DeliveryConfirmation(
                movement_id=movement.id,
                client_uuid='123e4567-e89b-12d3-a456-426614174112',
                confirmed_by=community.id,
                status='not_received',
                quantity_received=0,
            )
        )
        db.commit()
        incident_id = incident.id
        coordinator_token = create_access_token(coordinator.id)
        community_token = create_access_token(community.id)

    with TestClient(main.app) as client:
        client.incident_id = incident_id
        client.testing_session = testing_session
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.community_headers = {'Authorization': f'Bearer {community_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_bottleneck_scan_flags_m2_done_when_cases_and_is_idempotent(situation_client):
    client = situation_client
    first_scan = client.post(
        f'/bottlenecks/scan?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert first_scan.status_code == 200
    flags = client.get(
        f'/bottlenecks?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    ).json()
    flag_types = {flag['type'] for flag in flags}
    assert {'silent_area', 'stalled_delivery', 'delivery_mismatch', 'unstaffed_need', 'stale_report', 'blocked_access'} <= flag_types

    first_count = len(flags)
    silent_flag = next(flag for flag in flags if flag['type'] == 'silent_area')
    acknowledged = client.patch(
        f"/bottlenecks/{silent_flag['id']}",
        headers=client.coordinator_headers,
        json={'status': 'acknowledged'},
    )
    assert acknowledged.status_code == 200
    second_scan = client.post(
        f'/bottlenecks/scan?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert second_scan.status_code == 200
    rescanned_flags = client.get(
        f'/bottlenecks?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    ).json()
    assert len(rescanned_flags) == first_count
    assert next(flag for flag in rescanned_flags if flag['id'] == silent_flag['id'])['status'] == 'acknowledged'


def test_situation_and_recovery_keep_estimates_reports_and_verified_damage_separate(situation_client):
    client = situation_client
    situation = client.get(
        f'/situation?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert situation.status_code == 200
    school = next(
        row for row in situation.json()['locations']
        if row['location_name'] == 'School Shelter'
    )
    assert school['reported_need_count'] == 2
    assert school['verified_damage_count'] == 1
    assert school['reported_quantity_fulfilled'] == 0

    recovery = client.get(
        f'/reports/recovery?incident_id={client.incident_id}',
        headers=client.coordinator_headers,
    )
    assert recovery.status_code == 200
    assert recovery.json()['baseline_estimated_households'] == 100
    assert recovery.json()['reported_needs']['remaining_quantity'] == 11
    assert recovery.json()['verified_damage_assessments'][0]['damage_level'] == 3


def test_bottleneck_routes_require_coordinator(situation_client):
    client = situation_client
    assert client.post(
        f'/bottlenecks/scan?incident_id={client.incident_id}',
        headers=client.community_headers,
    ).status_code == 403


def test_optional_ai_judges_and_explains_without_changing_counts(situation_client, monkeypatch):
    client = situation_client

    class FakeIntelligenceClient:
        def __init__(self, host, timeout):
            pass

        async def generate(self, **kwargs):
            schema_name = kwargs['format']['title']
            if schema_name == 'DuplicateVerdict':
                output = {
                    'same_event': True,
                    'confidence': 'medium',
                    'rationale': 'The requests have closely matching wording.',
                }
            elif schema_name == 'BottleneckExplanation':
                output = {
                    'explanation': 'The delivery lacks a complete receipt confirmation.',
                    'suggested_action': 'Contact the receiving group.',
                }
            else:
                output = {
                    'narrative': 'Some assistance is confirmed while needs remain.',
                    'confidence': 'medium',
                }
            return SimpleNamespace(response=json.dumps(output))

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', FakeIntelligenceClient)
    scan = client.post(
        f'/bottlenecks/scan?incident_id={client.incident_id}&judge_duplicates=true',
        headers=client.coordinator_headers,
    )
    assert scan.status_code == 200
    assert scan.json()['duplicate_pairs_judged'] >= 1

    flags = client.get(
        f'/bottlenecks?incident_id={client.incident_id}&explain=true',
        headers=client.coordinator_headers,
    )
    duplicate = next(flag for flag in flags.json() if flag['type'] == 'duplicate_report_candidate')
    assert duplicate['status'] == 'open'
    assert duplicate['evidence']['duplicate_judgment']['same_event'] is True
    explained_flag = next(flag for flag in flags.json() if flag.get('explanation_source') == 'ai')
    assert explained_flag['explanation_source'] == 'ai'

    recovery = client.get(
        f'/reports/recovery?incident_id={client.incident_id}&explain=true',
        headers=client.coordinator_headers,
    )
    assert recovery.status_code == 200
    assert recovery.json()['summary_source'] == 'ai'
    assert recovery.json()['summary'] == 'Some assistance is confirmed while needs remain.'
    with client.testing_session() as db:
        assert db.query(AICallLog).count() >= 3
