import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EXPOSURE_AI_TIMEOUT_SECONDS
from app.geo.routing import EstimateRoutingClient
from app.ledger import append_audit_log
from app.models import AIProposal, Assignment, Incident, Location, Need, Route, Skill, VolunteerProfile
from app.services.allocation_matching import build_allocation_options
from app.services.matching import ACTIVE_ASSIGNMENT_STATUSES, build_match_candidates, resolve_task_window
from .client import generate_json
from .schemas import CoordinatorSelection


PROMPT_DIR = Path(__file__).parent / 'prompts'
OPEN_NEED_STATUSES = ('open', 'partially_fulfilled', 'in_progress')
MAX_ACTIONS_PER_CYCLE = 5
MAX_CANDIDATES_PER_CYCLE = 20


async def run_coordination_cycle(
    db: Session,
    *,
    actor_id: int,
    incident_id: int,
    batch_uuid: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> dict:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ValueError('Incident not found')

    existing = db.scalars(
        select(AIProposal).where(AIProposal.batch_uuid == batch_uuid).order_by(AIProposal.id)
    ).all()
    if existing:
        return {
            'incident_id': incident_id,
            'batch_uuid': batch_uuid,
            'source': existing[0].source,
            'proposals': existing,
            'duplicate': True,
        }

    starts_at, ends_at = resolve_task_window(starts_at, ends_at)
    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(OPEN_NEED_STATUSES),
        ).order_by(Need.urgency.desc(), Need.id)
    ).all()
    candidates = []
    for need in needs:
        if need.required_skills:
            try:
                matches = build_match_candidates(db, need, starts_at, ends_at)[:3]
            except ValueError:
                matches = []
            active_ids = set(db.scalars(
                select(Assignment.volunteer_id).where(
                    Assignment.need_id == need.id,
                    Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                )
            ))
            for match in matches:
                if match['volunteer_id'] in active_ids:
                    continue
                candidate_id = f'assignment:{need.id}:{match["volunteer_id"]}'
                candidates.append({
                    'candidate_id': candidate_id,
                    'action': 'assignment',
                    'score': match['score'],
                    'need': {
                        'need_id': need.id,
                        'description': need.description[:240],
                        'category': need.category,
                        'urgency': need.urgency,
                        'remaining_quantity': max(0, need.quantity_requested - need.quantity_fulfilled),
                        'unit': need.unit,
                    },
                    'volunteer': {
                        'volunteer_id': match['volunteer_id'],
                        'name': match['full_name'],
                        'verified_skills': match['verified_skills'],
                        'score': match['score'],
                        'score_breakdown': match['score_breakdown'],
                        'route_duration_min': round(match['route']['duration_min'], 1),
                        'route_distance_km': round(match['route']['distance_km'], 2),
                    },
                    '_need': need,
                    '_match': match,
                    '_required_skills': list(need.required_skills),
                    '_starts_at': starts_at,
                    '_ends_at': ends_at,
                })

        allocation_result = build_allocation_options(db, need)
        allocation_options = allocation_result['options'][:3]
        for option in allocation_options:
            candidate_id = f'allocation:{need.id}:{option["stock_id"]}'
            candidates.append({
                'candidate_id': candidate_id,
                'action': 'allocation',
                'score': option['score'],
                'need': {
                    'need_id': need.id,
                    'description': need.description[:240],
                    'category': need.category,
                    'urgency': need.urgency,
                        'remaining_quantity': allocation_result['remaining_quantity'],
                    'unit': need.unit,
                },
                'stock': {
                    'stock_id': option['stock_id'],
                    'organization_name': option['organization_name'],
                    'resource_type': option['resource_type'],
                    'quantity_available': option['quantity_available'],
                    'proposed_quantity': option['quantity'],
                    'route_duration_min': round(option['route']['duration_min'], 1),
                },
                '_need': need,
                '_option': option,
            })

    candidates.sort(key=lambda item: (-item['score'], item['candidate_id']))
    candidates = candidates[:MAX_CANDIDATES_PER_CYCLE]
    if not candidates:
        return {
            'incident_id': incident_id,
            'batch_uuid': batch_uuid,
            'source': 'rules',
            'proposals': [],
            'duplicate': False,
        }

    public_candidates = [
        {key: value for key, value in candidate.items() if not key.startswith('_')}
        for candidate in candidates
    ]
    expected_ids = {candidate['candidate_id'] for candidate in candidates}
    candidates_by_id = {candidate['candidate_id']: candidate for candidate in candidates}

    def validate(result: CoordinatorSelection) -> None:
        candidate_ids = [decision.candidate_id for decision in result.decisions]
        if len(candidate_ids) > MAX_ACTIONS_PER_CYCLE:
            raise ValueError('Coordinator may select at most five actions per cycle')
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError('Coordinator candidate IDs must be unique')
        if set(candidate_ids) - expected_ids:
            raise ValueError('Coordinator selected an action not supplied by code')
        selected_volunteers = [
            candidates_by_id[candidate_id]['_match']['volunteer_id']
            for candidate_id in candidate_ids
            if candidates_by_id[candidate_id]['action'] == 'assignment'
        ]
        if len(selected_volunteers) != len(set(selected_volunteers)):
            raise ValueError('A volunteer cannot be selected for multiple assignments in one cycle')

    def fallback() -> dict:
        first = candidates[0]
        return {
            'decisions': [{
                'candidate_id': first['candidate_id'],
                'rationale': 'Selected the highest code-ranked feasible action.',
                'confidence': 'medium',
                'rank': 1,
            }]
        }

    prompt = (PROMPT_DIR / 'coordinator_v1.txt').read_text(encoding='utf-8').format(
        candidates=json.dumps(public_candidates, separators=(',', ':'))
    )
    selection, source = await generate_json(
        db,
        task='coordinator_cycle',
        prompt_version='coordinator_v1',
        prompt=prompt,
        input_summary=json.dumps(public_candidates, separators=(',', ':')),
        schema=CoordinatorSelection,
        fallback=fallback,
        validate=validate,
        timeout_seconds=EXPOSURE_AI_TIMEOUT_SECONDS,
        max_output_tokens=512,
    )
    by_id = {candidate['candidate_id']: candidate for candidate in candidates}
    proposals = []
    for decision in selection.decisions:
        candidate = by_id[decision.candidate_id]
        proposal = _create_draft_proposal(
            db,
            actor_id=actor_id,
            batch_uuid=batch_uuid,
            candidate=candidate,
            rationale=decision.rationale,
            confidence=decision.confidence,
            source=source,
        )
        if proposal is not None:
            proposals.append(proposal)
    db.commit()
    for proposal in proposals:
        db.refresh(proposal)
    return {
        'incident_id': incident_id,
        'batch_uuid': batch_uuid,
        'source': source,
        'proposals': proposals,
        'duplicate': False,
    }


def _create_draft_proposal(
    db: Session,
    *,
    actor_id: int,
    batch_uuid: str,
    candidate: dict,
    rationale: str,
    confidence: str,
    source: str,
) -> AIProposal | None:
    candidate_id = candidate['candidate_id']
    need = candidate['_need']
    result_entity = None
    result_id = None
    if candidate['action'] == 'assignment':
        match = candidate['_match']
        current_candidates = build_match_candidates(
            db,
            need,
            candidate['_starts_at'],
            candidate['_ends_at'],
            required_skills=candidate['_required_skills'],
        )
        current_match = next(
            (item for item in current_candidates if item['volunteer_id'] == match['volunteer_id']),
            None,
        )
        if current_match is None:
            return None
        profile = db.get(VolunteerProfile, current_match['volunteer_id'])
        need_location = db.get(Location, need.location_id)
        base_location = db.get(Location, profile.base_location_id)
        route = Route(
            from_point={'latitude': base_location.latitude, 'longitude': base_location.longitude},
            to_point={'latitude': need_location.latitude, 'longitude': need_location.longitude},
            geometry=current_match['route']['geometry'],
            distance_km=current_match['route']['distance_km'],
            duration_min=current_match['route']['duration_min'],
            blocked_segments_considered=current_match['route']['blocked_segments_considered'],
            avoids_blockages=current_match['route']['avoids_blockages'],
            engine=current_match['route']['source'],
        )
        db.add(route)
        db.flush()
        assignment = Assignment(
            need_id=need.id,
            volunteer_id=profile.id,
            required_skills_snapshot=candidate['_required_skills'],
            status='proposed',
            proposed_by='ai',
            route_id=route.id,
            eta=datetime.now(timezone.utc) + timedelta(minutes=route.duration_min),
            starts_at=candidate['_starts_at'],
            ends_at=candidate['_ends_at'],
        )
        db.add(assignment)
        db.flush()
        result_entity = 'assignment'
        result_id = assignment.id
        payload = {
            'assignment_id': assignment.id,
            'need_id': need.id,
            'volunteer_id': profile.id,
            'required_skills': candidate['_required_skills'],
            'score': current_match['score'],
            'score_breakdown': current_match['score_breakdown'],
            'route_distance_km': current_match['route']['distance_km'],
            'route_duration_min': current_match['route']['duration_min'],
            'starts_at': candidate['_starts_at'].isoformat(),
            'ends_at': candidate['_ends_at'].isoformat(),
        }
        append_audit_log(
            db,
            actor_id=actor_id,
            action='assignment_proposed_by_coordinator_cycle',
            entity='assignment',
            entity_id=assignment.id,
            after={
                'need_id': need.id,
                'volunteer_id': profile.id,
                'status': assignment.status,
                'route_id': route.id,
            },
        )
        proposal_type = 'assignment'
    else:
        option = candidate['_option']
        current_options = build_allocation_options(db, need)['options']
        current_option = next(
            (item for item in current_options if item['stock_id'] == option['stock_id']),
            None,
        )
        if current_option is None:
            return None
        payload = {
            'need_id': need.id,
            'stock_id': current_option['stock_id'],
            'resource_id': current_option['resource_id'],
            'organization_id': current_option['organization_id'],
            'quantity': current_option['quantity'],
            'unit': current_option['unit'],
            'route_distance_km': current_option['route']['distance_km'],
            'route_duration_min': current_option['route']['duration_min'],
        }
        proposal_type = 'allocation'

    proposal = AIProposal(
        incident_id=need.incident_id,
        batch_uuid=batch_uuid,
        candidate_key=candidate_id,
        proposal_type=proposal_type,
        payload=payload,
        rationale=rationale,
        confidence=confidence,
        source=source,
        status='proposed',
        created_by=actor_id,
        result_entity=result_entity,
        result_id=result_id,
    )
    db.add(proposal)
    db.flush()
    append_audit_log(
        db,
        actor_id=actor_id,
        action='ai_proposal_created',
        entity='ai_proposal',
        entity_id=proposal.id,
        after={
            'proposal_type': proposal.proposal_type,
            'status': proposal.status,
            'source': proposal.source,
            'confidence': proposal.confidence,
            'result_entity': proposal.result_entity,
            'result_id': proposal.result_id,
        },
    )
    return proposal