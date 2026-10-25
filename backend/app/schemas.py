from enum import Enum
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ContributionCreate(BaseModel):
    donor_name: str = Field(min_length=1, max_length=120)
    is_anonymous: bool = False
    amount_npr: float = Field(gt=0, le=100000000)
    txn_id: str = Field(min_length=3, max_length=80)
    channel: str = Field(pattern='^(esewa|khalti|bank|other)$')


class UserRole(str, Enum):
    community_member = 'community_member'
    volunteer = 'volunteer'
    org_admin = 'org_admin'
    coordinator = 'coordinator'
    admin = 'admin'


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('full_name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Full name cannot be blank')
        return value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    organization_id: int | None = None
    is_active: bool

    model_config = {'from_attributes': True}


class EmergencyContact(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=3, max_length=40)
    priority: int = Field(default=1, ge=1, le=5)
    share_location: bool = True
    consent_to_notify: bool = True


class UserProfileRead(BaseModel):
    phone_number: str | None = None
    address: dict | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_accuracy_m: float | None = None
    emergency_contacts: list[EmergencyContact] = Field(default_factory=list)
    profile_notes: str | None = None


class UserProfilePatch(BaseModel):
    phone_number: str | None = Field(default=None, max_length=40)
    address: dict | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100000)
    emergency_contacts: list[EmergencyContact] = Field(default_factory=list, max_length=5)
    profile_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def validate_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be provided together')
        if self.address is not None:
            allowed = {'district', 'city', 'ward', 'road', 'landmark'}
            unknown = set(self.address) - allowed
            if unknown:
                raise ValueError(f'Unsupported address fields: {sorted(unknown)}')
            self.address = {
                key: str(value).strip()
                for key, value in self.address.items()
                if str(value).strip()
            }
        return self


class HelpOfferCreate(BaseModel):
    category: str = Field(pattern='^(water|food|medicine|shelter|transport|skill|other)$')
    description: str = Field(min_length=3, max_length=1000)
    quantity: float = Field(gt=0, le=1000000)
    unit: str = Field(min_length=1, max_length=40)
    location_text: str = Field(min_length=2, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode='after')
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be provided together')
        return self


class ReportCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    channel: str = Field(pattern='^(app|sms|mesh|web)$')
    client_uuid: UUID
    incident_id: int | None = None
    location_id: int | None = None
    sender_ref: str | None = Field(default=None, max_length=160)


class NeedPatch(BaseModel):
    category: str | None = Field(
        default=None,
        pattern='^(rescue|medical|water|food|shelter|technical_repair|other)$',
    )
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    required_skills: list[str] | None = None
    required_equipment: list[str] | None = None
    preferred_languages: list[str] | None = None
    quantity_requested: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    urgency: int | None = Field(default=None, ge=1, le=5)
    vulnerable_groups: list[str] | None = None
    verification_status: str | None = Field(default=None, pattern='^(unverified|verified|rejected)$')
    confidence: str | None = Field(default=None, pattern='^(low|medium|high)$')

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError('At least one field must be provided')
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Need fields cannot be null')
        return self


class CoordinateRequest(BaseModel):
    incident_id: int = Field(gt=0)
    client_uuid: UUID


class VolunteerProfileCreate(BaseModel):
    contact_info: str | None = Field(default=None, max_length=240)
    organization_id: int | None = None
    base_location_id: int | None = None
    max_travel_km: float = Field(default=50, gt=0, le=1000)
    willing_to_relocate: bool = False
    languages: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)


class VolunteerProfilePatch(BaseModel):
    contact_info: str | None = Field(default=None, max_length=240)
    organization_id: int | None = None
    base_location_id: int | None = None
    max_travel_km: float | None = Field(default=None, gt=0, le=1000)
    availability_status: str | None = Field(
        default=None,
        pattern='^(available|assigned|unavailable|off_duty)$',
    )
    willing_to_relocate: bool | None = None
    languages: list[str] | None = None
    equipment: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VolunteerSkillCreate(BaseModel):
    skill_id: int
    level: int = Field(default=1, ge=1, le=5)
    certification_name: str | None = Field(default=None, max_length=160)
    certificate_ref: str | None = Field(default=None, max_length=240)


class VolunteerSkillRead(BaseModel):
    skill_id: int
    name: str
    category: str
    level: int
    certification_name: str | None
    certificate_ref: str | None
    verified: bool


class VolunteerProfileRead(BaseModel):
    contact_info: str | None = None
    id: int
    user_id: int
    full_name: str
    organization_id: int | None
    base_location_id: int | None
    max_travel_km: float
    availability_status: str
    willing_to_relocate: bool
    languages: list[str]
    equipment: list[str]
    notes: str | None
    skills: list[VolunteerSkillRead]


class AvailabilityWindowInput(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def validate_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('ends_at must be later than starts_at')
        return self


class VolunteerAvailabilityPatch(BaseModel):
    status: str = Field(pattern='^(available|assigned|unavailable|off_duty)$')
    windows: list[AvailabilityWindowInput] | None = None


class RoadBlockageCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=0.25, gt=0, le=5)
    expires_in_hours: float = Field(default=12, gt=0, le=168)
    notes: str | None = Field(default=None, max_length=1000)


class RoadUpdateCreate(BaseModel):
    client_uuid: UUID
    text: str = Field(min_length=1, max_length=4000)


class RoadBlockageVerificationItem(BaseModel):
    update_index: int = Field(ge=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=0.25, gt=0, le=5)
    expires_in_hours: float = Field(default=12, gt=0, le=168)


class RoadUpdateVerification(BaseModel):
    updates: list[RoadBlockageVerificationItem] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def validate_unique_update_indices(self):
        indexes = [item.update_index for item in self.updates]
        if len(indexes) != len(set(indexes)):
            raise ValueError('update_index values must be unique')
        return self


class RouteComputeRequest(BaseModel):
    from_latitude: float = Field(ge=-90, le=90)
    from_longitude: float = Field(ge=-180, le=180)
    to_latitude: float = Field(ge=-90, le=90)
    to_longitude: float = Field(ge=-180, le=180)


class MatchRequest(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode='after')
    def validate_task_window(self):
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError('starts_at and ends_at must be provided together')
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError('ends_at must be later than starts_at')
        return self


class CoordinationRunCreate(BaseModel):
    client_uuid: UUID
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode='after')
    def validate_window(self):
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError('starts_at and ends_at must be provided together')
        if self.starts_at is not None and self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError('ends_at must be later than starts_at')
        return self


class AssignmentCreate(BaseModel):
    need_id: int
    volunteer_id: int
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AssignmentStatusUpdate(BaseModel):
    status: str = Field(pattern='^(en_route|on_site|cancelled)$')


class AssignmentComplete(BaseModel):
    completion_criteria_met: bool
    outcome_notes: str | None = Field(default=None, max_length=2000)


class ResourceStockCreate(BaseModel):
    resource_id: int
    organization_id: int | None = None
    location_id: int | None = None
    quantity_available: float = Field(gt=0)


class ResourceAllocationCreate(BaseModel):
    need_id: int
    stock_id: int
    quantity: float = Field(gt=0)
    client_uuid: UUID | None = None


class AllocationProposalCreate(BaseModel):
    client_uuid: UUID


class MovementStatusPatch(BaseModel):
    status: str = Field(pattern='^(dispatched|delivered)$')


class DeliveryConfirmationCreate(BaseModel):
    client_uuid: UUID
    status: str = Field(pattern='^(full|partial|not_received)$')
    quantity_received: float = Field(ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class BottleneckStatusPatch(BaseModel):
    status: str = Field(pattern='^(acknowledged|resolved)$')


class DamageAssessmentCreate(BaseModel):
    kind: str = Field(pattern='^(pre|post)$')
    damage_level: int = Field(ge=0, le=5)
    details: str = Field(min_length=1, max_length=4000)
    evidence_ref: str | None = Field(default=None, max_length=300)


class SOSCategory(str, Enum):
    FOOD = 'FOOD'
    MEDICINE = 'MEDICINE'
    TRAPPED = 'TRAPPED'
    RESCUE = 'RESCUE'
    OTHER = 'OTHER'


class SOSAddress(BaseModel):
    district: str = Field(default='', max_length=80)
    city: str = Field(default='', max_length=100)
    ward: str = Field(default='', max_length=20)
    road: str = Field(default='', max_length=120)
    landmark: str = Field(default='', max_length=180)

    model_config = {'str_strip_whitespace': True, 'extra': 'forbid'}


class SOSLocationUpdate(BaseModel):
    latitude: float = Field(alias='lat', ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(alias='lon', ge=-180, le=180, allow_inf_nan=False)
    location_accuracy_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    model_config = {'populate_by_name': True}


class SOSEventCreate(BaseModel):
    client_uuid: UUID
    incident_id: int | None = None
    sender_ref: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, alias='lat', ge=-90, le=90)
    longitude: float | None = Field(default=None, alias='lon', ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0)
    category: SOSCategory | None = None
    urgency: int | None = Field(default=None, ge=1, le=5)
    message: str = Field(min_length=1, max_length=500)
    created_at_device: datetime | None = None
    channel: str = Field(default='app', pattern='^(app|mesh|sms|gateway)$')
    relay_path: list[str] = Field(default_factory=list, max_length=20)
    address: SOSAddress | None = None

    model_config = {'populate_by_name': True}


class SOSBatchCreate(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=100)


class SMSIncomingCreate(BaseModel):
    sender_phone: str = Field(min_length=3, max_length=40)
    text: str = Field(min_length=1, max_length=2000)
    client_uuid: UUID | None = None
    incident_id: int | None = None
    created_at_device: datetime | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    channel: str = Field(default='sms', pattern='^(sms|mesh)$')


class GatewayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gateway_type: str = Field(pattern='^(meshtastic|sms|app)$')


class SOSDispatch(BaseModel):
    assignment_id: int


class SOSResolve(BaseModel):
    status: str = Field(pattern='^(resolved|false_alarm)$')
    notes: str | None = Field(default=None, max_length=1000)


class SOSStateUpdate(BaseModel):
    state: str = Field(
        pattern='^(received|acknowledged|verified|awaiting_dispatch|assigned|'
        'responding|on_scene|resolved|cancelled)$'
    )
    notes: str | None = Field(default=None, max_length=1000)