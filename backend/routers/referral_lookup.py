import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Referral
from models import ReferralConfirmAttendanceOut, ReferralLookupOut
from services import audit

router = APIRouter(prefix="/api", tags=["referral_lookup"])

# Master doc v6.0 Section 1.1/16.6 (14 August 2026) — the referral-code
# pivot. Both routes are unauthenticated: hospital staff have no dashboard
# login, same deliberate precedent as POST /api/screen and
# GET /api/workers/{phone} (see routers/auth.py's get_current_user
# docstring). Takudzwa builds the hospital-facing entry page in
# dashboard/ against this pair — the shape is documented in
# docs/API_CONTRACT.md.


# **Every lookup is recorded, hit or miss** (16.3; docs/SECURITY.md's threat
# table, where "all lookups logged" is a listed control and "no lookup log"
# was the state). This is the most exposed identified-data surface in the
# system: no login, and a six-character code space. Rate limiting and lockout
# are Phase Two, so until they exist the log is the only thing that makes
# enumeration *visible* -- a miss is recorded with `allowed=False`, which is
# what `GET /api/v2/audit/refusals` reads, so a walk through the code space
# shows up as a run of refusals rather than as nothing at all.
#
# Detection before prevention is the right order when prevention is deferred,
# and it is not free: an unauthenticated caller can grow this table one row
# per attempt. The row is small and `object_id` is capped at 64 characters,
# and the rate limit is what bounds it -- written down here so the trade-off
# is deliberate rather than discovered.


def _get_referral_by_code(db: Session, code: str, action: str) -> Referral:
    referral = db.scalar(select(Referral).where(Referral.referral_code == code))
    if referral is None:
        # On its own session and never raising: a 404 has no transaction to
        # join, and failing to log a miss must not turn a clean 404 into a
        # 500.
        audit.record_refusal(
            audit.FACILITY_LOOKUP, action, object_type="referral", object_id=code,
            details={"reason": "unknown referral code"},
        )
        raise HTTPException(status_code=404, detail="Unknown referral code")
    return referral


@router.get("/referrals/lookup/{code}", response_model=ReferralLookupOut)
def lookup_referral(code: str, db: Session = Depends(get_db)):
    referral = _get_referral_by_code(db, code, "referral.read")
    screening = referral.screening
    miner = referral.miner
    contributing_factors = (
        json.loads(screening.ai_contributing_factors) if screening.ai_contributing_factors else []
    )
    out = ReferralLookupOut(
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
    # Written after the response is built, so a row exists only for a read
    # that actually returned a record. `person_id` stays empty: this is a v1
    # referral keyed to a `miners` row and that column means a `persons` id,
    # which item 1.11 maps.
    audit.record(
        db, audit.FACILITY_LOOKUP, "referral.read",
        object_type="referral", object_id=referral.referral_code,
        details={"tier": screening.tier, "status": referral.status},
    )
    db.commit()
    return out


@router.post("/referrals/lookup/{code}/confirm-attendance", response_model=ReferralConfirmAttendanceOut)
def confirm_attendance(code: str, db: Session = Depends(get_db)):
    referral = _get_referral_by_code(db, code, "referral.attend")
    if referral.status in ("attended", "closed"):
        # Recorded as a refusal: a repeat confirmation is how a mistyped code
        # that happens to exist shows up, and this is the one write on this
        # surface that could be used to make a referral look completed.
        audit.record_refusal(
            audit.FACILITY_LOOKUP, "referral.attend", object_type="referral",
            object_id=referral.referral_code,
            details={"reason": f"already {referral.status}"},
        )
        raise HTTPException(
            status_code=409, detail=f"Referral already marked {referral.status}"
        )
    referral.status = "attended"
    referral.attended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # In the same transaction as the write it records: this is the fact the
    # headline metric is computed from, so the row and its log entry stand or
    # fall together.
    audit.record(
        db, audit.FACILITY_LOOKUP, "referral.attend",
        object_type="referral", object_id=referral.referral_code,
    )
    db.commit()
    db.refresh(referral)
    return ReferralConfirmAttendanceOut(
        referral_code=referral.referral_code,
        status=referral.status,
        attended_at=format_datetime(referral.attended_at),
    )
