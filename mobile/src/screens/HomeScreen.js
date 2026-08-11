import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView, ScrollView, Alert, Linking } from 'react-native';
import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';
import StatCard from '../components/StatCard';
import SyncPill from '../components/SyncPill';
import SecondaryButton from '../components/SecondaryButton';
import MineSitePicker from '../components/MineSitePicker';
import { useOutreachSite } from '../context/OutreachSiteContext';
import { getDashboardToday } from '../services/api';

// The Intelligence Dashboard (dashboard/, 9-10 August) — a separate static
// web page, not part of this app, deployed to Render as a Static Site
// (dashboard/index.html + style.css + app.js, no build step). Opened in
// the phone's own browser, same one-tap pattern as every other secondary
// action here.
const DASHBOARD_URL = 'https://silicaguard-dashboard.onrender.com';

const EMPTY_TODAY = {
  screened_today: 0,
  todays_log: [],
  refer_now: { count: 0, items: [] },
  watch: { count: 0, items: [] },
  outreach_visits: [],
};

export default function HomeScreen({ navigation }) {
  const today = new Date().toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  // Which mine the VHW is at today — shared app-wide (10 August, previously
  // a hardcoded OUTREACH_SITE constant here). Real numbers below are
  // filtered by this; changing it re-fetches immediately.
  const { site, setSite, mine, setMine } = useOutreachSite();

  // Real numbers from GET /api/dashboard/today (7 August) — previously
  // hardcoded to zero. Re-fetched every time this screen gains focus (not
  // just on mount) AND whenever the selected site changes, so returning
  // here after a screening — or switching mines — shows the update without
  // needing a manual refresh. Fails silently to EMPTY_TODAY on any error
  // (offline, cold Render instance) — this data is never allowed to block
  // the primary "Screen New Miner" action.
  const [stats, setStats] = useState(EMPTY_TODAY);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      getDashboardToday(site)
        .then((data) => { if (!cancelled) setStats(data); })
        .catch(() => { if (!cancelled) setStats(EMPTY_TODAY); });
      return () => { cancelled = true; };
    }, [site])
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

  // No site param — Outreach Stats shows every scheduled visit across every
  // mine, not just wherever this Home screen is currently scoped to. Home's
  // own live numbers above stay scoped to the selected site (the VHW is
  // physically at one site during a visit); the stats screen is the
  // cross-site rollup a coordinator actually needs.
  const openOutreachStats = () => navigation.navigate('OutreachStats');

  const openDashboard = () => {
    Linking.openURL(DASHBOARD_URL).catch(() =>
      Alert.alert('Could not open Dashboard', 'Check your connection and try again.')
    );
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* Decorative blobs */}
      <View style={s.blob1} />
      <View style={s.blob2} />
      <View style={s.blob3} />

      {/* Whole body now scrolls (10 August) — was a fixed, non-scrolling
          layout, which left a large dead gap below the secondary-action
          row on anything taller than the shortest phones, and would have
          clipped content once the Outreach Planner preview below made the
          page taller than the screen on smaller devices. */}
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

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

      {/* ── OUTREACH BANNER — now a real mine picker (10 August), was
          hardcoded "Globe & Phoenix Mine" text with nothing behind it.
          Whole card is the tap target, reusing MineSitePicker's list/modal
          via renderTrigger so there's one single mines-picking
          implementation, not two. ── */}
      <MineSitePicker
        value={site}
        onChange={setSite}
        onSelectMine={setMine}
        renderTrigger={(open) => (
          <TouchableOpacity style={s.outreachBanner} onPress={open} activeOpacity={0.85}>
            <View style={s.outreachTop}>
              <Text style={s.eyebrow}>TODAY'S OUTREACH SITE</Text>
              <Text style={s.changeHint}>Change ▾</Text>
            </View>
            <Text style={s.outreachName}>{mine?.name || site}</Text>
            <View style={s.outreachTag}>
              <Text style={s.outreachTagText}>
                {mine?.district ? `${mine.district} District · ${mine.province}` : 'Tap to confirm today’s site'}
              </Text>
            </View>
          </TouchableOpacity>
        )}
      />

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
          "Today's Log" opens WorklistScreen (GET /api/dashboard/today).
          "Outreach Stats" now opens OutreachStatsScreen too (10 August) —
          the same endpoint gained an unauthenticated outreach_visits field,
          reusing the exact mapping GET /api/outreach uses for a logged-in
          coordinator, so this VHW-facing view can never disagree with it.
          "Settings" has nothing behind it yet — stays an honest
          "coming soon" (7 August fix; previously these three navigate()
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
          onPress={openOutreachStats}
        />
        <SecondaryButton
          icon="🖥️" label="Dashboard"
          colour={colours.mint}
          onPress={openDashboard}
        />
        <SecondaryButton
          icon="⚙️" label="Settings"
          colour={colours.muted}
          onPress={() => comingSoon('Settings')}
        />
      </View>

      {/* ── OUTREACH PLANNER preview (10 August) ──
          Same site-scoped outreach_visits GET /api/dashboard/today already
          returns for the stats above — no extra network call. Read-only:
          scheduling a visit is POST /api/outreach, which requires a
          dashboard login the VHW app deliberately doesn't have (same
          unauthenticated-by-design boundary as every other VHW-facing
          endpoint). "Manage" hands off to the web Dashboard, which does
          have the real schedule-a-visit form. */}
      <View style={s.plannerCard}>
        <View style={s.plannerHead}>
          <Text style={s.eyebrow}>OUTREACH PLANNER</Text>
          <TouchableOpacity onPress={openOutreachStats}>
            <Text style={s.plannerLink}>View all →</Text>
          </TouchableOpacity>
        </View>

        {stats.outreach_visits.length === 0 && (
          <Text style={s.plannerEmpty}>No visits scheduled for {mine?.name || site} yet.</Text>
        )}

        {stats.outreach_visits.slice(0, 3).map((v) => {
          const pct = v.expected_headcount > 0
            ? Math.min((v.screened_count / v.expected_headcount) * 100, 100)
            : 0;
          return (
            <View key={v.id} style={s.plannerRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.plannerDate}>{v.scheduled_date}</Text>
                <View style={s.plannerProgressTrack}>
                  <View style={[s.plannerProgressFill, { width: `${pct}%` }]} />
                </View>
                <Text style={s.plannerMeta}>{v.screened_count} / {v.expected_headcount} screened</Text>
              </View>
              <View style={[s.plannerBadge, v.report_generated ? s.plannerBadgeReady : s.plannerBadgePending]}>
                <Text style={[s.plannerBadgeText, { color: v.report_generated ? colours.mint : colours.watch }]}>
                  {v.report_generated ? 'Ready' : 'Pending'}
                </Text>
              </View>
            </View>
          );
        })}

        <TouchableOpacity style={s.plannerManageBtn} onPress={openDashboard} activeOpacity={0.85}>
          <Text style={s.plannerManageText}>Schedule a visit on the Dashboard →</Text>
        </TouchableOpacity>
      </View>

      </ScrollView>
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
  outreachTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  eyebrow: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
  },
  changeHint: {
    fontSize: typography.tiny,
    fontWeight: typography.semibold,
    color: colours.muted,
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

  scroll: { paddingBottom: spacing.xxl },

  plannerCard: {
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    backgroundColor: colours.card,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colours.purple,
    padding: spacing.lg,
  },
  plannerHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  plannerLink: {
    fontSize: typography.tiny,
    fontWeight: typography.bold,
    color: colours.purple,
  },
  plannerEmpty: {
    fontSize: typography.caption,
    color: colours.muted,
    paddingVertical: spacing.sm,
  },
  plannerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 0.5,
    borderTopColor: colours.mid,
  },
  plannerDate: {
    fontSize: typography.caption,
    fontWeight: typography.bold,
    color: colours.white,
  },
  plannerProgressTrack: {
    height: 5,
    backgroundColor: colours.mid,
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: spacing.xs,
  },
  plannerProgressFill: {
    height: '100%',
    backgroundColor: colours.mint,
    borderRadius: 999,
  },
  plannerMeta: {
    fontSize: typography.tiny,
    color: colours.muted,
    marginTop: spacing.xs,
  },
  plannerBadge: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  plannerBadgeReady: { backgroundColor: 'rgba(2,195,154,0.15)' },
  plannerBadgePending: { backgroundColor: 'rgba(255,184,0,0.15)' },
  plannerBadgeText: {
    fontSize: typography.micro,
    fontWeight: typography.black,
    textTransform: 'uppercase',
  },
  plannerManageBtn: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 0.5,
    borderTopColor: colours.mid,
  },
  plannerManageText: {
    fontSize: typography.tiny,
    color: colours.teal,
    fontWeight: typography.semibold,
    textAlign: 'center',
  },
});
