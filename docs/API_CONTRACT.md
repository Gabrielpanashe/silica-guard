# SilicaGuard API Contract

This is the source of truth for the backend's HTTP interface. Build the mobile app and dashboard against this document, not against reading the Python.

Every route is marked:
- **LIVE** — implemented today, in the shape described.
- **LIVE (shape will change)** — implemented today, but in an older pre-v4.0 shape; the target v4.0 shape is also shown.
- **TARGET (not yet built)** — specified by the v4.0 reference document, not implemented yet. Shape shown is the plan, not a guarantee — it may shift slightly during implementation. Check back or ask before building a hard dependency on field names here.

Base URL: local dev is `http://127.0.0.1:8000`. Deployed URL will be added here once Render deployment happens (Day 7 per the sprint plan).

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

### `POST /api/workers` — LIVE (shape will change; currently `POST /api/miners`)

**Currently live as `POST /api/miners`:**

**Request**
```json
{ "name": "Tendai Moyo", "phone": "+263771234567", "mine_site": "Sherwood Mine" }
```

**Response 200**
```json
{ "id": 14, "name": "Tendai Moyo", "phone": "+263771234567", "mine_site": "Sherwood Mine" }
```

**Errors**: `409` if `phone` is already registered (phone is the persistent worker identity).

**Target v4.0 shape** — route renamed `/api/workers`, adds job role, matching the `workers` register table (`site`, `job_role`):
```json
{
  "name": "Tendai Moyo",
  "phone": "+263771234567",
  "site": "Sherwood Mine",
  "job_role": "drilling"
}
```

### `GET /api/workers/{phone}` — TARGET (not yet built)

Look up a worker by phone number, returning their full screening history — this is what turns a visit into a re-screen. Not yet implemented; today there is no lookup-by-phone endpoint at all.

**Target response 200**
```json
{
  "id": 14,
  "name": "Tendai Moyo",
  "phone": "+263771234567",
  "site": "Sherwood Mine",
  "job_role": "drilling",
  "screenings": [
    { "id": 101, "tier": "YELLOW", "created_at": "2026-08-02T09:15:00Z", "advice_line": "..." },
    { "id": 88, "tier": "GREEN", "created_at": "2025-11-10T08:00:00Z", "advice_line": "..." }
  ]
}
```

**Target errors**: `404` if no worker with that phone exists.

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
  "offline_fallback_used": false
}
```

**Response 200**
```json
{
  "tier": "YELLOW",
  "confidence": 0.82,
  "explanation_english": "Significant drilling exposure with no symptoms yet...",
  "contributing_factors": ["10+ years underground", "inconsistent PPE use"],
  "advice_line": null,
  "previous_screening_id": 88,
  "provisional": false
}
```

**Errors**: `404` unknown `miner_id`; `422` empty `answers`; `502` AI risk engine unavailable (screening + answers are still persisted for retry/audit — only the tier fields stay null).

`tier` is one of `GREEN`, `YELLOW`, `ORANGE`, `RED` (Phase A schema migration, previously 3-tier `LOW`/`WATCH`/`REFER_NOW`). `previous_screening_id` links to this worker's most recent prior screening if one exists — it's just the link; comparing the two (Longitudinal Deterioration Detection) isn't built yet. `provisional` mirrors `offline_fallback_used` from the request. `advice_line` is always `null` for now — personalised advice generation (drawn from the miner's weakest answer) is not built yet; the column and field exist so the shape is stable when it lands.

**Still TARGET, not in this response yet**: `explanation_shona`, a populated `advice_line`, and a `deterioration` object comparing this screening against `previous_screening_id`:
```json
{
  "deterioration": {
    "compared_to_screening_id": 88,
    "changed": true,
    "summary": "Breathlessness moved from Grade 0 to Grade 1 since your last screening."
  }
}
```

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

### `GET /api/referrals` — LIVE (four-tier, new status lifecycle)

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
    "attended_at": null,
    "closed_at": null,
    "created_at": "2026-08-02 09:15:00"
  }
]
```

**Errors**: `401` missing/invalid token.

`deadline` is set on creation from the fixed urgency windows in `SILICAGUARD.md` Section 7 Pillar 2 (RED = created_at + 48h, ORANGE = created_at + 14 days) — this is Phase A schema migration, not the full Smart Referral Router. **Still TARGET, not built yet**: facility matching (every referral still goes to a single hardcoded `Kwekwe District Hospital` string, no `facility_id`/`facility_name` field), the day-3/day-7 reminder cascade (`status: "reminded"` exists in the schema but nothing sets it), and day-14 escalation (`status: "escalated"` likewise unreached by any code path yet).

### `PATCH /api/referrals/{referral_id}` — LIVE (new status lifecycle)

Requires `Authorization: Bearer <token>`.

**Request**
```json
{ "status": "closed" }
```
Valid statuses: `open`, `pre_alerted`, `reminded`, `attended`, `closed`, `escalated` (Phase A schema migration, replacing the old `PENDING`/`XRAY_UPLOADED`/`COMPLETE`; `XRAY_UPLOADED` is gone — it was a leftover from the removed chest X-ray feature). Setting `status` to `attended` stamps `attended_at`; setting it to `closed` stamps `closed_at`. A referral moves to `pre_alerted` automatically when the hospital pre-alert SMS succeeds — `reminded` and `escalated` aren't reachable yet since the reminder/escalation scheduler isn't built.

**Response 200**
```json
{ "id": 7, "miner_name": "Tendai Moyo", "mine_site": "Sherwood Mine", "tier": "RED", "status": "closed", "deadline": "2026-08-04 09:15:00", "pre_alert_sent": true, "attended_at": null, "closed_at": "2026-08-02 10:00:00", "created_at": "2026-08-02 09:15:00" }
```

**Errors**: `401` missing/invalid token; `404` unknown referral; `422` invalid status value.

---

## Outreach

The underlying `outreach_visits` and `facilities` tables exist in the database as of the Phase A schema migration, but no route reads or writes them yet — the routes below are still TARGET.

### `POST /api/outreach` — TARGET (not yet built)

Schedule a visit and trigger the 3-day / 1-day-before bulk SMS announcement to every registered worker at that site.

**Target request**
```json
{ "site": "Sherwood Mine", "scheduled_date": "2026-08-15", "expected_headcount": 40, "health_workers": ["Grace Chikwanha"] }
```

**Target response 201**
```json
{ "id": 3, "site": "Sherwood Mine", "scheduled_date": "2026-08-15", "expected_headcount": 40, "screened_count": 0, "report_generated": false }
```

### `GET /api/outreach` — TARGET (not yet built)

List scheduled/past outreach visits, including the auto-generated post-visit report (attendance, tier distribution, referral list) once a visit's data has synced.

**Target response 200**
```json
[
  { "id": 3, "site": "Sherwood Mine", "scheduled_date": "2026-08-15", "expected_headcount": 40, "screened_count": 38, "report_generated": true }
]
```

---

## Dashboard

### `GET /api/dashboard/week` — LIVE (narrative is a placeholder)

Requires `Authorization: Bearer <token>`.

**Response 200**
```json
{
  "total_screened": 142,
  "high_risk_count": 9,
  "referral_completion_rate": 0.67,
  "ai_narrative": "Weekly AI narrative not yet implemented.",
  "site_breakdown": [
    { "mine_site": "Sherwood Mine", "count": 62 },
    { "mine_site": "Unknown", "count": 5 }
  ]
}
```

**Errors**: `401` missing/invalid token.

`high_risk_count` counts screenings with `tier IN ('ORANGE', 'RED')`. `ai_narrative` is currently a hardcoded placeholder string. **Population Health Intelligence (the weekly job that should generate this) is not built yet.** Target: a real plain-language narrative describing what changed and where outreach should go next, produced by a scheduled job — this is one of the four AI modules.

---

## Summary table

| Route | Method | Status |
|---|---|---|
| `/api/health` | GET | LIVE |
| `/api/auth/login` | POST | LIVE (roles will change) |
| `/api/auth/me` | GET | LIVE (dev helper) |
| `/api/miners` → `/api/workers` | POST | LIVE (rename + reshape pending) |
| `/api/workers/{phone}` | GET | TARGET |
| `/api/screen` | POST | LIVE (four-tier) |
| `/api/ussd` | POST | LIVE (four-tier) |
| `/api/referrals` | GET | LIVE (new status lifecycle; facility matching pending) |
| `/api/referrals/{id}` | PATCH | LIVE (new status lifecycle) |
| `/api/outreach` | POST, GET | TARGET |
| `/api/dashboard/week` | GET | LIVE (narrative is a placeholder) |
