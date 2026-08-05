"""Smart Referral Router — facility matching. SILICAGUARD.md Section 10, AI
module 3: "matches the appropriate facility level". This module is the
matching rule itself: deterministic, no DB access of its own (the caller
queries `facilities` and passes the rows in), same style as
services/deterioration.py.

Matching rule (MVP-level, not clinically rigorous — no geocoding of worker
locations exists, only facility lat/long, which isn't used yet either):

- RED always routes to a district_hospital-level facility, never a clinic.
  The 48h emergency window is too tight to risk a lower-acuity facility,
  regardless of which mine site the worker is at.
- ORANGE tries to match a clinic-level facility whose name plausibly serves
  the worker's mine_site (case-insensitive substring match on the site's
  first word, e.g. "Sherwood Mine" -> "Sherwood Clinic"); falls back to the
  district hospital if no clinic matches.
- Ties among multiple hospital-level facilities are broken by lowest `id`
  (first one seeded/registered wins) — arbitrary but deterministic.
- Returns None if there is no district_hospital-level facility at all
  (empty/unseeded facilities table) — callers must handle this, not crash.
"""

from typing import Optional, Sequence


def _hospitals(facilities: Sequence):
    return sorted(
        (f for f in facilities if f["level"] == "district_hospital"),
        key=lambda f: f["id"],
    )


def _matching_clinic(mine_site: Optional[str], facilities: Sequence):
    if not mine_site:
        return None
    site_key = mine_site.split()[0].lower()
    clinics = sorted(
        (f for f in facilities if f["level"] == "clinic" and site_key in f["name"].lower()),
        key=lambda f: f["id"],
    )
    return clinics[0] if clinics else None


def select_facility(tier: str, mine_site: Optional[str], facilities: Sequence):
    """Returns the matched facility row (dict-like — sqlite3.Row or dict,
    indexed by ["id"]/["name"]/["level"]), or None if no hospital-level
    facility exists to fall back to."""
    hospitals = _hospitals(facilities)
    fallback = hospitals[0] if hospitals else None

    if tier == "RED":
        return fallback

    if tier == "ORANGE":
        return _matching_clinic(mine_site, facilities) or fallback

    return fallback
