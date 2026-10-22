import { View, Text, StyleSheet } from 'react-native';
import { ui, fonts } from '../theme';
import ReadyDot from '../../assets/icons/ready-dot.svg';

/**
 * VisitRow — one outreach visit in the Home "Outreach planner" card
 * (Figma "Visit item", 2 October 2026). Shows the same fields the old
 * planner rows did (date, screened / expected, progress, Ready/Pending) —
 * the date is now a SEP / 10 chip and the site name is the row title.
 */
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

export default function VisitRow({ visit }) {
  // scheduled_date is a plain YYYY-MM-DD — split it rather than new Date(),
  // which would parse it as UTC midnight and can show the previous day.
  const [, m, d] = (visit.scheduled_date || '').split('-');
  const month = MONTHS[Number(m) - 1] || '—';
  const day = d ? String(Number(d)) : '—';
  const pct = visit.expected_headcount > 0
    ? Math.min((visit.screened_count / visit.expected_headcount) * 100, 100)
    : 0;
  const ready = !!visit.report_generated;

  return (
    <View style={s.row}>
      <View style={s.dateChip}>
        <Text style={s.month}>{month}</Text>
        <Text style={s.day}>{day}</Text>
      </View>
      <View style={s.body}>
        <Text style={s.title} numberOfLines={1}>{visit.site || 'Outreach visit'}</Text>
        <Text style={s.meta}>{visit.screened_count} / {visit.expected_headcount} screened</Text>
        <View style={s.track}>
          <View style={[s.fill, { width: `${pct}%` }]} />
        </View>
      </View>
      <View style={[s.badge, { backgroundColor: ready ? ui.successSoft : ui.watchSoft }]}>
        {ready ? <ReadyDot /> : <View style={s.pendingDot} />}
        <Text style={[s.badgeText, { color: ready ? ui.success : ui.watch }]}>
          {ready ? 'Ready' : 'Pending'}
        </Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  dateChip: {
    width: 56, height: 60, borderRadius: 16, backgroundColor: ui.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  month: { fontFamily: fonts.bold, fontSize: 11, letterSpacing: 0.66, color: ui.primary },
  day: { fontFamily: fonts.bold, fontSize: 22, lineHeight: 26, color: ui.ink },
  body: { flex: 1, gap: 6 },
  title: { fontFamily: fonts.semibold, fontSize: 15, color: ui.ink },
  meta: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted },
  track: { height: 6, borderRadius: 3, backgroundColor: ui.track, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 3, backgroundColor: ui.primary },
  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingLeft: 8, paddingRight: 10, paddingVertical: 5, borderRadius: 999,
  },
  pendingDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: ui.watch },
  badgeText: { fontFamily: fonts.bold, fontSize: 12 },
});
