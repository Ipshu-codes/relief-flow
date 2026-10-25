import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import ROAD_UPDATE_AI_TIMEOUT_SECONDS
from .client import generate_json
from .schemas import RoadUpdateParse


PROMPT_DIR = Path(__file__).parent / 'prompts'


def rule_based_road_update(text: str) -> dict:
    normalized = re.sub(r'\s+', ' ', text.casefold())
    status = None
    if any(term in normalized for term in ('night restriction', 'night-time restriction', 'night time restriction')):
        status = 'night_restricted'
    elif any(term in normalized for term in ('one-way', 'one way', 'oneway')):
        status = 'one_way'
    elif any(term in normalized for term in ('partially open', 'partially blocked', 'partial closure', 'one lane')):
        status = 'partial'
    elif any(term in normalized for term in ('blocked', 'closed', 'closure', 'banda', 'bandha')):
        status = 'blocked'

    updates = []
    missing_fields = []
    follow_up_questions = []
    if status is not None:
        updates.append({
            'road_name': None,
            'location_text': None,
            'status': status,
            'reported_at': None,
            'notes': text[:500],
        })
        missing_fields.extend(['road_name', 'location_text'])
        follow_up_questions.append('Which road and location does this update refer to?')

    return {
        'updates': updates,
        'missing_fields': missing_fields,
        'follow_up_questions': follow_up_questions,
        'confidence': 'low',
    }


async def parse_road_update(db: Session, text: str) -> tuple[RoadUpdateParse, str]:
    template = (PROMPT_DIR / 'road_update_parser_v1.txt').read_text(encoding='utf-8')
    return await generate_json(
        db,
        task='road_update_parser',
        prompt_version='road_update_parser_v1',
        prompt=template.format(text=text[:4000]),
        input_summary=text[:500],
        schema=RoadUpdateParse,
        fallback=lambda: rule_based_road_update(text),
        timeout_seconds=ROAD_UPDATE_AI_TIMEOUT_SECONDS,
        max_output_tokens=256,
    )