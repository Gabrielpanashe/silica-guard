import {
  StyleSheet, Text, View, TouchableOpacity,
  SafeAreaView, ScrollView,
} from 'react-native';
import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius, riskConfig } from '../theme';
import { getDashboardToday } from '../services/api';

const TIER_ORDER = ['GREEN', 'YELLOW', 'ORANGE', 'RED'];

/**
 * OutreachStatsScreen — real outreach visit data (10 August), previously
 * a bare "Coming soon" Alert. Reads GET /api/dashboard/today's new
 * outreach_visits field (same shared services/outreach.visit_to_out
 * mapping the authenticated GET /api/outreach uses) — visual sibling of
 * WorklistScreen.js and the web dashboard's outreach panel, so all three
 * views of this data read the same way.
 *
 * route.params:
 *   site  string (optional) — scopes to one outreach site, same as Home's
 *         OUTREACH_SITE constant
 */
export default function OutreachStatsScreen({ navigation, route }) {
  const { site } = route.params || {};
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      setLoading(true);
      getDashboardToday(site)
        .then((data) => {
          if (!cancelled) {
            setVisits(data.outreach_visits || []);
            setError(null);
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err.message || 'Failed to load outreach stats.');
        })
        .finally(() => { if (!cancelled) setLoading(false); });
      return () => { cancelled = true; };
    }, [site])
  );

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={s.backBtn}>
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={s.headerText}>
          <Text style={s.headerTitle}>Outreach Stats</Text>
          <Text style={s.headerShona}>Zvidzidzo Zvekuenda Kunze</Text>
        </View>
        <View style={s.countBadge}>
          <Text style={s.countText}>{visits.length}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {loading && <Text style={s.loadingText}>Loading…</Text>}

        {!loading && error && (
          <View style={s.emptyState}>
            <Text style={s.emptyEmoji}>⚠️</Text>
            <Text style={s.emptyText}>{error}</Text>
          </View>
        )}

        {!loading && !error && visits.length === 0 && (
          <View style={s.emptyState}>
            <Text style={s.emptyEmoji}>📊</Text>
            <Text style={s.emptyText}>No outreach visits scheduled yet.</Text>
          </View>
        )}

        {!loading && !error && visits.map((visit) => {
          const pct = visit.expected_headcount > 0
            ? Math.min((visit.screened_count / visit.expected_headcount) * 100, 100)
            : 0;
          return (
            <View key={visit.id} style={s.card}>
              <View style={s.cardTop}>
                <View style={{ flex: 1 }}>
                  <Text style={s.site}>{visit.site}</Text>
                  <Text style={s.meta}>{visit.scheduled_date}</Text>
                </View>
                <View style={[s.reportBadge, visit.report_generated ? s.reportReady : s.reportPending]}>
                  <Text style={[s.reportBadgeText, { color: visit.report_generated ? colours.low : colours.watch }]}>
                    {visit.report_generated ? 'Report ready' : 'Pending'}
                  </Text>
                </View>
              </View>

              <View style={s.progressRow}>
                <View style={s.progressTrack}>
                  <View style={[s.progressFill, { width: `${pct}%` }]} />
                </View>
                <Text style={s.progressText}>{visit.screened_count} / {visit.expected_headcount} screened</Text>
              </View>

              {visit.report_generated && visit.tier_distribution && (
                <View style={s.reportSection}>
                  <View style={s.tierRow}>
                    {TIER_ORDER.map((tier) => (
                      <View key={tier} style={s.tierChip}>
                        <Text style={[s.tierChipCount, { color: riskConfig[tier].colour }]}>
                          {visit.tier_distribution[tier] ?? 0}
                        </Text>
                        <Text style={s.tierChipLabel}>{tier}</Text>
                      </View>
                    ))}
                  </View>
                  {(visit.referral_list || []).map((r, i) => (
                    <View key={i} style={s.referralRow}>
                      <Text style={s.referralName}>{r.miner_name}</Text>
                      <Text style={s.referralMeta}>{r.tier} · {r.status.replace('_', ' ')}</Text>
                    </View>
                  ))}
                  {(!visit.referral_list || visit.referral_list.length === 0) && (
                    <Text style={s.noReferrals}>No referrals from this visit.</Text>
                  )}
                </View>
              )}
            </View>
          );
        })}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colours.navy },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
    borderBottomWidth: 0.5, borderBottomColor: colours.card, gap: spacing.md,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.sm,
    backgroundColor: colours.card, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: colours.teal,
  },
  backArrow: { fontSize: 18, color: colours.teal },
  headerText: { flex: 1 },
  headerTitle: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  headerShona: { fontSize: typography.micro, color: colours.muted, fontStyle: 'italic', marginTop: 1 },
  countBadge: {
    backgroundColor: colours.tealFade, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: colours.teal, minWidth: 32, alignItems: 'center',
  },
  countText: { fontSize: typography.caption, color: colours.teal, fontWeight: typography.black },

  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  loadingText: { color: colours.muted, textAlign: 'center', marginTop: spacing.xxl },

  emptyState: { alignItems: 'center', paddingTop: spacing.xxl * 2, gap: spacing.md },
  emptyEmoji: { fontSize: 40 },
  emptyText: { fontSize: typography.body, color: colours.muted, textAlign: 'center', paddingHorizontal: spacing.xl },

  card: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.mid,
    padding: spacing.lg, marginBottom: spacing.md,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
  site: { fontSize: typography.body, fontWeight: typography.bold, color: colours.white },
  meta: { fontSize: typography.caption, color: colours.muted, marginTop: 2 },
  reportBadge: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 3 },
  reportReady: { backgroundColor: 'rgba(2,195,154,0.15)' },
  reportPending: { backgroundColor: 'rgba(255,184,0,0.15)' },
  reportBadgeText: { fontSize: typography.micro, fontWeight: typography.black, textTransform: 'uppercase', letterSpacing: 0.3 },

  progressRow: { marginTop: spacing.md, gap: spacing.xs },
  progressTrack: { height: 6, backgroundColor: colours.mid, borderRadius: 999, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colours.mint, borderRadius: 999 },
  progressText: { fontSize: typography.tiny, color: colours.muted },

  reportSection: { marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colours.mid },
  tierRow: { flexDirection: 'row', gap: spacing.lg, marginBottom: spacing.sm },
  tierChip: { alignItems: 'center' },
  tierChipCount: { fontSize: typography.subtitle, fontWeight: typography.black },
  tierChipLabel: { fontSize: typography.micro, color: colours.muted, fontWeight: typography.semibold, marginTop: 2 },
  referralRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.xs },
  referralName: { fontSize: typography.caption, color: colours.offwhite },
  referralMeta: { fontSize: typography.caption, color: colours.muted, textTransform: 'capitalize' },
  noReferrals: { fontSize: typography.caption, color: colours.muted, fontStyle: 'italic' },
});
