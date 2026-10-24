import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Location


def test_location_persists_hierarchy_and_estimated_baseline(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'locations.db'}")
    Base.metadata.create_all(bind=engine)

    boundary = {
        'type': 'Polygon',
        'coordinates': [[[85.3, 27.7], [85.4, 27.7], [85.4, 27.8], [85.3, 27.7]]],
    }
    with Session(engine) as db:
        ward = Location(name='Ward 1', location_type='ward')
        db.add(ward)
        db.flush()
        shelter = Location(
            name='Community School',
            location_type='shelter',
            latitude=27.7172,
            longitude=85.3240,
            boundary=boundary,
            parent_location_id=ward.id,
            baseline_households_estimate=240,
        )
        db.add(shelter)
        db.commit()

        stored = db.scalar(select(Location).where(Location.id == shelter.id))
        assert stored is not None
        assert stored.parent_location_id == ward.id
        assert stored.latitude == 27.7172
        assert stored.longitude == 85.3240
        assert stored.boundary == boundary
        assert stored.baseline_households_estimate == 240

    engine.dispose()


def test_location_rejects_invalid_coordinates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid-location.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add(Location(name='Invalid', location_type='settlement', latitude=91, longitude=85))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    engine.dispose()
