from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import Location, Organization, Skill, User, VolunteerProfile, VolunteerSkill
from ..schemas import UserRegister, VolunteerProfileCreate, VolunteerSkillCreate
from ..security import get_current_user, hash_password
from .volunteers import profile_response

router = APIRouter(tags=['organizations'])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    organization_type: str | None = Field(default=None, max_length=40)


class EmployeeCreate(UserRegister, VolunteerProfileCreate):
    skills: list[VolunteerSkillCreate] = Field(default_factory=list, max_length=30)


def managed_organization(db: Session, organization_id: int, user: User) -> Organization:
    if user.role not in {'admin', 'coordinator'} and not (
        user.role == 'org_admin' and user.organization_id == organization_id
    ):
        raise HTTPException(status_code=403, detail='Organization manager required')
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail='Organization not found')
    return organization


@router.get('/organizations')
def organizations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Organization).order_by(Organization.id)
    if user.role not in {'admin', 'coordinator'}:
        query = query.where(Organization.id == user.organization_id)
    return [
        {'id': row.id, 'name': row.name, 'organization_type': row.organization_type}
        for row in db.scalars(query)
    ]


@router.post('/organizations', status_code=201)
def register_organization(
    data: OrganizationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if user.organization_id is not None:
        raise HTTPException(status_code=409, detail='Account already belongs to an organization')
    if not data.name.strip():
        raise HTTPException(status_code=422, detail='Organization name cannot be blank')
    organization = Organization(
        name=data.name.strip(), organization_type=data.organization_type, trust_score=0
    )
    db.add(organization)
    db.flush()
    previous_role = user.role
    user.organization_id = organization.id
    if user.role not in {'coordinator', 'admin'}:
        user.role = 'org_admin'
    append_audit_log(
        db, actor_id=user.id, action='organization_registered', entity='organization',
        entity_id=organization.id,
        after={'name': organization.name, 'self_registered': True, 'trust_score': 0},
    )
    append_audit_log(
        db, actor_id=user.id, action='organization_membership_changed', entity='user',
        entity_id=user.id, before={'role': previous_role, 'organization_id': None},
        after={'role': user.role, 'organization_id': organization.id},
    )
    db.commit()
    return {'id': organization.id, 'name': organization.name, 'organization_type': organization.organization_type}


@router.post('/organizations/{organization_id}/employees', status_code=201)
def register_employee(
    organization_id: int, data: EmployeeCreate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    managed_organization(db, organization_id, user)
    if data.organization_id is not None and data.organization_id != organization_id:
        raise HTTPException(status_code=422, detail='Organization must match the URL')
    if data.base_location_id is not None and db.get(Location, data.base_location_id) is None:
        raise HTTPException(status_code=404, detail='Base location not found')
    skill_ids = [skill.skill_id for skill in data.skills]
    if len(set(skill_ids)) != len(skill_ids):
        raise HTTPException(status_code=422, detail='Duplicate skills are not allowed')
    if skill_ids:
        known = set(db.scalars(select(Skill.id).where(Skill.id.in_(skill_ids))))
        if known != set(skill_ids):
            raise HTTPException(status_code=422, detail='Unknown skill')
    if db.scalar(select(User.id).where(User.email == str(data.email))):
        raise HTTPException(status_code=409, detail='An account with this email already exists')
    employee = User(
        email=str(data.email), full_name=data.full_name.strip(),
        password_hash=hash_password(data.password), role='volunteer', organization_id=organization_id,
    )
    try:
        db.add(employee)
        db.flush()
        profile = VolunteerProfile(
            user_id=employee.id, organization_id=organization_id,
            **data.model_dump(include={
                'base_location_id', 'contact_info', 'max_travel_km', 'willing_to_relocate',
                'languages', 'equipment', 'notes',
            }),
        )
        db.add(profile)
        db.flush()
        for skill in data.skills:
            db.add(VolunteerSkill(volunteer_id=profile.id, **skill.model_dump(), verified=False))
        append_audit_log(
            db, actor_id=user.id, action='employee_registered', entity='volunteer_profile',
            entity_id=profile.id,
            after={'user_id': employee.id, 'organization_id': organization_id, 'skill_ids': skill_ids},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='Employee registration conflicts with an existing record') from exc
    return profile_response(db, profile)
