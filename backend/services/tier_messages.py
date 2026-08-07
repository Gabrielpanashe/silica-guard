"""Fixed Shona/English result messages, keyed by tier — the single source of
truth shared between the USSD decision tree (services/ussd_handler.py) and
the AI-driven /api/screen path (routers/screening.py).

Previously these diverged: ussd_handler.py had its own inline per-tier text,
while routers/screening.py used one generic ORANGE-flavored string
(GENERIC_REFERRAL_SHONA_MESSAGE, formerly in services/referrals.py) for
every AI-triggered referral regardless of whether the tier was actually
ORANGE or RED. Centralising here means both channels say the same thing for
the same tier, and RED miners on the APP path now get RED-specific wording
instead of the ORANGE "you'll get an X-ray" text.

DRAFT COPY, same caveat as services/advice_engine.py: none of this text has
the Clinical Lead's written sign-off yet (CLAUDE.md non-negotiable rule).
The GREEN/YELLOW/ORANGE/RED text below is reused verbatim from the
pre-v4.0 doctor-approved wording (see services/ussd_handler.py's prior
inline copy) — not reworded here, just relocated.
"""

# tier -> (shona, english)
TIER_MESSAGES = {
    "RED": (
        "Matiripo ako aratidza njodzi yakakwira. Enda kuchipatara Kwekwe nhasi.",
        "Your answers show serious warning signs. Please go to Kwekwe District Hospital today.",
    ),
    "ORANGE": (
        "Zvakafanana nemamiriro ane njodzi. Enda kuchipatara Kwekwe nhasi kuti upiwe X-ray.",
        "Your exposure and symptoms suggest high risk. Go to Kwekwe District Hospital for a chest X-ray.",
    ),
    "YELLOW": (
        "Une njodzi yakati wandei. Enda kuchipatara mumwedzi uno.",
        "You have moderate risk. Visit a clinic within the next 4 weeks.",
    ),
    "GREEN": (
        "Njodzi yako iri pasi. Ramba uchipfeka mask yako nguva dzose.",
        "Your risk appears low. Keep wearing your mask and stay safe.",
    ),
}
