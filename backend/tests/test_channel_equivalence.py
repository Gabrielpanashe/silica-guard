"""Channels are equivalent — asserted as a law, not as a per-case expectation.

`ARCHITECTURE.md` principle 4 and Master Reference v1.0 §13.1: a village
health worker's app session and a USSD self-screen must produce the same tier
from the same answers. `docs/IMPLEMENTATION_PLAN.md` item 1.16 names this file
as a Phase One exit criterion.

`test_instrument_regression.py` already checks the fixture profiles the
Clinical Lead wrote, one channel each. That proves the cases someone thought
of. **This file states the property over every answer the instrument offers**,
which is a different claim and the one principle 4 actually makes.

What equivalence does and does not mean:

  **It does not mean the channels ask the same questions.** §13.1 lets the
  Clinical Lead define a shorter USSD subset as data, because a long
  instrument plus consent does not fit a 180-second session.

  **It means the subset changes which questions are asked and nothing else.**
  Same answers in, same tier out. An answer to a question the channel does
  not ask is recorded and changes no result.

  **And it means a channel that has no defined subset is refused, not
  guessed.** An unrecognised channel would otherwise be given every question
  that names no `channels` and none of the limited ones — a silently
  different instrument, scored without complaint.

The failure this file exists to prevent is at the bottom:
`test_a_rule_on_an_app_only_question_breaks_the_other_channel` builds the
instrument an author could plausibly write and shows the two channels
disagreeing, then shows the validator refusing it. That mistake is invisible
in review and would reach a field pilot.
"""

import copy
import itertools
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

import database
from services import consent, instrument_store
from services.rules_engine import (
    CHANNELS,
    Screening,
    UnknownChannelError,
    applicable_questions,
    classify,
    primary_tier,
)

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"

#: Every value the instrument offers for the two questions both channels ask,
#: plus the app-only question. The cross product is the point: a law stated
#: over one hand-picked case is an example.
T1 = ["none", "some", "lots", "unknown"]
T2 = ["low", "mid", "high"]
T3 = ["yes_", "no_"]


@pytest.fixture(scope="module")
def instrument():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _result_shape(results):
    """Everything about a result that a channel must not influence.

    Deliberately not the whole object: `method` and the instrument version
    are also compared, because a channel that reached the same tier by a
    different route would still be a divergence worth failing on.
    """
    return sorted(
        (r.condition, r.tier, r.score, r.scored_tier, r.method,
         tuple(sorted(r.override_rule_codes)))
        for r in results
    )


# ------------------------------------------------------- the law, over the engine

@pytest.mark.parametrize("t1,t2,t3", list(itertools.product(T1, T2, T3)))
def test_the_same_answers_classify_identically_on_every_channel(instrument, t1, t2, t3):
    """**The property.** 24 answer sets × every channel pair.

    T3 is asked only on the app. Submitting it over USSD anyway — which a
    client replaying a queued session can do — must record it and change
    nothing, because no rule references it.
    """
    answers = {"T1": t1, "T2": t2, "T3": t3}
    shapes = {
        channel: _result_shape(classify(instrument, Screening(answers=dict(answers), channel=channel)))
        for channel in CHANNELS
    }
    first = shapes[CHANNELS[0]]
    for channel, shape in shapes.items():
        assert shape == first, (
            f"{channel} classified {answers} differently from {CHANNELS[0]}: "
            f"{shape} != {first}"
        )


@pytest.mark.parametrize("t1,t2,t3", list(itertools.product(T1, T2, T3)))
def test_the_primary_tier_matches_on_every_channel(instrument, t1, t2, t3):
    """The number a worker is actually told."""
    answers = {"T1": t1, "T2": t2, "T3": t3}
    tiers = {
        channel: primary_tier(classify(instrument, Screening(answers=dict(answers), channel=channel)))
        for channel in CHANNELS
    }
    assert len(set(tiers.values())) == 1, tiers


def test_deterioration_is_channel_independent(instrument):
    """A worker who screened on the app in March and over USSD in June must
    have his worsening detected. If the comparison were channel-sensitive the
    trend would reset every time he changed handsets."""
    previous = {"T1": "none", "T2": "low"}
    answers = {"T1": "some", "T2": "low", "T3": "no_"}
    shapes = {
        channel: _result_shape(classify(instrument, Screening(
            answers=dict(answers), channel=channel, previous_answers=dict(previous))))
        for channel in CHANNELS
    }
    assert len(set(map(str, shapes.values()))) == 1, shapes


def test_an_answer_to_a_question_the_channel_does_not_ask_changes_nothing(instrument):
    """Stated on its own because it is what makes the parametrised law above
    meaningful rather than vacuous."""
    base = {"T1": "some", "T2": "mid"}
    without = classify(instrument, Screening(answers=dict(base), channel="ussd"))
    with_t3 = classify(instrument, Screening(answers={**base, "T3": "yes_"}, channel="ussd"))
    assert _result_shape(without) == _result_shape(with_t3)


# ---------------------------------------------- what the subset may and may not do

def test_the_channel_subset_only_removes_questions(instrument):
    """USSD's question set must be a subset of the app's, not a different set.
    A question asked over USSD and not in the app would mean the app's
    instrument is missing something the rules might reference."""
    app = set(applicable_questions(instrument, Screening(answers={"T1": "some", "T2": "mid", "T3": "no_"}, channel="app")))
    ussd = set(applicable_questions(instrument, Screening(answers={"T1": "some", "T2": "mid", "T3": "no_"}, channel="ussd")))
    assert ussd <= app, f"USSD asks questions the app does not: {sorted(ussd - app)}"


def test_completeness_is_judged_against_this_channels_questions(instrument):
    """§13.1. The app-only question becomes applicable when T1 is `some`, so
    the app session is incomplete without it and the USSD session is complete
    — which is the one place the channels legitimately differ, and it differs
    in what is *asked*, never in how an answer is *scored*."""
    from services.rules_engine import IncompleteScreeningError

    partial = {"T1": "some", "T2": "mid"}
    classify(instrument, Screening(answers=dict(partial), channel="ussd"))  # fine
    with pytest.raises(IncompleteScreeningError) as raised:
        classify(instrument, Screening(answers=dict(partial), channel="app"))
    assert raised.value.missing == ["T3"]


# --------------------------------------------------- a channel nobody defined

@pytest.mark.parametrize("channel", ["sms", "whatsapp", "APP", "", "web"])
def test_an_unrecognised_channel_is_refused_rather_than_guessed(instrument, channel):
    """**Refused, not defaulted.** `_applies_to_channel` returns False for
    every limited question and True for every unlimited one, so an unknown
    channel would be handed an instrument nobody authored and scored without
    complaint. `"APP"` is in this list on purpose: the wire format is upper
    case and the engine's is lower, so the conversion belongs at the boundary
    and a leak through it must fail loudly."""
    with pytest.raises(UnknownChannelError):
        classify(instrument, Screening(answers={"T1": "none", "T2": "low"}, channel=channel))


def test_the_channel_set_has_one_definition():
    """`routers/instruments.py` imports it rather than repeating it. Two
    copies would be two answers to "does USSD ask T3?"."""
    from routers import instruments

    assert instruments.CHANNELS is CHANNELS


def test_the_schema_the_clinical_lead_writes_against_agrees(instrument):
    """The runtime tuple and the JSON Schema enum are different files; a
    channel added to one and not the other is a question the engine would
    quietly never ask."""
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import validate_instrument

    schema = json.loads(validate_instrument.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(validate_instrument._schema_channels(schema)) == set(CHANNELS)


# ------------------------------------------- the authoring trap, and its guard

def _rule_on_the_app_only_question(instrument, node):
    """TEST-INSTRUMENT with one extra safety rule referencing T3, which only
    the app asks."""
    broken = copy.deepcopy(instrument)
    broken["safety_rules"].append({
        "code": "trap",
        "forces_tier": "RED",
        "predicate": node,
        "label": "A rule on a question one channel never asks",
        "citation": "Not applicable — synthetic test fixture.",
    })
    return broken


def test_a_rule_on_an_app_only_question_breaks_the_other_channel(instrument):
    """**The failure the validator rule exists for, demonstrated before being
    guarded against.**

    `{"unknown": "T3"}` is the §12.2 item 10 protection — an unanswered red
    flag must not read as a negative. Pointed at a question USSD never asks,
    it is true for *every real* USSD session, because the engine derives
    `unknown` from "no answer recorded" and a question nobody asked has none.
    Every USSD screening comes out RED; every app screening does not.
    Direction-safe, operationally useless, and invisible in review.

    **And invisible to the law above**, which is why the validator rule
    matters rather than the test suite alone: hand both channels the identical
    answer dictionary and they still agree, because the channel is genuinely
    not an input to classification. The divergence appears only once the USSD
    session carries what a USSD session actually carries — the questions that
    channel asks, and no more.
    """
    broken = _rule_on_the_app_only_question(instrument, {"unknown": "T3"})

    identical = {"T1": "none", "T2": "low", "T3": "no_"}
    assert (
        primary_tier(classify(broken, Screening(answers=dict(identical), channel="app")))
        == primary_tier(classify(broken, Screening(answers=dict(identical), channel="ussd")))
    ), "the law still holds, which is exactly why this mistake survives review"

    # What the two channels really send for the same worker.
    app = primary_tier(classify(broken, Screening(
        answers={"T1": "none", "T2": "low", "T3": "no_"}, channel="app")))
    ussd = primary_tier(classify(broken, Screening(
        answers={"T1": "none", "T2": "low"}, channel="ussd")))
    assert app == "GREEN"
    assert ussd == "RED", "the trap, reproduced"
    assert app != ussd


def test_the_validator_refuses_a_rule_on_a_question_a_channel_does_not_ask(instrument, tmp_path):
    """So the instrument above cannot be merged. Both directions are checked
    because they fail oppositely: `unknown` over-fires, `answer` never fires."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import json

    import validate_instrument

    schema = json.loads(validate_instrument.SCHEMA_PATH.read_text(encoding="utf-8"))

    for node, expected in (
        ({"unknown": "T3"}, "fires on EVERY ussd session"),
        ({"answer": "T3", "in": ["yes_"]}, "can never match on ussd"),
    ):
        path = tmp_path / "BROKEN.yaml"
        path.write_text(yaml.safe_dump(_rule_on_the_app_only_question(instrument, node)),
                        encoding="utf-8")
        problems = validate_instrument.validate_file(path, schema)
        assert any("not asked on ussd" in p for p in problems), problems
        assert any(expected in p for p in problems), problems


def test_the_validator_refuses_branching_that_cannot_be_reached_on_a_channel(instrument, tmp_path):
    """The same trap one level down: a question every channel asks whose
    branching depends on one that is app-only is silently never asked over
    USSD."""
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import validate_instrument

    broken = copy.deepcopy(instrument)
    # T2 is asked on every channel; make it depend on the app-only T3.
    for question in broken["questions"]:
        if question["code"] == "T2":
            question["branching"] = {"answer": "T3", "in": ["yes_"]}

    path = tmp_path / "BROKEN.yaml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")
    schema = json.loads(validate_instrument.SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = validate_instrument.validate_file(path, schema)
    assert any("can never be reached there" in p for p in problems), problems


def test_the_shipped_fixture_passes_the_channel_rules(instrument, tmp_path):
    """The guard must not be so broad it rejects the legitimate case: T3 is
    app-only, which is allowed, because no rule references it."""
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import validate_instrument

    schema = json.loads(validate_instrument.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert validate_instrument.validate_file(FIXTURE, schema) == []


# ------------------------------------------------- through the route, end to end

@pytest.fixture
def ready(client):
    """An approved instrument, a facility, and two consented people — one per
    channel, because the same person screening twice would link the second
    session to the first and compare them."""
    from db_models import Facility, Message, MessageText

    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")

    db = next(client.app.dependency_overrides[database.get_db]())
    instrument_store.load(db, approved)
    db.add(Facility(name="Test District Hospital", level="district"))
    message = Message(code="consent.core.v1", version=1, channel="app",
                      status="approved", approved_by="Clinical Lead",
                      approved_at=datetime(2026, 11, 1), purpose="Test wording.")
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST."))
    text = consent.register_text(db, "CORE", message.code, status="approved",
                                 approved_by="Clinical Lead",
                                 approved_at=datetime(2026, 11, 1))
    db.commit()
    text_id = text.id
    db.close()

    people = []
    for name, phone in (("Tendai Moyo", "0771234567"), ("Rudo Phiri", "0772345678")):
        person = client.post("/api/v2/persons/resolve",
                             json={"name": name, "phone": phone}).json()
        client.post("/api/v2/consents", json={
            "person_id": person["person_id"], "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": True},
        })
        people.append(person["person_id"])
    return people


def _submit(client, person_id, channel, answers):
    response = client.post("/api/v2/screenings", json={
        "person_id": person_id,
        "client_session_uuid": str(uuid.uuid4()),
        "channel": channel,
        "answers": answers,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_the_route_produces_the_same_result_on_both_channels(client, ready):
    """The property through the whole §10.3 pipeline, not only the engine:
    identity, consent, the stored instrument, scoring, overrides, the result
    rows and the referral."""
    app_person, ussd_person = ready
    answers = {"T1": "lots", "T2": "low", "T3": "no_"}

    on_app = _submit(client, app_person, "APP", answers)
    on_ussd = _submit(client, ussd_person, "USSD", answers)

    def shape(body):
        return sorted(
            (r["condition"], r["tier"], r["score"], r["method"],
             tuple(sorted(r.get("override_rule_codes") or [])))
            for r in body["results"]
        )

    assert shape(on_app) == shape(on_ussd)
    assert on_app["primary_tier"] == on_ussd["primary_tier"] == "RED"


def test_both_channels_record_the_same_provenance(client, ready):
    """Every result row records the instrument and ruleset version it was
    produced by (principle 5). A channel pinned to a different version would
    be the same divergence a different rule set is."""
    from db_models import ScreeningResult

    app_person, ussd_person = ready
    answers = {"T1": "some", "T2": "mid", "T3": "no_"}
    _submit(client, app_person, "APP", answers)
    _submit(client, ussd_person, "USSD", answers)

    db = next(client.app.dependency_overrides[database.get_db]())
    rows = db.scalars(select(ScreeningResult)).all()
    provenance = {(r.instrument_code, r.instrument_version, r.ruleset_version) for r in rows}
    db.close()
    assert len(provenance) == 1, provenance


def test_the_route_refuses_a_channel_it_does_not_know(client, ready):
    """Before the session row exists, so nothing is stored attributed to a
    channel that does not exist — and nothing is lost, because no screening
    has been recorded yet."""
    from db_models import ScreeningSession

    app_person, _ = ready
    response = client.post("/api/v2/screenings", json={
        "person_id": app_person,
        "client_session_uuid": str(uuid.uuid4()),
        "channel": "WHATSAPP",
        "answers": {"T1": "none", "T2": "low"},
    })
    assert response.status_code == 400
    assert "not one of" in response.json()["detail"]

    db = next(client.app.dependency_overrides[database.get_db]())
    assert db.scalars(select(ScreeningSession)).all() == []
    db.close()


def test_the_instrument_served_to_a_device_is_the_same_document(client, ready):
    """Principle 4 is only guaranteed if the device's interpreter and the
    server's are given identical input. `channel` annotates; it must not
    filter."""
    app = client.get("/api/v2/instrument/active?channel=app").json()
    ussd = client.get("/api/v2/instrument/active?channel=ussd").json()

    assert app["instrument"] == ussd["instrument"], (
        "the document must not be filtered: a question absent from it can "
        "never be `unknown`, which would disarm §12.2 item 10's protection"
    )
    assert app["channel_questions"] != ussd["channel_questions"], (
        "and the annotation must actually say which subset this channel asks"
    )
    assert set(ussd["channel_questions"]) < set(app["channel_questions"])
