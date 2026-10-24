import asyncio
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.report_tasks import parse_report
from ..db import get_db
from ..ledger import append_audit_log
from ..models import Incident, Location, Need, RawReport, User
from ..schemas import NeedPatch, ReportCreate
from ..security import get_current_user


router = APIRouter(tags=['reports and needs'])
optional_bearer = HTTPBearer(auto_error=False)


def _optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
):
    if credentials is None:
        return None
    return get_current_user(credentials, db)


@router.post('/reports', status_code=201)
async def create_report(
    data: ReportCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User | None = Depends(_optional_current_user),
):
    existing = db.scalar(select(RawReport).where(RawReport.client_uuid == str(data.client_uuid)))
    if existing is not None:
        response.status_code = 200
        existing_needs = db.scalars(
            select(Need).where(Need.source_report_id == existing.id).order_by(Need.id)
        ).all()
        return _report_response(existing, existing_needs, 'duplicate')
    if data.incident_id is not None and db.get(Incident, data.incident_id) is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    if data.location_id is not None and db.get(Location, data.location_id) is None:
        raise HTTPException(status_code=404, detail='Location not found')

    report = RawReport(
        incident_id=data.incident_id,
        text=data.text.strip(),
        channel=data.channel,
        sender_ref=data.sender_ref.strip() if data.sender_ref else None,
        client_uuid=str(data.client_uuid),
        received_at=datetime.now(timezone.utc),
        parse_status='pending',
    )
    db.add(report)
    db.flush()
    locations = db.scalars(select(Location).order_by(Location.id)).all()
    parsed, source = await parse_report(db, report.text, [location.name for location in locations])
    parsed_data = parsed.model_dump()
    parsed_data['source'] = source
    report.parsed_json = parsed_data
    report.parse_status = 'parsed' if source == 'ai' else 'pending'

    incident = db.get(Incident, data.incident_id) if data.incident_id else _single_active_incident(db)
    location = db.get(Location, data.location_id) if data.location_id else _resolve_location(
        parsed.location_text, locations
    )
    if incident is not None:
        report.incident_id = incident.id
    if location is not None:
        report.location_id = location.id
        parsed_data['location_id'] = location.id
        report.parsed_json = parsed_data
    needs = []
    if incident is not None and location is not None:
        for item in parsed.needs:
            need = Need(
                incident_id=incident.id,
                location_id=location.id,
                category=item.category,
                description=item.item,
                required_skills=item.required_skills,
                quantity_requested=item.quantity if item.quantity is not None else 0,
                unit=item.unit or 'unspecified',
                urgency=parsed.urgency,
                vulnerable_groups=parsed.vulnerable_groups,
                status='open',
                verification_status='unverified',
                confidence=parsed.confidence,
                source='report',
                source_report_id=report.id,
            )
            db.add(need)
            db.flush()
            needs.append(need)
            append_audit_log(
                db,
                actor_id=user.id if user else None,
                action='need_created_from_report',
                entity='need',
                entity_id=need.id,
                after={
                    'incident_id': incident.id,
                    'location_id': location.id,
                    'category': need.category,
                    'description': need.description,
                    'verification_status': need.verification_status,
                    'source_report_id': report.id,
                },
            )

    append_audit_log(
        db,
        actor_id=user.id if user else None,
        action='report_received',
        entity='raw_report',
        entity_id=report.id,
        after={
            'client_uuid': report.client_uuid,
            'channel': report.channel,
            'parse_status': report.parse_status,
            'need_ids': [need.id for need in needs],
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(RawReport).where(RawReport.client_uuid == str(data.client_uuid)))
        if existing is not None:
            response.status_code = 200
            existing_needs = db.scalars(
                select(Need).where(Need.source_report_id == existing.id).order_by(Need.id)
            ).all()
            return _report_response(existing, existing_needs, 'duplicate')
        raise

    db.refresh(report)
    for need in needs:
        db.refresh(need)
    return _report_response(report, needs, 'created')


@router.get('/needs')
def list_needs(
    incident_id: int | None = None,
    location_id: int | None = None,
    category: str | None = None,
    status: str | None = None,
    urgency: int | None = Query(default=None, ge=1, le=5),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = select(Need).order_by(Need.id)
    if incident_id is not None:
        query = query.where(Need.incident_id == incident_id)
    if location_id is not None:
        query = query.where(Need.location_id == location_id)
    if category is not None:
        query = query.where(Need.category == category)
    if status is not None:
        query = query.where(Need.status == status)
    if urgency is not None:
        query = query.where(Need.urgency == urgency)
    needs = db.scalars(query.offset(offset).limit(limit)).all()
    report_ids = {need.source_report_id for need in needs if need.source_report_id is not None}
    reports = {
        report.id: report
        for report in db.scalars(select(RawReport).where(RawReport.id.in_(report_ids))).all()
    } if report_ids else {}
    return {
        'items': [_need_response(need, reports.get(need.source_report_id)) for need in needs],
        'limit': limit,
        'offset': offset,
    }


@router.get('/needs/{need_id}')
def get_need(
    need_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    need = db.get(Need, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    report = db.get(RawReport, need.source_report_id) if need.source_report_id else None
    return _need_response(need, report)


@router.patch('/needs/{need_id}')
def patch_need(
    need_id: int,
    data: NeedPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in {'admin', 'coordinator'}:
        raise HTTPException(status_code=403, detail='Coordinator role required')
    need = db.get(Need, need_id)
    if need is None:
        raise HTTPException(status_code=404, detail='Need not found')
    changes = data.model_dump(exclude_unset=True)
    if (
        'quantity_requested' in changes
        and changes['quantity_requested'] < need.quantity_fulfilled
    ):
        raise HTTPException(
            status_code=409,
            detail='Requested quantity cannot be less than confirmed fulfilled quantity',
        )
    before = {field: getattr(need, field) for field in changes}
    for field, value in changes.items():
        setattr(need, field, value)
    need.last_updated_at = datetime.now(timezone.utc)
    after = {field: getattr(need, field) for field in changes}
    append_audit_log(
        db,
        actor_id=user.id,
        action='need_updated',
        entity='need',
        entity_id=need.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(need)
    report = db.get(RawReport, need.source_report_id) if need.source_report_id else None
    return _need_response(need, report)


def _single_active_incident(db: Session) -> Incident | None:
    incidents = db.scalars(
        select(Incident).where(Incident.status == 'active').order_by(Incident.started_at.desc()).limit(2)
    ).all()
    return incidents[0] if len(incidents) == 1 else None


def _normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def _resolve_location(location_text: str | None, locations: list[Location]) -> Location | None:
    if not location_text:
        return None
    query = _normalize(location_text)
    matches = [
        location for location in locations
        if _location_matches(location.name, query)
    ]
    return matches[0] if len(matches) == 1 else None


def _location_matches(name: str, query: str) -> bool:
    normalized_name = _normalize(name)
    padded_query = f' {query} '
    return bool(normalized_name) and (
        normalized_name == query
        or f' {normalized_name} ' in padded_query
        or f' {normalized_name.split()[-1]} ' in padded_query
    )


def _need_response(need: Need, report: RawReport | None = None) -> dict:
    return {
        'id': need.id,
        'incident_id': need.incident_id,
        'location_id': need.location_id,
        'category': need.category,
        'description': need.description,
        'required_skills': need.required_skills,
        'quantity_requested': need.quantity_requested,
        'quantity_fulfilled': need.quantity_fulfilled,
        'unit': need.unit,
        'urgency': need.urgency,
        'vulnerable_groups': need.vulnerable_groups,
        'status': need.status,
        'verification_status': need.verification_status,
        'confidence': need.confidence,
        'source': need.source,
        'source_report_id': need.source_report_id,
        'last_updated_at': need.last_updated_at,
    }


def _report_response(report: RawReport, needs: list[Need], result: str) -> dict:
    return {
        'id': report.id,
        'result': result,
        'incident_id': report.incident_id,
        'channel': report.channel,
        'parse_status': report.parse_status,
        'parsed': report.parsed_json,
        'needs': [_need_response(need, report) for need in needs],
    }