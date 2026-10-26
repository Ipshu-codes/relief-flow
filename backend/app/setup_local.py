import argparse
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values, set_key
from sqlalchemy import select


def seed_demo(db):
    from .ledger import append_audit_log
    from .models import AvailabilityWindow, BaselineSettlement, HazardZone, Incident, Location, Need, Organization, Resource, ResourceStock, Skill, User, VolunteerProfile, VolunteerSkill
    from .security import hash_password
    from .seed import seed_resources, seed_skills

    seed_skills(db)
    seed_resources(db)
    admin = db.scalar(select(User).where(User.email == 'admin@demo.rahat.org'))
    if admin is None:
        admin = User(
            email='admin@demo.rahat.org',
            full_name='Demo Administrator',
            role='admin',
            password_hash=hash_password('Rahat123!'),
        )
        db.add(admin)
    if db.scalar(select(User).where(User.email == 'coordinator@demo.rahat.org')):
        db.commit()
        return
    coordinator = User(email='coordinator@demo.rahat.org', full_name='Demo Coordinator', role='coordinator', password_hash=hash_password('RahatDemo2026!'))
    volunteer = User(email='volunteer@demo.rahat.org', full_name='Demo Solar Technician', role='volunteer', password_hash=hash_password('RahatDemo2026!'))
    organization = Organization(name='[DEMO] Relief Team', trust_score=0.8)
    db.add_all([coordinator, volunteer, organization])
    db.flush()
    coordinator.organization_id = organization.id
    volunteer.organization_id = organization.id
    clinic = Location(name='[DEMO] Health Post', location_type='health_post', latitude=27.7172, longitude=85.3240)
    village = Location(name='[DEMO] Riverside Village', location_type='settlement', latitude=27.7272, longitude=85.3340)
    depot = Location(name='[DEMO] Supply Depot', location_type='shelter', latitude=27.7072, longitude=85.3140)
    incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc), affected_area='[DEMO] Training District')
    db.add_all([clinic, village, depot, incident])
    db.flush()
    profile = VolunteerProfile(user_id=volunteer.id, organization_id=organization.id, base_location_id=depot.id, max_travel_km=50, willing_to_relocate=True, languages=['ne', 'en'], equipment=['toolkit'])
    db.add(profile)
    db.flush()
    skill = db.scalar(select(Skill).where(Skill.name == 'solar_technician'))
    db.add(VolunteerSkill(volunteer_id=profile.id, skill_id=skill.id, level=4, verified=True, verified_by=coordinator.id, verified_at=datetime.now(timezone.utc)))
    db.add(AvailabilityWindow(volunteer_id=profile.id, starts_at=datetime.now(timezone.utc) - timedelta(days=1), ends_at=datetime.now(timezone.utc) + timedelta(days=30)))
    db.add(Need(incident_id=incident.id, location_id=clinic.id, category='technical_repair', description='[DEMO] Repair the health post solar power system.', required_skills=['solar_technician'], quantity_requested=1, unit='task', urgency=4, verification_status='verified', confidence='high', last_updated_at=datetime.now(timezone.utc) - timedelta(hours=4)))
    db.add(Need(incident_id=incident.id, location_id=village.id, category='water', description='[DEMO] Drinking water requested by the village.', quantity_requested=100, unit='litre', urgency=4, verification_status='verified', confidence='high'))
    water = db.scalar(select(Resource).where(Resource.resource_type == 'water'))
    db.add(ResourceStock(organization_id=organization.id, resource_id=water.id, location_id=depot.id, quantity_available=1000, quantity_reserved=0))
    db.add(BaselineSettlement(location_id=village.id, estimated_households=40, estimated_population=160, source='synthetic_demo', confidence=0.5))
    db.add(HazardZone(name='[DEMO] Flood exposure', location_id=village.id, geometry={'type': 'Point', 'coordinates': [village.longitude, village.latitude]}, hazard_type='flood', risk_level=4, source='synthetic_demo'))
    db.flush()
    append_audit_log(db, actor_id=coordinator.id, action='demo_seeded', entity='incident', entity_id=incident.id, after={'synthetic': True})
    db.commit()


def main():
    parser = argparse.ArgumentParser(description='Migrate the local database and optionally seed a synthetic demo.')
    parser.add_argument('--demo', action='store_true', help='Add synthetic data and public demo accounts. Local testing only.')
    args = parser.parse_args()
    env_path = Path(__file__).resolve().parents[1] / '.env'
    values = dotenv_values(env_path)
    if not values.get('JWT_SECRET'):
        set_key(str(env_path), 'JWT_SECRET', secrets.token_urlsafe(48))
    from alembic import command
    from alembic.config import Config
    from .db import SessionLocal

    migrations = Config()
    migrations.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    command.upgrade(migrations, 'head')
    if args.demo:
        with SessionLocal() as db:
            seed_demo(db)
        print('Synthetic demo ready. Accounts: coordinator@demo.rahat.org / volunteer@demo.rahat.org')
        print('Public demo password: RahatDemo2026! Do not expose this database publicly.')
        print('Command station admin: admin@demo.rahat.org / Rahat123!')
    else:
        from .seed import seed_resources, seed_skills

        with SessionLocal() as db:
            seed_skills(db)
            seed_resources(db)
    print('Local database initialized. Run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000')


if __name__ == '__main__':
    main()
