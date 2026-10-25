from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import (
    Assignment,
    AvailabilityWindow,
    Need,
    Organization,
    Skill,
    User,
    VolunteerProfile,
    VolunteerSkill,
)
from ..schemas import (
    AvailabilityWindowInput,
    VolunteerAvailabilityPatch,
    VolunteerProfileCreate,
    VolunteerProfilePatch,
    VolunteerProfileRead,
    VolunteerSkillCreate,
    VolunteerSkillRead,
)
from ..security import get_current_user
from ..services.matching import ACTIVE_ASSIGNMENT_STATUSES, build_match_candidates

router = APIRouter(tags=['volunteers'])
MANAGER_ROLES = {'admin', 'coordinator'}


def get_profile(db: Session, volunteer_id: int) -> VolunteerProfile:
    profile = db.get(VolunteerProfile, volunteer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail='Volunteer not found')
    return profile


def can_manage_profile(user: User, profile: VolunteerProfile) -> bool:
    return (
        user.role in MANAGER_ROLES
        or profile.user_id == user.id
        or (
            user.role == 'org_admin'
            and user.organization_id is not None
            and profile.organization_id == user.organization_id
        )
    )


def can_verify_skills(user: User, profile: VolunteerProfile) -> bool:
    return user.role in MANAGER_ROLES or (
        user.role == 'org_admin'
        and user.organization_id is not None
        and profile.organization_id == user.organization_id
    )


def profile_response(db: Session, profile: VolunteerProfile) -> dict:
    user = db.get(User, profile.user_id)
    skill_rows = db.execute(
        select(VolunteerSkill, Skill)
        .join(Skill, Skill.id == VolunteerSkill.skill_id)
        .where(VolunteerSkill.volunteer_id == profile.id)
        .order_by(Skill.name)
    ).all()
    return {
        'id': profile.id,
        'user_id': profile.user_id,
        'full_name': user.full_name,
        'organization_id': profile.organization_id,
        'base_location_id': profile.base_location_id,
        'max_travel_km': profile.max_travel_km,
        'availability_status': profile.availability_status,
        'willing_to_relocate': profile.willing_to_relocate,
        'languages': profile.languages,
        'equipment': profile.equipment,
        'notes': profile.notes,
        'contact_info': profile.contact_info,
        'skills': [
            {
                'skill_id': skill.id,
                'name': skill.name,
                'category': skill.category,
                'level': volunteer_skill.level,
                'certification_name': volunteer_skill.certification_name,
                'certificate_ref': volunteer_skill.certificate_ref,
                'verified': volunteer_skill.verified,
            }
            for volunteer_skill, skill in skill_rows
        ],
    }


def profile_snapshot(profile: VolunteerProfile) -> dict:
    return {
        'user_id': profile.user_id,
        'organization_id': profile.organization_id,
        'base_location_id': profile.base_location_id,
        'max_travel_km': profile.max_travel_km,
        'availability_status': profile.availability_status,
        'willing_to_relocate': profile.willing_to_relocate,
        'languages': profile.languages,
        'equipment': profile.equipment,
        'notes': profile.notes,
        'contact_info': profile.contact_info,
    }


@router.post('/volunteers', response_model=VolunteerProfileRead, status_code=201)
def create_volunteer(
    data: VolunteerProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.scalar(select(VolunteerProfile.id).where(VolunteerProfile.user_id == user.id)):
        raise HTTPException(status_code=409, detail='Volunteer profile already exists')
    if data.organization_id is not None:
        if user.role == 'org_admin' and data.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail='Cannot create a profile for another organization')
        if user.role not in MANAGER_ROLES | {'org_admin'}:
            raise HTTPException(status_code=403, detail='Organization assignment requires coordinator approval')
        if db.get(Organization, data.organization_id) is None:
            raise HTTPException(status_code=404, detail='Organization not found')

    profile = VolunteerProfile(
        user_id=user.id,
        contact_info=data.contact_info,
        organization_id=data.organization_id,
        base_location_id=data.base_location_id,
        max_travel_km=data.max_travel_km,
        willing_to_relocate=data.willing_to_relocate,
        languages=data.languages,
        equipment=data.equipment,
        notes=data.notes,
    )
    if data.base_location_id is not None:
        from ..models import Location

        if db.get(Location, data.base_location_id) is None:
            raise HTTPException(status_code=404, detail='Base location not found')
    db.add(profile)
    db.flush()
    before_role = user.role
    if user.role == 'community_member':
        user.role = 'volunteer'
    append_audit_log(
        db,
        actor_id=user.id,
        action='created',
        entity='volunteer_profile',
        entity_id=profile.id,
        after=profile_snapshot(profile),
    )
    if user.role != before_role:
        append_audit_log(
            db,
            actor_id=user.id,
            action='role_changed',
            entity='user',
            entity_id=user.id,
            before={'role': before_role},
            after={'role': user.role},
        )
    db.commit()
    db.refresh(profile)
    return profile_response(db, profile)


@router.get('/volunteers', response_model=list[VolunteerProfileRead])
def list_volunteers(
    skill: str | None = None,
    area: int | None = None,
    availability: str | None = Query(default=None, pattern='^(available|assigned|unavailable|off_duty)$'),
    verified_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(VolunteerProfile)
    if user.role in MANAGER_ROLES:
        pass
    elif user.role == 'org_admin' and user.organization_id is not None:
        statement = statement.where(VolunteerProfile.organization_id == user.organization_id)
    elif user.role == 'volunteer':
        statement = statement.where(VolunteerProfile.user_id == user.id)
    else:
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    if area is not None:
        statement = statement.where(VolunteerProfile.base_location_id == area)
    if availability is not None:
        statement = statement.where(VolunteerProfile.availability_status == availability)
    if skill is not None or verified_only:
        statement = statement.join(VolunteerSkill).join(Skill)
        if skill is not None:
            statement = statement.where(Skill.name == skill)
        if verified_only:
            statement = statement.where(VolunteerSkill.verified.is_(True))
    profiles = db.scalars(statement.distinct().order_by(VolunteerProfile.id).limit(limit)).all()
    return [profile_response(db, profile) for profile in profiles]


@router.patch('/volunteers/{volunteer_id}', response_model=VolunteerProfileRead)
def update_volunteer(
    volunteer_id: int,
    data: VolunteerProfilePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = get_profile(db, volunteer_id)
    if not can_manage_profile(user, profile):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    changes = data.model_dump(exclude_unset=True)
    before = profile_snapshot(profile)
    if 'organization_id' in changes:
        if user.role not in MANAGER_ROLES and not (
            user.role == 'org_admin' and changes['organization_id'] == user.organization_id
        ):
            raise HTTPException(status_code=403, detail='Cannot change organization assignment')
        if changes['organization_id'] is not None and db.get(
            __import__('app.models', fromlist=['Organization']).Organization,
            changes['organization_id'],
        ) is None:
            raise HTTPException(status_code=404, detail='Organization not found')
    for field, value in changes.items():
        setattr(profile, field, value)
    append_audit_log(
        db,
        actor_id=user.id,
        action='updated',
        entity='volunteer_profile',
        entity_id=profile.id,
        before=before,
        after=profile_snapshot(profile),
    )
    db.commit()
    db.refresh(profile)
    return profile_response(db, profile)


@router.get('/skills')
def list_skills(db: Session = Depends(get_db)):
    return [
        {'id': skill.id, 'name': skill.name, 'category': skill.category}
        for skill in db.scalars(select(Skill).order_by(Skill.category, Skill.name))
    ]


@router.post('/volunteers/{volunteer_id}/skills', response_model=VolunteerSkillRead, status_code=201)
def add_volunteer_skill(
    volunteer_id: int,
    data: VolunteerSkillCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = get_profile(db, volunteer_id)
    if not can_manage_profile(user, profile):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    skill = db.get(Skill, data.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail='Skill not found')
    if db.scalar(
        select(VolunteerSkill.id).where(
            VolunteerSkill.volunteer_id == profile.id,
            VolunteerSkill.skill_id == skill.id,
        )
    ):
        raise HTTPException(status_code=409, detail='Volunteer already has this skill')
    volunteer_skill = VolunteerSkill(
        volunteer_id=profile.id,
        skill_id=skill.id,
        level=data.level,
        certification_name=data.certification_name,
        certificate_ref=data.certificate_ref,
        verified=False,
    )
    db.add(volunteer_skill)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='skill_added',
        entity='volunteer_skill',
        entity_id=volunteer_skill.id,
        after={
            'volunteer_id': profile.id,
            'skill_id': skill.id,
            'level': volunteer_skill.level,
            'verified': False,
        },
    )
    db.commit()
    return {
        'skill_id': skill.id,
        'name': skill.name,
        'category': skill.category,
        'level': volunteer_skill.level,
        'certification_name': volunteer_skill.certification_name,
        'certificate_ref': volunteer_skill.certificate_ref,
        'verified': False,
    }


@router.post('/volunteers/{volunteer_id}/skills/{skill_id}/verify', response_model=VolunteerSkillRead)
def verify_volunteer_skill(
    volunteer_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = get_profile(db, volunteer_id)
    if not can_verify_skills(user, profile):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    volunteer_skill = db.scalar(
        select(VolunteerSkill).where(
            VolunteerSkill.volunteer_id == profile.id,
            VolunteerSkill.skill_id == skill_id,
        )
    )
    if volunteer_skill is None:
        raise HTTPException(status_code=404, detail='Volunteer skill not found')
    before = {'verified': volunteer_skill.verified, 'verified_by': volunteer_skill.verified_by}
    volunteer_skill.verified = True
    volunteer_skill.verified_by = user.id
    volunteer_skill.verified_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        actor_id=user.id,
        action='skill_verified',
        entity='volunteer_skill',
        entity_id=volunteer_skill.id,
        before=before,
        after={'verified': True, 'verified_by': user.id},
    )
    db.commit()
    skill = db.get(Skill, skill_id)
    return {
        'skill_id': skill.id,
        'name': skill.name,
        'category': skill.category,
        'level': volunteer_skill.level,
        'certification_name': volunteer_skill.certification_name,
        'certificate_ref': volunteer_skill.certificate_ref,
        'verified': volunteer_skill.verified,
    }


@router.patch('/volunteers/{volunteer_id}/availability')
def update_availability(
    volunteer_id: int,
    data: VolunteerAvailabilityPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = get_profile(db, volunteer_id)
    if not can_manage_profile(user, profile):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    before = profile_snapshot(profile)
    affected_needs = []
    if data.status == 'unavailable':
        active_assignments = db.scalars(
            select(Assignment).where(
                Assignment.volunteer_id == profile.id,
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            )
        ).all()
        if any(assignment.status in {'en_route', 'on_site'} for assignment in active_assignments):
            raise HTTPException(
                status_code=409,
                detail='En-route or on-site assignments require coordinator intervention',
            )
        for assignment in active_assignments:
            previous_assignment_status = assignment.status
            assignment.status = 'cancelled'
            append_audit_log(
                db,
                actor_id=user.id,
                action='assignment_cancelled_volunteer_unavailable',
                entity='assignment',
                entity_id=assignment.id,
                before={'status': previous_assignment_status},
                after={'status': 'cancelled'},
            )
            need = db.get(Need, assignment.need_id)
            if need is not None and need.status not in {'fulfilled', 'closed'}:
                previous_need_status = need.status
                remaining_assignments = db.scalar(
                    select(func.count(Assignment.id)).where(
                        Assignment.need_id == need.id,
                        Assignment.id != assignment.id,
                        Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                    )
                ) or 0
                need.status = 'in_progress' if remaining_assignments else 'open'
                if need.status != previous_need_status:
                    append_audit_log(
                        db,
                        actor_id=user.id,
                        action='need_reopened_volunteer_unavailable',
                        entity='need',
                        entity_id=need.id,
                        before={'status': previous_need_status},
                        after={'status': need.status},
                    )
                affected_needs.append(need)
    profile.availability_status = data.status
    if data.windows is not None:
        db.execute(delete(AvailabilityWindow).where(AvailabilityWindow.volunteer_id == profile.id))
        db.add_all(
            AvailabilityWindow(
                volunteer_id=profile.id,
                starts_at=window.starts_at,
                ends_at=window.ends_at,
            )
            for window in data.windows
        )
    append_audit_log(
        db,
        actor_id=user.id,
        action='availability_changed',
        entity='volunteer_profile',
        entity_id=profile.id,
        before=before,
        after={
            **profile_snapshot(profile),
            'windows': [
                {'starts_at': window.starts_at.isoformat(), 'ends_at': window.ends_at.isoformat()}
                for window in data.windows
            ] if data.windows is not None else None,
        },
    )
    db.commit()
    db.refresh(profile)
    affected = []
    for need in affected_needs:
        try:
            candidates = build_match_candidates(db, need)
        except ValueError:
            candidates = []
        candidate_ids = [candidate['volunteer_id'] for candidate in candidates]
        append_audit_log(
            db,
            actor_id=user.id,
            action='replacement_options_generated',
            entity='need',
            entity_id=need.id,
            after={'candidate_volunteer_ids': candidate_ids},
        )
        affected.append({'need_id': need.id, 'replacement_candidates': candidates})
    if affected:
        db.commit()
    return {**profile_response(db, profile), 'affected_needs': affected}
