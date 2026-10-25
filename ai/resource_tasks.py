import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import ALLOCATION_CHOICE_AI_TIMEOUT_SECONDS
from .client import generate_json
from .schemas import AllocationChoice


PROMPT_DIR = Path(__file__).parent / 'prompts'


async def choose_allocation_stock(
    db: Session,
    options: list[dict],
) -> tuple[AllocationChoice | None, str]:
    safe_options = [
        {
            'stock_id': option['stock_id'],
            'organization_name': option['organization_name'],
            'resource_type': option['resource_type'],
            'unit': option['unit'],
            'quantity_available': option['quantity_available'],
            'proposed_quantity': option['quantity'],
            'route_duration_min': round(option['route']['duration_min'], 1),
            'route_distance_km': round(option['route']['distance_km'], 2),
        }
        for option in options[:3]
    ]
    if not safe_options:
        return None, 'rules'
    expected_stock_ids = {option['stock_id'] for option in safe_options}
    prompt = (PROMPT_DIR / 'allocation_chooser_v1.txt').read_text(encoding='utf-8').format(
        options=json.dumps(safe_options, separators=(',', ':'))
    )

    def validate(result: AllocationChoice) -> None:
        if result.stock_id not in expected_stock_ids:
            raise ValueError('The selected stock must be one of the supplied options')

    def fallback() -> dict:
        first = safe_options[0]
        return {
            'stock_id': first['stock_id'],
            'rationale': 'Selected the highest code-ranked available stock option.',
            'confidence': 'medium',
        }

    return await generate_json(
        db,
        task='allocation_chooser',
        prompt_version='allocation_chooser_v1',
        prompt=prompt,
        input_summary=json.dumps(safe_options, separators=(',', ':')),
        schema=AllocationChoice,
        fallback=fallback,
        validate=validate,
        timeout_seconds=ALLOCATION_CHOICE_AI_TIMEOUT_SECONDS,
        max_output_tokens=128,
    )