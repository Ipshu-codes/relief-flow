import json
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import BaselineFeature, HazardZone, HistoricalIncident, Location, User
from app.security import create_access_token


@pytest.fixture
def intelligence_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'intelligence-test-secret-long-enough-123456')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'intelligence-api.db'}",
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
            email='baseline-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        community = User(
            email='baseline-community@example.org',
            full_name='Community',
            password_hash='test',
        )
        db.add_all([coordinator, community])
        db.commit()
        coordinator_token = create_access_token(coordinator.id)
        community_token = create_access_token(community.id)

    with TestClient(main.app) as client:
        client.testing_session = testing_session
        client.coordinator_headers = {'Authorization': f'Bearer {coordinator_token}'}
        client.community_headers = {'Authorization': f'Bearer {community_token}'}
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_baseline_csv_and_location_profile_keep_data_classes_separate(intelligence_client):
    client = intelligence_client
    csv_content = (
        'name,location_type,latitude,longitude,estimated_households,estimated_population,source,confidence,data_date\n'
        'Ward 4,ward,27.70,85.30,240,1100,census,0.85,2025-01-01T00:00:00Z\n'
    )
    response = client.post(
        '/api/admin/import/baseline',
        headers=client.coordinator_headers,
        files={'file': ('settlements.csv', csv_content, 'text/csv')},
    )
    assert response.status_code == 200
    assert response.json() == {'locations_created': 1, 'baselines_written': 1, 'features_imported': 0}

    from app.models import BaselineSettlement

    with client.testing_session() as db:
        location = db.scalar(select(Location).where(Location.name == 'Ward 4'))
        baseline = db.scalar(select(BaselineSettlement).where(BaselineSettlement.location_id == location.id))
        location_id = location.id
        assert baseline.estimated_households == 240
        assert baseline.confidence == 0.85

    profile = client.get(f'/locations/{location_id}/profile', headers=client.coordinator_headers)
    assert profile.status_code == 200
    payload = profile.json()
    assert payload['baseline_estimate']['estimated_households'] == 240
    assert payload['baseline_estimate']['verification_status'] == 'estimated'
    assert payload['reported_needs'] == []
    assert payload['verified_damage'] == []
    assert payload['assistance_confirmed_quantity'] == 0


def test_baseline_geojson_imports_settlement_and_feature(intelligence_client):
    client = intelligence_client
    geojson = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [85.31, 27.71]},
                'properties': {
                    'name': 'Riverside',
                    'location_type': 'settlement',
                    'estimated_households': 90,
                    'source': 'OSM',
                },
            },
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[[85.3, 27.7], [85.4, 27.7], [85.4, 27.8], [85.3, 27.7]]],
                },
                'properties': {
                    'name': 'Polygon Settlement',
                    'location_type': 'ward',
                    'estimated_households': 15,
                    'source': 'manual',
                },
            },
            {
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [85.32, 27.72]},
                'properties': {'name': 'Health Post', 'feature_type': 'health_post', 'source': 'OSM'},
            },
            {
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': []},
                'properties': {
                    'name': 'River Flood Zone',
                    'hazard_type': 'flood',
                    'risk_level': 4,
                    'source': 'manual',
                },
            },
        ],
    }
    response = client.post(
        '/api/admin/import/baseline',
        headers=client.coordinator_headers,
        files={'file': ('region.geojson', json.dumps(geojson), 'application/geo+json')},
    )
    assert response.status_code == 200
    assert response.json()['locations_created'] == 2
    assert response.json()['features_imported'] == 2
    with client.testing_session() as db:
        polygon_location = db.scalar(
            select(Location).where(Location.name == 'Polygon Settlement')
        )
        assert polygon_location.boundary['type'] == 'Polygon'
        assert db.scalar(select(BaselineFeature).where(BaselineFeature.feature_type == 'health_post'))
        assert db.scalar(select(HazardZone).where(HazardZone.hazard_type == 'flood'))
        assert check_audit_chain(db) == (True, None)


def test_historical_import_and_baseline_failure_cases(intelligence_client):
    client = intelligence_client
    historical = (
        'incident_type,occurred_at,affected_area,damage_summary,source\n'
        'flood,2020-08-01T00:00:00Z,Central Nepal,Bridge damaged,BIPAD\n'
    )
    imported = client.post(
        '/api/admin/import/historical',
        headers=client.coordinator_headers,
        files={'file': ('history.csv', historical, 'text/csv')},
    )
    assert imported.status_code == 200
    assert imported.json()['historical_incidents_imported'] == 1

    forbidden = client.post(
        '/api/admin/import/baseline',
        headers=client.community_headers,
        files={'file': ('settlements.csv', 'name,location_type\n', 'text/csv')},
    )
    assert forbidden.status_code == 403

    invalid = client.post(
        '/api/admin/import/baseline',
        headers=client.coordinator_headers,
        files={
            'file': (
                'invalid.csv',
                'name,location_type,latitude,longitude,estimated_households\nBad,settlement,91,85,3\n',
                'text/csv',
            )
        },
    )
    assert invalid.status_code == 422
    with client.testing_session() as db:
        assert db.scalar(select(func.count()).select_from(HistoricalIncident)) == 1
        assert db.scalar(select(func.count()).select_from(Location)) == 0


def test_geojson_historical_import_and_verified_damage_assessment(intelligence_client):
    client = intelligence_client
    historical_geojson = {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [85.3, 27.7]},
            'properties': {
                'incident_type': 'landslide',
                'occurred_at': '2019-06-10T00:00:00Z',
                'source': 'BIPAD',
            },
        }],
    }
    imported = client.post(
        '/api/admin/import/historical',
        headers=client.coordinator_headers,
        files={'file': ('history.geojson', json.dumps(historical_geojson), 'application/geo+json')},
    )
    assert imported.status_code == 200
    assert imported.json()['historical_incidents_imported'] == 1

    baseline_response = client.post(
        '/api/admin/import/baseline',
        headers=client.coordinator_headers,
        files={
            'file': (
                'settlements.csv',
                'name,location_type\nWard 8,ward\n',
                'text/csv',
            )
        },
    )
    with client.testing_session() as db:
        location = db.scalar(select(Location).where(Location.name == 'Ward 8'))
        location_id = location.id

    assessment = client.post(
        f'/locations/{location_id}/damage-assessments',
        headers=client.coordinator_headers,
        json={'kind': 'post', 'damage_level': 3, 'details': 'Several homes flooded.'},
    )
    assert assessment.status_code == 201
    assert assessment.json()['verified'] is True
    profile = client.get(
        f'/locations/{location_id}/profile',
        headers=client.coordinator_headers,
    )
    assert profile.json()['verified_damage'][0]['details'] == 'Several homes flooded.'
