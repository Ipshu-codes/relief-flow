from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AvailabilityWindow, Skill, User, VolunteerProfile, VolunteerSkill


def test_volunteer_skill_verification_and_availability_persist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'volunteers.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        user = User(
            email='responder@example.org',
            full_name='Responder',
            password_hash='not-used-in-this-model-test',
        )
        skill = Skill(name='first_aid', category='medical')
        db.add_all([user, skill])
        db.flush()
        volunteer = VolunteerProfile(
            user_id=user.id,
            max_travel_km=35,
            languages=['Nepali', 'English'],
            equipment=['first_aid_kit'],
        )
        db.add(volunteer)
        db.flush()
        volunteer_skill = VolunteerSkill(
            volunteer_id=volunteer.id,
            skill_id=skill.id,
            level=3,
            verified=True,
            verified_by=user.id,
            verified_at=datetime.now(timezone.utc),
        )
        starts_at = datetime.now(timezone.utc)
        window = AvailabilityWindow(
            volunteer_id=volunteer.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=8),
        )
        db.add_all([volunteer_skill, window])
        db.commit()

        stored_skill = db.scalar(
            select(VolunteerSkill).where(VolunteerSkill.volunteer_id == volunteer.id)
        )
        assert stored_skill is not None
        assert stored_skill.verified is True
        assert stored_skill.level == 3
        assert db.scalar(select(AvailabilityWindow).where(AvailabilityWindow.volunteer_id == volunteer.id))

    engine.dispose()


def test_availability_window_rejects_nonpositive_duration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid-window.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        user = User(
            email='volunteer@example.org',
            full_name='Volunteer',
            password_hash='not-used-in-this-model-test',
        )
        db.add(user)
        db.flush()
        volunteer = VolunteerProfile(user_id=user.id)
        db.add(volunteer)
        db.flush()
        timestamp = datetime.now(timezone.utc)
        db.add(
            AvailabilityWindow(
                volunteer_id=volunteer.id,
                starts_at=timestamp,
                ends_at=timestamp,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    engine.dispose()
