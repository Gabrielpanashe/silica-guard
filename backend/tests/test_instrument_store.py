"""Loading a reviewed instrument into the database, and reading it back.

Master Reference v1.0 §8.3. The decisive test here is the **round trip**:
an instrument loaded from YAML into the tables and read back must make the
rules engine produce identical results to the same instrument read straight
from the file. That is what proves the tables model the format faithfully
rather than approximately -- a missing column would show up as a different
tier, which is exactly the failure that must never reach a worker.

The fixture is the synthetic `clinical/examples/TEST-INSTRUMENT.yaml`
(codes T1-T3, meaning nothing). It carries `status: example`, which the
loader refuses, so these tests flip the status explicitly on a copy -- which
is itself one of the things worth testing.
"""

import copy
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import (
    AnswerBand,
    AnswerOption,
    Base,
    Instrument,
    InstrumentChannel,
    InstrumentQuestion,
    SafetyRule,
    ScoringRule,
    TierRule,
)
from services import instrument_store
from services.instrument_store import InstrumentLoadError
from services.rules_engine import Screening, classify, primary_tier

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'instr.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def loadable(doc: dict, status: str = "draft") -> dict:
    out = copy.deepcopy(doc)
    out["status"] = status
    if status == "approved":
        out["approved_by"] = "Clinical Lead"
        out["approved_at"] = "2026-11-01"
    return out


# ------------------------------------------------------- the round trip

#: Profiles chosen to exercise each branch of the fixture's cascade: a
#: baseline, a score band, the combination rule, a safety override, and the
#: unknown escalation.
PROFILES = [
    {"T1": "none", "T2": "low"},
    {"T1": "some", "T2": "mid", "T3": "no_"},
    {"T1": "some", "T2": "high", "T3": "yes_"},
    {"T1": "lots", "T2": "low", "T3": "no_"},
    {"T1": "unknown", "T2": "low"},
]


@pytest.mark.parametrize("answers", PROFILES, ids=lambda a: "-".join(sorted(a.values())))
def test_file_and_database_classify_identically(db, doc, answers):
    """The whole point of the tables. If a column were missing, a tier would
    differ here rather than somewhere in production."""
    from_file = loadable(doc)
    instrument_store.load(db, from_file)
    db.commit()
    from_db = instrument_store.read(db, from_file["code"], from_file["version"])

    screening = Screening(answers=answers)
    file_results = classify(from_file, screening)
    db_results = classify(from_db, screening)

    assert [(r.condition, r.tier, r.score, r.override_rule_codes) for r in db_results] == \
           [(r.condition, r.tier, r.score, r.override_rule_codes) for r in file_results]
    assert primary_tier(db_results) == primary_tier(file_results)


def test_the_round_trip_preserves_deterioration_behaviour(db, doc):
    """tracked_for_trajectory survives the trip, so a re-screen escalates the
    same way from either source."""
    instrument_store.load(db, loadable(doc))
    db.commit()
    from_db = instrument_store.read(db, doc["code"], doc["version"])

    screening = Screening(answers={"T1": "some", "T2": "low", "T3": "no_"},
                          previous_answers={"T1": "none", "T2": "low"})
    r = classify(from_db, screening)[0]
    assert r.deterioration.changed and "T1" in r.deterioration.worsened_codes
    assert r.tier != r.scored_tier


def test_branching_and_channels_survive_the_round_trip(db, doc):
    """T3 is asked only when T1 is some/lots, and only on the app channel.
    Lose either and a USSD screening would be reported incomplete."""
    instrument_store.load(db, loadable(doc))
    db.commit()
    from_db = instrument_store.read(db, doc["code"], doc["version"])

    # On USSD, T3 is not asked, so its absence is not an incomplete screening.
    results = classify(from_db, Screening(answers={"T1": "some", "T2": "mid"}, channel="ussd"))
    assert results, "USSD subset must still classify"


# -------------------------------------------------------- what it writes

def test_every_part_of_the_document_reaches_a_table(db, doc):
    instrument_store.load(db, loadable(doc))
    db.commit()
    instrument = db.scalar(select(Instrument))

    assert instrument.code == "TEST-INSTRUMENT" and instrument.version == 1
    assert db.query(InstrumentQuestion).count() == len(doc["questions"])
    assert db.query(TierRule).count() == len(doc["tier_rules"])
    assert db.query(SafetyRule).count() == len(doc["safety_rules"])
    assert db.query(AnswerOption).count() == sum(len(q.get("options") or []) for q in doc["questions"])
    assert db.query(AnswerBand).count() == sum(len(q.get("bands") or []) for q in doc["questions"])
    assert db.query(ScoringRule).count() == sum(len(q.get("scores") or []) for q in doc["questions"])
    assert db.query(InstrumentChannel).count() == sum(len(q.get("channels") or []) for q in doc["questions"])


def test_predicates_are_stored_as_json_text_not_repr(db, doc):
    """Portability: a native JSON column behaves differently on SQLite and
    PostgreSQL, which §16.2 flags. Text holding JSON behaves the same on
    both, and must still parse."""
    import json
    instrument_store.load(db, loadable(doc))
    db.commit()
    for rule in db.scalars(select(TierRule)):
        assert isinstance(rule.predicate, str)
        json.loads(rule.predicate)


def test_the_unknown_option_flag_survives(db, doc):
    """is_unknown is what makes the `unknown` predicate meaningful rather
    than an inference from absence (§12.2 item 10)."""
    instrument_store.load(db, loadable(doc))
    db.commit()
    flagged = db.scalars(select(AnswerOption).where(AnswerOption.is_unknown == 1)).all()
    assert [o.value for o in flagged] == ["unknown"]


def test_citations_are_required_by_the_schema(db, doc):
    """§12.1: a citation for every question and every threshold. The column
    is NOT NULL, so a specification without them cannot be stored."""
    broken = loadable(doc)
    del broken["questions"][0]["citation"]
    with pytest.raises(KeyError):
        instrument_store.load(db, broken)


# -------------------------------------------------------- the two rules

def test_an_example_instrument_is_refused(db, doc):
    """`status: example` may never reach a database in any environment. A
    plausible invented question set that could be loaded is the single most
    dangerous artefact clinical/ could hold."""
    with pytest.raises(InstrumentLoadError, match="may never be loaded"):
        instrument_store.load(db, copy.deepcopy(doc))


def test_the_fixture_on_disk_is_still_an_example(doc):
    """Belt and braces: if someone flips the status in the file, the test
    above stops testing anything."""
    assert doc["status"] == "example"


def test_an_approved_version_cannot_be_overwritten(db, doc):
    """§8.3. Every screening result stores the version that produced it, so a
    result whose rules were edited afterwards is uninterpretable. A change is
    a new version."""
    instrument_store.load(db, loadable(doc, status="approved"))
    db.commit()

    edited = loadable(doc, status="approved")
    edited["tier_rules"][0]["priority"] = 999
    with pytest.raises(InstrumentLoadError, match="immutable"):
        instrument_store.load(db, edited)


def test_a_retired_version_cannot_be_overwritten(db, doc):
    instrument_store.load(db, loadable(doc, status="retired"))
    db.commit()
    with pytest.raises(InstrumentLoadError, match="immutable"):
        instrument_store.load(db, loadable(doc, status="retired"))


def test_a_draft_may_be_reloaded_in_place(db, doc):
    """A specification under review is edited repeatedly before approval;
    reloading must replace it cleanly rather than accumulating rows."""
    instrument_store.load(db, loadable(doc))
    db.commit()
    first = db.query(TierRule).count()

    instrument_store.load(db, loadable(doc))
    db.commit()
    assert db.query(Instrument).count() == 1
    assert db.query(TierRule).count() == first, "reload must not duplicate rules"


def test_a_new_version_sits_alongside_the_approved_one(db, doc):
    instrument_store.load(db, loadable(doc, status="approved"))
    db.commit()
    v2 = loadable(doc, status="draft")
    v2["version"] = 2
    v2["supersedes"] = 1
    instrument_store.load(db, v2)
    db.commit()

    assert db.query(Instrument).count() == 2
    assert instrument_store.read(db, doc["code"], 1)["status"] == "approved"
    assert instrument_store.read(db, doc["code"], 2)["supersedes"] == 1


# ------------------------------------------------------------ selection

def test_read_active_returns_the_highest_approved_version(db, doc):
    for version in (1, 2):
        d = loadable(doc, status="approved")
        d["version"] = version
        instrument_store.load(db, d)
    db.commit()
    assert instrument_store.read_active(db, doc["code"])["version"] == 2


def test_read_active_ignores_drafts(db, doc):
    approved = loadable(doc, status="approved")
    instrument_store.load(db, approved)
    draft = loadable(doc, status="draft")
    draft["version"] = 2
    instrument_store.load(db, draft)
    db.commit()
    assert instrument_store.read_active(db, doc["code"])["version"] == 1


def test_read_active_refuses_when_nothing_is_approved(db, doc):
    """An instrument must be approved by the Clinical Lead before it can
    classify anybody."""
    instrument_store.load(db, loadable(doc, status="draft"))
    db.commit()
    with pytest.raises(InstrumentLoadError, match="must be approved"):
        instrument_store.read_active(db, doc["code"])


def test_reading_an_unknown_instrument_raises(db):
    with pytest.raises(InstrumentLoadError, match="no instrument"):
        instrument_store.read(db, "NOPE", 1)
