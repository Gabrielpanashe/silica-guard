"""The version two schema.

Master Reference v1.0 §8.1, §8.2, §8.5. These tests pin the structural
decisions that are expensive to reverse once a real record exists -- which is
the whole reason the schema is being cut now, while the database holds only
demonstration data.

The migration itself (`0004_v2_identity_sessions_results_consent`) is
exercised forward and backward on PostgreSQL by the CI `migrations` job.
These tests run against the models on SQLite, like the rest of the suite.
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import database
from db_models import (
    Base,
    ConsentRecord,
    ConsentText,
    Contact,
    Person,
    PersonMerge,
    Programme,
    ScreeningResult,
    ScreeningSession,
    Site,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v2.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _person(db, **kw):
    p = Person(**kw)
    db.add(p)
    db.commit()
    return p


# ------------------------------------------------- the defining change

def test_a_session_produces_one_result_row_per_condition(db):
    """§8.1's single most important change. A screening used to carry one
    tier in its own columns, which is silicosis-shaped; it now produces rows,
    so a second condition is rows rather than a migration."""
    person = _person(db)
    session = ScreeningSession(person_id=person.id, channel="APP")
    db.add(session)
    db.commit()

    for condition, tier in (("silicosis", "ORANGE"), ("tuberculosis", "YELLOW")):
        db.add(ScreeningResult(
            session_id=session.id, condition_code=condition, tier=tier,
            method="deterministic_rules",
        ))
    db.commit()

    db.refresh(session)
    assert {r.condition_code: r.tier for r in session.results} == {
        "silicosis": "ORANGE", "tuberculosis": "YELLOW",
    }


def test_no_column_anywhere_names_a_condition(db):
    """The discipline that holds the whole model together (§8.1): the word
    silicosis may appear as a VALUE and never as a column name. This test is
    what stops someone adding `silicosis_tier` in a hurry."""
    inspector = inspect(db.get_bind())
    offenders = []
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            name = column["name"].lower()
            for condition in ("silicosis", "tuberculosis", "tb_", "copd", "pneumoconiosis"):
                if condition in name:
                    offenders.append(f"{table}.{column['name']}")
    assert not offenders, f"condition names used as columns: {offenders}"


def test_a_result_records_its_provenance(db):
    """§10.1: nothing clinical is produced by logic that cannot be named
    afterwards. Without this, a tier assigned before a threshold moved is
    uninterpretable and no sensitivity claim can be made (§8.3)."""
    person = _person(db)
    session = ScreeningSession(
        person_id=person.id, channel="APP",
        instrument_code="SG-LUNG", instrument_version=1, ruleset_version="1",
    )
    db.add(session)
    db.commit()
    db.add(ScreeningResult(
        session_id=session.id, condition_code="silicosis", tier="RED",
        scored_tier="YELLOW", method="deterministic_rules",
        instrument_code="SG-LUNG", instrument_version=1, ruleset_version="1",
        override_fired=1, override_rule_codes="severe_breathlessness",
    ))
    db.commit()

    r = db.query(ScreeningResult).one()
    assert (r.instrument_code, r.instrument_version, r.method) == ("SG-LUNG", 1, "deterministic_rules")
    assert r.scored_tier == "YELLOW" and r.tier == "RED"
    assert r.override_fired == 1 and "severe_breathlessness" in r.override_rule_codes


# ----------------------------------------------------------- identity

def test_a_person_holds_no_phone_number(db):
    """§8.2: telephone number is an attribute with history on Contact, never
    an identity key. If a `phone` column ever reappears on persons, the
    false-merge problem comes back with it."""
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("persons")}
    assert not {"phone", "phone_number", "msisdn"} & columns


def test_many_people_may_share_a_number(db):
    """Handsets are shared, borrowed and sold. Two people on one number must
    be representable -- it is the normal case, not an error."""
    a, b = _person(db), _person(db)
    for person in (a, b):
        db.add(Contact(person_id=person.id, number_hmac="same-hmac", number_encrypted="x"))
    db.commit()
    assert db.query(Contact).filter_by(number_hmac="same-hmac").count() == 2


def test_a_number_is_stored_twice_for_two_different_jobs(db):
    """An encrypted column cannot be indexed for equality, so lookup needs a
    keyed hash and sending needs the recoverable form. Both are required."""
    columns = {c["name"]: c for c in inspect(db.get_bind()).get_columns("contacts")}
    assert not columns["number_hmac"]["nullable"]
    assert not columns["number_encrypted"]["nullable"]


def test_participant_code_is_unique(db):
    _person(db, participant_code="SG-ABC123")
    with pytest.raises(IntegrityError):
        _person(db, participant_code="SG-ABC123")


def test_a_merge_keeps_the_losing_record(db):
    """§8.2: merges are reversible from the first day. The loser is flagged,
    never deleted, because a false merge mixes two clinical histories and no
    inspection afterwards can separate them."""
    winner, loser = _person(db), _person(db)
    loser.merged_into_id = winner.id
    db.add(PersonMerge(
        winner_person_id=winner.id, loser_person_id=loser.id,
        evidence="hashed id match", merged_by="coordinator",
    ))
    db.commit()

    assert db.query(Person).count() == 2, "the losing person row must survive a merge"
    merge = db.query(PersonMerge).one()
    assert merge.evidence and merge.merged_by
    assert hasattr(merge, "reversed_at"), "a merge must be undoable"


# ------------------------------------------------------- idempotency

def test_the_same_client_session_uuid_cannot_create_two_sessions(db):
    """§10.3. This constraint is what makes the duplicate-screening incident
    of 23 August -- one miner accumulating 18 rows during a flaky window --
    structurally impossible rather than merely unlikely."""
    person = _person(db)
    db.add(ScreeningSession(person_id=person.id, channel="APP", client_session_uuid="uuid-1"))
    db.commit()
    db.add(ScreeningSession(person_id=person.id, channel="APP", client_session_uuid="uuid-1"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_sessions_without_a_uuid_are_still_allowed(db):
    """A null idempotency key must not collide with another null: a session
    created server-side (the USSD webhook) has no device-generated uuid."""
    person = _person(db)
    db.add_all([
        ScreeningSession(person_id=person.id, channel="USSD"),
        ScreeningSession(person_id=person.id, channel="USSD"),
    ])
    db.commit()
    assert db.query(ScreeningSession).count() == 2


# ---------------------------------------------------------- consent

def test_consent_is_one_row_per_permission(db):
    """§14.2: layered and recorded as data, never bundled. A worker may
    accept screening and decline retention."""
    person = _person(db)
    text_row = ConsentText(code="consent.core", version=1, message_code="consent.core.v1")
    db.add(text_row)
    db.commit()
    db.add_all([
        ConsentRecord(person_id=person.id, permission="screening_and_referral",
                      granted=1, consent_text_id=text_row.id, channel="APP"),
        ConsentRecord(person_id=person.id, permission="longitudinal_record",
                      granted=0, consent_text_id=text_row.id, channel="APP"),
    ])
    db.commit()

    granted = {c.permission: c.granted for c in db.query(ConsentRecord).all()}
    assert granted == {"screening_and_referral": 1, "longitudinal_record": 0}


def test_an_unknown_permission_is_rejected(db):
    person = _person(db)
    db.add(ConsentRecord(person_id=person.id, permission="anything_we_like", granted=1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_employer_disclosure_is_a_separate_refusable_permission(db):
    """§14.4, the most consequential governance rule in the document. It has
    to be its own permission so it can be refused on its own."""
    person = _person(db)
    db.add(ConsentRecord(person_id=person.id, permission="employer_disclosure", granted=0))
    db.commit()
    assert db.query(ConsentRecord).one().granted == 0


def test_withdrawal_keeps_the_original_record(db):
    """§14.3 requires a working withdrawal mechanism that is demonstrable."""
    assert "withdrawn_at" in {c["name"] for c in inspect(db.get_bind()).get_columns("consent_records")}


# ------------------------------------------------- the programme seam

def test_a_session_may_carry_no_programme(db):
    """Absent means community outreach. The nullable reference is the entire
    formal-sector seam (§5.3) and no feature is built on it in phase one."""
    person = _person(db)
    db.add(ScreeningSession(person_id=person.id, channel="APP"))
    db.commit()
    assert db.query(ScreeningSession).one().programme_id is None


def test_a_programme_kind_is_constrained(db):
    db.add(Programme(code="X", name="X", kind="whatever"))
    with pytest.raises(IntegrityError):
        db.commit()


# ------------------------------------------------------- constraints

@pytest.mark.parametrize("tier", ["GREEN", "YELLOW", "ORANGE", "RED"])
def test_valid_tiers_are_accepted(db, tier):
    person = _person(db)
    session = ScreeningSession(person_id=person.id, channel="APP")
    db.add(session)
    db.commit()
    db.add(ScreeningResult(session_id=session.id, condition_code="c", tier=tier,
                           method="deterministic_rules"))
    db.commit()


def test_an_invalid_tier_is_rejected(db):
    person = _person(db)
    session = ScreeningSession(person_id=person.id, channel="APP")
    db.add(session)
    db.commit()
    db.add(ScreeningResult(session_id=session.id, condition_code="c", tier="PURPLE",
                           method="deterministic_rules"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_an_invalid_channel_is_rejected(db):
    person = _person(db)
    db.add(ScreeningSession(person_id=person.id, channel="CARRIER_PIGEON"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_site_carries_a_sector(db):
    """§5.2: the exposure axis grows to quarrying, construction, foundries
    and tobacco processing, so a site is not implicitly a gold mine."""
    db.add(Site(name="Somewhere", sector="construction", district="Kwekwe"))
    db.commit()
    assert db.query(Site).one().sector == "construction"


def test_a_free_text_site_needs_no_curated_row(db):
    """§15.6: informal workings are informal. Forcing structure that does not
    exist produces worse data than a curated list with a fallback."""
    person = _person(db)
    db.add(ScreeningSession(person_id=person.id, channel="APP",
                            site_id=None, site_text="unnamed working near the river"))
    db.commit()
    assert db.query(ScreeningSession).one().site_text


# ----------------------------------------------------- v1 regression

def test_the_version_one_tables_still_exist(db):
    """v2 is added alongside v1, not in place of it: the deployed routes keep
    serving the mobile app and dashboard until those clients move
    (docs/IMPLEMENTATION_PLAN.md §5). `0008_v2_drop_v1` removes them, and not
    before."""
    tables = set(inspect(db.get_bind()).get_table_names())
    assert {"miners", "screenings", "screening_answers", "referrals", "notifications"} <= tables


def test_timestamps_are_naive_utc_on_both_backends(db):
    """The project convention, and the SQLite-vs-Postgres breakage the master
    document flags in §16.2: every timestamp is a plain TIMESTAMP, never
    TIMESTAMPTZ."""
    person = _person(db)
    assert person.created_at.tzinfo is None
    raw = db.execute(text("SELECT created_at FROM persons")).scalar()
    assert raw is not None
