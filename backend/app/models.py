
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Contribution(Base):
    __tablename__ = 'contributions'

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_name: Mapped[str] = mapped_column(String(120))
    is_anonymous: Mapped[bool] = mapped_column(default=False)
    amount_npr: Mapped[float | None] = mapped_column(Float, nullable=True)
    txn_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='ready')
    slip_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_token: Mapped[str] = mapped_column(
        String(40), unique=True, default=lambda: secrets.token_urlsafe(8)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LedgerEntry(Base):
    __tablename__ = 'ledger_entries'

    id: Mapped[int] = mapped_column(primary_key=True)
    contribution_id: Mapped[int]
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    record_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(30), default='community_member')
    organization_id: Mapped[int | None] = mapped_column(ForeignKey('organizations.id'), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Organization(Base):
    __tablename__ = 'organizations'
    __table_args__ = (
        CheckConstraint('trust_score BETWEEN 0 AND 1', name='ck_organizations_trust_score'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    organization_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Incident(Base):
    __tablename__ = 'incidents'

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default='active')
    affected_area: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Location(Base):
    __tablename__ = 'locations'
    __table_args__ = (
        CheckConstraint(
            '(latitude IS NULL AND longitude IS NULL) OR '
            '(latitude IS NOT NULL AND longitude IS NOT NULL)',
            name='ck_locations_coordinate_pair',
        ),
        CheckConstraint(
            'latitude IS NULL OR latitude BETWEEN -90 AND 90',
            name='ck_locations_latitude_range',
        ),
        CheckConstraint(
            'longitude IS NULL OR longitude BETWEEN -180 AND 180',
            name='ck_locations_longitude_range',
        ),
        CheckConstraint(
            'baseline_households_estimate IS NULL OR baseline_households_estimate >= 0',
            name='ck_locations_nonnegative_household_estimate',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    location_type: Mapped[str] = mapped_column(String(30))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    boundary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_location_id: Mapped[int | None] = mapped_column(
        ForeignKey('locations.id'), nullable=True
    )
    baseline_households_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Need(Base):
    __tablename__ = 'needs'
    __table_args__ = (
        CheckConstraint(
            "category IN ('rescue', 'medical', 'water', 'food', 'shelter', "
            "'technical_repair', 'other')",
            name='ck_needs_category',
        ),
        CheckConstraint('quantity_requested >= 0', name='ck_needs_requested_nonnegative'),
        CheckConstraint('quantity_fulfilled >= 0', name='ck_needs_fulfilled_nonnegative'),
        CheckConstraint('quantity_fulfilled <= quantity_requested', name='ck_needs_fulfilled_lte_requested'),
        CheckConstraint('urgency BETWEEN 1 AND 5', name='ck_needs_urgency_range'),
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name='ck_needs_confidence'),
        CheckConstraint(
            'priority_rank IS NULL OR priority_rank >= 1',
            name='ck_needs_priority_rank_positive',
        ),
        CheckConstraint(
            "status IN ('open', 'partially_fulfilled', 'in_progress', 'fulfilled', 'closed')",
            name='ck_needs_status',
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name='ck_needs_verification_status',
        ),
        CheckConstraint(
            "source IN ('sos', 'report', 'volunteer', 'coordinator')",
            name='ck_needs_source',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('incidents.id'))
    location_id: Mapped[int] = mapped_column(ForeignKey('locations.id'))
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    quantity_requested: Mapped[float] = mapped_column(Float)
    quantity_fulfilled: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(40))
    urgency: Mapped[int] = mapped_column(Integer)
    vulnerable_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default='open')
    verification_status: Mapped[str] = mapped_column(String(20), default='unverified')
    confidence: Mapped[str] = mapped_column(String(10), default='low', server_default='low')
    priority_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default='coordinator')
    source_report_id: Mapped[int | None] = mapped_column(
        ForeignKey('raw_reports.id', ondelete='RESTRICT'), nullable=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AuditLog(Base):
    __tablename__ = 'audit_log'
    __table_args__ = (UniqueConstraint('entry_hash', name='uq_audit_log_entry_hash'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


class AIProposal(Base):
    __tablename__ = 'ai_proposals'
    __table_args__ = (
        UniqueConstraint('batch_uuid', 'candidate_key', name='uq_ai_proposal_batch_candidate'),
        CheckConstraint(
            "proposal_type IN ('assignment', 'reassignment', 'allocation', 'bottleneck_flag', 'priority')",
            name='ck_ai_proposals_type',
        ),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name='ck_ai_proposals_status',
        ),
        CheckConstraint("source IN ('ai', 'fallback')", name='ck_ai_proposals_source'),
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name='ck_ai_proposals_confidence'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('incidents.id'))
    batch_uuid: Mapped[str] = mapped_column(String(36))
    candidate_key: Mapped[str] = mapped_column(String(160))
    proposal_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='proposed')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_entity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VolunteerProfile(Base):
    __tablename__ = 'volunteer_profiles'
    __table_args__ = (
        CheckConstraint('max_travel_km > 0', name='ck_volunteer_profiles_positive_travel'),
        CheckConstraint(
            "availability_status IN ('available', 'assigned', 'unavailable', 'off_duty')",
            name='ck_volunteer_profiles_availability',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey('organizations.id'), nullable=True)
    base_location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id'), nullable=True)
    max_travel_km: Mapped[float] = mapped_column(Float, default=50)
    availability_status: Mapped[str] = mapped_column(String(20), default='available')
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, default=False)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Skill(Base):
    __tablename__ = 'skills'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(60))


class VolunteerSkill(Base):
    __tablename__ = 'volunteer_skills'
    __table_args__ = (
        UniqueConstraint('volunteer_id', 'skill_id', name='uq_volunteer_skill'),
        CheckConstraint('level BETWEEN 1 AND 5', name='ck_volunteer_skills_level'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey('volunteer_profiles.id'))
    skill_id: Mapped[int] = mapped_column(ForeignKey('skills.id'))
    level: Mapped[int] = mapped_column(Integer, default=1)
    certification_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    certificate_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AvailabilityWindow(Base):
    __tablename__ = 'availability_windows'
    __table_args__ = (
        CheckConstraint('ends_at > starts_at', name='ck_availability_window_order'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey('volunteer_profiles.id'))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoadBlockage(Base):
    __tablename__ = 'road_blockages'
    __table_args__ = (
        CheckConstraint('latitude BETWEEN -90 AND 90', name='ck_blockages_latitude_range'),
        CheckConstraint('longitude BETWEEN -180 AND 180', name='ck_blockages_longitude_range'),
        CheckConstraint('radius_km > 0 AND radius_km <= 5', name='ck_blockages_radius_range'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=0.25)
    reported_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Route(Base):
    __tablename__ = 'routes'
    __table_args__ = (
        CheckConstraint('distance_km >= 0', name='ck_routes_nonnegative_distance'),
        CheckConstraint('duration_min >= 0', name='ck_routes_nonnegative_duration'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_point: Mapped[dict] = mapped_column(JSON)
    to_point: Mapped[dict] = mapped_column(JSON)
    geometry: Mapped[list[dict]] = mapped_column(JSON)
    distance_km: Mapped[float] = mapped_column(Float)
    duration_min: Mapped[float] = mapped_column(Float)
    blocked_segments_considered: Mapped[list[int]] = mapped_column(JSON, default=list)
    avoids_blockages: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    engine: Mapped[str] = mapped_column(String(30), default='estimate')


class Assignment(Base):
    __tablename__ = 'assignments'
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'approved', 'accepted', 'en_route', 'on_site', "
            "'completed', 'cancelled', 'rejected')",
            name='ck_assignments_status',
        ),
        CheckConstraint("proposed_by IN ('ai', 'coordinator')", name='ck_assignments_proposed_by'),
        CheckConstraint(
            'starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at',
            name='ck_assignments_task_window_order',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey('needs.id'))
    volunteer_id: Mapped[int] = mapped_column(ForeignKey('volunteer_profiles.id'))
    status: Mapped[str] = mapped_column(String(20), default='proposed')
    proposed_by: Mapped[str] = mapped_column(String(20), default='coordinator')
    route_id: Mapped[int | None] = mapped_column(ForeignKey('routes.id'), nullable=True)
    required_skills_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_criteria_met: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AICallLog(Base):
    __tablename__ = 'ai_call_log'

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_summary: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text)
    validation_result: Mapped[str] = mapped_column(String(300))
    fallback_used: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RawReport(Base):
    __tablename__ = 'raw_reports'
    __table_args__ = (
        CheckConstraint("channel IN ('app', 'sms', 'mesh', 'web')", name='ck_raw_reports_channel'),
        UniqueConstraint('client_uuid', name='uq_raw_reports_client_uuid'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey('incidents.id'), nullable=True)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey('locations.id', ondelete='SET NULL'), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20))
    sender_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    client_uuid: Mapped[str] = mapped_column(String(36))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    parse_status: Mapped[str] = mapped_column(String(20), default='pending')
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BaselineSettlement(Base):
    __tablename__ = 'baseline_settlements'
    __table_args__ = (
        UniqueConstraint('location_id', name='uq_baseline_settlements_location'),
        CheckConstraint('estimated_households >= 0', name='ck_baseline_households_nonnegative'),
        CheckConstraint(
            'estimated_population IS NULL OR estimated_population >= 0',
            name='ck_baseline_population_nonnegative',
        ),
        CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_baseline_confidence_range'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey('locations.id'))
    estimated_households: Mapped[int] = mapped_column(Integer)
    estimated_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(40))
    data_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BaselineFeature(Base):
    __tablename__ = 'baseline_features'

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_type: Mapped[str] = mapped_column(String(60))
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    geometry: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(80))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HistoricalIncident(Base):
    __tablename__ = 'historical_incidents'

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id'), nullable=True)
    affected_area: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(80))


class HazardZone(Base):
    __tablename__ = 'hazard_zones'
    __table_args__ = (
        CheckConstraint("hazard_type IN ('flood', 'landslide', 'other')", name='ck_hazard_zones_type'),
        CheckConstraint('risk_level BETWEEN 1 AND 5', name='ck_hazard_zones_risk'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id'), nullable=True)
    geometry: Mapped[dict] = mapped_column(JSON)
    hazard_type: Mapped[str] = mapped_column(String(30))
    risk_level: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DamageAssessment(Base):
    __tablename__ = 'damage_assessments'
    __table_args__ = (
        CheckConstraint("kind IN ('pre', 'post')", name='ck_damage_assessments_kind'),
        CheckConstraint('damage_level BETWEEN 0 AND 5', name='ck_damage_assessments_level'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey('locations.id'))
    kind: Mapped[str] = mapped_column(String(10))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    damage_level: Mapped[int] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Resource(Base):
    __tablename__ = 'resources'

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResourceStock(Base):
    __tablename__ = 'resource_stock'
    __table_args__ = (
        UniqueConstraint(
            'organization_id', 'resource_id', 'location_id',
            name='uq_resource_stock_source',
        ),
        CheckConstraint('quantity_available >= 0', name='ck_resource_stock_available'),
        CheckConstraint('quantity_reserved >= 0', name='ck_resource_stock_reserved'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'))
    resource_id: Mapped[int] = mapped_column(ForeignKey('resources.id'))
    location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id'), nullable=True)
    quantity_available: Mapped[float] = mapped_column(Float)
    quantity_reserved: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ResourceMovement(Base):
    __tablename__ = 'resource_movements'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_resource_movements_positive_quantity'),
        CheckConstraint('quantity_confirmed >= 0', name='ck_resource_movements_confirmed_nonnegative'),
        CheckConstraint('quantity_confirmed <= quantity', name='ck_resource_movements_confirmed_lte_quantity'),
        CheckConstraint(
            "status IN ('allocated', 'dispatched', 'delivered', 'confirmed', 'cancelled')",
            name='ck_resource_movements_status',
        ),
        UniqueConstraint('client_uuid', name='uq_resource_movements_client_uuid'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey('needs.id'))
    resource_id: Mapped[int] = mapped_column(ForeignKey('resources.id'))
    stock_id: Mapped[int] = mapped_column(ForeignKey('resource_stock.id'))
    quantity: Mapped[float] = mapped_column(Float)
    quantity_confirmed: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default='allocated')
    client_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    allocated_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeliveryConfirmation(Base):
    __tablename__ = 'delivery_confirmations'
    __table_args__ = (
        CheckConstraint(
            "status IN ('full', 'partial', 'not_received')",
            name='ck_delivery_confirmations_status',
        ),
        CheckConstraint('quantity_received >= 0', name='ck_delivery_confirmations_quantity'),
        UniqueConstraint('client_uuid', name='uq_delivery_confirmations_client_uuid'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey('resource_movements.id'))
    client_uuid: Mapped[str] = mapped_column(String(36))
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20))
    quantity_received: Mapped[float] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BottleneckFlag(Base):
    __tablename__ = 'bottleneck_flags'
    __table_args__ = (
        CheckConstraint('severity BETWEEN 1 AND 5', name='ck_bottleneck_flags_severity'),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name='ck_bottleneck_flags_status',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    flag_type: Mapped[str] = mapped_column(String(60))
    location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id'), nullable=True)
    need_id: Mapped[int | None] = mapped_column(ForeignKey('needs.id'), nullable=True)
    severity: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='open')
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    explanation: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)


class Gateway(Base):
    __tablename__ = 'gateways'
    __table_args__ = (
        CheckConstraint("gateway_type IN ('meshtastic', 'sms', 'app')", name='ck_gateways_type'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    gateway_type: Mapped[str] = mapped_column(String(20))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SOSEvent(Base):
    __tablename__ = 'sos_events'
    __table_args__ = (
        UniqueConstraint('client_uuid', name='uq_sos_events_client_uuid'),
        CheckConstraint(
            "category IN ('FOOD', 'MEDICINE', 'TRAPPED', 'RESCUE', 'OTHER')",
            name='ck_sos_events_category',
        ),
        CheckConstraint(
            "channel IN ('app', 'mesh', 'sms', 'gateway')",
            name='ck_sos_events_channel',
        ),
        CheckConstraint(
            "status IN ('new', 'acknowledged', 'dispatched', 'resolved', 'false_alarm')",
            name='ck_sos_events_status',
        ),
        CheckConstraint('urgency BETWEEN 1 AND 5', name='ck_sos_events_urgency'),
        CheckConstraint('latitude IS NULL OR latitude BETWEEN -90 AND 90', name='ck_sos_events_latitude'),
        CheckConstraint('longitude IS NULL OR longitude BETWEEN -180 AND 180', name='ck_sos_events_longitude'),
        CheckConstraint(
            "(has_location = 0) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude != 0 AND longitude != 0)",
            name='ck_sos_events_location_honesty',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_uuid: Mapped[str] = mapped_column(String(36))
    incident_id: Mapped[int | None] = mapped_column(ForeignKey('incidents.id'), nullable=True)
    sender_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sender_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_location: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(20), default='OTHER')
    urgency: Mapped[int] = mapped_column(Integer, default=3)
    message: Mapped[str] = mapped_column(String(500))
    created_at_device: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at_server: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    channel: Mapped[str] = mapped_column(String(20), default='app')
    relay_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    transmission_status: Mapped[str] = mapped_column(String(30), default='received')
    status: Mapped[str] = mapped_column(String(20), default='new')
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey('sos_events.id'), nullable=True)
    linked_need_id: Mapped[int | None] = mapped_column(ForeignKey('needs.id'), nullable=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey('assignments.id'), nullable=True)
    gateway_id: Mapped[int | None] = mapped_column(ForeignKey('gateways.id'), nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SyncBatch(Base):
    __tablename__ = 'sync_batches'
    __table_args__ = (
        CheckConstraint('count_received >= 0', name='ck_sync_batches_received'),
        CheckConstraint('count_new >= 0', name='ck_sync_batches_new'),
        CheckConstraint('count_duplicate >= 0', name='ck_sync_batches_duplicate'),
        CheckConstraint('count_rejected >= 0', name='ck_sync_batches_rejected'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gateway_id: Mapped[int | None] = mapped_column(ForeignKey('gateways.id'), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    count_received: Mapped[int] = mapped_column(Integer)
    count_new: Mapped[int] = mapped_column(Integer)
    count_duplicate: Mapped[int] = mapped_column(Integer)
    count_rejected: Mapped[int] = mapped_column(Integer, default=0)


class SOSAcknowledgement(Base):
    __tablename__ = 'sos_acknowledgements'

    id: Mapped[int] = mapped_column(primary_key=True)
    sos_id: Mapped[int] = mapped_column(ForeignKey('sos_events.id'))
    by_user: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)