import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import SOS_AI_TIMEOUT_SECONDS
from app.db import SessionLocal
from app.ledger import append_audit_log
from app.models import Incident, Location, Need, SOSEvent, Skill
from app.services.sos_notifications import notify_sos
from app.services.sos import haversine_km
from .client import generate_json
from .schemas import SOSInterpretation
from .volunteer_tasks import PROMPT_DIR, rule_based_skill_map


CATEGORY_NEED_MAP = {
    'FOOD': 'food',
    'MEDICINE': 'medical',
    'TRAPPED': 'rescue',
    'RESCUE': 'rescue',
    'OTHER': 'other',
}
NEED_KEYWORDS = {
    'medical': ('medical', 'medicine', 'medication', 'doctor', 'nurse', 'injury', 'hospital', 'औषधि', 'चिकित्स'),
    'rescue': ('rescue', 'trapped', 'evacuat', 'boat', 'stuck', 'फसे', 'उद्धार'),
    'water': ('water', 'drink', 'पानी', 'खानेपानी'),
    'food': ('food', 'meal', 'rice', 'खाना', 'चामल'),
    'shelter': ('shelter', 'blanket', 'tent', 'आश्रय', 'कम्बल'),
    'technical_repair': ('repair', 'electric', 'power', 'technical', 'मर्मत'),
}
logger = logging.getLogger(__name__)


def _need_category(text: str, default: str) -> str:
    normalized = text.casefold()
    for category, keywords in NEED_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return default


def _area_name(event: SOSEvent, location_text: str | None) -> str:
    if location_text:
        return location_text[:160]
    address = event.address or {}
    parts = [address.get(key) for key in ('district', 'city', 'ward', 'road', 'landmark')]
    label = ', '.join(str(part) for part in parts if part)
    return label[:160] if label else f'SOS #{event.id} location'


def rule_interpret_sos(message: str, selected_category: str, allowed_skills: list[str]) -> dict:
    normalized = message.casefold()
    category = selected_category
    if category == 'OTHER':
        if any(word in normalized for word in ('medicine', 'medical', 'ausadhi', 'nurse', 'doctor')):
            category = 'MEDICINE'
        elif any(word in normalized for word in ('food', 'hungry', 'khana', 'bhok')):
            category = 'FOOD'
        elif any(word in normalized for word in ('trapped', 'stuck', 'fasyo', 'stranded')):
            category = 'TRAPPED'
        elif any(word in normalized for word in ('rescue', 'water rising', 'pani badhyo', 'bachau')):
            category = 'RESCUE'
    urgency = 5 if any(word in normalized for word in ('trapped', 'stuck', 'fasyo', 'water rising', 'pani badhyo')) else 3
    needs = [
        kind
        for kind, keywords in NEED_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    if not needs:
        needs = [CATEGORY_NEED_MAP[category]]
    return {
        'category': category,
        'urgency': urgency,
        'required_skills': rule_based_skill_map(message, allowed_skills),
        'location_text': None,
        'people_affected': None,
        'needs': needs,
        'vulnerable_groups': [],
        'missing_information': [],
    }


async def interpret_sos_event(sos_id: int, *, link_location: bool = False) -> None:
    with SessionLocal() as db:
        event = db.get(SOSEvent, sos_id)
        if event is None or (event.parsed_json is not None and not link_location):
            return
        if event.status in ('resolved', 'false_alarm'):
            return
        allowed_skills = list(db.scalars(select(Skill.name).order_by(Skill.name)))
        template = (PROMPT_DIR / 'sos_interpreter_v1.txt').read_text(encoding='utf-8')
        prompt = template.format(
            category=event.category,
            skills=', '.join(allowed_skills),
            message=event.message[:1000],
        )

        def validate(result: SOSInterpretation) -> None:
            unsupported = set(result.required_skills) - set(allowed_skills)
            if unsupported:
                raise ValueError(f'Unsupported skill names: {sorted(unsupported)}')
            if event.category != 'OTHER' and result.category != event.category:
                raise ValueError('The user-supplied category cannot be changed')

        try:
            if event.parsed_json is not None:
                result = SOSInterpretation.model_validate(event.parsed_json)
                source = event.parsed_json['source']
                validate(result)
            else:
                result, source = await generate_json(
                    db,
                    task='sos_interpreter',
                    prompt_version='sos_interpreter_v1',
                    prompt=prompt,
                    input_summary=event.message[:500],
                    schema=SOSInterpretation,
                    fallback=lambda: rule_interpret_sos(event.message, event.category, allowed_skills),
                    validate=validate,
                    timeout_seconds=SOS_AI_TIMEOUT_SECONDS,
                )
            before = {'category': event.category, 'urgency': event.urgency, 'linked_need_id': event.linked_need_id}
            if event.category == 'OTHER':
                event.category = result.category
            if not event.urgency_override:
                event.urgency = result.urgency
            event.parsed_json = {
                'category': event.category,
                'urgency': event.urgency,
                'required_skills': result.required_skills,
                'location_text': result.location_text,
                'people_affected': result.people_affected,
                'needs': result.needs,
                'vulnerable_groups': result.vulnerable_groups,
                'missing_information': result.missing_information,
                'urgency_source': 'user' if event.urgency_override else 'ai',
                'source': source,
            }
            linked_need = None
            incident = db.get(Incident, event.incident_id) if event.incident_id else None
            if incident is None:
                incident = db.scalar(
                    select(Incident)
                    .where(Incident.status.not_in(('resolved', 'cancelled')))
                    .order_by(Incident.started_at.desc())
                    .limit(1)
                )
                if incident is None:
                    incident = Incident(
                        incident_type=event.category.casefold(),
                        started_at=datetime.now(timezone.utc),
                        status='received',
                        affected_area=_area_name(event, result.location_text),
                    )
                    db.add(incident)
                    db.flush()
                event.incident_id = incident.id

            location = None
            if event.has_location:
                candidates = db.scalars(
                    select(Location).where(
                        Location.latitude.is_not(None),
                        Location.longitude.is_not(None),
                    )
                ).all()
                nearby = [
                    (haversine_km((event.latitude, event.longitude), (candidate.latitude, candidate.longitude)), candidate)
                    for candidate in candidates
                ]
                nearby = [(distance, candidate) for distance, candidate in nearby if distance <= 2.0]
                if nearby:
                    location = min(nearby, key=lambda pair: pair[0])[1]
                else:
                    location = Location(
                        name=_area_name(event, result.location_text),
                        location_type='settlement',
                        latitude=event.latitude,
                        longitude=event.longitude,
                    )
                    db.add(location)
                    db.flush()
            else:
                location = Location(
                    name=_area_name(event, result.location_text),
                    location_type='settlement',
                )
                db.add(location)
                db.flush()

            if incident is not None and location is not None:
                fallback = CATEGORY_NEED_MAP[event.category]
                need_texts = [item.strip() for item in result.needs if item.strip()]
                if not need_texts:
                    need_texts = [event.message.strip() or _area_name(event, result.location_text)]
                seen: set[tuple[str, str]] = set()
                for need_text in need_texts:
                    need_category = _need_category(need_text, fallback)
                    key = (need_category, need_text.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    need = Need(
                        incident_id=incident.id,
                        location_id=location.id,
                        category=need_category,
                        description=f'{need_text}: {event.message}'[:4000],
                        required_skills=result.required_skills,
                        quantity_requested=1,
                        unit='request',
                        urgency=result.urgency,
                        vulnerable_groups=result.vulnerable_groups,
                        confidence='medium' if source == 'ai' else 'low',
                        source='sos',
                        verification_status='unverified',
                    )
                    db.add(need)
                    db.flush()
                    if linked_need is None:
                        linked_need = need
                    append_audit_log(
                        db,
                        actor_id=None,
                        action='need_created_from_sos',
                        entity='need',
                        entity_id=need.id,
                        after={
                            'incident_id': incident.id,
                            'location_id': location.id,
                            'category': need.category,
                            'description': need.description,
                            'verification_status': need.verification_status,
                            'source': 'sos',
                        },
                    )
                event.linked_need_id = linked_need.id if linked_need else None

            append_audit_log(
                db,
                actor_id=None,
                action='sos_interpreted',
                entity='sos_event',
                entity_id=event.id,
                before=before,
                after={
                    'category': event.category,
                    'urgency': event.urgency,
                    'required_skills': result.required_skills,
                    'linked_need_id': event.linked_need_id,
                    'source': source,
                },
            )
            await notify_sos(db, event, event.parsed_json)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception('SOS %s was saved but background interpretation failed', sos_id)
