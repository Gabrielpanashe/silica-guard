"""The deterministic clinical rules engine.

Master Reference v1.0 §9.1: the rule cascade is the tier of record on every
channel. These tests pin the behaviour the clinical safety of the system
rests on -- above all the **order** of §10.3:

    score -> tier rule -> deterioration -> safety overrides LAST

and the rule that overrides raise and never lower. If a change makes
overrides run before deterioration, or lets anything lower a tier, these
fail.

The instrument under test is the synthetic `clinical/examples/
TEST-INSTRUMENT.yaml` (codes T1-T3, which mean nothing) plus small
purpose-built instruments defined inline. No clinical content is invented
here: instrument version one is the Clinical Lead's deliverable (§12.5).
"""

import copy
from pathlib import Path

import pytest
import yaml

from services.predicates import PredicateError
from services.rules_engine import (
    IncompleteScreeningError,
    InstrumentError,
    Screening,
    TIER_ORDER,
    applicable_questions,
    classify,
    primary_tier,
    score_condition,
)

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"


@pytest.fixture(scope="module")
def instrument():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def tier_of(results, condition):
    return next(r for r in results if r.condition == condition).tier


def result_for(results, condition):
    return next(r for r in results if r.condition == condition)


# --------------------------------------------------------------- scoring

def test_scores_are_per_condition(instrument):
    """The same answer weighs differently for different conditions, which is
    what lets a second condition be rows rather than columns (§8.3)."""
    answers = {"T1": "lots", "T2": "low"}
    assert score_condition(instrument, answers, "condition_a") == 5
    assert score_condition(instrument, answers, "condition_b") == 1


def test_unscored_questions_contribute_nothing(instrument):
    """T3 has no scores. Demographics are recorded and not scored, and that
    must stay valid."""
    base = {"T1": "some", "T2": "low"}
    assert score_condition(instrument, base, "condition_a") == \
        score_condition(instrument, {**base, "T3": "yes_"}, "condition_a")


def test_banded_questions_score_by_band(instrument):
    assert score_condition(instrument, {"T1": "none", "T2": "high"}, "condition_a") == 6


# ------------------------------------------------------------ tier rules

def test_first_matching_rule_by_descending_priority_wins(instrument):
    """T1=some,T2=mid scores 5: over the YELLOW band (>=3) but under the
    ORANGE combination rule, which needs score>=6."""
    results = classify(instrument, Screening(answers={"T1": "some", "T2": "mid", "T3": "no_"}))
    assert tier_of(results, "condition_a") == "YELLOW"


def test_the_combination_rule_fires_when_a_score_band_alone_would_not(instrument):
    """The shape §12.2 contains and a (min,max) table cannot express:
    score>=6 AND (T2=high OR two of T1/T3 answered positively)."""
    results = classify(instrument, Screening(answers={"T1": "some", "T2": "high", "T3": "no_"}))
    r = result_for(results, "condition_a")
    assert r.score == 8 and r.tier == "ORANGE"


def test_a_result_carries_its_provenance(instrument):
    """§10.1: every clinical output is traceable to the instrument and rule
    that produced it."""
    r = result_for(classify(instrument, Screening(answers={"T1": "none", "T2": "low"})), "condition_a")
    assert r.method == "deterministic_rules"
    assert r.instrument_code == "TEST-INSTRUMENT" and r.instrument_version == 1
    assert r.tier_rule_label


def test_one_result_per_condition(instrument):
    results = classify(instrument, Screening(answers={"T1": "none", "T2": "low"}))
    assert sorted(r.condition for r in results) == ["condition_a", "condition_b"]


def test_no_matching_tier_rule_raises_rather_than_guessing():
    inst = {
        "code": "X", "version": 1, "conditions": ["c"],
        "questions": [], "safety_rules": [],
        "tier_rules": [{"condition": "c", "tier": "RED", "priority": 10,
                        "predicate": {"score": "c", "gte": 99}}],
        "unknown_handling": {"partial_session_may_produce_tier": False},
    }
    with pytest.raises(InstrumentError, match="no tier rule matched"):
        classify(inst, Screening(answers={}))


# ------------------------------------------------- safety overrides, LAST

def test_safety_override_raises_the_tier(instrument):
    results = classify(instrument, Screening(answers={"T1": "lots", "T2": "low", "T3": "no_"}))
    r = result_for(results, "condition_a")
    assert r.tier == "RED" and r.override_fired
    assert "test_red_flag" in r.override_rule_codes
    assert r.scored_tier != "RED", "scored_tier must record the tier before the override"


def test_an_unscoped_safety_rule_applies_to_every_condition(instrument):
    results = classify(instrument, Screening(answers={"T1": "lots", "T2": "low", "T3": "no_"}))
    assert tier_of(results, "condition_a") == "RED"
    assert tier_of(results, "condition_b") == "RED"


def test_a_condition_scoped_safety_rule_applies_only_there(instrument):
    """test_unknown_escalation is scoped to condition_a."""
    results = classify(instrument, Screening(answers={"T1": "unknown", "T2": "low"}))
    assert tier_of(results, "condition_a") == "ORANGE"
    assert tier_of(results, "condition_b") == "GREEN"


def test_an_unanswered_red_flag_does_not_read_as_a_negative(instrument):
    """§12.2 item 10. Answering 'unknown' to T1 escalates rather than being
    scored as absent."""
    unknown = result_for(classify(instrument, Screening(answers={"T1": "unknown", "T2": "low"})), "condition_a")
    answered_none = result_for(classify(instrument, Screening(answers={"T1": "none", "T2": "low"})), "condition_a")
    assert unknown.tier == "ORANGE" and answered_none.tier == "GREEN"


def test_an_override_never_lowers_a_tier():
    """A safety rule forcing YELLOW on a worker already at RED must leave him
    at RED. §4.3: overrides raise and never lower."""
    inst = {
        "code": "X", "version": 1, "conditions": ["c"], "questions": [],
        "tier_rules": [
            {"condition": "c", "tier": "RED", "priority": 20, "predicate": {"score": "c", "lte": 0}},
            {"condition": "c", "tier": "GREEN", "priority": 10, "predicate": {"score": "c", "gte": 0}},
        ],
        "safety_rules": [
            {"code": "lowering_rule", "forces_tier": "YELLOW", "predicate": {"score": "c", "lte": 0}},
        ],
        "unknown_handling": {"partial_session_may_produce_tier": False},
    }
    r = classify(inst, Screening(answers={}))[0]
    assert r.tier == "RED"
    assert r.override_fired is False
    assert "lowering_rule" in r.non_raising_override_codes, (
        "a rule that matched but changed nothing must still be recorded"
    )


# --------------------------------------------------------- deterioration

def _two_session(instrument, now, before):
    return classify(instrument, Screening(answers=now, previous_answers=before))


def test_deterioration_escalates_one_level(instrument):
    """T1 none -> some is a worsening on a tracked question. Score 2 would be
    GREEN; the escalation makes it YELLOW."""
    results = _two_session(instrument, {"T1": "some", "T2": "low", "T3": "no_"}, {"T1": "none", "T2": "low"})
    r = result_for(results, "condition_a")
    assert r.scored_tier == "GREEN" and r.tier == "YELLOW"
    assert r.deterioration.changed and "T1" in r.deterioration.worsened_codes


def test_improvement_does_not_escalate(instrument):
    results = _two_session(instrument, {"T1": "none", "T2": "low"}, {"T1": "some", "T2": "low"})
    r = result_for(results, "condition_a")
    assert r.deterioration.compared and not r.deterioration.changed
    assert r.tier == r.scored_tier


def test_no_previous_screening_is_said_explicitly(instrument):
    """§4.3 module 2: says so when there is insufficient prior data rather
    than inferring."""
    r = result_for(classify(instrument, Screening(answers={"T1": "none", "T2": "low"})), "condition_a")
    assert r.deterioration.compared is False
    assert "No previous screening" in r.deterioration.summary


def test_untracked_questions_do_not_count_as_deterioration(instrument):
    """Only questions the Clinical Lead flagged tracked_for_trajectory. T2 is
    not flagged, so a worsening there must not escalate."""
    results = _two_session(instrument, {"T1": "none", "T2": "high"}, {"T1": "none", "T2": "low"})
    r = result_for(results, "condition_a")
    assert not r.deterioration.changed


def test_deterioration_cannot_exceed_red(instrument):
    results = _two_session(instrument, {"T1": "lots", "T2": "high", "T3": "yes_"}, {"T1": "none", "T2": "low"})
    assert tier_of(results, "condition_a") == "RED"


# ------------------------------------------- ORDER: overrides run last

def test_safety_overrides_run_after_deterioration():
    """The ordering §10.3 step 7 requires, as an outcome rather than a
    comment. Deterioration raises GREEN->YELLOW; the safety rule then forces
    RED. If overrides ran first, the escalation would raise RED's rank and
    the two steps would compose differently -- and more importantly, nothing
    after an override could be the last word on a red flag."""
    inst = {
        "code": "ORDER", "version": 1, "conditions": ["c"],
        "questions": [{
            "code": "Q", "block": "b", "clinical_label": "tracked",
            "response_type": "single_select", "label_message_code": "m.q",
            "tracked_for_trajectory": True, "citation": "synthetic",
            "options": [{"value": "lo", "label_message_code": "m.lo"},
                        {"value": "hi", "label_message_code": "m.hi"}],
            "scores": [{"condition": "c", "value": "lo", "score": 0},
                       {"condition": "c", "value": "hi", "score": 1}],
        }],
        "tier_rules": [{"condition": "c", "tier": "GREEN", "priority": 10,
                        "predicate": {"score": "c", "gte": 0}}],
        "safety_rules": [{"code": "flag", "forces_tier": "RED",
                          "predicate": {"answer": "Q", "in": ["hi"]}}],
        "unknown_handling": {"partial_session_may_produce_tier": False},
    }
    r = classify(inst, Screening(answers={"Q": "hi"}, previous_answers={"Q": "lo"}))[0]
    assert r.scored_tier == "GREEN"
    assert r.deterioration.changed is True
    assert r.tier == "RED" and r.override_fired, "the override must have the final word"


# -------------------------------------------- partial sessions and branching

def test_a_partial_session_produces_no_tier(instrument):
    """§13.1: a partially answered instrument must never produce a tier. The
    caller keeps the answers -- a screening is never discarded (§10.1) -- but
    there is no result."""
    with pytest.raises(IncompleteScreeningError) as exc:
        classify(instrument, Screening(answers={"T1": "some"}))
    assert "T2" in exc.value.missing


def test_a_skipped_branch_is_not_required(instrument):
    """T3 is asked only when T1 is some/lots. With T1=none it is not
    applicable, so its absence is not an incomplete screening."""
    results = classify(instrument, Screening(answers={"T1": "none", "T2": "low"}))
    assert tier_of(results, "condition_a") == "GREEN"


def test_a_live_branch_is_required(instrument):
    with pytest.raises(IncompleteScreeningError) as exc:
        classify(instrument, Screening(answers={"T1": "some", "T2": "low"}))
    assert "T3" in exc.value.missing


def test_applicable_questions_respects_branching_and_channel(instrument):
    on_app = applicable_questions(instrument, Screening(answers={"T1": "some", "T2": "low"}, channel="app"))
    on_ussd = applicable_questions(instrument, Screening(answers={"T1": "some", "T2": "low"}, channel="ussd"))
    assert "T3" in on_app and "T3" not in on_ussd


def test_a_channel_subset_still_classifies(instrument):
    """§13.1: the Clinical Lead defines a shorter USSD subset as data. The
    engine must classify from it rather than refuse."""
    results = classify(instrument, Screening(answers={"T1": "some", "T2": "mid"}, channel="ussd"))
    assert tier_of(results, "condition_a") == "YELLOW"


# --------------------------------------------------------------- misc

def test_primary_tier_is_the_highest_across_conditions(instrument):
    results = classify(instrument, Screening(answers={"T1": "unknown", "T2": "low"}))
    assert tier_of(results, "condition_b") == "GREEN"
    assert primary_tier(results) == "ORANGE"


def test_tier_order_is_lowest_to_highest():
    assert TIER_ORDER == ("GREEN", "YELLOW", "ORANGE", "RED")


def test_a_malformed_rule_raises_rather_than_classifying(instrument):
    """A wrong tier is worse than no tier."""
    broken = copy.deepcopy(instrument)
    broken["tier_rules"][0]["predicate"] = {"bogus": True}
    with pytest.raises(PredicateError):
        classify(broken, Screening(answers={"T1": "none", "T2": "low"}))


def test_an_instrument_with_no_conditions_raises():
    with pytest.raises(InstrumentError, match="no conditions"):
        classify({"code": "X", "version": 1, "conditions": []}, Screening(answers={}))


def test_classification_is_reproducible(instrument):
    """§9.2: a classifier whose output varies between calls cannot be
    validated in the ordinary sense."""
    screening = Screening(answers={"T1": "some", "T2": "mid", "T3": "yes_"},
                          previous_answers={"T1": "none", "T2": "low"})
    first = classify(instrument, screening)
    for _ in range(5):
        again = classify(instrument, screening)
        assert [(r.condition, r.tier, r.score) for r in again] == \
               [(r.condition, r.tier, r.score) for r in first]


def test_the_engine_does_not_mutate_its_inputs(instrument):
    """It is handed the instrument the rest of the system is using."""
    before = copy.deepcopy(instrument)
    answers = {"T1": "some", "T2": "mid", "T3": "no_"}
    classify(instrument, Screening(answers=answers))
    assert instrument == before
    assert answers == {"T1": "some", "T2": "mid", "T3": "no_"}
