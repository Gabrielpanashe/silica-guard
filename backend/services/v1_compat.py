"""The v1 adapter: old routes, v2 storage, one classifier.

`docs/IMPLEMENTATION_PLAN.md` items 1.9 and 1.11, and §7's ordering. The
point of §7 step 3 is worth restating because it is the whole design
constraint: **the v1 route switches at the same moment as every other
caller, so there is no window in which two clients get two classifiers.**
A per-client rollout of a clinical classifier is not a cautious rollout; it
is two instruments in the field at once.

So this module ships **dormant**. While it is dormant, `POST /api/screen`
behaves exactly as it does today — the model call, the v1 tables, all of it
— and nothing about the live demonstration changes. When every condition in
`readiness()` is met, the same route runs the §10.3 deterministic pipeline
and maps the result back into the v1 response shape, byte-compatible, so no
client has to change on the day.

**What it is waiting for, and who owns each one.** This is the useful output
of building it now: the remaining work is visible and attributable instead
of being discovered in Week 10.

  1. **An approved instrument** — the Clinical Lead's deliverable (§12.5).
     Without it there are no questions, no scores and no rules.
  2. **A question mapping** — which instrument question each of the ten v1
     question codes corresponds to. One edit here, once the instrument's
     codes exist. Nobody can write it before then, and guessing it would
     silently rescore every screening.
  3. **Approved result text in English and Shona** — the v1 response's
     `explanation_english` and `explanation_shona` are required, non-null
     strings, so a worker is being given a Shona explanation today. The
     adapter cannot produce one: §8.4 forbids runtime translation and no
     Shona string is authored yet (item 1.6b; Shona and Ndebele are the
     Clinical Lead's Week 12 deliverable). Returning English in the Shona
     field, or an empty string, would both be worse than waiting — one is a
     silent language failure and the other removes an explanation a worker
     currently gets.

**And two requirements that belong to the mobile application, which the
adapter enforces rather than waits for.** Both were found by building this
rather than by reading the plan, and together they mean the Week 10 roadmap
line is **not a backend-only item**:

  - **A participant code in the request.** `identity.resolve()` is
    deterministic only on a participant code or a hashed national identity
    number. A name-and-number bundle goes through the probabilistic pass,
    which **queues a probable match and never applies it** (§8.2) — so there
    is no bundle the adapter could send that would reach an existing person.
    Handed a `miners.id` and nothing else it would create a new person on
    every screening, which is the duplicate-identity problem the whole v2
    design exists to prevent, and the screening would attach to somebody
    other than whoever consented. Items 1.13 and 1.14.
  - **Consent.** The pipeline hard-gates on it (§14.2) and the v1 request
    carries none. Item 1.8's consent screen.

Both are refused per request once the adapter is active, never fallen back
from — so the application must ship them **before** the mapping is filled
in, which is the one piece of release ordering this design makes explicit.

One thing the switch quietly fixes: the v1 request sends `answer_score` per
answer, so today **the device decides the clinical weight of an answer**.
The adapter ignores it and scores from the instrument, which is what §8.3
means by scoring rules as versioned data. A handset running an old build
cannot carry an old weighting into a new tier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import Instrument
from services import instrument_store

logger = logging.getLogger("silicaguard.v1_compat")

#: The ten v1 question codes, read off `questions.SCREENING_QUESTIONS`. Listed
#: here rather than imported so that a change to the v1 set is a visible
#: change to the mapping's completeness rather than a silent one.
V1_QUESTION_CODES = (
    "YEARS_UNDERGROUND",
    "JOB_ROLE",
    "WET_DRILLING",
    "PPE_USE",
    "COUGH_DURATION",
    "BREATHLESSNESS",
    "TB_HISTORY",
    "WEIGHT_LOSS",
    "CHEST_PAIN",
    "PRIOR_LUNG_DIAGNOSIS",
)

#: v1 question code -> instrument question code. **Deliberately empty.**
#:
#: It cannot be filled until instrument version one exists, because it names
#: that instrument's codes, and it must not be guessed: mapping
#: `COUGH_DURATION` onto the wrong question rescores every screening that
#: answered it, in a way no test would catch, because both sides would be
#: internally consistent.
#:
#: When the instrument lands this becomes ten lines, and
#: `tests/test_v1_adapter.py` asserts that every v1 code is covered and that
#: every target exists in the instrument.
V1_QUESTION_MAP: dict[str, str] = {}

#: Answer values are mapped the same way and for the same reason: a v1
#: option value such as `over_10_years` has to name an option the instrument
#: actually offers, or the engine scores it as unknown.
V1_ANSWER_MAP: dict[str, dict[str, str]] = {}


@dataclass(frozen=True)
class Readiness:
    """Whether the adapter may run, and what is missing if not."""

    active: bool
    blockers: tuple[str, ...] = ()

    def reason(self) -> str | None:
        return "; ".join(self.blockers) if self.blockers else None


def approved_instrument(db: Session) -> dict | None:
    """The active approved instrument, or None."""
    for (code,) in db.query(Instrument.code).filter(
        Instrument.status == "approved"
    ).distinct().all():
        try:
            return instrument_store.read_active(db, code)
        except Exception:  # noqa: BLE001 - a half-loaded version is not usable
            continue
    return None


def mapping_gaps(instrument: dict, mapping: dict[str, str] | None = None) -> list[str]:
    """Which v1 questions have no usable mapping into this instrument.

    Checked both ways. A v1 code with no entry cannot be answered, and an
    entry naming a question the instrument does not have is worse, because
    the engine would treat the answer as absent and an absent red flag is
    exactly what §12.2 item 10 exists to stop.
    """
    mapping = V1_QUESTION_MAP if mapping is None else mapping
    known = {q["code"] for q in instrument.get("questions") or []}

    gaps = [code for code in V1_QUESTION_CODES if code not in mapping]
    gaps += [
        f"{v1} -> {target} (no such question in {instrument.get('code')})"
        for v1, target in sorted(mapping.items())
        if target not in known
    ]
    return gaps


#: The content codes the v1 response shape needs, and the languages it
#: promises. `screening_v2` already selects by tier; this is the same set
#: seen from the other end, as a readiness condition rather than a lookup.
RESULT_LANGUAGES = ("en", "sn")


def content_gaps(db: Session) -> list[str]:
    """Tier messages with no approved text in a language v1 promises."""
    from services import content_store
    from services.screening_v2 import TIER_MESSAGE_CODES

    gaps: list[str] = []
    for tier, code in sorted(TIER_MESSAGE_CODES.items()):
        for language in RESULT_LANGUAGES:
            try:
                rendered = content_store.render(db, code, language)
            except Exception:  # noqa: BLE001 - absent, unapproved or unrenderable
                gaps.append(f"{code} [{language}]")
                continue
            # `render()` falls back to English and reports the language it
            # actually came from, which is the right behaviour for a sender
            # that records what a person was told -- and a gap here. English
            # in the v1 response's `explanation_shona` field is a silent
            # language failure, so a fallback counts as missing text.
            if rendered.get("language") != language:
                gaps.append(
                    f"{code} [{language}] (fell back to "
                    f"{rendered.get('language')})"
                )
    return gaps


def readiness(db: Session, *, mapping: dict[str, str] | None = None) -> Readiness:
    """Whether `POST /api/screen` may run the deterministic pipeline.

    **Three conditions, all derived from data in the database.** There is no
    environment variable and no per-request fallback, and both omissions are
    §7 step 3: a flag that turns a clinical classifier on and off per
    deployment gets set differently in two places, and a route that runs the
    new engine for requests that look ready and the old one for the rest is
    two instruments in the field at once.

    The two client-side requirements -- a participant code and consent in the
    request -- are therefore **not** conditions here. They are enforced per
    request once the adapter is active, as a refusal rather than a fallback,
    which means the mobile application has to ship them **before** the
    mapping below is filled in. That ordering is the release coordination
    this design deliberately makes explicit; see `docs/API_CONTRACT.md`.
    """
    blockers: list[str] = []

    instrument = approved_instrument(db)
    if instrument is None:
        blockers.append(
            "no approved instrument is loaded (instrument version one, "
            "Clinical Lead, Master Reference §12.5)"
        )
    else:
        gaps = mapping_gaps(instrument, mapping)
        if gaps:
            blockers.append(
                f"{len(gaps)} v1 question(s) are not mapped to "
                f"{instrument['code']}: {', '.join(gaps[:4])}"
                + (" …" if len(gaps) > 4 else "")
            )

    text_gaps = content_gaps(db)
    if text_gaps:
        blockers.append(
            f"{len(text_gaps)} result message(s) have no approved text: "
            f"{', '.join(text_gaps[:4])}"
            + (" …" if len(text_gaps) > 4 else "")
            + " — the v1 response promises a Shona explanation and §8.4 "
            "forbids translating one at runtime (item 1.6b)"
        )

    return Readiness(active=not blockers, blockers=tuple(blockers))


def to_v2_answers(
    v1_answers: list,
    *,
    mapping: dict[str, str] | None = None,
    answer_mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Convert v1 answers into the instrument's own codes and values.

    `answer_score` from the request is **discarded**, deliberately: today the
    handset sends the clinical weight of each answer, which means an old
    build carries an old weighting into a new tier. The instrument scores.
    """
    mapping = V1_QUESTION_MAP if mapping is None else mapping
    answer_mapping = V1_ANSWER_MAP if answer_mapping is None else answer_mapping

    out: dict[str, str] = {}
    for answer in v1_answers:
        code = getattr(answer, "question_code", None) or answer["question_code"]
        value = getattr(answer, "answer_value", None) or answer["answer_value"]
        target = mapping.get(code)
        if target is None:
            continue
        out[target] = answer_mapping.get(code, {}).get(value, value)
    return out


def log_client(client_header: str | None, route: str) -> None:
    """Record which client version called a v1 route.

    §5's time-box depends on this: the adapter and `drop_v1` land together
    once staging logs show no v1 traffic for two weeks, and "no v1 traffic"
    is only observable if the calls are counted. No personal data — a client
    version string and a route.
    """
    logger.info(
        "v1 route called (route=%s client=%s)", route, client_header or "unidentified"
    )


def tier_of_record(results) -> str | None:
    """The single tier a v1 response can carry, from a list of results.

    A v2 session produces one result per condition and the v1 shape has one
    `tier` field, so something has to give. The highest tier across
    conditions is the only safe reduction: a worker at RED for one condition
    is at RED whatever the others say. The information lost is which
    condition drove it, which is why `drop_v1` removes this shape rather
    than keeping it.
    """
    from services.rules_engine import primary_tier

    return primary_tier(list(results)) if results else None


def contributing_factors(results) -> list[str]:
    """The v1 field, populated from the rules that actually fired.

    §7 step 3: the same words for the same rules every time. These are the
    labels the Clinical Lead wrote on the instrument's own rules, not model
    output and not generated text — which is what lets this field keep its
    name while the thing behind it changes completely.
    """
    labels: list[str] = []
    for result in results:
        if result.tier_rule_label:
            labels.append(result.tier_rule_label)
        labels.extend(result.override_rule_codes)
    seen: set[str] = set()
    return [x for x in labels if not (x in seen or seen.add(x))]


def result_text(db: Session, tier: str, language: str) -> str:
    """The approved result message for a tier, in one language.

    Only reachable once `readiness()` has established that every tier has
    approved text in every language the v1 shape promises, so this does not
    fall back: a fallback here would be a sentence nobody approved reaching
    a worker, which is the one thing §8.4 exists to prevent. If it raises,
    the gate was bypassed and the screening should fail loudly rather than
    improvise.
    """
    from services import content_store
    from services.screening_v2 import TIER_MESSAGE_CODES

    code = TIER_MESSAGE_CODES[tier]
    rendered = content_store.render(db, code, language)
    if rendered["language"] != language:
        # Only reachable if the gate was bypassed. Loud, because the
        # alternative is a worker given English in the Shona field.
        raise RuntimeError(
            f"{code} has no {language} text and fell back to "
            f"{rendered['language']}; readiness() should have blocked this"
        )
    return rendered["text"]
