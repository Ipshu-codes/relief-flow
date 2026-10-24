from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Incident


def test_incident_persists_core_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'incidents.db'}")
    Base.metadata.create_all(bind=engine)
    started_at = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)

    with Session(engine) as db:
        incident = Incident(
            incident_type='flood',
            started_at=started_at,
            affected_area='Kathmandu Valley',
        )
        db.add(incident)
        db.commit()

        stored = db.scalar(select(Incident).where(Incident.id == incident.id))
        assert stored is not None
        assert stored.incident_type == 'flood'
        assert stored.started_at.replace(tzinfo=timezone.utc) == started_at
        assert stored.status == 'active'
        assert stored.affected_area == 'Kathmandu Valley'
        assert stored.created_at is not None

    engine.dispose()
