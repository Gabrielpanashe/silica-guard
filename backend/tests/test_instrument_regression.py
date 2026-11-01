"""The instrument regression suite — §11.8's seventh CI gate.

Master Reference v1.0 §11.7, §11.8. Every approved instrument version ships
with a fixture file of answer profiles and the tier each must produce, and
this parametrises over them.

**The point is not that the code works; it is that a clinical change is
visible.** Once version one is approved, nobody can move a threshold without
either a fixture failing or the Clinical Lead changing a fixture on the same
pull request — and the second is the reviewable act. A rules engine with no
regression fixtures is a rules engine whose behaviour nobody can see change.

**The expected tiers are the Clinical Lead's assertions**, not test details.
"This answer profile must come out ORANGE" is a clinical statement with a
person on the other end of it, which is why `clinical/fixtures.schema.json`
asks for an approver and why the file is approved on the same pull request as
the instrument (§11.4).

**Right now it regresses only the synthetic fixture.** `clinical/instruments/`
is empty — instrument version one is item 1.4, the Clinical Lead's deliverable
— so the harness runs against `clinical/examples/`, which carries
`status: example` and asserts nothing clinical. The moment a real instrument
and its fixtures land in `clinical/instruments/`, this file picks them up with
no changes: that is the whole reason it discovers files rather than naming
them.

**A real instrument with no fixtures fails the build.** Not skips — fails. An
approved instrument whose behaviour nobody has pinned is the thing this gate
exists to prevent, and a skip is how that becomes permanent.
"""

from pathlib import Path

import pytest
import yaml

from services.rules_engine import (
    IncompleteScreeningError,
    Screening,
    classify,
    primary_tier,
)

REPO = Path(__file__).resolve().parent.parent.parent
INSTRUMENTS = REPO / "clinical" / "instruments"
EXAMPLES = REPO / "clinical" / "examples"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _pairs() -> list[tuple[Path, Path]]:
    """(instrument, fixtures) for every instrument that has fixtures.

    Real instruments first; the synthetic example only when there are no real
    ones, so that a green suite never means "the example passed" once version
    one exists.
    """
    real = [
        (path, path.with_suffix("").with_suffix(".fixtures.yaml"))
        for path in sorted(INSTRUMENTS.glob("*.yaml"))
        if not path.name.endswith(".fixtures.yaml")
    ]
    real = [(i, f) for i, f in real if f.exists()]
    if real:
        return real
    example = EXAMPLES / "TEST-INSTRUMENT.yaml"
    fixtures = EXAMPLES / "TEST-INSTRUMENT.fixtures.yaml"
    return [(example, fixtures)] if example.exists() and fixtures.exists() else []


def _cases():
    out = []
    for instrument_path, fixtures_path in _pairs():
        doc = _load(fixtures_path)
        for index, profile in enumerate(doc.get("profiles") or []):
            out.append(
                pytest.param(
                    instrument_path,
                    fixtures_path,
                    profile,
                    id=f"{doc.get('instrument')}-v{doc.get('version')}:{profile.get('name', index)}",
                )
            )
    return out


CASES = _cases()


# ----------------------------------------------- the gate's own preconditions

def test_every_real_instrument_has_fixtures():
    """**Fails rather than skips.** An approved instrument whose behaviour
    nobody has pinned is exactly what this gate exists to prevent, and a skip
    is how that becomes permanent."""
    missing = [
        path.name
        for path in sorted(INSTRUMENTS.glob("*.yaml"))
        if not path.name.endswith(".fixtures.yaml")
        and not path.with_suffix("").with_suffix(".fixtures.yaml").exists()
    ]
    assert not missing, (
        f"instrument files with no fixtures: {missing}. Every approved version "
        "ships with the answer profiles that pin its behaviour (§11.7), "
        "approved on the same pull request (§11.4)."
    )


def test_there_is_something_to_regress():
    """Guards against the harness silently finding nothing — a green suite
    that tested no profile is the worst possible outcome for a gate."""
    assert CASES, (
        "no instrument/fixture pair was found at all. Expected either a real "
        "pair in clinical/instruments/ or the synthetic one in "
        "clinical/examples/."
    )


def test_the_fixtures_name_the_instrument_they_test():
    """A fixture file pointing at the wrong version regresses the wrong
    behaviour, which is worse than no fixture."""
    for instrument_path, fixtures_path in _pairs():
        instrument, fixtures = _load(instrument_path), _load(fixtures_path)
        assert fixtures["instrument"] == instrument["code"], fixtures_path.name
        assert fixtures["version"] == instrument["version"], fixtures_path.name


def test_real_fixtures_carry_the_clinical_leads_approval():
    """An expected tier is a clinical assertion. Fixtures that gate a release
    need an approver and a date; the synthetic example is exempt because
    `status: example` means it gates nothing."""
    for _instrument_path, fixtures_path in _pairs():
        doc = _load(fixtures_path)
        if doc.get("status") == "example":
            continue
        assert doc.get("approved_by"), fixtures_path.name
        assert doc.get("approved_at"), fixtures_path.name


# ---------------------------------------------------------- the regression

@pytest.mark.parametrize("instrument_path,fixtures_path,profile", CASES)
def test_profile_produces_the_expected_tiers(instrument_path, fixtures_path, profile):
    """One answer profile, against the cascade, compared with what the
    Clinical Lead said it must produce.

    The failure message names the profile in the Clinical Lead's own words,
    because whoever reads a red build needs to know which clinical case broke
    rather than which array index did.
    """
    instrument = _load(instrument_path)
    expect = profile.get("expect") or {}
    screening = Screening(
        answers=dict(profile["answers"]),
        channel=profile.get("channel", "app"),
        previous_answers=profile.get("previous_answers"),
    )
    where = f"{profile['name']!r} ({fixtures_path.name})"

    # §13.1: a partially answered instrument must never produce a tier.
    if expect.get("incomplete"):
        with pytest.raises(IncompleteScreeningError):
            classify(instrument, screening)
        return

    results = classify(instrument, screening)
    by_condition = {r.condition: r for r in results}

    if "primary_tier" in expect:
        assert primary_tier(results) == expect["primary_tier"], (
            f"{where}: primary tier. A worker at the highest tier for one "
            "condition is at that tier, whatever the others say."
        )

    for condition, tier in (expect.get("tiers") or {}).items():
        assert condition in by_condition, f"{where}: no result for {condition}"
        assert by_condition[condition].tier == tier, f"{where}: {condition} tier"

    for condition, tier in (expect.get("scored_tiers") or {}).items():
        assert by_condition[condition].scored_tier == tier, (
            f"{where}: {condition} scored tier — the tier BEFORE deterioration "
            "and overrides. This is what distinguishes an override firing from "
            "a score that was already there."
        )

    for condition, score in (expect.get("scores") or {}).items():
        assert by_condition[condition].score == score, f"{where}: {condition} score"

    if "overrides" in expect:
        fired = sorted(
            {code for r in results for code in r.override_rule_codes}
        )
        assert fired == sorted(expect["overrides"]), (
            f"{where}: safety rules that fired. An empty expectation is a real "
            "assertion and the one most likely to catch an over-eager rule."
        )

    if "deterioration_changed" in expect:
        changed = any(r.deterioration and r.deterioration.changed for r in results)
        assert changed is expect["deterioration_changed"], f"{where}: deterioration"


# --------------------------------------------------------------- coverage

def test_the_fixtures_cover_every_tier_the_instrument_can_reach():
    """A fixture set that never reaches ORANGE cannot notice the ORANGE rule
    breaking. Checked per instrument rather than globally, because coverage is
    a property of one version's fixtures."""
    for instrument_path, fixtures_path in _pairs():
        instrument, fixtures = _load(instrument_path), _load(fixtures_path)
        reachable = {
            rule["tier"] for rule in instrument.get("tier_rules") or []
        } | {
            rule["forces_tier"] for rule in instrument.get("safety_rules") or []
        }
        asserted = set()
        for profile in fixtures.get("profiles") or []:
            expect = profile.get("expect") or {}
            if expect.get("primary_tier"):
                asserted.add(expect["primary_tier"])
            asserted.update((expect.get("tiers") or {}).values())

        missing = reachable - asserted
        assert not missing, (
            f"{fixtures_path.name} asserts no profile reaching {sorted(missing)}, "
            f"but {instrument_path.name} has rules that produce them. A tier no "
            "fixture reaches is a tier whose rule can break unnoticed."
        )


def test_the_fixtures_cover_every_safety_rule():
    """A safety rule no fixture fires is a red flag nobody has checked still
    works — and these are the rules that exist precisely because the cost of
    missing them is a person."""
    for instrument_path, fixtures_path in _pairs():
        instrument, fixtures = _load(instrument_path), _load(fixtures_path)
        declared = {
            rule["code"] for rule in instrument.get("safety_rules") or []
        }
        exercised = set()
        for profile in fixtures.get("profiles") or []:
            exercised.update((profile.get("expect") or {}).get("overrides") or [])

        missing = declared - exercised
        assert not missing, (
            f"{fixtures_path.name} never fires {sorted(missing)}. A safety rule "
            "no fixture exercises is a red flag nobody has checked still works."
        )


def test_at_least_one_profile_asserts_that_no_override_fires():
    """The negative case. A fixture set where every profile fires something
    cannot catch a rule that has become too eager."""
    for _instrument_path, fixtures_path in _pairs():
        fixtures = _load(fixtures_path)
        assert any(
            (profile.get("expect") or {}).get("overrides") == []
            for profile in fixtures.get("profiles") or []
        ), (
            f"{fixtures_path.name} has no profile asserting that NO safety rule "
            "fires. Without one, a rule that starts matching everything passes."
        )
