from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Resource, Skill

DEFAULT_SKILLS = (
    ('solar_technician', 'technical'),
    ('electrician', 'technical'),
    ('doctor', 'medical'),
    ('nurse', 'medical'),
    ('civil_engineer', 'technical'),
    ('boat_rescue', 'rescue'),
    ('first_aid', 'medical'),
    ('water_purification', 'technical'),
)

DEFAULT_RESOURCES = (
    ('water', 'litre'),
    ('food', 'pack'),
    ('medicine', 'kit'),
    ('equipment', 'unit'),
)


def seed_skills(db: Session) -> int:
    inserted = 0
    for name, category in DEFAULT_SKILLS:
        exists = db.scalar(select(Skill.id).where(Skill.name == name))
        if exists is None:
            db.add(Skill(name=name, category=category))
            inserted += 1
    db.commit()
    return inserted


def seed_resources(db: Session) -> int:
    inserted = 0
    for resource_type, unit in DEFAULT_RESOURCES:
        exists = db.scalar(select(Resource.id).where(Resource.resource_type == resource_type))
        if exists is None:
            db.add(Resource(resource_type=resource_type, unit=unit))
            inserted += 1
    db.commit()
    return inserted


def main() -> None:
    with SessionLocal() as db:
        inserted = seed_skills(db)
        resources_inserted = seed_resources(db)
    print(f'Added {inserted} controlled skills and {resources_inserted} resource types.')


if __name__ == '__main__':
    main()
