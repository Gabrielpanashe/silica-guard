"""
Seeds a reproducible demo dataset: multiple mine sites, all four risk tiers,
referrals across every lifecycle state (open/pre_alerted/attended/closed AND
reminded/escalated — those last two are seeded explicitly with
self-consistent timestamps rather than left to the live APScheduler cascade
to produce, so the demo data is deterministic regardless of when you seed
relative to when you present), one worker with two screenings (a YELLOW
followed later by a RED, for demoing the deterioration story), and two
outreach visits: one future-dated with nothing synced yet, one past-dated
with two linked screenings and report_generated=1 so GET /api/outreach has
a real populated report to demo, not just an empty shell. (The
employers/campaigns tables and their seed rows were removed 5 August
2026 — SilicaGuard is artisanal-miner-only now, see SILICAGUARD.md
Section 13.)

facilities AND outreach_visits are seeded FIRST, ahead of screenings/
referrals, so screenings can carry a real outreach_visit_id and referrals a
real facility_id (Outreach Planner and Smart Referral Router facility
matching, both 5 August 2026) — this is why both moved to the top of
seed() rather than the bottom.

Safe to re-run: clears every table this script owns first, so running it
twice reproduces the same known state rather than duplicating rows or
hitting the UNIQUE(phone) constraint.

Inserts screenings with pre-computed tiers directly — it does not call the
live Gemini risk engine, so it needs no GEMINI_API_KEY. It also never calls
services.notifications, so it needs no Africa's Talking key either;
referral rows are inserted directly with pre_alert_sent/status set to
reflect a plausible outcome rather than an actual SMS send, and no
`notifications` audit rows are inserted for the same reason — this script
simulates end states, not the act of sending.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/seed_demo_data.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from database import get_fresh_session, init_db  # noqa: E402
from db_models import Facility, Miner, Mine, OutreachVisit, Referral, Screening, ScreeningAnswer  # noqa: E402
from models import ScreeningAnswerIn  # noqa: E402
from questions import SCREENING_QUESTIONS  # noqa: E402
from services.advice_engine import personalised_advice_line  # noqa: E402
from services.referrals import _generate_referral_code  # noqa: E402

# Option index (0-based) per question, in SCREENING_QUESTIONS order, per tier profile.
GREEN_PROFILE = [0, 3, 0, 0, 0, 0, 0, 0, 0, 0]
YELLOW_PROFILE = [2, 0, 1, 1, 0, 1, 0, 0, 0, 0]
# Score >= 12, no hard safety trigger touched -> ORANGE (see services/referrals.py).
ORANGE_PROFILE = [3, 0, 2, 0, 0, 0, 0, 0, 0, 0]
# Touches every hard safety trigger (severe breathlessness/chest pain, current
# TB, prior lung diagnosis) -> RED regardless of score.
RED_PROFILE = [3, 0, 2, 3, 2, 2, 2, 2, 2, 1]

_now = datetime.now(timezone.utc).replace(tzinfo=None)

# Midlands province mine sites for the VHW's outreach-site dropdown
# (7 August 2026) — a curated suggestion list, not a hard foreign key
# target (miners.mine_site/outreach_visits.site stay free TEXT, see
# routers/mines.py). Names/districts are illustrative for the demo, not
# verified real-world coordinates — the three already used elsewhere in
# this seed script (Globe & Phoenix, Sherwood, Kwekwe Consolidated) are
# included so the dropdown matches the rest of the demo data.
MIDLANDS_MINES = [
    ("Globe & Phoenix Mine", "Kwekwe"),
    ("Sherwood Mine", "Kwekwe"),
    ("Kwekwe Consolidated", "Kwekwe"),
    ("Empress Nickel Mine", "Kwekwe"),
    ("Sandawana Mine", "Zvishavane"),
    ("Mimosa Mine", "Zvishavane"),
    ("Unki Mine", "Shurugwi"),
    ("Ngezi Mine", "Shurugwi"),
    ("Zenith Mine", "Gweru"),
    ("Mberengwa Chrome Belt", "Mberengwa"),
    ("Gokwe Alluvial Fields", "Gokwe"),
]


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


def _insert_worker(db, name: str, phone: str, mine_site: str) -> int:
    miner = Miner(name=name, phone=phone, mine_site=mine_site)
    db.add(miner)
    db.flush()
    return miner.id


def _insert_screening(
    db,
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
    outreach_visit_id: int | None = None,
) -> int:
    answers = _answers_for(profile)
    # advice_line (10 August) — this script never calls the live AI
    # pipeline, so it never got one before; reuses the real
    # personalised_advice_line logic (same weakest-answer selection a live
    # screening uses) rather than inventing separate canned text, so the
    # seeded history in the Screening History card reads exactly like a
    # real one, not a placeholder.
    advice_line = personalised_advice_line([ScreeningAnswerIn(**a) for a in answers])

    screening = Screening(
        miner_id=miner_id,
        previous_screening_id=previous_screening_id,
        screened_by=screened_by,
        channel=channel,
        tier=tier,
        risk_confidence=confidence,
        ai_explanation_english=explanation_english,
        ai_contributing_factors=json.dumps(contributing_factors),
        advice_line=advice_line,
        provisional=0,
        fallback_used=0,
        synced=1,
        created_at=created_at,
        outreach_visit_id=outreach_visit_id,
    )
    db.add(screening)
    db.flush()

    for answer in answers:
        db.add(
            ScreeningAnswer(
                screening_id=screening.id,
                question_code=answer["question_code"],
                question_text=answer["question_text"],
                answer_value=answer["answer_value"],
                answer_score=answer["answer_score"],
            )
        )
    return screening.id


def _insert_referral(
    db,
    screening_id: int,
    miner_id: int,
    status: str,
    deadline: datetime,
    pre_alert_sent: bool,
    created_at: datetime,
    facility_id: int,
    facility_name: str,
    reminder_stage: int = 0,
    attended_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> None:
    db.add(
        Referral(
            screening_id=screening_id,
            miner_id=miner_id,
            hospital=facility_name,
            facility_id=facility_id,
            # Seeded referrals get a real code too (14 August, master doc
            # v6.0 Section 1.1), same generator create_referral_and_notify
            # uses for a live referral — so the dashboard's referral list
            # and the lookup page have something real to demo without
            # needing a live screening first.
            referral_code=_generate_referral_code(db),
            deadline=deadline,
            pre_alert_sent=1 if pre_alert_sent else 0,
            status=status,
            reminder_stage=reminder_stage,
            attended_at=attended_at,
            closed_at=closed_at,
            created_at=created_at,
        )
    )


def seed() -> None:
    init_db()
    db = get_fresh_session()
    try:
        # Clear in FK-dependency order so this is safe to re-run from any state.
        db.query(Referral).delete()
        db.query(ScreeningAnswer).delete()
        db.query(Screening).delete()
        db.query(Miner).delete()
        db.query(OutreachVisit).delete()
        db.query(Facility).delete()
        db.query(Mine).delete()
        db.commit()

        # --- Mines dropdown list (Midlands province) ---
        for name, district in MIDLANDS_MINES:
            db.add(Mine(name=name, district=district, province="Midlands"))
        db.commit()

        # --- Facilities, seeded first so referrals below can carry a real
        # facility_id (Smart Referral Router facility matching). ---
        hospital = Facility(
            name="Kwekwe District Hospital",
            level="district_hospital",
            address="Corner Robert Mugabe / Sixth Ave, Kwekwe",
            phone="055-24000",
            latitude=-18.9281,
            longitude=29.8149,
        )
        db.add(hospital)
        db.flush()
        hospital_id = hospital.id
        hospital_name = hospital.name

        sherwood_clinic = Facility(
            name="Sherwood Clinic",
            level="clinic",
            address="Sherwood Mine, Kwekwe",
            phone="055-24101",
            latitude=-18.8931,
            longitude=29.7872,
        )
        db.add(sherwood_clinic)
        db.flush()
        sherwood_clinic_id = sherwood_clinic.id
        sherwood_clinic_name = sherwood_clinic.name

        # --- Outreach visits, seeded before the screenings below so two of
        # them can carry a real outreach_visit_id. ---
        future_visit = OutreachVisit(
            site="Globe & Phoenix Mine",
            scheduled_date=(_now + timedelta(days=13)).date(),
            expected_headcount=40,
            screened_count=0,
            health_workers='["Grace Chikwanha"]',
            report_generated=0,
            sms_3day_sent=0,
            sms_1day_sent=0,
        )
        db.add(future_visit)
        db.flush()

        # Past visit, already fully processed by the scheduled cascade (both
        # announcements sent, report ready) — linked screenings below give
        # GET /api/outreach a real report to show, not an empty shell.
        past_visit = OutreachVisit(
            site="Sherwood Mine",
            scheduled_date=(_now - timedelta(days=9)).date(),
            expected_headcount=5,
            screened_count=2,
            health_workers='["Grace Chikwanha"]',
            report_generated=1,
            sms_3day_sent=1,
            sms_1day_sent=1,
        )
        db.add(past_visit)
        db.flush()
        past_visit_id = past_visit.id

        # --- Farai Ncube — Sherwood Mine — GREEN, single screening, from the
        # past outreach visit above ---
        farai_id = _insert_worker(db, "Farai Ncube", "+263771000002", "Sherwood Mine")
        _insert_screening(
            db,
            farai_id,
            GREEN_PROFILE,
            "GREEN",
            0.91,
            "Minimal exposure, consistent N95 use, no symptoms reported.",
            ["under 2 years exposure", "always wears N95"],
            "APP",
            "VHW Grace Chikwanha",
            _now - timedelta(days=12),
            outreach_visit_id=past_visit_id,
        )

        # --- Blessing Sithole — Globe & Phoenix Mine — YELLOW, single screening ---
        blessing_id = _insert_worker(db, "Blessing Sithole", "+263771000003", "Globe & Phoenix Mine")
        _insert_screening(
            db,
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
        tapiwa_id = _insert_worker(db, "Tapiwa Gumbo", "+263771000004", "Globe & Phoenix Mine")
        tapiwa_created = _now - timedelta(days=25)
        tapiwa_screening_id = _insert_screening(
            db,
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
            db,
            tapiwa_screening_id,
            tapiwa_id,
            "closed",
            deadline=tapiwa_created + timedelta(hours=48),
            pre_alert_sent=True,
            created_at=tapiwa_created,
            facility_id=hospital_id,
            facility_name=hospital_name,
            attended_at=_now - timedelta(days=20),
            closed_at=_now - timedelta(days=18),
        )

        # --- Nyasha Chitiyo — Kwekwe Consolidated — RED, referral open ---
        nyasha_id = _insert_worker(db, "Nyasha Chitiyo", "+263771000005", "Kwekwe Consolidated")
        nyasha_created = _now - timedelta(days=2)
        nyasha_screening_id = _insert_screening(
            db,
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
            db,
            nyasha_screening_id,
            nyasha_id,
            "open",
            deadline=nyasha_created + timedelta(hours=48),
            pre_alert_sent=False,
            created_at=nyasha_created,
            facility_id=hospital_id,
            facility_name=hospital_name,
        )

        # --- Kudakwashe Marecha — Sherwood Mine — ORANGE, referral attended (not yet closed) ---
        kuda_id = _insert_worker(db, "Kudakwashe Marecha", "+263771000007", "Sherwood Mine")
        kuda_created = _now - timedelta(days=6)
        kuda_screening_id = _insert_screening(
            db,
            kuda_id,
            ORANGE_PROFILE,
            "ORANGE",
            0.84,
            "Over 10 years of dry drilling; symptoms consistent with possible disease requiring clinical assessment.",
            ["10+ years exposure", "dry drilling", "never wears PPE"],
            "APP",
            "VHW Grace Chikwanha",
            kuda_created,
            outreach_visit_id=past_visit_id,
        )
        _insert_referral(
            db,
            kuda_screening_id,
            kuda_id,
            "attended",
            deadline=kuda_created + timedelta(days=14),
            pre_alert_sent=True,
            created_at=kuda_created,
            # ORANGE at Sherwood Mine matches the Sherwood Clinic by name —
            # same rule services/facility_matching.py applies live.
            facility_id=sherwood_clinic_id,
            facility_name=sherwood_clinic_name,
            reminder_stage=1,  # day-3 reminder already sent before he attended
            attended_at=_now - timedelta(days=1),
        )

        # --- Rutendo Marufu — Kwekwe Consolidated — GREEN, single screening ---
        rutendo_id = _insert_worker(db, "Rutendo Marufu", "+263771000006", "Kwekwe Consolidated")
        _insert_screening(
            db,
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
        tendai_id = _insert_worker(db, "Tendai Moyo", "+263771000001", "Sherwood Mine")
        tendai_first_id = _insert_screening(
            db,
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
            db,
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
            db,
            tendai_second_id,
            tendai_id,
            "pre_alerted",
            deadline=tendai_second_created + timedelta(hours=48),
            pre_alert_sent=True,
            created_at=tendai_second_created,
            # RED always routes to the hospital regardless of mine_site.
            facility_id=hospital_id,
            facility_name=hospital_name,
        )

        # --- Tatenda Moyana — Globe & Phoenix Mine — ORANGE, mid-cascade
        # 'reminded' state. No clinic at this site in the seed data, so the
        # ORANGE match falls back to the hospital, same as the live rule. ---
        tatenda_id = _insert_worker(db, "Tatenda Moyana", "+263771000008", "Globe & Phoenix Mine")
        tatenda_created = _now - timedelta(days=5)
        tatenda_screening_id = _insert_screening(
            db,
            tatenda_id,
            ORANGE_PROFILE,
            "ORANGE",
            0.82,
            "Over 10 years of dry drilling; symptoms consistent with possible disease requiring clinical assessment.",
            ["10+ years exposure", "dry drilling", "never wears PPE"],
            "APP",
            "VHW Grace Chikwanha",
            tatenda_created,
        )
        _insert_referral(
            db,
            tatenda_screening_id,
            tatenda_id,
            "reminded",
            deadline=tatenda_created + timedelta(days=14),
            pre_alert_sent=True,
            created_at=tatenda_created,
            facility_id=hospital_id,
            facility_name=hospital_name,
            reminder_stage=1,  # day-3 reminder sent; day-7 not due yet at day 5
        )

        # --- Farai Chikara — Kwekwe Consolidated — RED, 'escalated' (missed
        # the 48h emergency window entirely). ---
        farai_c_id = _insert_worker(db, "Farai Chikara", "+263771000009", "Kwekwe Consolidated")
        farai_c_created = _now - timedelta(days=3)
        farai_c_screening_id = _insert_screening(
            db,
            farai_c_id,
            RED_PROFILE,
            "RED",
            0.96,
            "Over 10 years of dry drilling with severe cough, chest pain and a current TB diagnosis.",
            ["10+ years exposure", "dry drilling", "current TB", "severe chest pain"],
            "APP",
            "VHW Grace Chikwanha",
            farai_c_created,
        )
        _insert_referral(
            db,
            farai_c_screening_id,
            farai_c_id,
            "escalated",
            deadline=farai_c_created + timedelta(hours=48),
            pre_alert_sent=True,
            created_at=farai_c_created,
            facility_id=hospital_id,
            facility_name=hospital_name,
            reminder_stage=1,  # the 24h reminder went out before he missed the 48h deadline
        )

        db.commit()

        counts = {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (Miner, Screening, Referral, Facility, OutreachVisit, Mine)
        }
        site_count = db.scalar(
            select(func.count(func.distinct(Miner.mine_site))).where(Miner.mine_site.is_not(None))
        )
        print(
            f"Seeded: {counts['miners']} miners, {counts['screenings']} screenings, "
            f"{counts['referrals']} referrals across {site_count} sites "
            "(every referral status incl. reminded/escalated represented); "
            f"{counts['facilities']} facilities, {counts['outreach_visits']} outreach visits, "
            f"{counts['mines']} mines in the outreach-site dropdown."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
