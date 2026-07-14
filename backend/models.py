from typing import List, Optional

from pydantic import BaseModel, Field


class MinerCreate(BaseModel):
    name: str
    phone: str
    mine_site: Optional[str] = None


class MinerOut(BaseModel):
    id: int
    name: str
    phone: str
    mine_site: Optional[str] = None


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


class ScreeningResult(BaseModel):
    risk_level: str
    confidence: float
    explanation_english: str
    contributing_factors: List[str]


class ReferralOut(BaseModel):
    id: int
    miner_name: str
    mine_site: Optional[str] = None
    risk_level: str
    status: str
    created_at: str


class ReferralStatusUpdate(BaseModel):
    status: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
