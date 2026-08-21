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

To try the USSD web simulator without a phone or an Africa's Talking sandbox number (master doc v6.0 Section 16.1, live as of 15 August): open `http://127.0.0.1:8000/ussd-simulator` in a browser while the server is running. It's a keypad + green-screen page that sends the exact form fields (`sessionId`, `phoneNumber`, `serviceCode`, `text`) a real Africa's Talking webhook would, against the real `/api/ussd` endpoint — same code path as `ussd_simulator.py` below, just in a browser instead of a terminal.

### Mobile (React Native / Expo)

```
cd mobile
npm install
npx expo start
```

Talks directly to the deployed backend (`https://silicaguard-backend.onrender.com`, hardcoded as `BASE_URL` in `mobile/src/services/api.js`) — no local backend needed to run the app, though you can point `BASE_URL` at `http://127.0.0.1:8000` for local backend testing. Check `docs/API_CONTRACT.md` for the current request/response shapes.

### Dashboard (plain HTML/CSS/JS, no build step)

No install, no build — it's static files. Either open `dashboard/index.html` directly in a browser, or serve the folder locally (e.g. `npx serve dashboard`) if you need it under `http://` rather than `file://`. Same hardcoded `BASE_URL` pattern as mobile (`dashboard/app.js`), pointed at the deployed backend. `dashboard/lookup.html` is the hospital-facing referral-code entry page (master doc v6.0 Section 1.1/16.6) — open it directly, or via the "Referral Lookup ↗" link in the main dashboard's topbar. **Not yet on `main`** as of 21 August — currently on `feat/mobile-redesign-blue-theme`, check `CLAUDE.md`'s sprint status for whether it's merged yet.

## How to add a new API endpoint

Follow the existing pattern in `backend/routers/` and `backend/services/`:

1. **Route file** (`backend/routers/<area>.py`) — thin. Parses the request, calls a service function, returns the response. No business logic here.
2. **Business logic** (`backend/services/<area>.py`) — the actual work. Route handlers call into this, never the other way around.
3. **Response/request schema** (`backend/models.py`) — Pydantic models. Keep JSON keys `snake_case`.
4. **Register the router** in `backend/main.py` if it's a new file: `app.include_router(<area>.router)`.
5. **Errors**: raise `HTTPException` with a real status code and a `detail` string from the route handler — don't let raw exceptions bubble to the client.
6. **Update `docs/API_CONTRACT.md`** with the new route's method, path, request/response shape and error cases before merging. The collaborator builds against this document, not against reading your Python.

## How to add or change a database field

The schema is declared as SQLAlchemy models in `backend/db_models.py`, applied via Alembic migrations in `backend/alembic/` (live since 15–16 August — see `CLAUDE.md`'s sprint status for the ORM/Postgres migration history).

1. Edit the field on the relevant model in `backend/db_models.py`.
2. `cd backend && ./venv/Scripts/python.exe -m alembic revision --autogenerate -m "describe the change"` — generates a migration in `backend/alembic/versions/`.
3. **Review the generated migration by hand before applying it** — autogenerate is good but not infallible (check column types, defaults, and that it isn't dropping something it shouldn't).
4. `./venv/Scripts/python.exe -m alembic upgrade head` — applies it to whatever `DATABASE_URL` names (local SQLite by default; point at the real Supabase `DATABASE_URL` to apply it there too, which you'll usually want to do in the same sitting for a schema change).
5. Update `backend/scripts/seed_demo_data.py` so seeded data matches the new shape.
6. Update `docs/API_CONTRACT.md` if the field is exposed in any response.
7. **Announce the change** — a schema or response-shape change can break the mobile app's assumptions and the dashboard's. Post it in the shared log before merging, not after.

## How to call the AI

Pattern used in `backend/services/ai_risk_engine.py` — follow it for any new Gemini call:

1. **System prompt lives in `backend/prompts/<name>.txt`** — a separate file, never inline in Python. Loaded once at import time.
2. **Strict JSON output**: the prompt tells the model to respond with JSON only. Parse defensively — Gemini sometimes wraps JSON in markdown code fences (```` ```json ... ``` ````). Strip them before parsing; see `_extract_json()` in `ai_risk_engine.py` for the regex that does this.
3. **Malformed response handling**: if `json.loads` fails or the model call errors, don't let it corrupt saved data — the screening/answers should already be persisted before the AI call, so a failed AI call is retryable rather than data-destroying. Return a clear error to the caller (see `screen_miner()` in `routers/screening.py` for the pattern: catch, then `HTTPException(502, "AI risk engine unavailable, please retry")`).
4. **Store input and output together** — every AI call's input (the answers sent) and output (the JSON result) must be persisted on the screening row for audit. Never let only one side survive.
5. **Hard safety overrides are not the model's job.** If a rule must always hold (e.g. "certain findings always mean RED"), enforce it in Python after the model responds, not just in the prompt text.

## How to test the offline flow

`mobile/src/services/offlineQueue.js` (on `feat/mobile-redesign-blue-theme`, not yet on `main` as of 21 August) persists a failed screening to `AsyncStorage` and retries it every time `HomeScreen` regains focus — see `CLAUDE.md`'s sprint status for the full mechanism. Code-complete but **never actually verified with a real airplane-mode test** as of this writing — no offline feature is "done" until this passes:

1. Put the device in airplane mode.
2. Complete three screenings entirely offline — each should fall into `ResultScreen.js`'s offline path (`offlineScore()` shown immediately, `queueOfflineScreening()` persisting it) rather than erroring out.
3. Reconnect to the network, then navigate back to Home — this is what triggers `attemptSync()`.
4. Verify all three screenings appear on the backend for real (query `GET /api/workers/<phone>` or check the dashboard), not just that the app's UI says they synced.

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
