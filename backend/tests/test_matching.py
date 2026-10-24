from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AvailabilityWindow, Incident, Location, Need, Skill, User, VolunteerProfile, VolunteerSkill
from app.services.matching import build_match_candidates


def test_match_candidates_require_verified_skill_and_covering_window(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matching.db'}")
    Base.metadata.create_all(bind=engine)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=2)
    ends_at = starts_at + timedelta(hours=2)

    with Session(engine) as db:
        origin = Location(name='Base', location_type='ward', latitude=27.70, longitude=85.30)
        destination = Location(name='Shelter', location_type='shelter', latitude=27.70, longitude=85.32)
        incident = Incident(incident_type='flood', started_at=starts_at)
        user = User(email='nurse@example.org', full_name='Nurse', password_hash='test')
        skill = Skill(name='nurse', category='medical')
        db.add_all([origin, destination, incident, user, skill])
        db.flush()
        profile = VolunteerProfile(
            user_id=user.id,
            base_location_id=origin.id,
            max_travel_km=50,
            equipment=['stethoscope'],
            languages=['Nepali'],
        )
        db.add(profile)
        db.flush()
        db.add_all([
            VolunteerSkill(volunteer_id=profile.id, skill_id=skill.id, level=4, verified=True),
            AvailabilityWindow(
                volunteer_id=profile.id,
                starts_at=starts_at - timedelta(minutes=30),
                ends_at=ends_at + timedelta(minutes=30),
            ),
        ])
        need = Need(
            incident_id=incident.id,
            location_id=destination.id,
            category='medical',
            description='Medical support',
            required_skills=['nurse'],
            required_equipment=['stethoscope'],
            preferred_languages=['Nepali'],
            quantity_requested=1,
            unit='team',
            urgency=4,
        )
        db.add(need)
        db.flush()

        candidates = build_match_candidates(db, need, starts_at, ends_at)
        assert len(candidates) == 1
        assert candidates[0]['volunteer_id'] == profile.id
        assert candidates[0]['route']['source'] == 'estimate'
        assert candidates[0]['score_breakdown']['equipment_match'] == 10
        assert candidates[0]['score_breakdown']['language_match'] == 10
        assert candidates[0]['score_breakdown']['organization_trust'] == 8
        assert candidates[0]['score'] == sum(
            value for key, value in candidates[0]['score_breakdown'].items() if key != 'total'
        )

        db.query(VolunteerSkill).filter_by(volunteer_id=profile.id).update({'verified': False})
        db.flush()
        assert build_match_candidates(db, need, starts_at, ends_at) == []

    engine.dispose()


def test_matching_requires_coordinates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-coordinates.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        location = Location(name='Unlocated Shelter', location_type='shelter')
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([location, incident])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='rescue',
            description='Rescue request',
            quantity_requested=1,
            unit='team',
            urgency=5,
        )
        db.add(need)
        db.flush()

        with pytest.raises(ValueError, match='coordinates'):
            build_match_candidates(db, need)

    engine.dispose()
