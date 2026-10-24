from typing import Literal

from pydantic import BaseModel, Field


class ParsedNeed(BaseModel):
    category: Literal['rescue', 'medical', 'water', 'food', 'shelter', 'technical_repair', 'other']
    item: str = Field(min_length=1, max_length=500)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    required_skills: list[str] = Field(default_factory=list)


class ParsedReport(BaseModel):
    location_text: str | None = Field(default=None, max_length=240)
    families_affected: int | None = Field(default=None, ge=0)
    needs: list[ParsedNeed] = Field(default_factory=list)
    urgency: int = Field(default=3, ge=1, le=5)
    vulnerable_groups: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    language: str = Field(default='unknown', max_length=40)
    confidence: Literal['low', 'medium', 'high'] = 'low'


class CoordinatorDecision(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=800)
    confidence: Literal['low', 'medium', 'high'] = 'medium'
    rank: int | None = Field(default=None, ge=1)


class CoordinatorSelection(BaseModel):
    decisions: list[CoordinatorDecision] = Field(default_factory=list, max_length=20)


class SkillMapping(BaseModel):
    skills: list[str] = Field(default_factory=list)


class CandidateExplanationItem(BaseModel):
    volunteer_id: int
    reason: str = Field(min_length=1, max_length=500)


class CandidateExplanations(BaseModel):
    explanations: list[CandidateExplanationItem]


class DuplicateVerdict(BaseModel):
    same_event: bool
    confidence: str = Field(pattern='^(low|medium|high)$')
    rationale: str = Field(min_length=1, max_length=500)


class BottleneckExplanation(BaseModel):
    explanation: str = Field(min_length=1, max_length=800)
    suggested_action: str = Field(min_length=1, max_length=500)


class RecoveryNarrative(BaseModel):
    narrative: str = Field(min_length=1, max_length=1200)
    confidence: str = Field(pattern='^(low|medium|high)$')


class SOSInterpretation(BaseModel):
    category: str = Field(pattern='^(FOOD|MEDICINE|TRAPPED|RESCUE|OTHER)$')
    urgency: int = Field(ge=1, le=5)
    required_skills: list[str] = Field(default_factory=list)
