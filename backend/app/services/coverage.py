from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Assignment, Incident, Need, Location, Skill, User, VolunteerProfile, VolunteerSkill
from .matching import ACTIVE_ASSIGNMENT_STATUSES, build_match_candidates

SAFETY_BUFFER_RESPONDERS = 1
OPEN_NEED_STATUSES = ('open', 'partially_fulfilled', 'in_progress')


def coverage_by_incident(db: Session, incident_id: int) -> list[dict]:
    if db.get(Incident, incident_id) is None:
        raise ValueError('Incident not found')

    stats = defaultdict(lambda: {'required': 0.0, 'assigned': 0, 'available': 0, 'volunteer_ids': set()})
    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(OPEN_NEED_STATUSES),
        )
    ).all()
    need_by_id = {need.id: need for need in needs}
    for need in needs:
        remaining = max(0.0, need.quantity_requested - need.quantity_fulfilled)
        for skill in set(need.required_skills or []):
            stats[(need.location_id, skill)]['required'] += remaining

    assignments = db.scalars(
        select(Assignment).where(
            Assignment.need_id.in_(need_by_id or {-1}),
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ).all()
    for assignment in assignments:
        need = need_by_id[assignment.need_id]
        for skill in set(need.required_skills or []):
            stats[(need.location_id, skill)]['assigned'] += 1

    profiles = db.scalars(
        select(VolunteerProfile).where(VolunteerProfile.availability_status == 'available')
    ).all()
    for profile in profiles:
        if profile.base_location_id is None:
            continue
        verified_names = db.scalars(
            select(Skill.name)
            .join(VolunteerSkill, VolunteerSkill.skill_id == Skill.id)
            .where(
                VolunteerSkill.volunteer_id == profile.id,
                VolunteerSkill.verified.is_(True),
            )
        ).all()
        for skill_name in set(verified_names):
            row = stats[(profile.base_location_id, skill_name)]
            row['available'] += 1
            row['volunteer_ids'].add(profile.id)

    result = []
    for (location_id, skill_name), values in sorted(stats.items()):
        location = db.get(Location, location_id)
        unmet_demand = max(0.0, values['required'] - values['assigned'])
        shortage = max(0.0, unmet_demand - values['available'])
        surplus = max(0, values['available'] - unmet_demand - SAFETY_BUFFER_RESPONDERS)
        result.append(
            {
                'location_id': location_id,
                'location_name': location.name if location else None,
                'skill': skill_name,
                'required': values['required'],
                'assigned': values['assigned'],
                'available': values['available'],
                'shortage': shortage,
                'surplus': surplus,
                'volunteer_ids': sorted(values['volunteer_ids']),
            }
        )
    return result


def reassignment_suggestions(db: Session, incident_id: int) -> list[dict]:
    coverage = coverage_by_incident(db, incident_id)
    demand = {
        (row['location_id'], row['skill']): row
        for row in coverage
        if row['shortage'] > 0
    }
    supply = [row for row in coverage if row['surplus'] > 0]
    active_needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(OPEN_NEED_STATUSES),
        )
    ).all()
    suggestions = []

    for source in supply:
        for profile_id in source['volunteer_ids']:
            profile = db.get(VolunteerProfile, profile_id)
            if profile is None or not profile.willing_to_relocate:
                continue
            for (target_location_id, skill_name), target in demand.items():
                if target_location_id == source['location_id'] or skill_name != source['skill']:
                    continue
                target_needs = [
                    need for need in active_needs
                    if need.location_id == target_location_id
                    and skill_name in (need.required_skills or [])
                ]
                for need in target_needs:
                    candidates = build_match_candidates(db, need)
                    candidate = next(
                        (item for item in candidates if item['volunteer_id'] == profile.id),
                        None,
                    )
                    if candidate is None:
                        continue
                    source_after = source['available'] - 1
                    suggestions.append(
                        {
                            'volunteer_id': profile.id,
                            'skill': skill_name,
                            'source_location_id': source['location_id'],
                            'target_location_id': target_location_id,
                            'need_id': need.id,
                            'route': candidate['route'],
                            'proposed_assignment': {
                                'need_id': need.id,
                                'volunteer_id': profile.id,
                                'proposed_by': 'coordinator',
                            },
                            'tradeoff': {
                                'source_available_before': source['available'],
                                'source_available_after': source_after,
                                'source_required': source['required'],
                                'source_safety_buffer': SAFETY_BUFFER_RESPONDERS,
                                'target_shortage_before': target['shortage'],
                            },
                            'explanation': (
                                f"Move one verified {skill_name} responder from "
                                f"{source['location_name']} to {target['location_name']}; "
                                f"the source retains {source_after} available responders and "
                                f"the target has a shortage of {target['shortage']}."
                            ),
                        }
                    )
    return sorted(
        suggestions,
        key=lambda item: (item['route']['duration_min'], item['volunteer_id'], item['need_id']),
    )
