import { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Easing } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Feather } from '@expo/vector-icons';
import { Badge } from '@ant-design/react-native';
import { ui, fonts } from '../theme';
import LogoShield from '../../assets/icons/logo-shield.svg';
import LiveDot from '../../assets/icons/live-dot.svg';
import BellIcon from '../../assets/icons/bell.svg';

/**
 * AppHeader — redesigned Home header (Figma "Header", 2 October 2026).
 *
 * Logo mark + "SilicaGuard / Field screening" on the left; status pill,
 * sync button and notifications bell on the right.
 *
 *   live          bool — same honest signal the old SyncPill used
 *                 (pendingCount === 0, see HomeScreen.js): green "Live",
 *                 or amber "Pending" when screenings are queued.
 *   pendingCount  number — badge on the sync button
 *   syncing       bool — spins the sync arrows, disables the button
 *   onSync        () => void
 *   unreadCount   number — badge on the bell
 *   onBell        () => void
 *
 * The sync button isn't in the Figma frame — it's an addition, so the
 * offline-queue retry is always one tap away rather than only appearing in
 * the pending banner. It uses Feather's refresh-cw, which shares the
 * design's outline icon style (2px round strokes).
 */
export default function AppHeader({ live, pendingCount, syncing, onSync, unreadCount, onBell }) {
  const spin = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!syncing) {
      spin.stopAnimation();
      spin.setValue(0);
      return undefined;
    }
    const loop = Animated.loop(
      Animated.timing(spin, { toValue: 1, duration: 900, easing: Easing.linear, useNativeDriver: true })
    );
    loop.start();
    return () => loop.stop();
  }, [syncing, spin]);

  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  return (
    <View style={s.header}>
      <View style={s.brand}>
        <LinearGradient
          colors={[ui.primaryDeep, ui.primary]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={s.logo}
        >
          <LogoShield />
        </LinearGradient>
        <View>
          <Text style={s.brandName}>SilicaGuard</Text>
          <Text style={s.brandSub}>Field screening</Text>
        </View>
      </View>

      <View style={s.right}>
        {live ? (
          <View style={[s.pill, { backgroundColor: ui.successSoft }]}>
            <LiveDot />
            <Text style={[s.pillText, { color: ui.success }]}>Live</Text>
          </View>
        ) : (
          <View style={[s.pill, { backgroundColor: ui.watchSoft }]}>
            <View style={[s.dot, { backgroundColor: ui.watch }]} />
            <Text style={[s.pillText, { color: ui.watch }]}>Pending</Text>
          </View>
        )}

        <Badge text={pendingCount > 0 ? pendingCount : undefined} overflowCount={99}>
          <TouchableOpacity
            style={[s.circleBtn, syncing && { opacity: 0.6 }]}
            onPress={onSync}
            disabled={syncing}
            activeOpacity={0.75}
            accessibilityLabel="Sync offline screenings"
          >
            <Animated.View style={{ transform: [{ rotate }] }}>
              <Feather name="refresh-cw" size={18} color={ui.ink} />
            </Animated.View>
          </TouchableOpacity>
        </Badge>

        <Badge text={unreadCount > 0 ? unreadCount : undefined} overflowCount={9}>
          <TouchableOpacity
            style={s.circleBtn}
            onPress={onBell}
            activeOpacity={0.75}
            accessibilityLabel="Notifications"
          >
            <BellIcon />
          </TouchableOpacity>
        </Badge>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
  logo: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  brandName: { fontFamily: fonts.extrabold, fontSize: 19, letterSpacing: -0.38, color: ui.ink },
  brandSub: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted },

  right: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingLeft: 10, paddingRight: 12, paddingVertical: 6, borderRadius: 999,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  pillText: { fontFamily: fonts.bold, fontSize: 12 },
  circleBtn: {
    width: 42, height: 42, borderRadius: 21,
    backgroundColor: ui.surface, borderWidth: 1, borderColor: ui.border,
    alignItems: 'center', justifyContent: 'center',
  },
});
