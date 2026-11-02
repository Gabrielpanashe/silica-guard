# SilicaGuard API Contract

> **Two contracts live here.** Everything from Health to Dashboard below is **v1**: the prototype API as it runs today. The **v2 section** near the end holds the Phase One routes as they land, one at a time, under `/api/v2/`. The v1 routes keep serving the current mobile application and dashboard until those clients move, then become thin adapters over v2 storage and are deleted (`docs/IMPLEMENTATION_PLAN.md` §5). No v1 route survives to the pilot.

> **The v1 contract.** The Phase One rebuild (`ARCHITECTURE.md` — per-condition result rows, person/contact identity, instrument versions, consent) changes the shape of most routes below. Until a route's v2 replacement lands, the v1 shape here is accurate for the deployed backend and is what both frontends build against.

This is the source of truth for the backend's HTTP interface. Build the mobile app and dashboard against this document, not against reading the Python.

Every route is marked:
- **LIVE** — implemented today, in the shape described.
- **LIVE (shape will change)** — implemented today, but in an older pre-v4.0 shape; the target v4.0 shape is also shown.
- **TARGET (not yet built)** — specified by the v4.0 reference document, not implemented yet. Shape shown is the plan, not a guarantee — it may shift slightly during implementation. Check back or ask before building a hard dependency on field names here.

Base URL: local dev is `http://127.0.0.1:8000`. **Deployed: `https://silicaguard-backend.onrender.com`** (Render free tier — sleeps after inactivity, warm it with `/api/health` a few minutes before any demo). **As of 16 August, Postgres via Supabase (master doc v6.0 Section 16.2, Step B) — storage is persistent**, and `AUTO_SEED_ON_BOOT` is `false` in production, so state (screenings, referral-code confirmations) now survives restarts/sleep-wake and across the 25–27 August rehearsals. A scheduled keep-alive job (`services/db_keepalive.py`) pings the database periodically so the free Supabase project's 7-day auto-pause window is never hit before the 28 August showcase. Re-seed manually (`scripts/seed_demo_data.py`) when you actually want a known-good reset — it now wipes and reseeds Postgres, not a local file.

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

**`schema`, additive as of 2 November 2026.** `database: up` means the database answered `SELECT 1`; it says nothing about whether the schema matches the code. Those are different failures with different fixes, and during the Phase One deploy they were indistinguishable from outside: every route touching a missing column returned 500 while this endpoint reported everything fine.

```json
{"status": "ok", "database": "up", "schema": "drifted",
 "schema_missing": {"referrals": ["result_id", "outcome"],
                    "screening_answers": ["session_id"]}}
```

`schema` is `ok` or `drifted`, and `schema_missing` appears only when drifted. Both are absent when `database` is `down`, because there is nothing to compare against.

Served from a check run **at boot**, not recomputed per request: this endpoint is also what wakes a sleeping free-tier instance, and inspecting thirty-five tables on every call would make it slow for no benefit — drift only changes when a migration runs. **`GET /api/health?recheck=1`** forces a fresh look, which is what you want immediately after running one.

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

Currently issues one of two demo roles: `hospital`, `cimas`, backed by env-var credentials (no `users` table yet). A `practitioner`/`clinical` role rename was floated in an earlier version but explicitly declined as not needed post-pivot (see `CLAUDE.md`) — don't build UI assuming those role names will arrive. The master doc's "four role views" dashboard concept (Section 16.3: MoHCC, NSSA, Cimas, Hospital) is a dashboard-side filtering question, not necessarily a backend role-rename — undecided, raise with the team before building against it.

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

**Still TARGET, not in this shape yet**: `job_role`, `employer_id` (the latter is moot post-pivot — no formal-sector features in phase one, see `README.md` "Scope decisions that are locked" — and won't be added; the v2 schema's nullable programme reference replaces the concept). No `workers` schema column exists for `job_role` yet either; don't build UI against it until it lands.

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

## Facilities

### `GET /api/facilities` — LIVE (12 August 2026)

Powers the mobile Outreach Planner's "nearest hospital" preview when scheduling a visit. **Unauthenticated**, same precedent as `GET /api/mines`. Read-only view of the same rows `backend/services/facility_matching.py` already uses internally for referral routing.

**Response 200**
```json
[
  { "id": 1, "name": "Kwekwe District Hospital", "level": "district_hospital", "address": "Corner Robert Mugabe / Sixth Ave, Kwekwe", "phone": "055-24000", "latitude": -18.9281, "longitude": 29.8149 },
  { "id": 2, "name": "Sherwood Clinic", "level": "clinic", "address": "Sherwood Mine, Kwekwe", "phone": "055-24101", "latitude": null, "longitude": null }
]
```
Ordered by `level`, then `name`.

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
  },
  "referral_code": null,
  "facility_name": null,
  "deadline": null
}
```

**`referral_code`/`facility_name`/`deadline` (new 16 August 2026, real bug fix)**: populated only when this screening's tier is `ORANGE`/`RED` (a referral was created), `null` otherwise. Previously **absent from this response entirely** despite the referral-code feature (master doc v6.0 Section 1.1) being live since 15 August — the only consumer with no auth token (the VHW mobile app) had no way to get the real code at screening time, and was rendering its own client-side-fabricated one instead, which could never actually be looked up at `GET /api/referrals/lookup/{code}`. `referral_code` here is guaranteed to be the same value that route returns for it — build any "show the referral card" UI against these three fields now, not a locally-generated ID. `deadline` uses the same string format as everywhere else in this doc (`"YYYY-MM-DD HH:MM:SS"`, via `database.format_datetime`).

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

### `GET /api/miners` — LIVE (10 August 2026)

Requires `Authorization: Bearer <token>`. The dashboard's Miners directory — every registered miner, most recently active first. Distinct from `GET /api/workers/{phone}` (unauthenticated, single-miner lookup for the VHW re-screen flow) — this is the full roster for a logged-in coordinator.

**Response 200**
```json
[
  { "id": 14, "name": "Tendai Moyo", "phone": "+263771234567", "site": "Sherwood Mine", "latest_tier": "ORANGE", "screening_count": 2, "last_screened_at": "2026-08-09 10:33:51", "created_at": "2026-07-01 08:00:00" }
]
```
`latest_tier`/`last_screened_at` are `null` for a miner with no screenings yet (registered but not yet screened). `latest_tier` is the miner's **most recent** screening's tier, not their first or their worst.

### `GET /api/screenings` — LIVE (10 August 2026)

Requires `Authorization: Bearer <token>`. The dashboard's All Screenings activity log — every screening across every miner and channel (`APP`/`USSD`), most recent first. Optional `?limit=` (default 200) caps the response.

**Response 200**
```json
[
  { "id": 41, "miner_id": 14, "miner_name": "Tendai Moyo", "phone": "+263771234567", "site": "Sherwood Mine", "tier": "RED", "channel": "APP", "advice_line": "A cough that has lasted this long needs to be checked by a clinician as soon as possible.", "created_at": "2026-08-09 10:33:51" }
]
```

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
    "referral_code": "SG-4K7Q",
    "reminder_stage": 0,
    "attended_at": null,
    "closed_at": null,
    "created_at": "2026-08-02 09:15:00"
  }
]
```

**Errors**: `401` missing/invalid token.

`deadline` is set on creation from the fixed urgency windows (RED = created_at + 48h, ORANGE = created_at + 14 days) — the tier-3 window is one of the items awaiting explicit clinical confirmation in `docs/CLINICAL.md`.

`facility_id`/`facility_name` (new) are matched by `backend/services/facility_matching.py`: RED always matches a `district_hospital`-level facility, regardless of `mine_site` — the 48h window is too tight to risk a lower-acuity facility. ORANGE tries to match a `clinic`-level facility whose name plausibly serves the worker's site, falling back to the hospital if none matches. `facility_id` is `null` (and `facility_name` falls back to the literal `"Kwekwe District Hospital"`) only if no hospital-level facility is seeded at all.

`reminder_stage` (new) and the `reminded`/`escalated` statuses are now live, driven by an in-process scheduler (`backend/services/referral_cascade.py`, fired via APScheduler in `main.py`) — **not** synchronously on any request: RED gets one reminder at ~24h and escalates at 48h if still unattended; ORANGE reminds at day 3 and day 7 and escalates at day 14. This only runs while the server process is awake — see the free-tier notes in `docs/STACK.md`.

### `PATCH /api/referrals/{referral_id}` — LIVE (new status lifecycle)

Requires `Authorization: Bearer <token>`.

**Request**
```json
{ "status": "closed" }
```
Valid statuses: `open`, `pre_alerted`, `reminded`, `attended`, `closed`, `escalated`. Setting `status` to `attended` stamps `attended_at`; setting it to `closed` stamps `closed_at`. A referral moves to `pre_alerted` automatically when the hospital pre-alert SMS succeeds. `reminded`/`escalated` are now also reachable automatically by the reminder/escalation cascade (see above) — this endpoint can still set them manually too (e.g. a coordinator escalating early).

**Response 200**
```json
{ "id": 7, "miner_name": "Tendai Moyo", "mine_site": "Sherwood Mine", "tier": "RED", "status": "closed", "deadline": "2026-08-04 09:15:00", "pre_alert_sent": true, "facility_id": 1, "facility_name": "Kwekwe District Hospital", "referral_code": "SG-4K7Q", "reminder_stage": 0, "attended_at": null, "closed_at": "2026-08-02 10:00:00", "created_at": "2026-08-02 09:15:00" }
```
`referral_code` (new 15 August 2026, see below) appears here too, and on `GET /api/referrals`, not just the lookup routes and SMS text.

**Errors**: `401` missing/invalid token; `404` unknown referral; `422` invalid status value.

### `GET /api/referrals/lookup/{code}` — LIVE

Master doc v6.0 Section 1.1/16.6 (14 August 2026, built 15 August). No auth: hospital staff have no login, same deliberate precedent as `POST /api/screen` and `GET /api/workers/{phone}`. `{code}` is the short human-readable code generated at referral creation (`SG-4K7Q` style — `SG-` + 4 chars from an alphabet excluding `0/O/1/I`), sent to the miner by SMS (`services.notifications.send_miner_result`) and included in the facility pre-alert (`send_hospital_prealert`).

**Response 200**
```json
{
  "referral_code": "SG-4K7Q",
  "tier": "RED",
  "status": "pre_alerted",
  "deadline": "2026-08-17 09:15:00",
  "miner_name": "Tendai Moyo",
  "mine_site": "Sherwood Mine",
  "facility_name": "Kwekwe District Hospital",
  "advice_line": "...",
  "contributing_factors": ["..."],
  "attended_at": null
}
```
**Errors**: `404` unknown code.

Takudzwa builds the hospital-facing entry page in `dashboard/` against this contract.

### `POST /api/referrals/lookup/{code}/confirm-attendance` — LIVE

Companion to the route above. No auth, same reasoning. Sets `status='attended'`, `attended_at=now`. This is what makes referral completion rate (the project's headline KPI, master doc Section 7.5) measurable end to end instead of self-reported. Rejects a referral already `attended` or `closed` rather than silently re-stamping `attended_at`.

**Response 200**
```json
{ "referral_code": "SG-4K7Q", "status": "attended", "attended_at": "2026-08-16 11:02:00" }
```
**Errors**: `404` unknown code; `409` already attended/closed.

### `POST /api/referrals/notify-email` — LIVE (12 August 2026, undocumented until 16 August)

Fires the hospital referral-alert email (`services/email_notifications.py`, Resend) for a worker's most recent referral. Unauthenticated, mobile-facing — called by `ReferralScreen.js` when the VHW taps "Generate Referral Card," so the demo has a live, on-demand email trigger tied to that exact moment. **This is a deliberate re-send**, not the only time the email fires: the same email already fires automatically inside `POST /api/screen` at referral-creation time (`services/referrals.create_referral_and_notify`) — a hospital shouldn't wait on a miner tapping a button in the app to be pre-alerted.

**Request**
```json
{ "phone": "+263771234567" }
```

**Response 200**
```json
{ "sent": true, "tier": "RED", "facility_name": "Kwekwe District Hospital" }
```
`sent` reflects the actual Resend API call result (`false` on failure, e.g. `RESEND_API_KEY` unset — never raises).

**Errors**: `404` unknown phone, or the worker has no referral on record.

### Every referral-code lookup is audited — LIVE 2 November 2026

Applies to all four unauthenticated referral-code routes: `GET /api/referrals/lookup/{code}`, `POST /api/referrals/lookup/{code}/confirm-attendance`, and the v2 pair `GET /api/v2/referrals/{code}` and `POST /api/v2/referrals/{code}/close`.

They have no login by design — hospital staff have no dashboard account — and the v1 lookup returns a name and a mine site against a six-character code, which makes this the most exposed identified-data surface in the system. §16.3 requires every clinical read and write to be recorded, and these four were the only ones escaping it.

A hit writes an `allowed=True` row. An unknown code, a repeat attendance confirmation and a rejected outcome each write `allowed=False`, so a walk through the code space appears as a run of refusals in `GET /api/v2/audit/refusals` rather than as nothing at all. The actor is recorded as `facility_lookup_unauthenticated` rather than left empty, because a NULL actor must mean one thing; that role holds no capability and `require()` can never produce it.

**No response shape changes.** Two behaviours do: a read that cannot be recorded returns an error rather than being served quietly, because an unauthenticated read of an identified record that leaves no trace is what §16.3 forbids; and a log failure on the *miss* path still returns a clean `404`, so the log's state cannot be probed by watching status codes.

Rate limiting and lockout are Phase Two (`docs/SECURITY.md`). This is detection without prevention, deliberately — and until they exist an unauthenticated caller can grow the audit table one row per attempt, which the rate limit is what bounds.

---

## Outreach

### `POST /api/outreach` — LIVE

**Unauthenticated as of 12 August 2026** — was `Authorization: Bearer <token>`-gated (a coordinator/dashboard action, not a field action) until the mobile Outreach Planner needed to schedule a visit directly from a VHW's phone, which has no login. Explicit scope decision to demonstrate the functionality now rather than build mobile auth first — flagged in `CLAUDE.md`'s sprint status, not a silent change. `GET /api/outreach` below is unaffected and still requires auth (the dashboard's coordinator view). Schedules a visit; the 3-day/1-day-before bulk SMS announcement to every worker registered at that site is triggered later by the same in-process scheduler as the referral cascade (`backend/services/outreach.py`, `run_scheduled_outreach`), not synchronously on this call.

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
      { "referral_id": 7, "miner_name": "Tendai T", "phone": "+263776877873", "mine_site": "Globe & Phoenix Mine", "tier": "RED", "status": "pre_alerted", "deadline": "2026-08-09 10:33:56", "referral_code": "SG-4K7Q", "facility_name": "Kwekwe District Hospital" }
    ]
  },
  "watch": {
    "count": 1,
    "items": [
      { "screening_id": 39, "miner_name": "Blessing Sithole", "phone": "+263771000003", "mine_site": "Globe & Phoenix Mine", "tier": "YELLOW", "created_at": "2026-07-18 11:48:55" }
    ]
  },
  "outreach_visits": [
    { "id": 2, "site": "Sherwood Mine", "scheduled_date": "2026-07-31", "expected_headcount": 5, "screened_count": 2, "report_generated": true, "tier_distribution": { "GREEN": 1, "YELLOW": 0, "ORANGE": 1, "RED": 0 }, "referral_list": [ { "miner_name": "Kudakwashe Marecha", "tier": "ORANGE", "status": "attended" } ] }
  ]
}
```

`screened_today` / `todays_log` = screenings whose `created_at` falls on the server's current UTC calendar date — Zimbabwe is UTC+2 (CAT), so a screening in the ~2 hours before UTC midnight can land on the "wrong" day. A known simplification, same class as `outreach_visits.report_generated`.

`refer_now` is a **live worklist, not scoped to today** — any referral with `status` in `open`/`pre_alerted`/`reminded`/`escalated`. It drops off once `status` becomes `attended` or `closed` — that's how "have they taken action" gets answered by re-polling this endpoint, using the contact details already in each item. Two ways to make that happen: `PATCH /api/referrals/{id}` (JWT-gated — the dashboard's coordinator flow), or, **new 21 August 2026**, `referral_code`/`facility_name` on each item (same real code as `POST /api/screen`'s response, not a fabricated one) let an unauthenticated caller — the VHW mobile app, which never logs in by design — instead call `POST /api/referrals/lookup/{code}/confirm-attendance` directly. Both routes converge on the same `status`/`attended_at` fields, so either path is equally valid; this one just doesn't need a token.

`watch` = miners whose **most recent** screening (not just any screening) is `YELLOW` — YELLOW never creates a referral, so this is sourced from `screenings`, not `referrals`. A miner whose YELLOW screening was later superseded by a re-screen of any tier drops off this list.

`outreach_visits` (**LIVE 10 August 2026**, same shape as `GET /api/outreach`'s items below) — powers the mobile app's Outreach Stats screen, which previously had no unauthenticated data source to show. Uses the exact same mapping (`services/outreach.visit_to_out`) as the authenticated coordinator route, so the two views can never disagree about a visit's report. `tier_distribution`/`referral_list` are `null` until `report_generated` is `true`.

### `GET /api/dashboard/week` — LIVE (Population Health Intelligence)

Requires `Authorization: Bearer <token>`.

**Response 200**
```json
{
  "total_screened": 142,
  "high_risk_count": 9,
  "referral_completion_rate": 0.67,
  "ai_narrative": "This week 142 miners were screened across three sites, with 9 at elevated risk...",   // illustrative example output, not a figure
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

## v2 — Content store

> **The first `/api/v2` route.** v2 routes land one at a time under `/api/v2/` while the v1 routes above keep serving the current mobile application and dashboard (`docs/IMPLEMENTATION_PLAN.md` §5). A v2 route never changes shape once a client depends on it; a change is a new field or a new route.

### `GET /api/v2/content` — LIVE

Every approved patient-facing string in one language. A client caches this and renders from the cache, so the words a worker reads are the reviewed words whether or not the handset has coverage — **offline is the normal case** (§10.1).

**Query parameters**

| Name | Default | Meaning |
|---|---|---|
| `language` | `en` | `en`, `sn` or `nd`. Anything else is `400`, not a fallback — a silent fallback would be indistinguishable from a translation having happened. |
| `channel` | all | `sms`, `ussd`, `app` or `clinician`. The gateway and the handset need different subsets and neither needs the other's. |
| `since` | — | ISO-8601 timestamp. Returns only messages created after it. Approved versions are immutable and a change is a new row, so this is a sound watermark for an incremental refresh. |

**Response**

```json
{
  "language": "sn",
  "count": 2,
  "generated_at": "2026-11-01T14:52:11+00:00",
  "messages": [
    {
      "code": "result.green.sms",
      "version": 1,
      "channel": "sms",
      "language": "sn",
      "text": "…",
      "placeholders": ["name"]
    }
  ]
}
```

- `language` at the top echoes the request. **`language` on a row is the language actually served**, which may be `en` where that message has not been authored in the requested language yet. The gap is reported rather than filled: there is no machine translation anywhere in this system (§8.4), so a client can see that an authoring gap exists.
- `placeholders` is the substitution contract. The client substitutes offline and must supply exactly this set; a message rendered with a placeholder left unresolved reaches a worker as literal braces.
- `count: 0` with an empty `messages` is the **correct** response until the Clinical Lead approves content version one, not an error. Only `approved` messages are ever served, so draft and review text cannot reach a handset.

**Auth: none.** Same deliberate precedent as the screening path — the mobile application never logs in, and this response contains nothing about any person.

**There is no write route, and will not be one.** `POST`, `PUT`, `PATCH` and `DELETE` all return `405`. Content enters through a migration generated from `content/`, on a pull request the Clinical Lead approves (§11.4); an HTTP endpoint that could add a patient-facing string would be a way around that approval.

**Not served here:** the strings in `content/EXCEPTIONS.md`, which by definition cannot come from the store. There are three, each reviewed.

### Identity — `/api/v2/persons` — LIVE

Master Reference §8.2. The telephone number is **not** an identity key anywhere in this group of routes.

**`POST /api/v2/persons/resolve`** — no auth

Resolve what is known about a worker to a person. Always returns a person a screening can be written against: an uncertain match produces a new person plus a queue entry, never a blocked screening.

```json
{
  "participant_code": "8NBNFM",   // the card in his pocket, if he has it
  "national_id": "63-123456-A-00", // voluntary; stored as a keyed hash only
  "name": "Tendai Moyo",
  "phone": "0771234567",
  "age_band": "30-39",
  "sex": "male",
  "site_id": 3,
  "site_text": "Globe & Phoenix",
  "language": "sn",
  "channel": "APP"                 // APP or USSD; changes the anonymous case
}
```

At least one of `participant_code`, `national_id`, `name` or `phone` is required — a bundle of demographics identifies nobody and is a `400`.

```json
{
  "person_id": 41,
  "participant_code": "8NBNFM",
  "outcome": "created_pending_review",
  "provisional": false,
  "provisional_reason": null,
  "candidates": [
    {"person_id": 12, "participant_code": "K4R2TP", "score": 0.8,
     "reasons": ["name similar (0.96)", "shares a contact number", "same age band", "same sex"]}
  ],
  "queued_match_ids": [7]
}
```

`outcome` is one of:

| Value | Meaning |
|---|---|
| `matched_participant_code` | He presented his card. **Applied.** |
| `matched_national_id` | Deterministic match on the hashed identity number. **Applied.** |
| `created` | Nothing looked like him; a clean new record. |
| `created_pending_review` | A new record, with probable matches **queued for a human and not applied**. |
| `created_provisional` | §8.2 part four: a USSD caller with no usable participant code. |

**The response carries no name and no number.** The route is unauthenticated, on the same precedent as the screening path, so a candidate is identified by participant code and the reviewer opens each side with a token.

`503` means the server's identity keys are not configured. Nothing was saved; it is retryable, and the mobile offline queue should treat it that way rather than discarding the screening.

**`GET /api/v2/persons/{participant_code}`** — Bearer

The person behind a card, following any merge — so a card printed before a merge still works. Returns `name` and `phone` decrypted, plus `age_band`, `sex`, `language`, `provisional`, `provisional_reason`, `has_national_id` (whether one was given, never the number), `session_count` and `merged_into_person_id`.

Bearer-protected deliberately: public, this would let anyone walk a six-character code space and harvest names and telephone numbers. **The consequence is a real gap** — the VHW application has no login, so it cannot yet show "is this the right person?" at the next outreach. It needs a device credential (item 1.13), and that flow waits for it.

**`GET /api/v2/persons/matches/queue?limit=50`** — Bearer

Probable matches awaiting a human decision — §8.2's "never merged automatically", as a worklist. Each row carries both participant codes, the `score`, the `reasons`, the `status` and `created_at`. No name and no number: a reviewer opens each side by code.

**`POST /api/v2/persons/matches/{match_id}`** — Bearer

```json
{"decision": "merge", "decided_by": "sister.moyo"}
```

`merge` applies it with the queued evidence attached, so the reason the reviewer was shown the pair becomes the reason recorded against the merge. `reject` is **recorded, not discarded**: "reviewed, and they are different people" has to survive, or the same pair is queued again at the next screening. A decided row cannot be decided twice.

**`POST /api/v2/persons/merges`** — Bearer

```json
{"winner_person_id": 12, "loser_person_id": 41, "merged_by": "sister.moyo", "reason": "presented the same card"}
```

Contacts and sessions move to the winner; the winner inherits only what it was missing and **overwrites nothing**. The losing record is kept and flagged, never deleted. Merging a person into themselves, or chaining a merge onto an already-merged record, is a `400`.

**`DELETE /api/v2/persons/merges/{merge_id}?reversed_by=supervisor`** — Bearer

Reverses a merge, keeping both the merge and the reversal in the audit. **Contacts and sessions are not moved back** — which rows belonged to which record before the merge is not recoverable from the surviving data, so the reversal restores the two identities and a health worker reassigns the encounters.

**Today any dashboard login can merge two people.** There are two flat accounts; a merge is a clinical safety event and belongs to one named role. Item 1.13 scopes it.

### Consent — `/api/v2/consents` — LIVE

Master Reference §8.5, §14.2. **Absence is never consent**: every response names all six permissions, and one nobody recorded reads `false`. A client never has to decide what a missing key means.

**`GET /api/v2/consents/permissions`** — no auth

The six permissions and what each covers, so a consent screen renders from the server's definition rather than a copy in the client. A copy drifts, and a consent screen that drifts asks for agreement to something other than what is recorded.

```json
[{"code": "screening_and_referral", "scope": "Screening, tier assignment, referral…",
  "required_to_screen": true, "future_phase": false}]
```

| Permission | Notes |
|---|---|
| `screening_and_referral` | Required to proceed. Without it there is no service. |
| `longitudinal_record` | Separable — a worker may accept screening and decline retention. |
| `contact_by_message` | Required for referral follow-through. Distinct from education broadcast. |
| `education_broadcast` | Separate, with a working and permanent opt-out. |
| `research_and_statistics` | Refusable without losing the service. |
| `employer_disclosure` | **Future phase. Cannot be granted** — a grant is rejected `400`. A refusal may be recorded. |

**`GET /api/v2/consents/texts/{code}`** — no auth

The approved consent text version to show. Returns `consent_text_id`, `code`, `version`, `message_code`, `status`, `approved_by`, `approved_at` — **not the wording**. The words are a message code in the content store, so consent text goes through the same review, three languages and GSM-7 checks as every other patient-facing string (§8.4).

`404` until the Clinical Lead approves one, which is why consent capture does not work before then. That is correct sequencing, not a gap: nobody is asked to agree to unreviewed wording.

**`POST /api/v2/consents`** — no auth

```json
{
  "person_id": 41,
  "consent_text_id": 3,
  "channel": "APP",
  "recorded_by": "sister.moyo",
  "decisions": {
    "screening_and_referral": true,
    "longitudinal_record": false,
    "contact_by_message": true,
    "education_broadcast": false,
    "research_and_statistics": false
  }
}
```

`consent_text_id` is **required** and must name an *approved* text — §14.2 records the version displayed, and a row saying "agreed" with nothing attached is not evidence. `channel` is `APP`, `USSD` or `PAPER`.

**All-or-nothing.** A half-recorded consent screen is worse than a failed one, because afterwards the missing permissions are indistinguishable from refusals. A `400` leaves nothing written.

A **refusal is recorded as deliberately as a grant**: "asked and declined" is the answer an ethics committee wants, and it stops the same question being asked at every visit.

Response (also returned by withdraw and by the per-person read):

```json
{
  "person_id": 41,
  "participant_code": "8NBNFM",
  "standing": {"screening_and_referral": true, "longitudinal_record": false, "...": false},
  "may_screen": true,
  "may_keep_longitudinal_record": false,
  "history": [
    {"record_id": 7, "permission": "screening_and_referral", "granted": true,
     "consent_text_code": "CORE", "consent_text_version": 1, "channel": "APP",
     "recorded_at": "2026-11-01T14:52:11", "recorded_by": "sister.moyo", "withdrawn_at": null}
  ]
}
```

`may_keep_longitudinal_record: false` is the one place the layering changes what a caller does: the session is recorded with **no `previous_session_id`** and no deterioration comparison. The screening still happens and the result is still real; it simply has no history attached.

Unauthenticated on the same precedent as the screening path — a consent screen is part of a screening, and the VHW application never logs in. Requiring a token for consent while screening itself is open would be incoherent.

**`POST /api/v2/consents/withdraw`** — Bearer

```json
{"person_id": 41, "permission": "education_broadcast", "withdrawn_by": "supervisor"}
```

The original row is **kept and stamped**, never deleted: §14.3 requires the withdrawal mechanism to be demonstrable, and "granted, then withdrawn on this date" is a different story from "never granted". Withdrawing something never granted succeeds quietly — a worker opting out of what he never opted into should not get a failure.

**Bearer-protected, and that is a named gap.** A worker's own withdrawal should not need a token, but an open endpoint keyed on a person id would let anyone stop anyone's referral reminders — a harm to the person it pretends to serve. The worker-facing route is the USSD and SMS opt-out, which reaches the same service function server-side through the gateway, and it lands with item 1.9. Until then withdrawal is staff-operated and §14.2's "working and permanent opt out" is unfinished.

**`GET /api/v2/persons/{participant_code}/consents`** — Bearer

Everything recorded for one person, by the code on their card. Follows a merge, so a decision recorded against a record that later lost a merge is still found — a worker's decision must not be lost because a clerk joined two records.

### Screening — `POST /api/v2/screenings` — LIVE

Master Reference §10.3. **The deterministic cascade is the tier of record. No model sits between a set of answers and a tier on this route, by construction and by test.**

**No auth** — the village health worker's application never logs in, and a screening must work in a gold-panning area with no dashboard session. Same precedent as `POST /api/screen`.

```json
{
  "person_id": 41,
  "client_session_uuid": "8f3c1e2a-...",
  "answers": {"T1": "some", "T2": "mid", "T3": "no_"},
  "channel": "APP",
  "screened_by": "sister.moyo",
  "site_id": 3,
  "site_text": "Globe & Phoenix",
  "programme_id": null,
  "outreach_visit_id": 7,
  "instrument_code": "SILICA-ASM",
  "started_at": "2026-11-01T08:00:00Z",
  "offline": false
}
```

`client_session_uuid` is **required** (minimum 8 characters). It is generated on the device when the session starts and replayed on retry, and it is the only thing that makes a duplicate submission safe. A channel that cannot produce one will create duplicates — which the v1 path did, eighteen times for one miner during a model-flakiness window.

`answers` maps question code to the recorded value. **An explicit unknown or refused option belongs here too**: the engine derives `unknown` from the instrument rather than from absence (§12.2 item 10), because an unanswered red-flag question must never read as a negative.

`instrument_code` may be omitted only when the database holds exactly one instrument. An instrument is chosen deliberately, never guessed.

**Response**

```json
{
  "session_id": 112,
  "person_id": 41,
  "participant_code": "8NBNFM",
  "primary_tier": "ORANGE",
  "results": [
    {"condition": "silicosis", "tier": "ORANGE", "score": 14,
     "method": "deterministic_rules",
     "instrument_code": "SILICA-ASM", "instrument_version": 1,
     "scored_tier": "YELLOW", "tier_rule_label": "…",
     "override_fired": false, "override_rule_codes": [],
     "deterioration_compared": true, "deterioration_changed": true,
     "deterioration_summary": "Worsened since the previous screening on: …"}
  ],
  "instrument_code": "SILICA-ASM",
  "instrument_version": 1,
  "replayed": false,
  "longitudinal_linked": true,
  "referrals": [
    {"referral_code": "SG-4K7Q", "condition": "silicosis", "tier": "ORANGE",
     "facility": "Kwekwe District Hospital", "deadline": "2026-11-15T14:52:11"}
  ],
  "messages": [{"code": "result.orange.sms", "available": false,
                "reason": "not in the content store yet"}],
  "not_sent_reason": "no message was sent: the v2 pipeline does not send yet …",
  "started_at": "2026-11-01T08:00:00",
  "completed_at": "2026-11-01T08:04:33"
}
```

**`results` is a list, not a tier.** This is the single most important shape change in the v2 API: a session produces one result per condition assessed, which is what makes adding tuberculosis rows rather than a migration of patient records. `primary_tier` is the highest across conditions — a worker at RED for one condition is at RED, whatever the others say.

`scored_tier` is the tier *before* deterioration escalation and overrides, so the cascade is auditable step by step rather than only at its end.

`longitudinal_linked: false` means the worker declined retention (§14.2), so no previous session was linked and no deterioration comparison was possible. **The screening still happened and the result is still real** — it simply has no history attached.

`replayed: true` means this submission matched an existing `client_session_uuid`. **Nothing was written.** The response is the stored result of the first session, read from the rows rather than re-classified — because the instrument may have been superseded between the submission and the retry, and a worker must be told what he was told.

`messages` says what *would* be sent and whether the reviewed words exist. **There is no fallback sentence**: §8.4 means a worker reads reviewed words or nothing, and a placeholder shipped "for now" is how unreviewed text reaches people. `not_sent_reason` is non-null until item 1.6b (the words) and the `drop_v1` migration (which rebuilds `notifications` so a row can name a person rather than a v1 miner).

**Status codes, and what a mobile offline queue should do with each**

| Code | Meaning | Retry? |
|---|---|---|
| `200` | Screened, or replayed. | Done. |
| `400` | Request wrong, or **screening incomplete**. The body carries `{"message", "session_id", "missing", "answers_saved": true}`. | No — the answers are saved; complete *that* session rather than resubmitting. |
| `403` | Consent for screening has not been recorded. | No — go back to the worker. |
| `422` | Schema violation (missing key, empty answers). | No. |
| `503` | Server misconfigured: identity keys absent. **Nothing was saved.** | Yes. |

`400` on an incomplete screening is the one a queue must not misread. §13.1: a partially answered instrument must never produce a tier — and rule 7: the answers given are kept regardless.

### `GET /api/v2/referrals/{referral_code}` — LIVE, no auth

What a facility sees when staff key in the code. Unauthenticated for the same reason the v1 lookup page is — facility staff have no account — and with the same recorded weakness: no rate limiting and no lockout on a code-keyed public endpoint (§15.4, item 1.13).

Returns `referral_code`, `condition_code`, `person_id`, `result_id`, `facility`, `deadline`, `status`, `attended_at`, the outcome fields, and **`contributing_reasons`** — the tier, the scored tier, the condition, whether an override fired and which rules, and the instrument version. A facility reading this knows what to look for rather than receiving a bare instruction to investigate.

### `POST /api/v2/referrals/{referral_code}/close` — LIVE, no auth

```json
{"outcome": "attended_imaging_abnormal", "recorded_by": "nurse", "notes": "Upper zones."}
```

§10.4: **closing a referral captures the radiological or clinical outcome and returns it to the person's record, not merely that they attended.** Without it the pilot produces an operational result and no labelled dataset. With it, every completed referral is a training example nobody else in the country holds — which is why the vocabulary is closed and not free text. Free text is easier for the person filling it in and produces nothing a model can learn from.

`GET /api/v2/referrals/outcomes/vocabulary` serves the five values, so the facility page renders from the server's definition rather than a copy that can drift out of step with what the database accepts:

`attended_imaging_normal` · `attended_imaging_abnormal` · `attended_no_imaging` · `not_attended` · `other`

An outcome beginning `attended` sets `attended_at` if the confirm step was skipped — the two were independently recordable in v1 and could disagree.




### Roles, users and the audit trail — LIVE

Master Reference §16.3, §16.6.

**`GET /api/v2/roles`** — no auth

Every role, its capabilities, its scope field, and §16.3's own **"cannot see"** column. Unauthenticated because it describes the model rather than any data: a reviewer or an ethics committee reading what a role is refused should not need an account.

```json
[{"code": "national_stakeholder", "label": "National stakeholder",
  "capabilities": ["aggregate.read"], "scope_field": null,
  "cannot": "Any identified record.", "prototype": false}]
```

Seven roles have logins. §16.3's table has eight rows; the eighth is **the person screened**, who has no account — a worker reaches their own record through USSD and the card in their pocket, so their access is bounded by the participant code rather than by a role. `prototype: true` marks `hospital` and `cimas`, which exist only for the transition and are refused to any new user.

**`POST /api/v2/users`** — Bearer, `admin.manage`

```json
{"email": "nurse@example.org", "password": "…", "role": "facility_user", "facility_id": 3}
```

A **scoped role with no scope is a `400`**: it passes every capability check and is bounded by nothing, which is worse than no account at all. `site_ids` (a list) for a village health worker, `facility_id` for a facility user, `district` for a coordinator, `programme_id` for a sponsor.

**`GET /api/v2/users`** — Bearer, `admin.manage`.
**`DELETE /api/v2/users/{id}`** — Bearer, `admin.manage`. **Deactivates, never deletes**: an audit row names a user id, and a deleted user would let somebody erase their own trail by removing their account. An administrator cannot deactivate themselves — with one administrator that would lock the system out of user management.

**`GET /api/v2/audit/persons/{person_id}`** — Bearer, `person.read`

Every access to one person's record. "Who has read my record?" is a question a worker is entitled to an answer to, and §16.3's audit exists so the answer is not "we cannot tell". **Reading the trail is itself audited** — an audit log nobody's reads are recorded in is a log that can be mined quietly.

**Not available to an administrator**, deliberately: §16.3's "administrative access is not a licence to read records". An administrator who needs a record has to be given a clinical role as well, which is a decision somebody makes rather than a capability that arrives with the job.

**`GET /api/v2/audit/refusals`** — Bearer, `admin.manage`

Every refused access, newest first. **These are the rows that matter**: a role boundary nobody can show being enforced is a boundary nobody can show exists.

```json
[{"entry_id": 91, "actor_email": "r@example.org", "actor_role": "researcher",
  "action": "admin.user_create", "object_type": "capability",
  "object_id": "admin.manage", "person_id": null,
  "at": "2026-11-01T18:42:02", "request_id": "a1b2c3d4e5f60718",
  "allowed": false, "details": {"role": "researcher", "capability": "admin.manage"}}]
```

`details` carries codes, counts and ids and **never a name, a number, an answer or a password** — checked by a forbidden-key list rather than trusted, because the log must not become a second copy of the register. A failed-login row records neither the address tried nor the password.

### Changes to existing auth routes

**`GET /api/auth/me` gained fields** (additive; `email` and `role` unchanged): `scope`, `capabilities`, `cannot` and `prototype_account`. A client renders the boundary from the server's definition rather than from a copy.

**`POST /api/auth/login` now authenticates against the `users` table** with `scrypt`-hashed passwords. The two environment-variable accounts still work, but **only while the `users` table is empty** — the moment a real user exists they stop, and a token issued to one stops with them. That is not a feature flag: a flag nobody turns off is how a prototype credential reaches production.

Both successful and failed logins are audited. §15.4 already records that this surface has no rate limiting or lockout; credential stuffing against it is at least visible now.

**`SECRET_KEY` has no fallback.** It previously defaulted to `"dev-secret"` — a value published in this repository, which meant anyone could mint an administrator token against a misconfigured instance. A missing key is now a `503` at signing time.

**The first administrator is created by `backend/scripts/create_admin.py`**, which needs database access. The prototype accounts do not hold `admin.manage`, so they cannot create one, and both alternatives were worse: widening them defeats the point of retiring them, and an unauthenticated user-creation route while the table is empty opens a window in which whoever reaches a fresh instance first owns the system.

Clients pass `X-Request-Id` to correlate the audit rows one request writes, which is what makes a mobile synchronisation traceable from the handset's own log.


### The active instrument — `GET /api/v2/instrument/active` — LIVE, no auth

Master Reference §10.1. What the mobile application fetches before an outreach visit so the handset can run the same cascade with no connectivity — **offline is the normal case** — and what unblocks the JavaScript port of `services/predicates.py` (item 1.14a).

| Parameter | Default | Meaning |
|---|---|---|
| `channel` | `app` | `app` or `ussd`. **Annotates, does not filter** — see below. |
| `code` | — | Required only when the database holds more than one instrument. An instrument is chosen deliberately, never guessed. |

```json
{
  "code": "SILICA-ASM",
  "version": 1,
  "status": "approved",
  "approved_by": "…",
  "approved_at": "2026-11-01",
  "ruleset_version": "SILICA-ASM-v1",
  "channel": "ussd",
  "channel_questions": ["Q1", "Q2", "Q5"],
  "instrument": { "…the whole document…" }
}
```

**`instrument` is the complete document, including questions this channel does not ask.** That is a safety decision, not an oversight. Removing them would be the obvious optimisation and would silently change what the rules do: a question absent from the document can never be `unknown`, so a safety rule of the form `{"unknown": "Q"}` — the §12.2 item 10 protection that stops an unanswered red flag reading as a negative — would stop firing. A transport optimisation that disarms a red-flag rule is the worst kind of bug, because nothing fails and the tier is simply wrong.

So `channel_questions` names what to *render* while the rules are evaluated over the whole document, exactly as `services/rules_engine.py` does. The two interpreters are given identical input, which is the only way "channels are equivalent" can be guaranteed rather than asserted.

**Branching is not resolved here.** A question whose `branching` predicate depends on an answer cannot be known before the answers exist; the device evaluates it as it goes.

`instrument` is in the shape the rules engine consumes, so the device's interpreter is a *port* rather than a reimplementation.

`404` when nothing is approved — the state until instrument version one lands, and correct rather than a fault. A device must never be handed a draft to screen against.

**`GET /api/v2/instrument/versions`** — no auth. Every stored version with its status and approver, and **no clinical content**. Exists so "which instrument is this server serving?" is answerable without database access — the question §10.1 says every clinical output must be traceable to.

### A worker's history — `GET /api/v2/persons/{participant_code}/sessions` — Bearer, `screening.read`

Encounters newest first, each with its **per-condition results** — a list, not a tier. Follows a merge, so a card printed before one still finds the history the merge joined, which is the reason to perform a merge at all.

```json
{
  "person_id": 41,
  "participant_code": "8NBNFM",
  "longitudinal_consent": true,
  "session_count": 3,
  "sessions": [
    {"session_id": 112, "channel": "APP", "site": "Globe & Phoenix",
     "instrument_code": "SILICA-ASM", "instrument_version": 1,
     "started_at": "…", "completed_at": "…", "previous_session_id": 108,
     "primary_tier": "ORANGE",
     "results": [{"condition": "silicosis", "tier": "ORANGE", "…": "…"}],
     "referral_codes": ["SG-4K7Q"]}
  ]
}
```

`longitudinal_consent: false` is why a history may be shorter than the number of encounters: without it the sessions are never linked, and a trend drawn across them would be an inference the worker refused (§14.2).

**Refused to `national_stakeholder`, `researcher`, `programme_sponsor` and `administrator`** — §16.3's "cannot see" column, including "administrative access is not a licence to read records". Every read writes an audit row.

### The day — `GET /api/v2/dashboard/{today|week|month}` — Bearer, `aggregate.read`

**Counts per condition *and* tier, not per tier alone.** The v1 dashboard counts tiers, which works only while there is one condition: `high_risk_count` becomes ambiguous the day tuberculosis is added — high risk of *what*?

```json
{
  "period": "today", "from_date": "…", "to_date": "…",
  "sessions": 14, "people": 12, "incomplete_sessions": 1,
  "by_condition_and_tier": [
    {"condition": "silicosis", "tier": "GREEN", "count": 8},
    {"condition": "silicosis", "tier": "ORANGE", "count": 3}
  ],
  "referrals_open": 3, "referrals_attended": 1,
  "referrals_closed_with_outcome": 1, "worsened": 2
}
```

**`incomplete_sessions` is counted rather than hidden.** A session that produced no result because an applicable question was unanswered (§13.1) is absent from every tier count, so without a separate number a channel that keeps producing them looks like a channel nobody is using.

Returns **no identified record** — only counts — which is why it sits behind `aggregate.read`, the capability a district coordinator, a national stakeholder and a programme sponsor all hold while none of them may read a person.

**This needs a token, and v1's `GET /api/dashboard/today` does not.** That is a deliberate difference: the v2 response names conditions, and an open endpoint returning per-condition clinical counts is a disclosure once a second condition exists. The mobile Home screen therefore needs a device credential — item 1.13, the same gap `routers/persons.py` records for the identity lookup.


---

## Summary table

| Route | Method | Status |
|---|---|---|
| `/api/health` | GET | LIVE |
| `/api/auth/login` | POST | LIVE (hashed passwords, `users` table; prototype accounts self-disarm) |
| `/api/auth/me` | GET | LIVE (gained scope, capabilities, cannot, prototype_account) |
| `/api/workers` | POST | LIVE |
| `/api/workers/{phone}` | GET | LIVE |
| `/api/mines` | GET, POST | LIVE |
| `/api/miners` | GET | LIVE (dashboard Miners directory) |
| `/api/screenings` | GET | LIVE (dashboard All Screenings log) |
| `/api/screen` | POST | LIVE (four-tier, hard safety overrides, deterioration detection, advice line + Shona explanation, result SMS for all four tiers) |
| `/api/ussd` | POST | LIVE (four-tier) |
| `/api/referrals` | GET | LIVE (facility matching + reminder/escalation cascade) |
| `/api/referrals/{id}` | PATCH | LIVE (new status lifecycle) |
| `/api/referrals/lookup/{code}` | GET | LIVE (unauthenticated, referral-code pivot) |
| `/api/referrals/lookup/{code}/confirm-attendance` | POST | LIVE (unauthenticated) |
| `/api/outreach` | POST, GET | LIVE |
| `/api/dashboard/today` | GET | LIVE (unauthenticated, VHW Home-screen numbers) |
| `/api/dashboard/week` | GET | LIVE (real Population Health Intelligence narrative) |
| `/api/v2/content` | GET | LIVE (first v2 route — approved patient-facing strings, read-only) |
| `/api/v2/persons/resolve` | POST | LIVE (unauthenticated; probable matches queued, never applied) |
| `/api/v2/persons/{participant_code}` | GET | LIVE (Bearer — decrypts a name and a number) |
| `/api/v2/persons/matches/queue` | GET | LIVE (Bearer — the human review worklist) |
| `/api/v2/persons/matches/{match_id}` | POST | LIVE (Bearer — merge or reject one pair) |
| `/api/v2/persons/merges` | POST | LIVE (Bearer — apply a merge, reversibly) |
| `/api/v2/persons/merges/{merge_id}` | DELETE | LIVE (Bearer — reverse one) |
| `/api/v2/consents/permissions` | GET | LIVE (the six permissions, for rendering a consent screen) |
| `/api/v2/consents/texts/{code}` | GET | LIVE (the approved consent text version; 404 until one exists) |
| `/api/v2/consents` | POST | LIVE (unauthenticated; all-or-nothing, names the text version shown) |
| `/api/v2/consents/withdraw` | POST | LIVE (Bearer — the worker-facing opt-out is 1.9) |
| `/api/v2/persons/{participant_code}/consents` | GET | LIVE (Bearer — standing position plus full history) |
| `/api/v2/screenings` | POST | LIVE (the §10.3 pipeline; one result per condition; idempotent) |
| `/api/v2/referrals/{referral_code}` | GET | LIVE (facility-facing, with contributing reasons) |
| `/api/v2/referrals/{referral_code}/close` | POST | LIVE (structured outcome — the labelled dataset) |
| `/api/v2/referrals/outcomes/vocabulary` | GET | LIVE (the five permitted outcomes) |
| `/api/v2/roles` | GET | LIVE (the roles and §16.3's "cannot see" column) |
| `/api/v2/users` | POST, GET | LIVE (Bearer, `admin.manage`) |
| `/api/v2/users/{id}` | DELETE | LIVE (Bearer — deactivates, never deletes) |
| `/api/v2/audit/persons/{id}` | GET | LIVE (Bearer, `person.read` — not an administrator) |
| `/api/v2/audit/refusals` | GET | LIVE (Bearer, `admin.manage`) |
| `/api/v2/instrument/active` | GET | LIVE (the whole instrument, for a device to interpret offline) |
| `/api/v2/instrument/versions` | GET | LIVE (provenance only, no clinical content) |
| `/api/v2/persons/{participant_code}/sessions` | GET | LIVE (Bearer, `screening.read` — per-condition results) |
| `/api/v2/dashboard/{today\|week\|month}` | GET | LIVE (Bearer, `aggregate.read` — counts per condition and tier) |
