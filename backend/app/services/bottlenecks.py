from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    BOTTLENECK_DISPATCH_HOURS,
    BOTTLENECK_STALE_REPORT_HOURS,
    BOTTLENECK_UNSTAFFED_HOURS,
    DUPLICATE_REPORT_SIMILARITY,
)
from ..ledger import append_audit_log
from ..models import (
    Assignment,
    BaselineSettlement,
    BottleneckFlag,
    DeliveryConfirmation,
    HazardZone,
    Incident,
    Location,
    Need,
    RawReport,
    ResourceMovement,
    Route,
)
from .matching import ACTIVE_ASSIGNMENT_STATUSES

OPEN_NEED_STATUSES = ('open', 'partially_fulfilled', 'in_progress')


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _record_flag(
    db: Session,
    actor_id: int,
    incident_id: int,
    *,
    flag_type: str,
    key: str,
    location_id: int | None,
    need_id: int | None,
    severity: int,
    evidence: dict,
    explanation: str,
    suggested_action: str,
    seen: set[str],
) -> bool:
    seen.add(key)
    payload = {'incident_id': incident_id, 'dedupe_key': key, **evidence}
    current_flags = db.scalars(
        select(BottleneckFlag).where(
            BottleneckFlag.flag_type == flag_type,
            BottleneckFlag.status.in_(('open', 'acknowledged')),
        )
    ).all()
    existing = next(
        (flag for flag in current_flags if flag.evidence.get('dedupe_key') == key),
        None,
    )
    if existing is not None:
        if existing.evidence != payload or existing.severity != severity:
            before = {'evidence': existing.evidence, 'severity': existing.severity}
            existing.evidence = payload
            existing.severity = severity
            existing.detected_at = datetime.now(timezone.utc)
            append_audit_log(
                db,
                actor_id=actor_id,
                action='bottleneck_evidence_updated',
                entity='bottleneck_flag',
                entity_id=existing.id,
                before=before,
                after={'evidence': payload, 'severity': severity},
            )
        return False

    flag = BottleneckFlag(
        flag_type=flag_type,
        location_id=location_id,
        need_id=need_id,
        severity=severity,
        evidence=payload,
        status='open',
        explanation=explanation,
        suggested_action=suggested_action,
    )
    db.add(flag)
    db.flush()
    append_audit_log(
        db,
        actor_id=actor_id,
        action='bottleneck_detected',
        entity='bottleneck_flag',
        entity_id=flag.id,
        after={
            'incident_id': incident_id,
            'flag_type': flag_type,
            'severity': severity,
            'evidence': payload,
        },
    )
    return True


def scan_bottlenecks(db: Session, incident_id: int, actor_id: int) -> dict:
    if db.get(Incident, incident_id) is None:
        raise ValueError('Incident not found')
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    created = 0
    examined = 0

    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.status.in_(OPEN_NEED_STATUSES),
        )
    ).all()
    needs_by_location: dict[int, list[Need]] = {}
    for need in needs:
        needs_by_location.setdefault(need.location_id, []).append(need)
    incident_reports = db.scalars(
        select(RawReport).where(RawReport.incident_id == incident_id)
    ).all()

    # A high-risk settlement with an estimated population but no linked Need/report is silent.
    for zone in db.scalars(
        select(HazardZone).where(HazardZone.risk_level >= 3, HazardZone.location_id.is_not(None))
    ):
        location_id = zone.location_id
        if location_id in needs_by_location:
            continue
        location = db.get(Location, location_id)
        baseline = db.scalar(
            select(BaselineSettlement).where(BaselineSettlement.location_id == location_id)
        )
        if baseline is None or baseline.estimated_households <= 0:
            continue
        has_raw_report = any(
            (report.parsed_json or {}).get('location_id') == location_id
            for report in incident_reports
        )
        if has_raw_report:
            continue
        examined += 1
        key = f'silent_area:{incident_id}:{location_id}:{zone.id}'
        created += _record_flag(
            db,
            actor_id,
            incident_id,
            flag_type='silent_area',
            key=key,
            location_id=location_id,
            need_id=None,
            severity=min(5, zone.risk_level + 1),
            evidence={
                'zone_id': zone.id,
                'hazard_type': zone.hazard_type,
                'risk_level': zone.risk_level,
                'estimated_households': baseline.estimated_households,
                'baseline_confidence': baseline.confidence,
                'location_name': location.name if location else None,
                'reported_need_count': 0,
            },
            explanation='High-risk area has a population baseline but no linked needs or located reports.',
            suggested_action='Contact local coordinators to verify conditions and register any reported needs.',
            seen=seen,
        )

    # Stalled deliveries and partial/missing receipts remain open until confirmed quantity catches up.
    movements = db.scalars(
        select(ResourceMovement).join(Need, Need.id == ResourceMovement.need_id).where(
            Need.incident_id == incident_id,
            ResourceMovement.status.in_(('dispatched', 'delivered', 'confirmed')),
        )
    ).all()
    stale_cutoff = now - timedelta(hours=BOTTLENECK_DISPATCH_HOURS)
    for movement in movements:
        examined += 1
        confirmed = movement.quantity_confirmed
        if confirmed < movement.quantity:
            timestamp = movement.delivered_at or movement.dispatched_at or movement.created_at
            if _utc(timestamp) <= stale_cutoff:
                need = db.get(Need, movement.need_id)
                key = f'stalled_delivery:{incident_id}:{movement.id}'
                created += _record_flag(
                    db,
                    actor_id,
                    incident_id,
                    flag_type='stalled_delivery',
                    key=key,
                    location_id=need.location_id,
                    need_id=need.id,
                    severity=4 if confirmed == 0 else 3,
                    evidence={
                        'movement_id': movement.id,
                        'movement_status': movement.status,
                        'quantity_dispatched': movement.quantity,
                        'quantity_confirmed': confirmed,
                        'age_hours': round((now - _utc(timestamp)).total_seconds() / 3600, 1),
                    },
                    explanation='Dispatched or delivered resources have no full receipt confirmation past the time limit.',
                    suggested_action='Contact the receiving community to confirm receipt or report a delivery issue.',
                    seen=seen,
                )
        confirmations = db.scalars(
            select(DeliveryConfirmation).where(DeliveryConfirmation.movement_id == movement.id)
        ).all()
        if any(item.status in {'partial', 'not_received'} for item in confirmations):
            need = db.get(Need, movement.need_id)
            key = f'delivery_mismatch:{incident_id}:{movement.id}'
            created += _record_flag(
                db,
                actor_id,
                incident_id,
                flag_type='delivery_mismatch',
                key=key,
                location_id=need.location_id,
                need_id=need.id,
                severity=4 if confirmed == 0 else 3,
                evidence={
                    'movement_id': movement.id,
                    'quantity_dispatched': movement.quantity,
                    'quantity_confirmed': confirmed,
                    'confirmation_ids': [item.id for item in confirmations],
                },
                explanation='Confirmed receipt is partial or missing relative to the dispatched quantity.',
                suggested_action='Verify the shortfall with the receiving group and arrange remaining supplies.',
                seen=seen,
            )

    # Open skilled Needs without active assignments are flagged after the response window.
    unstaffed_cutoff = now - timedelta(hours=BOTTLENECK_UNSTAFFED_HOURS)
    for need in needs:
        if not need.required_skills or _utc(need.last_updated_at) > unstaffed_cutoff:
            continue
        active_count = sum(
            1
            for assignment in db.scalars(
                select(Assignment).where(
                    Assignment.need_id == need.id,
                    Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                )
            )
        )
        if active_count:
            continue
        examined += 1
        key = f'unstaffed_need:{incident_id}:{need.id}'
        created += _record_flag(
            db,
            actor_id,
            incident_id,
            flag_type='unstaffed_need',
            key=key,
            location_id=need.location_id,
            need_id=need.id,
            severity=need.urgency,
            evidence={
                'required_skills': need.required_skills,
                'hours_open': round((now - _utc(need.last_updated_at)).total_seconds() / 3600, 1),
            },
            explanation='An aged open Need requiring skills has no active assignment.',
            suggested_action='Review verified volunteer candidates or request additional responders.',
            seen=seen,
        )

    # Flag overlapping assignments for one volunteer or duplicate assignments on one Need.
    assignments = db.scalars(
        select(Assignment)
        .join(Need, Need.id == Assignment.need_id)
        .where(
            Need.incident_id == incident_id,
            Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        .order_by(Assignment.id)
    ).all()
    for index, first in enumerate(assignments):
        for second in assignments[index + 1:]:
            same_need = first.need_id == second.need_id
            same_volunteer = first.volunteer_id == second.volunteer_id
            if not same_need and not same_volunteer:
                continue
            overlaps = (
                first.starts_at is None or second.starts_at is None
                or (first.starts_at < second.ends_at and second.starts_at < first.ends_at)
            )
            if not same_need and not overlaps:
                continue
            examined += 1
            key = f'duplicate_assignment:{incident_id}:{first.id}:{second.id}'
            need = db.get(Need, first.need_id)
            created += _record_flag(
                db,
                actor_id,
                incident_id,
                flag_type='duplicate_assignment',
                key=key,
                location_id=need.location_id,
                need_id=need.id,
                severity=4,
                evidence={
                    'assignment_ids': [first.id, second.id],
                    'same_need': same_need,
                    'same_volunteer': same_volunteer,
                    'overlapping_window': overlaps,
                },
                explanation='Two active assignments target the same Need or overlap for the same volunteer.',
                suggested_action='Review assignments and keep only the approved feasible coverage.',
                seen=seen,
            )

    # An active assignment whose stored route intersects a known blockage requires review.
    for assignment in assignments:
        route = db.get(Route, assignment.route_id) if assignment.route_id else None
        if route is None or route.avoids_blockages:
            continue
        need = db.get(Need, assignment.need_id)
        examined += 1
        key = f'blocked_access:{incident_id}:{assignment.id}:{route.id}'
        created += _record_flag(
            db,
            actor_id,
            incident_id,
            flag_type='blocked_access',
            key=key,
            location_id=need.location_id,
            need_id=need.id,
            severity=5,
            evidence={
                'assignment_id': assignment.id,
                'route_id': route.id,
                'blocked_segments_considered': route.blocked_segments_considered,
            },
            explanation='An active assignment has no estimated route that avoids all verified blockages.',
            suggested_action='Ask the coordinator to choose an alternate responder or path before travel continues.',
            seen=seen,
        )

    # Pending report parses that exceed the freshness window need coordinator review.
    report_cutoff = now - timedelta(hours=BOTTLENECK_STALE_REPORT_HOURS)
    for report in incident_reports:
        if report.parse_status != 'pending' or _utc(report.received_at) > report_cutoff:
            continue
        examined += 1
        location_id = (report.parsed_json or {}).get('location_id')
        key = f'stale_report:{incident_id}:{report.id}'
        created += _record_flag(
            db,
            actor_id,
            incident_id,
            flag_type='stale_report',
            key=key,
            location_id=location_id,
            need_id=None,
            severity=3,
            evidence={
                'raw_report_id': report.id,
                'channel': report.channel,
                'age_hours': round((now - _utc(report.received_at)).total_seconds() / 3600, 1),
            },
            explanation='A raw report remains unparsed beyond the configured freshness window.',
            suggested_action='Review the report and create or update the related Need.',
            seen=seen,
        )

    # Exact and near-identical raw reports are deterministic duplicate candidates.
    reports = [
        report for report in incident_reports
        if _utc(report.received_at) >= now - timedelta(days=2)
    ]
    for index, first in enumerate(reports):
        normalized_first = ' '.join(first.text.casefold().split())
        for second in reports[index + 1:]:
            if first.id == second.id:
                continue
            normalized_second = ' '.join(second.text.casefold().split())
            similarity = SequenceMatcher(None, normalized_first, normalized_second).ratio()
            if similarity < DUPLICATE_REPORT_SIMILARITY:
                continue
            examined += 1
            key = f'duplicate_report:{incident_id}:{first.id}:{second.id}'
            created += _record_flag(
                db,
                actor_id,
                incident_id,
                flag_type='duplicate_report_candidate',
                key=key,
                location_id=None,
                need_id=None,
                severity=3,
                evidence={
                    'raw_report_ids': [first.id, second.id],
                    'text_similarity': round(similarity, 3),
                    'judge': 'rules',
                },
                explanation='Recent report texts are highly similar and may describe the same event.',
                suggested_action='Compare sender, time, and location before merging or dismissing either report.',
                seen=seen,
            )

    # Resolve old open flags for this incident when their underlying condition disappears.
    open_flags = db.scalars(
        select(BottleneckFlag).where(BottleneckFlag.status == 'open')
    ).all()
    resolved = 0
    for flag in open_flags:
        if flag.evidence.get('incident_id') != incident_id:
            continue
        if flag.evidence.get('dedupe_key') in seen:
            continue
        before = flag.status
        flag.status = 'resolved'
        append_audit_log(
            db,
            actor_id=actor_id,
            action='bottleneck_resolved',
            entity='bottleneck_flag',
            entity_id=flag.id,
            before={'status': before},
            after={'status': flag.status, 'reason': 'condition_not_detected_on_rescan'},
        )
        resolved += 1

    return {'created': created, 'resolved': resolved, 'examined': examined}
