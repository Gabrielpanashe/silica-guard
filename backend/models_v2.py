"""Pydantic request and response shapes for the `/api/v2` surface.

Kept apart from `models.py` rather than grown into it. The v1 shapes serve the
mobile application and dashboard until those clients move (`docs/
IMPLEMENTATION_PLAN.md` §5), and two files make it obvious which contract a
change affects -- `docs/API_CONTRACT.md` is versioned the same way.

The v1 file is deleted with the adapter, not merged into this one.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    """One approved string in one language — what a client caches so that the
    text it shows offline is the reviewed text (§8.4, §10.1).

    `language` is what was actually served, which may be the English fallback
    rather than the language asked for. It is reported rather than silently
    substituted: there is no machine translation anywhere in this system, so a
    missing language is a gap in authoring and the client should be able to see
    that it has one.
    """

    code: str
    version: int
    channel: str
    language: str
    text: str
    placeholders: List[str] = Field(default_factory=list)


class ContentCatalogueOut(BaseModel):
    """The snapshot. `language` echoes the request; a message served in English
    instead carries its own `language` on the row."""

    language: str
    count: int
    messages: List[MessageOut]
    #: Null when the store holds no approved content yet, which is the correct
    #: state until the Clinical Lead approves version one rather than an error.
    generated_at: Optional[str] = None
