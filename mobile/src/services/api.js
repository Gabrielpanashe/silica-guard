// ─────────────────────────────────────────────────────────────
//  SilicaGuard API Service
//  Source of truth: docs/api-contract.md in the backend repo
// ─────────────────────────────────────────────────────────────

// ── CONFIG ────────────────────────────────────────────────────
const BASE_URL = 'https://silicaguard-backend.onrender.com';

// In-memory token store (replace with SecureStore in production)
let _token = null;

// ── HELPERS ───────────────────────────────────────────────────
const authHeaders = () => ({
  'Content-Type': 'application/json',
  ...((_token) ? { Authorization: `Bearer ${_token}` } : {}),
});

const handleResponse = async (res) => {
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data?.detail || `HTTP ${res.status}`);
    err.status = res.status; // lets a caller distinguish e.g. 409 "already done" from a real failure
    throw err;
  }
  return data;
};

// ── HEALTH ────────────────────────────────────────────────────
/**
 * Ping the backend — call this on app start to warm the Render
 * free-tier server before the demo.
 * GET /api/health → { status: "ok" }
 */
export const checkHealth = async () => {
  const res = await fetch(`${BASE_URL}/api/health`);
  return handleResponse(res);
};

// ── AUTH ──────────────────────────────────────────────────────
/**
 * Log in and store the bearer token.
 * POST /api/auth/login
 * Current demo credentials:
 *   hospital@silicaguard.health / change-me  → role: "hospital"
 *   cimas@silicaguard.health / change-me     → role: "cimas"
 *
 * NOTE: roles will change to practitioner / clinical / employer
 * in a future sprint — flag before building role-gated UI.
 */
export const login = async (email, password) => {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await handleResponse(res);
  _token = data.access_token;
  return data; // { access_token, role }
};

export const getToken = () => _token;
export const clearToken = () => { _token = null; };

// ── WORKERS ───────────────────────────────────────────────────
/**
 * Register a new miner before their first screening.
 * POST /api/workers
 *
 * @param {object} worker
 *   name       string  — full name
 *   phone      string  — "+263771234567" (unique identifier)
 *   mine_site  string  — e.g. "Globe & Phoenix Mine"
 *
 * Response: { id, name, phone, site }
 * Error 409: phone already registered
 */
export const registerWorker = async ({ name, phone, mine_site }) => {
  const res = await fetch(`${BASE_URL}/api/workers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, phone, site: mine_site }),
  });
  return handleResponse(res);
};

/**
 * Look up an existing worker by phone.
 * GET /api/workers/{phone}
 *
 * Response: { id, name, phone, site, screenings: [...] }
 * Error 404: phone not registered
 */
export const getWorkerByPhone = async (phone) => {
  const res = await fetch(`${BASE_URL}/api/workers/${phone}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse(res);
};

/**
 * Resolves a { name, phone, mine_site } to a backend miner_id, registering
 * them if this is the first time or looking them up if they already exist
 * (409). Pulled out of ResultScreen.js (16 August) so
 * services/offlineQueue.js's retry path uses the exact same
 * register-or-look-up logic instead of a second, driftable copy —
 * `resolveMinerId(miner)` replaces ResultScreen's old inline try/catch.
 *
 * @param {object} miner — { name, phone, mine_site }
 * @returns {Promise<number>} miner_id
 */
export const resolveMinerId = async (miner) => {
  try {
    const worker = await registerWorker({
      name: miner.name,
      phone: miner.phone,
      mine_site: miner.mine_site,
    });
    return worker.id;
  } catch (e) {
    const msg = e.message?.toLowerCase() || '';
    if (msg.includes('already registered') || msg.includes('409')) {
      const existing = await getWorkerByPhone(miner.phone);
      return existing.id;
    }
    throw e; // genuine failure — caller decides what to do
  }
};

// ── SCREENING ─────────────────────────────────────────────────
/**
 * Submit a completed screening.
 * POST /api/screen
 *
 * @param {object} payload
 *   miner_id              number   — from registerWorker/getWorkerByPhone response
 *   answers               array    — see shape below
 *   screened_by           string   — VHW name
 *   offline_fallback_used boolean  — true if AI was unavailable
 *
 * answers array shape:
 *   [{ question_code: "YEARS_UNDERGROUND", answer_value: "over_10", answer_score: 5 }]
 *
 * Response:
 *   tier                  "GREEN" | "YELLOW" | "ORANGE" | "RED"
 *   confidence            0.0–1.0
 *   explanation_english   string
 *   explanation_shona     string  (live since 7 August — always populated)
 *   contributing_factors  string[]
 *   advice_line           string  (always populated, template-bound)
 *   previous_screening_id number | null
 *   provisional           boolean
 *   deterioration         { compared_to_screening_id, changed, summary }
 *   referral_code         string | null  (22 August — the REAL code, ORANGE/RED only;
 *                          null for GREEN/YELLOW where no referral exists)
 *   facility_name         string | null  (same conditions as referral_code)
 *   deadline              string | null  (same conditions as referral_code)
 *
 * Error 404: unknown miner_id
 * Error 422: empty answers
 * Error 502: AI unavailable (screening still persisted for retry)
 */
export const submitScreening = async ({
  miner_id,
  answers,
  screened_by = 'VHW',
  offline_fallback_used = false,
}) => {
  const res = await fetch(`${BASE_URL}/api/screen`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      miner_id,
      answers,
      channel: 'APP',
      screened_by,
      offline_fallback_used,
    }),
  });
  return handleResponse(res);
};

// ── REFERRALS ─────────────────────────────────────────────────
/**
 * Fetch all referrals (hospital/cimas roles).
 * GET /api/referrals — requires auth token
 *
 * Response array item:
 *   id, miner_name, mine_site, tier, status, deadline,
 *   pre_alert_sent, attended_at, closed_at, created_at
 *
 * Valid statuses: open | pre_alerted | reminded | attended | closed | escalated
 * NOTE: reminded + escalated not reachable yet (scheduler not built)
 */
export const getReferrals = async () => {
  const res = await fetch(`${BASE_URL}/api/referrals`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
};

/**
 * Update referral status.
 * PATCH /api/referrals/{referral_id}
 *
 * @param {number} referralId
 * @param {string} status — one of the valid statuses above
 */
export const updateReferralStatus = async (referralId, status) => {
  const res = await fetch(`${BASE_URL}/api/referrals/${referralId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ status }),
  });
  return handleResponse(res);
};

// ── DASHBOARD ─────────────────────────────────────────────────
/**
 * Weekly dashboard summary.
 * GET /api/dashboard/week — requires auth token
 *
 * Response:
 *   total_screened        number
 *   high_risk_count       number  (ORANGE + RED tiers)
 *   referral_completion_rate  0.0–1.0
 *   ai_narrative          string  (placeholder for now)
 *   site_breakdown        [{ mine_site, count }]
 */
export const getDashboardWeek = async () => {
  const res = await fetch(`${BASE_URL}/api/dashboard/week`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
};

/**
 * Today's live VHW numbers — Screened Today / Refer Now / Watch / Today's Log.
 * GET /api/dashboard/today — unauthenticated (same field-worker precedent
 * as everything above), live since 7 August.
 *
 * @param {string} [site] — optional, filters every section to one mine site
 *
 * Response:
 *   screened_today  number
 *   todays_log      [{ screening_id, miner_name, phone, mine_site, tier, created_at }]
 *   refer_now       { count, items: [{ referral_id, miner_name, phone, mine_site, tier,
 *                     status, deadline, referral_code, facility_name }] }
 *                     — referral_code/facility_name live 22 August, specifically so
 *                     the mobile app (no login) can confirm attendance via
 *                     confirmReferralAttendance() below instead of the auth-gated
 *                     PATCH /api/referrals/{id}, which it can never reach.
 *   watch           { count, items: [{ screening_id, miner_name, phone, mine_site, tier, created_at }] }
 *
 * refer_now is a live worklist (not scoped to today) — an item drops off
 * once its status becomes attended/closed. watch reflects each miner's
 * most recent screening only.
 *
 * outreach_visits (live 10 August) — [{ id, site, scheduled_date,
 * expected_headcount, screened_count, report_generated, tier_distribution,
 * referral_list }], same shape GET /api/outreach returns to a logged-in
 * coordinator. tier_distribution/referral_list are null until
 * report_generated is true. Powers the Outreach Stats screen.
 */
export const getDashboardToday = async (site) => {
  const query = site ? `?site=${encodeURIComponent(site)}` : '';
  const res = await fetch(`${BASE_URL}/api/dashboard/today${query}`);
  return handleResponse(res);
};

// ── MINES ─────────────────────────────────────────────────────
/**
 * List mine sites for the outreach-site dropdown.
 * GET /api/mines — unauthenticated, live since 7 August.
 *
 * Response: [{ id, name, district, province }], ordered by district then name.
 */
export const getMines = async () => {
  const res = await fetch(`${BASE_URL}/api/mines`);
  return handleResponse(res);
};

/**
 * Add a mine that isn't in the list yet.
 * POST /api/mines — unauthenticated.
 *
 * @param {object} mine — { name, district, province = "Midlands" }
 * Error 409: name already registered
 */
export const createMine = async ({ name, district, province = 'Midlands' }) => {
  const res = await fetch(`${BASE_URL}/api/mines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, district, province }),
  });
  return handleResponse(res);
};

// ── FACILITIES ───────────────────────────────────────────────
/**
 * List every referral facility (hospitals, clinics) on record.
 * GET /api/facilities — unauthenticated (12 August).
 *
 * Response: [{ id, name, level, address, phone, latitude, longitude }]
 * Powers the Outreach Planner's "nearest hospital" preview — same rows
 * services/facility_matching.py uses internally for referral routing.
 */
export const getFacilities = async () => {
  const res = await fetch(`${BASE_URL}/api/facilities`);
  return handleResponse(res);
};

// ── OUTREACH PLANNER (write) ────────────────────────────────
/**
 * Schedule a new outreach visit.
 * POST /api/outreach — unauthenticated as of 12 August (was dashboard-only;
 * opened up so the VHW mobile app can schedule directly in the field —
 * see routers/outreach.py for the tradeoff this made deliberately).
 *
 * @param {object} visit
 *   site                string  — mine name
 *   scheduled_date      string  — "YYYY-MM-DD"
 *   expected_headcount  number
 *   health_workers      string[] (optional)
 *
 * Response: full OutreachVisitOut, same shape GET /api/dashboard/today's
 * outreach_visits and GET /api/outreach both already return.
 */
export const createOutreachVisit = async ({ site, scheduled_date, expected_headcount, health_workers = [] }) => {
  const res = await fetch(`${BASE_URL}/api/outreach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ site, scheduled_date, expected_headcount, health_workers }),
  });
  return handleResponse(res);
};

// ── REFERRALS (mobile-facing) ───────────────────────────────
/**
 * Fires the hospital referral alert email for a miner's most recent
 * referral — called by ReferralScreen when the card is generated (12
 * August), so the demo has a live, on-demand email trigger tied to that
 * exact moment. The same email also fires automatically server-side at
 * screening time regardless of this call.
 * POST /api/referrals/notify-email — unauthenticated.
 *
 * @param {string} phone
 * Response: { sent: boolean, tier: string, facility_name: string|null }
 * Error 404: worker not found, or worker has no referral on record.
 */
export const notifyReferralEmail = async (phone) => {
  const res = await fetch(`${BASE_URL}/api/referrals/notify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  });
  return handleResponse(res);
};

/**
 * Mark a referral attended, by its referral_code — the mobile-reachable
 * equivalent of updateReferralStatus() above, which hits an auth-gated
 * route this app can never call (no login). Same unauthenticated route
 * dashboard/lookup.html uses (22 August).
 * POST /api/referrals/lookup/{code}/confirm-attendance — unauthenticated.
 *
 * @param {string} code — e.g. "SG-4K7Q"
 * Response: { referral_code, status: "attended", attended_at }
 * Error 404: unknown code
 * Error 409: already attended/closed — treat as success, not a real failure
 */
export const confirmReferralAttendance = async (code) => {
  const res = await fetch(`${BASE_URL}/api/referrals/lookup/${encodeURIComponent(code)}/confirm-attendance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse(res);
};