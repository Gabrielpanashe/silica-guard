"""Loading reviewed content into the database, reading it back, and rendering
a message for a person.

Master Reference v1.0 §8.4. The decisive tests here are the **round trip**
(the tables hold the file faithfully rather than approximately) and the
**approval gate** (nothing unapproved can reach a worker, so the filler in
`content/messages/example.yaml` is structurally unsendable).

The fixture is that example file, every message of which is `status: draft`.
Tests that need an approved message build one in memory and fill the Shona and
Ndebele entries with strings that are obviously **not** Shona or Ndebele
("TEST sn"). That is deliberate: §8.4 requires local-language text to be
authored by a first-language health communicator, and plausible-looking
invented Shona anywhere in this repository is indistinguishable from reviewed
Shona a month later. Nothing invented is ever written to `content/`.
"""

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import Base, Message, MessageText
from services import content_store
from services.content_store import (
    ContentLoadError,
    ContentNotApproved,
    ContentNotFound,
    PlaceholderError,
)

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "content" / "messages" / "example.yaml"


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'content.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def approved(doc: dict, only: str | None = None) -> dict:
    """The example file with every message (or one named message) approved and
    all three languages present. The sn/nd strings are marked test text, never
    invented Shona or Ndebele — see this module's docstring."""
    out = copy.deepcopy(doc)
    messages = [m for m in out["messages"] if only is None or m["code"] == only]
    out["messages"] = messages
    for message in messages:
        message["status"] = "approved"
        message["approved_by"] = "Clinical Lead"
        message["approved_at"] = "2026-11-01"
        english = message["text"]["en"]
        for language in ("sn", "nd"):
            # Same placeholders as English, because the contract is checked.
            message["text"][language] = f"TEST {language} " + english
    return out


# ------------------------------------------------------------ round trip

def test_the_file_survives_the_round_trip(db, doc):
    """Load, read back, and the dict must match the file message for message.
    A column missing from these tables shows up here rather than as a message
    a worker cannot read."""
    content_store.load(db, doc)
    db.commit()

    for entry in doc["messages"]:
        back = content_store.read(db, entry["code"], entry.get("version", 1))
        assert back["channel"] == entry["channel"]
        assert back["status"] == entry["status"]
        assert back["text"]["en"] == entry["text"]["en"]
        assert back["text"].get("sn") == entry["text"].get("sn")
        assert back["text"].get("nd") == entry["text"].get("nd")
        assert back.get("placeholders", []) == sorted(entry.get("placeholders") or [])
        assert back.get("purpose") == entry.get("purpose")


def test_every_message_in_the_file_reaches_a_table(db, doc):
    content_store.load(db, doc)
    db.commit()
    assert db.query(Message).count() == len(doc["messages"])
    expected_texts = sum(len(m["text"]) for m in doc["messages"])
    assert db.query(MessageText).count() == expected_texts


def test_the_area_label_is_carried_from_the_file(db, doc):
    content_store.load(db, doc)
    db.commit()
    assert {m.area for m in db.scalars(select(Message)).all()} == {"example"}


def test_septets_are_computed_and_stored(db, doc):
    """Stored rather than recomputed per caller, so the segment arithmetic is
    auditable and one definition of it exists."""
    from services.content_format import septets

    content_store.load(db, doc)
    db.commit()
    for row in db.scalars(select(MessageText)).all():
        assert row.septets == septets(row.text_value) >= 0


# ------------------------------------------------------- the approval gate

def test_a_draft_may_not_be_rendered(db, doc):
    """The whole file is draft filler. If this ever passes, filler text is one
    call away from a worker's handset."""
    content_store.load(db, doc)
    db.commit()
    with pytest.raises(ContentNotApproved):
        content_store.render(db, "example.ussd.prompt", "en")


def test_the_example_file_on_disk_is_still_all_draft(doc):
    """Belt and braces: if someone approves a message in the example file, the
    test above stops testing anything."""
    assert {m["status"] for m in doc["messages"]} == {"draft"}


def test_the_example_file_has_no_authored_local_language_text(doc):
    """§8.4. Every sn/nd entry in the example file must still be an explicit
    'to be authored' marker. A plausible-looking invented Shona string here
    would be indistinguishable from a reviewed one within a month."""
    for message in doc["messages"]:
        for language in ("sn", "nd"):
            value = message["text"].get(language)
            if value is None:
                continue
            assert "to be authored" in value, (
                f"{message['code']} [{language}] no longer says it is unauthored"
            )


def test_an_approved_message_renders(db, doc):
    content_store.load(db, approved(doc, only="example.ussd.prompt"))
    db.commit()
    out = content_store.render(db, "example.ussd.prompt", "en")
    assert out["text"].startswith("EXAMPLE FILLER prompt")
    assert out["language"] == "en" and out["version"] == 1
    assert out["gsm7"] is True and out["over_budget"] is False


def test_an_unknown_code_is_not_found(db):
    with pytest.raises(ContentNotFound):
        content_store.render(db, "nope.at.all", "en")


def test_approval_requires_all_three_languages(db, doc):
    """A message is not usable until English, Shona and Ndebele exist. Ndebele
    is not optional in this geography (§8.4)."""
    broken = approved(doc, only="example.sms.result")
    del broken["messages"][0]["text"]["nd"]
    with pytest.raises(ContentLoadError, match="Ndebele"):
        content_store.load(db, broken)


def test_approval_requires_an_approver_and_a_date(db, doc):
    broken = approved(doc, only="example.sms.result")
    del broken["messages"][0]["approved_by"]
    with pytest.raises(ContentLoadError, match="approver"):
        content_store.load(db, broken)


# ------------------------------------------------------------ immutability

def test_an_approved_message_cannot_be_overwritten(db, doc):
    """A consent text or a result message must be reproducible for any session
    that referenced it, so a change is a new version."""
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()

    edited = approved(doc, only="example.sms.result")
    edited["messages"][0]["text"]["en"] = "EDITED {name} {code}"
    with pytest.raises(ContentLoadError, match="immutable"):
        content_store.load(db, edited)


def test_a_retired_message_cannot_be_overwritten(db, doc):
    retired = approved(doc, only="example.sms.result")
    retired["messages"][0]["status"] = "retired"
    content_store.load(db, retired)
    db.commit()
    with pytest.raises(ContentLoadError, match="immutable"):
        content_store.load(db, retired)


def test_a_draft_may_be_reloaded_in_place(db, doc):
    """A string under review is edited repeatedly before approval; reloading
    must replace it rather than accumulate rows."""
    content_store.load(db, doc)
    db.commit()
    first_texts = db.query(MessageText).count()

    content_store.load(db, doc)
    db.commit()
    assert db.query(Message).count() == len(doc["messages"])
    assert db.query(MessageText).count() == first_texts


def test_a_new_version_sits_alongside_the_approved_one(db, doc):
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()

    v2 = approved(doc, only="example.sms.result")
    v2["messages"][0]["version"] = 2
    v2["messages"][0]["text"]["en"] = "SECOND VERSION for {name}, reference {code}."
    for language in ("sn", "nd"):
        v2["messages"][0]["text"][language] = f"TEST {language} {{name}} {{code}}"
    content_store.load(db, v2)
    db.commit()

    assert db.query(Message).count() == 2
    assert content_store.read(db, "example.sms.result", 1)["version"] == 1
    assert content_store.read_active(db, "example.sms.result")["version"] == 2
    assert content_store.render(db, "example.sms.result", "en",
                                {"name": "A", "code": "B"})["version"] == 2


def test_read_active_refuses_when_nothing_is_approved(db, doc):
    content_store.load(db, doc)
    db.commit()
    with pytest.raises(ContentNotApproved):
        content_store.read_active(db, "example.app.notice")


# -------------------------------------------- the character-set trap at load

def test_a_non_gsm7_character_is_refused_at_load(db, doc):
    """One curly apostrophe pasted out of a word processor drops a segment from
    160 characters to 70 and multiplies the cost of every send containing it.
    CI only checks pull requests that touch content/; this check fires on
    anything that tries to enter the database."""
    broken = copy.deepcopy(doc)
    broken["messages"] = [broken["messages"][0]]
    broken["messages"][0]["text"]["en"] = "Don\u2019t for {name}, reference {code}."
    with pytest.raises(ContentLoadError, match="seven-bit"):
        content_store.load(db, broken)


def test_the_error_names_the_replacement_for_a_lookalike(db, doc):
    broken = copy.deepcopy(doc)
    broken["messages"] = [broken["messages"][0]]
    broken["messages"][0]["text"]["en"] = "Don\u2019t for {name}, reference {code}."
    with pytest.raises(ContentLoadError, match=r"use \"'\"|use \"\\'\"|use '"):
        content_store.load(db, broken)


def test_over_budget_is_refused_at_load(db, doc):
    """A string that does not fit is rewritten by its author, never truncated
    at runtime (§13.1)."""
    broken = copy.deepcopy(doc)
    broken["messages"] = [broken["messages"][0]]
    broken["messages"][0]["text"]["en"] = "x" * 200 + " {name} {code}"
    with pytest.raises(ContentLoadError, match="septets against a sms budget"):
        content_store.load(db, broken)


def test_a_max_len_override_is_honoured(db, doc):
    """The override exists so an exception is visible in the data rather than
    argued in a review comment."""
    wide = copy.deepcopy(doc)
    wide["messages"] = [wide["messages"][0]]
    wide["messages"][0]["text"]["en"] = "x" * 200 + " {name} {code}"
    wide["messages"][0]["max_len_override"] = 400
    content_store.load(db, wide)
    db.commit()
    assert content_store.read(db, "example.sms.result", 1)["max_len_override"] == 400


def test_the_extension_set_costs_two_septets(db, doc):
    """`^ { } \\ [ ] ~ |` and the euro sign stay inside seven-bit but each
    counts as two. A budget check that missed this would pass a string the
    network splits into two segments."""
    entry = copy.deepcopy(doc)
    entry["messages"] = [entry["messages"][2]]  # the app-channel message
    entry["messages"][0]["text"] = {"en": "~" * 100}
    entry["messages"][0].pop("placeholders", None)
    content_store.load(db, entry)
    db.commit()
    row = db.scalar(select(MessageText))
    assert row.septets == 200


# ------------------------------------------------- the placeholder contract

def test_a_placeholder_missing_from_one_language_is_refused(db, doc):
    """A placeholder present in English and missing in Shona sends a broken
    message to the people least able to query it."""
    broken = approved(doc, only="example.sms.result")
    broken["messages"][0]["text"]["sn"] = "TEST sn with only {name}"
    with pytest.raises(ContentLoadError, match="placeholders"):
        content_store.load(db, broken)


def test_an_undeclared_placeholder_is_refused_from_review_onward(db, doc):
    broken = copy.deepcopy(doc)
    broken["messages"] = [broken["messages"][1]]  # declares none
    broken["messages"][0]["status"] = "review"
    broken["messages"][0]["text"]["en"] = "Prompt for {name}"
    with pytest.raises(ContentLoadError, match="placeholders"):
        content_store.load(db, broken)


def test_a_draft_with_unauthored_local_language_text_still_loads(db, doc):
    """Parity is checked from `review` onward, matching
    scripts/validate_content.py. A message is authored one language at a time
    over weeks, so a draft whose Shona entry is still a marker must load --
    and `render()` refuses drafts anyway, so nothing can be sent from one."""
    content_store.load(db, doc)
    db.commit()
    stored = content_store.read(db, "example.sms.result", 1)
    assert "to be authored" in stored["text"]["sn"]
    assert stored["placeholders"] == ["code", "name"]


def test_render_substitutes_every_declared_placeholder(db, doc):
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    out = content_store.render(db, "example.sms.result", "en",
                               {"name": "Tendai", "code": "K4R2"})
    assert "Tendai" in out["text"] and "K4R2" in out["text"]
    assert "{" not in out["text"]


def test_render_refuses_a_missing_value(db, doc):
    """Rather than sending literal braces to a worker."""
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    with pytest.raises(PlaceholderError):
        content_store.render(db, "example.sms.result", "en", {"name": "Tendai"})


def test_render_refuses_an_unexpected_value(db, doc):
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    with pytest.raises(PlaceholderError):
        content_store.render(db, "example.sms.result", "en",
                             {"name": "A", "code": "B", "extra": "C"})


def test_render_reports_a_substituted_value_that_breaks_the_character_set(db, doc):
    """content/EXCEPTIONS.md item 2. A worker whose name carries a curly
    apostrophe must still receive their result — rule 7, fail toward
    recording, never toward silence — so this is reported, not refused."""
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    out = content_store.render(db, "example.sms.result", "en",
                               {"name": "O\u2019Brien", "code": "K4R2"})
    assert out["gsm7"] is False and out["over_budget"] is True
    assert out["septets"] is None
    assert "O\u2019Brien" in out["text"]


def test_render_reports_a_substitution_that_overflows_the_budget(db, doc):
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    out = content_store.render(db, "example.sms.result", "en",
                               {"name": "A" * 200, "code": "K4R2"})
    assert out["over_budget"] is True and out["gsm7"] is True


# ----------------------------------------------------------- language choice

def test_the_requested_language_is_served(db, doc):
    content_store.load(db, approved(doc, only="example.app.notice"))
    db.commit()
    out = content_store.render(db, "example.app.notice", "nd")
    assert out["language"] == "nd" and out["text"].startswith("TEST nd")


def test_a_missing_language_falls_back_to_english_and_says_so(db, doc):
    """§8.4 forbids machine translation, so there is no generated fallback. The
    authored English is served and the response names the language actually
    used, which makes an authoring gap visible in the data rather than silent."""
    partial = approved(doc, only="example.app.notice")
    del partial["messages"][0]["text"]["nd"]
    partial["messages"][0]["status"] = "review"  # approval would require all three
    content_store.load(db, partial)
    db.commit()

    served = content_store.catalogue(db, language="nd")
    assert served == [], "an unapproved message is not in the catalogue at all"

    # Approved content with a language gap cannot be created through load(),
    # which is the point — so the fallback is exercised through the row.
    message = db.scalar(select(Message))
    message.status = "approved"
    message.approved_by, message.approved_at = "Clinical Lead", datetime(2026, 11, 1)
    db.commit()
    out = content_store.render(db, "example.app.notice", "nd")
    assert out["language"] == "en"


# ------------------------------------------------------------- the catalogue

def test_the_catalogue_holds_only_approved_messages(db, doc):
    """Offline is the normal case (§10.1): the client caches this and shows it
    with no connectivity, so an unapproved string in it would be an
    unreviewed string on a handset in a gold-panning area."""
    mixed = copy.deepcopy(doc)
    content_store.load(db, mixed)
    content_store.load(db, approved(doc, only="example.app.notice"))
    db.commit()

    rows = content_store.catalogue(db, language="en")
    assert [r["code"] for r in rows] == ["example.app.notice"]


def test_the_catalogue_filters_by_channel(db, doc):
    content_store.load(db, approved(doc))
    db.commit()
    rows = content_store.catalogue(db, language="en", channel="sms")
    assert [r["code"] for r in rows] == ["example.sms.result"]


def test_the_catalogue_returns_the_highest_approved_version(db, doc):
    content_store.load(db, approved(doc, only="example.sms.result"))
    v2 = approved(doc, only="example.sms.result")
    v2["messages"][0]["version"] = 2
    content_store.load(db, v2)
    db.commit()
    rows = content_store.catalogue(db, language="en")
    assert [r["version"] for r in rows] == [2]


def test_the_catalogue_watermark_returns_only_newer_rows(db, doc):
    """Approved versions are immutable and a change is a new row, so creation
    time is a sound watermark for an incremental client refresh."""
    content_store.load(db, approved(doc))
    db.commit()
    assert content_store.catalogue(db, language="en")
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    assert content_store.catalogue(db, language="en", since=future) == []


def test_the_catalogue_carries_the_placeholder_contract(db, doc):
    """The client substitutes offline, so it needs to know what to supply."""
    content_store.load(db, approved(doc, only="example.sms.result"))
    db.commit()
    row = content_store.catalogue(db, language="en")[0]
    assert row["placeholders"] == ["code", "name"]
