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
let _role = sessionStorage.getItem('sg_role') || null;

// Cache of GET /api/workers/{phone} responses, keyed by phone — a miner's
// full history is fetched once on first expand, not refetched every click.
const _minerHistoryCache = new Map();

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
  _role = data.role;
  sessionStorage.setItem('sg_token', _token);
  sessionStorage.setItem('sg_role', _role);
  return data;
}

function logout() {
  _token = null;
  _role = null;
  sessionStorage.removeItem('sg_token');
  sessionStorage.removeItem('sg_role');
  stopAutoRefresh();
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

let _miners = [];   // last fetched list, kept for client-side search/filter
let _minerFilter = { search: '', tier: '' };

async function loadAll() {
  showWakeBanner(true);
  hideError();
  try {
    const [week, referrals, outreach, miners, screenings, today, mines] = await Promise.all([
      fetchJSON('/api/dashboard/week', { headers: authHeaders() }),
      fetchJSON('/api/referrals', { headers: authHeaders() }),
      fetchJSON('/api/outreach', { headers: authHeaders() }),
      fetchJSON('/api/miners', { headers: authHeaders() }),
      fetchJSON('/api/screenings?limit=100', { headers: authHeaders() }),
      fetchJSON('/api/dashboard/today', {}), // unauthenticated by design, no headers needed
      fetchJSON('/api/mines', {}), // unauthenticated by design, powers the outreach form's site datalist
    ]);
    showWakeBanner(false);
    renderStats(week, referrals, today);
    renderTierChart(week.tier_distribution);
    renderNarrative(week.ai_narrative);
    renderSiteBreakdown(week.site_breakdown);
    renderReferralTable(referrals);
    renderOutreach(outreach);
    renderMinesDatalist(mines);
    _miners = miners;
    renderMinersTable();
    renderScreeningsLog(screenings);
    renderWatchList(today.watch.items);
    $('role-badge').textContent = _role ? `Signed in · ${_role}` : '';
    $('last-updated').textContent = `Updated ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (err) {
    showWakeBanner(false);
    showError(err.message || 'Failed to load dashboard data.');
  }
}

// ── RENDER: stat row ──────────────────────────────────────────
function renderStats(week, referrals, today) {
  $('stat-screened').textContent = week.total_screened;
  $('stat-today').textContent = today.screened_today;
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
        const refs = v.referral_list || [];
        const attended = refs.filter((r) => ['attended', 'closed'].includes(r.status)).length;
        const pending = refs.length - attended;
        const highRisk = (v.tier_distribution.ORANGE ?? 0) + (v.tier_distribution.RED ?? 0);
        const tiers = TIER_ORDER.map((t) => `<span style="color:${TIER_COLOUR[t]}">${t}: ${v.tier_distribution[t] ?? 0}</span>`).join(' &nbsp;·&nbsp; ');
        const refRows = refs
          .map((r) => `<div class="outreach-referral-row"><span>${escapeHtml(r.miner_name)} — ${r.tier}</span><span>${r.status.replace('_', ' ')}</span></div>`)
          .join('');
        reportHtml = `
          <div class="outreach-report">
            <div class="outreach-summary-row">
              <div class="outreach-summary-stat"><span class="outreach-summary-value">${v.screened_count}</span><span class="outreach-summary-label">Screened</span></div>
              <div class="outreach-summary-stat"><span class="outreach-summary-value" style="color:var(--mint)">${attended}</span><span class="outreach-summary-label">Attended</span></div>
              <div class="outreach-summary-stat"><span class="outreach-summary-value" style="color:var(--watch)">${pending}</span><span class="outreach-summary-label">Pending referral</span></div>
              <div class="outreach-summary-stat"><span class="outreach-summary-value" style="color:var(--refer)">${highRisk}</span><span class="outreach-summary-label">High risk</span></div>
            </div>
            <div class="outreach-report-tiers">${tiers}</div>
            ${refRows || '<p class="muted small">No referrals from this visit.</p>'}
          </div>`;
      } else if (!v.report_generated) {
        reportHtml = `<p class="outreach-pending-note">Report generates automatically once ${escapeHtml(v.scheduled_date)} has passed.</p>`;
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

// ── RENDER: mines datalist (Outreach Planner site field) ───────
function renderMinesDatalist(mines) {
  const el = $('mines-datalist');
  el.innerHTML = (mines || []).map((m) => `<option value="${escapeHtml(m.name)}">${escapeHtml(m.district || '')}</option>`).join('');
}

// ── Outreach Planner: schedule a new visit ──────────────────────
async function scheduleOutreachVisit(e) {
  e.preventDefault();
  const errEl = $('outreach-form-error');
  const okEl = $('outreach-form-success');
  errEl.hidden = true;
  okEl.hidden = true;

  const site = $('outreach-site-input').value.trim();
  const scheduled_date = $('outreach-date-input').value;
  const expected_headcount = parseInt($('outreach-headcount-input').value, 10);

  if (!site || !scheduled_date || !expected_headcount || expected_headcount < 1) {
    errEl.textContent = 'Fill in site, date and expected headcount.';
    errEl.hidden = false;
    return;
  }

  const btn = $('outreach-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Scheduling…';
  try {
    await fetchJSON('/api/outreach', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ site, scheduled_date, expected_headcount, health_workers: [] }),
    });
    okEl.textContent = `✓ Visit scheduled at ${site} for ${scheduled_date}.`;
    okEl.hidden = false;
    $('outreach-site-input').value = '';
    $('outreach-headcount-input').value = '';
    await loadAll();
  } catch (err) {
    errEl.textContent = err.message || 'Failed to schedule visit.';
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = '+ Schedule visit';
  }
}

// ── RENDER: Miners directory ───────────────────────────────────
function renderMinersTable() {
  const tbody = $('miners-tbody');
  const search = _minerFilter.search.trim().toLowerCase();
  const tier = _minerFilter.tier;

  const filtered = _miners.filter((m) => {
    if (tier && m.latest_tier !== tier) return false;
    if (!search) return true;
    return (
      m.name.toLowerCase().includes(search) ||
      m.phone.toLowerCase().includes(search) ||
      (m.site || '').toLowerCase().includes(search)
    );
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">${_miners.length === 0 ? 'No miners registered yet.' : 'No miners match this search.'}</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((m) => {
      const config = m.latest_tier ? TIER_COLOUR[m.latest_tier] : null;
      const tierCell = m.latest_tier
        ? `<span class="tier-pill ${m.latest_tier}">${m.latest_tier}</span>`
        : '<span class="muted">—</span>';
      return `
      <tr class="miner-row" data-phone="${escapeHtml(m.phone)}">
        <td><span class="miner-expand-icon">▸</span></td>
        <td>${escapeHtml(m.name)}</td>
        <td class="muted">${escapeHtml(m.phone)}</td>
        <td class="muted">${escapeHtml(m.site || '—')}</td>
        <td>${tierCell}</td>
        <td>${m.screening_count}</td>
        <td class="muted">${m.last_screened_at ? relativeTime(m.last_screened_at) : 'Never'}</td>
      </tr>
      <tr class="miner-detail-row" data-detail-for="${escapeHtml(m.phone)}" hidden>
        <td colspan="7"><div class="miner-detail"></div></td>
      </tr>`;
    })
    .join('');

  tbody.querySelectorAll('tr.miner-row').forEach((row) => {
    row.addEventListener('click', () => toggleMinerDetail(row));
  });
}

async function toggleMinerDetail(row) {
  const phone = row.dataset.phone;
  const detailRow = document.querySelector(`tr.miner-detail-row[data-detail-for="${CSS.escape(phone)}"]`);
  const isOpen = !detailRow.hidden;

  // Collapse any other open row first — one at a time keeps the table readable.
  document.querySelectorAll('tr.miner-detail-row').forEach((r) => { r.hidden = true; });
  document.querySelectorAll('tr.miner-row.expanded').forEach((r) => r.classList.remove('expanded'));

  if (isOpen) return; // was already open — this click just closed it

  detailRow.hidden = false;
  row.classList.add('expanded');
  const detailEl = detailRow.querySelector('.miner-detail');

  if (_minerHistoryCache.has(phone)) {
    detailEl.innerHTML = renderMinerHistoryHtml(_minerHistoryCache.get(phone));
    return;
  }

  detailEl.innerHTML = '<p class="miner-detail-loading">Loading history…</p>';
  try {
    const worker = await fetchJSON(`/api/workers/${encodeURIComponent(phone)}`);
    _minerHistoryCache.set(phone, worker);
    detailEl.innerHTML = renderMinerHistoryHtml(worker);
  } catch (err) {
    detailEl.innerHTML = `<p class="muted">Could not load history: ${escapeHtml(err.message || 'unknown error')}</p>`;
  }
}

function renderMinerHistoryHtml(worker) {
  if (!worker.screenings || worker.screenings.length === 0) {
    return '<p class="muted">No screenings recorded for this miner yet.</p>';
  }
  return worker.screenings
    .map(
      (s) => `
      <div class="miner-history-row">
        <span class="tier-pill ${s.tier || 'GREEN'}">${s.tier || '—'}</span>
        <span class="muted">${escapeHtml(s.created_at)}</span>
        <span class="miner-history-advice">${escapeHtml(s.advice_line || '')}</span>
      </div>`
    )
    .join('');
}

// ── RENDER: All Screenings activity log ────────────────────────
function renderScreeningsLog(screenings) {
  const el = $('screenings-log');
  if (!screenings || screenings.length === 0) {
    el.innerHTML = '<p class="muted small">No screenings recorded yet.</p>';
    return;
  }
  el.innerHTML = screenings.map((s) => activityRowHtml(s, { showChannel: true })).join('');
}

// ── RENDER: Watch list ──────────────────────────────────────────
function renderWatchList(items) {
  const el = $('watch-list');
  if (!items || items.length === 0) {
    el.innerHTML = '<p class="muted small">Nobody on the watch list right now.</p>';
    return;
  }
  el.innerHTML = items.map((w) => activityRowHtml(w, { showChannel: false })).join('');
}

// Shared row template for the Activity Log and Watch List — both are
// "miner + tier + when" rows, just sourced from different endpoints
// (GET /api/screenings vs GET /api/dashboard/today's watch.items).
function activityRowHtml(item, { showChannel }) {
  const colour = TIER_COLOUR[item.tier] || '#8BA0B0';
  const name = item.miner_name || item.name || 'Unknown';
  return `
    <div class="activity-row">
      <span class="activity-tier-dot" style="background:${colour}"></span>
      <div class="activity-main">
        <span class="activity-name">${escapeHtml(name)}</span>
        <span class="tier-pill ${item.tier}" style="margin-left:8px">${item.tier}</span>
        <div class="activity-meta">${escapeHtml(item.site || item.mine_site || 'Unknown site')}${item.advice_line ? ' · ' + escapeHtml(item.advice_line) : ''}</div>
      </div>
      ${showChannel ? `<span class="activity-channel">${escapeHtml(item.channel || '')}</span>` : ''}
      <span class="activity-time">${relativeTime(item.created_at)}</span>
    </div>`;
}

// ── Relative time ("2m ago", "3h ago") ──────────────────────────
// SQLite stores UTC without a 'Z' suffix — append it so Date parses it as
// UTC rather than assuming local time, which would throw the diff off by
// the viewer's own timezone offset.
function relativeTime(isoLike) {
  if (!isoLike) return '—';
  const iso = isoLike.includes('T') ? isoLike : isoLike.replace(' ', 'T') + 'Z';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return isoLike;
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

// ── Auto-refresh ─────────────────────────────────────────────────
// Every 45s, only while the tab is actually visible — a dashboard left
// open on a second monitor during the demo stays current without anyone
// touching Refresh, but a backgrounded tab doesn't keep hammering the API.
let _autoRefreshTimer = null;
function startAutoRefresh() {
  stopAutoRefresh();
  _autoRefreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible' && _token) loadAll();
  }, 45000);
}
function stopAutoRefresh() {
  if (_autoRefreshTimer) { clearInterval(_autoRefreshTimer); _autoRefreshTimer = null; }
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
    startAutoRefresh();
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

$('miner-search').addEventListener('input', (e) => {
  _minerFilter.search = e.target.value;
  renderMinersTable();
});
$('miner-tier-filter').addEventListener('change', (e) => {
  _minerFilter.tier = e.target.value;
  renderMinersTable();
});

$('outreach-form').addEventListener('submit', scheduleOutreachVisit);
// Default the planner's date field to tomorrow — a visit scheduled for
// today would already be past next scheduler tick's SMS windows.
{
  const tomorrow = new Date(Date.now() + 86400000);
  $('outreach-date-input').value = tomorrow.toISOString().slice(0, 10);
}

// If a token survived a page refresh (sessionStorage), skip straight to the dashboard.
if (_token) {
  $('login-screen').hidden = true;
  $('dashboard').hidden = false;
  loadAll();
  startAutoRefresh();
}
