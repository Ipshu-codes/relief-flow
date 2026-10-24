from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import get_current_user
from ..services.coverage import coverage_by_incident, reassignment_suggestions

router = APIRouter(tags=['coverage'])


def require_coordinator(user: User) -> None:
    if user.role not in {'coordinator', 'admin'}:
        raise HTTPException(status_code=403, detail='Coordinator role required')


@router.get('/coverage')
def get_coverage(
    incident_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    try:
        return {'incident_id': incident_id, 'locations': coverage_by_incident(db, incident_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/reassignment-suggestions')
def get_reassignment_suggestions(
    incident_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_coordinator(user)
    try:
        return {
            'incident_id': incident_id,
            'suggestions': reassignment_suggestions(db, incident_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
