"""A USSD turn must answer inside its budget.

`CLAUDE.md`, among the rules that are not negotiable: **no language-model
call inside a USSD session. Under 3 s per turn, hard ceiling well under
10 s.** Master Reference v1.0 §10.7, §13.1.

The first half has been enforced since the content store landed — `tests/
test_content_runtime_rule.py` asserts on the import graph that neither
`services.ussd_handler` nor `routers.ussd` can reach a model client by any
path. **The second half was enforced by nothing**, and was being broken.

What the final turn did, measured rather than assumed: on the ORANGE/RED path
it made three synchronous outbound calls — the miner's result SMS, the
hospital pre-alert SMS and the demonstration email — each with a ten-second
timeout. A merely slow gateway (two seconds a call, well inside each one's own
limit) cost **six seconds on one turn**; the worst case is around thirty.
Africa's Talking terminates the session at ten.

**What that costs is the one screen that matters.** The screening survives,
because it is committed before any send — rule 7 working. What the miner loses
is the turn that says "go to Kwekwe District Hospital within 48 hours", which
for a RED self-screen is the entire clinical point of the channel. He answered
every question and saw an error.

Two docstrings asserted the opposite while it was happening: the handler's said
it "must return in milliseconds", and the router's said "no network calls, so
this is effectively instant". Prose claiming safety the code did not have, in
the dangerous direction.

**And one note about this file itself.** `conftest.py` has an autouse fixture
that stubs every `notifications.send_*` function to a no-op, which is right
for every other test file and fatal for this one: with the senders stubbed the
turn is fast whatever the gateway does, and the first version of these tests
passed while the defect was still there. The fixture is overridden below and
`httpx` is patched instead, so the real senders run against a slow provider.
A latency test that cannot fail is worse than no latency test, because it
reads as evidence.
"""

import time
import types

import pytest
from sqlalchemy import select

import database
from services import email_notifications, notifications, ussd_handler

#: Each outbound call's own timeout is ten seconds, so a gateway can be this
#: slow without anything timing out or logging a failure.
SLOW_CALL_SECONDS = 2.0

#: `CLAUDE.md`'s budget. The gateway's hard limit is ten; this is the number
#: the rule actually states, and the margin is the point of stating it.
BUDGET_SECONDS = 3.0


class _Gateway:
    """A slow but entirely healthy provider."""

    def __init__(self, delay=SLOW_CALL_SECONDS):
        self.delay = delay
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        time.sleep(self.delay)
        return types.SimpleNamespace(
            status_code=200,
            text='{"SMSMessageData":{"Recipients":[{"status":"Success"}]}}',
            raise_for_status=lambda: None,
            json=lambda: {"id": "re_x"},
        )


@pytest.fixture(autouse=True)
def _mock_notifications():
    """**Deliberately override `conftest`'s autouse stub.**

    That fixture replaces every `notifications.send_*` function with a no-op,
    which is right for every other file and fatal here: with the senders
    stubbed, the turn is fast whatever the gateway does, and the first version
    of this file passed its timing assertions against a defect that was still
    present. This file patches `httpx` instead, so the real senders run
    against a slow provider.
    """
    yield


@pytest.fixture
def gateway(monkeypatch):
    """A slow provider wired into both senders, and a nurse to pre-alert."""
    g = _Gateway()
    monkeypatch.setattr(notifications, "httpx", types.SimpleNamespace(post=g.post))
    monkeypatch.setattr(email_notifications, "httpx", types.SimpleNamespace(post=g.post))
    monkeypatch.setenv("HOSPITAL_NURSE_PHONE", "+263770000000")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_TO", "nurse@example.org")
    ussd_handler._sessions.clear()
    return g


#: The highest option on every question: the answer sequence that reaches the
#: top tier, hence the referral path with the most sending on it. Read off
#: `ussd_handler.SCREENING_QUESTIONS` rather than hardcoded, so a changed
#: question set changes this with it.
def _worst_case_inputs():
    return [str(len(q["options"])) for q in ussd_handler.SCREENING_QUESTIONS]


def _turn(client, text, session="sess-budget", phone="+263771234567"):
    return client.post("/api/ussd", data={
        "sessionId": session, "phoneNumber": phone,
        "serviceCode": "*384*1#", "text": text,
    })


def _walk_to_the_last_turn(client, session="sess-budget", phone="+263771234567"):
    """Answer every question but the last, one POST per turn.

    The gateway sends the whole accumulated `text` each time and the handler
    reads only its final element, advancing `pending_index` by one — so the
    session has to be driven turn by turn rather than in a single post.
    Returns the `text` value for the turn that completes the screening.
    """
    inputs = _worst_case_inputs()
    _turn(client, "", session=session, phone=phone)          # the opening menu
    accumulated = []
    for choice in inputs[:-1]:
        accumulated.append(choice)
        response = _turn(client, "*".join(accumulated), session=session, phone=phone)
        assert response.text.startswith("CON"), response.text[:60]
    accumulated.append(inputs[-1])
    return "*".join(accumulated)


# ------------------------------------------------------------- the budget

def test_the_final_turn_makes_no_outbound_call(client, gateway):
    """**The assertion that was missing, in the form that can actually be
    made.**

    Wall-clock through the route cannot show this: Starlette's `TestClient`
    runs background tasks before `client.post` returns, so the six seconds
    still accrue in a test even though the gateway never waits for them in
    production. What *is* observable, and is the property the budget depends
    on, is that **no outbound call happens while the turn is being answered**.
    A turn that makes none cannot be slowed by a slow provider, whatever the
    provider does.
    """
    tasks: list = []
    ussd_handler._sessions.clear()
    inputs = _worst_case_inputs()
    ussd_handler.handle_ussd("budget", "+263771111111", "", defer=tasks.append)
    for i in range(1, len(inputs)):
        ussd_handler.handle_ussd(
            "budget", "+263771111111", "*".join(inputs[:i]), defer=tasks.append)

    calls_before = gateway.calls
    started = time.monotonic()
    body = ussd_handler.handle_ussd(
        "budget", "+263771111111", "*".join(inputs), defer=tasks.append)
    elapsed = time.monotonic() - started

    assert body.startswith("END"), body[:60]
    assert gateway.calls == calls_before, (
        f"the turn made {gateway.calls - calls_before} outbound calls; a turn "
        "that makes any can be held up by a slow provider"
    )
    assert elapsed < BUDGET_SECONDS, (
        f"the turn took {elapsed:.2f}s against a {BUDGET_SECONDS}s budget "
        "even with nothing sent, so something else on it is slow"
    )

    # And the work was handed over rather than dropped.
    assert tasks, "the sending must be deferred, not discarded"
    for task in tasks:
        task()
    assert gateway.calls >= 2, "the miner's SMS and the facility pre-alert"


def test_the_turn_still_tells_the_miner_what_to_do(client, gateway):
    """Moving the sending off the turn must not empty the turn. This is the
    screen a RED self-screener loses when the session is killed, so it has to
    carry something."""
    body = _turn(client, _walk_to_the_last_turn(client)).text
    assert body.startswith("END")
    assert len(body) > len("END ") + 20


def test_every_turn_before_the_last_is_fast_too(client, gateway):
    """The earlier turns never sent anything, and must stay that way: a
    regression here would be a query added per keypress."""
    inputs = _worst_case_inputs()
    _turn(client, "", session="sess-early")
    for i in range(1, len(inputs)):
        started = time.monotonic()
        response = _turn(client, "*".join(inputs[:i]), session="sess-early")
        assert time.monotonic() - started < BUDGET_SECONDS, f"turn {i}"
        assert response.text.startswith("CON"), f"turn {i} should still be asking"


# --------------------------------------------- and the sending still happens

def test_the_sending_happens_after_the_response(client, gateway):
    """Deferred, not dropped. TestClient runs background tasks before it
    returns, so by the time the response is in hand the sends are done — the
    timing assertion above is what proves they were not *on* the turn."""
    _turn(client, _walk_to_the_last_turn(client))
    assert gateway.calls >= 2, (
        f"only {gateway.calls} outbound calls: the miner's SMS and the "
        "facility pre-alert must both still go"
    )


def test_the_screening_is_committed_before_anything_is_sent(client, gateway):
    """Rule 7, and the property that makes deferring safe at all: the
    screening is durable before the first send, so a send that never happens
    cannot cost a screening."""
    from db_models import Screening

    sent_at_commit = {}

    original = notifications._send_sms

    def record_then_send(*args, **kwargs):
        db = next(client.app.dependency_overrides[database.get_db]())
        sent_at_commit["rows"] = len(db.scalars(select(Screening)).all())
        db.close()
        return original(*args, **kwargs)

    final = _walk_to_the_last_turn(client)
    notifications._send_sms = record_then_send
    try:
        _turn(client, final)
    finally:
        notifications._send_sms = original

    assert sent_at_commit.get("rows", 0) >= 1, (
        "the screening must already be committed when the first send runs"
    )


def test_a_failed_send_does_not_lose_the_screening(client, monkeypatch):
    """The reason the sending may be moved at all. A gateway that is down
    costs follow-up, never the record."""
    from db_models import Screening

    def explode(*args, **kwargs):
        raise OSError("the gateway is unreachable")

    monkeypatch.setattr(notifications, "httpx", types.SimpleNamespace(post=explode))
    monkeypatch.setattr(email_notifications, "httpx", types.SimpleNamespace(post=explode))
    ussd_handler._sessions.clear()

    response = _turn(client, _walk_to_the_last_turn(client))
    assert response.status_code == 200 and response.text.startswith("END")

    db = next(client.app.dependency_overrides[database.get_db]())
    assert db.scalars(select(Screening)).all(), "the screening survives the outage"
    db.close()


# ------------------------------------------------- the inline path still works

def test_without_a_defer_the_sends_run_inline(client, gateway):
    """`defer=None` keeps the old behaviour for a caller with no request to
    hang work off — and this is also the shape the measurement was taken in,
    so the test file can show the problem it fixed."""
    ussd_handler._sessions.clear()
    inputs = _worst_case_inputs()
    ussd_handler.handle_ussd("inline", "+263779999999", "")
    for i in range(1, len(inputs)):
        ussd_handler.handle_ussd("inline", "+263779999999", "*".join(inputs[:i]))

    started = time.monotonic()
    ussd_handler.handle_ussd("inline", "+263779999999", "*".join(inputs))
    elapsed = time.monotonic() - started

    assert gateway.calls >= 2
    assert elapsed >= SLOW_CALL_SECONDS * 2, (
        f"inline, the same work takes {elapsed:.1f}s — which is the defect "
        f"the route's `defer` removes, kept here as the measurement"
    )


def test_the_router_defers(client):
    """Structural, so the wiring cannot be dropped while the timing test
    keeps passing on a fast machine."""
    import inspect

    import routers.ussd as module

    source = inspect.getsource(module.ussd_webhook)
    assert "background.add_task" in source
    assert "BackgroundTasks" in inspect.getsource(module)
