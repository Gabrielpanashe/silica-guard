"""The §10.3 screening pipeline, end to end.

Master Reference v1.0 §10.3, Figure 2. The order is deliberate and each step
exists because of a specific failure the previous design allowed, so the tests
here are mostly about *order* and about what survives a failure:

  **Answers are persisted before any scoring occurs.** A scoring failure
  leaves the session and its answers on disk with no result rows. The v1 path
  does the opposite — `routers/screening.py` **deletes** the screening when
  the model call fails.

  **Safety overrides run last**, after deterioration escalation, so no earlier
  step can be the final word on a red flag.

  **A duplicate submission does not create a second session.** The structural
  fix for the 23 August incident, where a model-flakiness window produced
  eighteen rows for one miner.

  **Consent for screening is a hard gate.** §14.2: without it there is no
  service.

  **Declined retention means no deterioration comparison** — §14.2's own
  example, and the one place the consent layering changes what the code does.

The instrument is the synthetic `TEST-INSTRUMENT` fixture (codes `T1`-`T3`,
meaning nothing), loaded as `approved` on a copy. Nothing clinical is invented
anywhere in this file.
"""

import copy
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import (
    Base,
    Facility,
    Message,
    MessageText,
    Referral,
    ScreeningAnswer,
    ScreeningResult,
    ScreeningSession,
)
from services import consent, identity, instrument_store, referrals_v2, screening_v2
from services.consent import ConsentMissing
from services.identity import IdentityBundle
from services.rules_engine import InstrumentError
from services.screening_v2 import IncompleteScreening, ScreeningRequest, ScreeningError

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def instrument(db, doc):
    approved = copy.deepcopy(doc)
    approved["status"] = "approved"
    approved["approved_by"] = "Clinical Lead"
    approved["approved_at"] = "2026-11-01"
    instrument_store.load(db, approved)
    db.add(Facility(name="Test District Hospital", level="district"))
    db.commit()
    return approved


@pytest.fixture
def consent_text(db):
    message = Message(
        code="consent.core.v1", version=1, channel="app", status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
        purpose="Stands in for approved consent wording.",
    )
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST wording."))
    text = consent.register_text(
        db, "CORE", message.code, status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
    )
    db.commit()
    return text


def make_person(db, consent_text, *, name="Tendai Moyo", phone="0771234567",
                screening=True, longitudinal=True):
    resolution = identity.resolve(db, IdentityBundle(name=name, phone=phone))
    db.commit()
    decisions = {}
    if screening:
        decisions["screening_and_referral"] = True
    if longitudinal is not None:
        decisions["longitudinal_record"] = bool(longitudinal)
    if decisions:
        consent.record_many(db, resolution.person_id, decisions,
                            consent_text_id=consent_text.id)
        db.commit()
    return resolution.person_id


def request_for(person_id, answers, **kwargs):
    kwargs.setdefault("client_session_uuid", str(uuid.uuid4()))
    return ScreeningRequest(person_id=person_id, answers=answers, **kwargs)


#: Answer profiles against the fixture's cascade. T1/T2/T3 mean nothing.
BASELINE = {"T1": "none", "T2": "low"}
BANDED = {"T1": "some", "T2": "mid", "T3": "no_"}
OVERRIDE = {"T1": "lots", "T2": "low", "T3": "no_"}


# ---------------------------------------------------- the pipeline in order

def test_a_screening_produces_one_result_row_per_condition(db, instrument, consent_text):
    """§8.1's single most important change, now visible end to end: a session
    produces a list of results, not a tier."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BASELINE))

    stored = db.scalars(select(ScreeningResult)).all()
    assert {r.condition_code for r in stored} == set(instrument["conditions"])
    assert len(outcome.results) == len(instrument["conditions"])
    assert outcome.primary_tier in ("GREEN", "YELLOW", "ORANGE", "RED")


def test_every_result_row_carries_its_provenance(db, instrument, consent_text):
    """§10.1: every clinical output is traceable to the instrument and rule
    that produced it, and says whether an override fired. Without this, a tier
    assigned before a threshold moved is uninterpretable."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, BASELINE))

    for row in db.scalars(select(ScreeningResult)).all():
        assert row.instrument_code == "TEST-INSTRUMENT"
        assert row.instrument_version == 1
        assert row.ruleset_version == "TEST-INSTRUMENT-v1"
        assert row.method == "deterministic_rules"
        assert row.scored_tier in ("GREEN", "YELLOW", "ORANGE", "RED")


def test_the_session_records_the_instrument_and_the_clock(db, instrument, consent_text):
    """Screening duration is a pilot indicator that cannot be added
    retrospectively (§13.3), so the clock starts in the schema."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BASELINE))

    session = db.get(ScreeningSession, outcome.session_id)
    assert session.instrument_code == "TEST-INSTRUMENT"
    assert session.instrument_version == 1
    assert session.started_at is not None and session.completed_at is not None
    assert session.completed_at >= session.started_at


def test_answers_are_persisted_against_the_session(db, instrument, consent_text):
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BANDED))

    answers = db.scalars(
        select(ScreeningAnswer).where(ScreeningAnswer.session_id == outcome.session_id)
    ).all()
    assert {a.question_code: a.answer_value for a in answers} == BANDED


def test_question_wording_is_never_copied_into_a_clinical_row(db, instrument, consent_text):
    """§8.4. The wording of a question is a patient-facing string and lives in
    the content store against a message code; copying it here would be a
    second, unreviewed copy of text a worker read."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, BANDED))
    assert all(a.question_text is None for a in db.scalars(select(ScreeningAnswer)).all())


def test_the_per_answer_score_column_is_left_alone(db, instrument, consent_text):
    """v2 scores per condition, so one score per answer cannot express it —
    the silicosis-shaped defect §8.1 names, in a different table."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, BANDED))
    assert all(a.answer_score is None for a in db.scalars(select(ScreeningAnswer)).all())


# ------------------------------------------- answers survive a late failure

def test_an_incomplete_screening_keeps_the_answers_and_produces_no_tier(
    db, instrument, consent_text
):
    """**The assertion that distinguishes this pipeline from the v1 one.**
    §13.1: a partially answered instrument must never produce a tier. Rule 7:
    a completed screening is never discarded. `routers/screening.py` deletes
    the screening when its model call fails; this keeps it.
    """
    person_id = make_person(db, consent_text)
    # T3 is applicable when T1 is `some`, and is not answered here.
    with pytest.raises(IncompleteScreening) as exc:
        screening_v2.screen(db, request_for(person_id, {"T1": "some", "T2": "mid"}))

    assert "T3" in exc.value.missing
    session = db.get(ScreeningSession, exc.value.session_id)
    assert session is not None, "the session must survive"
    assert db.query(ScreeningAnswer).count() == 2, "the answers must survive"
    assert db.query(ScreeningResult).count() == 0, "no tier may be produced"


def test_the_incomplete_error_names_the_session_so_it_is_not_resubmitted(
    db, instrument, consent_text
):
    """Resubmitting under the same idempotency key would only replay a
    resultless session, so the caller needs the session id to finish."""
    person_id = make_person(db, consent_text)
    key = str(uuid.uuid4())
    with pytest.raises(IncompleteScreening) as exc:
        screening_v2.screen(
            db,
            ScreeningRequest(
                person_id=person_id,
                client_session_uuid=key,
                answers={"T1": "some", "T2": "mid"},
            ),
        )
    assert exc.value.session_id == db.scalar(select(ScreeningSession.id))

    # And a replay of that key is refused rather than silently returning an
    # empty result.
    with pytest.raises(ScreeningError, match="nothing to replay"):
        screening_v2.screen(
            db,
            ScreeningRequest(
                person_id=person_id, client_session_uuid=key, answers=BASELINE
            ),
        )


# --------------------------------------------------------- idempotency

def test_a_repeat_submission_does_not_create_a_second_session(
    db, instrument, consent_text
):
    """The 23 August incident, structurally: a model-flakiness window produced
    eighteen duplicate rows for one miner because every mobile retry created a
    fresh screening. The idempotency key makes that impossible."""
    person_id = make_person(db, consent_text)
    key = str(uuid.uuid4())
    first = screening_v2.screen(
        db, ScreeningRequest(person_id=person_id, client_session_uuid=key, answers=BASELINE)
    )

    for _ in range(5):
        again = screening_v2.screen(
            db,
            ScreeningRequest(person_id=person_id, client_session_uuid=key, answers=BASELINE),
        )
        assert again.replayed is True
        assert again.session_id == first.session_id

    assert db.query(ScreeningSession).count() == 1
    assert db.query(ScreeningResult).count() == len(instrument["conditions"])


def test_a_replay_returns_what_the_worker_was_told_not_a_fresh_classification(
    db, instrument, consent_text, doc
):
    """The subtler reason a replay reads stored rows rather than re-running
    the engine: the instrument can be superseded between the first submission
    and the retry, and a retry must return what the worker was actually
    told."""
    person_id = make_person(db, consent_text)
    key = str(uuid.uuid4())
    first = screening_v2.screen(
        db, ScreeningRequest(person_id=person_id, client_session_uuid=key, answers=BASELINE)
    )

    # A second approved version with a different baseline tier.
    v2 = copy.deepcopy(doc)
    v2.update(status="approved", version=2, approved_by="Clinical Lead",
              approved_at="2026-11-02", supersedes=1)
    for rule in v2["tier_rules"]:
        if rule["tier"] == "GREEN":
            rule["tier"] = "YELLOW"
    instrument_store.load(db, v2)
    db.commit()

    again = screening_v2.screen(
        db, ScreeningRequest(person_id=person_id, client_session_uuid=key, answers=BASELINE)
    )
    assert again.instrument_version == 1, "the replay reports the version that ran"
    assert [r.tier for r in again.results] == [r.tier for r in first.results]


def test_a_missing_idempotency_key_is_refused(db, instrument, consent_text):
    """A channel that cannot produce one is a channel that will create
    duplicates."""
    person_id = make_person(db, consent_text)
    with pytest.raises(ScreeningError, match="client_session_uuid is required"):
        screening_v2.screen(
            db, ScreeningRequest(person_id=person_id, client_session_uuid="", answers=BASELINE)
        )


def test_different_keys_create_different_sessions(db, instrument, consent_text):
    """Two real screenings of the same worker must both be recorded."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, BASELINE))
    screening_v2.screen(db, request_for(person_id, BASELINE))
    assert db.query(ScreeningSession).count() == 2


# ------------------------------------------------------------- consent

def test_screening_is_refused_without_consent(db, instrument, consent_text):
    """§14.2: the core permission is required to proceed. Without it there is
    no service — and nothing is written."""
    person_id = make_person(db, consent_text, screening=False, longitudinal=None)
    with pytest.raises(ConsentMissing):
        screening_v2.screen(db, request_for(person_id, BASELINE))

    assert db.query(ScreeningSession).count() == 0
    assert db.query(ScreeningAnswer).count() == 0


def test_declined_retention_means_no_deterioration_comparison(
    db, instrument, consent_text
):
    """§14.2's own example, and the one place the consent layering changes
    what the code does. The screening still happens and the result is still
    real; it simply has no history attached."""
    person_id = make_person(db, consent_text, longitudinal=False)
    screening_v2.screen(db, request_for(person_id, BASELINE))
    second = screening_v2.screen(db, request_for(person_id, BANDED))

    assert second.longitudinal_linked is False
    session = db.get(ScreeningSession, second.session_id)
    assert session.previous_session_id is None
    assert all(not r.deterioration.compared for r in second.results)


def test_granted_retention_links_the_previous_session(db, instrument, consent_text):
    person_id = make_person(db, consent_text, longitudinal=True)
    first = screening_v2.screen(db, request_for(person_id, BASELINE))
    second = screening_v2.screen(db, request_for(person_id, BANDED))

    assert second.longitudinal_linked is True
    session = db.get(ScreeningSession, second.session_id)
    assert session.previous_session_id == first.session_id
    assert all(r.deterioration.compared for r in second.results)


def test_deterioration_escalates_and_is_recorded(db, instrument, consent_text):
    """Step 6 runs between scoring and overrides, so an escalation can raise a
    tier but can never outrank an override."""
    person_id = make_person(db, consent_text, longitudinal=True)
    screening_v2.screen(db, request_for(person_id, BASELINE))
    second = screening_v2.screen(db, request_for(person_id, BANDED))

    worsened = [r for r in second.results if r.deterioration.changed]
    assert worsened, "the fixture's tracked question moved none -> some"
    assert any(r.tier != r.scored_tier for r in worsened)
    assert any(
        row.deterioration_changed == 1 for row in db.scalars(select(ScreeningResult)).all()
    )


# ------------------------------------------------------------- identity

def test_a_screening_follows_a_merge_to_the_surviving_record(
    db, instrument, consent_text
):
    """A card presented after a merge still screens the right person."""
    winner = make_person(db, consent_text, phone="0771234567")
    loser = make_person(db, consent_text, phone="0789999999")
    identity.merge(db, winner, loser, merged_by="clerk")
    db.commit()

    outcome = screening_v2.screen(db, request_for(loser, BASELINE))
    assert outcome.person_id == winner


def test_an_unknown_person_is_refused_before_anything_is_written(db, instrument):
    with pytest.raises(Exception):
        screening_v2.screen(db, request_for(9999, BASELINE))
    assert db.query(ScreeningSession).count() == 0


# ---------------------------------------------------------- the instrument

def test_an_unapproved_instrument_cannot_screen_anybody(db, doc, consent_text):
    """An instrument must be approved by the Clinical Lead before it
    classifies anyone."""
    draft = copy.deepcopy(doc)
    draft["status"] = "draft"
    instrument_store.load(db, draft)
    db.commit()
    person_id = make_person(db, consent_text)

    with pytest.raises(ScreeningError, match="must be approved"):
        screening_v2.screen(db, request_for(person_id, BASELINE))
    assert db.query(ScreeningSession).count() == 0


def test_the_instrument_is_never_guessed_when_several_exist(db, instrument, consent_text, doc):
    """An instrument is chosen deliberately. Two in the database and no code
    given is an error, not a coin toss."""
    second = copy.deepcopy(doc)
    second.update(code="OTHER-INSTRUMENT", status="approved",
                  approved_by="Clinical Lead", approved_at="2026-11-01")
    instrument_store.load(db, second)
    db.commit()
    person_id = make_person(db, consent_text)

    with pytest.raises(ScreeningError, match="instrument_code must be given"):
        screening_v2.screen(db, request_for(person_id, BASELINE))


def test_a_named_instrument_is_used(db, instrument, consent_text):
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(
        db, request_for(person_id, BASELINE, instrument_code="TEST-INSTRUMENT")
    )
    assert outcome.instrument_code == "TEST-INSTRUMENT"


# ---------------------------------------------------------- the referral

def test_a_referring_tier_creates_a_referral_keyed_to_the_result(
    db, instrument, consent_text
):
    """§10.4 and item 1.10: the referral belongs to a result, not a session. A
    worker referred for one condition and later flagged for another needs two
    referrals with two deadlines."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, OVERRIDE))
    assert outcome.primary_tier in ("ORANGE", "RED")
    assert outcome.referrals

    referral = db.scalar(select(Referral))
    result_ids = {r.id for r in db.scalars(select(ScreeningResult)).all()}
    assert referral.result_id in result_ids
    assert referral.person_id == person_id
    assert referral.condition_code
    assert referral.referral_code.startswith("SG-")
    assert referral.deadline is not None


def test_the_referral_window_comes_from_the_instrument(db, instrument, consent_text):
    """§12.2 item 8. The v1 path hardcodes 48 hours and 14 days in
    `services/referrals.py:17`, numbers that appear in no approved document."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, OVERRIDE))

    referral = db.scalar(select(Referral))
    result = db.get(ScreeningResult, referral.result_id)
    expected = referrals_v2.referral_window(
        instrument, result.condition_code, result.tier
    )
    session = db.get(ScreeningSession, outcome.session_id)
    assert abs((referral.deadline - session.completed_at) - expected).total_seconds() < 120


def test_a_missing_window_refuses_rather_than_inventing_a_deadline(
    db, doc, consent_text
):
    """A deadline is a clinical instruction with a number on it, so an absent
    number is a missing instruction rather than a reason to pick one."""
    stripped = copy.deepcopy(doc)
    stripped.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")
    stripped["intervals"] = [
        i for i in stripped["intervals"] if i["tier"] not in ("ORANGE", "RED")
    ]
    instrument_store.load(db, stripped)
    db.add(Facility(name="Test District Hospital", level="district"))
    db.commit()
    person_id = make_person(db, consent_text)

    with pytest.raises(referrals_v2.ReferralError, match="states no referral window"):
        screening_v2.screen(db, request_for(person_id, OVERRIDE))

    # The answers and the results still stand -- rule 7.
    assert db.query(ScreeningAnswer).count() == 3
    assert db.query(ScreeningResult).count() >= 1


def test_a_non_referring_tier_creates_no_referral(db, instrument, consent_text):
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BASELINE))
    if outcome.primary_tier in ("GREEN", "YELLOW"):
        assert outcome.referrals == ()
        assert db.query(Referral).count() == 0


def test_the_referral_records_why_it_was_raised(db, instrument, consent_text):
    """So a facility reading the pre-alert knows what to look for, and an
    audit can reconstruct the decision."""
    import json

    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, OVERRIDE))
    referral = db.scalar(select(Referral))
    reasons = json.loads(referral.contributing_reasons)
    assert reasons["tier"] in ("ORANGE", "RED")
    assert reasons["instrument"] == "TEST-INSTRUMENT v1"
    assert "override_fired" in reasons


# ------------------------------------------------------- the outcome, §10.4

def test_closing_a_referral_captures_the_outcome(db, instrument, consent_text):
    """Without the finding, the pilot produces an operational result and no
    labelled dataset. With it, every completed referral is a training example
    nobody else in the country holds."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, OVERRIDE))
    code = db.scalar(select(Referral.referral_code))

    referral = referrals_v2.close_with_outcome(
        db, code, "attended_imaging_abnormal", recorded_by="nurse", notes="Upper zones."
    )
    db.commit()
    assert referral.status == "closed"
    assert referral.outcome == "attended_imaging_abnormal"
    assert referral.outcome_recorded_by == "nurse"
    assert referral.outcome_recorded_at is not None
    assert referral.attended_at is not None, "an attended outcome is attendance"


def test_a_not_attended_outcome_does_not_set_attendance(db, instrument, consent_text):
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, OVERRIDE))
    code = db.scalar(select(Referral.referral_code))

    referral = referrals_v2.close_with_outcome(
        db, code, "not_attended", recorded_by="nurse"
    )
    db.commit()
    assert referral.attended_at is None


def test_an_unknown_outcome_is_refused(db, instrument, consent_text):
    """The vocabulary is closed because the point of capturing it is a
    labelled dataset, and free text is not a label."""
    person_id = make_person(db, consent_text)
    screening_v2.screen(db, request_for(person_id, OVERRIDE))
    code = db.scalar(select(Referral.referral_code))

    with pytest.raises(referrals_v2.ReferralError, match="unknown outcome"):
        referrals_v2.close_with_outcome(db, code, "he seemed fine", recorded_by="nurse")


def test_closing_an_unknown_code_is_refused(db):
    with pytest.raises(referrals_v2.ReferralError, match="no referral"):
        referrals_v2.close_with_outcome(db, "SG-ZZZZ", "not_attended", recorded_by="x")


# --------------------------------------------------------------- the text

def test_nothing_is_sent_and_the_reason_is_recorded(db, instrument, consent_text):
    """§10.3: a messaging failure is recorded, never a lost screening. "No
    approved text exists yet" is a recorded reason rather than a silent skip —
    and there is deliberately no fallback sentence, because a placeholder
    shipped "for now" is how unreviewed text reaches people (§8.4)."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BASELINE))

    assert outcome.not_sent_reason
    assert all(not m.available for m in outcome.messages)
    assert all(m.text is None for m in outcome.messages)


def test_an_approved_message_is_selected_when_one_exists(db, instrument, consent_text):
    """The selector works; only the words are missing. Proven with an approved
    message so the wiring is not taken on trust."""
    person_id = make_person(db, consent_text)
    first = screening_v2.screen(db, request_for(person_id, BASELINE))
    code = screening_v2.TIER_MESSAGE_CODES[first.primary_tier]

    content_doc = {
        "area": "results",
        "messages": [
            {
                "code": code, "channel": "sms", "status": "approved",
                "approved_by": "Clinical Lead", "approved_at": "2026-11-01",
                "purpose": "Stands in for an approved tier result message.",
                "text": {"en": "TEST en result.", "sn": "TEST sn result.",
                         "nd": "TEST nd result."},
            }
        ],
    }
    from services import content_store

    content_store.load(db, content_doc)
    db.commit()

    outcome = screening_v2.screen(db, request_for(person_id, BASELINE))
    plan = next(m for m in outcome.messages if m.code == code)
    assert plan.available is True
    assert plan.text == "TEST en result."
    assert plan.language == "en"


def test_the_message_is_selected_in_the_persons_language(db, instrument, consent_text):
    """No machine translation anywhere: the person's language selects an
    authored row, and the plan reports which one was served."""
    resolution = identity.resolve(
        db, IdentityBundle(name="Tendai Moyo", phone="0771234567", language="sn")
    )
    db.commit()
    consent.record_many(
        db, resolution.person_id,
        {"screening_and_referral": True, "longitudinal_record": True},
        consent_text_id=consent_text.id,
    )
    db.commit()

    first = screening_v2.screen(db, request_for(resolution.person_id, BASELINE))
    code = screening_v2.TIER_MESSAGE_CODES[first.primary_tier]
    from services import content_store

    content_store.load(db, {
        "area": "results",
        "messages": [{
            "code": code, "channel": "sms", "status": "approved",
            "approved_by": "Clinical Lead", "approved_at": "2026-11-01",
            "purpose": "Stands in for an approved tier result message.",
            "text": {"en": "TEST en.", "sn": "TEST sn.", "nd": "TEST nd."},
        }],
    })
    db.commit()

    outcome = screening_v2.screen(db, request_for(resolution.person_id, BASELINE))
    plan = next(m for m in outcome.messages if m.code == code)
    assert plan.language == "sn" and plan.text == "TEST sn."


# ---------------------------------------------- no model on this path, ever

def test_the_pipeline_does_not_import_a_model_client():
    """`docs/IMPLEMENTATION_PLAN.md` §7 step 2: the v2 route is deterministic
    from its first commit. Asserted here as well as in
    test_content_runtime_rule.py, because this is the module where it would
    matter most."""
    import ast

    source = (Path(__file__).resolve().parent.parent / "services" / "screening_v2.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
    assert "google" not in imported
    assert "ai_risk_engine" not in str(imported)


def test_every_result_says_it_came_from_the_rules(db, instrument, consent_text):
    """`method` exists so that a future method is distinguishable in the data
    rather than inferred from a date. Today there is exactly one."""
    person_id = make_person(db, consent_text)
    outcome = screening_v2.screen(db, request_for(person_id, BANDED))
    assert {r.method for r in outcome.results} == {"deterministic_rules"}
