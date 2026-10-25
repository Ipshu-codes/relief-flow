from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ai.coordinator import run_coordination_cycle
from ..db import get_db
from ..models import User
from ..schemas import CoordinationRunCreate
from ..security import get_current_user


router = APIRouter(prefix='/ai', tags=['AI coordination'])
MANAGER_ROLES = {'admin', 'coordinator'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def proposal_response(proposal) -> dict:
    return {
        'id': proposal.id,
        'incident_id': proposal.incident_id,
        'batch_uuid': proposal.batch_uuid,
        'type': proposal.proposal_type,
        'payload': proposal.payload,
        'rationale': proposal.rationale,
        'confidence': proposal.confidence,
        'source': proposal.source,
        'status': proposal.status,
        'created_by': proposal.created_by,
        'created_at': proposal.created_at.isoformat(),
        'reviewed_by': proposal.reviewed_by,
        'reviewed_at': proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
        'result_entity': proposal.result_entity,
        'result_id': proposal.result_id,
    }


@router.post('/coordinate')
async def coordinate(
    incident_id: int = Query(gt=0),
    data: CoordinationRunCreate = ...,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    try:
        result = await run_coordination_cycle(
            db,
            actor_id=user.id,
            incident_id=incident_id,
            batch_uuid=str(data.client_uuid),
            starts_at=data.starts_at,
            ends_at=data.ends_at,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        'incident_id': result['incident_id'],
        'batch_uuid': result['batch_uuid'],
        'source': result['source'],
        'duplicate': result['duplicate'],
        'proposal_count': len(result['proposals']),
        'proposals': [proposal_response(proposal) for proposal in result['proposals']],
    }