import json
from datetime import datetime, timezone

from sqlalchemy import select

from ..config import SOS_AI_TIMEOUT_SECONDS
from ..db import SessionLocal
from ..ledger import append_audit_log
from ..models import Incident, Location, Need, SOSEvent, Skill
from ..services.sos import haversine_km
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
    return {
        'category': category,
        'urgency': urgency,
        'required_skills': rule_based_skill_map(message, allowed_skills),
    }


async def interpret_sos_event(sos_id: int) -> None:
    with SessionLocal() as db:
        event = db.get(SOSEvent, sos_id)
        if event is None or event.parsed_json is not None:
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
            event.urgency = result.urgency
            event.parsed_json = {
                'category': event.category,
                'urgency': event.urgency,
                'required_skills': result.required_skills,
                'source': source,
            }
            linked_need = None
            incident = db.get(Incident, event.incident_id) if event.incident_id else None
            if incident is None:
                active_incidents = db.scalars(
                    select(Incident).where(Incident.status == 'active').order_by(Incident.started_at.desc())
                ).all()
                if len(active_incidents) == 1:
                    incident = active_incidents[0]
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

            if incident is not None and location is not None:
                need_category = CATEGORY_NEED_MAP[event.category]
                linked_need = db.scalar(
                    select(Need).where(
                        Need.incident_id == incident.id,
                        Need.location_id == location.id,
                        Need.category == need_category,
                        Need.status.in_(('open', 'partially_fulfilled', 'in_progress')),
                    ).order_by(Need.id).limit(1)
                )
                if linked_need is None:
                    linked_need = Need(
                        incident_id=incident.id,
                        location_id=location.id,
                        category=need_category,
                        description=event.message,
                        required_skills=result.required_skills,
                        quantity_requested=1,
                        unit='request',
                        urgency=result.urgency,
                        source='sos',
                        verification_status='unverified',
                    )
                    db.add(linked_need)
                    db.flush()
                    append_audit_log(
                        db,
                        actor_id=None,
                        action='need_created_from_sos',
                        entity='need',
                        entity_id=linked_need.id,
                        after={
                            'incident_id': incident.id,
                            'location_id': location.id,
                            'category': linked_need.category,
                            'verification_status': linked_need.verification_status,
                            'source': 'sos',
                        },
                    )
                event.linked_need_id = linked_need.id

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
            db.commit()
        except Exception:
            db.rollback()
            return
