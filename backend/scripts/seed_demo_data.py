"""
Seeds a reproducible demo dataset: multiple mine sites, all four risk tiers,
referrals across different lifecycle states, one worker with two screenings
(a YELLOW followed later by a RED, for demoing the deterioration story once
that engine exists), and a starter row in the facilities and outreach_visits
tables so there is something to look at even though no endpoints read/write
outreach_visits yet. (The employers/campaigns tables and their seed rows
were removed 5 August 2026 — SilicaGuard is artisanal-miner-only now, see
SILICAGUARD.md Section 13.)

Safe to re-run: clears every table this script owns first, so running it
twice reproduces the same known state rather than duplicating rows or
hitting the UNIQUE(phone) constraint.

Inserts screenings with pre-computed tiers directly — it does not call the
live Gemini risk engine, so it needs no GEMINI_API_KEY. It also never calls
services.notifications, so it needs no Africa's Talking key either;
referral rows are inserted directly with pre_alert_sent/status set to
reflect a plausible outcome rather than an actual SMS send.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/seed_demo_data.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_connection, init_db  # noqa: E402
from questions import SCREENING_QUESTIONS  # noqa: E402

# Option index (0-based) per question, in SCREENING_QUESTIONS order, per tier profile.
GREEN_PROFILE = [0, 3, 0, 0, 0, 0, 0, 0, 0, 0]
YELLOW_PROFILE = [2, 0, 1, 1, 0, 1, 0, 0, 0, 0]
# Score >= 12, no hard safety trigger touched -> ORANGE (see services/referrals.py).
ORANGE_PROFILE = [3, 0, 2, 0, 0, 0, 0, 0, 0, 0]
# Touches every hard safety trigger (severe breathlessness/chest pain, current
# TB, prior lung diagnosis) -> RED regardless of score.
RED_PROFILE = [3, 0, 2, 3, 2, 2, 2, 2, 2, 1]

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
    tier: str,
    confidence: float,
    explanation_english: str,
    contributing_factors: list[str],
    channel: str,
    screened_by: str,
    created_at: datetime,
    previous_screening_id: int | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO screenings
           (miner_id, previous_screening_id, screened_by, channel, tier,
            risk_confidence, ai_explanation_english, ai_contributing_factors,
            provisional, fallback_used, synced, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1, ?)""",
        (
            miner_id,
            previous_screening_id,
            screened_by,
            channel,
            tier,
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
    deadline: datetime,
    pre_alert_sent: bool,
    created_at: datetime,
    attended_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> None:
    conn.execute(
        """INSERT INTO referrals
           (screening_id, miner_id, hospital, deadline, pre_alert_sent, status,
            attended_at, closed_at, created_at)
           VALUES (?, ?, 'Kwekwe District Hospital', ?, ?, ?, ?, ?, ?)""",
        (
            screening_id,
            miner_id,
            _iso(deadline),
            1 if pre_alert_sent else 0,
            status,
            _iso(attended_at) if attended_at else None,
            _iso(closed_at) if closed_at else None,
            _iso(created_at),
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
        conn.execute("DELETE FROM outreach_visits")
        conn.execute("DELETE FROM facilities")
        conn.commit()

        # --- Farai Ncube — Sherwood Mine — GREEN, single screening ---
        farai_id = _insert_worker(conn, "Farai Ncube", "+263771000002", "Sherwood Mine")
        _insert_screening(
            conn,
            farai_id,
            GREEN_PROFILE,
            "GREEN",
            0.91,
            "Minimal exposure, consistent N95 use, no symptoms reported.",
            ["under 2 years exposure", "always wears N95"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=12),
        )

        # --- Blessing Sithole — Globe & Phoenix Mine — YELLOW, single screening ---
        blessing_id = _insert_worker(
            conn, "Blessing Sithole", "+263771000003", "Globe & Phoenix Mine"
        )
        _insert_screening(
            conn,
            blessing_id,
            YELLOW_PROFILE,
            "YELLOW",
            0.78,
            "Moderate exposure with inconsistent dust suppression and mild breathlessness on exertion.",
            ["5-10 years drilling", "inconsistent wet drilling", "moderate breathlessness"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=20),
        )

        # --- Tapiwa Gumbo — Globe & Phoenix Mine — RED, referral closed ---
        tapiwa_id = _insert_worker(
            conn, "Tapiwa Gumbo", "+263771000004", "Globe & Phoenix Mine"
        )
        tapiwa_created = _now - timedelta(days=25)
        tapiwa_screening_id = _insert_screening(
            conn,
            tapiwa_id,
            RED_PROFILE,
            "RED",
            0.95,
            "Over 10 years of dry drilling with severe cough, chest pain and a current TB diagnosis.",
            ["10+ years exposure", "dry drilling", "current TB", "severe chest pain"],
            "APP",
            "VHW Grace Chikwanha",
            tapiwa_created,
        )
        _insert_referral(
            conn,
            tapiwa_screening_id,
            tapiwa_id,
            "closed",
            deadline=tapiwa_created + timedelta(hours=48),
            pre_alert_sent=True,
            created_at=tapiwa_created,
            attended_at=_now - timedelta(days=20),
            closed_at=_now - timedelta(days=18),
        )

        # --- Nyasha Chitiyo — Kwekwe Consolidated — RED, referral open ---
        nyasha_id = _insert_worker(
            conn, "Nyasha Chitiyo", "+263771000005", "Kwekwe Consolidated"
        )
        nyasha_created = _now - timedelta(days=2)
        nyasha_screening_id = _insert_screening(
            conn,
            nyasha_id,
            RED_PROFILE,
            "RED",
            0.93,
            "Severe breathlessness at rest with a prior lung diagnosis — urgent referral triggered.",
            ["severe breathlessness", "prior lung diagnosis", "no PPE"],
            "USSD",
            "USSD_SELF",
            nyasha_created,
        )
        _insert_referral(
            conn,
            nyasha_screening_id,
            nyasha_id,
            "open",
            deadline=nyasha_created + timedelta(hours=48),
            pre_alert_sent=False,
            created_at=nyasha_created,
        )

        # --- Kudakwashe Marecha — Sherwood Mine — ORANGE, referral attended (not yet closed) ---
        kuda_id = _insert_worker(
            conn, "Kudakwashe Marecha", "+263771000007", "Sherwood Mine"
        )
        kuda_created = _now - timedelta(days=6)
        kuda_screening_id = _insert_screening(
            conn,
            kuda_id,
            ORANGE_PROFILE,
            "ORANGE",
            0.84,
            "Over 10 years of dry drilling; symptoms consistent with possible disease requiring clinical assessment.",
            ["10+ years exposure", "dry drilling", "never wears PPE"],
            "APP",
            "VHW Grace Chikwanha",
            kuda_created,
        )
        _insert_referral(
            conn,
            kuda_screening_id,
            kuda_id,
            "attended",
            deadline=kuda_created + timedelta(days=14),
            pre_alert_sent=True,
            created_at=kuda_created,
            attended_at=_now - timedelta(days=1),
        )

        # --- Rutendo Marufu — Kwekwe Consolidated — GREEN, single screening ---
        rutendo_id = _insert_worker(
            conn, "Rutendo Marufu", "+263771000006", "Kwekwe Consolidated"
        )
        _insert_screening(
            conn,
            rutendo_id,
            GREEN_PROFILE,
            "GREEN",
            0.89,
            "Minimal exposure, no symptoms.",
            ["under 2 years exposure"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=5),
        )

        # --- Tendai Moyo — Sherwood Mine — YELLOW then RED (two screenings) ---
        tendai_id = _insert_worker(conn, "Tendai Moyo", "+263771000001", "Sherwood Mine")
        tendai_first_id = _insert_screening(
            conn,
            tendai_id,
            YELLOW_PROFILE,
            "YELLOW",
            0.80,
            "Moderate exposure, no symptoms yet — worth monitoring.",
            ["5-10 years drilling", "inconsistent PPE use"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=120),
        )
        tendai_second_created = _now - timedelta(days=1)
        tendai_second_id = _insert_screening(
            conn,
            tendai_id,
            RED_PROFILE,
            "RED",
            0.94,
            "Marked deterioration since last screening: new severe cough, chest pain and breathlessness.",
            ["10+ years exposure", "new severe symptoms since last screening"],
            "APP",
            "VHW Grace Chikwanha",
            tendai_second_created,
            previous_screening_id=tendai_first_id,
        )
        _insert_referral(
            conn,
            tendai_second_id,
            tendai_id,
            "pre_alerted",
            deadline=tendai_second_created + timedelta(hours=48),
            pre_alert_sent=True,
            created_at=tendai_second_created,
        )

        # --- Outreach starter rows (no endpoints read these yet) ---
        conn.execute(
            "INSERT INTO facilities (name, level, address, phone, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Kwekwe District Hospital",
                "district_hospital",
                "Corner Robert Mugabe / Sixth Ave, Kwekwe",
                "055-24000",
                -18.9281,
                29.8149,
            ),
        )
        conn.execute(
            "INSERT INTO facilities (name, level, address, phone, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Sherwood Clinic",
                "clinic",
                "Sherwood Mine, Kwekwe",
                "055-24101",
                -18.8931,
                29.7872,
            ),
        )

        conn.execute(
            "INSERT INTO outreach_visits "
            "(site, scheduled_date, expected_headcount, screened_count, health_workers, report_generated) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Globe & Phoenix Mine",
                (_now + timedelta(days=13)).strftime("%Y-%m-%d"),
                40,
                0,
                "Grace Chikwanha",
                0,
            ),
        )

        conn.commit()

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "miners",
                "screenings",
                "referrals",
                "facilities",
                "outreach_visits",
            )
        }
        print(
            f"Seeded: {counts['miners']} miners, {counts['screenings']} screenings, "
            f"{counts['referrals']} referrals across 3 sites; "
            f"{counts['facilities']} facilities, {counts['outreach_visits']} outreach visits."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
