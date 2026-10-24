import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import client as ai_client
from app.ai import sos_tasks
from app.db import Base
from app.ledger import check_audit_chain
from app.models import AICallLog, Incident, Location, Need, Skill, SOSEvent


class FakeClient:
    output = '{}'

    def __init__(self, host, timeout):
        pass

    async def generate(self, **kwargs):
        return SimpleNamespace(response=self.output)


def create_sos_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'sos-ai.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(sos_tasks, 'SessionLocal', factory)
    with factory() as db:
        incident = Incident(incident_type='flood', started_at=datetime.now(timezone.utc))
        location = Location(name='Ward 3', location_type='ward', latitude=27.7, longitude=85.3)
        db.add_all([incident, location, Skill(name='nurse', category='medical'), Skill(name='first_aid', category='medical')])
        db.flush()
        event = SOSEvent(
            client_uuid='123e4567-e89b-12d3-a456-426614174301',
            incident_id=incident.id,
            sender_ref='device-1',
            sender_verified=False,
            latitude=27.7001,
            longitude=85.3001,
            has_location=True,
            category='OTHER',
            urgency=3,
            message='Elderly need medicine and first aid for injuries',
            channel='app',
            relay_path=[],
            transmission_status='received',
            status='new',
        )
        db.add(event)
        db.commit()
        event_id = event.id
    return engine, factory, event_id


def test_sos_ai_interpretation_creates_unverified_need_from_controlled_skills(tmp_path, monkeypatch):
    engine, factory, event_id = create_sos_db(tmp_path, monkeypatch)

    class SuccessClient(FakeClient):
        async def generate(self, **kwargs):
            return SimpleNamespace(
                response=json.dumps({
                    'category': 'MEDICINE',
                    'urgency': 4,
                    'required_skills': ['nurse'],
                })
            )

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', SuccessClient)
    asyncio.run(sos_tasks.interpret_sos_event(event_id))

    with factory() as db:
        event = db.get(SOSEvent, event_id)
        need = db.scalar(select(Need).where(Need.id == event.linked_need_id))
        assert event.category == 'MEDICINE'
        assert event.urgency == 4
        assert event.parsed_json['source'] == 'ai'
        assert need is not None
        assert need.category == 'medical'
        assert need.required_skills == ['nurse']
        assert need.source == 'sos'
        assert need.verification_status == 'unverified'
        assert db.scalar(select(AICallLog).where(AICallLog.task == 'sos_interpreter'))
        assert check_audit_chain(db) == (True, None)
    engine.dispose()


def test_sos_ai_falls_back_when_ollama_is_unavailable(tmp_path, monkeypatch):
    engine, factory, event_id = create_sos_db(tmp_path, monkeypatch)

    class OfflineClient(FakeClient):
        async def generate(self, **kwargs):
            raise ConnectionError('Ollama unavailable')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', OfflineClient)
    asyncio.run(sos_tasks.interpret_sos_event(event_id))

    with factory() as db:
        event = db.get(SOSEvent, event_id)
        assert event.category == 'MEDICINE'
        assert event.urgency == 3
        assert event.parsed_json['source'] == 'fallback'
        assert event.linked_need_id is not None
        logs = db.scalars(select(AICallLog).where(AICallLog.task == 'sos_interpreter')).all()
        assert len(logs) == 3
        assert all(log.fallback_used for log in logs)
    engine.dispose()
