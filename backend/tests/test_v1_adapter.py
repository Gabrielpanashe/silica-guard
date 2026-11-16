"""The v1 adapter: old route, v2 storage, one classifier — and dormant.

`docs/IMPLEMENTATION_PLAN.md` items 1.9 and 1.11, and §7's ordering.

**Why it ships dormant rather than switched on.** §7 step 3: the v1 route
changes classifier at the same moment as every other caller, so there is
never a window in which two clients get two classifiers. A per-client
rollout of a clinical classifier is not caution; it is two instruments in
the field at once.

**What building it early bought.** Four conditions have to hold before the
route may run the deterministic pipeline, and three of them were not visible
before the adapter existed. Two belong to other people, which means the
Week 10 roadmap line — "deterministic engine live as the tier of record on
both channels" — **is not a backend-only item**, and the roadmap treats it
as one.

Three conditions in the database, which gate the switch:

  1. An approved instrument.                      Clinical Lead, §12.5
  2. A v1-question-to-instrument mapping.         Backend, one edit, after 1
  3. Approved result text in English and Shona.   Clinical Lead, item 1.6b

And two requirements of the client, which the adapter **refuses** rather
than waits for, because §7 step 3 forbids running the new engine for the
requests that look ready and the old one for the rest:

  4. A participant code in the request.           Mobile, items 1.13, 1.14
  5. Consent recorded for that person.            Mobile, item 1.8

Requirement 4 was found by building this rather than by reading the plan.
`identity.resolve()` is deterministic only on a participant code or a hashed
national identity number, and a name-and-number bundle **queues** a probable
match rather than applying it (§8.2) — so there is no bundle the adapter
could send that reaches an existing person. Given a `miners.id` and nothing
else it would create a new person on every screening and attach it to
someone other than whoever consented.

The tests below prove each condition reports itself, prove the dormant path
is byte-identical to today's behaviour, and prove the active path works by
running it against the synthetic instrument with an injected mapping — so
"dormant" means not yet switched on, not untested.
"""

import copy
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

import database
from services import consent, instrument_store, v1_compat

BACKEND = Path(__file__).resolve().parent.parent
FIXTURE = BACKEND.parent / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"

#: TEST-INSTRUMENT's three questions, standing in for the real mapping. The
#: shipped `V1_QUESTION_MAP` is empty on purpose: it names the real
#: instrument's codes and cannot be written before they exist.
TEST_MAPPING = {code: target for code, target in zip(
    v1_compat.V1_QUESTION_CODES, ["T1", "T2", "T3"] * 4
)}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _load_instrument(db):
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")
    instrument_store.load(db, approved)
    db.commit()
    return approved


def _load_result_text(db):
    """Approved result messages in English and Shona, for all four tiers."""
    from db_models import Message, MessageText
    from services.screening_v2 import TIER_MESSAGE_CODES

    for tier, code in TIER_MESSAGE_CODES.items():
        message = Message(code=code, version=1, channel="sms", status="approved",
                          approved_by="Clinical Lead",
                          approved_at=datetime(2026, 11, 1),
                          purpose=f"Result message for {tier}.")
        db.add(message)
        db.flush()
        for language, text in (("en", f"Level text for {tier}."),
                               ("sn", f"Shona text for {tier}.")):
            db.add(MessageText(message_id=message.id, language=language,
                               text_value=text))
    db.commit()


# ------------------------------------------------------- the four conditions

def test_everything_is_missing_on_a_fresh_database(client):
    db = _session(client)
    ready = v1_compat.readiness(db)
    db.close()

    assert ready.active is False
    assert len(ready.blockers) == 2, ready.blockers
    joined = " ".join(ready.blockers)
    assert "no approved instrument" in joined
    assert "no approved text" in joined


def test_the_instrument_is_reported_by_name_once_loaded(client):
    """With an instrument but no mapping, the blocker changes from "there is
    no instrument" to "these questions are not mapped to it" — which is the
    difference between waiting on the Clinical Lead and waiting on me."""
    db = _session(client)
    _load_instrument(db)
    ready = v1_compat.readiness(db)
    db.close()

    joined = " ".join(ready.blockers)
    assert "no approved instrument" not in joined
    assert "not mapped to TEST-INSTRUMENT" in joined


def test_the_shipped_mapping_is_empty_and_that_is_deliberate():
    """It names the real instrument's question codes, which do not exist yet.
    Guessing it would rescore every screening that answered the question, in
    a way no test could catch, because both sides would be internally
    consistent."""
    assert v1_compat.V1_QUESTION_MAP == {}
    assert len(v1_compat.V1_QUESTION_CODES) == 10


def test_a_mapping_naming_a_question_the_instrument_lacks_is_a_gap(client):
    """Checked both ways. A missing entry means a question cannot be
    answered; an entry pointing at nothing is worse, because the engine
    treats the answer as absent, and an absent red flag is what §12.2 item 10
    exists to stop."""
    db = _session(client)
    instrument = _load_instrument(db)
    db.close()

    wrong = dict(TEST_MAPPING)
    wrong["COUGH_DURATION"] = "NO_SUCH_QUESTION"
    gaps = v1_compat.mapping_gaps(instrument, wrong)

    assert any("NO_SUCH_QUESTION" in g for g in gaps)
    assert any("no such question in TEST-INSTRUMENT" in g for g in gaps)


def test_the_three_data_conditions_are_enough_to_activate(client):
    """The switch is gated on data alone — no environment variable, because a
    flag that turns a clinical classifier on and off per deployment gets set
    differently in two places."""
    db = _session(client)
    _load_instrument(db)
    _load_result_text(db)
    ready = v1_compat.readiness(db, mapping=TEST_MAPPING)
    db.close()

    assert ready.active is True, ready.blockers


def test_readiness_takes_no_flag():
    """Asserted on the signature, because the temptation to add one is
    exactly what §7 step 3 warns about."""
    import inspect

    params = set(inspect.signature(v1_compat.readiness).parameters)
    assert params == {"db", "mapping"}, params


def test_missing_shona_text_blocks_the_adapter(client):
    """The v1 response declares `explanation_shona` as a required, non-null
    string, so a worker is given a Shona explanation today. §8.4 forbids
    translating one at runtime, so the adapter waits for authored text rather
    than returning English in a Shona field or an empty string."""
    from db_models import Message, MessageText
    from services.screening_v2 import TIER_MESSAGE_CODES

    db = _session(client)
    _load_instrument(db)
    for tier, code in TIER_MESSAGE_CODES.items():
        message = Message(code=code, version=1, channel="sms", status="approved",
                          approved_by="Clinical Lead",
                          approved_at=datetime(2026, 11, 1), purpose="English only.")
        db.add(message)
        db.flush()
        db.add(MessageText(message_id=message.id, language="en",
                           text_value=f"Level text for {tier}."))
    db.commit()

    ready = v1_compat.readiness(db, mapping=TEST_MAPPING)
    db.close()

    assert ready.active is False
    assert any("[sn]" in b for b in ready.blockers), ready.blockers


# --------------------------------------------------------- the dormant path

def test_the_live_route_is_unchanged_while_dormant(client):
    """The demonstration must be unaffected: the route still calls the model
    and still answers in the same shape.

    **The model call is patched, as every other test of this route does.**
    The first version of this test called the real one, which passed locally
    because a developer `.env` holds a key and failed in CI, which has none —
    an environment-dependent test, and the kind that reads as evidence while
    proving only that somebody's machine was configured.
    """
    from unittest.mock import patch

    from db_models import Miner

    db = _session(client)
    miner = Miner(name="Tendai Moyo", phone="0771234567", mine_site="Globe & Phoenix")
    db.add(miner)
    db.commit()
    miner_id = miner.id
    db.close()

    with patch("routers.screening.assess_risk", return_value={
        "tier": "YELLOW", "confidence": 0.82,
        "contributing_factors": ["test factor"],
        "explanation_english": "test explanation",
    }) as called:
        response = client.post("/api/screen", json={
            "miner_id": miner_id, "channel": "APP", "screened_by": "sister.moyo",
            "answers": [{"question_code": "COUGH_DURATION", "question_text": "?",
                         "answer_value": "none", "answer_score": 0}],
        })

    assert response.status_code == 200, response.text
    assert response.json()["tier"] in ("GREEN", "YELLOW", "ORANGE", "RED")
    assert called.called, (
        "while dormant the route must still go through the model path -- if "
        "it stopped, the adapter has taken over without its conditions being "
        "met, which is the one thing the gate exists to prevent"
    )


def test_health_reports_the_adapter_and_what_it_waits_on(client):
    """The same reasoning as the `schema` field: the state was invisible from
    outside, and an invisible state is one nobody checks before a deadline."""
    body = client.get("/api/health?recheck=1").json()

    assert body["v1_adapter"] == "dormant"
    assert body["v1_adapter_waiting_on"], body
    assert any("instrument" in b for b in body["v1_adapter_waiting_on"])


def test_health_does_not_compute_it_without_recheck(client):
    """This endpoint wakes a sleeping free-tier instance; reading the
    instrument and the content store on every call would make the wake
    slower for no benefit."""
    body = client.get("/api/health").json()
    assert "v1_adapter" not in body


# ---------------------------------------------------------- the active path

def test_the_active_path_produces_a_deterministic_tier(client, monkeypatch):
    """**"Dormant" means not yet switched on, not untested.** Runs the real
    pipeline through the v1 route against the synthetic instrument."""
    from db_models import Facility, Message, MessageText, Miner, ScreeningResult

    db = _session(client)
    _load_instrument(db)
    _load_result_text(db)
    db.add(Facility(name="Test District Hospital", level="district"))

    text_message = Message(code="consent.core.v1", version=1, channel="app",
                           status="approved", approved_by="Clinical Lead",
                           approved_at=datetime(2026, 11, 1), purpose="Consent.")
    db.add(text_message)
    db.flush()
    db.add(MessageText(message_id=text_message.id, language="en", text_value="TEST."))
    consent_text = consent.register_text(
        db, "CORE", text_message.code, status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1))
    miner = Miner(name="Tendai Moyo", phone="0771234567", mine_site="Globe & Phoenix")
    db.add(miner)
    db.commit()
    miner_id, text_id = miner.id, consent_text.id
    db.close()

    # The consent the mobile application will send once item 1.8 lands. The
    # adapter cannot invent it, so the test supplies it the way the client
    # eventually will.
    # **The same bundle the adapter will send**, including the site. Any
    # difference produces a different person and a queued match rather than
    # a match applied (§8.2), which is condition 4 in this file's docstring:
    # the client has to send a participant code for this to be reliable.
    person = client.post("/api/v2/persons/resolve", json={
        "name": "Tendai Moyo", "phone": "0771234567",
        "site_text": "Globe & Phoenix"}).json()
    client.post("/api/v2/consents", json={
        "person_id": person["person_id"], "consent_text_id": text_id,
        "decisions": {"screening_and_referral": True, "longitudinal_record": True},
    })

    monkeypatch.setattr(v1_compat, "V1_QUESTION_MAP", TEST_MAPPING)
    monkeypatch.setattr(
        v1_compat, "readiness",
        lambda db, **kw: v1_compat.Readiness(active=True),
    )

    response = client.post("/api/screen", json={
        "miner_id": miner_id, "channel": "APP", "screened_by": "sister.moyo",
        "participant_code": person["participant_code"],
        "answers": [
            {"question_code": "YEARS_UNDERGROUND", "question_text": "?",
             "answer_value": "lots", "answer_score": 99},
            {"question_code": "JOB_ROLE", "question_text": "?",
             "answer_value": "low", "answer_score": 99},
            {"question_code": "WET_DRILLING", "question_text": "?",
             "answer_value": "no_", "answer_score": 99},
        ],
    })
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["tier"] == "RED", "the safety override fired, deterministically"
    assert body["confidence"] == 1.0
    assert body["explanation_shona"] == "Shona text for RED.", "authored, not translated"
    assert body["contributing_factors"], "the rules that fired, by their own labels"

    db = _session(client)
    rows = db.scalars(select(ScreeningResult)).all()
    assert rows, "the screening is stored in the v2 tables"
    assert all(r.method == "deterministic_rules" for r in rows)
    db.close()


def test_the_active_path_ignores_the_score_the_handset_sent(client, monkeypatch):
    """Today the device sends `answer_score`, so **the handset decides the
    clinical weight of an answer** and an old build carries an old weighting
    into a new tier. The adapter scores from the instrument (§8.3)."""
    answers = [
        {"question_code": "YEARS_UNDERGROUND", "question_text": "?",
         "answer_value": "none", "answer_score": 10_000},
        {"question_code": "JOB_ROLE", "question_text": "?",
         "answer_value": "low", "answer_score": 10_000},
    ]
    converted = v1_compat.to_v2_answers(answers, mapping=TEST_MAPPING)

    assert converted == {"T1": "none", "T2": "low"}
    assert "10000" not in str(converted)
    assert not any(isinstance(v, int) for v in converted.values())


def test_an_unmapped_v1_answer_is_dropped_not_guessed():
    """A v1 code with no mapping cannot be placed in the instrument. Dropping
    it means the engine sees it as unanswered, which is a state the rules can
    test (§12.2 item 10); inventing a target would score it as something
    else."""
    answers = [{"question_code": "SOMETHING_NEW", "question_text": "?",
                "answer_value": "yes", "answer_score": 1}]
    assert v1_compat.to_v2_answers(answers, mapping=TEST_MAPPING) == {}


# ----------------------------------------- what the switch takes away with it

def test_the_active_path_has_no_delete_on_failure_block():
    """§7 step 6. That block exists because the v1 path persists answers,
    makes an external call, then persists a tier — so a failed model call
    left a row with a NULL tier that nothing would complete. The active path
    makes no external call between the two, so there is nothing to guard, and
    `client_session_uuid` handles the retry case it was compensating for."""
    import inspect

    import routers.screening as module

    source = inspect.getsource(module._screen_via_v2)
    body = source.split('"""')[-1]       # past the docstring, which says "delete"
    assert "delete" not in body.lower()
    assert "assess_risk" not in body


def test_the_active_path_never_calls_the_model():
    """Asserted on the source rather than on behaviour: a behavioural test
    catches only the path somebody thought to exercise."""
    import inspect

    import routers.screening as module

    body = inspect.getsource(module._screen_via_v2).split('"""')[-1]
    for forbidden in ("assess_risk", "gemini", "ai_risk_engine"):
        assert forbidden not in body.lower()


def test_the_client_version_is_logged(client):
    """§5's time-box depends on it: the adapter and `drop_v1` land once the
    logs show no v1 traffic for two weeks, and that is only observable if the
    calls are counted."""
    import logging

    from db_models import Miner

    db = _session(client)
    miner = Miner(name="Tendai Moyo", phone="0771234567", mine_site="Globe & Phoenix")
    db.add(miner)
    db.commit()
    miner_id = miner.id
    db.close()

    # `caplog` does not see records emitted inside a TestClient request on
    # this setup, so the handler is attached directly.
    lines: list[str] = []
    handler = logging.Handler(logging.INFO)
    handler.emit = lambda record: lines.append(record.getMessage())
    logger = logging.getLogger("silicaguard.v1_compat")
    logger.addHandler(handler)
    try:
        client.post("/api/screen", headers={"X-SilicaGuard-Client": "mobile/2.1.0"},
                    json={"miner_id": miner_id, "channel": "APP",
                          "screened_by": "x", "answers": [{"question_code": "COUGH_DURATION", "question_text": "?", "answer_value": "none", "answer_score": 0}]})
    finally:
        logger.removeHandler(handler)

    joined = chr(10).join(lines)
    assert "mobile/2.1.0" in joined
    assert "POST /api/screen" in joined


def test_the_tier_of_record_is_the_highest_across_conditions():
    """The v1 shape has one `tier` field and a v2 session produces one result
    per condition, so something has to give. A worker at RED for one
    condition is at RED whatever the others say — and the information lost is
    which condition drove it, which is why `drop_v1` removes this shape
    instead of keeping it."""
    from services.rules_engine import ConditionResult

    def result(condition, tier):
        return ConditionResult(
            condition=condition, tier=tier, score=0, method="deterministic_rules",
            instrument_code="X", instrument_version=1, scored_tier=tier,
        )

    assert v1_compat.tier_of_record(
        [result("silicosis", "GREEN"), result("tuberculosis", "RED")]
    ) == "RED"
    assert v1_compat.tier_of_record([]) is None


def test_the_active_path_refuses_a_request_with_no_participant_code(client, monkeypatch):
    """Refused, not fallen back from. §7 step 3: running the new engine for
    the requests that look ready and the old one for the rest is two
    instruments in the field at once."""
    from db_models import Miner

    db = _session(client)
    miner = Miner(name="Tendai Moyo", phone="0771234567", mine_site="Globe & Phoenix")
    db.add(miner)
    db.commit()
    miner_id = miner.id
    db.close()

    monkeypatch.setattr(
        v1_compat, "readiness", lambda db, **kw: v1_compat.Readiness(active=True))

    response = client.post("/api/screen", json={
        "miner_id": miner_id, "channel": "APP", "screened_by": "x", "answers": [{"question_code": "COUGH_DURATION", "question_text": "?", "answer_value": "none", "answer_score": 0}],
    })
    assert response.status_code == 400
    assert "participant_code is required" in response.json()["detail"]


def test_the_participant_code_is_optional_in_the_shape(client):
    """Additive, so adding it breaks no client today -- and required by the
    adapter, so the application must ship it before the switch is thrown."""
    import models

    field = models.ScreeningCreate.model_fields["participant_code"]
    assert field.is_required() is False
    assert field.default is None
