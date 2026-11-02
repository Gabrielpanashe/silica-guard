"""The active instrument, for a device to interpret offline.

Master Reference v1.0 §10.1 — **offline is the normal case** — and
`docs/IMPLEMENTATION_PLAN.md` §5 and item 1.14a. This is the route the mobile
application fetches before an outreach visit so that the handset can run the
same cascade with no connectivity, and it is what unblocks the JavaScript port
of `services/predicates.py`.

**It serves the whole instrument, not a channel-filtered subset, and that is a
safety decision rather than laziness.** Removing a question the channel does
not ask would be the obvious optimisation and would silently change what the
rules do: a question absent from the document can never be `unknown`, so a
safety rule of the form `{"unknown": "Q"}` — the §12.2 item 10 protection that
stops an unanswered red flag reading as a negative — would stop firing. A
transport optimisation that disarms a red-flag rule is the worst kind of bug,
because nothing fails and the tier is simply wrong.

So the `channel` parameter **annotates** rather than filters: the response
names which questions that channel asks, and the device renders those while
evaluating the rules over the whole document, exactly as
`services/rules_engine.py` does. The two interpreters have to behave
identically — that is what "channels are equivalent" means — and the only way
to guarantee it is to give them the same input.

**Unauthenticated**, on the same precedent as the screening path: the village
health worker's application never logs in, and an instrument version is not
personal data. It is also already public in effect — the clinical content is
a reviewed document the team intends to publish for scrutiny (§17), and an
instrument nobody outside the team can read is an instrument nobody outside
the team can check.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import Instrument
from models_v2 import InstrumentOut
from services import instrument_store
from services.instrument_store import InstrumentLoadError

router = APIRouter(prefix="/api/v2", tags=["instrument"])

#: Channels a question can be limited to, matching `instrument_channels`.
CHANNELS = ("app", "ussd")


def _channel_questions(document: dict, channel: str) -> list[str]:
    """Question codes this channel asks.

    Branching is **not** resolved here: a question whose `branching` predicate
    depends on an answer cannot be known before the answers exist. The device
    evaluates branching as it goes, which is what `rules_engine.
    applicable_questions()` does with a part-filled screening.
    """
    out: list[str] = []
    for question in document.get("questions") or []:
        channels = question.get("channels")
        if channels is None or channel in channels:
            out.append(question["code"])
    return out


@router.get("/instrument/active", response_model=InstrumentOut)
def get_active_instrument(
    channel: str = Query("app", description="app or ussd"),
    code: str | None = Query(
        None,
        description=(
            "Instrument code. Required only when the database holds more than "
            "one instrument — an instrument is chosen deliberately, never "
            "guessed."
        ),
    ),
    db: Session = Depends(get_db),
):
    """The highest approved version of an instrument, whole.

    `404` when nothing is approved, which is the state until instrument
    version one lands (item 1.4) and is correct rather than an error
    condition: a device must not be handed a draft to screen against.
    """
    if channel not in CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"channel must be one of {', '.join(CHANNELS)}",
        )

    if code is None:
        codes = sorted({row for row in db.scalars(select(Instrument.code)).all()})
        if not codes:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No instrument is loaded. Instrument version one is the "
                    "Clinical Lead's deliverable (§12.5); until it is approved "
                    "there is nothing to screen against, and that is the "
                    "correct state rather than a fault."
                ),
            )
        if len(codes) > 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The database holds {len(codes)} instruments "
                    f"({', '.join(codes)}), so `code` is required. An "
                    "instrument is chosen deliberately, never guessed."
                ),
            )
        code = codes[0]

    try:
        document = instrument_store.read_active(db, code)
    except InstrumentLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return InstrumentOut(
        code=document["code"],
        version=document["version"],
        status=document["status"],
        approved_by=document.get("approved_by"),
        approved_at=document.get("approved_at"),
        ruleset_version=f"{document['code']}-v{document['version']}",
        channel=channel,
        channel_questions=_channel_questions(document, channel),
        instrument=document,
    )


@router.get("/instrument/versions", response_model=list[dict])
def list_instrument_versions(db: Session = Depends(get_db)):
    """Every stored version and its status.

    Exists so that "which instrument is this server serving?" is answerable
    without database access — the question §10.1 says every clinical output
    must be traceable to. Carries no clinical content, only provenance.
    """
    return [
        {
            "code": row.code,
            "version": row.version,
            "status": row.status,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at.date().isoformat() if row.approved_at else None,
            "supersedes": row.supersedes,
        }
        for row in db.scalars(
            select(Instrument).order_by(Instrument.code, Instrument.version)
        ).all()
    ]
