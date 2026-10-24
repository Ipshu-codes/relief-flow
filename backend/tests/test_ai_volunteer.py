import asyncio
import json
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai import client as ai_client
from app.ai.volunteer_tasks import explain_match_candidates, map_need_skills
from app.db import Base
from app.models import AICallLog


class FakeOllamaClient:
    response = '{}'

    def __init__(self, host, timeout):
        pass

    async def generate(self, **kwargs):
        return SimpleNamespace(response=self.response)


def test_skill_mapper_uses_only_controlled_names(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'skill-map-ai.db'}")
    Base.metadata.create_all(bind=engine)

    class SuccessfulClient(FakeOllamaClient):
        async def generate(self, **kwargs):
            return SimpleNamespace(response='{"skills":["nurse"]}')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', SuccessfulClient)
    with Session(engine) as db:
        skills, source = asyncio.run(
            map_need_skills(db, 'Health post needs a nurse', ['nurse', 'first_aid'])
        )
        db.commit()
        assert skills == ['nurse']
        assert source == 'ai'
        assert db.scalar(select(AICallLog)).task == 'skill_mapper'
    engine.dispose()


def test_unsupported_skill_retries_then_uses_rule_fallback(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'skill-map-fallback.db'}")
    Base.metadata.create_all(bind=engine)

    class UnsupportedClient(FakeOllamaClient):
        async def generate(self, **kwargs):
            return SimpleNamespace(response='{"skills":["invented_skill"]}')

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', UnsupportedClient)
    with Session(engine) as db:
        skills, source = asyncio.run(
            map_need_skills(db, 'People need first aid for injuries', ['nurse', 'first_aid'])
        )
        db.commit()
        logs = db.scalars(select(AICallLog).order_by(AICallLog.id)).all()
        assert skills == ['first_aid']
        assert source == 'fallback'
        assert len(logs) == 3
        assert all(log.fallback_used for log in logs)
    engine.dispose()


def test_invalid_explanation_ids_use_fallback_without_selecting_candidates(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'explanation-fallback.db'}")
    Base.metadata.create_all(bind=engine)

    class WrongIdClient(FakeOllamaClient):
        async def generate(self, **kwargs):
            return SimpleNamespace(
                response=json.dumps({'explanations': [{'volunteer_id': 999, 'reason': 'Wrong ID'}]})
            )

    monkeypatch.setattr(ai_client.ollama, 'AsyncClient', WrongIdClient)
    candidates = [
        {
            'volunteer_id': 4,
            'verified_skills': ['nurse'],
            'score': 90,
            'score_breakdown': {'total': 90},
            'route': {'distance_km': 3.0, 'duration_min': 8.0},
        }
    ]
    with Session(engine) as db:
        explanations, source = asyncio.run(explain_match_candidates(db, candidates))
        db.commit()
        assert source == 'fallback'
        assert list(explanations) == [4]
        assert 'Score 90/100' in explanations[4]
    engine.dispose()
