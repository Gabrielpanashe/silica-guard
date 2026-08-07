import { View, Text, StyleSheet } from 'react-native';
import { colours, typography, spacing, radius } from '../theme';

/**
 * SyncPill
 * Props:
 *   connected — bool (true = LIVE green, false = OFFLINE red)
 */
export default function SyncPill({ connected = true }) {
  const colour = connected ? colours.mint : colours.refer;
  const label  = connected ? 'LIVE' : 'OFFLINE';

  return (
    <View style={[s.pill, { borderColor: colour, backgroundColor: connected ? colours.mintFade : 'rgba(255,59,59,0.15)' }]}>
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
