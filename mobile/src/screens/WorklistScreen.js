import {
  StyleSheet, Text, View, TouchableOpacity,
  ScrollView, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius, riskConfig } from '../theme';

// Explicit colour-coded status, not just raw enum text — mint/checkmark for
// resolved (attended/closed), amber for still pending, red for missed its
// deadline. Matches the same visual language as dashboard/style.css's
// .status-pill on the web dashboard, so both frontends read the same way.
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
  const { title = '', shonaTitle = '', items = [], kind = 'log' } = route.params || {};

  const call = (phone) => {
    if (!phone) return;
    Linking.openURL(`tel:${phone}`).catch(() => {});
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={s.backBtn}>
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={s.headerText}>
          <Text style={s.headerTitle}>{title}</Text>
          {!!shonaTitle && <Text style={s.headerShona}>{shonaTitle}</Text>}
        </View>
        <View style={s.countBadge}>
          <Text style={s.countText}>{items.length}</Text>
        </View>
      </View>

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
                      { backgroundColor: (STATUS_CONFIG[item.status] || {}).background || 'rgba(255,255,255,0.08)' },
                    ]}
                  >
                    <Text style={[s.statusPillText, { color: (STATUS_CONFIG[item.status] || {}).colour || colours.muted }]}>
                      {(STATUS_CONFIG[item.status] || {}).label || item.status.replace('_', ' ')}
                    </Text>
                  </View>
                )}
              </View>

              {kind === 'watch' && (
                <Text style={s.watchCaption}>No referral needed yet — informal monitoring only</Text>
              )}

              {kind === 'refer_now' && item.deadline && (
                <Text style={s.deadline}>⏱ Deadline: {item.deadline}</Text>
              )}

              <TouchableOpacity style={s.callRow} onPress={() => call(item.phone)} activeOpacity={0.7}>
                <Text style={s.callIcon}>📞</Text>
                <Text style={s.callText}>{item.phone}</Text>
              </TouchableOpacity>
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

  emptyState: { alignItems: 'center', paddingTop: spacing.xxl * 2, gap: spacing.md },
  emptyEmoji: { fontSize: 40 },
  emptyText: { fontSize: typography.body, color: colours.muted },

  card: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.mid, borderLeftWidth: 4,
    padding: spacing.lg, marginBottom: spacing.md,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { fontSize: typography.body, fontWeight: typography.bold, color: colours.white, flex: 1 },
  tierPill: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 2 },
  tierPillText: { fontSize: typography.micro, fontWeight: typography.black, letterSpacing: 0.5 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.xs, flexWrap: 'wrap' },
  meta: { fontSize: typography.caption, color: colours.muted },
  statusPill: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 2 },
  statusPillText: { fontSize: typography.micro, fontWeight: typography.bold, textTransform: 'capitalize' },
  watchCaption: { fontSize: typography.tiny, color: colours.muted, fontStyle: 'italic', marginTop: spacing.xs },
  deadline: { fontSize: typography.caption, color: colours.muted, marginTop: spacing.xs },
  callRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    marginTop: spacing.md, alignSelf: 'flex-start',
    backgroundColor: colours.tealFade, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
  },
  callIcon: { fontSize: 14 },
  callText: { fontSize: typography.caption, color: colours.teal, fontWeight: typography.semibold },
});
