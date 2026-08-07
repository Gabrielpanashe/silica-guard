import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView, Alert } from 'react-native';
import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';
import StatCard from '../components/StatCard';
import SyncPill from '../components/SyncPill';
import SecondaryButton from '../components/SecondaryButton';
import { getDashboardToday } from '../services/api';

// Matches the outreach banner below — kept as one constant so the numbers
// shown and the site the banner claims to be at never disagree. TARGET:
// once there's a real "which outreach visit is active" signal available
// without auth, both this and the banner text should come from that
// instead of being hardcoded here.
const OUTREACH_SITE = 'Globe & Phoenix Mine';

const EMPTY_TODAY = {
  screened_today: 0,
  todays_log: [],
  refer_now: { count: 0, items: [] },
  watch: { count: 0, items: [] },
};

export default function HomeScreen({ navigation }) {
  const today = new Date().toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  // Real numbers from GET /api/dashboard/today (7 August) — previously
  // hardcoded to zero. Re-fetched every time this screen gains focus (not
  // just on mount) so returning here after a screening shows the update
  // without needing a manual refresh. Fails silently to EMPTY_TODAY on any
  // error (offline, cold Render instance) — this data is never allowed to
  // block the primary "Screen New Miner" action.
  const [stats, setStats] = useState(EMPTY_TODAY);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      getDashboardToday(OUTREACH_SITE)
        .then((data) => { if (!cancelled) setStats(data); })
        .catch(() => { if (!cancelled) setStats(EMPTY_TODAY); });
      return () => { cancelled = true; };
    }, [])
  );

  const openWorklist = (kind) => {
    const configByKind = {
      refer_now: { title: 'Refer Now', shonaTitle: 'Tumira Chipatara Izvozvi', items: stats.refer_now.items },
      watch:     { title: 'Watch',     shonaTitle: 'Tarisa Zvakanyanya',       items: stats.watch.items },
      log:       { title: "Today's Log", shonaTitle: 'Zvakaitika Nhasi',       items: stats.todays_log },
    };
    navigation.navigate('Worklist', { kind, ...configByKind[kind] });
  };

  const comingSoon = (feature) =>
    Alert.alert('Coming soon', `${feature} isn't built yet.`);

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* Decorative blobs */}
      <View style={s.blob1} />
      <View style={s.blob2} />
      <View style={s.blob3} />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <View>
          <Text style={s.brandWord}>SILICA</Text>
          <Text style={s.brandAccent}>Guard<Text style={s.brandDot}>●</Text></Text>
        </View>
        <View style={s.headerRight}>
          <SyncPill connected={true} />
          <Text style={s.dateText}>{today}</Text>
        </View>
      </View>

      {/* ── OUTREACH BANNER ── */}
      <View style={s.outreachBanner}>
        <Text style={s.eyebrow}>TODAY'S OUTREACH SITE</Text>
        <Text style={s.outreachName}>Globe &{'\n'}Phoenix Mine</Text>
        <View style={s.outreachTag}>
          <Text style={s.outreachTagText}>Kwekwe District · Midlands</Text>
        </View>
      </View>

      {/* ── STATS — real numbers, tappable (7 August) ── */}
      <View style={s.statsRow}>
        <StatCard
          value={stats.screened_today}
          label="Screened Today"
          colour={colours.mint}
          large
          onPress={() => openWorklist('log')}
        />
        <View style={s.statCol}>
          <StatCard
            value={stats.refer_now.count}
            label="Refer Now"
            colour={colours.refer}
            onPress={() => openWorklist('refer_now')}
          />
          <StatCard
            value={stats.watch.count}
            label="Watch"
            colour={colours.watch}
            onPress={() => openWorklist('watch')}
          />
        </View>
      </View>

      {/* ── MAIN CTA ── */}
      <TouchableOpacity
        style={s.cta}
        activeOpacity={0.88}
        onPress={() => navigation.navigate('Intake')}
      >
        <View style={s.ctaInner}>
          <Text style={s.ctaPlus}>+</Text>
          <View>
            <Text style={s.ctaMain}>SCREEN NEW{'\n'}MINER</Text>
            <Text style={s.ctaShona}>Tanga Kuongorora Mushandi →</Text>
          </View>
        </View>
        <View style={s.ctaShadow} />
      </TouchableOpacity>

      {/* ── SECONDARY ACTIONS ──
          "Today's Log" now opens a real screen (WorklistScreen, backed by
          GET /api/dashboard/today). "Outreach Stats"/"Settings" have no
          unauthenticated backend data to show yet — GET /api/outreach
          requires a coordinator login this app doesn't have a flow for —
          so they're an honest "coming soon" instead of a route that
          doesn't exist (7 August fix; previously these three navigate()
          calls all pointed at unregistered screens, which is what was
          producing the "action NAVIGATE not handled" warning). */}
      <View style={s.secondRow}>
        <SecondaryButton
          icon="📋" label={'Today\'s\nLog'}
          colour={colours.teal}
          onPress={() => openWorklist('log')}
        />
        <SecondaryButton
          icon="📊" label={'Outreach\nStats'}
          colour={colours.purple}
          onPress={() => comingSoon('Outreach Stats')}
        />
        <SecondaryButton
          icon="⚙️" label="Settings"
          colour={colours.muted}
          onPress={() => comingSoon('Settings')}
        />
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colours.navy,
    overflow: 'hidden',
  },
  blob1: {
    position: 'absolute', top: -80, right: -80,
    width: 220, height: 220, borderRadius: 110,
    backgroundColor: colours.teal, opacity: 0.18,
  },
  blob2: {
    position: 'absolute', top: 160, left: -60,
    width: 160, height: 160, borderRadius: 80,
    backgroundColor: colours.purple, opacity: 0.15,
  },
  blob3: {
    position: 'absolute', bottom: 80, right: -40,
    width: 130, height: 130, borderRadius: 65,
    backgroundColor: colours.mint, opacity: 0.12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  brandWord: {
    fontSize: typography.tiny,
    fontWeight: typography.light,
    color: colours.muted,
    letterSpacing: 4,
  },
  brandAccent: {
    fontSize: typography.hero,
    fontWeight: typography.black,
    color: colours.white,
    lineHeight: 36,
    letterSpacing: -1,
  },
  brandDot: { color: colours.mint, fontSize: 28 },
  headerRight: { alignItems: 'flex-end', paddingTop: 4, gap: spacing.xs },
  dateText: { fontSize: typography.tiny, color: colours.muted, textAlign: 'right' },

  outreachBanner: {
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    backgroundColor: colours.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1.5,
    borderColor: colours.teal,
    borderLeftWidth: 5,
  },
  eyebrow: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
    marginBottom: spacing.sm,
  },
  outreachName: {
    fontSize: 30,
    fontWeight: typography.black,
    color: colours.white,
    lineHeight: 32,
    letterSpacing: -0.5,
  },
  outreachTag: {
    marginTop: spacing.md,
    alignSelf: 'flex-start',
    backgroundColor: colours.tealFade,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  outreachTagText: {
    fontSize: typography.caption,
    color: colours.teal,
    fontWeight: typography.semibold,
  },

  statsRow: {
    flexDirection: 'row',
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    gap: spacing.md,
  },
  statCol: { flex: 1, gap: spacing.md },

  cta: { marginHorizontal: spacing.xl, marginTop: spacing.lg },
  ctaInner: {
    backgroundColor: colours.teal,
    borderRadius: radius.lg,
    padding: spacing.xl + 2,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    borderWidth: 2,
    borderColor: colours.mint,
    zIndex: 2,
  },
  ctaShadow: {
    position: 'absolute',
    bottom: -5, right: -5, left: 5,
    height: '100%',
    borderRadius: radius.lg,
    backgroundColor: colours.mint,
    zIndex: 1,
    opacity: 0.3,
  },
  ctaPlus: {
    fontSize: 52, fontWeight: typography.light,
    color: colours.white, lineHeight: 56,
  },
  ctaMain: {
    fontSize: typography.title,
    fontWeight: typography.black,
    color: colours.white,
    letterSpacing: -0.5,
    lineHeight: 26,
  },
  ctaShona: {
    fontSize: typography.caption,
    color: 'rgba(255,255,255,0.7)',
    marginTop: spacing.xs,
    fontStyle: 'italic',
  },

  secondRow: {
    flexDirection: 'row',
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    gap: spacing.md,
  },
});
