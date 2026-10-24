import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai import client as ai_client
from app.ai.schemas import SkillMapping
from app.db import Base
from app.models import AICallLog


def test_generate_json_validates_and_logs_ai_output(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ai-valid.db'}")
    Base.metadata.create_all(bind=engine)
    calls = []

    class FakeClient:
        def __init__(self, host, timeout):
            calls.append((host, timeout))

        async def generate(self, **kwargs):
            return SimpleNamespace(response='{"skills":["nurse"]}')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', FakeClient)
    with Session(engine) as db:
        result, source = asyncio.run(
            ai_client.generate_json(
                db,
                task='skill_mapper',
                prompt_version='skill_mapper_v1',
                prompt='map skills',
                input_summary='Need a nurse',
                schema=SkillMapping,
                fallback=lambda: {'skills': []},
            )
        )
        db.commit()
        log = db.scalar(select(AICallLog))
        assert result.skills == ['nurse']
        assert source == 'ai'
        assert log.validation_result == 'valid'
        assert log.fallback_used is False
        assert log.model
    assert calls
    engine.dispose()


def test_generate_json_retries_then_logs_rule_fallback(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ai-fallback.db'}")
    Base.metadata.create_all(bind=engine)
    attempts = 0

    class FakeClient:
        def __init__(self, host, timeout):
            pass

        async def generate(self, **kwargs):
            nonlocal attempts
            attempts += 1
            raise ConnectionError('Ollama unavailable')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', FakeClient)
    with Session(engine) as db:
        result, source = asyncio.run(
            ai_client.generate_json(
                db,
                task='skill_mapper',
                prompt_version='skill_mapper_v1',
                prompt='map skills',
                input_summary='Need first aid',
                schema=SkillMapping,
                fallback=lambda: {'skills': ['first_aid']},
            )
        )
        db.commit()
        logs = db.scalars(select(AICallLog).order_by(AICallLog.id)).all()
        assert result.skills == ['first_aid']
        assert source == 'fallback'
        assert attempts == 2
        assert len(logs) == 3
        assert all(log.fallback_used for log in logs)
        assert logs[-1].validation_result == 'fallback_valid'
    engine.dispose()
