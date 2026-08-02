import json
import sqlite3

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import MinerCreate, MinerOut, ScreeningCreate, ScreeningResult
from services.ai_risk_engine import assess_risk
from services.referrals import GENERIC_REFERRAL_SHONA_MESSAGE, create_referral_and_notify

router = APIRouter(prefix="/api", tags=["screening"])


@router.post("/miners", response_model=MinerOut)
def create_miner(miner: MinerCreate):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
            (miner.name, miner.phone, miner.mine_site),
        )
        conn.commit()
        return MinerOut(
            id=cur.lastrowid,
            name=miner.name,
            phone=miner.phone,
            mine_site=miner.mine_site,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Phone number already registered")
    finally:
        conn.close()


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

        conn.execute(
            """UPDATE screenings SET
                 tier = ?, risk_confidence = ?,
                 ai_explanation_english = ?, ai_contributing_factors = ?
               WHERE id = ?""",
            (
                result["tier"],
                result["confidence"],
                result["explanation_english"],
                json.dumps(result["contributing_factors"]),
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
            advice_line=None,
            previous_screening_id=previous_screening_id,
            provisional=bool(provisional),
        )
    finally:
        conn.close()


