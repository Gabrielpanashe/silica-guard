import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * OutreachSiteContext — "which mine is the VHW at today", shared across the
 * whole app (10 August). Previously a hardcoded OUTREACH_SITE constant
 * inside HomeScreen.js — Home's live numbers (screened today, today's log,
 * refer now, watch) were filtered by that fixed string, but IntakeScreen's
 * own MineSitePicker let the VHW register a miner at a *different* site
 * with nothing keeping the two in sync. If they didn't match, a just-
 * completed screening simply never showed up anywhere on Home — not a
 * refresh bug, a site-mismatch bug.
 *
 * Persisted (2 October 2026, design revamp) — originally deliberately not,
 * because AsyncStorage wasn't a dependency yet; it has been since the
 * offline sync queue (services/offlineQueue.js) landed, so the old reason
 * no longer applies. The selected site now survives an app restart, and
 * the redesigned Home's "Confirm today's site" button records which site
 * was confirmed on which date. A confirmation only counts for the same
 * site on the same local calendar day — picking a different mine, or
 * opening the app tomorrow, asks the VHW to confirm again.
 *
 * Every AsyncStorage call is best-effort: a failed read/write just means
 * the in-memory default is used, never a blocked screen.
 */
const OutreachSiteContext = createContext(null);

const DEFAULT_SITE = 'Globe & Phoenix Mine';
const STORAGE_KEY = 'sg_outreach_site';

// Local calendar date as YYYY-MM-DD — the VHW's "today", not UTC's.
export function localDateKey(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function OutreachSiteProvider({ children }) {
  const [site, setSite] = useState(DEFAULT_SITE);
  // Full { id, name, district, province } when a real seeded mine was
  // picked from the list; null for a free-typed custom site (MineSitePicker's
  // fallback path) — Home's banner falls back to plain `site` text then.
  const [mine, setMine] = useState(null);
  // { site, date } of the last "Confirm today's site" tap, or null.
  const [confirmed, setConfirmed] = useState(null);
  // Don't write anything back until the saved value has been read —
  // otherwise the defaults above would overwrite it on first render.
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (!raw) return;
        const saved = JSON.parse(raw);
        if (saved.site) setSite(saved.site);
        if (saved.mine) setMine(saved.mine);
        if (saved.confirmed) setConfirmed(saved.confirmed);
      })
      .catch(() => {})
      .finally(() => setHydrated(true));
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ site, mine, confirmed })).catch(() => {});
  }, [hydrated, site, mine, confirmed]);

  const confirmSite = useCallback(() => {
    setConfirmed({ site, date: localDateKey() });
  }, [site]);

  const isConfirmedToday =
    !!confirmed && confirmed.site === site && confirmed.date === localDateKey();

  return (
    <OutreachSiteContext.Provider
      value={{ site, setSite, mine, setMine, confirmSite, isConfirmedToday }}
    >
      {children}
    </OutreachSiteContext.Provider>
  );
}

export function useOutreachSite() {
  const ctx = useContext(OutreachSiteContext);
  if (!ctx) {
    throw new Error('useOutreachSite() must be called within an OutreachSiteProvider');
  }
  return ctx;
}
