from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..db import SessionLocal
from ..models import Incident
from .bottlenecks import scan_bottlenecks


def scan_active_incidents(session_factory: sessionmaker = SessionLocal) -> dict:
    scanned = 0
    failures = []
    with session_factory() as db:
        incident_ids = db.scalars(
            select(Incident.id).where(Incident.status == 'active').order_by(Incident.id)
        ).all()

    for incident_id in incident_ids:
        with session_factory() as db:
            try:
                scan_bottlenecks(db, incident_id, actor_id=None)
                db.commit()
                scanned += 1
            except Exception as exc:
                db.rollback()
                failures.append({'incident_id': incident_id, 'error': type(exc).__name__})
    return {'incidents_scanned': scanned, 'failures': failures}
