from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..geo.routing import AVERAGE_SPEED_KMH, EstimateRoutingClient
from ..models import (
    Assignment,
    AvailabilityWindow,
    Location,
    Need,
    Organization,
    RoadBlockage,
    Skill,
    User,
    VolunteerProfile,
    VolunteerSkill,
)

ACTIVE_ASSIGNMENT_STATUSES = ('approved', 'accepted', 'en_route', 'on_site')


def resolve_task_window(starts_at: datetime | None, ends_at: datetime | None):
    if starts_at is None and ends_at is None:
        starts_at = datetime.now(timezone.utc)
        ends_at = starts_at + timedelta(hours=1)
    elif starts_at is None or ends_at is None or ends_at <= starts_at:
        raise ValueError('A valid start and end time are required')
    return starts_at, ends_at


def build_match_candidates(
    db: Session,
    need: Need,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    required_skills: list[str] | None = None,
) -> list[dict]:
    starts_at, ends_at = resolve_task_window(starts_at, ends_at)
    need_location = db.get(Location, need.location_id)
    if need_location is None or need_location.latitude is None or need_location.longitude is None:
        raise ValueError('Need location must have coordinates before matching')

    blockages = db.scalars(
        select(RoadBlockage).where(
            RoadBlockage.verified.is_(True),
            RoadBlockage.cleared_at.is_(None),
        )
    ).all()
    routing = EstimateRoutingClient()
    candidates = []
    for profile in db.scalars(
        select(VolunteerProfile).where(VolunteerProfile.availability_status == 'available')
    ):
        if profile.base_location_id is None:
            continue
        base_location = db.get(Location, profile.base_location_id)
        if base_location is None or base_location.latitude is None or base_location.longitude is None:
            continue
        window_id = db.scalar(
            select(AvailabilityWindow.id)
            .where(
                AvailabilityWindow.volunteer_id == profile.id,
                AvailabilityWindow.starts_at <= starts_at,
                AvailabilityWindow.ends_at >= ends_at,
            )
            .limit(1)
        )
        if window_id is None:
            continue

        verified_skills = db.execute(
            select(Skill.name, VolunteerSkill.level)
            .join(VolunteerSkill, VolunteerSkill.skill_id == Skill.id)
            .where(
                VolunteerSkill.volunteer_id == profile.id,
                VolunteerSkill.verified.is_(True),
            )
        ).all()
        verified_levels = {name: level for name, level in verified_skills}
        required_skill_names = set(
            need.required_skills if required_skills is None else required_skills
        )
        if not verified_levels or not required_skill_names.issubset(verified_levels):
            continue

        route = routing.compute_route(
            origin=(base_location.latitude, base_location.longitude),
            destination=(need_location.latitude, need_location.longitude),
            blockages=[
                {
                    'id': blockage.id,
                    'latitude': blockage.latitude,
                    'longitude': blockage.longitude,
                    'radius_km': blockage.radius_km,
                }
                for blockage in blockages
            ],
        )
        if not route['avoids_blockages'] or route['distance_km'] > profile.max_travel_km:
            continue

        required_levels = [verified_levels[name] for name in required_skill_names]
        skill_score = round((sum(required_levels) / len(required_levels) / 5) * 30) if required_levels else 0
        max_travel_duration_min = profile.max_travel_km / AVERAGE_SPEED_KMH * 60
        travel_score = round(max(0, 1 - route['duration_min'] / max_travel_duration_min) * 25)
        required_equipment = set(need.required_equipment or [])
        equipment_match = (
            len(required_equipment.intersection(profile.equipment)) / len(required_equipment)
            if required_equipment
            else 1.0
        )
        equipment_score = round(equipment_match * 10)
        preferred_languages = {language.casefold() for language in (need.preferred_languages or [])}
        volunteer_languages = {language.casefold() for language in profile.languages}
        language_match = (
            bool(preferred_languages.intersection(volunteer_languages))
            if preferred_languages
            else True
        )
        language_score = 10 if language_match else 0
        organization = db.get(Organization, profile.organization_id) if profile.organization_id else None
        organization_trust = organization.trust_score if organization else 0.5
        organization_score = round(organization_trust * 15)
        active_assignments = db.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.volunteer_id == profile.id,
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            )
        ) or 0
        commitment_score = max(0, 10 - active_assignments * 10)
        score = skill_score + travel_score + equipment_score + language_score + organization_score + commitment_score
        user = db.get(User, profile.user_id)
        candidates.append(
            {
                'volunteer_id': profile.id,
                'user_id': profile.user_id,
                'full_name': user.full_name,
                'verified_skills': sorted(required_skill_names or set(verified_levels)),
                'route': route,
                'score': score,
                'score_breakdown': {
                    'verified_skill_level': skill_score,
                    'route_duration': travel_score,
                    'equipment_match': equipment_score,
                    'language_match': language_score,
                    'organization_trust': organization_score,
                    'existing_commitments': commitment_score,
                    'total': score,
                },
            }
        )
    return sorted(
        candidates,
        key=lambda item: (-item['score'], item['route']['duration_min'], item['volunteer_id']),
    )
