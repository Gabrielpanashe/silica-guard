import json
import sqlite3

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import MinerCreate, MinerOut, ScreeningCreate, ScreeningResult
from services.ai_risk_engine import assess_risk

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

        cur = conn.execute(
            """INSERT INTO screenings (miner_id, screened_by, channel, fallback_used)
               VALUES (?, ?, ?, ?)""",
            (
                payload.miner_id,
                payload.screened_by,
                payload.channel,
                1 if payload.offline_fallback_used else 0,
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

        result = assess_risk(payload.answers)

        conn.execute(
            """UPDATE screenings SET
                 risk_level = ?, risk_confidence = ?,
                 ai_explanation_shona = ?, ai_explanation_english = ?,
                 ai_contributing_factors = ?
               WHERE id = ?""",
            (
                result["risk_level"],
                result["confidence"],
                result["explanation_shona"],
                result["explanation_english"],
                json.dumps(result["contributing_factors"]),
                screening_id,
            ),
        )
        conn.commit()

        return ScreeningResult(
            risk_level=result["risk_level"],
            confidence=result["confidence"],
            explanation_shona=result["explanation_shona"],
            explanation_english=result["explanation_english"],
            contributing_factors=result["contributing_factors"],
        )
    finally:
        conn.close()
