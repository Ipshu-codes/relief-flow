from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Assignment, Incident, Location, Need, Organization, Resource, ResourceMovement, ResourceStock, User, VolunteerProfile
from ..security import get_current_user
from ..ledger import append_audit_log
from .assignments import assignment_response
from .resources import movement_response

router = APIRouter(tags=['workspace'])
MANAGER_ROLES = {'admin', 'coordinator'}


class IncidentCreate(BaseModel):
    incident_type: str = Field(min_length=1, max_length=40)
    affected_area: str = Field(min_length=1, max_length=500)


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    location_type: str = Field(pattern='^(settlement|ward|shelter|health_post)$')
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode='after')
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Both coordinates are required together')
        return self


@router.post('/incidents', status_code=201)
def create_incident(
    data: IncidentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')
    incident = Incident(**data.model_dump(), started_at=datetime.now(timezone.utc))
    db.add(incident)
    db.flush()
    append_audit_log(
        db, actor_id=user.id, action='incident_created', entity='incident',
        entity_id=incident.id, after=data.model_dump(),
    )
    db.commit()
    return {'id': incident.id, 'name': incident.affected_area, 'status': incident.status}


@router.post('/locations', status_code=201)
def create_location(
    data: LocationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')
    location = Location(**data.model_dump())
    db.add(location)
    db.flush()
    append_audit_log(
        db, actor_id=user.id, action='location_created', entity='location',
        entity_id=location.id, after=data.model_dump(),
    )
    db.commit()
    return {'id': location.id, 'name': location.name}


@router.get('/workspace')
def workspace(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    organizations = select(Organization)
    if user.role not in MANAGER_ROLES:
        organizations = organizations.where(Organization.id == user.organization_id)
    return {
        'incidents': [
            {'id': row.id, 'name': row.affected_area or row.incident_type, 'status': row.status}
            for row in db.scalars(select(Incident).order_by(Incident.id.desc()).limit(100))
        ],
        'locations': [
            {'id': row.id, 'name': row.name, 'latitude': row.latitude, 'longitude': row.longitude}
            for row in db.scalars(select(Location).order_by(Location.name).limit(500))
        ],
        'organizations': [
            {'id': row.id, 'name': row.name} for row in db.scalars(organizations)
        ],
        'resources': [
            {'id': row.id, 'name': row.resource_type, 'unit': row.unit}
            for row in db.scalars(select(Resource).order_by(Resource.id))
        ],
    }


@router.get('/assignments')
def assignments(
    incident_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Assignment).join(Need, Need.id == Assignment.need_id)
    if incident_id is not None:
        query = query.where(Need.incident_id == incident_id)
    if user.role not in MANAGER_ROLES:
        query = query.join(VolunteerProfile, VolunteerProfile.id == Assignment.volunteer_id)
        if user.role == 'org_admin' and user.organization_id is not None:
            query = query.where(VolunteerProfile.organization_id == user.organization_id)
        else:
            query = query.where(VolunteerProfile.user_id == user.id)
    return [assignment_response(row) for row in db.scalars(query.order_by(Assignment.id.desc()).limit(limit))]


@router.get('/movements')
def movements(
    incident_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ResourceMovement).join(Need, Need.id == ResourceMovement.need_id)
    if incident_id is not None:
        query = query.where(Need.incident_id == incident_id)
    if user.role == 'org_admin':
        query = query.join(ResourceStock, ResourceStock.id == ResourceMovement.stock_id)
        query = query.where(ResourceStock.organization_id == user.organization_id)
    return [movement_response(row) for row in db.scalars(query.order_by(ResourceMovement.id.desc()).limit(limit))]