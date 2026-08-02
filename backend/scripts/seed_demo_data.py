"""
Seeds a reproducible demo dataset: multiple mine sites, a spread of risk
tiers, referrals in different lifecycle states, and one worker with two
screenings (a WATCH followed later by a REFER_NOW, for demoing the
deterioration story once that engine exists).

Safe to re-run: clears the miners/screenings/screening_answers/referrals
tables first, so running this twice reproduces the same known state rather
than duplicating rows or hitting the UNIQUE(phone) constraint.

Inserts screenings with pre-computed risk results directly — it does not
call the live Gemini risk engine, so it needs no GEMINI_API_KEY. It also
never calls services.notifications, so it needs no Africa's Talking key
either; referral rows are inserted directly with pre_alert_sent set to
reflect a plausible outcome rather than an actual SMS send.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/seed_demo_data.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_connection, init_db  # noqa: E402
from questions import SCREENING_QUESTIONS  # noqa: E402

# Option index (0-based) per question, in SCREENING_QUESTIONS order, per profile.
LOW_PROFILE = [0, 3, 0, 0, 0, 0, 0, 0, 0, 0]
WATCH_PROFILE = [2, 0, 1, 1, 0, 1, 0, 0, 0, 0]
REFER_NOW_PROFILE = [3, 0, 2, 3, 2, 2, 2, 2, 2, 1]

_now = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _answers_for(profile: list[int]) -> list[dict]:
    answers = []
    for question, option_index in zip(SCREENING_QUESTIONS, profile):
        option = question["options"][option_index]
        answers.append(
            {
                "question_code": question["code"],
                "question_text": question["shona"],
                "answer_value": option["value"],
                "answer_score": option["score"],
            }
        )
    return answers


def _insert_worker(conn, name: str, phone: str, mine_site: str) -> int:
    cur = conn.execute(
        "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
        (name, phone, mine_site),
    )
    return cur.lastrowid


def _insert_screening(
    conn,
    miner_id: int,
    profile: list[int],
    risk_level: str,
    confidence: float,
    explanation_english: str,
    contributing_factors: list[str],
    channel: str,
    screened_by: str,
    created_at: datetime,
) -> int:
    import json

    cur = conn.execute(
        """INSERT INTO screenings
           (miner_id, screened_by, channel, risk_level, risk_confidence,
            ai_explanation_english, ai_contributing_factors, fallback_used,
            synced, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1, ?)""",
        (
            miner_id,
            screened_by,
            channel,
            risk_level,
            confidence,
            explanation_english,
            json.dumps(contributing_factors),
            _iso(created_at),
        ),
    )
    screening_id = cur.lastrowid

    for answer in _answers_for(profile):
        conn.execute(
            """INSERT INTO screening_answers
               (screening_id, question_code, question_text, answer_value, answer_score)
               VALUES (?, ?, ?, ?, ?)""",
            (
                screening_id,
                answer["question_code"],
                answer["question_text"],
                answer["answer_value"],
                answer["answer_score"],
            ),
        )
    return screening_id


def _insert_referral(
    conn,
    screening_id: int,
    miner_id: int,
    status: str,
    pre_alert_sent: bool,
    created_at: datetime,
    completed_at: datetime | None = None,
) -> None:
    conn.execute(
        """INSERT INTO referrals
           (screening_id, miner_id, hospital, pre_alert_sent, status, created_at, completed_at)
           VALUES (?, ?, 'Kwekwe District Hospital', ?, ?, ?, ?)""",
        (
            screening_id,
            miner_id,
            1 if pre_alert_sent else 0,
            status,
            _iso(created_at),
            _iso(completed_at) if completed_at else None,
        ),
    )


def seed() -> None:
    init_db()
    conn = get_connection()
    try:
        # Clear in FK-dependency order so this is safe to re-run from any state.
        conn.execute("DELETE FROM referrals")
        conn.execute("DELETE FROM screening_answers")
        conn.execute("DELETE FROM screenings")
        conn.execute("DELETE FROM miners")
        conn.commit()

        # --- Farai Ncube — Sherwood Mine — LOW, single screening ---
        farai_id = _insert_worker(conn, "Farai Ncube", "+263771000002", "Sherwood Mine")
        _insert_screening(
            conn,
            farai_id,
            LOW_PROFILE,
            "LOW",
            0.91,
            "Minimal exposure, consistent N95 use, no symptoms reported.",
            ["under 2 years exposure", "always wears N95"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=12),
        )

        # --- Blessing Sithole — Globe & Phoenix Mine — WATCH, single screening ---
        blessing_id = _insert_worker(
            conn, "Blessing Sithole", "+263771000003", "Globe & Phoenix Mine"
        )
        _insert_screening(
            conn,
            blessing_id,
            WATCH_PROFILE,
            "WATCH",
            0.78,
            "Moderate exposure with inconsistent dust suppression and mild breathlessness on exertion.",
            ["5-10 years drilling", "inconsistent wet drilling", "moderate breathlessness"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=20),
        )

        # --- Tapiwa Gumbo — Globe & Phoenix Mine — REFER_NOW, referral COMPLETE ---
        tapiwa_id = _insert_worker(
            conn, "Tapiwa Gumbo", "+263771000004", "Globe & Phoenix Mine"
        )
        tapiwa_screening_id = _insert_screening(
            conn,
            tapiwa_id,
            REFER_NOW_PROFILE,
            "REFER_NOW",
            0.95,
            "Over 10 years of dry drilling with severe cough, chest pain and a current TB diagnosis.",
            ["10+ years exposure", "dry drilling", "current TB", "severe chest pain"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=25),
        )
        _insert_referral(
            conn,
            tapiwa_screening_id,
            tapiwa_id,
            "COMPLETE",
            pre_alert_sent=True,
            created_at=_now - timedelta(days=25),
            completed_at=_now - timedelta(days=18),
        )

        # --- Nyasha Chitiyo — Kwekwe Consolidated — REFER_NOW, referral PENDING ---
        nyasha_id = _insert_worker(
            conn, "Nyasha Chitiyo", "+263771000005", "Kwekwe Consolidated"
        )
        nyasha_screening_id = _insert_screening(
            conn,
            nyasha_id,
            REFER_NOW_PROFILE,
            "REFER_NOW",
            0.93,
            "Severe breathlessness at rest with a prior lung diagnosis — urgent referral triggered.",
            ["severe breathlessness", "prior lung diagnosis", "no PPE"],
            "USSD",
            "USSD_SELF",
            _now - timedelta(days=2),
        )
        _insert_referral(
            conn,
            nyasha_screening_id,
            nyasha_id,
            "PENDING",
            pre_alert_sent=True,
            created_at=_now - timedelta(days=2),
        )

        # --- Rutendo Marufu — Kwekwe Consolidated — LOW, single screening ---
        rutendo_id = _insert_worker(
            conn, "Rutendo Marufu", "+263771000006", "Kwekwe Consolidated"
        )
        _insert_screening(
            conn,
            rutendo_id,
            LOW_PROFILE,
            "LOW",
            0.89,
            "Minimal exposure, no symptoms.",
            ["under 2 years exposure"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=5),
        )

        # --- Tendai Moyo — Sherwood Mine — WATCH then REFER_NOW (two screenings) ---
        tendai_id = _insert_worker(conn, "Tendai Moyo", "+263771000001", "Sherwood Mine")
        _insert_screening(
            conn,
            tendai_id,
            WATCH_PROFILE,
            "WATCH",
            0.80,
            "Moderate exposure, no symptoms yet — worth monitoring.",
            ["5-10 years drilling", "inconsistent PPE use"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=120),
        )
        tendai_second_id = _insert_screening(
            conn,
            tendai_id,
            REFER_NOW_PROFILE,
            "REFER_NOW",
            0.94,
            "Marked deterioration since last screening: new severe cough, chest pain and breathlessness.",
            ["10+ years exposure", "new severe symptoms since last screening"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=1),
        )
        _insert_referral(
            conn,
            tendai_second_id,
            tendai_id,
            "PENDING",
            pre_alert_sent=True,
            created_at=_now - timedelta(days=1),
        )

        conn.commit()

        counts = {
            "miners": conn.execute("SELECT COUNT(*) FROM miners").fetchone()[0],
            "screenings": conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0],
            "referrals": conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0],
        }
        print(f"Seeded: {counts['miners']} miners, {counts['screenings']} screenings, "
              f"{counts['referrals']} referrals across 3 sites.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
