from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BaselineSettlement,
    DamageAssessment,
    HazardZone,
    HistoricalIncident,
    Location,
    Need,
    RawReport,
    SOSEvent,
)


OPEN_NEED_STATUSES = ('open', 'partially_fulfilled', 'in_progress')
RECENT_INCIDENT_WINDOW = timedelta(days=30)


def build_location_exposure(
    db: Session,
    *,
    incident_id: int,
    location: Location,
    rainfall: dict | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    baseline = db.scalar(
        select(BaselineSettlement).where(BaselineSettlement.location_id == location.id)
    )
    hazards = db.scalars(
        select(HazardZone).where(HazardZone.location_id == location.id)
    ).all()
    needs = db.scalars(
        select(Need).where(
            Need.incident_id == incident_id,
            Need.location_id == location.id,
        )
    ).all()
    reports = db.scalars(
        select(RawReport).where(
            RawReport.incident_id == incident_id,
            RawReport.location_id == location.id,
        )
    ).all()
    damage = db.scalars(
        select(DamageAssessment).where(
            DamageAssessment.location_id == location.id,
            DamageAssessment.verified.is_(True),
        )
    ).all()
    sos_events = db.scalars(
        select(SOSEvent)
        .join(Need, Need.id == SOSEvent.linked_need_id)
        .where(
            SOSEvent.incident_id == incident_id,
            Need.location_id == location.id,
        )
    ).all()
    recent_incidents = db.scalars(
        select(HistoricalIncident).where(
            HistoricalIncident.location_id == location.id,
            HistoricalIncident.occurred_at >= now - RECENT_INCIDENT_WINDOW,
        )
    ).all()

    estimated_households = (
        baseline.estimated_households
        if baseline is not None
        else location.baseline_households_estimate
    )
    estimated_population = baseline.estimated_population if baseline is not None else None
    baseline_confidence = baseline.confidence if baseline is not None else None
    baseline_source = baseline.source if baseline is not None else None
    baseline_year = baseline.data_date.year if baseline is not None and baseline.data_date else None

    reported_households = sum(
        report.parsed_json.get('families_affected', 0)
        for report in reports
        if isinstance(report.parsed_json, dict)
        and isinstance(report.parsed_json.get('families_affected'), int)
    )
    active_needs = [need for need in needs if need.status in OPEN_NEED_STATUSES]
    verified_need_count = sum(need.verification_status == 'verified' for need in needs)
    verified_damage = [item for item in damage if item.damage_level > 0]
    max_hazard_risk = max((zone.risk_level for zone in hazards), default=0)
    forecast_values = _precipitation_values(rainfall)
    forecast_total_mm = round(sum(forecast_values), 2) if forecast_values else None

    if verified_damage or verified_need_count:
        exposure_level = 'confirmed'
        confidence = 'high'
    elif max_hazard_risk >= 3 or recent_incidents:
        exposure_level = 'likely'
        confidence = 'medium'
    elif hazards or needs or reports or sos_events or (forecast_total_mm is not None and forecast_total_mm > 0):
        exposure_level = 'watch'
        confidence = 'low'
    else:
        exposure_level = 'none'
        confidence = 'low'

    vulnerable_groups = sorted({
        group for need in needs for group in (need.vulnerable_groups or [])
    })
    urgency = max(
        [need.urgency for need in active_needs]
        + ([max_hazard_risk] if max_hazard_risk else [])
        + [1]
    )
    unmet_shares = [
        max(0.0, need.quantity_requested - need.quantity_fulfilled) / need.quantity_requested
        if need.quantity_requested > 0 else 1.0
        for need in active_needs
    ]
    if unmet_shares:
        unmet_share = sum(unmet_shares) / len(unmet_shares)
    else:
        unmet_share = 1.0 if exposure_level != 'none' else 0.0
    people_factor = max(
        1,
        reported_households,
        estimated_households or 0 if hazards else 0,
    )
    vulnerable_factor = 1.25 if vulnerable_groups else 1.0
    latest_evidence = [
        _as_utc(report.received_at) for report in reports
    ] + [
        _as_utc(need.last_updated_at) for need in active_needs
    ] + [
        _as_utc(event.received_at_server) for event in sos_events
    ]
    if latest_evidence:
        age_hours = max(0.0, (now - max(latest_evidence)).total_seconds() / 3600)
        freshness_factor = max(0.25, 1.0 - min(age_hours / (24 * 7), 0.75))
    else:
        freshness_factor = 0.5 if exposure_level != 'none' else 0.0
    priority_score = round(
        urgency * people_factor * vulnerable_factor * unmet_share * freshness_factor,
        2,
    )

    evidence = {
        'baseline': {
            'estimated_households': estimated_households,
            'estimated_population': estimated_population,
            'source': baseline_source,
            'year': baseline_year,
            'confidence': baseline_confidence,
            'verification_status': 'estimated',
        },
        'reported': {
            'report_count': len(reports),
            'reported_households': reported_households,
            'verification_status': 'unverified',
        },
        'verified': {
            'verified_need_count': verified_need_count,
            'verified_damage_count': len(verified_damage),
            'verified_households': None,
        },
        'hazard_zones': [
            {
                'type': zone.hazard_type,
                'risk_level': zone.risk_level,
                'source': zone.source,
            }
            for zone in hazards
        ],
        'recent_incident_count_30d': len(recent_incidents),
        'need_count': len(needs),
        'active_need_count': len(active_needs),
        'vulnerable_groups': vulnerable_groups,
        'sos_count_linked_to_location_needs': len(sos_events),
        'rainfall_forecast': {
            'source': rainfall.get('source'),
            'verification_status': rainfall.get('verification_status'),
            'precipitation_total_mm': forecast_total_mm,
        } if rainfall is not None else None,
        'priority_factors': {
            'urgency': urgency,
            'people_factor': people_factor,
            'vulnerable_factor': vulnerable_factor,
            'unmet_share': round(unmet_share, 3),
            'freshness_factor': round(freshness_factor, 3),
        },
    }
    return {
        'location_id': location.id,
        'location_name': location.name,
        'exposure_level': exposure_level,
        'estimated_households': estimated_households,
        'estimated_population': estimated_population,
        'reported_households': reported_households,
        'verified_households': None,
        'confidence': confidence,
        'priority_score': priority_score,
        'evidence': evidence,
    }


def _precipitation_values(rainfall: dict | None) -> list[float]:
    if not rainfall or not isinstance(rainfall.get('data'), dict):
        return []
    hourly = rainfall['data'].get('hourly')
    values = hourly.get('precipitation') if isinstance(hourly, dict) else None
    return [value for value in values if isinstance(value, (int, float))] if isinstance(values, list) else []


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)