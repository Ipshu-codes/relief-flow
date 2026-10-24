from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import main, security
from app.db import Base, get_db
from app.ledger import check_audit_chain
from app.models import Assignment, Incident, Location, Need, Route, User, VolunteerProfile
from app.security import create_access_token


def test_new_blockage_recomputes_active_assignment_route(tmp_path, monkeypatch):
    monkeypatch.setattr(security, 'JWT_SECRET', 'blockage-recompute-test-secret-long-enough-123')
    engine = create_engine(
        f"sqlite:///{tmp_path / 'blockage-recompute.db'}",
        connect_args={'check_same_thread': False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        coordinator = User(
            email='blockage-coordinator@example.org',
            full_name='Coordinator',
            password_hash='test',
            role='coordinator',
        )
        volunteer_user = User(
            email='active-volunteer@example.org',
            full_name='Active Volunteer',
            password_hash='test',
            role='volunteer',
        )
        origin = Location(name='Base', location_type='settlement', latitude=27.70, longitude=85.30)
        destination = Location(name='Shelter', location_type='shelter', latitude=27.70, longitude=85.36)
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([coordinator, volunteer_user, origin, destination, incident])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=destination.id,
            category='rescue',
            description='Rescue team required',
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        profile = VolunteerProfile(
            user_id=volunteer_user.id,
            base_location_id=origin.id,
            availability_status='assigned',
        )
        db.add_all([need, profile])
        db.flush()
        route = Route(
            from_point={'latitude': origin.latitude, 'longitude': origin.longitude},
            to_point={'latitude': destination.latitude, 'longitude': destination.longitude},
            geometry=[
                {'latitude': origin.latitude, 'longitude': origin.longitude},
                {'latitude': destination.latitude, 'longitude': destination.longitude},
            ],
            distance_km=5,
            duration_min=10,
            blocked_segments_considered=[],
            avoids_blockages=True,
            engine='estimate',
        )
        db.add(route)
        db.flush()
        assignment = Assignment(
            need_id=need.id,
            volunteer_id=profile.id,
            route_id=route.id,
            status='accepted',
            eta=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(assignment)
        db.commit()
        assignment_id, previous_route_id = assignment.id, route.id
        coordinator_token = create_access_token(coordinator.id)

    def override_get_db():
        with testing_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(main.app).post(
            '/blockages',
            headers={'Authorization': f'Bearer {coordinator_token}'},
            json={'latitude': 27.70, 'longitude': 85.33},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()['recomputed_routes']
    with Session(engine) as db:
        updated = db.get(Assignment, assignment_id)
        assert updated.route_id != previous_route_id
        assert db.get(Route, updated.route_id).avoids_blockages is True
        assert check_audit_chain(db) == (True, None)

    engine.dispose()
