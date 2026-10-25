import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..ledger import append_audit_log
from ..models import (
    BaselineFeature,
    BaselineSettlement,
    DamageAssessment,
    DeliveryConfirmation,
    HistoricalIncident,
    HazardZone,
    Location,
    Need,
    ResourceMovement,
    User,
)
from ..schemas import DamageAssessmentCreate
from ..security import get_current_user

router = APIRouter(tags=['disaster intelligence'])
MANAGER_ROLES = {'admin', 'coordinator'}
LOCATION_TYPES = {'settlement', 'ward', 'shelter', 'health_post'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def as_float(value, default=None):
    if value in (None, ''):
        return default
    return float(value)


def as_int(value, default=None):
    if value in (None, ''):
        return default
    return int(value)


def parse_baseline_payload(filename: str, content: bytes) -> tuple[list[dict], list[dict]]:
    text = content.decode('utf-8-sig')
    if filename.lower().endswith(('.json', '.geojson')) or text.lstrip().startswith('{'):
        payload = json.loads(text)
        if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
            raise ValueError('GeoJSON import must be a FeatureCollection')
        settlements = []
        features = []
        for feature in payload['features']:
            properties = feature.get('properties') or {}
            geometry = feature.get('geometry')
            location_type = properties.get('location_type')
            if location_type in LOCATION_TYPES:
                point = geometry if geometry and geometry.get('type') == 'Point' else None
                coordinates = point.get('coordinates', []) if point else []
                settlements.append({
                    **properties,
                    'latitude': coordinates[1] if len(coordinates) == 2 else properties.get('latitude'),
                    'longitude': coordinates[0] if len(coordinates) == 2 else properties.get('longitude'),
                    'boundary': geometry if geometry and geometry.get('type') != 'Point' else properties.get('boundary'),
                })
            elif geometry is not None:
                features.append({**properties, 'geometry': geometry})
        return settlements, features

    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return [], []
    return rows, []


def upsert_baseline_location(db: Session, row: dict, actor_id: int) -> tuple[Location, bool]:
    name = str(row.get('name') or '').strip()
    location_type = str(row.get('location_type') or '').strip()
    if not name or location_type not in LOCATION_TYPES:
        raise ValueError('Each settlement row needs a name and a supported location_type')
    parent_id = as_int(row.get('parent_location_id'))
    if parent_id is not None and db.get(Location, parent_id) is None:
        raise ValueError(f'Parent location {parent_id} does not exist')

    location = db.scalar(
        select(Location).where(
            Location.name == name,
            Location.location_type == location_type,
            Location.parent_location_id == parent_id,
        )
    )
    created = location is None
    before_location = None
    if created:
        location = Location(name=name, location_type=location_type, parent_location_id=parent_id)
        db.add(location)
        db.flush()
    else:
        before_location = {
            'latitude': location.latitude,
            'longitude': location.longitude,
            'boundary': location.boundary,
            'parent_location_id': location.parent_location_id,
        }

    latitude = as_float(row.get('latitude'))
    longitude = as_float(row.get('longitude'))
    if (latitude is None) != (longitude is None):
        raise ValueError(f'Location {name} must provide both latitude and longitude, or neither')
    if latitude is not None:
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError(f'Location {name} has coordinates outside valid ranges')
        location.latitude = latitude
        location.longitude = longitude
    if row.get('boundary') is not None:
        location.boundary = row['boundary']

    after_location = {
        'name': location.name,
        'location_type': location.location_type,
        'latitude': location.latitude,
        'longitude': location.longitude,
        'boundary': location.boundary,
        'parent_location_id': location.parent_location_id,
    }
    if created or before_location != {
        'latitude': location.latitude,
        'longitude': location.longitude,
        'boundary': location.boundary,
        'parent_location_id': location.parent_location_id,
    }:
        append_audit_log(
            db,
            actor_id=actor_id,
            action='location_imported' if created else 'location_updated_from_import',
            entity='location',
            entity_id=location.id,
            before=before_location,
            after=after_location,
        )

    household_value = row.get('estimated_households')
    population_value = row.get('estimated_population')
    if household_value in (None, ''):
        if population_value not in (None, ''):
            raise ValueError(f'Location {name} needs estimated_households for a baseline row')
        return location, created

    estimated_households = int(household_value)
    estimated_population = as_int(population_value)
    if estimated_households < 0 or (estimated_population is not None and estimated_population < 0):
        raise ValueError(f'Location {name} has a negative baseline estimate')
    confidence = as_float(row.get('confidence'), 0.5)
    if confidence < 0 or confidence > 1:
        raise ValueError(f'Location {name} confidence must be between 0 and 1')
    source = str(row.get('source') or 'manual')[:40]
    data_date = parse_datetime(row.get('data_date'))
    baseline = db.scalar(
        select(BaselineSettlement).where(BaselineSettlement.location_id == location.id)
    )
    before = None
    if baseline is None:
        baseline = BaselineSettlement(location_id=location.id, estimated_households=estimated_households, source=source)
        db.add(baseline)
    else:
        before = {
            'estimated_households': baseline.estimated_households,
            'estimated_population': baseline.estimated_population,
            'source': baseline.source,
            'confidence': baseline.confidence,
        }
    baseline.estimated_households = estimated_households
    baseline.estimated_population = estimated_population
    baseline.source = source
    baseline.confidence = confidence
    baseline.data_date = data_date
    location.baseline_households_estimate = estimated_households
    db.flush()
    append_audit_log(
        db,
        actor_id=actor_id,
        action='baseline_imported' if before is None else 'baseline_updated',
        entity='baseline_settlement',
        entity_id=baseline.id,
        before=before,
        after={
            'location_id': location.id,
            'estimated_households': estimated_households,
            'estimated_population': estimated_population,
            'source': source,
            'confidence': confidence,
            'verification_status': 'estimated',
        },
    )
    return location, created


@router.post('/api/admin/import/baseline')
async def import_baseline(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    try:
        settlements, features = parse_baseline_payload(file.filename or '', await file.read())
        locations_created = 0
        baselines_written = 0
        for row in settlements:
            location, created = upsert_baseline_location(db, row, user.id)
            locations_created += int(created)
            baselines_written += int(row.get('estimated_households') not in (None, ''))
        for feature in features:
            source = str(feature.get('source') or file.filename or 'import')[:80]
            if feature.get('hazard_type'):
                location_id = as_int(feature.get('location_id'))
                if location_id is not None and db.get(Location, location_id) is None:
                    raise ValueError(f"Location {location_id} does not exist for hazard zone")
                zone = HazardZone(
                    name=str(feature.get('name') or feature.get('hazard_type'))[:160],
                    location_id=location_id,
                    geometry=feature['geometry'],
                    hazard_type=str(feature['hazard_type']),
                    risk_level=as_int(feature.get('risk_level'), 3),
                    source=source,
                )
                db.add(zone)
                db.flush()
                append_audit_log(
                    db,
                    actor_id=user.id,
                    action='hazard_zone_imported',
                    entity='hazard_zone',
                    entity_id=zone.id,
                    after={
                        'name': zone.name,
                        'location_id': zone.location_id,
                        'hazard_type': zone.hazard_type,
                        'risk_level': zone.risk_level,
                        'source': zone.source,
                    },
                )
            else:
                feature_type = str(feature.get('feature_type') or feature.get('type') or 'unknown')[:60]
                baseline_feature = BaselineFeature(
                    feature_type=feature_type,
                    name=feature.get('name'),
                    geometry=feature['geometry'],
                    source=source,
                )
                db.add(baseline_feature)
                db.flush()
                append_audit_log(
                    db,
                    actor_id=user.id,
                    action='baseline_feature_imported',
                    entity='baseline_feature',
                    entity_id=baseline_feature.id,
                    after={'feature_type': feature_type, 'name': baseline_feature.name, 'source': source},
                )
        db.commit()
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error, TypeError, ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f'Invalid baseline import: {exc}') from exc
    return {
        'locations_created': locations_created,
        'baselines_written': baselines_written,
        'features_imported': len(features),
    }


@router.post('/api/admin/import/historical')
async def import_historical(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    try:
        text = (await file.read()).decode('utf-8-sig')
        if (file.filename or '').lower().endswith(('.json', '.geojson')) or text.lstrip().startswith('{'):
            payload = json.loads(text)
            if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
                raise ValueError('GeoJSON import must be a FeatureCollection')
            rows = [feature.get('properties') or {} for feature in payload['features']]
        else:
            rows = list(csv.DictReader(io.StringIO(text)))
        created = 0
        for row in rows:
            incident_type = str(row.get('incident_type') or '').strip()
            occurred_at = parse_datetime(row.get('occurred_at'))
            if not incident_type or occurred_at is None:
                raise ValueError('Each historical row needs incident_type and occurred_at')
            location_id = as_int(row.get('location_id'))
            if location_id is not None and db.get(Location, location_id) is None:
                raise ValueError(f'Location {location_id} does not exist')
            historical = HistoricalIncident(
                    incident_type=incident_type[:40],
                    occurred_at=occurred_at,
                    location_id=location_id,
                    affected_area=row.get('affected_area'),
                    damage_summary=row.get('damage_summary'),
                    source=str(row.get('source') or file.filename or 'import')[:80],
                )
            db.add(historical)
            db.flush()
            append_audit_log(
                db,
                actor_id=user.id,
                action='historical_incident_imported',
                entity='historical_incident',
                entity_id=historical.id,
                after={
                    'incident_type': historical.incident_type,
                    'occurred_at': historical.occurred_at.isoformat(),
                    'location_id': historical.location_id,
                    'source': historical.source,
                },
            )
            created += 1
        db.commit()
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error, ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f'Invalid historical import: {exc}') from exc
    return {'historical_incidents_imported': created}


@router.post('/locations/{location_id}/damage-assessments', status_code=201)
def create_damage_assessment(
    location_id: int,
    data: DamageAssessmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    if db.get(Location, location_id) is None:
        raise HTTPException(status_code=404, detail='Location not found')
    assessment = DamageAssessment(
        location_id=location_id,
        kind=data.kind,
        verified=True,
        verified_by=user.id,
        damage_level=data.damage_level,
        details=data.details,
        evidence_ref=data.evidence_ref,
    )
    db.add(assessment)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='damage_assessment_verified',
        entity='damage_assessment',
        entity_id=assessment.id,
        after={
            'location_id': location_id,
            'kind': assessment.kind,
            'damage_level': assessment.damage_level,
            'verified': True,
            'evidence_ref': assessment.evidence_ref,
        },
    )
    db.commit()
    return {
        'id': assessment.id,
        'location_id': assessment.location_id,
        'kind': assessment.kind,
        'verified': assessment.verified,
        'damage_level': assessment.damage_level,
        'details': assessment.details,
        'evidence_ref': assessment.evidence_ref,
    }


@router.get('/locations/{location_id}/profile')
def location_profile(
    location_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail='Location not found')
    baseline = db.scalar(
        select(BaselineSettlement).where(BaselineSettlement.location_id == location.id)
    )
    needs = db.scalars(
        select(Need).where(Need.location_id == location.id).order_by(Need.last_updated_at.desc())
    ).all()
    verified_damage = db.scalars(
        select(DamageAssessment)
        .where(DamageAssessment.location_id == location.id, DamageAssessment.verified.is_(True))
        .order_by(DamageAssessment.assessed_at.desc())
    ).all()
    hazards = db.scalars(select(HazardZone).where(HazardZone.location_id == location.id)).all()
    confirmed = db.scalar(
        select(func.coalesce(func.sum(DeliveryConfirmation.quantity_received), 0.0))
        .join(ResourceMovement, ResourceMovement.id == DeliveryConfirmation.movement_id)
        .join(Need, Need.id == ResourceMovement.need_id)
        .where(Need.location_id == location.id)
    ) or 0.0
    return {
        'location': {
            'id': location.id,
            'name': location.name,
            'location_type': location.location_type,
            'latitude': location.latitude,
            'longitude': location.longitude,
            'boundary': location.boundary,
        },
        'baseline_estimate': None if baseline is None else {
            'estimated_households': baseline.estimated_households,
            'estimated_population': baseline.estimated_population,
            'source': baseline.source,
            'data_date': baseline.data_date.isoformat() if baseline.data_date else None,
            'confidence': baseline.confidence,
            'verification_status': 'estimated',
        },
        'reported_needs': [
            {
                'id': need.id,
                'category': need.category,
                'description': need.description,
                'quantity_requested': need.quantity_requested,
                'quantity_fulfilled': need.quantity_fulfilled,
                'status': need.status,
                'verification_status': need.verification_status,
            }
            for need in needs
        ],
        'verified_damage': [
            {
                'id': assessment.id,
                'kind': assessment.kind,
                'damage_level': assessment.damage_level,
                'details': assessment.details,
                'assessed_at': assessment.assessed_at.isoformat(),
            }
            for assessment in verified_damage
        ],
        'hazards': [
            {
                'id': zone.id,
                'name': zone.name,
                'hazard_type': zone.hazard_type,
                'risk_level': zone.risk_level,
                'geometry': zone.geometry,
            }
            for zone in hazards
        ],
        'assistance_confirmed_quantity': confirmed,
    }
