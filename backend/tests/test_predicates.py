"""The predicate interpreter.

Master Reference v1.0 §9.2. Every node type, and -- more importantly -- the
two behaviours that keep a mistake from becoming a wrong tier:

  * an unrecognised node RAISES rather than evaluating False, so a typo in a
    rule cannot silently stop a red flag from firing;
  * an unknown answer is not a value, so `{"answer": X, "in": [...]}` is
    False when the worker did not say, and `{"unknown": X}` is the only node
    that is True for it (§12.2 item 10).
"""

import pytest

from services.predicates import EvalContext, PredicateError, evaluate, referenced_questions


def ctx(answers=None, scores=None, unknown=()):
    return EvalContext(
        answers=answers or {},
        scores=scores or {},
        unknown=frozenset(unknown),
    )


# ------------------------------------------------------------------ answer

def test_answer_matches_a_listed_value():
    assert evaluate({"answer": "Q", "in": ["a", "b"]}, ctx({"Q": "a"})) is True


def test_answer_is_false_for_an_unlisted_value():
    assert evaluate({"answer": "Q", "in": ["a"]}, ctx({"Q": "z"})) is False


def test_answer_is_false_for_an_unanswered_question():
    assert evaluate({"answer": "Q", "in": ["a"]}, ctx({})) is False


def test_answer_is_false_when_the_worker_said_unknown():
    """The heart of §12.2 item 10. 'Is it severe?' must be False when he did
    not say -- not True, and not an error. A rule that wants to act on the
    silence uses {"unknown": ...}."""
    assert evaluate({"answer": "Q", "in": ["severe"]}, ctx({"Q": "unknown"}, unknown=["Q"])) is False


# ----------------------------------------------------------------- unknown

def test_unknown_is_true_only_for_an_unknown_answer():
    assert evaluate({"unknown": "Q"}, ctx({"Q": "unknown"}, unknown=["Q"])) is True
    assert evaluate({"unknown": "Q"}, ctx({"Q": "mild"})) is False


# ------------------------------------------------------------------- score

def test_score_gte_and_lte():
    c = ctx(scores={"cond": 5})
    assert evaluate({"score": "cond", "gte": 5}, c) is True
    assert evaluate({"score": "cond", "gte": 6}, c) is False
    assert evaluate({"score": "cond", "lte": 5}, c) is True
    assert evaluate({"score": "cond", "lte": 4}, c) is False


def test_score_supports_a_closed_band():
    c = ctx(scores={"cond": 5})
    assert evaluate({"score": "cond", "gte": 3, "lte": 7}, c) is True
    assert evaluate({"score": "cond", "gte": 6, "lte": 7}, c) is False


def test_a_condition_with_no_scored_answers_scores_zero():
    """Zero is a real score, not a missing one -- a GREEN baseline rule of
    {"score": c, "lte": 0} has to match a worker who answered nothing
    scoreable."""
    assert evaluate({"score": "cond", "lte": 0}, ctx()) is True


# ------------------------------------------------------------------- count

def test_count_counts_matching_answers():
    c = ctx({"A": "yes", "B": "yes", "C": "no"})
    assert evaluate({"count": {"codes": ["A", "B", "C"], "in": ["yes"]}, "gte": 2}, c) is True
    assert evaluate({"count": {"codes": ["A", "B", "C"], "in": ["yes"]}, "gte": 3}, c) is False


def test_count_does_not_count_unknown_answers():
    c = ctx({"A": "yes", "B": "unknown"}, unknown=["B"])
    assert evaluate({"count": {"codes": ["A", "B"], "in": ["yes"]}, "gte": 2}, c) is False


# ------------------------------------------------------------- composition

def test_all_any_not():
    c = ctx({"A": "yes", "B": "no"})
    assert evaluate({"all": [{"answer": "A", "in": ["yes"]}, {"answer": "B", "in": ["no"]}]}, c) is True
    assert evaluate({"all": [{"answer": "A", "in": ["yes"]}, {"answer": "B", "in": ["yes"]}]}, c) is False
    assert evaluate({"any": [{"answer": "A", "in": ["no"]}, {"answer": "B", "in": ["no"]}]}, c) is True
    assert evaluate({"not": {"answer": "A", "in": ["no"]}}, c) is True


def test_nesting_is_arbitrary_depth():
    c = ctx({"A": "yes"}, scores={"cond": 9})
    node = {"all": [{"any": [{"not": {"answer": "A", "in": ["no"]}}, {"score": "cond", "gte": 99}]}]}
    assert evaluate(node, c) is True


# ------------------------------------------------- malformed nodes raise

@pytest.mark.parametrize("node,fragment", [
    ({"answers": "Q", "in": ["a"]}, "unrecognised predicate"),
    ({"answer": "Q"}, "requires exactly 'in'"),
    ({"answer": "Q", "in": []}, "non-empty list"),
    ({"all": []}, "non-empty list"),
    ({"any": "nope"}, "non-empty list"),
    ({"score": "cond"}, "requires 'gte' and/or 'lte'"),
    ({"score": "cond", "gte": "5"}, "expected an integer"),
    ({"count": {"codes": ["A"]}, "gte": 1}, "expected {codes, in}"),
    ({"count": {"codes": ["A"], "in": ["y"]}}, "requires exactly 'gte'"),
    ({"unknown": "Q", "in": ["a"]}, "takes no sibling keys"),
    ({"all": [{"answer": "A", "in": ["x"]}], "any": []}, "no sibling keys"),
    ({}, "empty predicate"),
    ("not a dict", "must be an object"),
])
def test_malformed_nodes_raise_rather_than_evaluating_false(node, fragment):
    """This is the point of the whole module. A rule that cannot be
    interpreted must stop the engine, not quietly return False and let a red
    flag through."""
    with pytest.raises(PredicateError) as exc:
        evaluate(node, ctx({"A": "x"}))
    assert fragment in str(exc.value)


def test_the_error_names_the_path_to_the_bad_node():
    with pytest.raises(PredicateError) as exc:
        evaluate({"all": [{"answer": "A", "in": ["x"]}, {"bogus": 1}]}, ctx())
    assert "predicate.all[1]" in str(exc.value)


def test_a_bad_node_inside_any_still_raises_even_if_an_earlier_child_is_true():
    """`any` must not short-circuit past a malformed sibling: the rule is
    still broken and still needs fixing."""
    with pytest.raises(PredicateError):
        evaluate({"any": [{"answer": "A", "in": ["x"]}, {"bogus": 1}]}, ctx({"A": "x"}))


# ------------------------------------------------------ referenced_questions

def test_referenced_questions_collects_every_code():
    node = {"all": [
        {"answer": "A", "in": ["x"]},
        {"any": [{"unknown": "B"}, {"count": {"codes": ["C", "D"], "in": ["y"]}, "gte": 1}]},
        {"not": {"answer": "E", "in": ["z"]}},
    ]}
    assert referenced_questions(node) == {"A", "B", "C", "D", "E"}


def test_referenced_questions_ignores_condition_codes():
    assert referenced_questions({"score": "silicosis", "gte": 1}) == set()
