"""The predicate interpreter for clinical tier and safety rules.

Master Reference v1.0 §9.2: the tier cascade is "expressible entirely as
boolean logic over answer values". §12.2's corrections contain rules of the
form *(years > 10 AND any symptoms) OR (past TB AND any breathlessness)*,
which a (min_score, max_score) table cannot hold -- so rules are predicates
over a **closed** grammar, documented in `clinical/README.md`:

    {"all": [...]}  {"any": [...]}  {"not": p}
    {"answer": CODE, "in": [VALUE, ...]}
    {"score": CONDITION, "gte": N}   {"score": CONDITION, "lte": N}
    {"count": {"codes": [...], "in": [...]}, "gte": N}
    {"unknown": CODE}

Three properties matter more than elegance here, because this module decides
what a worker is told about his lungs:

1. **Nothing is ever evaluated dynamically.** No `eval`, no expression
   language, no import of rule code. The grammar is a fixed set of dict
   shapes and anything else raises.

2. **An unrecognised node is an error, never False.** A typo in a rule --
   `{"answers": ...}` for `{"answer": ...}` -- must not quietly evaluate
   false and silently stop a red flag from firing. It raises
   `PredicateError`, the validator catches it before merge, and the engine
   refuses to classify rather than classify wrongly.

3. **Unknown is a value, not an absence.** §12.2 item 10: an unanswered
   red-flag question must never default to a negative. `{"answer": ...}` is
   False for an unknown answer, and `{"unknown": CODE}` is the only node
   that is True for one -- so a rule can act on "he did not say" explicitly.

The same grammar is interpreted in JavaScript on the device, against the
same fixtures, which is what makes the channel-equivalence claim testable
(§10.1, §11.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class PredicateError(ValueError):
    """A rule is malformed. Never raised for an answer the engine dislikes --
    only for a predicate it cannot interpret."""


@dataclass(frozen=True)
class EvalContext:
    """Everything a predicate may read. Deliberately small: a predicate can
    see this worker's answers and the scores already computed for him, and
    nothing else -- no database, no clock, no previous session. Deterioration
    is applied by the engine around the predicates, not inside them, so that
    a rule stays a pure function of the answers in front of it."""

    #: question code -> recorded answer value, for questions actually answered
    answers: dict[str, str] = field(default_factory=dict)
    #: condition code -> score already computed for this session
    scores: dict[str, int] = field(default_factory=dict)
    #: questions answered with an explicit unknown/refused option, or asked
    #: and left unanswered. Both are "he did not tell us".
    unknown: frozenset[str] = frozenset()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PredicateError(message)


def evaluate(node, ctx: EvalContext, path: str = "predicate") -> bool:
    """True if `node` holds for `ctx`. Raises PredicateError on a malformed
    node, with the path to it."""
    _require(isinstance(node, dict), f"{path}: a predicate must be an object, got {type(node).__name__}")
    _require(len(node) >= 1, f"{path}: empty predicate")

    # `all` and `any` deliberately do NOT short-circuit.
    #
    # Python's builtins stop at the first False / first True, which would mean
    # a malformed sibling node goes unevaluated for some workers and raises
    # for others, depending on the answers in front of it. A broken rule would
    # then be detected intermittently -- the one property this engine exists
    # to remove. Every child is evaluated so that an unusable instrument fails
    # the same way for everyone, immediately. These trees are a handful of
    # nodes over a handful of answers; there is no performance argument on the
    # other side.
    if "all" in node:
        _require(set(node) == {"all"}, f"{path}: 'all' takes no sibling keys, got {sorted(node)}")
        children = node["all"]
        _require(isinstance(children, list) and children, f"{path}.all: expected a non-empty list")
        outcomes = [evaluate(c, ctx, f"{path}.all[{i}]") for i, c in enumerate(children)]
        return all(outcomes)

    if "any" in node:
        _require(set(node) == {"any"}, f"{path}: 'any' takes no sibling keys, got {sorted(node)}")
        children = node["any"]
        _require(isinstance(children, list) and children, f"{path}.any: expected a non-empty list")
        outcomes = [evaluate(c, ctx, f"{path}.any[{i}]") for i, c in enumerate(children)]
        return any(outcomes)

    if "not" in node:
        _require(set(node) == {"not"}, f"{path}: 'not' takes no sibling keys, got {sorted(node)}")
        return not evaluate(node["not"], ctx, f"{path}.not")

    if "answer" in node:
        _require(set(node) == {"answer", "in"}, f"{path}: 'answer' requires exactly 'in', got {sorted(node)}")
        code = node["answer"]
        values = node["in"]
        _require(isinstance(code, str), f"{path}.answer: expected a question code")
        _require(isinstance(values, list) and values, f"{path}.in: expected a non-empty list")
        # An unknown answer is not a value: a rule asking "is it severe?"
        # must be False when he did not say, and {"unknown": CODE} is how a
        # rule acts on that instead.
        if code in ctx.unknown:
            return False
        return ctx.answers.get(code) in set(values)

    if "score" in node:
        _require(
            set(node) <= {"score", "gte", "lte"} and ("gte" in node or "lte" in node),
            f"{path}: 'score' requires 'gte' and/or 'lte', got {sorted(node)}",
        )
        condition = node["score"]
        _require(isinstance(condition, str), f"{path}.score: expected a condition code")
        # A condition with no scored answers scores zero; that is a real
        # score, not a missing one.
        value = ctx.scores.get(condition, 0)
        if "gte" in node:
            _require(isinstance(node["gte"], int), f"{path}.gte: expected an integer")
            if value < node["gte"]:
                return False
        if "lte" in node:
            _require(isinstance(node["lte"], int), f"{path}.lte: expected an integer")
            if value > node["lte"]:
                return False
        return True

    if "count" in node:
        _require(set(node) == {"count", "gte"}, f"{path}: 'count' requires exactly 'gte', got {sorted(node)}")
        spec = node["count"]
        _require(isinstance(spec, dict) and set(spec) == {"codes", "in"},
                 f"{path}.count: expected {{codes, in}}, got {sorted(spec) if isinstance(spec, dict) else type(spec).__name__}")
        codes, values = spec["codes"], spec["in"]
        _require(isinstance(codes, list) and codes, f"{path}.count.codes: expected a non-empty list")
        _require(isinstance(values, list) and values, f"{path}.count.in: expected a non-empty list")
        _require(isinstance(node["gte"], int), f"{path}.gte: expected an integer")
        wanted = set(values)
        hits = sum(
            1 for c in codes
            if c not in ctx.unknown and ctx.answers.get(c) in wanted
        )
        return hits >= node["gte"]

    if "unknown" in node:
        _require(set(node) == {"unknown"}, f"{path}: 'unknown' takes no sibling keys, got {sorted(node)}")
        code = node["unknown"]
        _require(isinstance(code, str), f"{path}.unknown: expected a question code")
        return code in ctx.unknown

    # Reached only by a node the grammar does not define. Raising is the
    # whole point: a mistyped rule must stop the build and the engine, not
    # evaluate false and let a red flag through unnoticed.
    raise PredicateError(
        f"{path}: unrecognised predicate {sorted(node)}. "
        f"The grammar is all, any, not, answer, score, count, unknown "
        f"(see clinical/README.md)."
    )


def referenced_questions(node, path: str = "predicate") -> set[str]:
    """Every question code a predicate depends on. Used by the validator and
    by the engine's applicability check."""
    out: set[str] = set()
    if not isinstance(node, dict):
        return out
    for key in ("all", "any"):
        for i, child in enumerate(node.get(key) or []):
            out |= referenced_questions(child, f"{path}.{key}[{i}]")
    if "not" in node:
        out |= referenced_questions(node["not"], f"{path}.not")
    if isinstance(node.get("answer"), str):
        out.add(node["answer"])
    if isinstance(node.get("unknown"), str):
        out.add(node["unknown"])
    spec = node.get("count")
    if isinstance(spec, dict):
        out |= {c for c in (spec.get("codes") or []) if isinstance(c, str)}
    return out
