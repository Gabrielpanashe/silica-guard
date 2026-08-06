// ─────────────────────────────────────────────────────────────
//  SilicaGuard API Service
//  Source of truth: docs/api-contract.md in the backend repo
//  Switch BASE_URL to Render URL once Panashe deploys (Day 7)
// ─────────────────────────────────────────────────────────────

// ── CONFIG ────────────────────────────────────────────────────
const BASE_URL = 'http://127.0.0.1:8000';
// TODO Day 7: replace with → 'https://silica-guard.onrender.com'

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
    throw new Error(data?.detail || `HTTP ${res.status}`);
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
 * Currently live as POST /api/miners — will rename to /api/workers.
 *
 * @param {object} worker
 *   name       string  — full name
 *   phone      string  — "+263771234567" (unique identifier)
 *   mine_site  string  — e.g. "Globe & Phoenix Mine"
 *
 * Response: { id, name, phone, mine_site }
 * Error 409: phone already registered
 */
export const registerWorker = async ({ name, phone, mine_site }) => {
  const res = await fetch(`${BASE_URL}/api/miners`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, phone, mine_site }),
  });
  return handleResponse(res);
};

// TARGET — not built yet, don't call this until Panashe ships it
// export const getWorkerByPhone = async (phone) => { ... }

// ── SCREENING ─────────────────────────────────────────────────
/**
 * Submit a completed screening.
 * POST /api/screen
 *
 * @param {object} payload
 *   miner_id              number   — from registerWorker response
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
 *   contributing_factors  string[]
 *   advice_line           null (not built yet)
 *   previous_screening_id number | null
 *   provisional           boolean
 *
 * STILL TARGET (not in response yet):
 *   explanation_shona, populated advice_line, deterioration object
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