import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai import client as ai_client
from app.ai.intelligence_tasks import (
    explain_bottleneck,
    judge_duplicate_reports,
    write_recovery_narrative,
)
from app.db import Base
from app.models import AICallLog, BottleneckFlag, RawReport


class FakeClient:
    response = '{}'

    def __init__(self, host, timeout):
        pass

    async def generate(self, **kwargs):
        return SimpleNamespace(response=self.response)


def test_duplicate_judge_validates_and_logs(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'duplicate-judge.db'}")
    Base.metadata.create_all(bind=engine)

    class SameEventClient(FakeClient):
        async def generate(self, **kwargs):
            return SimpleNamespace(
                response='{"same_event":true,"confidence":"high","rationale":"Same location and request."}'
            )

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', SameEventClient)
    with Session(engine) as db:
        first = RawReport(text='Need water at the school', channel='web', client_uuid='r1')
        second = RawReport(text='Need water at school', channel='sms', client_uuid='r2')
        db.add_all([first, second])
        db.flush()
        verdict, source = asyncio.run(judge_duplicate_reports(db, first, second, 0.93))
        db.commit()
        assert verdict.same_event is True
        assert source == 'ai'
        assert db.scalar(select(AICallLog)).task == 'duplicate_judge'
    engine.dispose()


def test_bottleneck_and_recovery_ai_fallbacks(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'm2-ai-fallbacks.db'}")
    Base.metadata.create_all(bind=engine)

    class OfflineClient(FakeClient):
        async def generate(self, **kwargs):
            raise ConnectionError('Ollama unavailable')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', OfflineClient)
    with Session(engine) as db:
        flag = BottleneckFlag(
            flag_type='stalled_delivery',
            severity=4,
            evidence={'movement_id': 7, 'quantity_confirmed': 0},
            explanation='Delivery is overdue and unconfirmed.',
            suggested_action='Contact the receiver.',
        )
        db.add(flag)
        db.flush()
        explanation, explanation_source = asyncio.run(explain_bottleneck(db, flag))
        narrative, narrative_source = asyncio.run(
            write_recovery_narrative(
                db,
                {
                    'confidence': 'medium',
                    'reported_needs': {'count': 2, 'remaining_quantity': 5},
                    'confirmed_assistance_quantity': 3,
                },
            )
        )
        db.commit()
        logs = db.scalars(select(AICallLog)).all()
        assert explanation_source == 'fallback'
        assert explanation.explanation == flag.explanation
        assert narrative_source == 'fallback'
        assert '2 reported needs' in narrative.narrative
        assert len(logs) == 6
        assert all(log.fallback_used for log in logs)
    engine.dispose()
