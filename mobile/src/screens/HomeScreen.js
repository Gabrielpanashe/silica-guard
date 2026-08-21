import {
  StyleSheet, Text, View, TouchableOpacity, ScrollView,
  Modal, TextInput, Alert, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useCallback, useEffect, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { colours, light, typography, spacing, radius } from '../theme';
import StatCard from '../components/StatCard';
import SyncPill from '../components/SyncPill';
import SecondaryButton from '../components/SecondaryButton';
import MineSitePicker from '../components/MineSitePicker';
import { useOutreachSite } from '../context/OutreachSiteContext';
import { getDashboardToday, getFacilities, createOutreachVisit } from '../services/api';
import { getPendingScreenings, syncPendingScreenings } from '../services/offlineQueue';

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

  const refreshStats = useCallback(() => {
    return getDashboardToday(site)
      .then((data) => setStats(data))
      .catch(() => setStats(EMPTY_TODAY));
  }, [site]);

  // Offline screening sync (16 August) — see services/offlineQueue.js.
  // Home is the natural place to retry: it's the screen the VHW lands on
  // between screenings and after walking back into signal range, and it
  // already re-fetches on every focus. `syncing` gates the banner's retry
  // button so a tap can't fire two attempts at once; a successful sync
  // also refreshes today's stats, since a newly-synced screening should
  // show up in Screened Today / Refer Now immediately, not after a manual
  // pull-to-refresh.
  const [pendingCount, setPendingCount] = useState(0);
  const [syncing, setSyncing] = useState(false);

  const attemptSync = useCallback(() => {
    setSyncing(true);
    return syncPendingScreenings()
      .then(({ synced, remaining }) => {
        setPendingCount(remaining);
        if (synced > 0) refreshStats();
      })
      .catch(() => {})
      .finally(() => setSyncing(false));
  }, [refreshStats]);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      // Show whatever's queued immediately (cheap local read), then try
      // to actually sync it — so the banner never flashes "0 pending"
      // before the real count loads on a slow/offline connection.
      getPendingScreenings().then((q) => { if (!cancelled) setPendingCount(q.length); });
      attemptSync();
      return () => { cancelled = true; };
    }, [attemptSync])
  );

  // Outreach Planner — schedule a visit inline from Home (12 August).
  // POST /api/outreach is unauthenticated as of today specifically for
  // this — see routers/outreach.py for the tradeoff.
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [plannerSite, setPlannerSite] = useState(site);
  const [plannerMine, setPlannerMine] = useState(mine);
  const [plannerDate, setPlannerDate] = useState('');
  const [plannerHeadcount, setPlannerHeadcount] = useState('');
  const [plannerSubmitting, setPlannerSubmitting] = useState(false);
  const [plannerError, setPlannerError] = useState(null);
  const [facilities, setFacilities] = useState([]);

  useEffect(() => {
    getFacilities().then(setFacilities).catch(() => setFacilities([]));
  }, []);

  const openPlanner = () => {
    setPlannerSite(site);
    setPlannerMine(mine);
    setPlannerDate(new Date(Date.now() + 86400000).toISOString().slice(0, 10));
    setPlannerHeadcount('');
    setPlannerError(null);
    setPlannerOpen(true);
  };

  // Mirrors services/facility_matching.py's matching rule client-side —
  // district_hospital is always the fallback/RED match; a clinic matches
  // if its name contains the mine's first word (e.g. "Sherwood Mine" ->
  // "Sherwood Clinic"). Informational preview only, not stored on the
  // visit — the real match happens server-side per-referral at
  // screening time, same as it always has.
  const nearestHospital = facilities.find((f) => f.level === 'district_hospital');
  const nearestClinic = plannerMine
    ? facilities.find(
        (f) => f.level === 'clinic' &&
          f.name.toLowerCase().includes(plannerMine.name.split(' ')[0].toLowerCase())
      )
    : null;

  const submitPlanner = async () => {
    setPlannerError(null);
    const headcount = parseInt(plannerHeadcount, 10);
    if (!plannerSite.trim() || !plannerDate.trim() || !headcount || headcount < 1) {
      setPlannerError('Fill in site, date and expected headcount.');
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(plannerDate.trim())) {
      setPlannerError('Date must be in YYYY-MM-DD format, e.g. 2026-08-20.');
      return;
    }
    setPlannerSubmitting(true);
    try {
      await createOutreachVisit({
        site: plannerSite.trim(),
        scheduled_date: plannerDate.trim(),
        expected_headcount: headcount,
      });
      setPlannerOpen(false);
      await refreshStats();
      Alert.alert('Visit scheduled', `${plannerSite.trim()} on ${plannerDate.trim()}.`);
    } catch (e) {
      setPlannerError(e.message || 'Failed to schedule visit.');
    } finally {
      setPlannerSubmitting(false);
    }
  };

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
      <StatusBar style="dark" />

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

      {/* ── PENDING SYNC BANNER (16 August) ── one or more screenings were
          scored offline (backend/AI unreachable at the time) and are
          waiting in services/offlineQueue.js to be resubmitted. Retries
          automatically on every focus; the button here is just for a VHW
          who wants to force it right after regaining signal rather than
          waiting to navigate away and back. */}
      {pendingCount > 0 && (
        <View style={s.syncBanner}>
          <View style={{ flex: 1 }}>
            <Text style={s.syncBannerTitle}>
              ⏳ {pendingCount} screening{pendingCount === 1 ? '' : 's'} waiting to sync
            </Text>
            <Text style={s.syncBannerSub}>Scored offline — will submit automatically once connected.</Text>
          </View>
          <TouchableOpacity
            style={[s.syncRetryBtn, syncing && { opacity: 0.5 }]}
            onPress={attemptSync}
            disabled={syncing}
            activeOpacity={0.8}
          >
            <Text style={s.syncRetryText}>{syncing ? 'Syncing…' : 'Retry now'}</Text>
          </TouchableOpacity>
        </View>
      )}

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
          colour={light.accentEnd}
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
          colour={light.accentStart}
          onPress={() => openWorklist('log')}
        />
        <SecondaryButton
          icon="📊" label={'Outreach\nStats'}
          colour={colours.purple}
          onPress={openOutreachStats}
        />
        <SecondaryButton
          icon="🖥️" label="Dashboard"
          colour={light.accentEnd}
          onPress={openDashboard}
        />
        <SecondaryButton
          icon="⚙️" label="Settings"
          colour={light.textMuted}
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

        <TouchableOpacity style={s.plannerScheduleBtn} onPress={openPlanner} activeOpacity={0.85}>
          <Text style={s.plannerScheduleText}>+ Schedule a visit</Text>
        </TouchableOpacity>
      </View>

      </ScrollView>

      {/* ── Schedule Visit modal ── */}
      <Modal visible={plannerOpen} animationType="slide" transparent onRequestClose={() => setPlannerOpen(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <ScrollView keyboardShouldPersistTaps="handled">
              <View style={s.modalHeader}>
                <Text style={s.modalTitle}>Schedule Outreach Visit</Text>
                <TouchableOpacity onPress={() => setPlannerOpen(false)}>
                  <Text style={s.modalClose}>Done</Text>
                </TouchableOpacity>
              </View>

              <Text style={s.modalFieldLabel}>Mine</Text>
              <MineSitePicker
                value={plannerSite}
                onChange={setPlannerSite}
                onSelectMine={setPlannerMine}
              />

              {/* Location + nearest facility context — province, district,
                  town come from the mines table via MineSitePicker's
                  selection; nearest hospital/clinic from GET /api/facilities,
                  matched client-side the same way the backend does at
                  referral time. */}
              {plannerMine && (
                <View style={s.locationCard}>
                  <View style={s.locationRow}>
                    <Text style={s.locationLabel}>District</Text>
                    <Text style={s.locationValue}>{plannerMine.district || '—'}</Text>
                  </View>
                  <View style={s.locationRow}>
                    <Text style={s.locationLabel}>Province</Text>
                    <Text style={s.locationValue}>{plannerMine.province || '—'}</Text>
                  </View>
                  <View style={s.locationRow}>
                    <Text style={s.locationLabel}>Nearest hospital</Text>
                    <Text style={s.locationValue}>{nearestHospital?.name || 'Not on file'}</Text>
                  </View>
                  {nearestClinic && (
                    <View style={s.locationRow}>
                      <Text style={s.locationLabel}>Nearest clinic</Text>
                      <Text style={s.locationValue}>{nearestClinic.name}</Text>
                    </View>
                  )}
                </View>
              )}

              <Text style={s.modalFieldLabel}>Visit date</Text>
              <TextInput
                style={s.modalInput}
                value={plannerDate}
                onChangeText={setPlannerDate}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={light.textMuted}
              />

              <Text style={s.modalFieldLabel}>Expected miners</Text>
              <TextInput
                style={s.modalInput}
                value={plannerHeadcount}
                onChangeText={setPlannerHeadcount}
                placeholder="e.g. 40"
                placeholderTextColor={light.textMuted}
                keyboardType="number-pad"
              />

              {plannerError && <Text style={s.plannerErrorText}>{plannerError}</Text>}

              <TouchableOpacity
                style={[s.modalSubmitBtn, plannerSubmitting && { opacity: 0.6 }]}
                onPress={submitPlanner}
                disabled={plannerSubmitting}
                activeOpacity={0.85}
              >
                <Text style={s.modalSubmitText}>
                  {plannerSubmitting ? 'Scheduling…' : 'Schedule Visit'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity onPress={openDashboard} style={{ marginTop: spacing.md }}>
                <Text style={s.plannerManageText}>Manage all visits on the Dashboard →</Text>
              </TouchableOpacity>

              <View style={{ height: spacing.xxl }} />
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: light.bg,
    overflow: 'hidden',
  },
  blob1: {
    position: 'absolute', top: -80, right: -80,
    width: 220, height: 220, borderRadius: 110,
    backgroundColor: light.accentStart, opacity: 0.14,
  },
  blob2: {
    position: 'absolute', top: 160, left: -60,
    width: 160, height: 160, borderRadius: 80,
    backgroundColor: colours.purple, opacity: 0.12,
  },
  blob3: {
    position: 'absolute', bottom: 80, right: -40,
    width: 130, height: 130, borderRadius: 65,
    backgroundColor: light.accentEnd, opacity: 0.14,
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
    color: light.textMuted,
    letterSpacing: 4,
  },
  brandAccent: {
    fontSize: typography.hero,
    fontWeight: typography.black,
    color: light.textDark,
    lineHeight: 36,
    letterSpacing: -1,
  },
  brandDot: { color: light.accentEnd, fontSize: 28 },
  headerRight: { alignItems: 'flex-end', paddingTop: 4, gap: spacing.xs },
  dateText: { fontSize: typography.tiny, color: light.textMuted, textAlign: 'right' },

  syncBanner: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    marginHorizontal: spacing.xl, marginTop: spacing.md,
    backgroundColor: 'rgba(255,184,0,0.12)', borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.watch,
    padding: spacing.md,
  },
  syncBannerTitle: { fontSize: typography.caption, fontWeight: typography.bold, color: light.textDark },
  syncBannerSub: { fontSize: typography.tiny, color: light.textMuted, marginTop: 2 },
  syncRetryBtn: {
    backgroundColor: colours.watch, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
  },
  syncRetryText: { fontSize: typography.tiny, fontWeight: typography.black, color: light.textDark },

  outreachBanner: {
    marginHorizontal: spacing.xl,
    marginTop: spacing.md,
    backgroundColor: light.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1.5,
    borderColor: light.accentStart,
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
    color: light.accentStart,
    letterSpacing: 2,
  },
  changeHint: {
    fontSize: typography.tiny,
    fontWeight: typography.semibold,
    color: light.textMuted,
  },
  outreachName: {
    fontSize: 30,
    fontWeight: typography.black,
    color: light.textDark,
    lineHeight: 32,
    letterSpacing: -0.5,
  },
  outreachTag: {
    marginTop: spacing.md,
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(11,61,145,0.10)',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  outreachTagText: {
    fontSize: typography.caption,
    color: light.accentStart,
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
    backgroundColor: light.accentStart,
    borderRadius: radius.lg,
    padding: spacing.xl + 2,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    borderWidth: 2,
    borderColor: light.accentEnd,
    zIndex: 2,
  },
  ctaShadow: {
    position: 'absolute',
    bottom: -5, right: -5, left: 5,
    height: '100%',
    borderRadius: radius.lg,
    backgroundColor: light.accentEnd,
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
    backgroundColor: light.surface,
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
    color: light.textMuted,
    paddingVertical: spacing.sm,
  },
  plannerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 0.5,
    borderTopColor: light.border,
  },
  plannerDate: {
    fontSize: typography.caption,
    fontWeight: typography.bold,
    color: light.textDark,
  },
  plannerProgressTrack: {
    height: 5,
    backgroundColor: light.border,
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: spacing.xs,
  },
  plannerProgressFill: {
    height: '100%',
    backgroundColor: light.accentEnd,
    borderRadius: 999,
  },
  plannerMeta: {
    fontSize: typography.tiny,
    color: light.textMuted,
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
  plannerManageText: {
    fontSize: typography.tiny,
    color: light.accentStart,
    fontWeight: typography.semibold,
    textAlign: 'center',
  },
  plannerScheduleBtn: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 0.5,
    borderTopColor: light.border,
    alignItems: 'center',
  },
  plannerScheduleText: {
    fontSize: typography.caption,
    color: colours.purple,
    fontWeight: typography.bold,
  },

  // ── Schedule Visit modal ──
  // Overlay scrim stays a dark dim regardless of page theme — standard
  // practice for a bottom sheet.
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: light.bg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl,
    maxHeight: '88%', paddingHorizontal: spacing.xl, paddingTop: spacing.lg,
    borderWidth: 1, borderColor: light.border, borderBottomWidth: 0,
  },
  modalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.lg,
  },
  modalTitle: { fontSize: typography.subtitle, fontWeight: typography.black, color: light.textDark },
  modalClose: { fontSize: typography.body, color: light.accentStart, fontWeight: typography.semibold },
  modalFieldLabel: {
    fontSize: typography.caption, color: light.textMuted, fontWeight: typography.semibold,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.xs, marginTop: spacing.md,
  },
  modalInput: {
    backgroundColor: light.surface, borderRadius: radius.md, borderWidth: 1.5, borderColor: light.border,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, fontSize: typography.body, color: light.textDark,
  },
  locationCard: {
    backgroundColor: light.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: light.border,
    padding: spacing.md, marginTop: spacing.md, gap: spacing.xs,
  },
  locationRow: { flexDirection: 'row', justifyContent: 'space-between' },
  locationLabel: { fontSize: typography.tiny, color: light.textMuted },
  locationValue: { fontSize: typography.tiny, color: light.textDark, fontWeight: typography.semibold, flexShrink: 1, textAlign: 'right' },
  plannerErrorText: {
    fontSize: typography.caption, color: colours.refer, marginTop: spacing.md, textAlign: 'center',
  },
  modalSubmitBtn: {
    backgroundColor: colours.purple, borderRadius: radius.md, paddingVertical: spacing.md,
    alignItems: 'center', marginTop: spacing.lg, borderWidth: 1.5, borderColor: colours.purple,
  },
  modalSubmitText: { fontSize: typography.body, fontWeight: typography.black, color: colours.white },
});
