from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assignment, Incident, Location, Need, User, VolunteerProfile


def test_assignment_starts_as_proposed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'assignment.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        user = User(email='team@example.org', full_name='Team Member', password_hash='test')
        location = Location(name='Health Post', location_type='health_post', latitude=27.7, longitude=85.3)
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        db.add_all([user, location, incident])
        db.flush()
        profile = VolunteerProfile(user_id=user.id, base_location_id=location.id)
        db.add(profile)
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='medical',
            description='Medical support',
            quantity_requested=1,
            unit='team',
            urgency=4,
        )
        db.add(need)
        db.flush()
        assignment = Assignment(need_id=need.id, volunteer_id=profile.id)
        db.add(assignment)
        db.commit()

        assert assignment.status == 'proposed'
        assert assignment.completion_criteria_met is False

    engine.dispose()
