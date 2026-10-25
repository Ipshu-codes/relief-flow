import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import MATCH_CHOICE_AI_TIMEOUT_SECONDS
from .client import generate_json
from .schemas import CandidateExplanations, MatchChoice, SkillMapping

PROMPT_DIR = Path(__file__).parent / 'prompts'
SKILL_KEYWORDS = {
    'solar_technician': ('solar', 'panel', 'photovoltaic'),
    'electrician': ('electric', 'wiring', 'power line'),
    'doctor': ('doctor', 'physician', 'medical officer'),
    'nurse': ('nurse', 'nursing'),
    'civil_engineer': ('civil engineer', 'structural engineer', 'bridge damage'),
    'boat_rescue': ('boat rescue', 'boat team', 'water rescue'),
    'first_aid': ('first aid', 'first-aid', 'injury', 'wound'),
    'water_purification': ('water purification', 'purify water', 'unsafe drinking water'),
}


def rule_based_skill_map(description: str, available_skills: list[str]) -> list[str]:
    normalized = description.casefold()
    return sorted(
        skill
        for skill in set(available_skills)
        if any(keyword in normalized for keyword in SKILL_KEYWORDS.get(skill, ()))
    )


async def map_need_skills(
    db: Session,
    description: str,
    available_skills: list[str],
) -> tuple[list[str], str]:
    allowed = sorted(set(available_skills))
    if not allowed:
        return [], 'fallback'
    template = (PROMPT_DIR / 'skill_mapper_v1.txt').read_text(encoding='utf-8')
    prompt = template.format(
        skills=', '.join(allowed),
        description=description[:2000],
    )

    def validate(result: SkillMapping) -> None:
        unsupported = set(result.skills) - set(allowed)
        if unsupported:
            raise ValueError(f'Unsupported skill names: {sorted(unsupported)}')

    result, source = await generate_json(
        db,
        task='skill_mapper',
        prompt_version='skill_mapper_v1',
        prompt=prompt,
        input_summary=description[:500],
        schema=SkillMapping,
        fallback=lambda: {'skills': rule_based_skill_map(description, allowed)},
        validate=validate,
    )
    return sorted(set(result.skills)), source


async def explain_match_candidates(
    db: Session,
    candidates: list[dict],
) -> tuple[dict[int, str], str]:
    if not candidates:
        return {}, 'rules'
    expected_ids = {candidate['volunteer_id'] for candidate in candidates}
    safe_candidates = [
        {
            'volunteer_id': item['volunteer_id'],
            'verified_skills': item['verified_skills'],
            'route_duration_min': round(item['route']['duration_min'], 1),
            'route_distance_km': round(item['route']['distance_km'], 2),
            'score_breakdown': item['score_breakdown'],
        }
        for item in candidates[:5]
    ]
    template = (PROMPT_DIR / 'match_explainer_v1.txt').read_text(encoding='utf-8')
    prompt = template.format(candidates=json.dumps(safe_candidates, separators=(',', ':')))

    def validate(result: CandidateExplanations) -> None:
        ids = [item.volunteer_id for item in result.explanations]
        if len(ids) != len(set(ids)) or set(ids) != expected_ids:
            raise ValueError('Explanations must match the supplied volunteer IDs exactly')

    def fallback() -> dict:
        return {
            'explanations': [
                {
                    'volunteer_id': item['volunteer_id'],
                    'reason': (
                        f"Score {item['score']}/100 from verified skills and availability; "
                        f"estimated route is {item['route']['distance_km']:.1f} km "
                        f"({item['route']['duration_min']:.0f} minutes)."
                    ),
                }
                for item in candidates
            ]
        }

    result, source = await generate_json(
        db,
        task='match_explainer',
        prompt_version='match_explainer_v1',
        prompt=prompt,
        input_summary=json.dumps(safe_candidates, separators=(',', ':')),
        schema=CandidateExplanations,
        fallback=fallback,
        validate=validate,
    )
    return {item.volunteer_id: item.reason for item in result.explanations}, source


async def choose_match_candidate(
    db: Session,
    candidates: list[dict],
) -> tuple[MatchChoice | None, str]:
    safe_candidates = [
        {
            'volunteer_id': item['volunteer_id'],
            'verified_skills': item['verified_skills'],
            'score': item['score'],
            'score_breakdown': item['score_breakdown'],
            'route_duration_min': round(item['route']['duration_min'], 1),
            'route_distance_km': round(item['route']['distance_km'], 2),
        }
        for item in candidates[:3]
    ]
    if not safe_candidates:
        return None, 'rules'
    expected_ids = {item['volunteer_id'] for item in safe_candidates}
    prompt = (PROMPT_DIR / 'match_chooser_v1.txt').read_text(encoding='utf-8').format(
        candidates=json.dumps(safe_candidates, separators=(',', ':'))
    )

    def validate(result: MatchChoice) -> None:
        if result.volunteer_id not in expected_ids:
            raise ValueError('The selected volunteer must be one of the supplied candidates')

    def fallback() -> dict:
        first = safe_candidates[0]
        return {
            'volunteer_id': first['volunteer_id'],
            'rationale': 'Selected the highest code-ranked feasible candidate.',
            'confidence': 'medium',
        }

    return await generate_json(
        db,
        task='match_chooser',
        prompt_version='match_chooser_v1',
        prompt=prompt,
        input_summary=json.dumps(safe_candidates, separators=(',', ':')),
        schema=MatchChoice,
        fallback=fallback,
        validate=validate,
        timeout_seconds=MATCH_CHOICE_AI_TIMEOUT_SECONDS,
        max_output_tokens=128,
    )
