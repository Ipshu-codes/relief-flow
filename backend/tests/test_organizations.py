from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Organization


def test_organization_persists_core_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'organizations.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        organization = Organization(
            name='Nepal Relief Network',
            organization_type='ngo',
        )
        db.add(organization)
        db.commit()

        stored = db.scalar(select(Organization).where(Organization.id == organization.id))
        assert stored is not None
        assert stored.name == 'Nepal Relief Network'
        assert stored.organization_type == 'ngo'
        assert stored.created_at is not None

    engine.dispose()
