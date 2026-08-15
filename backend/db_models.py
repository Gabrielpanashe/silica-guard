"""SQLAlchemy ORM models — the schema-preserving replacement for the raw SQL
that used to live in `database.SCHEMA` (see git history for that string if
you need to compare column-for-column). Table and column names are
unchanged from the pre-migration schema on purpose: this is a storage-layer
swap, not a data-shape redesign, so nothing about request/response shapes
in `models.py` or `docs/API_CONTRACT.md` needed to change alongside it.

One addition: `Referral.referral_code`, new as of 14 August 2026 (master
doc v6.0 Section 1.1 — the QR referral card was reframed into a plain
human-readable code). It rides along with this migration instead of a
second one later, since we're touching this file anyway.

Every column that had a `DEFAULT` in the old raw-SQL schema gets BOTH a
Python-side `default=` and a matching `server_default=` here, not just one:
`server_default` is what makes the legacy `get_connection()`/raw-SQL
callers still still in the codebase during this migration (see
`database.py`) behave identically to before — a plain `INSERT INTO ...`
that omits the column now needs the *database* to supply the default,
since it never goes through SQLAlchemy's insert construct at all. The
Python-side `default=` is for callers already converted to the ORM, so a
freshly-added object's attribute is populated immediately without an extra
round trip. Drop the `server_default` half only after every raw-SQL caller
is gone.

See `database.py` for the engine/session that binds these models to either
SQLite (local dev/tests) or PostgreSQL via Supabase (production).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    # Naive UTC on purpose, matching the project's existing convention
    # (CLAUDE.md: "All timestamps stored in UTC, ISO 8601") and sidestepping
    # the SQLite-vs-Postgres timezone-aware-datetime breakage the master doc
    # flags (Section 16.2): every timestamp column below is a plain
    # TIMESTAMP/DATETIME on both backends, never TIMESTAMPTZ, so comparisons
    # against `datetime.utcnow()` elsewhere in the codebase (e.g.
    # `services/referral_cascade.py`) keep working unchanged.
    return datetime.now(timezone.utc).replace(tzinfo=None)


_NOW = text("CURRENT_TIMESTAMP")  # portable across SQLite and Postgres


class Miner(Base):
    __tablename__ = "miners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    mine_site = Column(String)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    screenings = relationship(
        "Screening", back_populates="miner", foreign_keys="Screening.miner_id"
    )
    referrals = relationship("Referral", back_populates="miner")


class Screening(Base):
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    miner_id = Column(Integer, ForeignKey("miners.id"))
    previous_screening_id = Column(Integer, ForeignKey("screenings.id"))
    screened_by = Column(String)
    channel = Column(String)
    tier = Column(String)
    risk_confidence = Column(Float)
    advice_line = Column(Text)
    ai_explanation_shona = Column(Text)
    ai_explanation_english = Column(Text)
    ai_contributing_factors = Column(Text)
    provisional = Column(Integer, default=0, server_default=text("0"))
    fallback_used = Column(Integer, default=0, server_default=text("0"))
    synced = Column(Integer, default=1, server_default=text("1"))
    outreach_visit_id = Column(Integer, ForeignKey("outreach_visits.id"))
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        CheckConstraint("tier IN ('GREEN','YELLOW','ORANGE','RED')", name="ck_screenings_tier"),
    )

    miner = relationship("Miner", back_populates="screenings", foreign_keys=[miner_id])
    answers = relationship("ScreeningAnswer", back_populates="screening")
    referrals = relationship("Referral", back_populates="screening")


class ScreeningAnswer(Base):
    __tablename__ = "screening_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"))
    question_code = Column(String)
    question_text = Column(String)
    answer_value = Column(String)
    answer_score = Column(Integer)

    screening = relationship("Screening", back_populates="answers")


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    level = Column(String)
    address = Column(String)
    phone = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"))
    miner_id = Column(Integer, ForeignKey("miners.id"))
    hospital = Column(
        String, default="Kwekwe District Hospital", server_default=text("'Kwekwe District Hospital'")
    )
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    # New 14 August 2026 (master doc v6.0 Section 1.1) — short human-readable
    # code (e.g. "SG-4K7Q"), sent by SMS and typed into a hospital web page
    # to confirm attendance. Nullable/non-unique-enforced-at-DB-level is
    # deliberately loose here (SQLite's ALTER-free create_all can't backfill
    # uniqueness cleanly on a table with existing NULL rows); application
    # code guarantees uniqueness at generation time — see services/referrals.py.
    referral_code = Column(String, index=True)
    deadline = Column(DateTime)
    pre_alert_sent = Column(Integer, default=0, server_default=text("0"))
    status = Column(String, default="open", server_default=text("'open'"))
    reminder_stage = Column(Integer, default=0, server_default=text("0"))
    attended_at = Column(DateTime)
    closed_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','pre_alerted','reminded','attended','closed','escalated')",
            name="ck_referrals_status",
        ),
    )

    miner = relationship("Miner", back_populates="referrals")
    screening = relationship("Screening", back_populates="referrals")
    facility = relationship("Facility")


class OutreachVisit(Base):
    __tablename__ = "outreach_visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site = Column(String, nullable=False)
    scheduled_date = Column(Date)
    expected_headcount = Column(Integer)
    screened_count = Column(Integer, default=0, server_default=text("0"))
    health_workers = Column(String)
    report_generated = Column(Integer, default=0, server_default=text("0"))
    sms_3day_sent = Column(Integer, default=0, server_default=text("0"))
    sms_1day_sent = Column(Integer, default=0, server_default=text("0"))


class Mine(Base):
    __tablename__ = "mines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    district = Column(String)
    province = Column(String, default="Midlands", server_default=text("'Midlands'"))
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(Integer, ForeignKey("miners.id"), nullable=False)
    channel = Column(String, nullable=False, default="sms", server_default=text("'sms'"))
    template = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=_utcnow, server_default=_NOW)
    delivery_status = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('sent','failed','skipped')",
            name="ck_notifications_delivery_status",
        ),
    )


class KeepAlivePing(Base):
    """One fixed row (id=1), touched on the same APScheduler cadence as the
    referral cascade — see `services/db_keepalive.py`. Exists solely so a
    free Supabase project (Step B, master doc v6.0 Section 16.2) sees
    regular database activity and never hits its 7-day auto-pause window
    between now and the 28 August showcase."""

    __tablename__ = "keepalive_pings"

    id = Column(Integer, primary_key=True)
    pinged_at = Column(DateTime, default=_utcnow, server_default=_NOW)
