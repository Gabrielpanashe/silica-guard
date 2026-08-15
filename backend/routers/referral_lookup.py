import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Referral
from models import ReferralConfirmAttendanceOut, ReferralLookupOut

router = APIRouter(prefix="/api", tags=["referral_lookup"])

# Master doc v6.0 Section 1.1/16.6 (14 August 2026) — the referral-code
# pivot. Both routes are unauthenticated: hospital staff have no dashboard
# login, same deliberate precedent as POST /api/screen and
# GET /api/workers/{phone} (see routers/auth.py's get_current_user
# docstring). Takudzwa builds the hospital-facing entry page in
# dashboard/ against this pair — the shape is documented in
# docs/API_CONTRACT.md.


def _get_referral_by_code(db: Session, code: str) -> Referral:
    referral = db.scalar(select(Referral).where(Referral.referral_code == code))
    if referral is None:
        raise HTTPException(status_code=404, detail="Unknown referral code")
    return referral


@router.get("/referrals/lookup/{code}", response_model=ReferralLookupOut)
def lookup_referral(code: str, db: Session = Depends(get_db)):
    referral = _get_referral_by_code(db, code)
    screening = referral.screening
    miner = referral.miner
    contributing_factors = (
        json.loads(screening.ai_contributing_factors) if screening.ai_contributing_factors else []
    )
    return ReferralLookupOut(
        referral_code=referral.referral_code,
        tier=screening.tier,
        status=referral.status,
        deadline=format_datetime(referral.deadline),
        miner_name=miner.name,
        mine_site=miner.mine_site,
        facility_name=referral.facility.name if referral.facility else referral.hospital,
        advice_line=screening.advice_line,
        contributing_factors=contributing_factors,
        attended_at=format_datetime(referral.attended_at),
    )


@router.post("/referrals/lookup/{code}/confirm-attendance", response_model=ReferralConfirmAttendanceOut)
def confirm_attendance(code: str, db: Session = Depends(get_db)):
    referral = _get_referral_by_code(db, code)
    if referral.status in ("attended", "closed"):
        raise HTTPException(
            status_code=409, detail=f"Referral already marked {referral.status}"
        )
    referral.status = "attended"
    referral.attended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(referral)
    return ReferralConfirmAttendanceOut(
        referral_code=referral.referral_code,
        status=referral.status,
        attended_at=format_datetime(referral.attended_at),
    )
