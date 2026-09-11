import { View, Text, StyleSheet } from 'react-native';
import { colours, typography, spacing, radius } from '../theme';

/**
 * SyncPill
 * Props:
 *   connected — bool (true = LIVE green, false = PENDING amber)
 *
 * 23 August 2026 — this used to say "OFFLINE" in red whenever anything was
 * queued, which reads as "no network connection" even when the real cause
 * is the AI risk engine briefly erroring (a 502, backend fully reachable,
 * see ResultScreen.js's matching fix) — a screening genuinely offline
 * (airplane mode) and a screening stuck retrying against a flaky AI call
 * are different situations, but this pill can't actually tell them apart
 * (derived purely from pendingCount > 0, no real network check — see
 * HomeScreen.js's comment on that same limitation). "PENDING" in amber is
 * the honest label for what's actually known: something hasn't synced yet,
 * not that the network is down.
 */
export default function SyncPill({ connected = true }) {
  const colour = connected ? colours.mint : colours.watch;
  const label  = connected ? 'LIVE' : 'PENDING';

  return (
    <View style={[s.pill, { borderColor: colour, backgroundColor: connected ? colours.mintFade : 'rgba(255,184,0,0.15)' }]}>
      <View style={[s.dot, { backgroundColor: colour }]} />
      <Text style={[s.text, { color: colour }]}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 3,
    borderWidth: 1,
    gap: spacing.xs,
  },
  dot: {
    width: 6, height: 6, borderRadius: 3,
  },
  text: {
    fontSize: typography.tiny,
    fontWeight: typography.bold,
    letterSpacing: 1,
  },
});
