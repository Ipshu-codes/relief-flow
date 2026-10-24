from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Skill
from app.seed import DEFAULT_SKILLS, seed_skills


def test_skill_seed_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'skills.db'}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        assert seed_skills(db) == len(DEFAULT_SKILLS)
        assert seed_skills(db) == 0
        assert db.scalar(select(func.count()).select_from(Skill)) == len(DEFAULT_SKILLS)

    engine.dispose()
