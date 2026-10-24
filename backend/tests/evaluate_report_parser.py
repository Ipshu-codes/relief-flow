import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
import sys

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.report_tasks import parse_report, rule_based_report
from app.ai.schemas import ParsedReport
from app.config import OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL
from app.db import SessionLocal
from app.models import Location


CASE_FILE = Path(__file__).parent / 'ai_eval' / 'report_cases.json'


async def require_model() -> None:
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        response = await client.get(f'{OLLAMA_URL}/api/tags')
        response.raise_for_status()
    available = response.json().get('models', [])
    if not any(item.get('name') == OLLAMA_MODEL for item in available if isinstance(item, dict)):
        raise RuntimeError(f'Ollama model {OLLAMA_MODEL!r} is not loaded; evaluation did not run')


async def evaluate(*, fallback_only: bool) -> dict:
    if not fallback_only:
        await require_model()
    cases = json.loads(CASE_FILE.read_text(encoding='utf-8'))
    exact_categories = 0
    exact_families = 0
    exact_both = 0
    source_counts = {'ai': 0, 'fallback': 0}

    database_context = nullcontext(None) if fallback_only else SessionLocal()
    with database_context as db:
        locations = [] if db is None else list(db.scalars(select(Location.name).order_by(Location.name)))
        for case in cases:
            if fallback_only:
                parsed = ParsedReport.model_validate(
                    rule_based_report(case['text'], [], locations)
                )
                source = 'fallback'
            else:
                parsed, source = await parse_report(db, case['text'], locations)
            actual_categories = {item.category for item in parsed.needs}
            categories_match = actual_categories == set(case['expected_categories'])
            families_match = parsed.families_affected == case['families_affected']
            exact_categories += categories_match
            exact_families += families_match
            exact_both += categories_match and families_match
            source_counts[source] = source_counts.get(source, 0) + 1
        if db is not None:
            db.commit()

    total = len(cases)
    scores = {
        'case_count': total,
        'exact_category_set': exact_categories / total if total else 0,
        'exact_family_count': exact_families / total if total else 0,
        'exact_categories_and_families': exact_both / total if total else 0,
        'source_counts': source_counts,
    }
    print(json.dumps(scores, indent=2, sort_keys=True))
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description='Evaluate report parser against the checked-in 25-case set.')
    parser.add_argument(
        '--fallback-only',
        action='store_true',
        help='Evaluate deterministic rules without contacting Ollama; not a model accuracy score.',
    )
    args = parser.parse_args()
    try:
        asyncio.run(evaluate(fallback_only=args.fallback_only))
    except (httpx.HTTPError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()