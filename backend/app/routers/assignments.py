from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.volunteer_tasks import choose_match_candidate, explain_match_candidates, map_need_skills
from ..db import get_db
from ..geo.routing import EstimateRoutingClient
from ..ledger import append_audit_log
from ..models import AIProposal, Assignment, Location, Need, Route, Skill, User, VolunteerProfile
from ..schemas import AssignmentComplete, AssignmentCreate, AssignmentStatusUpdate, MatchRequest
from ..security import get_current_user
from ..services.matching import ACTIVE_ASSIGNMENT_STATUSES, build_match_candidates, resolve_task_window

router = APIRouter(tags=['assignments'])
MANAGER_ROLES = {'admin', 'coordinator'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def get_need(db: Session, need_id: int) -> Need:
    need = db.get(Need, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    return need


def get_assignment(db: Session, assignment_id: int) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    return assignment


def assignment_response(assignment: Assignment) -> dict:
    return {
        'id': assignment.id,
        'need_id': assignment.need_id,
        'volunteer_id': assignment.volunteer_id,
        'status': assignment.status,
        'proposed_by': assignment.proposed_by,
        'required_skills': assignment.required_skills_snapshot,
        'route_id': assignment.route_id,
        'eta': assignment.eta.isoformat() if assignment.eta else None,
        'starts_at': assignment.starts_at.isoformat() if assignment.starts_at else None,
        'ends_at': assignment.ends_at.isoformat() if assignment.ends_at else None,
        'approved_by': assignment.approved_by,
        'outcome_notes': assignment.outcome_notes,
        'completion_criteria_met': assignment.completion_criteria_met,
        'created_at': assignment.created_at.isoformat(),
        'updated_at': assignment.updated_at.isoformat(),
    }


def ai_proposal_response(proposal: AIProposal) -> dict:
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


def audit_status(db: Session, actor_id: int, assignment: Assignment, previous: str) -> None:
    append_audit_log(
        db,
        actor_id=actor_id,
        action='assignment_status_changed',
        entity='assignment',
        entity_id=assignment.id,
        before={'status': previous},
        after={'status': assignment.status},
    )


def sync_ai_assignment_proposal_review(
    db: Session,
    user: User,
    assignment: Assignment,
    status: str,
) -> None:
    proposal = db.scalar(
        select(AIProposal).where(
            AIProposal.result_entity == 'assignment',
            AIProposal.result_id == assignment.id,
            AIProposal.status == 'proposed',
        )
    )
    if proposal is None:
        return
    previous = proposal.status
    proposal.status = status
    proposal.reviewed_by = user.id
    proposal.reviewed_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        actor_id=user.id,
        action='ai_proposal_reviewed',
        entity='ai_proposal',
        entity_id=proposal.id,
        before={'status': previous},
        after={
            'status': proposal.status,
            'result_entity': proposal.result_entity,
            'result_id': proposal.result_id,
        },
    )


def refresh_need_status(db: Session, need_id: int) -> None:
    active_count = db.scalar(
        select(func.count(Assignment.id)).where(
            Assignment.need_id == need_id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ) or 0
    need = db.get(Need, need_id)
    if need is not None and need.status != 'fulfilled' and need.status != 'closed':
        need.status = 'in_progress' if active_count else 'open'


def refresh_volunteer_status(db: Session, volunteer_id: int) -> None:
    active_count = db.scalar(
        select(func.count(Assignment.id)).where(
            Assignment.volunteer_id == volunteer_id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ) or 0
    profile = db.get(VolunteerProfile, volunteer_id)
    if profile is not None and profile.availability_status in {'assigned', 'available'}:
        profile.availability_status = 'assigned' if active_count else 'available'


def persist_route(db: Session, data: dict, route_data: dict) -> Route:
    route = Route(
        from_point={'latitude': data['from_latitude'], 'longitude': data['from_longitude']},
        to_point={'latitude': data['to_latitude'], 'longitude': data['to_longitude']},
        geometry=route_data['geometry'],
        distance_km=route_data['distance_km'],
        duration_min=route_data['duration_min'],
        blocked_segments_considered=route_data['blocked_segments_considered'],
        avoids_blockages=route_data['avoids_blockages'],
        engine=route_data['source'],
    )
    db.add(route)
    db.flush()
    return route


async def resolve_need_skills(db: Session, need: Need) -> tuple[list[str], str]:
    if need.required_skills:
        return list(need.required_skills), 'need'
    controlled_skills = list(db.scalars(select(Skill.name).order_by(Skill.name)))
    return await map_need_skills(db, need.description, controlled_skills)


@router.post('/needs/{need_id}/match')
async def match_need(
    need_id: int,
    data: MatchRequest | None = None,
    explain: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    need = get_need(db, need_id)
    data = data or MatchRequest()
    required_skills, skills_source = await resolve_need_skills(db, need)
    if not need.required_skills:
        db.commit()
    try:
        candidates = build_match_candidates(
            db,
            need,
            data.starts_at,
            data.ends_at,
            required_skills=required_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    candidates = candidates[:5]
    explanation_source = None
    if explain:
        explanations, explanation_source = await explain_match_candidates(db, candidates)
        for candidate in candidates:
            candidate['explanation'] = explanations.get(candidate['volunteer_id'])
            candidate['explanation_source'] = explanation_source
    if not need.required_skills or explain:
        db.commit()
    return {
        'need_id': need.id,
        'required_skills': required_skills,
        'skills_source': skills_source,
        'candidates': candidates,
    }


@router.post('/needs/{need_id}/assignment-proposal', status_code=201)
async def propose_ai_assignment(
    need_id: int,
    data: MatchRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    need = get_need(db, need_id)
    if need.status in {'fulfilled', 'closed'}:
        raise HTTPException(status_code=409, detail='Need is no longer open for assignment')
    data = data or MatchRequest()
    required_skills, _ = await resolve_need_skills(db, need)
    if not need.required_skills:
        db.commit()
    try:
        starts_at, ends_at = resolve_task_window(data.starts_at, data.ends_at)
        candidates = build_match_candidates(
            db,
            need,
            starts_at,
            ends_at,
            required_skills=required_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    active_volunteer_ids = set(db.scalars(
        select(Assignment.volunteer_id).where(
            Assignment.need_id == need.id,
            Assignment.status.not_in(('completed', 'cancelled', 'rejected')),
        )
    ))
    candidates = [
        item for item in candidates
        if item['volunteer_id'] not in active_volunteer_ids
    ][:3]
    if not candidates:
        raise HTTPException(status_code=409, detail='No feasible unassigned volunteers are available')

    choice, source = await choose_match_candidate(db, candidates)
    candidate = next(
        (item for item in candidates if item['volunteer_id'] == choice.volunteer_id),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=500, detail='Match chooser returned an invalid candidate')

    profile = db.get(VolunteerProfile, candidate['volunteer_id'])
    need_location = db.get(Location, need.location_id)
    base_location = db.get(Location, profile.base_location_id)
    route = persist_route(
        db,
        {
            'from_latitude': base_location.latitude,
            'from_longitude': base_location.longitude,
            'to_latitude': need_location.latitude,
            'to_longitude': need_location.longitude,
        },
        candidate['route'],
    )
    assignment = Assignment(
        need_id=need.id,
        volunteer_id=profile.id,
        required_skills_snapshot=required_skills,
        status='proposed',
        proposed_by='ai',
        route_id=route.id,
        eta=datetime.now(timezone.utc) + timedelta(minutes=route.duration_min),
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(assignment)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='assignment_proposed_by_ai',
        entity='assignment',
        entity_id=assignment.id,
        after={
            'need_id': need.id,
            'volunteer_id': profile.id,
            'status': assignment.status,
            'proposed_by': assignment.proposed_by,
            'route_id': route.id,
            'required_skills': required_skills,
        },
    )

    batch_uuid = str(uuid4())
    proposal = AIProposal(
        incident_id=need.incident_id,
        batch_uuid=batch_uuid,
        candidate_key=f'assignment:{need.id}:{profile.id}',
        proposal_type='assignment',
        payload={
            'assignment_id': assignment.id,
            'need_id': need.id,
            'volunteer_id': profile.id,
            'required_skills': required_skills,
            'score': candidate['score'],
            'score_breakdown': candidate['score_breakdown'],
            'route_distance_km': candidate['route']['distance_km'],
            'route_duration_min': candidate['route']['duration_min'],
            'starts_at': starts_at.isoformat(),
            'ends_at': ends_at.isoformat(),
        },
        rationale=choice.rationale,
        confidence=choice.confidence,
        source=source,
        status='proposed',
        created_by=user.id,
        result_entity='assignment',
        result_id=assignment.id,
    )
    db.add(proposal)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='ai_proposal_created',
        entity='ai_proposal',
        entity_id=proposal.id,
        after={
            'proposal_type': proposal.proposal_type,
            'status': proposal.status,
            'source': proposal.source,
            'confidence': proposal.confidence,
            'assignment_id': assignment.id,
        },
    )
    db.commit()
    db.refresh(assignment)
    db.refresh(proposal)
    return {
        'proposal': ai_proposal_response(proposal),
        'assignment': assignment_response(assignment),
        'selected_candidate': {
            'volunteer_id': candidate['volunteer_id'],
            'score': candidate['score'],
            'score_breakdown': candidate['score_breakdown'],
            'route': candidate['route'],
        },
    }


@router.get('/ai/proposals')
def list_ai_proposals(
    incident_id: int | None = None,
    status: str = Query(default='proposed', pattern='^(proposed|approved|rejected)$'),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    query = select(AIProposal).where(AIProposal.status == status)
    if incident_id is not None:
        query = query.where(AIProposal.incident_id == incident_id)
    proposals = db.scalars(
        query.order_by(AIProposal.created_at.desc(), AIProposal.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        'items': [ai_proposal_response(item) for item in proposals],
        'limit': limit,
        'offset': offset,
    }


@router.post('/assignments', status_code=201)
async def propose_assignment(
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    need = get_need(db, data.need_id)
    if need.status in {'fulfilled', 'closed'}:
        raise HTTPException(status_code=409, detail='Need is no longer open for assignment')
    required_skills, _ = await resolve_need_skills(db, need)
    if not need.required_skills:
        db.commit()
    try:
        starts_at, ends_at = resolve_task_window(data.starts_at, data.ends_at)
        candidates = build_match_candidates(
            db,
            need,
            starts_at,
            ends_at,
            required_skills=required_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    candidate = next((item for item in candidates if item['volunteer_id'] == data.volunteer_id), None)
    if candidate is None:
        raise HTTPException(status_code=409, detail='Volunteer is not currently feasible for this need')
    duplicate = db.scalar(
        select(Assignment.id).where(
            Assignment.need_id == need.id,
            Assignment.volunteer_id == data.volunteer_id,
            Assignment.status.not_in(('completed', 'cancelled', 'rejected')),
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail='Assignment already exists for this volunteer and need')

    route_data = candidate['route']
    need_location = db.get(Location, need.location_id)
    profile = db.get(VolunteerProfile, data.volunteer_id)
    base_location = db.get(Location, profile.base_location_id)
    route = persist_route(
        db,
        {
            'from_latitude': base_location.latitude,
            'from_longitude': base_location.longitude,
            'to_latitude': need_location.latitude,
            'to_longitude': need_location.longitude,
        },
        route_data,
    )
    assignment = Assignment(
        need_id=need.id,
        volunteer_id=profile.id,
        required_skills_snapshot=required_skills,
        status='proposed',
        proposed_by='coordinator',
        route_id=route.id,
        eta=datetime.now(timezone.utc) + timedelta(minutes=route.duration_min),
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(assignment)
    db.flush()
    append_audit_log(
        db,
        actor_id=user.id,
        action='assignment_proposed',
        entity='assignment',
        entity_id=assignment.id,
        after={
            'need_id': need.id,
            'volunteer_id': profile.id,
            'status': assignment.status,
            'proposed_by': assignment.proposed_by,
            'route_id': route.id,
            'required_skills': assignment.required_skills_snapshot,
        },
    )
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.post('/assignments/{assignment_id}/approve')
async def approve_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    assignment = get_assignment(db, assignment_id)
    if assignment.status != 'proposed':
        raise HTTPException(status_code=409, detail='Only proposed assignments can be approved')
    need = get_need(db, assignment.need_id)
    required_skills = assignment.required_skills_snapshot or list(need.required_skills or [])
    try:
        candidates = build_match_candidates(
            db,
            need,
            assignment.starts_at,
            assignment.ends_at,
            required_skills=required_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    candidate = next((item for item in candidates if item['volunteer_id'] == assignment.volunteer_id), None)
    if candidate is None:
        raise HTTPException(status_code=409, detail='Volunteer is no longer feasible for this need')
    previous = assignment.status
    assignment.status = 'approved'
    assignment.approved_by = user.id
    route_data = candidate['route']
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    from_location = db.get(Location, profile.base_location_id)
    to_location = db.get(Location, need.location_id)
    route = persist_route(
        db,
        {
            'from_latitude': from_location.latitude,
            'from_longitude': from_location.longitude,
            'to_latitude': to_location.latitude,
            'to_longitude': to_location.longitude,
        },
        route_data,
    )
    assignment.route_id = route.id
    assignment.eta = datetime.now(timezone.utc) + timedelta(minutes=route.duration_min)
    profile.availability_status = 'assigned'
    need.status = 'in_progress'
    audit_status(db, user.id, assignment, previous)
    sync_ai_assignment_proposal_review(db, user, assignment, 'approved')
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.post('/assignments/{assignment_id}/accept')
def accept_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = get_assignment(db, assignment_id)
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    if user.id != profile.user_id:
        raise HTTPException(status_code=403, detail='Only the assigned volunteer can accept')
    if assignment.status != 'approved':
        raise HTTPException(status_code=409, detail='Only approved assignments can be accepted')
    previous = assignment.status
    assignment.status = 'accepted'
    audit_status(db, user.id, assignment, previous)
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.post('/assignments/{assignment_id}/reject')
def reject_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = get_assignment(db, assignment_id)
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    if assignment.status == 'proposed' and user.role in MANAGER_ROLES:
        pass
    elif assignment.status == 'approved' and user.id == profile.user_id:
        pass
    else:
        raise HTTPException(status_code=403, detail='Assignment cannot be rejected by this user')
    previous = assignment.status
    assignment.status = 'rejected'
    refresh_need_status(db, assignment.need_id)
    refresh_volunteer_status(db, assignment.volunteer_id)
    audit_status(db, user.id, assignment, previous)
    sync_ai_assignment_proposal_review(db, user, assignment, 'rejected')
    db.commit()
    return assignment_response(assignment)


@router.patch('/assignments/{assignment_id}/status')
def update_assignment_status(
    assignment_id: int,
    data: AssignmentStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = get_assignment(db, assignment_id)
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    if user.id != profile.user_id and user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Only the assigned volunteer or a coordinator can update status')
    allowed = {
        'approved': {'cancelled'},
        'accepted': {'en_route', 'cancelled'},
        'en_route': {'on_site', 'cancelled'},
        'on_site': {'cancelled'},
    }
    if data.status not in allowed.get(assignment.status, set()):
        raise HTTPException(status_code=409, detail='Invalid assignment status transition')
    previous = assignment.status
    assignment.status = data.status
    if data.status == 'cancelled':
        refresh_need_status(db, assignment.need_id)
        refresh_volunteer_status(db, assignment.volunteer_id)
    audit_status(db, user.id, assignment, previous)
    db.commit()
    return assignment_response(assignment)


@router.post('/assignments/{assignment_id}/complete')
def complete_assignment(
    assignment_id: int,
    data: AssignmentComplete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = get_assignment(db, assignment_id)
    profile = db.get(VolunteerProfile, assignment.volunteer_id)
    if user.id != profile.user_id and user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Only the assigned volunteer or a coordinator can complete')
    if assignment.status != 'on_site':
        raise HTTPException(status_code=409, detail='Assignment must be on site before completion')
    need = get_need(db, assignment.need_id)
    if (
        data.completion_criteria_met
        and need.category in {'water', 'food', 'shelter'}
        and need.quantity_fulfilled < need.quantity_requested
    ):
        raise HTTPException(status_code=409, detail='Supply needs require confirmed delivery before fulfillment')
    previous = assignment.status
    assignment.status = 'completed'
    assignment.outcome_notes = data.outcome_notes
    assignment.completion_criteria_met = data.completion_criteria_met
    db.flush()
    previous_need_status = need.status
    if data.completion_criteria_met:
        need.status = 'fulfilled'
    else:
        refresh_need_status(db, need.id)
    refresh_volunteer_status(db, assignment.volunteer_id)
    audit_status(db, user.id, assignment, previous)
    append_audit_log(
        db,
        actor_id=user.id,
        action='need_completion_updated',
        entity='need',
        entity_id=need.id,
        before={'status': previous_need_status},
        after={'status': need.status, 'completion_criteria_met': data.completion_criteria_met},
    )
    db.commit()
    return assignment_response(assignment)
