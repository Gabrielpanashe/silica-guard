import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';
import StatCard from '../components/StatCard';
import SyncPill from '../components/SyncPill';
import SecondaryButton from '../components/SecondaryButton';

export default function HomeScreen({ navigation }) {
  const today = new Date().toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  // Mock session stats — will come from local DB / API later
  const stats = { screened: 0, refer: 0, watch: 0 };

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

      {/* ── STATS ── */}
      <View style={s.statsRow}>
        <StatCard value={stats.screened} label="Screened Today" colour={colours.mint} large />
        <View style={s.statCol}>
          <StatCard value={stats.refer} label="Refer Now" colour={colours.refer} />
          <StatCard value={stats.watch} label="Watch" colour={colours.watch} />
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

      {/* ── SECONDARY ACTIONS ── */}
      <View style={s.secondRow}>
        <SecondaryButton
          icon="📋" label={'Today\'s\nLog'}
          colour={colours.teal}
          onPress={() => navigation.navigate('Log')}
        />
        <SecondaryButton
          icon="📊" label={'Outreach\nStats'}
          colour={colours.purple}
          onPress={() => navigation.navigate('Stats')}
        />
        <SecondaryButton
          icon="⚙️" label="Settings"
          colour={colours.muted}
          onPress={() => navigation.navigate('Settings')}
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
