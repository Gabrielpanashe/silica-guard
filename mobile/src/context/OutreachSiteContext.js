import { createContext, useContext, useState } from 'react';

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
 * No persistence (no AsyncStorage dependency — adding a new native module
 * this close to the demo without being able to test a rebuild was judged
 * too risky, same call MineSitePicker.js made). Resets on app restart,
 * which is fine for a single outreach day's session.
 */
const OutreachSiteContext = createContext(null);

const DEFAULT_SITE = 'Globe & Phoenix Mine';

export function OutreachSiteProvider({ children }) {
  const [site, setSite] = useState(DEFAULT_SITE);
  // Full { id, name, district, province } when a real seeded mine was
  // picked from the list; null for a free-typed custom site (MineSitePicker's
  // fallback path) — Home's banner falls back to plain `site` text then.
  const [mine, setMine] = useState(null);

  return (
    <OutreachSiteContext.Provider value={{ site, setSite, mine, setMine }}>
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
