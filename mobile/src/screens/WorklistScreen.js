import {
  StyleSheet, Text, View, TouchableOpacity,
  ScrollView, Linking, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { colours, light, typography, spacing, radius, riskConfig } from '../theme';
import PhotoHeader from '../components/PhotoHeader';
import { confirmReferralAttendance } from '../services/api';

// Explicit colour-coded status, not just raw enum text — mint/checkmark for
// resolved (attended/closed), amber for still pending, red for missed its
// deadline. Matches the same visual language as dashboard/style.css's
// .status-pill on the web dashboard, so both frontends read the same way.
// These are risk/status-semantic colours, untouched by the light-theme
// pass (16 August) — only the surrounding surface/text chrome moved.
const STATUS_CONFIG = {
  attended:    { colour: colours.low,   background: 'rgba(2,195,154,0.15)',  label: '✓ Attended' },
  closed:      { colour: colours.low,   background: 'rgba(2,195,154,0.15)',  label: '✓ Closed' },
  escalated:   { colour: colours.refer, background: 'rgba(255,59,59,0.15)',  label: '⚠ Escalated' },
  open:        { colour: colours.watch, background: 'rgba(255,184,0,0.15)', label: 'Open' },
  pre_alerted: { colour: colours.watch, background: 'rgba(255,184,0,0.15)', label: 'Pre-alerted' },
  reminded:    { colour: colours.watch, background: 'rgba(255,184,0,0.15)', label: 'Reminded' },
};

/**
 * WorklistScreen — generic drill-down list for the Home screen's tappable
 * stat cards (Refer Now / Watch) and the Today's Log button. Reads its
 * content entirely from route.params, populated by GET /api/dashboard/today
 * (see services/api.js's getDashboardToday) — no fetching of its own, so it
 * always shows exactly the numbers the VHW just saw on Home.
 *
 * route.params:
 *   title       string — e.g. "Refer Now"
 *   shonaTitle  string — e.g. "Tumira Chipatara Izvozvi"
 *   items       array  — refer_now.items / watch.items / todays_log
 *   kind        "refer_now" | "watch" | "log" — controls which fields render
 *
 * Tapping a phone number opens the dialer directly (Linking.openURL) — the
 * whole point of surfacing contact details here is so the VHW can actually
 * follow up with someone who hasn't taken action yet.
 */
export default function WorklistScreen({ navigation, route }) {
  const { title = '', shonaTitle = '', kind = 'log' } = route.params || {};

  // Local copy (22 August) so a successful "Mark Attended" can update this
  // item's status pill immediately — this screen deliberately has no fetch
  // of its own (see docstring above), so there's nothing to re-fetch from.
  const [items, setItems] = useState(route.params?.items || []);
  const [confirming, setConfirming] = useState({}); // { [referral_id]: true } while a confirm is in flight

  const call = (phone) => {
    if (!phone) return;
    Linking.openURL(`tel:${phone}`).catch(() => {});
  };

  // Uses referral_code (live 22 August on refer_now items) against the same
  // unauthenticated confirm-attendance route dashboard/lookup.html uses —
  // PATCH /api/referrals/{id} is auth-gated and this app has no login, so
  // that route was never reachable from here. See services/api.js.
  const markAttended = async (item) => {
    if (!item.referral_code || confirming[item.referral_id]) return;
    setConfirming((c) => ({ ...c, [item.referral_id]: true }));
    try {
      await confirmReferralAttendance(item.referral_code);
      setItems((prev) =>
        prev.map((it) => (it.referral_id === item.referral_id ? { ...it, status: 'attended' } : it))
      );
    } catch (e) {
      if (e.status === 409) {
        // Someone else (the hospital, via the lookup page) already
        // confirmed it — not a real failure, just reflect that.
        setItems((prev) =>
          prev.map((it) => (it.referral_id === item.referral_id ? { ...it, status: 'attended' } : it))
        );
      } else {
        Alert.alert('Could not confirm', e.message || 'Try again in a moment.');
      }
    } finally {
      setConfirming((c) => ({ ...c, [item.referral_id]: false }));
    }
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="dark" />

      {/* ── HEADER — reuses Landing's outreach photo (16 August), see
          components/PhotoHeader.js ── */}
      <PhotoHeader
        title={title}
        shonaTitle={shonaTitle}
        onBack={() => navigation.goBack()}
        right={(
          <View style={s.countBadge}>
            <Text style={s.countText}>{items.length}</Text>
          </View>
        )}
      />

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {items.length === 0 && (
          <View style={s.emptyState}>
            <Text style={s.emptyEmoji}>✅</Text>
            <Text style={s.emptyText}>Nothing here right now.</Text>
          </View>
        )}

        {items.map((item, i) => {
          const config = riskConfig[item.tier] || riskConfig.GREEN;
          const key = item.referral_id ?? item.screening_id ?? i;
          return (
            <View key={key} style={[s.card, { borderLeftColor: config.colour }]}>
              <View style={s.cardTop}>
                <Text style={s.name}>{item.miner_name}</Text>
                <View style={[s.tierPill, { backgroundColor: config.background }]}>
                  <Text style={[s.tierPillText, { color: config.colour }]}>{item.tier}</Text>
                </View>
              </View>

              <View style={s.metaRow}>
                <Text style={s.meta}>{item.mine_site || 'Unknown site'}</Text>
                {kind === 'refer_now' && item.status && (
                  <View
                    style={[
                      s.statusPill,
                      { backgroundColor: (STATUS_CONFIG[item.status] || {}).background || light.surfaceAlt },
                    ]}
                  >
                    <Text style={[s.statusPillText, { color: (STATUS_CONFIG[item.status] || {}).colour || light.textMuted }]}>
                      {(STATUS_CONFIG[item.status] || {}).label || item.status.replace('_', ' ')}
                    </Text>
                  </View>
                )}
              </View>

              {kind === 'watch' && (
                <Text style={s.watchCaption}>Referral open (routine, 14-day window) — full queue on the Dashboard</Text>
              )}

              {kind === 'refer_now' && item.deadline && (
                <Text style={s.deadline}>⏱ Deadline: {item.deadline}</Text>
              )}

              <View style={s.actionsRow}>
                <TouchableOpacity style={s.callRow} onPress={() => call(item.phone)} activeOpacity={0.7}>
                  <Text style={s.callIcon}>📞</Text>
                  <Text style={s.callText}>{item.phone}</Text>
                </TouchableOpacity>

                {kind === 'refer_now' && item.referral_code && !['attended', 'closed'].includes(item.status) && (
                  <TouchableOpacity
                    style={[s.attendBtn, confirming[item.referral_id] && s.attendBtnDisabled]}
                    onPress={() => markAttended(item)}
                    activeOpacity={0.75}
                    disabled={!!confirming[item.referral_id]}
                  >
                    <Text style={s.attendBtnText}>
                      {confirming[item.referral_id] ? 'Confirming…' : '✓ Mark Attended'}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          );
        })}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: light.bg },
  // Header row/back-button/title styles moved into components/PhotoHeader.js
  // (16 August) — this screen's header is that component now. countBadge
  // is still defined here (passed in as PhotoHeader's `right` prop) but
  // restyled for sitting on the photo's dark scrim instead of light.bg —
  // the old accentStart-on-light-blue-fade treatment would have had poor
  // contrast there.
  countBadge: {
    backgroundColor: 'rgba(255,255,255,0.18)', borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.4)', minWidth: 32, alignItems: 'center',
  },
  countText: { fontSize: typography.caption, color: colours.white, fontWeight: typography.black },

  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },

  emptyState: { alignItems: 'center', paddingTop: spacing.xxl * 2, gap: spacing.md },
  emptyEmoji: { fontSize: 40 },
  emptyText: { fontSize: typography.body, color: light.textMuted },

  card: {
    backgroundColor: light.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: light.border, borderLeftWidth: 4,
    padding: spacing.lg, marginBottom: spacing.md,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { fontSize: typography.body, fontWeight: typography.bold, color: light.textDark, flex: 1 },
  tierPill: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 2 },
  tierPillText: { fontSize: typography.micro, fontWeight: typography.black, letterSpacing: 0.5 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.xs, flexWrap: 'wrap' },
  meta: { fontSize: typography.caption, color: light.textMuted },
  statusPill: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 2 },
  statusPillText: { fontSize: typography.micro, fontWeight: typography.bold, textTransform: 'capitalize' },
  watchCaption: { fontSize: typography.tiny, color: light.textMuted, fontStyle: 'italic', marginTop: spacing.xs },
  deadline: { fontSize: typography.caption, color: light.textMuted, marginTop: spacing.xs },
  actionsRow: {
    flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap',
    gap: spacing.sm, marginTop: spacing.md,
  },
  callRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    backgroundColor: 'rgba(47,127,239,0.10)', borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
  },
  callIcon: { fontSize: 14 },
  callText: { fontSize: typography.caption, color: light.accentStart, fontWeight: typography.semibold },
  // "Mark Attended" (22 August) — filled, not an outline like callRow, so
  // it reads as the more committal of the two actions.
  attendBtn: {
    backgroundColor: colours.low, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
  },
  attendBtnDisabled: { opacity: 0.6 },
  attendBtnText: { fontSize: typography.caption, color: colours.white, fontWeight: typography.semibold },
});
