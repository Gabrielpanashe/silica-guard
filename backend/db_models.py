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
    UniqueConstraint,
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
    # to confirm attendance. Nullable (GREEN/YELLOW screenings never get
    # one) but unique where set — added 16 August 2026 once Alembic/Postgres
    # (Step B) made a real migration possible; originally left DB-level-loose
    # only because SQLite's ALTER-free create_all() couldn't backfill
    # uniqueness cleanly on a table with existing NULL rows. Application
    # code already guarantees uniqueness at generation time via a
    # collision-check loop (services/referrals.py::_generate_referral_code)
    # — this is defense-in-depth against that theoretical race, not the
    # only thing preventing a collision.
    referral_code = Column(String, unique=True, index=True)
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


# ─────────────────────────────────────────────────────────────────────────
#  VERSION TWO MODEL — Master Reference v1.0 §8.1, §8.2, §8.5, §10.5
#
#  Added alongside the version one tables, not in place of them. Both sets
#  exist during the transition: the v1 routes keep serving the mobile app and
#  dashboard from `miners`/`screenings` until those clients move to v2, and
#  `0008_v2_drop_v1` removes the old tables once the adapter is deleted
#  (docs/IMPLEMENTATION_PLAN.md §3, §5).
#
#  The rule that holds all of it together, worth writing on the wall: the
#  word silicosis may appear in this database as a VALUE. It may never appear
#  as a column name. Follow that and the day tuberculosis is added is a day
#  of adding rows, not of migrating patient records.
#
#  There is no backfill from v1. The database holds only demonstration data,
#  so the v2 tables are cut clean and `scripts/seed_demo_data.py` is rewritten
#  against them (§8.1: "cut the version two schema deliberately while the
#  database still contains only demonstration data, and reseed").
# ─────────────────────────────────────────────────────────────────────────


class Person(Base):
    """The identity anchor. Renamed from `miners` because a construction
    worker or a tobacco grader is not a miner and the same individual moves
    between sectors (§8.1).

    Holds identity only: no clinical content, no occupation, no site. Those
    live in ExposureProfile and ScreeningSession, which is what lets analysis
    run against a de-identified view by default (§10.1, §16.4).

    Telephone number is NOT here. It is an attribute with history on
    Contact, never an identity key (§8.2) — handsets are shared, borrowed
    and sold, and a false merge mixes two clinical histories in a way no
    inspection can detect afterwards.
    """

    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    #: Short human-readable code, printed on a card the worker keeps. Six
    #: characters from the referral-code alphabet: about a billion codes,
    #: against the four-character referral format's million, because this one
    #: addresses a register meant for more than 500,000 people and a
    #: collision here is a clinical safety event rather than an annoyance
    #: (docs/IMPLEMENTATION_PLAN.md §12 item 4).
    participant_code = Column(String, unique=True, index=True)
    #: Salted hash only, never a recoverable form (§16.2). Voluntary.
    national_id_hash = Column(String, index=True)
    #: Banded rather than a birth date: enough for stratified analysis and
    #: reference values, less identifying.
    age_band = Column(String)
    sex = Column(String)
    #: Preferred language for every patient-facing string sent to them.
    language = Column(String, default="en", server_default=text("'en'"))
    #: Set when this record loses a merge. The losing record is kept rather
    #: than deleted so that every merge is reversible from the first day
    #: (§8.2).
    merged_into_id = Column(Integer, ForeignKey("persons.id"))
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "sex IS NULL OR sex IN ('male','female','prefer_not_to_say')",
            name="ck_persons_sex",
        ),
    )


class Contact(Base):
    """Telephone numbers and other contact points, with validity dates.

    Many people may share a number; one person may hold several over time.
    Never an identity key (§8.2).

    Two columns for one number, deliberately: `number_hmac` is a keyed hash
    for equality lookup (the USSD webhook arrives with a caller number and
    must find the person), and `number_encrypted` is the recoverable form
    needed to actually send a message. An encrypted column cannot be indexed
    for equality, so one alone cannot do both jobs — see
    docs/IMPLEMENTATION_PLAN.md §12 item 11. Key handling and rotation are in
    docs/SECURITY.md.
    """

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    kind = Column(String, default="phone", server_default=text("'phone'"))
    number_hmac = Column(String, index=True, nullable=False)
    number_encrypted = Column(Text, nullable=False)
    is_primary = Column(Integer, default=0, server_default=text("0"))
    #: Verified at a screening. A long-dormant contact is re-verified before
    #: use, and sends stop after repeated delivery failures, because a
    #: recycled number means disclosing health data to a stranger (§13.2).
    verified = Column(Integer, default=0, server_default=text("0"))
    verified_at = Column(DateTime)
    valid_from = Column(DateTime, default=_utcnow, server_default=_NOW)
    valid_to = Column(DateTime)

    person = relationship("Person")


class Site(Base):
    """Renamed from `mines`, and carries a sector and a type, because the
    exposure axis grows to quarrying, construction, foundries and tobacco
    processing (§5.2).

    Deliberately NOT a hard foreign-key target from a session: informal
    workings are informal, many are entered as free text, and forcing
    structure that does not exist produces worse data than a curated list
    with a free-text fallback (§15.6).
    """

    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    sector = Column(String, default="asm_gold", server_default=text("'asm_gold'"))
    type = Column(String)
    district = Column(String)
    province = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    #: True for the curated list offered in a dropdown; False for a name a
    #: health worker typed in the field.
    curated = Column(Integer, default=1, server_default=text("1"))
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)


class Programme(Base):
    """An employer- or insurer-funded cohort.

    This table plus the one nullable reference on ScreeningSession is the
    entire formal-sector seam (§5.3, §8.1). No formal-sector features are
    built in phase one; the only discipline is that no code may assume a
    session has no programme. Absent, or kind 'community', means outreach.

    Employer disclosure consent lives on ConsentRecord, not here: an employer
    never receives individual results without separate, specific, refusable
    consent from the worker (§14.4), and that is a per-person permission, not
    a programme setting.
    """

    __tablename__ = "programmes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    kind = Column(String, default="community", server_default=text("'community'"))
    payer = Column(String)
    data_owner = Column(String)
    #: Which consent text version this programme's workers are shown.
    consent_text_code = Column(String)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('community','employer','insurer')",
            name="ck_programmes_kind",
        ),
    )


class ExposureProfile(Base):
    """Occupation history: what the worker does, for how long, with what
    controls.

    Separated from the screening on purpose (§8.1). This is the block that
    changes when the system moves to a new sector, while the symptom core
    stays the same — which is what makes a new sector a configuration change
    rather than a rebuild (§5.2).
    """

    __tablename__ = "exposure_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    #: Recorded during a session, but kept as its own row so a work history
    #: accumulates across sessions and across sectors.
    session_id = Column(Integer, ForeignKey("screening_sessions.id"))
    sector = Column(String)
    occupation = Column(String)
    tasks = Column(Text)
    years_band = Column(String)
    controls = Column(Text)
    wet_or_dry = Column(String)
    recorded_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    person = relationship("Person")


class ScreeningSession(Base):
    """The encounter. Replaces `screenings`, which carried a tier in its own
    columns — the silicosis-shaped defect §8.1 names.

    A session now produces zero or more ScreeningResult rows, one per
    condition assessed. That single change is what makes tuberculosis a day
    of adding rows rather than a migration of patient records.
    """

    __tablename__ = "screening_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    channel = Column(String, nullable=False)
    screened_by = Column(String)
    #: Curated site where known, free text otherwise (§15.6).
    site_id = Column(Integer, ForeignKey("sites.id"))
    site_text = Column(String)
    #: The formal-sector seam. Null, or a 'community' programme, means outreach.
    programme_id = Column(Integer, ForeignKey("programmes.id"))
    #: Provenance as a natural key rather than a surrogate foreign key: §10.1
    #: requires a result to name the instrument and rules that produced it,
    #: and a code plus version answers that directly and survives any later
    #: restructuring of the instrument tables. `0005_v2_instrument` may add a
    #: foreign key alongside these if normalisation is wanted; the audit value
    #: is in these two columns either way.
    instrument_code = Column(String)
    instrument_version = Column(Integer)
    ruleset_version = Column(String)
    #: Longitudinal link, for deterioration. Null where the worker declined
    #: retention of a longitudinal record (§14.2) or this is a first visit.
    previous_session_id = Column(Integer, ForeignKey("screening_sessions.id"))
    #: Idempotency key, generated on the device when the session starts and
    #: replayed on retry. A mobile retry or a gateway redelivery must not
    #: create a second session (§10.3) — this is the column that makes the
    #: duplicate-screening incident of 23 August structurally impossible.
    client_session_uuid = Column(String, unique=True, index=True)
    outreach_visit_id = Column(Integer, ForeignKey("outreach_visits.id"))
    #: Screening duration is a pilot indicator and cannot be added
    #: retrospectively (§13.3, §19.2), so the clock starts in the schema.
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    person = relationship("Person", foreign_keys=[person_id])
    results = relationship("ScreeningResult", back_populates="session")

    __table_args__ = (
        CheckConstraint("channel IN ('APP','USSD')", name="ck_sessions_channel"),
    )


class ScreeningResult(Base):
    """One row per condition assessed. **The single most important change in
    the whole schema** (§8.1).

    Carries the provenance §10.1 requires: which instrument version, which
    ruleset, by what method, and whether a safety override fired. Nothing
    clinical is ever produced by logic that cannot be named afterwards —
    without this, every tier assigned before a threshold moved becomes
    uninterpretable and no sensitivity claim can be made at all (§8.3).
    """

    __tablename__ = "screening_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("screening_sessions.id"), nullable=False)
    #: A value, never a column name.
    condition_code = Column(String, nullable=False)
    tier = Column(String, nullable=False)
    score = Column(Integer)
    #: Fixed for rule-based classification; kept because the four-tier API
    #: has always carried one and the dashboards read it.
    confidence = Column(Float)
    #: How the tier was reached. 'deterministic_rules' is the only value the
    #: engine produces; the column exists so that a future method is
    #: distinguishable in the data rather than inferred from a date.
    method = Column(
        String, nullable=False, default="deterministic_rules",
        server_default=text("'deterministic_rules'"),
    )
    instrument_code = Column(String)
    instrument_version = Column(Integer)
    ruleset_version = Column(String)
    #: Tier before deterioration and overrides, so the cascade is auditable
    #: step by step rather than only at its end.
    scored_tier = Column(String)
    override_fired = Column(Integer, default=0, server_default=text("0"))
    #: Codes of the safety rules that fired, comma-separated. Stored because
    #: "the rule fired" and "the rule never matched" are different audit
    #: stories.
    override_rule_codes = Column(Text)
    deterioration_changed = Column(Integer, default=0, server_default=text("0"))
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    session = relationship("ScreeningSession", back_populates="results")

    __table_args__ = (
        CheckConstraint("tier IN ('GREEN','YELLOW','ORANGE','RED')", name="ck_results_tier"),
        CheckConstraint(
            "scored_tier IS NULL OR scored_tier IN ('GREEN','YELLOW','ORANGE','RED')",
            name="ck_results_scored_tier",
        ),
    )


class ConsentText(Base):
    """The exact wording a person was shown, versioned.

    Consent cannot be applied retrospectively, and an ethics committee will
    ask what was said (§8.5, §14.2). The words themselves live in the content
    store, referenced by `message_code`, so one review and translation
    pipeline covers consent text like every other patient-facing string
    (§8.4).
    """

    __tablename__ = "consent_texts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    message_code = Column(String, nullable=False)
    status = Column(String, default="draft", server_default=text("'draft'"))
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)


class ConsentRecord(Base):
    """One row per permission per person: consent is layered and recorded as
    data, never bundled or assumed (§14.2).

    The six permissions are screening_and_referral, longitudinal_record,
    contact_by_message, education_broadcast, research_and_statistics and
    employer_disclosure. The last is future-phase, separate, specific and
    refusable — building that boundary now, before any commercial pressure
    exists, is what makes the formal-sector module defensible to a union, a
    ministry and an ethics committee (§14.4).
    """

    __tablename__ = "consent_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    permission = Column(String, nullable=False)
    granted = Column(Integer, nullable=False)
    consent_text_id = Column(Integer, ForeignKey("consent_texts.id"))
    channel = Column(String)
    session_id = Column(Integer, ForeignKey("screening_sessions.id"))
    recorded_at = Column(DateTime, default=_utcnow, server_default=_NOW)
    recorded_by = Column(String)
    #: Set when a permission is later withdrawn. The original row is kept:
    #: the retention and withdrawal mechanism must be demonstrable (§14.3).
    withdrawn_at = Column(DateTime)

    person = relationship("Person")

    __table_args__ = (
        CheckConstraint(
            "permission IN ('screening_and_referral','longitudinal_record',"
            "'contact_by_message','education_broadcast','research_and_statistics',"
            "'employer_disclosure')",
            name="ck_consent_permission",
        ),
    )


class PersonMatchQueue(Base):
    """Probable identity matches awaiting a human decision.

    Never merged automatically (§8.2). Duplicates are an annoyance that can
    be fixed later; a false merge is a clinical safety event that mixes two
    histories with no way to detect it by inspection. A deterministic match
    on a hashed identity number is applied directly; everything else lands
    here.
    """

    __tablename__ = "person_match_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incoming_person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    candidate_person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    score = Column(Float)
    evidence = Column(Text)
    status = Column(String, default="pending", server_default=text("'pending'"))
    resolved_by = Column(String)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','merged','rejected')",
            name="ck_match_queue_status",
        ),
    )


class PersonMerge(Base):
    """An applied merge, and the evidence it rested on.

    Reversible from the first day (§8.2): the losing person row is kept and
    flagged via Person.merged_into_id rather than deleted, so an incorrect
    merge can be undone with both histories intact.
    """

    __tablename__ = "person_merges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    winner_person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    loser_person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    evidence = Column(Text)
    merged_by = Column(String)
    merged_at = Column(DateTime, default=_utcnow, server_default=_NOW)
    reversed_by = Column(String)
    reversed_at = Column(DateTime)


# ─────────────────────────────────────────────────────────────────────────
#  INSTRUMENT AND RULES AS VERSIONED DATA — Master Reference v1.0 §8.3
#
#  The third irreversible decision. At present the questions live in a source
#  file, the scoring lives in code, the USSD thresholds are numeric literals
#  and the safety overrides are hardcoded — every one of them a deployment
#  away from silently changing, and none recorded against the result it
#  produced. That is fatal for validation: to claim any sensitivity or
#  specificity the system must be able to say which instrument version and
#  which ruleset produced which tier for which person.
#
#  These tables mirror `clinical/instrument.schema.json` one-for-one, so a
#  reviewed YAML file maps to rows without interpretation. `services/
#  instrument_store.py` loads a file into them and reads it back into exactly
#  the dict shape `services/rules_engine.py` already consumes — the round
#  trip is tested, which is what proves the tables model the format
#  faithfully rather than approximately.
#
#  Two properties make this safe rather than fragile (§8.3):
#    * An APPROVED version is immutable. A change creates a new version and
#      never edits an approved row, because a result whose rules were edited
#      afterwards is uninterpretable.
#    * Every screening result stores the instrument and ruleset version that
#      produced it — already true, on ScreeningResult above.
#
#  Predicates are stored as JSON text rather than a native JSON column, for
#  the same reason every timestamp here is a plain TIMESTAMP: the schema must
#  behave identically on SQLite (local, tests) and PostgreSQL (production),
#  and §16.2 flags exactly this class of divergence. They are parsed on load
#  and evaluated by the closed grammar in `services/predicates.py`; nothing
#  is ever eval'd.
# ─────────────────────────────────────────────────────────────────────────


class Instrument(Base):
    """One version of the clinical screening instrument.

    `status` drives the loader: `approved` is immutable and selectable;
    `example` is refused outright, so the synthetic format illustration in
    `clinical/examples/` can never reach a database (§8.3, clinical/README).
    """

    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="draft", server_default=text("'draft'"))
    approved_by = Column(String)
    approved_at = Column(DateTime)
    supersedes = Column(Integer)
    #: §12.2 item 10. An unanswered red-flag question must never default to a
    #: negative, so the treatment of unknown and refused is part of the
    #: version rather than a convention in code.
    unknown_score = Column(Integer, default=0, server_default=text("0"))
    refused_score = Column(Integer, default=0, server_default=text("0"))
    #: §13.1: a partially answered instrument must never produce a tier.
    partial_session_may_produce_tier = Column(Integer, default=0, server_default=text("0"))
    #: §12.5's honest statement of what the instrument does not detect,
    #: including the asymptomatic early-disease limitation. JSON array of
    #: strings: documentation that forms part of the ethics submission, never
    #: queried, so it is stored whole rather than split into rows.
    limitations = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=_utcnow, server_default=_NOW)

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_instruments_code_version"),
        CheckConstraint(
            "status IN ('draft','review','approved','retired','example')",
            name="ck_instruments_status",
        ),
    )


class InstrumentCondition(Base):
    """Which conditions a version assesses. A row, never a column — adding
    tuberculosis is an insert (§8.1)."""

    __tablename__ = "instrument_conditions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    condition_code = Column(String, nullable=False)
    ordinal = Column(Integer, default=0, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("instrument_id", "condition_code", name="uq_instrument_condition"),
    )


class InstrumentBlock(Base):
    """Identity, exposure, lifestyle, symptom core, history (§12.1). The
    symptom core is shared across conditions; the exposure block is what
    changes for a new sector."""

    __tablename__ = "instrument_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    code = Column(String, nullable=False)
    title_message_code = Column(String, nullable=False)
    ordinal = Column(Integer, default=0, server_default=text("0"))
    notes = Column(Text)

    __table_args__ = (
        UniqueConstraint("instrument_id", "code", name="uq_instrument_block"),
    )


class InstrumentQuestion(Base):
    """A question belonging to one instrument version.

    The wording a worker reads is NOT here: `label_message_code` points at
    the content store, so one review, translation and GSM-7 pipeline covers
    every patient-facing string (§8.4). `clinical_label` is the internal
    clinical name and is never shown to a worker.
    """

    __tablename__ = "instrument_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    code = Column(String, nullable=False)
    block_code = Column(String, nullable=False)
    clinical_label = Column(String, nullable=False)
    response_type = Column(String, nullable=False)
    label_message_code = Column(String, nullable=False)
    ordinal = Column(Integer, default=0, server_default=text("0"))
    #: Whether a worsening answer counts as deterioration against the
    #: worker's previous session. The Clinical Lead's decision, recorded as
    #: data, replacing the hardcoded set in the v1 services/deterioration.py.
    tracked_for_trajectory = Column(Integer, default=0, server_default=text("0"))
    #: Predicate deciding whether the question is asked at all. JSON text.
    branching = Column(Text)
    #: §12.1 requires a citation for every question and every threshold. The
    #: current draft has none, and this is what an ethics committee asks for.
    citation = Column(Text, nullable=False)
    notes = Column(Text)

    __table_args__ = (
        UniqueConstraint("instrument_id", "code", name="uq_instrument_question"),
        CheckConstraint(
            "response_type IN ('single_select','multi_select','integer_banded','boolean')",
            name="ck_question_response_type",
        ),
    )


class AnswerOption(Base):
    """A selectable answer. `is_unknown` marks the explicit unknown or
    refused option, which is what makes the `unknown` predicate meaningful
    rather than an inference from absence (§12.2 item 10)."""

    __tablename__ = "answer_options"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("instrument_questions.id"), nullable=False)
    value = Column(String, nullable=False)
    label_message_code = Column(String, nullable=False)
    ordinal = Column(Integer, default=0, server_default=text("0"))
    is_unknown = Column(Integer, default=0, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("question_id", "value", name="uq_answer_option_value"),
    )


class AnswerBand(Base):
    """For an `integer_banded` question: a number is recorded, a band is
    scored. Banding rather than a free integer improves recall accuracy and
    usability (§12.4)."""

    __tablename__ = "answer_bands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("instrument_questions.id"), nullable=False)
    #: Inclusive lower bound.
    from_value = Column(Integer, nullable=False)
    value = Column(String, nullable=False)
    label_message_code = Column(String, nullable=False)
    ordinal = Column(Integer, default=0, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("question_id", "value", name="uq_answer_band_value"),
    )


class InstrumentChannel(Base):
    """Which channels ask a question.

    §13.1: a long instrument plus consent does not fit a 180-second USSD
    session. The Clinical Lead defines any shorter USSD subset deliberately,
    as data, rather than the channel truncating silently. No rows for a
    question means every channel asks it.
    """

    __tablename__ = "instrument_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("instrument_questions.id"), nullable=False)
    channel = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("question_id", "channel", name="uq_instrument_channel"),
        CheckConstraint("channel IN ('app','ussd')", name="ck_instrument_channel"),
    )


class ScoringRule(Base):
    """What one answer contributes to one condition.

    Keyed by condition because the same answer can weigh differently for
    silicosis than for tuberculosis (§8.3) — which is precisely what lets a
    second condition be rows rather than a second score column.
    """

    __tablename__ = "scoring_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("instrument_questions.id"), nullable=False)
    condition_code = Column(String, nullable=False)
    answer_value = Column(String, nullable=False)
    score = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("question_id", "condition_code", "answer_value", name="uq_scoring_rule"),
    )


class TierRule(Base):
    """One branch of the tier cascade, as a predicate.

    §9.2: the cascade is boolean logic over answer values, and §12.2 contains
    rules of the form (years > 10 AND any symptoms) OR (past TB AND any
    breathlessness) — which a (min_score, max_score) table cannot express. A
    plain score band is one predicate, so nothing is lost. Evaluated in
    descending priority; first match wins.
    """

    __tablename__ = "tier_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    condition_code = Column(String, nullable=False)
    tier = Column(String, nullable=False)
    priority = Column(Integer, nullable=False, default=0, server_default=text("0"))
    predicate = Column(Text, nullable=False)
    label = Column(String)
    citation = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("tier IN ('GREEN','YELLOW','ORANGE','RED')", name="ck_tier_rule_tier"),
    )


class SafetyRule(Base):
    """A red flag. Runs LAST and may raise a tier, never lower one (§10.3
    step 7), so that no earlier step — and no model, if one is ever
    introduced upstream — can be the final word on it.

    Owned by the Clinical Lead rather than inherited from code: §12.2 item 1
    records that the deployed overrides and the draft tier rules currently
    disagree, and this table is where that is resolved once, visibly.
    """

    __tablename__ = "safety_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    #: Recorded on every result this rule fires on, so a classification can
    #: be audited afterwards.
    code = Column(String, nullable=False)
    #: Null means the rule applies to every condition.
    condition_code = Column(String)
    forces_tier = Column(String, nullable=False)
    predicate = Column(Text, nullable=False)
    label = Column(String)
    citation = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("instrument_id", "code", name="uq_safety_rule_code"),
        CheckConstraint("forces_tier IN ('GREEN','YELLOW','ORANGE','RED')", name="ck_safety_rule_tier"),
    )


class InstrumentInterval(Base):
    """Re-screen interval and referral window per condition and tier.

    §12.2 items 7 and 8: the tier-three referral window is unstated in the
    draft while the system uses 14 days, and the re-screen intervals conflict
    between drafts. Both must be stated explicitly by the Clinical Lead
    rather than implied by code, and this is where they are stated.
    """

    __tablename__ = "instrument_intervals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    condition_code = Column(String, nullable=False)
    tier = Column(String, nullable=False)
    #: Null where the interval is linked to a referral outcome rather than a
    #: fixed period.
    rescreen_days = Column(Integer)
    #: Required for tiers that generate a referral.
    referral_window_hours = Column(Integer)
    citation = Column(Text)

    __table_args__ = (
        UniqueConstraint("instrument_id", "condition_code", "tier", name="uq_instrument_interval"),
        CheckConstraint("tier IN ('GREEN','YELLOW','ORANGE','RED')", name="ck_interval_tier"),
    )
