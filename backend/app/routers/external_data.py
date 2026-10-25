from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Location, User
from ..security import get_current_user
from ..services.external_data import ExternalDataUnavailable, OpenMeteoClient


router = APIRouter(prefix='/api/external', tags=['external data'])
open_meteo = OpenMeteoClient()
MANAGER_ROLES = {'admin', 'coordinator'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def get_location_coordinates(db: Session, location_id: int) -> tuple[Location, float, float]:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail='Location not found')
    if location.latitude is None or location.longitude is None:
        raise HTTPException(status_code=422, detail='Location needs coordinates for weather data')
    return location, location.latitude, location.longitude


def add_location_metadata(result: dict, location: Location) -> dict:
    return {
        **result,
        'location': {
            'id': location.id,
            'name': location.name,
        },
    }


@router.get('/locations/{location_id}/rainfall')
async def rainfall_forecast(
    location_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    location, latitude, longitude = get_location_coordinates(db, location_id)
    try:
        result = await open_meteo.fetch_rainfall(latitude, longitude)
    except ExternalDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return add_location_metadata(result, location)


@router.get('/locations/{location_id}/river-discharge')
async def river_discharge_forecast(
    location_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    location, latitude, longitude = get_location_coordinates(db, location_id)
    try:
        result = await open_meteo.fetch_river_discharge(latitude, longitude)
    except ExternalDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return add_location_metadata(result, location)