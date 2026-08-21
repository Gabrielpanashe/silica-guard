import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colours, light, typography, spacing, radius } from '../theme';

/**
 * StatCard
 * Props:
 *   value      — number or string to display large
 *   label      — text below the number
 *   colour     — border + number colour (defaults to mint; callers still
 *                pass risk-tier/semantic colours directly — those are
 *                unchanged by the light-theme pass, only this card's own
 *                surface/label chrome moved to `light` tokens)
 *   large      — bool, makes the number bigger (for "Screened Today")
 *   onPress    — optional. When provided, the card becomes tappable
 *                (used for Refer Now / Watch drill-down lists) — omit
 *                for a plain, non-interactive card.
 */
export default function StatCard({ value = 0, label = '', colour = colours.mint, large = false, onPress }) {
  const Wrapper = onPress ? TouchableOpacity : View;
  return (
    <Wrapper
      style={[s.card, { borderColor: colour }, large && s.cardLarge]}
      onPress={onPress}
      activeOpacity={onPress ? 0.75 : 1}
    >
      <Text style={[s.value, { color: colour }, large && s.valueLarge]}>
        {value}
      </Text>
      <Text style={s.label}>{label}</Text>
    </Wrapper>
  );
}

const s = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: light.surface,
    borderRadius: radius.md,
    borderWidth: 1.5,
    padding: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardLarge: {
    paddingVertical: spacing.xl,
    flex: 1.2,
  },
  value: {
    fontSize: typography.subtitle,
    fontWeight: typography.black,
    lineHeight: 36,
  },
  valueLarge: {
    fontSize: typography.display,
    lineHeight: 62,
    letterSpacing: -2,
  },
  label: {
    fontSize: typography.micro,
    color: light.textMuted,
    fontWeight: typography.semibold,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.xs,
  },
});
