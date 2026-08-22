import {
  StyleSheet, Text, View, TextInput,
  TouchableOpacity, ScrollView,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, light, typography, spacing, radius } from '../theme';
import MineSitePicker from '../components/MineSitePicker';
import { useOutreachSite } from '../context/OutreachSiteContext';

export default function IntakeScreen({ navigation }) {
  // Defaults to whichever mine is selected on Home (10 August) — was
  // hardcoded to 'Globe & Phoenix Mine' regardless of Home's own state,
  // which is exactly what let a screening get registered under a site
  // Home's live numbers weren't filtering by, so it silently never showed
  // up in Screened Today / Today's Log / Refer Now / Watch. Still a real,
  // independent MineSitePicker below — a VHW covering more than one site
  // in a day can still override per-miner.
  const { site: defaultSite } = useOutreachSite();
  const [name, setName]         = useState('');
  const [phone, setPhone]       = useState('');
  const [mineSite, setMineSite] = useState(defaultSite);
  const [errors, setErrors]     = useState({});

  const validate = () => {
    const e = {};
    if (!name.trim())  e.name  = 'Full name is required';
    if (!phone.trim()) e.phone = 'Phone number is required';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleNext = () => {
    if (!validate()) return;
    navigation.navigate('Question', {
      miner: {
        name:      name.trim(),
        phone:     phone.trim(),
        mine_site: mineSite.trim(),
      },
    });
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="dark" />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={s.backBtn}>
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={s.headerText}>
          <Text style={s.headerTitle}>New Screening</Text>
          <Text style={s.headerShona}>Kuongorora Mushandi Mutsva</Text>
        </View>
        <View style={s.stepBadge}>
          <Text style={s.stepText}>Step 1 of 2</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={s.sectionLabel}>MINER IDENTITY</Text>
          <Text style={s.sectionHint}>
            Job role and exposure history will be asked as part of the screening questions.
          </Text>

          {/* Name */}
          <View style={s.field}>
            <Text style={s.fieldLabel}>Full Name <Text style={s.required}>*</Text></Text>
            <TextInput
              style={[s.input, errors.name && s.inputError]}
              placeholder="e.g. Tendai Moyo"
              placeholderTextColor={light.textMuted}
              value={name}
              onChangeText={t => { setName(t); setErrors(e => ({ ...e, name: null })); }}
              autoCapitalize="words"
            />
            {errors.name && <Text style={s.errorText}>{errors.name}</Text>}
          </View>

          {/* Phone */}
          <View style={s.field}>
            <Text style={s.fieldLabel}>Phone Number <Text style={s.required}>*</Text></Text>
            <TextInput
              style={[s.input, errors.phone && s.inputError]}
              placeholder="+263771234567"
              placeholderTextColor={light.textMuted}
              value={phone}
              onChangeText={t => { setPhone(t); setErrors(e => ({ ...e, phone: null })); }}
              keyboardType="phone-pad"
            />
            {errors.phone && <Text style={s.errorText}>{errors.phone}</Text>}
            <Text style={s.fieldHint}>
              Phone number is the miner's permanent ID — used to link all future screenings
            </Text>
          </View>

          {/* Mine Site */}
          <View style={s.field}>
            <Text style={s.fieldLabel}>Mine Site</Text>
            <MineSitePicker value={mineSite} onChange={setMineSite} />
          </View>

          {/* Info card */}
          <View style={s.infoCard}>
            <Text style={s.infoIcon}>ℹ️</Text>
            <Text style={s.infoText}>
              The next step is 10 clinical questions. They take about 5 minutes.
              Read each question aloud to the miner — they do not need to touch the screen.
            </Text>
          </View>

          {/* CTA */}
          <TouchableOpacity style={s.nextBtn} onPress={handleNext} activeOpacity={0.88}>
            <View style={s.nextInner}>
              <Text style={s.nextText}>START SCREENING QUESTIONS</Text>
              <Text style={s.nextShona}>Tanga Mibvunzo Yechipatara →</Text>
            </View>
            <View style={s.nextShadow} />
          </TouchableOpacity>

          <View style={{ height: spacing.xxl }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: light.bg },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
    borderBottomWidth: 0.5, borderBottomColor: light.border, gap: spacing.md,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.sm,
    backgroundColor: light.surface, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: light.accentStart,
  },
  backArrow: { fontSize: 18, color: light.accentStart },
  headerText: { flex: 1 },
  headerTitle: { fontSize: typography.subtitle, fontWeight: typography.bold, color: light.textDark },
  headerShona: { fontSize: typography.micro, color: light.textMuted, fontStyle: 'italic', marginTop: 1 },
  stepBadge: {
    backgroundColor: 'rgba(47,127,239,0.12)', borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: light.accentStart,
  },
  stepText: { fontSize: typography.tiny, color: light.accentStart, fontWeight: typography.bold },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  sectionLabel: {
    fontSize: typography.micro, fontWeight: typography.bold,
    color: light.accentStart, letterSpacing: 2, marginBottom: spacing.sm,
  },
  sectionHint: {
    fontSize: typography.caption, color: light.textMuted,
    marginBottom: spacing.xl, lineHeight: 18,
  },
  field: { marginBottom: spacing.lg },
  fieldLabel: {
    fontSize: typography.caption, color: light.textMuted,
    fontWeight: typography.semibold, marginBottom: spacing.xs,
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  // Was `colours.red`, a key that doesn't exist in theme/index.js (only
  // `colours.refer`) — fixed while converting this screen's colours.
  required: { color: colours.refer },
  input: {
    backgroundColor: light.surface, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: light.border,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    fontSize: typography.body, color: light.textDark,
  },
  inputError: { borderColor: colours.refer },
  errorText: { fontSize: typography.tiny, color: colours.refer, marginTop: spacing.xs, fontWeight: typography.semibold },
  fieldHint: { fontSize: typography.tiny, color: light.textMuted, marginTop: spacing.xs, lineHeight: 16 },
  infoCard: {
    flexDirection: 'row', gap: spacing.md,
    backgroundColor: light.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: light.accentStart,
    padding: spacing.lg, marginBottom: spacing.xl,
    borderLeftWidth: 4,
  },
  infoIcon: { fontSize: 18 },
  infoText: { flex: 1, fontSize: typography.caption, color: light.textBody, lineHeight: 18 },
  nextBtn: { marginTop: spacing.sm },
  nextInner: {
    backgroundColor: light.accentStart, borderRadius: radius.lg,
    padding: spacing.xl, alignItems: 'center',
    borderWidth: 2, borderColor: light.accentEnd, zIndex: 2,
  },
  nextShadow: {
    position: 'absolute', bottom: -5, right: -5, left: 5,
    height: '100%', borderRadius: radius.lg,
    backgroundColor: light.accentEnd, zIndex: 1, opacity: 0.3,
  },
  nextText: { fontSize: typography.body, fontWeight: typography.black, color: colours.white, letterSpacing: 0.5 },
  nextShona: { fontSize: typography.caption, color: 'rgba(255,255,255,0.7)', marginTop: spacing.xs, fontStyle: 'italic' },
});
