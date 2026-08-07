import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import { colours, typography, spacing, radius } from '../theme';

/**
 * SecondaryButton
 * Props:
 *   icon      — emoji string
 *   label     — button text
 *   onPress   — function
 *   colour    — border accent colour
 */
export default function SecondaryButton({ icon = '', label = '', onPress, colour = colours.muted }) {
  return (
    <TouchableOpacity style={[s.btn, { borderColor: colour }]} onPress={onPress} activeOpacity={0.75}>
      <Text style={s.icon}>{icon}</Text>
      <Text style={s.label}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  btn: {
    flex: 1,
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1.5,
    padding: spacing.md,
    alignItems: 'center',
    gap: spacing.xs,
  },
  icon: { fontSize: 20 },
  label: {
    fontSize: typography.micro,
    color: colours.muted,
    fontWeight: typography.semibold,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
});
