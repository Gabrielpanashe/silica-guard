"""The content store, read-only, over HTTP.

Master Reference v1.0 §8.4 and §10.1. One route: the approved strings in one
language, so a client can hold a copy and show reviewed text with no
connectivity. **Offline is the normal case** — a village health worker screens
in a gold-panning area with no coverage, so the words a worker reads are
cached on the handset before the visit rather than fetched per screening.

Unauthenticated, on the same deliberate precedent as the screening path: the
mobile application never logs in (`CLAUDE.md`, "API surface"), and this
returns nothing about any person. Every row it serves has the Clinical Lead's
recorded approval, which is the only access control the content itself needs.

There is no write route. Content enters through a migration generated from
`content/`, on a pull request Gabriel approves (§11.4) — an HTTP endpoint that
could add a patient-facing string would be a way around that approval, which
is the one thing this store exists to make impossible.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models_v2 import ContentCatalogueOut, MessageOut
from services import content_store

router = APIRouter(prefix="/api/v2", tags=["content"])


@router.get("/content", response_model=ContentCatalogueOut)
def get_content(
    language: str = Query("en", description="en, sn or nd"),
    channel: str | None = Query(None, description="sms, ussd, app or clinician"),
    since: str | None = Query(
        None,
        description=(
            "ISO-8601 timestamp. Returns only messages created after it. "
            "Approved versions are immutable and a change is a new row, so "
            "this is a sound watermark for an incremental client refresh."
        ),
    ),
    db: Session = Depends(get_db),
):
    if language not in content_store.LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"language must be one of {', '.join(content_store.LANGUAGES)}. "
                "There is no machine translation in this system, so an "
                "unsupported language is an error rather than a fallback."
            ),
        )
    if channel is not None and channel not in content_store.CHANNEL_BUDGET:
        raise HTTPException(
            status_code=400,
            detail=f"channel must be one of {', '.join(content_store.CHANNEL_BUDGET)}",
        )

    watermark = None
    if since:
        try:
            watermark = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="since must be an ISO-8601 timestamp")
        if watermark.tzinfo is not None:
            watermark = watermark.astimezone(timezone.utc).replace(tzinfo=None)

    rows = content_store.catalogue(db, language=language, channel=channel, since=watermark)
    return ContentCatalogueOut(
        language=language,
        count=len(rows),
        messages=[MessageOut(**row) for row in rows],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
