import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { ui, fonts, shadows } from '../theme';
import PlusIcon from '../../assets/icons/cta-plus.svg';
import ArrowRight from '../../assets/icons/cta-arrow-right.svg';

/**
 * PrimaryActionCard — "Screen new miner" (Figma "CTA — Screen new miner",
 * 2 October 2026). The app's one primary action; replaces the old blue
 * offset-shadow CTA with the same English + Shona copy.
 */
export default function PrimaryActionCard({ title, subtitle, onPress }) {
  return (
    <TouchableOpacity style={[s.shadow, shadows.cta]} onPress={onPress} activeOpacity={0.9}>
      <LinearGradient
        colors={[ui.ctaStart, ui.ctaEnd]}
        start={{ x: 0, y: 0.5 }}
        end={{ x: 1, y: 0.5 }}
        style={s.card}
      >
        <View style={s.plusTile}>
          <PlusIcon />
        </View>
        <View style={s.text}>
          <Text style={s.title}>{title}</Text>
          <Text style={s.subtitle}>{subtitle}</Text>
        </View>
        <View style={s.arrow}>
          <ArrowRight />
        </View>
      </LinearGradient>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  shadow: { borderRadius: 24, backgroundColor: ui.ctaEnd },
  card: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 18, borderRadius: 24 },
  plusTile: {
    width: 52, height: 52, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center', justifyContent: 'center',
  },
  text: { flex: 1, gap: 3 },
  title: { fontFamily: fonts.bold, fontSize: 19, letterSpacing: -0.19, color: ui.surface },
  subtitle: { fontFamily: fonts.medium, fontSize: 13, color: 'rgba(255,255,255,0.8)' },
  arrow: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: ui.surface,
    alignItems: 'center', justifyContent: 'center',
  },
});
