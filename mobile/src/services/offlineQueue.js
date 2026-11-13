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
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import { resolveMinerId, submitScreening } from './api';
import { seal, open, isSealed, keyToHex, keyFromHex, KEY_BYTES } from './queueCrypto';

// ─────────────────────────────────────────────────────────────
//  Encryption at rest (docs/STACK.md: queued clinical data on a device that
//  can be lost must be encrypted).
//
//  The queue is one AES-256-GCM blob (queueCrypto.js) in AsyncStorage. The
//  32-byte key lives in expo-secure-store (Android Keystore), never next to
//  the data. Rules this file keeps, because a screening is never discarded:
//
//   - A blob that cannot be decrypted is quarantined under another key, never
//     overwritten or deleted. It is not "an empty queue".
//   - Old plaintext entries from before this change are migrated, and the
//     plaintext copy is removed only after the encrypted one reads back.
//   - If secure storage is unavailable, entries are held in memory for the
//     session rather than written in plaintext. That survives navigation, not
//     an app restart — a stated gap, not a silent one.
// ─────────────────────────────────────────────────────────────

const STORAGE_KEY = 'sg_pending_screenings_enc'; // sealed blob
const LEGACY_KEY = 'sg_pending_screenings'; // plaintext, pre-encryption builds
const QUARANTINE_PREFIX = 'sg_pending_screenings_unreadable_';
const KEY_ALIAS = 'sg_queue_key';

let memoryQueue = []; // used only while secure storage is unavailable

async function secureAvailable() {
  try {
    return await SecureStore.isAvailableAsync();
  } catch {
    return false;
  }
}

/** Returns the key, creating it when `create` is set. null = no usable key. */
async function getKey(create) {
  if (!(await secureAvailable())) return null;
  try {
    const hex = await SecureStore.getItemAsync(KEY_ALIAS);
    if (hex) return keyFromHex(hex);
    if (!create) return null;
    const key = Crypto.getRandomBytes(KEY_BYTES);
    await SecureStore.setItemAsync(KEY_ALIAS, keyToHex(key));
    // Read back: a key we cannot read again would encrypt data we can never open.
    if ((await SecureStore.getItemAsync(KEY_ALIAS)) !== keyToHex(key)) return null;
    return key;
  } catch {
    return null;
  }
}

async function quarantine(raw) {
  try {
    await AsyncStorage.setItem(`${QUARANTINE_PREFIX}${Date.now()}`, raw);
    return true;
  } catch {
    return false; // caller must then leave the original blob where it is
  }
}

function parseLegacy(raw) {
  try {
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeQueue(queue) {
  const key = await getKey(true);
  if (!key) {
    memoryQueue = queue;
    return false;
  }
  try {
    await AsyncStorage.setItem(STORAGE_KEY, seal(key, queue, Crypto.getRandomBytes));
    memoryQueue = [];
    return true;
  } catch {
    memoryQueue = queue;
    return false;
  }
}

async function readQueue() {
  let entries = [];
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw && isSealed(raw)) {
      const key = await getKey(false);
      try {
        if (!key) throw new Error('no key');
        entries = open(key, raw);
      } catch {
        // Wrong key, missing key or tampered: keep the bytes, start a fresh queue.
        if (await quarantine(raw)) await AsyncStorage.removeItem(STORAGE_KEY);
      }
    }
  } catch {
    // Storage itself unavailable — fall through to whatever is in memory.
  }

  // Entries from builds before encryption existed: move them across.
  try {
    const legacyRaw = await AsyncStorage.getItem(LEGACY_KEY);
    if (legacyRaw) {
      const legacy = parseLegacy(legacyRaw);
      const merged = [...legacy, ...entries];
      if (await writeQueue(merged)) {
        const key = await getKey(false);
        const back = key && (await AsyncStorage.getItem(STORAGE_KEY));
        if (key && back && open(key, back).length === merged.length) {
          await AsyncStorage.removeItem(LEGACY_KEY);
        }
        entries = merged;
      } else {
        entries = merged; // not encrypted yet, plaintext copy stays for the next try
      }
    }
  } catch {
    // Leave the legacy copy where it is; nothing is lost.
  }

  return [...entries, ...memoryQueue.filter((m) => !entries.some((e) => e.id === m.id))];
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
