import json

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import DeteriorationResult, ScreeningCreate, ScreeningResult
from services.advice_engine import personalised_advice_line
from services.ai_risk_engine import assess_risk
from services.deterioration import compare_to_previous, escalate_tier_if_worsened
from services.referrals import GENERIC_REFERRAL_SHONA_MESSAGE, create_referral_and_notify
from services.safety_overrides import apply_safety_overrides

router = APIRouter(prefix="/api", tags=["screening"])

# Worker registration/lookup lives in routers/workers.py (POST /api/workers,
# GET /api/workers/{phone}) — this router is screening only, as of 5 August
# 2026 (previously also had POST /api/miners).


@router.post("/screen", response_model=ScreeningResult)
def screen_miner(payload: ScreeningCreate):
    conn = get_connection()
    try:
        miner_row = conn.execute(
            "SELECT id FROM miners WHERE id = ?", (payload.miner_id,)
        ).fetchone()
        if miner_row is None:
            raise HTTPException(status_code=404, detail="Miner not found")

        # Most recent prior screening for this worker, if any — just the link;
        # actual trajectory comparison (Longitudinal Deterioration Detection)
        # is not built yet.
        previous_row = conn.execute(
            """SELECT id FROM screenings WHERE miner_id = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (payload.miner_id,),
        ).fetchone()
        previous_screening_id = previous_row["id"] if previous_row else None
        provisional = 1 if payload.offline_fallback_used else 0

        # Answers from that previous screening, for Longitudinal Deterioration
        # Detection. Empty list (not an error) if this is the worker's first.
        previous_answer_rows = (
            conn.execute(
                "SELECT question_code, answer_score FROM screening_answers WHERE screening_id = ?",
                (previous_screening_id,),
            ).fetchall()
            if previous_screening_id
            else []
        )

        cur = conn.execute(
            """INSERT INTO screenings
                 (miner_id, previous_screening_id, screened_by, channel, fallback_used, provisional)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                payload.miner_id,
                previous_screening_id,
                payload.screened_by,
                payload.channel,
                1 if payload.offline_fallback_used else 0,
                provisional,
            ),
        )
        screening_id = cur.lastrowid

        for answer in payload.answers:
            conn.execute(
                """INSERT INTO screening_answers
                   (screening_id, question_code, question_text, answer_value, answer_score)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    screening_id,
                    answer.question_code,
                    answer.question_text,
                    answer.answer_value,
                    answer.answer_score,
                ),
            )
        conn.commit()

        try:
            result = assess_risk(payload.answers)
        except Exception:
            # screening_id + answers are already saved for audit purposes;
            # risk fields stay NULL until a retry succeeds.
            raise HTTPException(
                status_code=502, detail="AI risk engine unavailable, please retry"
            )

        # Longitudinal Deterioration Detection: escalate one tier on any
        # adverse trajectory, before the hard safety override gets the final
        # word — see services/deterioration.py and services/safety_overrides.py.
        deterioration = compare_to_previous(
            payload.answers, previous_screening_id, previous_answer_rows
        )
        result["tier"] = escalate_tier_if_worsened(result["tier"], deterioration["changed"])
        result = apply_safety_overrides(payload.answers, result)

        advice_line = personalised_advice_line(payload.answers)

        conn.execute(
            """UPDATE screenings SET
                 tier = ?, risk_confidence = ?,
                 ai_explanation_english = ?, ai_contributing_factors = ?,
                 advice_line = ?
               WHERE id = ?""",
            (
                result["tier"],
                result["confidence"],
                result["explanation_english"],
                json.dumps(result["contributing_factors"]),
                advice_line,
                screening_id,
            ),
        )
        conn.commit()

        if result["tier"] in ("ORANGE", "RED"):
            miner = conn.execute(
                "SELECT name, phone, mine_site FROM miners WHERE id = ?",
                (payload.miner_id,),
            ).fetchone()
            create_referral_and_notify(
                conn,
                screening_id=screening_id,
                miner_id=payload.miner_id,
                miner_name=miner["name"],
                phone_number=miner["phone"],
                mine_site=miner["mine_site"],
                tier=result["tier"],
                shona_message=GENERIC_REFERRAL_SHONA_MESSAGE,
                contributing_factors=result["contributing_factors"],
            )

        return ScreeningResult(
            tier=result["tier"],
            confidence=result["confidence"],
            explanation_english=result["explanation_english"],
            contributing_factors=result["contributing_factors"],
            advice_line=advice_line,
            previous_screening_id=previous_screening_id,
            provisional=bool(provisional),
            deterioration=DeteriorationResult(**deterioration),
        )
    finally:
        conn.close()


