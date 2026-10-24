from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.intelligence_tasks import explain_bottleneck, judge_duplicate_reports, write_recovery_narrative
from ..db import get_db
from ..ledger import append_audit_log
from ..models import (
    BaselineSettlement,
    BottleneckFlag,
    DamageAssessment,
    DeliveryConfirmation,
    HazardZone,
    Incident,
    Location,
    Need,
    RawReport,
    ResourceMovement,
    User,
)
from ..schemas import BottleneckStatusPatch
from ..security import get_current_user
from ..services.bottlenecks import scan_bottlenecks

router = APIRouter(tags=['disaster intelligence'])
MANAGER_ROLES = {'admin', 'coordinator'}


def require_manager(user: User) -> None:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail='Coordinator role required')


def location_summary(db: Session, location: Location, incident_id: int) -> dict:
    needs = db.scalars(
        select(Need).where(Need.location_id == location.id, Need.incident_id == incident_id)
    ).all()
    confirmed = db.scalar(
        select(func.coalesce(func.sum(DeliveryConfirmation.quantity_received), 0.0))
        .join(ResourceMovement, ResourceMovement.id == DeliveryConfirmation.movement_id)
        .join(Need, Need.id == ResourceMovement.need_id)
        .where(Need.location_id == location.id, Need.incident_id == incident_id)
    ) or 0.0
    baseline = db.scalar(
        select(BaselineSettlement).where(BaselineSettlement.location_id == location.id)
    )
    verified_damage = db.scalars(
        select(DamageAssessment).where(
            DamageAssessment.location_id == location.id,
            DamageAssessment.verified.is_(True),
        )
    ).all()
    hazards = db.scalars(select(HazardZone).where(HazardZone.location_id == location.id)).all()
    return {
        'location_id': location.id,
        'location_name': location.name,
        'baseline_estimate': None if baseline is None else {
            'households': baseline.estimated_households,
            'population': baseline.estimated_population,
            'confidence': baseline.confidence,
            'verification_status': 'estimated',
        },
        'reported_need_count': len(needs),
        'reported_quantity_requested': sum(need.quantity_requested for need in needs),
        'reported_quantity_fulfilled': sum(need.quantity_fulfilled for need in needs),
        'confirmed_assistance_quantity': confirmed,
        'verified_damage_count': len(verified_damage),
        'verified_damage_level_max': max((item.damage_level for item in verified_damage), default=None),
        'hazard_zone_count': len(hazards),
        'open_need_count': sum(need.status in {'open', 'partially_fulfilled', 'in_progress'} for need in needs),
    }


@router.get('/situation')
def situation(
    incident_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    location_ids = set(db.scalars(select(Need.location_id).where(Need.incident_id == incident_id)))
    location_ids.update(db.scalars(select(BaselineSettlement.location_id)))
    location_ids.update(
        db.scalars(select(HazardZone.location_id).where(HazardZone.location_id.is_not(None)))
    )
    locations = db.scalars(select(Location).where(Location.id.in_(location_ids)).order_by(Location.id)).all()
    summaries = [location_summary(db, location, incident_id) for location in locations]
    needs = db.scalars(select(Need).where(Need.incident_id == incident_id)).all()
    return {
        'incident_id': incident_id,
        'incident_status': incident.status,
        'counts': {
            'locations': len(summaries),
            'needs': len(needs),
            'open_needs': sum(need.status in {'open', 'partially_fulfilled', 'in_progress'} for need in needs),
            'fulfilled_needs': sum(need.status == 'fulfilled' for need in needs),
            'verified_needs': sum(need.verification_status == 'verified' for need in needs),
        },
        'locations': summaries,
    }
@router.post('/bottlenecks/scan')
async def scan(
    incident_id: int = Query(gt=0),
    judge_duplicates: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    try:
        result = scan_bottlenecks(db, incident_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    judged = 0
    if judge_duplicates:
        candidate_flags = db.scalars(
            select(BottleneckFlag).where(
                BottleneckFlag.flag_type == 'duplicate_report_candidate',
                BottleneckFlag.status.in_(('open', 'acknowledged')),
            )
        ).all()
        for flag in candidate_flags:
            if flag.evidence.get('incident_id') != incident_id:
                continue
            similarity = flag.evidence.get('text_similarity', 0)
            if similarity < 0.9 or similarity >= 0.98:
                continue
            report_ids = flag.evidence.get('raw_report_ids', [])
            if len(report_ids) != 2:
                continue
            first, second = (db.get(RawReport, report_id) for report_id in report_ids)
            if first is None or second is None:
                continue
            verdict, source = await judge_duplicate_reports(db, first, second, similarity)
            before = {'evidence': flag.evidence, 'status': flag.status}
            flag.evidence = {
                **flag.evidence,
                'duplicate_judgment': {
                    'same_event': verdict.same_event,
                    'confidence': verdict.confidence,
                    'rationale': verdict.rationale,
                    'source': source,
                },
            }
            append_audit_log(
                db,
                actor_id=user.id,
                action='duplicate_report_judged',
                entity='bottleneck_flag',
                entity_id=flag.id,
                before=before,
                after={'evidence': flag.evidence, 'status': flag.status},
            )
            judged += 1
    db.commit()
    return {'incident_id': incident_id, **result, 'duplicate_pairs_judged': judged}


@router.get('/bottlenecks')
async def list_bottlenecks(
    incident_id: int = Query(gt=0),
    status: str | None = Query(default=None, pattern='^(open|acknowledged|resolved)$'),
    explain: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    statement = select(BottleneckFlag)
    if status is not None:
        statement = statement.where(BottleneckFlag.status == status)
    flags = db.scalars(statement.order_by(BottleneckFlag.severity.desc(), BottleneckFlag.id).limit(limit)).all()
    flags = [flag for flag in flags if flag.evidence.get('incident_id') == incident_id]
    response = [bottleneck_response(flag) for flag in flags]
    if explain:
        for flag, item in zip(flags[:5], response[:5]):
            explanation, source = await explain_bottleneck(db, flag)
            item['explanation'] = explanation.explanation
            item['suggested_action'] = explanation.suggested_action
            item['explanation_source'] = source
        db.commit()
    return response


@router.patch('/bottlenecks/{flag_id}')
def update_bottleneck(
    flag_id: int,
    data: BottleneckStatusPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    flag = db.get(BottleneckFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail='Bottleneck flag not found')
    if flag.status == 'resolved':
        raise HTTPException(status_code=409, detail='Resolved flags cannot be changed')
    before = flag.status
    flag.status = data.status
    append_audit_log(
        db,
        actor_id=user.id,
        action='bottleneck_status_changed',
        entity='bottleneck_flag',
        entity_id=flag.id,
        before={'status': before},
        after={'status': flag.status},
    )
    db.commit()
    return bottleneck_response(flag)


@router.get('/reports/recovery')
async def recovery_report(
    incident_id: int = Query(gt=0),
    explain: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_manager(user)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail='Incident not found')
    needs = db.scalars(select(Need).where(Need.incident_id == incident_id)).all()
    location_ids = {need.location_id for need in needs}
    location_ids.update(db.scalars(select(BaselineSettlement.location_id)))
    location_ids.update(
        db.scalars(select(HazardZone.location_id).where(HazardZone.location_id.is_not(None)))
    )
    baselines = db.scalars(
        select(BaselineSettlement).where(BaselineSettlement.location_id.in_(location_ids or {-1}))
    ).all()
    damage = db.scalars(
        select(DamageAssessment)
        .join(Location, Location.id == DamageAssessment.location_id)
        .where(Location.id.in_(location_ids or {-1}), DamageAssessment.verified.is_(True))
        .order_by(DamageAssessment.assessed_at)
    ).all()
    confirmed = db.scalar(
        select(func.coalesce(func.sum(DeliveryConfirmation.quantity_received), 0.0))
        .join(ResourceMovement, ResourceMovement.id == DeliveryConfirmation.movement_id)
        .join(Need, Need.id == ResourceMovement.need_id)
        .where(Need.incident_id == incident_id)
    ) or 0.0
    estimated_households = sum(row.estimated_households for row in baselines)
    confidence_values = [row.confidence for row in baselines]
    average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
    result = {
        'incident_id': incident.id,
        'incident_type': incident.incident_type,
        'confidence': 'medium' if average_confidence is None or average_confidence < 0.8 else 'high',
        'baseline_estimated_households': estimated_households,
        'baseline_confidence_average': average_confidence,
        'reported_needs': {
            'count': len(needs),
            'requested_quantity': sum(need.quantity_requested for need in needs),
            'confirmed_quantity': sum(need.quantity_fulfilled for need in needs),
            'remaining_quantity': sum(
                max(0, need.quantity_requested - need.quantity_fulfilled) for need in needs
            ),
        },
        'verified_damage_assessments': [
            {
                'location_id': assessment.location_id,
                'kind': assessment.kind,
                'damage_level': assessment.damage_level,
                'assessed_at': assessment.assessed_at.isoformat(),
            }
            for assessment in damage
        ],
        'confirmed_assistance_quantity': confirmed,
        'summary': 'Table-based recovery summary.',
        'summary_source': 'rules',
    }
    if explain:
        narrative, source = await write_recovery_narrative(
            db,
            {
                'incident_type': result['incident_type'],
                'baseline_estimated_households': result['baseline_estimated_households'],
                'baseline_confidence_average': result['baseline_confidence_average'],
                'reported_needs': result['reported_needs'],
                'verified_damage_assessments': result['verified_damage_assessments'],
                'confirmed_assistance_quantity': result['confirmed_assistance_quantity'],
            },
        )
        result['summary'] = narrative.narrative
        result['confidence'] = narrative.confidence
        result['summary_source'] = source
        db.commit()
    return result


def bottleneck_response(flag: BottleneckFlag) -> dict:
    return {
        'id': flag.id,
        'type': flag.flag_type,
        'location_id': flag.location_id,
        'need_id': flag.need_id,
        'severity': flag.severity,
        'evidence': flag.evidence,
        'status': flag.status,
        'detected_at': flag.detected_at.isoformat(),
        'explanation': flag.explanation,
        'suggested_action': flag.suggested_action,
    }
