// ─────────────────────────────────────────────────────────────
//  SilicaGuard Intelligence Dashboard
//  Plain vanilla JS, no build step, no framework — see SILICAGUARD.md
//  for why this deviates from the documented React+Vite dashboard
//  stack (built the night before an 11 August demo, no way to test
//  a build toolchain blind). Fetches the live production backend
//  directly; CORS is already open (allow_origins=["*"]).
// ─────────────────────────────────────────────────────────────

const BASE_URL = 'https://silicaguard-backend.onrender.com';

let _token = sessionStorage.getItem('sg_token') || null;

const $ = (id) => document.getElementById(id);

// ── AUTH ──────────────────────────────────────────────────────
async function login(email, password) {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
  _token = data.access_token;
  sessionStorage.setItem('sg_token', _token);
  return data;
}

function logout() {
  _token = null;
  sessionStorage.removeItem('sg_token');
  $('dashboard').hidden = true;
  $('login-screen').hidden = false;
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${_token}`,
});

// ── DATA FETCH ────────────────────────────────────────────────
async function fetchJSON(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (res.status === 401) {
    logout();
    throw new Error('Session expired — please sign in again.');
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status} on ${path}`);
  return data;
}

async function loadAll() {
  showWakeBanner(true);
  hideError();
  try {
    const [week, referrals, outreach] = await Promise.all([
      fetchJSON('/api/dashboard/week', { headers: authHeaders() }),
      fetchJSON('/api/referrals', { headers: authHeaders() }),
      fetchJSON('/api/outreach', { headers: authHeaders() }),
    ]);
    showWakeBanner(false);
    renderStats(week, referrals);
    renderTierChart(week.tier_distribution);
    renderNarrative(week.ai_narrative);
    renderSiteBreakdown(week.site_breakdown);
    renderReferralTable(referrals);
    renderOutreach(outreach);
    $('last-updated').textContent = `Updated ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (err) {
    showWakeBanner(false);
    showError(err.message || 'Failed to load dashboard data.');
  }
}

// ── RENDER: stat row ──────────────────────────────────────────
function renderStats(week, referrals) {
  $('stat-screened').textContent = week.total_screened;
  $('stat-highrisk').textContent = week.high_risk_count;
  $('stat-completion').textContent = `${Math.round(week.referral_completion_rate * 100)}%`;
  const openCount = referrals.filter((r) => !['attended', 'closed'].includes(r.status)).length;
  $('stat-openreferrals').textContent = openCount;
}

// ── RENDER: tier distribution (inline SVG-free CSS bars) ──────
const TIER_ORDER = ['GREEN', 'YELLOW', 'ORANGE', 'RED'];
const TIER_COLOUR = { GREEN: '#02C39A', YELLOW: '#FFB800', ORANGE: '#FF8C00', RED: '#FF3B3B' };

function renderTierChart(distribution) {
  const counts = TIER_ORDER.map((t) => distribution?.[t] ?? 0);
  const max = Math.max(...counts, 1);
  const el = $('tier-chart');
  el.innerHTML = TIER_ORDER.map((tier, i) => {
    const count = counts[i];
    const heightPct = Math.max((count / max) * 100, count > 0 ? 6 : 2);
    return `
      <div class="tier-bar-col">
        <div class="tier-bar-count" style="color:${TIER_COLOUR[tier]}">${count}</div>
        <div class="tier-bar" style="height:${heightPct}%; background:${TIER_COLOUR[tier]}"></div>
        <div class="tier-bar-label">${tier}</div>
      </div>`;
  }).join('');
}

// ── RENDER: AI narrative ──────────────────────────────────────
function renderNarrative(text) {
  $('narrative-text').textContent = text || 'No narrative available yet.';
}

// ── RENDER: site breakdown ────────────────────────────────────
function renderSiteBreakdown(sites) {
  const el = $('site-breakdown');
  if (!sites || sites.length === 0) {
    el.innerHTML = '<p class="muted small">No screenings recorded yet.</p>';
    return;
  }
  const max = Math.max(...sites.map((s) => s.count), 1);
  el.innerHTML = sites
    .slice()
    .sort((a, b) => b.count - a.count)
    .map(
      (s) => `
      <div class="site-row">
        <span class="site-name" title="${escapeHtml(s.mine_site)}">${escapeHtml(s.mine_site)}</span>
        <div class="site-bar-track"><div class="site-bar-fill" style="width:${(s.count / max) * 100}%"></div></div>
        <span class="site-count">${s.count}</span>
      </div>`
    )
    .join('');
}

// ── RENDER: referral table ────────────────────────────────────
function renderReferralTable(referrals) {
  const tbody = $('referral-tbody');
  if (!referrals || referrals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No referrals yet.</td></tr>';
    return;
  }
  tbody.innerHTML = referrals
    .map((r) => {
      const canAttend = !['attended', 'closed'].includes(r.status);
      const canClose = r.status !== 'closed';
      return `
      <tr>
        <td>${escapeHtml(r.miner_name)}</td>
        <td class="muted">${escapeHtml(r.mine_site || '—')}</td>
        <td><span class="tier-pill ${r.tier}">${r.tier}</span></td>
        <td><span class="status-pill ${r.status}">${r.status.replace('_', ' ')}</span></td>
        <td class="muted">${escapeHtml(r.deadline || '—')}</td>
        <td>${r.pre_alert_sent ? '✅' : '—'}</td>
        <td>
          ${canAttend ? `<button class="action-btn" data-action="attended" data-id="${r.id}">Mark Attended</button>` : ''}
          ${canClose ? `<button class="action-btn danger" data-action="closed" data-id="${r.id}">Close</button>` : ''}
        </td>
      </tr>`;
    })
    .join('');

  tbody.querySelectorAll('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => updateReferralStatus(btn.dataset.id, btn.dataset.action, btn));
  });
}

async function updateReferralStatus(referralId, status, btn) {
  btn.disabled = true;
  btn.textContent = '…';
  try {
    await fetchJSON(`/api/referrals/${referralId}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    });
    await loadAll(); // status change affects referral_completion_rate too — refresh everything
  } catch (err) {
    showError(err.message || 'Failed to update referral.');
    btn.disabled = false;
  }
}

// ── RENDER: outreach planner ──────────────────────────────────
function renderOutreach(visits) {
  const el = $('outreach-list');
  if (!visits || visits.length === 0) {
    el.innerHTML = '<p class="muted small">No outreach visits scheduled yet.</p>';
    return;
  }
  el.innerHTML = visits
    .slice()
    .sort((a, b) => (a.scheduled_date < b.scheduled_date ? 1 : -1))
    .map((v) => {
      const pct = v.expected_headcount > 0 ? Math.min((v.screened_count / v.expected_headcount) * 100, 100) : 0;
      let reportHtml = '';
      if (v.report_generated && v.tier_distribution) {
        const tiers = TIER_ORDER.map((t) => `<span style="color:${TIER_COLOUR[t]}">${t}: ${v.tier_distribution[t] ?? 0}</span>`).join(' &nbsp;·&nbsp; ');
        const refs = (v.referral_list || [])
          .map((r) => `<div class="outreach-referral-row"><span>${escapeHtml(r.miner_name)} — ${r.tier}</span><span>${r.status.replace('_', ' ')}</span></div>`)
          .join('');
        reportHtml = `
          <div class="outreach-report">
            <div class="outreach-report-tiers">${tiers}</div>
            ${refs || '<p class="muted small">No referrals from this visit.</p>'}
          </div>`;
      }
      return `
        <div class="outreach-item">
          <div class="outreach-top">
            <div>
              <div class="outreach-site">${escapeHtml(v.site)}</div>
              <div class="outreach-meta">${escapeHtml(v.scheduled_date)} · ${v.screened_count} / ${v.expected_headcount} screened</div>
            </div>
            <div class="outreach-progress-track"><div class="outreach-progress-fill" style="width:${pct}%"></div></div>
            <span class="report-badge ${v.report_generated ? 'ready' : 'pending'}">${v.report_generated ? 'Report ready' : 'Pending'}</span>
          </div>
          ${reportHtml}
        </div>`;
    })
    .join('');
}

// ── UI helpers ────────────────────────────────────────────────
function showWakeBanner(show) { $('wake-banner').hidden = !show; }
function showError(msg) { const el = $('error-banner'); el.textContent = `⚠ ${msg}`; el.hidden = false; }
function hideError() { $('error-banner').hidden = true; }
function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── BOOT ──────────────────────────────────────────────────────
$('base-url-display').textContent = BASE_URL;

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('login-btn');
  btn.disabled = true;
  btn.textContent = 'Signing in…';
  $('login-error').hidden = true;
  try {
    await login($('login-email').value.trim(), $('login-password').value);
    $('login-screen').hidden = true;
    $('dashboard').hidden = false;
    await loadAll();
  } catch (err) {
    $('login-error').textContent = err.message || 'Login failed.';
    $('login-error').hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sign in';
  }
});

$('refresh-btn').addEventListener('click', loadAll);
$('logout-btn').addEventListener('click', logout);

// If a token survived a page refresh (sessionStorage), skip straight to the dashboard.
if (_token) {
  $('login-screen').hidden = true;
  $('dashboard').hidden = false;
  loadAll();
}
