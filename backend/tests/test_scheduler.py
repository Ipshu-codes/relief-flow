from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Incident
from app.services import scheduler


def test_scheduler_scans_each_active_incident_independently(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'scheduled-scan.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        db.add_all([
            Incident(incident_type='flood', started_at=datetime.now(timezone.utc), status='active'),
            Incident(incident_type='landslide', started_at=datetime.now(timezone.utc), status='closed'),
        ])
        db.commit()

    calls = []

    def scan(db, incident_id, actor_id):
        calls.append((incident_id, actor_id))
        if len(calls) == 1:
            raise ValueError('one incident failed')

    monkeypatch.setattr(scheduler, 'scan_bottlenecks', scan)
    result = scheduler.scan_active_incidents(factory)

    assert result['incidents_scanned'] == 0
    assert result['failures'] == [{'incident_id': 1, 'error': 'ValueError'}]
    assert calls == [(1, None)]
    engine.dispose()
