import AsyncStorage from '@react-native-async-storage/async-storage';
import { localDateKey } from '../context/OutreachSiteContext';

/**
 * notificationsFeed — what the Home header's bell shows (2 October 2026,
 * design revamp).
 *
 * There's no notifications pipeline on the backend yet (planned, not
 * built). Until there is, this builds the list on the device from data Home
 * already has — GET /api/dashboard/today plus the offline sync queue — so
 * the bell is useful today without inventing anything:
 *
 *   - a referral that's escalated, overdue, or due within 24 hours
 *   - an outreach visit at this site today or tomorrow
 *   - screenings scored offline and still waiting to sync
 *
 * When the real pipeline lands, swap buildNotifications() for a fetch and
 * keep the same item shape — NotificationsSheet and the unread badge don't
 * care where items come from.
 *
 * Item shape: { id, kind, tone, title, body, action }
 *   tone   'danger' | 'warning' | 'info'
 *   action 'refer_now' | 'outreach' | 'sync' — what tapping it opens
 *
 * `id` deliberately encodes the item's *state* (e.g. `ref-7-overdue`), so a
 * referral that moves from "due soon" to "overdue" counts as a new, unread
 * notification rather than staying marked as seen.
 */

const SEEN_KEY = 'sg_seen_notifications';
const DAY_MS = 24 * 60 * 60 * 1000;

// Backend timestamps are UTC "YYYY-MM-DD HH:MM:SS" (see docs/API_CONTRACT.md).
function parseUtc(ts) {
  if (!ts) return null;
  const d = new Date(`${ts.replace(' ', 'T')}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function hoursUntil(date, now) {
  return Math.round((date.getTime() - now.getTime()) / (60 * 60 * 1000));
}

export function buildNotifications({ stats, pendingCount, now = new Date() }) {
  const items = [];

  if (pendingCount > 0) {
    items.push({
      id: `sync-${pendingCount}`,
      kind: 'sync',
      tone: 'warning',
      title: `${pendingCount} screening${pendingCount === 1 ? '' : 's'} waiting to sync`,
      body: 'Scored offline. Tap to try sending now.',
      action: 'sync',
    });
  }

  for (const r of stats?.refer_now?.items || []) {
    const deadline = parseUtc(r.deadline);
    const who = r.miner_name || 'A miner';
    if (r.status === 'escalated') {
      items.push({
        id: `ref-${r.referral_id}-escalated`,
        kind: 'referral',
        tone: 'danger',
        title: `${who}'s referral was escalated`,
        body: `${r.tier} · missed the deadline at ${r.facility_name || 'the facility'}.`,
        action: 'refer_now',
      });
    } else if (deadline && deadline < now) {
      items.push({
        id: `ref-${r.referral_id}-overdue`,
        kind: 'referral',
        tone: 'danger',
        title: `${who} is overdue for referral`,
        body: `${r.tier} · ${r.facility_name || 'facility'} · code ${r.referral_code || '—'}`,
        action: 'refer_now',
      });
    } else if (deadline && deadline.getTime() - now.getTime() <= DAY_MS) {
      items.push({
        id: `ref-${r.referral_id}-due`,
        kind: 'referral',
        tone: 'warning',
        title: `${who} must attend within ${Math.max(hoursUntil(deadline, now), 1)}h`,
        body: `${r.tier} · ${r.facility_name || 'facility'} · code ${r.referral_code || '—'}`,
        action: 'refer_now',
      });
    }
  }

  const today = localDateKey(now);
  const tomorrow = localDateKey(new Date(now.getTime() + DAY_MS));
  for (const v of stats?.outreach_visits || []) {
    if (v.scheduled_date !== today && v.scheduled_date !== tomorrow) continue;
    const when = v.scheduled_date === today ? 'today' : 'tomorrow';
    items.push({
      id: `visit-${v.id}-${when}`,
      kind: 'outreach',
      tone: 'info',
      title: `Outreach visit ${when} at ${v.site}`,
      body: `${v.screened_count} / ${v.expected_headcount} miners screened so far.`,
      action: 'outreach',
    });
  }

  return items;
}

export async function getSeenIds() {
  try {
    const raw = await AsyncStorage.getItem(SEEN_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

// Stores only the ids currently in the feed, so the seen list can't grow
// forever as referrals come and go.
export async function markSeen(items) {
  try {
    await AsyncStorage.setItem(SEEN_KEY, JSON.stringify(items.map((i) => i.id)));
  } catch {
    // Best-effort — worst case the badge reappears next time.
  }
}
