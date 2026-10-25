import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPORT_AI_TIMEOUT_SECONDS
from app.models import Skill
from .client import generate_json
from .schemas import ParsedReport
from .volunteer_tasks import PROMPT_DIR, rule_based_skill_map


REPORT_PROMPT_VERSION = 'report_parser_v2'
FAMILY_COUNT_RE = re.compile(r'\b(\d+)\s+(?:famil(?:y|ies)|households?)\b', re.IGNORECASE)
QUANTITY_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*(liters?|litres?|bottles?|kg|kilograms?|packs?|kits?|people|persons?)\b',
    re.IGNORECASE,
)
NEED_RULES = (
    ('water', ('water', 'pani'), 'drinking water'),
    ('food', ('food', 'hungry', 'khana', 'bhok'), 'food'),
    ('medical', ('medicine', 'medical', 'ausadhi', 'nurse', 'doctor'), 'medicine'),
    ('rescue', ('trapped', 'rescue', 'stuck', 'fasyo', 'stranded'), 'rescue assistance'),
    ('shelter', ('shelter', 'tent', 'homeless'), 'shelter'),
    ('technical_repair', ('electricity', 'electric', 'solar', 'power line', 'repair'), 'technical repair'),
)


def rule_based_report(text: str, allowed_skills: list[str], location_names: list[str]) -> dict:
    normalized = text.casefold()
    families = FAMILY_COUNT_RE.search(text)
    quantities = list(QUANTITY_RE.finditer(text))
    needs = []
    for category, keywords, item in NEED_RULES:
        if any(keyword in normalized for keyword in keywords):
            needs.append({
                'category': category,
                'item': item,
                'quantity': None,
                'unit': None,
                'required_skills': rule_based_skill_map(text, allowed_skills),
            })
    if len(needs) == 1 and quantities:
        needs[0]['quantity'] = float(quantities[0].group(1))
        needs[0]['unit'] = quantities[0].group(2).lower()

    normalized_text = _normalize(text)
    mentioned_locations = [
        name for name in location_names
        if _location_name_matches(name, normalized_text)
    ]
    location_text = max(mentioned_locations, key=len) if mentioned_locations else None
    vulnerable_groups = [
        group for group, keywords in (
            ('elderly', ('elderly', 'older people')),
            ('children', ('children', 'child')),
            ('people with disabilities', ('disability', 'disabled')),
        ) if any(keyword in normalized for keyword in keywords)
    ]
    urgency = 5 if any(word in normalized for word in ('trapped', 'rescue', 'water rising', 'fasyo')) else 3
    return {
        'location_text': location_text,
        'families_affected': int(families.group(1)) if families else None,
        'needs': needs,
        'urgency': urgency,
        'vulnerable_groups': vulnerable_groups,
        'hazards': [],
        'missing_fields': ['quantity'] if needs and not quantities else [],
        'follow_up_questions': [],
        'language': 'unknown',
        'confidence': 'low',
    }


async def parse_report(db: Session, text: str, location_names: list[str]) -> tuple[ParsedReport, str]:
    allowed_skills = list(db.scalars(select(Skill.name).order_by(Skill.name)))
    prompt_template = (PROMPT_DIR / f'{REPORT_PROMPT_VERSION}.txt').read_text(encoding='utf-8')
    prompt = prompt_template.format(
        skills=', '.join(allowed_skills),
        locations=', '.join(location_names),
        report=text[:4000],
    )

    def validate(result: ParsedReport) -> None:
        unsupported = {
            skill
            for need in result.needs
            for skill in need.required_skills
            if skill not in allowed_skills
        }
        if unsupported:
            raise ValueError(f'Unsupported skill names: {sorted(unsupported)}')

    return await generate_json(
        db,
        task='report_parser',
        prompt_version=REPORT_PROMPT_VERSION,
        prompt=prompt,
        input_summary=text[:500],
        schema=ParsedReport,
        fallback=lambda: rule_based_report(text, allowed_skills, location_names),
        validate=validate,
        timeout_seconds=REPORT_AI_TIMEOUT_SECONDS,
    )


def _normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def _location_name_matches(name: str, normalized_text: str) -> bool:
    normalized_name = _normalize(name)
    if not normalized_name:
        return False
    padded_text = f' {normalized_text} '
    return (
        f' {normalized_name} ' in padded_text
        or f' {normalized_name.split()[-1]} ' in padded_text
    )