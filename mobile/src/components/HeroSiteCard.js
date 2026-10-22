import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Feather } from '@expo/vector-icons';
import { ui, fonts, shadows } from '../theme';
import EllipseLg from '../../assets/icons/hero-ellipse-lg.svg';
import EllipseSm from '../../assets/icons/hero-ellipse-sm.svg';
import MapPin from '../../assets/icons/map-pin.svg';
import ChevronDown from '../../assets/icons/chevron-down.svg';
import CheckIcon from '../../assets/icons/check.svg';

/**
 * HeroSiteCard — "Today's outreach site" (Figma "Hero — Today site",
 * 2 October 2026). Replaces the old white outreach banner; keeps everything
 * it showed (site name, district · province) and adds today's visit
 * progress plus the "Confirm today's site" action.
 *
 *   siteName     string
 *   mine         { district, province } | null
 *   visit        today's outreach visit at this site, or null
 *   confirmed    bool — already confirmed for today
 *   onConfirm    () => void
 *   onChange     () => void — opens the mine picker
 */
export default function HeroSiteCard({ siteName, mine, visit, confirmed, onConfirm, onChange }) {
  const expected = visit?.expected_headcount || 0;
  const screened = visit?.screened_count || 0;
  const pct = expected > 0 ? Math.min(Math.round((screened / expected) * 100), 100) : 0;
  const location = mine?.district ? `${mine.district} District · ${mine.province}` : null;

  return (
    <View style={[s.shadow, shadows.hero]}>
      <LinearGradient
        colors={[ui.heroStart, ui.heroEnd]}
        locations={[0.143, 0.857]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.card}
      >
        <View style={s.ellipseLg} pointerEvents="none"><EllipseLg /></View>
        <View style={s.ellipseSm} pointerEvents="none"><EllipseSm /></View>

        <View style={s.topRow}>
          <View style={s.eyebrowPill}>
            <MapPin />
            <Text style={s.eyebrow}>TODAY'S OUTREACH SITE</Text>
          </View>
          <TouchableOpacity style={s.change} onPress={onChange} activeOpacity={0.7} hitSlop={8}>
            <Text style={s.changeText}>Change</Text>
            <ChevronDown />
          </TouchableOpacity>
        </View>

        <View style={s.titleBlock}>
          <Text style={s.siteName} numberOfLines={2}>{siteName}</Text>
          <Text style={s.subtitle}>
            {visit
              ? `Scheduled visit  ·  ${expected} miners planned`
              : 'No outreach visit scheduled here today'}
          </Text>
          {!!location && <Text style={s.subtitle}>{location}</Text>}
        </View>

        {visit && (
          <View style={s.progressBlock}>
            <View style={s.progressLabels}>
              <Text style={s.progressText}>{screened} of {expected} screened</Text>
              <Text style={s.progressPct}>{pct}%</Text>
            </View>
            <View style={s.track}>
              <View style={[s.fill, { width: `${pct}%` }]} />
            </View>
          </View>
        )}

        {confirmed ? (
          <View style={[s.button, s.buttonConfirmed]}>
            <Feather name="check-circle" size={18} color={ui.heroAccent} />
            <Text style={[s.buttonText, { color: ui.surface }]}>Confirmed for today</Text>
          </View>
        ) : (
          <TouchableOpacity style={s.button} onPress={onConfirm} activeOpacity={0.85}>
            <CheckIcon />
            <Text style={s.buttonText}>Confirm today's site</Text>
          </TouchableOpacity>
        )}
      </LinearGradient>
    </View>
  );
}

const s = StyleSheet.create({
  shadow: { borderRadius: 28, backgroundColor: ui.heroStart },
  card: { borderRadius: 28, padding: 20, gap: 16, overflow: 'hidden' },
  // Figma positions these from the left of a 372-wide card; anchored to the
  // right edge here so they stay put on any phone width.
  ellipseLg: { position: 'absolute', right: -78, top: -90 },
  ellipseSm: { position: 'absolute', right: -48, top: 150 },

  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  eyebrowPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 999,
    paddingLeft: 8, paddingRight: 10, paddingVertical: 6,
  },
  eyebrow: { fontFamily: fonts.bold, fontSize: 10.5, letterSpacing: 0.84, color: 'rgba(255,255,255,0.9)' },
  change: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  changeText: { fontFamily: fonts.semibold, fontSize: 13, color: 'rgba(255,255,255,0.8)' },

  titleBlock: { gap: 6 },
  siteName: { fontFamily: fonts.bold, fontSize: 28, lineHeight: 34, letterSpacing: -0.56, color: ui.surface },
  subtitle: { fontFamily: fonts.medium, fontSize: 13, color: 'rgba(255,255,255,0.7)' },

  progressBlock: { gap: 8 },
  progressLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  progressText: { fontFamily: fonts.semibold, fontSize: 12, color: 'rgba(255,255,255,0.85)' },
  progressPct: { fontFamily: fonts.bold, fontSize: 12, color: ui.heroAccent },
  track: { height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.15)', overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 4, backgroundColor: ui.heroAccent },

  button: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: ui.surface, borderRadius: 16, paddingHorizontal: 16, paddingVertical: 15,
  },
  buttonConfirmed: { backgroundColor: 'rgba(255,255,255,0.12)' },
  buttonText: { fontFamily: fonts.bold, fontSize: 15, color: ui.primaryDeep },
});
