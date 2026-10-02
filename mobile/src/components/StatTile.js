import { Text, TouchableOpacity, View, StyleSheet } from 'react-native';
import { ui, fonts, shadows } from '../theme';

/**
 * StatTile — one of the three Home stat cards (Figma "Stats", 2 October
 * 2026). Replaces StatCard on the redesigned Home; StatCard stays in the
 * repo for any screen not yet migrated.
 *
 *   Icon         SVG component (from assets/icons)
 *   value        number
 *   label        string — wraps onto two lines like the design
 *   tone         'primary' | 'refer' | 'watch'
 *   onPress      () => void
 */
const TONES = {
  primary: { number: ui.ink,   tile: ui.primarySoft, border: ui.border },
  refer:   { number: ui.refer, tile: ui.referSoft,   border: ui.referBorder },
  watch:   { number: ui.watch, tile: ui.watchSoft,   border: ui.watchBorder },
};

export default function StatTile({ Icon, value, label, tone = 'primary', onPress }) {
  const t = TONES[tone];
  return (
    <TouchableOpacity
      style={[s.card, shadows.card, { borderColor: t.border }]}
      onPress={onPress}
      activeOpacity={0.8}
    >
      <View style={[s.iconTile, { backgroundColor: t.tile }]}>
        <Icon />
      </View>
      <Text style={[s.value, { color: t.number }]}>{value}</Text>
      <Text style={s.label}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  card: {
    flex: 1, backgroundColor: ui.surface, borderWidth: 1, borderRadius: 20,
    padding: 14, gap: 10,
  },
  iconTile: { width: 34, height: 34, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  value: { fontFamily: fonts.bold, fontSize: 30, lineHeight: 32, letterSpacing: -0.9 },
  label: { fontFamily: fonts.semibold, fontSize: 12, lineHeight: 15, color: ui.muted },
});
