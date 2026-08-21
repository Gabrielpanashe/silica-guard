// ─────────────────────────────────────────────────────────────
//  Offline Screening Queue (16 August)
//
//  Closes a real gap against CLAUDE.md's non-negotiable rule — "The mobile
//  app must complete a full screening with no connectivity and sync
//  cleanly afterwards" — that wasn't actually true before this file
//  existed. ResultScreen.js's offline fallback computed a tier locally
//  (services/ai_risk_engine.py's thresholds mirrored client-side in
//  QuestionScreen.js's offlineScore) but never persisted or retried the
//  submission — it only ever lived in that one screen's React state, gone
//  the moment the VHW navigated away. This module is the missing half.
//
//  AsyncStorage, not expo-sqlite (CLAUDE.md's originally documented
//  choice) — this is a small pending-items array, not relational data;
//  expo-sqlite would be real overkill for it. Revisit if a genuine offline
//  data model shows up elsewhere.
// ─────────────────────────────────────────────────────────────

import AsyncStorage from '@react-native-async-storage/async-storage';
import { resolveMinerId, submitScreening } from './api';

const STORAGE_KEY = 'sg_pending_screenings';

async function readQueue() {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return []; // corrupt/unavailable storage — fail empty, never crash a screen over this
  }
}

async function writeQueue(queue) {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
  } catch {
    // Best-effort — if storage itself is unavailable there's nothing more
    // to do here; the caller already has the result on screen either way.
  }
}

/** Every screening currently waiting to sync, oldest first. */
export const getPendingScreenings = () => readQueue();

/**
 * Queues a screening that was scored offline because submitScreening
 * failed. Called from ResultScreen.js's offline-fallback branch, right
 * after the local tier is computed — never blocks or throws into the
 * screen that's already showing the miner their (offline) result.
 *
 * @param {object} params
 *   miner        { name, phone, mine_site }
 *   answers      the exact array already sent to offlineScore()
 *   screened_by  string
 * @returns {Promise<object>} the queued entry (has an `id` for later removal)
 */
export async function queueOfflineScreening({ miner, answers, screened_by }) {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    miner,
    answers,
    screened_by: screened_by || 'VHW',
    queuedAt: new Date().toISOString(),
    attempts: 0,
    lastError: null,
  };
  const queue = await readQueue();
  queue.push(entry);
  await writeQueue(queue);
  return entry;
}

/**
 * Attempts to sync every queued screening against the real backend.
 * Best-effort and independent per entry — one still-unreachable entry
 * never blocks another that might succeed (e.g. the AI came back up but
 * one particular retry hits a transient network blip). Safe to call
 * often and speculatively (e.g. every time Home gains focus) — a fully
 * offline phone just gets every entry re-queued with attempts+1 and
 * returns immediately.
 *
 * @returns {Promise<{ synced: number, remaining: number }>}
 */
export async function syncPendingScreenings() {
  const queue = await readQueue();
  if (queue.length === 0) return { synced: 0, remaining: 0 };

  let synced = 0;
  const stillPending = [];

  for (const entry of queue) {
    try {
      const minerId = await resolveMinerId(entry.miner);
      await submitScreening({
        miner_id: minerId,
        answers: entry.answers,
        screened_by: entry.screened_by,
        // This is the one real screening that actually was offline-scored
        // at the time — true here, unlike ResultScreen's live-path call
        // (which hardcodes false), is what makes offline_fallback_used
        // mean something on this record once it lands.
        offline_fallback_used: true,
      });
      synced += 1;
    } catch (e) {
      stillPending.push({
        ...entry,
        attempts: (entry.attempts || 0) + 1,
        lastError: e.message || 'Unknown error',
      });
    }
  }

  await writeQueue(stillPending);
  return { synced, remaining: stillPending.length };
}
