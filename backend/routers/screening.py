import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from db_models import Miner, OutreachVisit, Screening, ScreeningAnswer
from models import DeteriorationResult, ScreeningCreate, ScreeningResult
from services import notifications
from services.advice_engine import personalised_advice_line
from services.ai_risk_engine import assess_risk
from services.deterioration import compare_to_previous, escalate_tier_if_worsened
from services.explanation_shona import personalised_explanation_shona
from services.outreach import match_active_visit
from services.referrals import create_referral_and_notify
from services.safety_overrides import apply_safety_overrides
from services.tier_messages import TIER_MESSAGES

router = APIRouter(prefix="/api", tags=["screening"])

# Worker registration/lookup lives in routers/workers.py (POST /api/workers,
# GET /api/workers/{phone}) — this router is screening only, as of 5 August
# 2026 (previously also had POST /api/miners).


@router.post("/screen", response_model=ScreeningResult)
def screen_miner(payload: ScreeningCreate, db: Session = Depends(get_db)):
    miner = db.get(Miner, payload.miner_id)
    if miner is None:
        raise HTTPException(status_code=404, detail="Miner not found")

    # Outreach Planner (5 August 2026): link this screening to a visit for
    # live screened_count tracking + the post-visit report. Explicit id is
    # trusted if it exists (never fail the screening over a bad reference —
    # same philosophy as "a failed AI call doesn't corrupt the screening
    # record"); otherwise infer it for APP-channel screenings via
    # services/outreach.py's match_active_visit. USSD self-screens never
    # auto-link — not a coordinated site visit.
    outreach_visit_id = None
    if payload.outreach_visit_id is not None:
        visit = db.get(OutreachVisit, payload.outreach_visit_id)
        outreach_visit_id = visit.id if visit else None
    elif payload.channel == "APP" and miner.mine_site:
        candidate_visits = db.scalars(
            select(OutreachVisit).where(func.lower(OutreachVisit.site) == miner.mine_site.lower())
        ).all()
        # match_active_visit() is pure dict-subscript logic (services/outreach.py)
        # — pass plain dicts rather than changing that module to expect ORM
        # attribute access, same reasoning as facility_matching's dict interface.
        candidate_dicts = [
            {"id": v.id, "site": v.site, "scheduled_date": v.scheduled_date} for v in candidate_visits
        ]
        matched_visit = match_active_visit(
            miner.mine_site, datetime.now(timezone.utc), candidate_dicts
        )
        outreach_visit_id = matched_visit["id"] if matched_visit else None

    # Most recent prior screening for this worker, if any.
    previous_screening = db.scalar(
        select(Screening)
        .where(Screening.miner_id == payload.miner_id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(1)
    )
    previous_screening_id = previous_screening.id if previous_screening else None
    provisional = 1 if payload.offline_fallback_used else 0

    # Answers from that previous screening, for Longitudinal Deterioration
    # Detection. Empty list (not an error) if this is the worker's first.
    previous_answer_dicts = (
        [
            {"question_code": a.question_code, "answer_score": a.answer_score}
            for a in db.scalars(
                select(ScreeningAnswer).where(ScreeningAnswer.screening_id == previous_screening_id)
            ).all()
        ]
        if previous_screening_id
        else []
    )

    screening = Screening(
        miner_id=payload.miner_id,
        previous_screening_id=previous_screening_id,
        screened_by=payload.screened_by,
        channel=payload.channel,
        fallback_used=1 if payload.offline_fallback_used else 0,
        provisional=provisional,
        outreach_visit_id=outreach_visit_id,
    )
    db.add(screening)
    db.flush()  # need screening.id for the answers below, before commit

    if outreach_visit_id is not None:
        visit = db.get(OutreachVisit, outreach_visit_id)
        visit.screened_count = (visit.screened_count or 0) + 1

    for answer in payload.answers:
        db.add(
            ScreeningAnswer(
                screening_id=screening.id,
                question_code=answer.question_code,
                question_text=answer.question_text,
                answer_value=answer.answer_value,
                answer_score=answer.answer_score,
            )
        )
    db.commit()

    try:
        result = assess_risk(payload.answers)
    except Exception:
        # screening_id + answers are already saved for audit purposes;
        # risk fields stay NULL until a retry succeeds.
        raise HTTPException(status_code=502, detail="AI risk engine unavailable, please retry")

    # Longitudinal Deterioration Detection: escalate one tier on any
    # adverse trajectory, before the hard safety override gets the final
    # word — see services/deterioration.py and services/safety_overrides.py.
    deterioration = compare_to_previous(payload.answers, previous_screening_id, previous_answer_dicts)
    result["tier"] = escalate_tier_if_worsened(result["tier"], deterioration["changed"])
    result = apply_safety_overrides(payload.answers, result)

    advice_line = personalised_advice_line(payload.answers)
    explanation_shona = personalised_explanation_shona(payload.answers)

    screening.tier = result["tier"]
    screening.risk_confidence = result["confidence"]
    screening.ai_explanation_english = result["explanation_english"]
    screening.ai_explanation_shona = explanation_shona
    screening.ai_contributing_factors = json.dumps(result["contributing_factors"])
    screening.advice_line = advice_line
    db.commit()

    # Result notification, per tier (CLAUDE.md: "Everyone receives their
    # result... by SMS"). ORANGE/RED go through create_referral_and_notify
    # (referral + facility match + hospital pre-alert + miner SMS);
    # GREEN/YELLOW never get a referral but still get a result-only SMS —
    # see services/notifications.send_screening_result_sms.
    shona_message = TIER_MESSAGES[result["tier"]][0]
    if result["tier"] in ("ORANGE", "RED"):
        create_referral_and_notify(
            db,
            screening_id=screening.id,
            miner_id=payload.miner_id,
            miner_name=miner.name,
            phone_number=miner.phone,
            mine_site=miner.mine_site,
            tier=result["tier"],
            shona_message=shona_message,
            contributing_factors=result["contributing_factors"],
        )
    else:
        notifications.send_screening_result_sms(payload.miner_id, miner.phone, result["tier"], shona_message)

    return ScreeningResult(
        tier=result["tier"],
        confidence=result["confidence"],
        explanation_english=result["explanation_english"],
        explanation_shona=explanation_shona,
        contributing_factors=result["contributing_factors"],
        advice_line=advice_line,
        previous_screening_id=previous_screening_id,
        provisional=bool(provisional),
        deterioration=DeteriorationResult(**deterioration),
    )
