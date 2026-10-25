import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.exposure_tasks import explain_exposure
from ..db import get_db
from ..models import (
    BaselineSettlement,
    HazardZone,
    HistoricalIncident,
    Incident,
    Location,
    Need,
    User,
)
from ..security import get_current_user
from ..services.exposure import build_location_exposure
from ..services.external_data import ExternalDataUnavailable
from .external_data import open_meteo


router = APIRouter(tags=['exposure assessment'])
MANAGER_ROLES = {'admin', 'coordinator'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


@router.get('/api/exposure')
async def incident_exposure(
    incident_id: int = Query(gt=0),
    explain: bool = False,
    include_weather: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')

    location_ids = set(db.scalars(
        select(Location.id).where(Location.location_type.in_(('ward', 'settlement')))
    ))
    location_ids.update(db.scalars(select(Need.location_id).where(Need.incident_id == incident_id)))
    location_ids.update(db.scalars(
        select(HazardZone.location_id).where(HazardZone.location_id.is_not(None))
    ))
    location_ids.update(db.scalars(
        select(BaselineSettlement.location_id)
    ))
    location_ids.update(db.scalars(
        select(HistoricalIncident.location_id).where(HistoricalIncident.location_id.is_not(None))
    ))
    locations = db.scalars(
        select(Location).where(Location.id.in_(location_ids or {-1})).order_by(Location.id)
    ).all()

    assessments = [
        build_location_exposure(db, incident_id=incident_id, location=location)
        for location in locations
    ]
    assessments.sort(key=lambda item: (-item['priority_score'], item['location_id']))
    assessments = assessments[:limit]
    locations_by_id = {location.id: location for location in locations}
    for rank, item in enumerate(assessments, start=1):
        item['priority_rank'] = rank
        item['assessment'] = None
        item['explanation_source'] = 'rules'

    if include_weather:
        await asyncio.gather(*(
            _attach_rainfall(locations_by_id[item['location_id']], item)
            for item in assessments
            if locations_by_id[item['location_id']].latitude is not None
            and locations_by_id[item['location_id']].longitude is not None
        ))

    attention_order = [item['location_id'] for item in assessments]
    explanation_source = 'rules'
    if explain and assessments:
        candidates = assessments[:5]
        explanation, explanation_source = await explain_exposure(db, candidates)
        text_by_id = {item.location_id: item.assessment for item in explanation.explanations}
        for item in candidates:
            item['assessment'] = text_by_id[item['location_id']]
            item['explanation_source'] = explanation_source
        candidate_ids = {item['location_id'] for item in candidates}
        attention_order = explanation.attention_order + [
            item['location_id'] for item in assessments
            if item['location_id'] not in candidate_ids
        ]
        for rank, location_id in enumerate(attention_order, start=1):
            next(item for item in assessments if item['location_id'] == location_id)[
                'recommended_attention_rank'
            ] = rank
        db.commit()
    else:
        for rank, item in enumerate(assessments, start=1):
            item['recommended_attention_rank'] = rank

    return {
        'incident_id': incident_id,
        'incident_type': incident.incident_type,
        'locations': assessments,
        'attention_order': attention_order,
        'attention_order_source': explanation_source,
    }


async def _attach_rainfall(location: Location, assessment: dict) -> None:
    try:
        rainfall = await open_meteo.fetch_rainfall(location.latitude, location.longitude)
    except ExternalDataUnavailable:
        rainfall = None
    if rainfall is None:
        rainfall_evidence = {
            'source': 'unavailable',
            'verification_status': 'estimated',
            'precipitation_total_mm': None,
        }
    else:
        hourly = rainfall['data'].get('hourly', {})
        values = hourly.get('precipitation', []) if isinstance(hourly, dict) else []
        precipitation_values = [value for value in values if isinstance(value, (int, float))]
        rainfall_evidence = {
            'source': rainfall['source'],
            'verification_status': rainfall['verification_status'],
            'precipitation_total_mm': round(sum(precipitation_values), 2),
        }
    assessment['evidence']['rainfall_forecast'] = rainfall_evidence