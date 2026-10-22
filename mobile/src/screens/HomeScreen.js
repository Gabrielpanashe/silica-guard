import {
  StyleSheet, Text, View, TouchableOpacity, ScrollView,
  Modal, TextInput, Alert, Linking, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { DatePicker, Toast } from '@ant-design/react-native';
import { light, ui, fonts, shadows, typography, spacing, radius } from '../theme';
import AppHeader from '../components/AppHeader';
import HeroSiteCard from '../components/HeroSiteCard';
import StatTile from '../components/StatTile';
import PrimaryActionCard from '../components/PrimaryActionCard';
import VisitRow from '../components/VisitRow';
import BottomNav from '../components/BottomNav';
import NotificationsSheet from '../components/NotificationsSheet';
import MineSitePicker from '../components/MineSitePicker';
import { useOutreachSite, localDateKey } from '../context/OutreachSiteContext';
import { getDashboardToday, getFacilities, createOutreachVisit } from '../services/api';
import { getPendingScreenings, syncPendingScreenings } from '../services/offlineQueue';
import { buildNotifications, getSeenIds, markSeen } from '../services/notificationsFeed';
import UsersIcon from '../../assets/icons/stat-users.svg';
import AlertIcon from '../../assets/icons/stat-alert.svg';
import EyeIcon from '../../assets/icons/stat-eye.svg';
import ViewAllArrow from '../../assets/icons/view-all-arrow.svg';
import SchedulePlus from '../../assets/icons/schedule-plus.svg';

// Redesigned 2 October 2026 to the Figma "SilicaGuard — Home Redesign"
// frame (branch fe/design-revamp). Every feature the previous Home had is
// still here — only restyled or moved:
//   - Today's Log / Outreach Stats / Dashboard / Settings buttons -> BottomNav
//   - LIVE/PENDING SyncPill -> AppHeader's status pill
//   - date in the header -> greeting block
//   - outreach banner + district/province -> HeroSiteCard
//   - pending-sync banner, Outreach Planner card and Schedule Visit sheet
//     stay, restyled
// Added: "Confirm today's site", today's-visit progress, a sync button,
// the notifications bell, pull-to-refresh, a real date picker in the
// Schedule Visit sheet, and toasts instead of blocking alerts.

// The Intelligence Dashboard (dashboard/, 9-10 August) — a separate static
// web page, not part of this app, deployed to Render as a Static Site.
// Opened in the phone's own browser.
const DASHBOARD_URL = 'https://silicaguard-dashboard.onrender.com';

const EMPTY_TODAY = {
  screened_today: 0,
  todays_log: [],
  refer_now: { count: 0, items: [] },
  watch: { count: 0, items: [] },
  outreach_visits: [],
};

const WEEKDAYS = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
  'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];

// Built by hand rather than toLocaleDateString — Hermes' Intl output varies
// by Android version, and the design wants one exact format.
function formatToday(d) {
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function greetingFor(d) {
  const h = d.getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function HomeScreen({ navigation }) {
  const now = new Date();

  // Which mine the VHW is at today — shared app-wide and persisted (see
  // OutreachSiteContext). Real numbers below are filtered by this;
  // changing it re-fetches immediately.
  const { site, setSite, mine, setMine, confirmSite, isConfirmedToday } = useOutreachSite();

  // Real numbers from GET /api/dashboard/today (7 August). Re-fetched every
  // time this screen gains focus AND whenever the selected site changes.
  // Fails silently to EMPTY_TODAY on any error (offline, cold Render
  // instance) — this data is never allowed to block "Screen new miner".
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
  // between screenings and after walking back into signal range. `syncing`
  // gates the sync button so a tap can't fire two attempts at once; a
  // successful sync also refreshes today's stats.
  const [pendingCount, setPendingCount] = useState(0);
  const [syncing, setSyncing] = useState(false);

  const attemptSync = useCallback(({ announce = false } = {}) => {
    setSyncing(true);
    return syncPendingScreenings()
      .then(({ synced, remaining }) => {
        setPendingCount(remaining);
        if (synced > 0) refreshStats();
        if (announce) {
          if (remaining === 0 && synced > 0) Toast.success(`${synced} screening${synced === 1 ? '' : 's'} synced`);
          else if (remaining === 0) Toast.info('Everything is synced');
          else Toast.offline(`${remaining} still waiting — will retry automatically`);
        }
      })
      .catch(() => { if (announce) Toast.offline('Couldn’t reach the server — will retry automatically'); })
      .finally(() => setSyncing(false));
  }, [refreshStats]);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      // Show whatever's queued immediately (cheap local read), then try to
      // actually sync it — so the count never flashes 0 before the real
      // number loads on a slow/offline connection.
      getPendingScreenings().then((q) => { if (!cancelled) setPendingCount(q.length); });
      attemptSync();
      return () => { cancelled = true; };
    }, [attemptSync])
  );

  // Pull-to-refresh — re-fetches today's numbers and retries the sync queue.
  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(() => {
    setRefreshing(true);
    Promise.all([refreshStats(), attemptSync()]).finally(() => setRefreshing(false));
  }, [refreshStats, attemptSync]);

  // Notifications bell — built on-device for now (services/notificationsFeed.js).
  const [notifOpen, setNotifOpen] = useState(false);
  const [seenIds, setSeenIds] = useState(new Set());
  useEffect(() => { getSeenIds().then(setSeenIds); }, []);

  const notifications = useMemo(
    () => buildNotifications({ stats, pendingCount }),
    [stats, pendingCount]
  );
  const unreadCount = notifications.filter((n) => !seenIds.has(n.id)).length;

  const openNotifications = () => {
    setNotifOpen(true);
    markSeen(notifications);
    setSeenIds(new Set(notifications.map((n) => n.id)));
  };

  const handleNotification = (item) => {
    setNotifOpen(false);
    if (item.action === 'refer_now') openWorklist('refer_now');
    else if (item.action === 'outreach') openOutreachStats();
    else if (item.action === 'sync') attemptSync({ announce: true });
  };

  // Today's visit at this site, if one is scheduled — drives the hero
  // card's "N miners planned" line and progress bar.
  const todayKey = localDateKey(now);
  const todaysVisit = stats.outreach_visits.find(
    (v) => v.scheduled_date === todayKey && v.site?.toLowerCase() === site.toLowerCase()
  ) || null;

  const handleConfirmSite = () => {
    confirmSite();
    Toast.success(`Today's site: ${mine?.name || site}`);
  };

  // Outreach Planner — schedule a visit inline from Home (12 August).
  // POST /api/outreach is unauthenticated specifically for this — see
  // routers/outreach.py for the tradeoff.
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
    setPlannerDate(localDateKey(new Date(Date.now() + 86400000)));
    setPlannerHeadcount('');
    setPlannerError(null);
    setPlannerOpen(true);
  };

  // Mirrors services/facility_matching.py's matching rule client-side —
  // district_hospital is always the fallback/RED match; a clinic matches
  // if its name contains the mine's first word (e.g. "Sherwood Mine" ->
  // "Sherwood Clinic"). Informational preview only, not stored on the
  // visit — the real match happens server-side per-referral at screening
  // time, same as it always has.
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
      setPlannerError('Pick a visit date.');
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
      Toast.success(`Visit scheduled: ${plannerSite.trim()} on ${plannerDate.trim()}`);
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

  // No site param — Outreach Stats shows every scheduled visit across every
  // mine; Home's own numbers stay scoped to the selected site.
  const openOutreachStats = () => navigation.navigate('OutreachStats');

  const openDashboard = () => {
    Linking.openURL(DASHBOARD_URL).catch(() =>
      Alert.alert('Could not open Dashboard', 'Check your connection and try again.')
    );
  };

  const onTab = (key) => {
    if (key === 'log') openWorklist('log');
    else if (key === 'stats') openOutreachStats();
    else if (key === 'dashboard') openDashboard();
    else if (key === 'settings') Toast.info('Settings is coming soon');
  };

  return (
    <SafeAreaView style={s.root} edges={['top', 'left', 'right']}>
      <StatusBar style="dark" />

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={ui.primary} colors={[ui.primary]} />}
      >
        {/* 22 August 2026 — the status pill used to be a hardcoded "LIVE".
            There's no real network check anywhere in this app (no NetInfo
            dependency) — pendingCount === 0 is the one honest signal: it
            only reaches 0 once syncPendingScreenings() has actually
            confirmed the backend is reachable. Known gap: a phone that's
            offline but has nothing queued yet still reads Live. */}
        <AppHeader
          live={pendingCount === 0}
          pendingCount={pendingCount}
          syncing={syncing}
          onSync={() => attemptSync({ announce: true })}
          unreadCount={unreadCount}
          onBell={openNotifications}
        />

        <View style={s.greeting}>
          <Text style={s.dateLine}>{formatToday(now)}</Text>
          <Text style={s.hello}>{greetingFor(now)}</Text>
        </View>

        {/* Pending sync banner (16 August) — screenings scored offline and
            waiting in services/offlineQueue.js. Retries automatically on
            every focus; the button is for a VHW who wants to force it
            right after regaining signal. */}
        {pendingCount > 0 && (
          <View style={s.syncBanner}>
            <View style={{ flex: 1 }}>
              <Text style={s.syncBannerTitle}>
                {pendingCount} screening{pendingCount === 1 ? '' : 's'} waiting to sync
              </Text>
              <Text style={s.syncBannerSub}>Scored offline — will submit automatically once connected.</Text>
            </View>
            <TouchableOpacity
              style={[s.syncRetryBtn, syncing && { opacity: 0.5 }]}
              onPress={() => attemptSync({ announce: true })}
              disabled={syncing}
              activeOpacity={0.8}
            >
              <Text style={s.syncRetryText}>{syncing ? 'Syncing…' : 'Retry now'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Hero — MineSitePicker supplies the list/modal/offline fallback
            through renderTrigger, so there's still one mine-picking
            implementation, not two. */}
        <MineSitePicker
          value={site}
          onChange={setSite}
          onSelectMine={setMine}
          renderTrigger={(open) => (
            <HeroSiteCard
              siteName={mine?.name || site}
              mine={mine}
              visit={todaysVisit}
              confirmed={isConfirmedToday}
              onConfirm={handleConfirmSite}
              onChange={open}
            />
          )}
        />

        {/* Stats — real numbers, tappable (7 August). */}
        <View style={s.statsRow}>
          <StatTile Icon={UsersIcon} value={stats.screened_today} label={'Screened\ntoday'} tone="primary" onPress={() => openWorklist('log')} />
          <StatTile Icon={AlertIcon} value={stats.refer_now.count} label={'Refer\nnow'} tone="refer" onPress={() => openWorklist('refer_now')} />
          <StatTile Icon={EyeIcon} value={stats.watch.count} label={'On\nwatch'} tone="watch" onPress={() => openWorklist('watch')} />
        </View>

        <PrimaryActionCard
          title="Screen new miner"
          subtitle="Tanga kuongorora mushandi"
          onPress={() => navigation.navigate('Intake')}
        />

        {/* Outreach Planner (10 August) — same site-scoped outreach_visits
            GET /api/dashboard/today already returns, no extra call. */}
        <View style={[s.plannerCard, shadows.card]}>
          <View style={s.plannerHead}>
            <Text style={s.plannerTitle}>Outreach planner</Text>
            <TouchableOpacity style={s.viewAll} onPress={openOutreachStats} hitSlop={8}>
              <Text style={s.viewAllText}>View all</Text>
              <ViewAllArrow />
            </TouchableOpacity>
          </View>

          {stats.outreach_visits.length === 0 && (
            <Text style={s.plannerEmpty}>No visits scheduled for {mine?.name || site} yet.</Text>
          )}

          {stats.outreach_visits.slice(0, 3).map((v) => <VisitRow key={v.id} visit={v} />)}

          <TouchableOpacity style={s.scheduleBtn} onPress={openPlanner} activeOpacity={0.85}>
            <SchedulePlus />
            <Text style={s.scheduleText}>Schedule a visit</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      <BottomNav active="home" onSelect={onTab} />

      <NotificationsSheet
        visible={notifOpen}
        items={notifications}
        onClose={() => setNotifOpen(false)}
        onAction={handleNotification}
      />

      {/* ── Schedule Visit modal ── */}
      <Modal visible={plannerOpen} animationType="slide" transparent onRequestClose={() => setPlannerOpen(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <ScrollView keyboardShouldPersistTaps="handled">
              <View style={s.modalHeader}>
                <Text style={s.modalTitle}>Schedule outreach visit</Text>
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

              {/* Location + nearest facility context — province/district
                  from the mines table via MineSitePicker's selection;
                  nearest hospital/clinic from GET /api/facilities, matched
                  client-side the same way the backend does at referral
                  time. */}
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

              {/* Was a free-text YYYY-MM-DD field — now Ant Design's
                  DatePicker, so a mistyped date can't happen. Past dates
                  are blocked (minDate = today). modalType="modal" matters:
                  Ant's default renders the popup through its root Portal,
                  which sits *under* this sheet's native Modal — the picker
                  would open invisibly behind it. */}
              <Text style={s.modalFieldLabel}>Visit date</Text>
              <DatePicker
                modalType="modal"
                value={plannerDate ? new Date(`${plannerDate}T00:00:00`) : undefined}
                minDate={new Date(new Date().setHours(0, 0, 0, 0))}
                maxDate={new Date(Date.now() + 365 * 86400000)}
                precision="day"
                title="Visit date"
                renderLabel={(type, n) => (type === 'month' ? MONTHS[n - 1].slice(0, 3) : String(n))}
                onOk={(d) => setPlannerDate(localDateKey(d))}
              >
                {({ toggle }) => (
                  <TouchableOpacity style={s.modalInput} onPress={toggle} activeOpacity={0.8}>
                    <Text style={{ fontSize: typography.body, color: plannerDate ? light.textDark : light.textMuted }}>
                      {plannerDate || 'Pick a date'}
                    </Text>
                  </TouchableOpacity>
                )}
              </DatePicker>

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
                  {plannerSubmitting ? 'Scheduling…' : 'Schedule visit'}
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
  root: { flex: 1, backgroundColor: ui.bg },
  scroll: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 24, gap: 20 },

  greeting: { gap: 4 },
  dateLine: { fontFamily: fonts.semibold, fontSize: 11, letterSpacing: 0.88, color: ui.muted },
  hello: { fontFamily: fonts.bold, fontSize: 26, letterSpacing: -0.52, color: ui.ink },

  syncBanner: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    backgroundColor: ui.watchSoft, borderRadius: 20,
    borderWidth: 1, borderColor: ui.watchBorder, padding: 14,
  },
  syncBannerTitle: { fontFamily: fonts.bold, fontSize: 13, color: ui.ink },
  syncBannerSub: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted, marginTop: 2 },
  syncRetryBtn: { backgroundColor: ui.watch, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
  syncRetryText: { fontFamily: fonts.bold, fontSize: 12, color: ui.surface },

  statsRow: { flexDirection: 'row', gap: 12 },

  plannerCard: {
    backgroundColor: ui.surface, borderWidth: 1, borderColor: ui.border,
    borderRadius: 24, padding: 20, gap: 16,
  },
  plannerHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  plannerTitle: { fontFamily: fonts.bold, fontSize: 17, letterSpacing: -0.17, color: ui.ink },
  viewAll: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  viewAllText: { fontFamily: fonts.semibold, fontSize: 13, color: ui.primary },
  plannerEmpty: { fontFamily: fonts.medium, fontSize: 13, color: ui.muted },
  scheduleBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: ui.dashedFill, borderWidth: 1.5, borderStyle: 'dashed', borderColor: ui.dashed,
    borderRadius: 14, paddingHorizontal: 16, paddingVertical: 13,
  },
  scheduleText: { fontFamily: fonts.bold, fontSize: 14, color: ui.primary },

  // ── Schedule Visit modal ── (not in the Figma frame; restyled to the
  // new palette, layout unchanged)
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: ui.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24,
    maxHeight: '88%', paddingHorizontal: spacing.xl, paddingTop: spacing.lg,
  },
  modalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.lg,
  },
  modalTitle: { fontFamily: fonts.bold, fontSize: 18, color: ui.ink },
  modalClose: { fontFamily: fonts.semibold, fontSize: 14, color: ui.primary },
  modalFieldLabel: {
    fontFamily: fonts.semibold, fontSize: 12, color: ui.muted,
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.xs, marginTop: spacing.md,
  },
  modalInput: {
    backgroundColor: ui.surface, borderRadius: radius.md, borderWidth: 1.5, borderColor: ui.border,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, fontSize: typography.body, color: ui.ink,
  },
  locationCard: {
    backgroundColor: ui.primarySoft, borderRadius: radius.md,
    padding: spacing.md, marginTop: spacing.md, gap: spacing.xs,
  },
  locationRow: { flexDirection: 'row', justifyContent: 'space-between' },
  locationLabel: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted },
  locationValue: { fontFamily: fonts.semibold, fontSize: 12, color: ui.ink, flexShrink: 1, textAlign: 'right' },
  plannerErrorText: { fontFamily: fonts.medium, fontSize: 12, color: ui.refer, marginTop: spacing.md, textAlign: 'center' },
  modalSubmitBtn: {
    backgroundColor: ui.primary, borderRadius: 16, paddingVertical: 15,
    alignItems: 'center', marginTop: spacing.lg,
  },
  modalSubmitText: { fontFamily: fonts.bold, fontSize: 15, color: ui.surface },
  plannerManageText: { fontFamily: fonts.semibold, fontSize: 12, color: ui.primary, textAlign: 'center' },
});
