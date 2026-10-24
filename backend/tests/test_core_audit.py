from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.ledger import append_audit_log, check_audit_chain
from app.models import Incident, Location, Need


def test_need_persists_coordination_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'need.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        location = Location(name='Community School', location_type='shelter')
        incident = Incident(
            incident_type='flood',
            started_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        )
        db.add_all([location, incident])
        db.flush()
        need = Need(
            incident_id=incident.id,
            location_id=location.id,
            category='medical',
            description='Elderly residents need medicine',
            required_skills=['nurse'],
            quantity_requested=12,
            unit='people',
            urgency=5,
            vulnerable_groups=['elderly'],
            source='coordinator',
        )
        db.add(need)
        db.commit()

        stored = db.scalar(select(Need).where(Need.id == need.id))
        assert stored is not None
        assert stored.required_skills == ['nurse']
        assert stored.quantity_fulfilled == 0
        assert stored.verification_status == 'unverified'

    engine.dispose()


def test_need_rejects_urgency_outside_range(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid-need.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        location = Location(name='Ward 1', location_type='ward')
        incident = Incident(
            incident_type='flood',
            started_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        )
        db.add_all([location, incident])
        db.flush()
        db.add(
            Need(
                incident_id=incident.id,
                location_id=location.id,
                category='food',
                description='Food needed',
                quantity_requested=10,
                unit='packs',
                urgency=8,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    engine.dispose()


def test_audit_chain_detects_field_tampering(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        entry = append_audit_log(
            db,
            actor_id=None,
            action='created',
            entity='need',
            entity_id=10,
            after={'status': 'open'},
        )
        db.commit()
        assert check_audit_chain(db) == (True, None)

        entry.after_json = '{"status":"closed"}'
        db.commit()
        assert check_audit_chain(db) == (False, entry.id)

    engine.dispose()
