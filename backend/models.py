from typing import List, Optional

from pydantic import BaseModel, Field


class WorkerCreate(BaseModel):
    name: str
    phone: str
    site: Optional[str] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    phone: str
    site: Optional[str] = None


class WorkerScreeningSummary(BaseModel):
    id: int
    tier: Optional[str] = None
    created_at: str
    advice_line: Optional[str] = None


class WorkerDetail(BaseModel):
    id: int
    name: str
    phone: str
    site: Optional[str] = None
    screenings: List[WorkerScreeningSummary]


class ScreeningAnswerIn(BaseModel):
    question_code: str
    question_text: Optional[str] = None
    answer_value: str
    answer_score: int


class ScreeningCreate(BaseModel):
    miner_id: int
    answers: List[ScreeningAnswerIn] = Field(..., min_length=1)
    channel: str = "APP"
    screened_by: Optional[str] = None
    offline_fallback_used: bool = False
    outreach_visit_id: Optional[int] = None


class DeteriorationResult(BaseModel):
    compared_to_screening_id: Optional[int] = None
    changed: bool
    summary: str


class ScreeningResult(BaseModel):
    tier: str
    confidence: float
    explanation_english: str
    explanation_shona: str
    contributing_factors: List[str]
    advice_line: Optional[str] = None
    previous_screening_id: Optional[int] = None
    provisional: bool = False
    deterioration: Optional[DeteriorationResult] = None


class ReferralOut(BaseModel):
    id: int
    miner_name: str
    mine_site: Optional[str] = None
    tier: str
    status: str
    deadline: Optional[str] = None
    pre_alert_sent: bool
    facility_id: Optional[int] = None
    facility_name: Optional[str] = None
    reminder_stage: int = 0
    attended_at: Optional[str] = None
    closed_at: Optional[str] = None
    created_at: str


class ReferralStatusUpdate(BaseModel):
    status: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str


class OutreachVisitCreate(BaseModel):
    site: str
    scheduled_date: str  # "YYYY-MM-DD"
    expected_headcount: int
    health_workers: List[str] = []


class ReferralListItem(BaseModel):
    miner_name: str
    tier: str
    status: str


class OutreachVisitOut(BaseModel):
    id: int
    site: str
    scheduled_date: str
    expected_headcount: int
    screened_count: int
    report_generated: bool
    tier_distribution: Optional[dict] = None
    referral_list: Optional[List[ReferralListItem]] = None
