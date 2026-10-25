import json

from sqlalchemy.orm import Session

from app.config import EXPOSURE_AI_TIMEOUT_SECONDS
from .client import generate_json
from .intelligence_tasks import PROMPT_DIR
from .schemas import ExposureAssessment


async def explain_exposure(db: Session, candidates: list[dict]) -> tuple[ExposureAssessment, str]:
    if not candidates:
        return ExposureAssessment(explanations=[], attention_order=[]), 'rules'

    expected_ids = {item['location_id'] for item in candidates}
    safe_candidates = [
        {
            'location_id': item['location_id'],
            'location_name': item['location_name'],
            'exposure_level': item['exposure_level'],
            'priority_rank': item['priority_rank'],
            'priority_score': item['priority_score'],
            'evidence': item['evidence'],
        }
        for item in candidates
    ]
    prompt_template = (PROMPT_DIR / 'exposure_assessor_v1.txt').read_text(encoding='utf-8')

    def validate(result: ExposureAssessment) -> None:
        explanation_ids = [item.location_id for item in result.explanations]
        if len(explanation_ids) != len(set(explanation_ids)) or set(explanation_ids) != expected_ids:
            raise ValueError('Explanations must include each candidate location exactly once')
        if len(result.attention_order) != len(set(result.attention_order)) or set(result.attention_order) != expected_ids:
            raise ValueError('Attention order must contain only supplied location IDs exactly once')

    def fallback() -> dict:
        return {
            'explanations': [
                {
                    'location_id': item['location_id'],
                    'assessment': (
                        f"{item['location_name']}: {item['exposure_level']} exposure; "
                        f"priority score {item['priority_score']:.2f} from reported and verified evidence."
                    ),
                }
                for item in candidates
            ],
            'attention_order': [item['location_id'] for item in candidates],
        }

    return await generate_json(
        db,
        task='exposure_assessment',
        prompt_version='exposure_assessor_v1',
        prompt=prompt_template.format(
            candidates=json.dumps(safe_candidates, separators=(',', ':'))
        ),
        input_summary=json.dumps(safe_candidates, separators=(',', ':')),
        schema=ExposureAssessment,
        fallback=fallback,
        validate=validate,
        timeout_seconds=EXPOSURE_AI_TIMEOUT_SECONDS,
        max_output_tokens=256,
    )