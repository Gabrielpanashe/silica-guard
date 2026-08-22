// ─────────────────────────────────────────────────────────────
//  SilicaGuard Referral Code Lookup — hospital/clinic-facing,
//  unauthenticated. Standalone script (no build step, no shared
//  module with app.js — duplicates the couple of tiny helpers it
//  needs rather than pull in the whole authenticated dashboard).
//  Backed by GET/POST /api/referrals/lookup/{code}, live since
//  14 August, unconsumed by any frontend until this page (16 August).
// ─────────────────────────────────────────────────────────────

const BASE_URL = 'https://silicaguard-backend.onrender.com';

const $ = (id) => document.getElementById(id);

const TIER_LABEL = {
  GREEN: 'LOW RISK', YELLOW: 'ELEVATED RISK', ORANGE: 'HIGH RISK', RED: 'CRITICAL RISK',
};

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data?.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// Normalises what the user typed (SMS text often gets pasted with a
// trailing period, extra whitespace, or lowercase) before it hits the API.
function normaliseCode(raw) {
  return String(raw || '').trim().toUpperCase().replace(/[.\s]+$/g, '');
}

let _currentCode = null;

function showLookupError(msg) {
  const el = $('lookup-error');
  el.textContent = msg;
  el.hidden = false;
}
function hideLookupError() { $('lookup-error').hidden = true; }

function renderResult(referral) {
  _currentCode = referral.referral_code;

  $('result-tier').textContent = TIER_LABEL[referral.tier] || referral.tier;
  $('result-tier').className = `tier-pill ${referral.tier}`;
  $('result-code').textContent = referral.referral_code;

  $('result-miner').textContent = `${referral.miner_name}${referral.mine_site ? ' · ' + referral.mine_site : ''}`;
  $('result-facility').textContent = referral.facility_name || 'Not yet matched to a facility';
  $('result-deadline').textContent = referral.deadline || '—';
  $('result-advice').textContent = referral.advice_line || '—';

  const factorsWrap = $('result-factors-wrap');
  const factorsEl = $('result-factors');
  if (referral.contributing_factors && referral.contributing_factors.length > 0) {
    factorsWrap.hidden = false;
    factorsEl.innerHTML = referral.contributing_factors
      .map((f) => `<span class="lookup-factor-chip">${escapeHtml(f)}</span>`)
      .join('');
  } else {
    factorsWrap.hidden = true;
  }

  const attendedBanner = $('attended-banner');
  const confirmBtn = $('confirm-btn');
  const alreadyAttended = referral.status === 'attended' || referral.status === 'closed';
  if (alreadyAttended) {
    attendedBanner.hidden = false;
    attendedBanner.textContent = referral.attended_at
      ? `✓ Attendance already confirmed — ${referral.attended_at}`
      : '✓ Attendance already confirmed';
    confirmBtn.hidden = true;
  } else {
    attendedBanner.hidden = true;
    confirmBtn.hidden = false;
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Confirm Attendance';
  }
  $('confirm-error').hidden = true;

  $('result-panel').hidden = false;
  $('not-found-panel').hidden = true;
}

async function doLookup(rawCode) {
  const code = normaliseCode(rawCode);
  hideLookupError();
  $('result-panel').hidden = true;
  $('not-found-panel').hidden = true;

  if (!code) {
    showLookupError('Enter a referral code first.');
    return;
  }

  const btn = $('lookup-btn');
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const referral = await fetchJSON(`/api/referrals/lookup/${encodeURIComponent(code)}`);
    renderResult(referral);
  } catch (err) {
    if (err.status === 404) {
      $('not-found-panel').hidden = false;
    } else {
      showLookupError(err.message || 'Could not reach the server — try again in a moment.');
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Look up';
  }
}

async function doConfirm() {
  if (!_currentCode) return;
  const btn = $('confirm-btn');
  btn.disabled = true;
  btn.textContent = '…';
  $('confirm-error').hidden = true;
  try {
    const result = await fetchJSON(`/api/referrals/lookup/${encodeURIComponent(_currentCode)}/confirm-attendance`, {
      method: 'POST',
    });
    $('attended-banner').hidden = false;
    $('attended-banner').textContent = `✓ Attendance confirmed — ${result.attended_at || 'just now'}`;
    btn.hidden = true;
  } catch (err) {
    // 409 = someone else already confirmed it between page-load and this
    // click — not a real failure, just re-render as already-attended.
    if (err.status === 409) {
      await doLookup(_currentCode);
    } else {
      btn.disabled = false;
      btn.textContent = 'Confirm Attendance';
      const el = $('confirm-error');
      el.textContent = err.message || 'Could not confirm — try again.';
      el.hidden = false;
    }
  }
}

// ── BOOT ──────────────────────────────────────────────────────
$('lookup-form').addEventListener('submit', (e) => {
  e.preventDefault();
  doLookup($('code-input').value);
});
$('confirm-btn').addEventListener('click', doConfirm);

// Support a deep link (e.g. ?code=SG-4K7Q) for a future QR/SMS-link
// convenience layer, even though nothing generates that link yet.
const _preFillCode = new URLSearchParams(window.location.search).get('code');
if (_preFillCode) {
  $('code-input').value = _preFillCode;
  doLookup(_preFillCode);
}
