"""Referrals keyed to a result get chased too.

`docs/IMPLEMENTATION_PLAN.md` item 1.10's planned half, §10.4, and the
metric the whole system is judged on: **referral completion**.

**The defect this file was written for, reproduced below before it was
fixed.** `services/referral_cascade.py` reads `referral.screening.tier` and
`referral.miner.phone`. A v2 referral is keyed to a `screening_results` row
and a `persons` row, with `screening_id` and `miner_id` null — so the first
attribute raised `AttributeError`, the cascade's per-row `try/except` caught
it, logged a failure, and moved on. **Every tick. Permanently.**

A v2 referral therefore never reminded, never escalated, and passed its
deadline with nothing to show but a repeating exception in the logs. The
per-row handler exists so that one bad row cannot abort the batch; here it
turned a structural mismatch into a silent, permanent skip. Defensive error
handling converting a loud failure into a quiet one is the thing to watch
for, and this is what it looks like.

Two properties of the fix carry the weight:

  **Timing comes from the instrument.** v1 computes everything from
  `created_at` plus windows hardcoded in `services/referrals.py`. A v2
  referral carries the window the Clinical Lead stated per condition and
  tier (§12.2 item 8), and reminders are fractions of it — so a 48-hour
  window and a 14-day one are chased in proportion, and changing the
  clinical window changes the chasing with it.

  **Nothing is sent, and that is recorded rather than hidden.** No
  patient-facing string is approved (item 1.6b) and §8.4 forbids inventing
  one, so each action advances the referral and reports what it *would* have
  sent — the same choice `screening_v2` makes with `not_sent_reason`. The
  alternative, waiting for the words before tracking deadlines at all, is
  exactly what produced the silent skip.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import database
from services import referral_cascade, referral_cascade_v2

NOW = datetime(2026, 11, 18, 12, 0)


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _v2_referral(db, *, created, deadline, status="open", stage=0, tier="ORANGE",
                 code="SG-V2AA"):
    """A referral as `referrals_v2.create_for_result()` makes one: keyed to a
    result and a person, with no v1 screening or miner."""
    from db_models import Person, Referral, ScreeningResult, ScreeningSession

    # `screening_sessions.person_id` is a real foreign key, so the person has
    # to exist -- a reminder that the v2 tables enforce what the v1 ones left
    # to application code.
    person = db.scalar(select(Person))
    if person is None:
        person = Person(participant_code="SEED01")
        db.add(person)
        db.flush()

    session = ScreeningSession(person_id=person.id, channel="APP")
    db.add(session)
    db.flush()
    result = ScreeningResult(
        session_id=session.id, condition_code="silicosis", tier=tier,
        score=10, confidence=1.0, method="deterministic_rules",
        instrument_code="TEST-INSTRUMENT", instrument_version=1,
        ruleset_version="1", scored_tier=tier,
    )
    db.add(result)
    db.flush()
    referral = Referral(
        result_id=result.id, person_id=person.id, condition_code="silicosis",
        referral_code=code, status=status, reminder_stage=stage,
        created_at=created, deadline=deadline,
    )
    db.add(referral)
    db.commit()
    return referral


def _v1_referral(db, *, tier="ORANGE", code="SG-V1AA"):
    from db_models import Miner, Referral, Screening

    miner = Miner(name="Tendai Moyo", phone="0771234567", mine_site="Globe & Phoenix")
    db.add(miner)
    db.flush()
    screening = Screening(miner_id=miner.id, tier=tier, channel="APP")
    db.add(screening)
    db.flush()
    referral = Referral(
        screening_id=screening.id, miner_id=miner.id, referral_code=code,
        status="open", reminder_stage=0, created_at=NOW - timedelta(days=30),
    )
    db.add(referral)
    db.commit()
    return referral


# --------------------------------------------------- the defect, reproduced

def test_the_v1_cascade_used_to_lose_these_rows_and_now_skips_them(client, caplog):
    """**The regression this file exists for.** The v1 cascade must leave a
    v2 referral alone *deliberately* — not reach for `referral.screening`,
    raise, and have its own error handler bury the row."""
    import logging

    db = _session(client)
    _v2_referral(db, created=NOW - timedelta(days=20),
                 deadline=NOW - timedelta(days=15))

    with caplog.at_level(logging.ERROR, logger="silicaguard.referral_cascade"):
        referral_cascade.process_due_referrals(db, now=NOW)

    assert "Failed to process referral cascade" not in caplog.text, (
        "the v1 cascade is still raising on a v2 row and logging it as a "
        "failure, which is how these referrals were lost"
    )
    db.close()


def test_the_v1_cascade_still_processes_its_own_rows(client):
    """The skip has to be the narrow one it claims to be."""
    db = _session(client)
    _v1_referral(db)
    referral_cascade.process_due_referrals(db, now=NOW)

    from db_models import Referral

    row = db.scalar(select(Referral).where(Referral.referral_code == "SG-V1AA"))
    assert row.status != "open", "a v1 referral 30 days past must have advanced"
    db.close()


# ----------------------------------------------------------- the v2 cascade

def test_a_referral_past_its_deadline_escalates(client):
    db = _session(client)
    _v2_referral(db, created=NOW - timedelta(days=20),
                 deadline=NOW - timedelta(days=15))

    run = referral_cascade_v2.process_due(db, now=NOW)

    from db_models import Referral

    row = db.scalar(select(Referral))
    assert run.escalated == 1, run
    assert row.status == "escalated"
    db.close()


def test_a_reminder_falls_at_a_fraction_of_the_window_not_a_fixed_offset(client):
    """**The property that makes this worth a separate module.** A 48-hour
    window and a 14-day one are chased in proportion, so changing the
    clinical window changes the chasing with it and nobody has to remember
    to edit two places."""
    db = _session(client)
    # A 10-day window, half elapsed: the first reminder is due.
    referral = _v2_referral(db, created=NOW - timedelta(days=5),
                            deadline=NOW + timedelta(days=5))

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert run.reminded == 1, run
    assert referral.status == "reminded" and referral.reminder_stage == 1
    db.close()


def test_a_short_window_is_chased_proportionally_sooner(client):
    """The same fraction against a 48-hour window puts the first reminder at
    24 hours, with no 48-hour constant written anywhere in this code."""
    db = _session(client)
    referral = _v2_referral(db, created=NOW - timedelta(hours=25),
                            deadline=NOW + timedelta(hours=23))

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert run.reminded == 1
    assert referral.reminder_stage == 1
    db.close()


def test_nothing_is_due_early_in_the_window(client):
    db = _session(client)
    referral = _v2_referral(db, created=NOW - timedelta(hours=1),
                            deadline=NOW + timedelta(days=13))

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert run.nothing_due == 1 and run.reminded == 0
    assert referral.status == "open" and referral.reminder_stage == 0
    db.close()


def test_the_second_reminder_follows_the_first(client):
    db = _session(client)
    referral = _v2_referral(db, created=NOW - timedelta(days=9),
                            deadline=NOW + timedelta(days=1),
                            status="reminded", stage=1)

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert run.reminded == 1
    assert referral.reminder_stage == 2
    db.close()


def test_an_attended_referral_is_left_alone(client):
    """Chasing somebody who has already been is worse than not chasing: it
    teaches a worker that the messages mean nothing."""
    db = _session(client)
    referral = _v2_referral(db, created=NOW - timedelta(days=20),
                            deadline=NOW - timedelta(days=15),
                            status="attended")

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert referral.status == "attended"
    assert run.reminded == 0 and run.escalated == 0
    db.close()


def test_a_referral_with_no_deadline_is_not_given_an_invented_one(client):
    """`referrals_v2.referral_window()` raises rather than defaulting when
    the instrument states no window, so a row without one is not a row to
    improvise a schedule for."""
    db = _session(client)
    referral = _v2_referral(db, created=NOW - timedelta(days=20), deadline=None)

    run = referral_cascade_v2.process_due(db, now=NOW)
    db.refresh(referral)

    assert referral.status == "open"
    assert run.nothing_due == 1
    db.close()


# ------------------------------------------- nothing is sent, and it is said

def test_each_action_reports_what_it_would_have_sent(client):
    """§8.4: no patient-facing string is approved yet and none may be
    invented. So the cascade advances the referral and says what it did not
    send — the same choice `screening_v2` makes with `not_sent_reason`.
    Waiting for the words before tracking deadlines is what produced the
    silent skip this module fixes."""
    db = _session(client)
    _v2_referral(db, created=NOW - timedelta(days=20),
                 deadline=NOW - timedelta(days=15))

    run = referral_cascade_v2.process_due(db, now=NOW)

    assert run.unsent_messages, "the message it could not send has to be named"
    assert all(code.startswith("referral.") for code in run.unsent_messages)
    db.close()


def test_the_cascade_sends_nothing_at_all(client, monkeypatch):
    """Asserted rather than assumed: the gateway must not be touched while
    the words do not exist."""
    import types

    from services import notifications

    def explode(*args, **kwargs):
        raise AssertionError("the v2 cascade must not send anything yet")

    monkeypatch.setattr(notifications, "httpx", types.SimpleNamespace(post=explode))

    db = _session(client)
    _v2_referral(db, created=NOW - timedelta(days=20),
                 deadline=NOW - timedelta(days=15))
    referral_cascade_v2.process_due(db, now=NOW)
    db.close()


def test_the_not_sent_reason_names_the_blocking_item(client):
    """A reason that does not say who unblocks it is a reason nobody acts
    on."""
    assert "1.6b" in referral_cascade_v2.NOT_SENT_REASON
    assert "approved" in referral_cascade_v2.NOT_SENT_REASON


# ------------------------------------------------- the two cascades together

def test_each_cascade_counts_the_other_s_rows_rather_than_failing(client):
    """The lesson from the defect, applied here: a row this cascade does not
    own is **counted**, not allowed to raise and be logged as a failure.
    That is how a structural mismatch became a repeating exception nobody
    read."""
    db = _session(client)
    _v1_referral(db)
    _v2_referral(db, created=NOW - timedelta(days=20),
                 deadline=NOW - timedelta(days=15))

    run = referral_cascade_v2.process_due(db, now=NOW)

    assert run.not_mine == 1, "the v1 row is counted, not thrown on"
    assert run.failed == 0, "and not recorded as a failure"
    assert run.escalated == 1
    db.close()


def test_no_clinical_window_is_written_in_this_module():
    """Every number here is a fraction of a window the instrument states. A
    48 or a 14 in this file would be a clinical constant living in code,
    which is what §8.3 and `docs/CLINICAL.md` correction 7 exist to stop.

    Read from the AST rather than by searching the text, because the first
    version of this test matched the string "48" inside a comment explaining
    why there is no 48 in the code — the same false positive as the
    dependency guard in `test_identity_route_authz.py`, and the same fix.
    """
    import ast
    import pathlib

    tree = ast.parse(
        pathlib.Path(referral_cascade_v2.__file__).read_text(encoding="utf-8")
    )

    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "timedelta"):
            continue
        for kw in node.keywords:
            if isinstance(kw.value, ast.Constant) and kw.value.value > 1:
                offenders.append(f"timedelta({kw.arg}={kw.value.value})")
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value > 1:
                offenders.append(f"timedelta({arg.value})")

    assert offenders == [], (
        f"{offenders} encode a referral window in code; the window is the "
        "Clinical Lead's, stated per condition and tier in the instrument"
    )


def test_the_only_tuning_numbers_are_the_reminder_fractions():
    """And they are fractions, so they carry no duration of their own."""
    assert referral_cascade_v2.REMINDER_FRACTIONS == (0.5, 0.8)
    assert all(0 < f < 1 for f in referral_cascade_v2.REMINDER_FRACTIONS)


def test_the_scheduler_runs_both(client):
    """Two jobs, because the two compute their timing from different places.
    Asserted so that removing one is deliberate."""
    import inspect

    import main

    source = inspect.getsource(main)
    assert 'id="referral_cascade"' in source
    assert 'id="referral_cascade_v2"' in source
