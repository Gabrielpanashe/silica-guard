# SKILL.md

Where `CLAUDE.md` says what the project is, this file says how we do things here. Practical, repeatable procedures.

## How to run the project locally

### Backend

```
cd backend
python -m venv venv                 # first time only
./venv/Scripts/activate              # Windows
pip install -r requirements.txt
copy .env.example .env               # then fill in real values
uvicorn main:app --reload
```

The API is now at `http://127.0.0.1:8000`. Swagger UI (auto-generated OpenAPI docs) is at `http://127.0.0.1:8000/docs` — nothing disables it, it's on by default. Use it to explore the live API without needing to ask the backend owner.

To test USSD locally without an Africa's Talking sandbox number:

```
cd backend
./venv/Scripts/python.exe scripts/ussd_simulator.py
```

To run the test suite:

```
cd backend
pip install -r requirements-dev.txt
pytest
```

### Mobile (React Native / Expo)

Not yet scaffolded in this repo. Once the collaborator initialises it: `cd mobile && npm install && npx expo start`. Points at the backend's `DATABASE_URL`-independent API base URL — check `docs/API_CONTRACT.md` for the current base URL to use.

### Dashboard (React + Vite)

Not yet scaffolded in this repo. Once the collaborator initialises it: `cd dashboard && npm install && npm run dev`.

## How to add a new API endpoint

Follow the existing pattern in `backend/routers/` and `backend/services/`:

1. **Route file** (`backend/routers/<area>.py`) — thin. Parses the request, calls a service function, returns the response. No business logic here.
2. **Business logic** (`backend/services/<area>.py`) — the actual work. Route handlers call into this, never the other way around.
3. **Response/request schema** (`backend/models.py`) — Pydantic models. Keep JSON keys `snake_case`.
4. **Register the router** in `backend/main.py` if it's a new file: `app.include_router(<area>.router)`.
5. **Errors**: raise `HTTPException` with a real status code and a `detail` string from the route handler — don't let raw exceptions bubble to the client.
6. **Update `docs/API_CONTRACT.md`** with the new route's method, path, request/response shape and error cases before merging. The collaborator builds against this document, not against reading your Python.

## How to add or change a database field

The schema lives as raw SQL in `backend/database.py` (`SCHEMA` string, `CREATE TABLE IF NOT EXISTS`). There is no ORM and no migration framework yet — SQLite is on the MVP tier.

1. Edit the `SCHEMA` string in `backend/database.py`.
2. Since `CREATE TABLE IF NOT EXISTS` won't alter an existing table, delete `backend/data/silicaguard.db` locally (or add an `ALTER TABLE` statement to `init_db()` for existing databases) and re-run to pick up the change.
3. Update `backend/scripts/seed_demo_data.py` so seeded data matches the new shape.
4. Update `docs/API_CONTRACT.md` if the field is exposed in any response.
5. **Announce the change** — a schema or response-shape change breaks the mobile app's local `expo-sqlite` schema and the dashboard's assumptions. Post it in the shared log before merging, not after.

## How to call the AI

Pattern used in `backend/services/ai_risk_engine.py` — follow it for any new Gemini call:

1. **System prompt lives in `backend/prompts/<name>.txt`** — a separate file, never inline in Python. Loaded once at import time.
2. **Strict JSON output**: the prompt tells the model to respond with JSON only. Parse defensively — Gemini sometimes wraps JSON in markdown code fences (```` ```json ... ``` ````). Strip them before parsing; see `_extract_json()` in `ai_risk_engine.py` for the regex that does this.
3. **Malformed response handling**: if `json.loads` fails or the model call errors, don't let it corrupt saved data — the screening/answers should already be persisted before the AI call, so a failed AI call is retryable rather than data-destroying. Return a clear error to the caller (see `screen_miner()` in `routers/screening.py` for the pattern: catch, then `HTTPException(502, "AI risk engine unavailable, please retry")`).
4. **Store input and output together** — every AI call's input (the answers sent) and output (the JSON result) must be persisted on the screening row for audit. Never let only one side survive.
5. **Hard safety overrides are not the model's job.** If a rule must always hold (e.g. "certain findings always mean RED"), enforce it in Python after the model responds, not just in the prompt text.

## How to test the offline flow

Not yet testable — `mobile/` doesn't exist in this repo yet. Once it does, no offline feature is "done" until this passes:

1. Put the device in airplane mode.
2. Complete three screenings entirely offline.
3. Reconnect to the network.
4. Verify all three screenings appear on the backend (query `/api/workers/<phone>` or check the dashboard).

## How to add a screening question

The question bank lives in `backend/questions.py` (`SCREENING_QUESTIONS`). Each question has a `code`, bilingual (Shona/English) text, and scored options.

- **Question codes are shared between mobile and backend and must match exactly.** The mobile app's local screening flow and the backend's scoring both key off `question_code`. Changing a code, or adding/removing options, on one side without the other silently breaks scoring — the answer will still submit, but the score or downstream tier will be wrong with no error raised.
- Any new or changed question needs the Clinical Lead's sign-off before it ships (it's patient-facing).

## How to seed demo data

```
cd backend
./venv/Scripts/python.exe scripts/seed_demo_data.py
```

This creates a reproducible demo dataset (multiple mine sites, a spread of risk tiers, referrals across different lifecycle states, at least one worker with two screenings). It is safe to re-run — re-seed to this known state before any demo or rehearsal so the data on screen is predictable. It requires no Gemini API key: screenings are inserted directly with pre-computed results, not run through the live AI engine.

## Definition of done

Before merging, a piece of work must:

- [ ] Run locally without errors.
- [ ] Handle the failure path (bad input, downstream service down, empty/missing data) — not just the happy path.
- [ ] Contain no committed secret (check the diff, not just `.gitignore`).
- [ ] Have `docs/API_CONTRACT.md` updated if the request/response shape changed.
- [ ] Have the other developer notified if it affects `mobile/`, `dashboard/`, the schema, or the API contract.

## Common gotchas in this project

- **The Africa's Talking Python SDK fails with an SSL error on Windows.** Use `httpx` against their REST API directly — see `backend/services/notifications.py` for the working pattern. Don't reach for the `africastalking` package.
- **USSD's `text` field arrives as the full session history joined by `*`** (e.g. `"1*3*2"`). Read only the last segment: `text.split("*")[-1]`. The `sessionId` must stay identical across every request in one session — it's the only thing tying the turns together server-side.
- **Gemini sometimes wraps JSON in markdown code fences.** Strip them before parsing (see `_extract_json()` in `ai_risk_engine.py`).
- **The free-tier Render server sleeps after inactivity** and takes 30–50 seconds to wake. Warm it before any demo or rehearsal — hit `/api/health` a few minutes ahead of time.
- **Tests mock `services.notifications`** (see `tests/conftest.py`'s `_mock_notifications` fixture) so they never hit the real Africa's Talking API. If you add a new notification-sending function, mock it the same way or tests will attempt real network calls.
