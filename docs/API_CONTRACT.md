# SilicaGuard API Contract

This is the source of truth for the backend's HTTP interface. Build the mobile app and dashboard against this document, not against reading the Python.

Every route is marked:
- **LIVE** — implemented today, in the shape described.
- **LIVE (shape will change)** — implemented today, but in an older pre-v4.0 shape; the target v4.0 shape is also shown.
- **TARGET (not yet built)** — specified by the v4.0 reference document, not implemented yet. Shape shown is the plan, not a guarantee — it may shift slightly during implementation. Check back or ask before building a hard dependency on field names here.

Base URL: local dev is `http://127.0.0.1:8000`. **Deployed: `https://silicaguard-backend.onrender.com`** (Render free tier — sleeps after inactivity, warm it with `/api/health` a few minutes before any demo; also note the DB reseeds on every restart, see `CLAUDE.md`'s `AUTO_SEED_ON_BOOT` note).

Interactive docs: **`GET /docs`** (Swagger UI) is enabled by default — nothing in `main.py` disables it. Use it to explore and try requests against a running local server without needing to ask the backend owner anything.

All responses use `snake_case` JSON keys. All timestamps are UTC, ISO 8601. Errors follow FastAPI's default shape: `{"detail": "<message>"}` with an appropriate HTTP status code, unless noted otherwise.

---

## Health

### `GET /api/health` — LIVE

No auth. Liveness check — also useful for warming the free-tier Render server before a demo.

**Response 200**
```json
{ "status": "ok" }
```

---

## Auth

### `POST /api/auth/login` — LIVE (roles will change)

No auth required to call this.

**Request**
```json
{ "email": "hospital@silicaguard.health", "password": "change-me" }
```

**Response 200**
```json
{ "access_token": "eyJhbGciOi...", "role": "hospital" }
```

**Errors**: `401` invalid credentials.

Currently issues one of two demo roles: `hospital`, `cimas`, backed by env-var credentials (no `users` table yet). **Target v4.0 roles are `practitioner`, `clinical`.** This is a planned, not-yet-scheduled change — flag before building UI that assumes the target role names.

### `GET /api/auth/me` — LIVE (dev helper, not part of the target contract)

Requires `Authorization: Bearer <token>`. Returns the decoded token claims. Useful for confirming a token works; not something the mobile app or dashboard should depend on long-term.

**Response 200**
```json
{ "email": "hospital@silicaguard.health", "role": "hospital" }
```

**Errors**: `401` missing/invalid/expired token.

---

## Workers

### `POST /api/workers` — LIVE

Replaces the old `POST /api/miners` (removed 5 August 2026 — that route now 404s).

**Request**
```json
{ "name": "Tendai Moyo", "phone": "+263771234567", "site": "Sherwood Mine" }
```

**Response 200**
```json
{ "id": 14, "name": "Tendai Moyo", "phone": "+263771234567", "site": "Sherwood Mine" }
```

**Errors**: `409` if `phone` is already registered (phone is the persistent worker identity).

**Still TARGET, not in this shape yet**: `job_role`, `employer_id` (the latter is moot post-pivot — see `SILICAGUARD.md` Section 13 — and won't be added). No `workers` schema column exists for `job_role` yet either; don't build UI against it until it lands.

### `GET /api/workers/{phone}` — LIVE

Look up a worker by phone number, returning their full screening history — this is what turns a visit into a re-screen. **Unauthenticated**, same deliberate precedent as `POST /api/screen` (VHWs in the field / USSD hold no dashboard login) — flagged explicitly since this route returns clinical history (tier, advice_line) by phone number alone, a bigger exposure than the write-only route it sits next to.

**Response 200**
```json
{
  "id": 14,
  "name": "Tendai Moyo",
  "phone": "+263771234567",
  "site": "Sherwood Mine",
  "screenings": [
    { "id": 101, "tier": "YELLOW", "created_at": "2026-08-02 09:15:00", "advice_line": "Wear your N95 mask every time you drill or crush, not just sometimes." },
    { "id": 88, "tier": "GREEN", "created_at": "2025-11-10 08:00:00", "advice_line": "Keep doing what you're doing — always wear your N95 mask and ask for wet drilling whenever it's available." }
  ]
}
```
`screenings` is ordered most-recent-first. Empty array for a worker with no screenings yet, not an error.

**Errors**: `404` if no worker with that phone exists.

---

## Mines

### `GET /api/mines` — LIVE (7 August 2026)

Powers the VHW's outreach-site dropdown on the mobile app (previously a hardcoded free-text default). **Unauthenticated**, same field-worker precedent as `POST /api/workers`.

**Response 200**
```json
[
  { "id": 1, "name": "Globe & Phoenix Mine", "district": "Kwekwe", "province": "Midlands" },
  { "id": 6, "name": "Mimosa Mine", "district": "Zvishavane", "province": "Midlands" }
]
```
Ordered by `district`, then `name`. Seeded with 11 Midlands mines (`backend/scripts/seed_demo_data.py`) — illustrative names for the demo, not verified real-world data.

**Deliberately not a foreign key target**: `miners.mine_site` and `outreach_visits.site` both stay free `TEXT`, not `mines.id` — this table is a curated suggestion list for the dropdown, not a hard schema constraint. A full migration tying the two together was judged too risky this close to feature freeze.

### `POST /api/mines` — LIVE (7 August 2026)

For the case where a VHW's site genuinely isn't in the list yet. Unauthenticated.

**Request**
```json
{ "name": "New Mine", "district": "Gweru", "province": "Midlands" }
```
`province` defaults to `"Midlands"` if omitted.

**Response 201**: same shape as a `GET /api/mines` item.

**Errors**: `409` if `name` is already registered.

---

## Screening

### `POST /api/screen` — LIVE (four-tier)

**Request**
```json
{
  "miner_id": 14,
  "answers": [
    { "question_code": "YEARS_UNDERGROUND", "answer_value": "over_10", "answer_score": 5 }
  ],
  "channel": "APP",
  "screened_by": "VHW Grace Chikwanha",
  "offline_fallback_used": false,
  "outreach_visit_id": null
}
```

`outreach_visit_id` (new, optional) links this screening to an Outreach Planner visit (see the Outreach section) for live `screened_count` tracking and the post-visit report. If omitted and `channel` is `"APP"`, the backend infers it by matching the worker's `mine_site` against a scheduled visit at the same site whose `scheduled_date` is today or yesterday (tolerates offline sync lag) — see `backend/services/outreach.py`'s `match_active_visit`. USSD self-screens never auto-link. An explicit id that doesn't exist is silently ignored (the screening still succeeds) rather than rejected — never fail a screening over a bad reference.

**Response 200**
```json
{
  "tier": "YELLOW",
  "confidence": 0.82,
  "explanation_english": "Significant drilling exposure with no symptoms yet...",
  "explanation_shona": "Une njodzi yakati wandei nokuda kwemakore ako ekushanda pasi pevhu.",
  "contributing_factors": ["10+ years underground", "inconsistent PPE use"],
  "advice_line": "Wear your N95 mask every time you drill or crush, not just sometimes.",
  "previous_screening_id": 88,
  "provisional": false,
  "deterioration": {
    "compared_to_screening_id": 88,
    "changed": true,
    "summary": "Deterioration since last screening: BREATHLESSNESS worsened compared to the previous screening."
  }
}
```

**Errors**: `404` unknown `miner_id`; `422` empty `answers`; `502` AI risk engine unavailable (screening + answers are still persisted for retry/audit — only the tier fields stay null).

`tier` is one of `GREEN`, `YELLOW`, `ORANGE`, `RED` (Phase A schema migration, previously 3-tier `LOW`/`WATCH`/`REFER_NOW`). `previous_screening_id` links to this worker's most recent prior screening if one exists. `provisional` mirrors `offline_fallback_used` from the request.

`advice_line` is now always populated (non-negotiable rule: every result must carry one) — a fixed, clinician-**pending** sentence selected from the miner's single weakest answer (`backend/services/advice_engine.py`). **The copy is draft, not yet Clinical-Lead-signed-off** — do not treat the exact wording as final.

`explanation_shona` (**LIVE as of 7 August 2026**, previously TARGET-only) is now always populated too, using the same mechanism and the same weakest-answer selection as `advice_line` (`backend/services/explanation_shona.py`) — a fixed, template-bound Shona sentence, not an AI-generated translation. **Also draft, not yet Clinical-Lead-signed-off.**

`deterioration` is now always present (`backend/services/deterioration.py`): `compared_to_screening_id` is `null` with `changed: false` and an explicit "no previous screening" summary when this is the worker's first screening; otherwise `changed` is `true` if any tracked symptom/exposure answer (`COUGH_DURATION`, `BREATHLESSNESS`, `CHEST_PAIN`, `WEIGHT_LOSS`, `PPE_USE`, `WET_DRILLING`) scored higher than on the previous screening. Any deterioration escalates `tier` one level versus what the AI alone would have returned — this can move a screening into `ORANGE`/`RED` referral territory even when this screening's own answers wouldn't have triggered a referral.

**Hard safety overrides** (`backend/services/safety_overrides.py`) are now enforced in Python, after the AI call, before this response is built — a `severe` value on `BREATHLESSNESS` or `CHEST_PAIN`, a `current` value on `TB_HISTORY`, or a `yes` value on `PRIOR_LUNG_DIAGNOSIS` always forces `tier: "RED"` regardless of what the AI model returned. Applied after deterioration escalation, so nothing can downgrade a safety-triggered RED.

**Result SMS, every tier (7 August 2026)**: `ORANGE`/`RED` results go through `services/referrals.create_referral_and_notify` (referral + facility match + hospital pre-alert + miner SMS, via `send_miner_result`). `GREEN`/`YELLOW` results now also send the miner a result SMS (`services/notifications.send_screening_result_sms`) — previously they sent nothing at all, silently contradicting CLAUDE.md's "everyone receives their result... by SMS." The SMS text for a given tier is the same fixed message the USSD self-screen path uses (`backend/services/tier_messages.py`, shared by both channels as of this change — previously the AI-driven path used one generic ORANGE-flavored message for both ORANGE and RED referrals; RED now gets RED-specific wording).

### `POST /api/ussd` — LIVE

Africa's Talking's USSD webhook. Form-encoded, not JSON — this is Africa's Talking's contract, not ours.

**Request** (form fields)
```
sessionId=ATUid_abc123
phoneNumber=+263771234567
serviceCode=*384*1#
text=1*3*2
```

`text` accumulates every input the caller has entered so far in the session, joined by `*`. The handler reads only the last segment.

**Response 200** (`text/plain`)
```
CON Une kuhema (cough) inoenderera kupfuura mavhiki matatu here?
1. Kwete
2. Hongu, zvishoma
3. Hongu, zvakanyanya
```
`CON` means the session continues and expects another reply; `END` means the session is over. Must respond within 10 seconds and complete within 180 seconds — no AI call happens inside this handler, by design (non-negotiable rule).

---

## Referrals

### `GET /api/referrals` — LIVE (Smart Referral Router: facility matching + reminder/escalation cascade)

Requires `Authorization: Bearer <token>`.

**Response 200**
```json
[
  {
    "id": 7,
    "miner_name": "Tendai Moyo",
    "mine_site": "Sherwood Mine",
    "tier": "RED",
    "status": "pre_alerted",
    "deadline": "2026-08-04 09:15:00",
    "pre_alert_sent": true,
    "facility_id": 1,
    "facility_name": "Kwekwe District Hospital",
    "reminder_stage": 0,
    "attended_at": null,
    "closed_at": null,
    "created_at": "2026-08-02 09:15:00"
  }
]
```

**Errors**: `401` missing/invalid token.

`deadline` is set on creation from the fixed urgency windows in `SILICAGUARD.md` Section 7 Pillar 2 (RED = created_at + 48h, ORANGE = created_at + 14 days).

`facility_id`/`facility_name` (new) are matched by `backend/services/facility_matching.py`: RED always matches a `district_hospital`-level facility, regardless of `mine_site` — the 48h window is too tight to risk a lower-acuity facility. ORANGE tries to match a `clinic`-level facility whose name plausibly serves the worker's site, falling back to the hospital if none matches. `facility_id` is `null` (and `facility_name` falls back to the literal `"Kwekwe District Hospital"`) only if no hospital-level facility is seeded at all.

`reminder_stage` (new) and the `reminded`/`escalated` statuses are now live, driven by an in-process scheduler (`backend/services/referral_cascade.py`, fired via APScheduler in `main.py`) — **not** synchronously on any request: RED gets one reminder at ~24h and escalates at 48h if still unattended; ORANGE reminds at day 3 and day 7 and escalates at day 14. This only runs while the server process is awake — see `SKILL.md`'s Render free-tier warm-up note.

### `PATCH /api/referrals/{referral_id}` — LIVE (new status lifecycle)

Requires `Authorization: Bearer <token>`.

**Request**
```json
{ "status": "closed" }
```
Valid statuses: `open`, `pre_alerted`, `reminded`, `attended`, `closed`, `escalated`. Setting `status` to `attended` stamps `attended_at`; setting it to `closed` stamps `closed_at`. A referral moves to `pre_alerted` automatically when the hospital pre-alert SMS succeeds. `reminded`/`escalated` are now also reachable automatically by the reminder/escalation cascade (see above) — this endpoint can still set them manually too (e.g. a coordinator escalating early).

**Response 200**
```json
{ "id": 7, "miner_name": "Tendai Moyo", "mine_site": "Sherwood Mine", "tier": "RED", "status": "closed", "deadline": "2026-08-04 09:15:00", "pre_alert_sent": true, "facility_id": 1, "facility_name": "Kwekwe District Hospital", "reminder_stage": 0, "attended_at": null, "closed_at": "2026-08-02 10:00:00", "created_at": "2026-08-02 09:15:00" }
```

**Errors**: `401` missing/invalid token; `404` unknown referral; `422` invalid status value.

---

## Outreach

### `POST /api/outreach` — LIVE

Requires `Authorization: Bearer <token>` — a coordinator/dashboard action, not a field action (deliberately not the unauthenticated shape this section originally drafted). Schedules a visit; the 3-day/1-day-before bulk SMS announcement to every worker registered at that site is triggered later by the same in-process scheduler as the referral cascade (`backend/services/outreach.py`, `run_scheduled_outreach`), not synchronously on this call.

**Request**
```json
{ "site": "Sherwood Mine", "scheduled_date": "2026-08-15", "expected_headcount": 40, "health_workers": ["Grace Chikwanha"] }
```

**Response 201**
```json
{
  "id": 3,
  "site": "Sherwood Mine",
  "scheduled_date": "2026-08-15",
  "expected_headcount": 40,
  "screened_count": 0,
  "report_generated": false,
  "tier_distribution": null,
  "referral_list": null
}
```

**Errors**: `401` missing/invalid token.

### `GET /api/outreach` — LIVE

Requires `Authorization: Bearer <token>`. Lists all scheduled/past outreach visits, most-recently-scheduled first.

**Response 200**
```json
[
  {
    "id": 3,
    "site": "Sherwood Mine",
    "scheduled_date": "2026-07-28",
    "expected_headcount": 5,
    "screened_count": 2,
    "report_generated": true,
    "tier_distribution": { "GREEN": 1, "YELLOW": 0, "ORANGE": 1, "RED": 0 },
    "referral_list": [
      { "miner_name": "Kudakwashe Marecha", "tier": "ORANGE", "status": "attended" }
    ]
  }
]
```

**Errors**: `401` missing/invalid token.

`screened_count` increments live as screenings link to the visit (see `POST /api/screen`'s `outreach_visit_id`). `report_generated`, `tier_distribution` and `referral_list` are all `null`/`false` until the visit's `scheduled_date` has passed — at that point the scheduler flips `report_generated` to `true` and `tier_distribution`/`referral_list` are computed live from every screening linked to the visit (not stored as a static snapshot, so they can't go stale). **Known simplification**: "report ready" is approximated as "the scheduled date has passed" — there's no genuine signal anywhere in the schema for "the mobile app has actually finished syncing this visit's offline screenings," so a report can show as ready even if a VHW's phone hasn't synced yet.

---

## Notifications (audit trail — no route yet)

Every SMS sent by the backend (screening result, hospital pre-alert, referral reminder/escalation, outreach announcement — `backend/services/notifications.py`) now logs a row to a `notifications` table (`worker_id`, `channel`, `template`, `payload`, `sent_at`, `delivery_status`: `sent`/`failed`/`skipped`), instead of only a server log line. `worker_id` always identifies the miner whose clinical event triggered the send, even for the two templates that physically go to the hospital nurse (`hospital_prealert`, `referral_escalation`). **No endpoint reads this table yet** — it's audit-only infrastructure for now, intentionally, not an oversight.

---

## Dashboard

### `GET /api/dashboard/today` — LIVE (7 August 2026)

**Unauthenticated** — same deliberate precedent as `POST /api/screen` and `GET /api/workers/{phone}` (a VHW in the field has no dashboard login), and the same tradeoff as that route: returns miner names/phone numbers/tiers without a login, flagged for the same reason it's flagged there. Powers the mobile Home screen's live numbers (previously all hardcoded to 0 client-side): Screened Today, Refer Now, Watch, Today's Log.

Optional query param `?site=<name>` (case-insensitive exact match against `miners.mine_site`) scopes every section to one outreach site.

**Response 200**
```json
{
  "screened_today": 3,
  "todays_log": [
    { "screening_id": 41, "miner_name": "Tendai T", "phone": "+263776877873", "mine_site": "Globe & Phoenix Mine", "tier": "RED", "created_at": "2026-08-07 10:33:51" }
  ],
  "refer_now": {
    "count": 2,
    "items": [
      { "referral_id": 7, "miner_name": "Tendai T", "phone": "+263776877873", "mine_site": "Globe & Phoenix Mine", "tier": "RED", "status": "pre_alerted", "deadline": "2026-08-09 10:33:56" }
    ]
  },
  "watch": {
    "count": 1,
    "items": [
      { "screening_id": 39, "miner_name": "Blessing Sithole", "phone": "+263771000003", "mine_site": "Globe & Phoenix Mine", "tier": "YELLOW", "created_at": "2026-07-18 11:48:55" }
    ]
  }
}
```

`screened_today` / `todays_log` = screenings whose `created_at` falls on the server's current UTC calendar date — Zimbabwe is UTC+2 (CAT), so a screening in the ~2 hours before UTC midnight can land on the "wrong" day. A known simplification, same class as `outreach_visits.report_generated`.

`refer_now` is a **live worklist, not scoped to today** — any referral with `status` in `open`/`pre_alerted`/`reminded`/`escalated`. It drops off once `PATCH /api/referrals/{id}` sets `status` to `attended` or `closed` — that's how "have they taken action" gets answered by re-polling this endpoint, using the contact details already in each item.

`watch` = miners whose **most recent** screening (not just any screening) is `YELLOW` — YELLOW never creates a referral, so this is sourced from `screenings`, not `referrals`. A miner whose YELLOW screening was later superseded by a re-screen of any tier drops off this list.

### `GET /api/dashboard/week` — LIVE (Population Health Intelligence)

Requires `Authorization: Bearer <token>`.

**Response 200**
```json
{
  "total_screened": 142,
  "high_risk_count": 9,
  "referral_completion_rate": 0.67,
  "ai_narrative": "This week 142 miners were screened across three sites, with 9 at elevated risk...",
  "tier_distribution": { "GREEN": 90, "YELLOW": 43, "ORANGE": 7, "RED": 2 },
  "site_breakdown": [
    { "mine_site": "Sherwood Mine", "count": 62 },
    { "mine_site": "Unknown", "count": 5 }
  ]
}
```

**Errors**: `401` missing/invalid token.

`high_risk_count` counts screenings with `tier IN ('ORANGE', 'RED')`. `tier_distribution` (new) is zero-filled for any tier with no screenings this period. `ai_narrative` is now a real Gemini call (`backend/services/population_intelligence.py`, `backend/prompts/population_narrative_prompt.txt`) generated fresh **on every request** (not cached/pre-computed by a scheduled job yet — a fast-follow candidate, not today's scope) — falls back to a deterministic templated sentence built from the same numbers if the AI call fails, so this endpoint never 500s because of it.

---

## Summary table

| Route | Method | Status |
|---|---|---|
| `/api/health` | GET | LIVE |
| `/api/auth/login` | POST | LIVE (roles will change) |
| `/api/auth/me` | GET | LIVE (dev helper) |
| `/api/workers` | POST | LIVE |
| `/api/workers/{phone}` | GET | LIVE |
| `/api/mines` | GET, POST | LIVE |
| `/api/screen` | POST | LIVE (four-tier, hard safety overrides, deterioration detection, advice line + Shona explanation, result SMS for all four tiers) |
| `/api/ussd` | POST | LIVE (four-tier) |
| `/api/referrals` | GET | LIVE (facility matching + reminder/escalation cascade) |
| `/api/referrals/{id}` | PATCH | LIVE (new status lifecycle) |
| `/api/outreach` | POST, GET | LIVE |
| `/api/dashboard/today` | GET | LIVE (unauthenticated, VHW Home-screen numbers) |
| `/api/dashboard/week` | GET | LIVE (real Population Health Intelligence narrative) |
