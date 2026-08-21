import { StyleSheet, Text, View, TouchableOpacity, ImageBackground } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { light, colours, typography, spacing, radius } from '../theme';

// Same key App.js checks at boot to decide whether Landing is the initial
// route at all — writing it here is what makes this a true first-run
// screen instead of a splash on every open (16 August).
const SEEN_LANDING_KEY = 'sg_has_seen_landing';

// First screen for the redesign (16 August) — Cimas-blue accent (see
// theme/index.js's `light.accentStart`/`accentEnd`), everything past
// "Get Started" is still the existing dark screens. Only this screen is
// wired to the `light` tokens for now; migrate the rest one at a time
// rather than flipping the whole app in one pass.
//
// Background is a real photo now (assets/landing-page.jpg, a real
// silicosis-screening outreach scene — added to the repo directly, since
// there's no image-generation tool in this environment to produce one).
// Replaces the earlier hand-drawn SVG hero entirely — a real photo of the
// actual thing SilicaGuard does is stronger than an illustration of it.
// ~3.5MB at 2816×1536; bundled fine for a demo, worth a resize pass later
// if app binary size becomes a concern.
const BG_IMAGE = require('../../assets/landing-page.jpg');

const FEATURES = [
  { icon: 'cloud-offline-outline', lib: 'ion', label: 'Works offline' },
  { icon: 'timer-outline', lib: 'ion', label: '10-min screening' },
  { icon: 'translate', lib: 'mci', label: 'English & Shona' },
];

function FeatureIcon({ lib, icon, size, color }) {
  const Icon = lib === 'mci' ? MaterialCommunityIcons : Ionicons;
  return <Icon name={icon} size={size} color={color} />;
}

export default function LandingScreen({ navigation }) {
  // Never lets a storage failure block navigation — worst case this
  // screen just shows again next launch, which is a mild annoyance, not
  // a broken app.
  const handleGetStarted = () => {
    AsyncStorage.setItem(SEEN_LANDING_KEY, 'true').catch(() => {});
    navigation.replace('Home');
  };

  return (
    <ImageBackground source={BG_IMAGE} resizeMode="cover" style={s.root}>
      <StatusBar style="light" />

      {/* Scrim — nearly transparent near the top (the photo itself is the
          hero) deepening to a solid navy where the copy/CTA sit, so white
          text stays legible over a busy photo without hiding it. */}
      <LinearGradient
        colors={['rgba(8,16,32,0.05)', 'rgba(8,16,32,0.45)', 'rgba(6,13,28,0.94)']}
        locations={[0, 0.5, 0.82]}
        style={StyleSheet.absoluteFill}
      />

      <SafeAreaView style={s.safe}>
        <View style={s.spacer} />

        {/* ── COPY ── */}
        <View style={s.body}>
          <Text style={s.eyebrow}>SILICOSIS SCREENING</Text>
          <Text style={s.title}>SilicaGuard</Text>
          <Text style={s.subtitle}>
            Catching lung disease early, one mine site at a time.
          </Text>
          <Text style={s.subtitleShona}>Kuchengetedza mapapu emabasa evanhu vanoshanda migodhi.</Text>

          <View style={s.featureRow}>
            {FEATURES.map((f) => (
              <View key={f.label} style={s.featureChip}>
                <FeatureIcon lib={f.lib} icon={f.icon} size={16} color={light.accentEnd} />
                <Text style={s.featureLabel}>{f.label}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── CTA ── */}
        <View style={s.footer}>
          <TouchableOpacity
            activeOpacity={0.88}
            onPress={handleGetStarted}
            style={s.ctaShadow}
          >
            <LinearGradient
              colors={[light.accentStart, light.accentEnd]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={s.cta}
            >
              <Text style={s.ctaText}>Get Started</Text>
              <Ionicons name="arrow-forward" size={18} color={colours.white} />
            </LinearGradient>
          </TouchableOpacity>
          <Text style={s.footerNote}>For health workers screening artisanal miners</Text>
        </View>
      </SafeAreaView>
    </ImageBackground>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: light.textDark },
  safe: { flex: 1 },
  spacer: { flex: 1 },

  body: { paddingHorizontal: spacing.xxl, alignItems: 'center' },
  eyebrow: {
    fontSize: typography.micro, fontWeight: typography.black,
    color: light.accentEnd, letterSpacing: 2, marginBottom: spacing.sm,
  },
  title: {
    fontSize: 38, fontWeight: typography.black,
    color: colours.white, letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: typography.subtitle, fontWeight: typography.medium,
    color: 'rgba(255,255,255,0.92)', textAlign: 'center',
    marginTop: spacing.md, lineHeight: 24,
  },
  subtitleShona: {
    fontSize: typography.caption, fontStyle: 'italic',
    color: 'rgba(255,255,255,0.65)', textAlign: 'center', marginTop: spacing.xs,
  },

  featureRow: {
    flexDirection: 'row', gap: spacing.sm,
    marginTop: spacing.xl, flexWrap: 'wrap', justifyContent: 'center',
  },
  featureChip: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: radius.pill,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)',
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
  },
  featureLabel: { fontSize: typography.caption, fontWeight: typography.semibold, color: colours.white },

  footer: { paddingHorizontal: spacing.xxl, paddingBottom: spacing.xl, paddingTop: spacing.xxl, alignItems: 'center' },
  ctaShadow: {
    width: '100%',
    shadowColor: light.accentStart, shadowOpacity: 0.5, shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 }, elevation: 6,
  },
  cta: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm,
    borderRadius: radius.pill, paddingVertical: spacing.lg,
  },
  ctaText: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  footerNote: { fontSize: typography.tiny, color: 'rgba(255,255,255,0.6)', marginTop: spacing.md, textAlign: 'center' },
});
