"""No personal data in a log line.

`CLAUDE.md` lists this among the rules that are not negotiable, and
`docs/SECURITY.md` §"Controls" repeats it. Master Reference v1.0 §16.2.

**What was wrong until 10 November 2026.** `services/notifications._send_sms`
logged the recipient's telephone number on success, logged it again on
failure, and logged the gateway's entire response body — which carries
`SMSMessageData.Recipients[].number`, so the number reached the log from the
provider as well as from us. `docs/IMPLEMENTATION_PLAN.md` §9 called it "a
one-line fix that should not wait for Phase Two"; it was three lines across
two files, and **the response-body line was the one that mattered**, because
it is the one nobody thinks to look for.

Two kinds of test, because one of them alone is not enough:

  **Behavioural.** Drive the real sender with a fake gateway that answers the
  way Africa's Talking does — a body naming the recipient — and assert the
  number appears nowhere in what was logged. This is the test that would have
  caught the original bug, including the provider-echo half of it.

  **Structural.** Walk the AST of every service and router and fail on a
  `logger.*` call that passes an argument whose name looks like personal
  data. A behavioural test only covers the call sites someone thought to
  exercise; this one covers the ones nobody has written yet.
"""

import ast
import logging
import pathlib

import pytest

from services import email_notifications, notifications

BACKEND = pathlib.Path(__file__).resolve().parent.parent

NUMBER = "+263771234567"

#: A real Africa's Talking success body. The recipient's number is in it,
#: which is the whole reason `response.text` may not be logged.
GATEWAY_BODY = (
    '{"SMSMessageData":{"Message":"Sent to 1/1 Total Cost: ZMW 0.8000",'
    '"Recipients":[{"statusCode":101,"number":"' + NUMBER + '",'
    '"status":"Success","cost":"KES 0.8000","messageId":"ATXid_abc123"}]}}'
)


class _Capture:
    """Collect everything written to a logger, formatted as it would appear.

    `caplog` does not see records emitted inside a `TestClient` request on
    this setup, and the formatted string is what matters here rather than the
    record's arguments: a `%s` that never interpolates is not a leak, and one
    that does is.
    """

    def __init__(self, *names):
        self.names = names
        self.lines: list[str] = []

    def __enter__(self):
        self.handlers = []
        for name in self.names:
            handler = logging.Handler(logging.DEBUG)
            handler.emit = lambda record: self.lines.append(
                record.getMessage() + (
                    logging.Formatter().formatException(record.exc_info)
                    if record.exc_info else ""
                )
            )
            logging.getLogger(name).addHandler(handler)
            self.handlers.append((name, handler))
        return self

    def __exit__(self, *exc):
        for name, handler in self.handlers:
            logging.getLogger(name).removeHandler(handler)
        return False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class _FakeResponse:
    def __init__(self, status_code=200, text=GATEWAY_BODY):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} from the gateway")


# ------------------------------------------------------------- behavioural

def test_a_successful_send_does_not_log_the_number(monkeypatch):
    """**The assertion the original bug needed.** Both halves: the number we
    passed in, and the number the gateway echoes back in its body."""
    monkeypatch.setattr(notifications.httpx, "post", lambda *a, **k: _FakeResponse())

    with _Capture("silicaguard.notifications") as log:
        assert notifications._send_sms(NUMBER, "Test message.",
                                       notifications._reference(41, "miner_result")) is True

    assert log.text, "something must be logged: a send that leaves no trace is its own problem"
    assert NUMBER not in log.text
    assert "771234567" not in log.text, "nor any part of it long enough to dial"
    assert "Recipients" not in log.text, "the gateway's body names the recipient"


def test_a_failed_send_does_not_log_the_number(monkeypatch):
    """The failure path logged it too, and `logger.exception` adds a traceback
    whose frames can carry local variables in some formatters."""
    monkeypatch.setattr(
        notifications.httpx, "post", lambda *a, **k: _FakeResponse(status_code=502))

    with _Capture("silicaguard.notifications") as log:
        assert notifications._send_sms(NUMBER, "Test message.",
                                       notifications._reference(41, "miner_result")) is False

    assert "FAILED" in log.text, "a failed send must be visible"
    assert NUMBER not in log.text
    assert "771234567" not in log.text


def test_a_network_error_does_not_log_the_number(monkeypatch):
    """An httpx exception's string form carries the request URL. The number
    travels in the form body, not the URL, so it must not surface — asserted
    rather than assumed, because it depends on the client library."""
    def explode(*args, **kwargs):
        raise OSError(f"connection refused while posting to {notifications._AT_SMS_URL}")

    monkeypatch.setattr(notifications.httpx, "post", explode)

    with _Capture("silicaguard.notifications") as log:
        assert notifications._send_sms(NUMBER, "Test.", "worker=41 template=x") is False

    assert NUMBER not in log.text


def test_the_log_still_says_enough_to_be_useful(monkeypatch):
    """Removing the number must not leave a log nobody can act on. "Did this
    worker's RED result get out?" has to be answerable from the log alone,
    which is why the reference carries an integer key and a template name."""
    monkeypatch.setattr(notifications.httpx, "post", lambda *a, **k: _FakeResponse())

    with _Capture("silicaguard.notifications") as log:
        notifications._send_sms(NUMBER, "Test message.",
                                notifications._reference(41, "referral_reminder"))

    assert "worker=41" in log.text
    assert "referral_reminder" in log.text


def test_the_reference_carries_nothing_contactable():
    reference = notifications._reference(41, "miner_result")
    assert NUMBER not in reference
    assert reference == "worker=41 template=miner_result"


def test_the_email_sender_does_not_log_the_provider_body(monkeypatch):
    """Resend's body is an id today, and a provider's response shape is not
    ours to rely on. The id is the only part worth keeping."""
    monkeypatch.setattr(email_notifications, "_log_notification", lambda *a, **k: None)
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_TO", "nurse@example.org")
    monkeypatch.setattr(
        email_notifications.httpx, "post",
        lambda *a, **k: _FakeResponse(text='{"id":"re_abc","to":["nurse@example.org"]}'))

    with _Capture("silicaguard.email_notifications",
                  "silicaguard.notifications") as log:
        email_notifications.send_referral_alert_email(
            worker_id=41, miner_name="Tendai Moyo", phone_number=NUMBER,
            mine_site="Globe & Phoenix", tier="RED",
            contributing_factors=["long exposure"],
        )

    assert "nurse@example.org" not in log.text
    assert "Tendai" not in log.text
    assert NUMBER not in log.text


# -------------------------------------------------------------- structural

#: Argument names that are personal data, or that hold a provider's response.
#: Checked by name because that is what a reviewer sees: a `logger.info` whose
#: argument reads `phone_number` is wrong on sight, whatever it happens to
#: contain at runtime.
FORBIDDEN = {
    "to", "phone", "phone_number", "number", "recipient", "recipients",
    "name", "miner_name", "worker_name", "full_name", "email", "email_to",
    "national_id", "nid", "answers", "answer", "message", "body", "text",
    "payload", "password", "token", "address", "participant_code",
}

#: Attribute accesses that are a provider's whole response.
FORBIDDEN_ATTRS = {"text", "content", "body"}

LOG_METHODS = {"info", "warning", "warn", "error", "exception", "critical", "debug", "log"}


def _logging_calls(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOG_METHODS:
            continue
        target = node.func.value
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
        if "log" in str(name).lower():
            yield node


def _offences(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for call in _logging_calls(tree):
        for arg in call.args[1:] + [kw.value for kw in call.keywords]:
            if isinstance(arg, ast.Name) and arg.id.lower() in FORBIDDEN:
                out.append(f"{path.name}:{call.lineno} logs `{arg.id}`")
            elif isinstance(arg, ast.Attribute) and arg.attr in FORBIDDEN_ATTRS:
                base = getattr(arg.value, "id", "?")
                out.append(f"{path.name}:{call.lineno} logs `{base}.{arg.attr}`")
    return out


SOURCES = sorted(
    path for folder in ("services", "routers", "scripts")
    for path in (BACKEND / folder).glob("*.py")
)


def test_there_are_sources_to_check():
    """A sweep over an empty list passes for the wrong reason."""
    assert len(SOURCES) > 20, SOURCES


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_log_line_takes_personal_data(path):
    """**The guard the behavioural tests cannot be.** They cover the call
    sites somebody exercised; this covers the ones nobody has written yet.

    If this fails on a legitimate line, the fix is to log an id instead of the
    value — not to add the name to an allowlist, because the names in
    `FORBIDDEN` are exactly the ones that identify a person.
    """
    assert _offences(path) == []


def test_the_sweep_catches_the_original_bug(tmp_path):
    """The guard tested against the failure rather than against itself —
    verbatim, as `services/notifications.py` had it."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import logging\n"
        "logger = logging.getLogger('x')\n"
        "def f(to, message, response):\n"
        "    logger.info('SMS to %s: %s', to, response.text)\n"
        "    logger.exception('Failed to send SMS to %s', to)\n",
        encoding="utf-8",
    )
    found = _offences(sample)
    assert len(found) == 3, found
    assert any("`to`" in f for f in found)
    assert any("response.text" in f for f in found)
