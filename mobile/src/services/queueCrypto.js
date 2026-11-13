// ─────────────────────────────────────────────────────────────
//  Authenticated encryption for the offline queue.
//
//  Why: the queue holds a miner's name, phone number, mine site and health
//  answers on a phone that can be lost or taken in a mining compound
//  (docs/STACK.md: "Queued clinical data on a device that can be lost ...
//  must be encrypted"). AsyncStorage on its own is plaintext on disk.
//
//  AES-256-GCM via @noble/ciphers: a fresh random 12-byte nonce for every
//  write, and the authentication tag means a tampered or wrong-key blob is
//  rejected rather than decrypted to garbage.
//
//  Pure functions on purpose — no Expo imports — so they can be exercised
//  under plain Node. Key storage and randomness are supplied by the caller
//  (offlineQueue.js: key in expo-secure-store, bytes from expo-crypto).
//
//  Stored format:  "sg1:" + hex(nonce, 12 bytes) + hex(ciphertext || tag)
//  The prefix is the format version, so the scheme can change later and old
//  blobs can still be told apart from plaintext JSON (which starts with
//  "[" or "{").
// ─────────────────────────────────────────────────────────────

import { gcm } from '@noble/ciphers/aes.js';

export const PREFIX = 'sg1:';
const NONCE_BYTES = 12;
export const KEY_BYTES = 32;

const enc = new TextEncoder();
const dec = new TextDecoder();

function toHex(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 1) s += bytes[i].toString(16).padStart(2, '0');
  return s;
}

function fromHex(hex) {
  if (hex.length % 2 !== 0 || /[^0-9a-f]/i.test(hex)) throw new Error('bad hex');
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export const keyToHex = toHex;

export function keyFromHex(hex) {
  const key = fromHex(hex);
  if (key.length !== KEY_BYTES) throw new Error('bad key length');
  return key;
}

/** True when `stored` is a blob this module produced (as opposed to legacy plaintext). */
export const isSealed = (stored) => typeof stored === 'string' && stored.startsWith(PREFIX);

/**
 * @param {Uint8Array} key       32 bytes
 * @param {unknown}    value     anything JSON-serialisable
 * @param {(n:number)=>Uint8Array} randomBytes  cryptographically secure source
 * @returns {string}
 */
export function seal(key, value, randomBytes) {
  const nonce = randomBytes(NONCE_BYTES);
  if (!nonce || nonce.length !== NONCE_BYTES) throw new Error('bad nonce');
  const ct = gcm(key, nonce).encrypt(enc.encode(JSON.stringify(value)));
  return PREFIX + toHex(nonce) + toHex(ct);
}

/**
 * Throws if the blob is malformed, was sealed with another key, or was
 * modified. The caller must treat a throw as "cannot read", never as "empty".
 */
export function open(key, stored) {
  if (!isSealed(stored)) throw new Error('not a sealed blob');
  const body = fromHex(stored.slice(PREFIX.length));
  if (body.length < NONCE_BYTES + 16) throw new Error('blob too short');
  const nonce = body.slice(0, NONCE_BYTES);
  const ct = body.slice(NONCE_BYTES);
  return JSON.parse(dec.decode(gcm(key, nonce).decrypt(ct)));
}
