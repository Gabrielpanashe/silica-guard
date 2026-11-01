"""The deterministic clinical rules engine.

Master Reference v1.0 §9.1: **the deterministic clinical rule cascade is the
tier of record, on every channel, online and offline.** No language model
sits between a set of answers and a tier. This module is that cascade.

It is a pure function of an instrument and a set of answers: no database, no
clock, no network, no global state. That is what makes it testable against
fixed answer profiles (the instrument regression suite, §11.7), runnable
identically on a handset with no connectivity (§10.1), and reproducible --
which validation requires and a prompted model cannot offer (§9.2).

Order of operations per condition, from §10.3 and not negotiable:

    1. score      sum the per-condition scores of the answers given
    2. tier       first matching tier rule, descending priority
    3. trajectory deterioration against the previous session may raise one level
    4. safety     safety rules run LAST and may raise, never lower

Step 4 is last so that no earlier step -- and no model, if one is ever
introduced upstream -- can be the final word on a red flag. Step 3 sits
before it for the same reason: an escalation must not be able to outrank an
override.

What this module does NOT do: load instruments from the database, persist
anything, send anything, or decide what a worker is told. It returns results
and the provenance of each, and the caller writes them.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.predicates import EvalContext, evaluate

#: Lowest to highest. The engine never lowers a tier, so this ordering is
#: load-bearing rather than cosmetic.
TIER_ORDER = ("GREEN", "YELLOW", "ORANGE", "RED")
_TIER_RANK = {tier: i for i, tier in enumerate(TIER_ORDER)}


class InstrumentError(ValueError):
    """The instrument is unusable: malformed, or asked to do something it
    does not define. Never raised for an unexpected answer."""


class IncompleteScreeningError(ValueError):
    """An applicable question was not answered and the instrument forbids a
    tier from a partial session (§13.1: "a partially answered instrument must
    never produce a tier"). The caller keeps the answers -- a screening is
    never discarded (§10.1) -- but no result is produced."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(
            "screening is incomplete; no tier may be produced from a partial "
            f"instrument. Unanswered applicable questions: {', '.join(missing)}"
        )


@dataclass(frozen=True)
class Deterioration:
    """Trajectory against the same worker's previous session. Deterministic
    engineering, not artificial intelligence (§4.3 module 2)."""

    compared: bool
    changed: bool
    worsened_codes: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class ConditionResult:
    """One result row's worth of outcome, with the provenance §10.1 requires:
    every clinical output is traceable to the instrument and rule that
    produced it, and says whether an override fired."""

    condition: str
    tier: str
    score: int
    method: str
    instrument_code: str
    instrument_version: int
    #: tier before deterioration and overrides, for audit
    scored_tier: str
    tier_rule_label: str | None = None
    deterioration: Deterioration | None = None
    override_fired: bool = False
    override_rule_codes: tuple[str, ...] = ()
    #: a safety rule matched but its forces_tier was at or below the tier
    #: already assigned, so it changed nothing. Recorded, not hidden.
    non_raising_override_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Screening:
    """The input. `answers` maps question code to recorded value; a question
    answered with an explicit unknown/refused option belongs here too, and
    the engine derives `unknown` from the instrument."""

    answers: dict[str, str]
    channel: str = "app"
    previous_answers: dict[str, str] | None = None


def _questions_by_code(instrument: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for q in instrument.get("questions") or []:
        code = q.get("code")
        if not code:
            raise InstrumentError("a question has no code")
        if code in out:
            raise InstrumentError(f"duplicate question code {code}")
        out[code] = q
    return out


def _answer_values(question: dict) -> set[str]:
    if question.get("response_type") == "integer_banded":
        return {b["value"] for b in question.get("bands") or []}
    return {o["value"] for o in question.get("options") or []}


def _unknown_values(question: dict) -> set[str]:
    return {
        o["value"] for o in question.get("options") or []
        if o.get("is_unknown")
    }


def _applies_to_channel(question: dict, channel: str) -> bool:
    """A question limited to a channel is simply not asked on the others.
    §13.1: a long instrument does not fit a 180-second USSD session, so the
    Clinical Lead defines the subset as data rather than the channel
    truncating silently."""
    channels = question.get("channels")
    return channels is None or channel in channels


def score_condition(instrument: dict, answers: dict[str, str], condition: str) -> int:
    """Sum of the per-condition scores of the answers given.

    Scores are keyed by condition because the same answer can weigh
    differently for different conditions (§8.3) -- which is what lets
    tuberculosis be added as rows rather than columns. An unscored question
    contributes nothing and is still part of the instrument: demographics are
    recorded and not scored."""
    total = 0
    for question in instrument.get("questions") or []:
        value = answers.get(question.get("code"))
        if value is None:
            continue
        for entry in question.get("scores") or []:
            if entry.get("condition") == condition and entry.get("value") == value:
                total += int(entry.get("score", 0))
    return total


def _build_context(instrument: dict, answers: dict[str, str], conditions: list[str]) -> EvalContext:
    questions = _questions_by_code(instrument)
    unknown: set[str] = set()
    for code, question in questions.items():
        value = answers.get(code)
        if value is None or value in _unknown_values(question):
            unknown.add(code)
    scores = {c: score_condition(instrument, answers, c) for c in conditions}
    return EvalContext(answers=dict(answers), scores=scores, unknown=frozenset(unknown))


def applicable_questions(instrument: dict, screening: Screening) -> list[str]:
    """Questions this screening was required to answer: in this channel, and
    with any branching condition satisfied by the answers given."""
    questions = _questions_by_code(instrument)
    conditions = list(instrument.get("conditions") or [])
    ctx = _build_context(instrument, screening.answers, conditions)

    out: list[str] = []
    for code, question in questions.items():
        if not _applies_to_channel(question, screening.channel):
            continue
        branching = question.get("branching")
        if branching is not None and not evaluate(branching, ctx, f"question {code} branching"):
            continue
        out.append(code)
    return out


def _check_complete(instrument: dict, screening: Screening) -> None:
    handling = instrument.get("unknown_handling") or {}
    if handling.get("partial_session_may_produce_tier", False):
        return
    missing = [
        code for code in applicable_questions(instrument, screening)
        if code not in screening.answers
    ]
    if missing:
        raise IncompleteScreeningError(sorted(missing))


def _deterioration(instrument: dict, screening: Screening) -> Deterioration:
    """Compare tracked answers against the worker's previous session.

    Worsening is a move to a higher-scoring answer on a question flagged
    `tracked_for_trajectory` -- flagged in the instrument by the Clinical
    Lead, not a hardcoded list as in the v1 services/deterioration.py. Scored
    against the first condition that scores the question, so the comparison
    uses the clinician's own weighting rather than option order.

    Says so explicitly when there is no prior data rather than inferring
    (§4.3 module 2)."""
    previous = screening.previous_answers
    if not previous:
        return Deterioration(compared=False, changed=False, summary="No previous screening to compare against.")

    worsened: list[str] = []
    for question in instrument.get("questions") or []:
        if not question.get("tracked_for_trajectory"):
            continue
        code = question.get("code")
        now, before = screening.answers.get(code), previous.get(code)
        if now is None or before is None or now == before:
            continue
        scores = question.get("scores") or []
        if not scores:
            continue
        by_value: dict[str, int] = {}
        first_condition = scores[0].get("condition")
        for entry in scores:
            if entry.get("condition") == first_condition:
                by_value[entry.get("value")] = int(entry.get("score", 0))
        if by_value.get(now, 0) > by_value.get(before, 0):
            worsened.append(code)

    if not worsened:
        return Deterioration(compared=True, changed=False, summary="No worsening against the previous screening.")
    return Deterioration(
        compared=True,
        changed=True,
        worsened_codes=tuple(sorted(worsened)),
        summary=f"Worsened since the previous screening on: {', '.join(sorted(worsened))}.",
    )


def _escalate(tier: str) -> str:
    rank = _TIER_RANK[tier]
    return TIER_ORDER[min(rank + 1, len(TIER_ORDER) - 1)]


def _higher(a: str, b: str) -> str:
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def classify(instrument: dict, screening: Screening) -> list[ConditionResult]:
    """Produce one result per condition the instrument assesses.

    Raises IncompleteScreeningError if an applicable question is unanswered
    and the instrument forbids a tier from a partial session. Raises
    InstrumentError or PredicateError if the instrument itself is unusable --
    both are bugs to fix before merge, not conditions to degrade through,
    because a wrong tier is worse than no tier."""
    conditions = list(instrument.get("conditions") or [])
    if not conditions:
        raise InstrumentError("instrument declares no conditions")
    _check_complete(instrument, screening)

    ctx = _build_context(instrument, screening.answers, conditions)
    trajectory = _deterioration(instrument, screening)

    code = instrument.get("code", "")
    version = int(instrument.get("version", 0))

    results: list[ConditionResult] = []
    for condition in conditions:
        score = ctx.scores[condition]

        # ---- 2. tier: first matching rule, descending priority -----------
        rules = [
            r for r in (instrument.get("tier_rules") or [])
            if r.get("condition") == condition
        ]
        rules.sort(key=lambda r: int(r.get("priority", 0)), reverse=True)

        scored_tier: str | None = None
        rule_label: str | None = None
        for rule in rules:
            where = f"tier_rule {condition}/{rule.get('tier')}"
            if evaluate(rule.get("predicate"), ctx, where):
                scored_tier = rule.get("tier")
                rule_label = rule.get("label")
                break

        if scored_tier is None:
            # Every condition needs a reachable baseline; the instrument
            # validator enforces a GREEN rule for exactly this reason. If it
            # still happens, refusing beats inventing a tier.
            raise InstrumentError(
                f"no tier rule matched for condition {condition!r} "
                f"(score {score}). Every condition needs a reachable baseline rule."
            )
        if scored_tier not in _TIER_RANK:
            raise InstrumentError(f"tier rule for {condition!r} names unknown tier {scored_tier!r}")

        tier = scored_tier

        # ---- 3. trajectory: may raise one level --------------------------
        if trajectory.changed:
            tier = _escalate(tier)

        # ---- 4. safety rules: LAST, raise only ---------------------------
        fired: list[str] = []
        non_raising: list[str] = []
        for rule in instrument.get("safety_rules") or []:
            if rule.get("condition") not in (None, condition):
                continue
            rule_code = rule.get("code") or "(unnamed)"
            where = f"safety_rule {rule_code}"
            if not evaluate(rule.get("predicate"), ctx, where):
                continue
            forces = rule.get("forces_tier")
            if forces not in _TIER_RANK:
                raise InstrumentError(f"safety rule {rule_code!r} names unknown tier {forces!r}")
            raised = _higher(tier, forces)
            if _TIER_RANK[raised] > _TIER_RANK[tier]:
                tier = raised
                fired.append(rule_code)
            else:
                # It matched but changed nothing. Recorded rather than
                # dropped: "the rule fired and the tier was already higher"
                # is a different audit story from "the rule never matched".
                non_raising.append(rule_code)

        results.append(
            ConditionResult(
                condition=condition,
                tier=tier,
                score=score,
                method="deterministic_rules",
                instrument_code=code,
                instrument_version=version,
                scored_tier=scored_tier,
                tier_rule_label=rule_label,
                deterioration=trajectory,
                override_fired=bool(fired),
                override_rule_codes=tuple(fired),
                non_raising_override_codes=tuple(non_raising),
            )
        )

    return results


def primary_tier(results: list[ConditionResult]) -> str:
    """The highest tier across conditions -- what drives the referral and
    what a single-tier caller (the v1 API adapter) reports. A worker at RED
    for one condition is at RED, whatever the others say."""
    if not results:
        raise InstrumentError("no results to take a primary tier from")
    return max((r.tier for r in results), key=lambda t: _TIER_RANK[t])
