import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ui, fonts } from '../theme';
import HomeIcon from '../../assets/icons/tab-home.svg';
import LogIcon from '../../assets/icons/tab-log.svg';
import StatsIcon from '../../assets/icons/tab-stats.svg';
import DashboardIcon from '../../assets/icons/tab-dashboard.svg';
import SettingsIcon from '../../assets/icons/tab-settings.svg';

/**
 * BottomNav — Figma "Bottom nav" (2 October 2026). Takes over the old
 * Home secondary-button row (Today's Log / Outreach Stats / Dashboard /
 * Settings) — same four destinations, plus Home.
 *
 * A plain component rather than @react-navigation/bottom-tabs on purpose:
 * Dashboard opens an external web page and Settings has no screen yet, so
 * these aren't real tabs. Revisit once more redesigned screens carry the
 * nav.
 *
 * Tab icon strokes are `currentColor` (mapped in .svgrrc from the Figma
 * export's grey/blue), so one SVG per tab serves both states via `color`.
 *
 *   active   'home' | 'log' | 'stats' | 'dashboard' | 'settings'
 *   onSelect (key) => void
 */
const TABS = [
  { key: 'home',      label: 'Home',      Icon: HomeIcon },
  { key: 'log',       label: 'Log',       Icon: LogIcon },
  { key: 'stats',     label: 'Stats',     Icon: StatsIcon },
  { key: 'dashboard', label: 'Dashboard', Icon: DashboardIcon },
  { key: 'settings',  label: 'Settings',  Icon: SettingsIcon },
];

export default function BottomNav({ active = 'home', onSelect }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[s.bar, { paddingBottom: Math.max(22, insets.bottom + 8) }]}>
      {TABS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        const colour = isActive ? ui.tabActive : ui.tabInactive;
        return (
          <TouchableOpacity
            key={key}
            style={s.tab}
            onPress={() => onSelect?.(key)}
            activeOpacity={0.7}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
          >
            <View style={[s.iconPill, isActive && { backgroundColor: ui.tabActiveSoft }]}>
              <Icon color={colour} />
            </View>
            <Text style={[s.label, { color: colour, fontFamily: isActive ? fonts.bold : fonts.semibold }]}>
              {label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  bar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: ui.surface, borderTopWidth: 1, borderTopColor: ui.border,
    paddingTop: 10, paddingHorizontal: 16,
  },
  tab: { alignItems: 'center', gap: 4, minWidth: 54 },
  iconPill: { paddingHorizontal: 16, paddingVertical: 5, borderRadius: 999 },
  label: { fontSize: 11 },
});
