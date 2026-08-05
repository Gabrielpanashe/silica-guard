import {
  StyleSheet, Text, View, TextInput,
  TouchableOpacity, SafeAreaView, ScrollView,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';

// ── JOB ROLES ─────────────────────────────────────────────────
const JOB_ROLES = [
  { code: 'drilling',   label: 'Driller',         shona: 'Mudhiriyi',       risk: 4 },
  { code: 'crushing',   label: 'Ore Crusher',      shona: 'Mucrusher',       risk: 4 },
  { code: 'blasting',   label: 'Blaster',          shona: 'Mublaster',       risk: 3 },
  { code: 'hauling',    label: 'Hauler / Tramming', shona: 'Muhauleri',      risk: 2 },
  { code: 'processing', label: 'Processing Plant',  shona: 'Muprosessing',   risk: 3 },
  { code: 'surface',    label: 'Surface Worker',    shona: 'Mushandi Wepasi', risk: 1 },
  { code: 'other',      label: 'Other / Unknown',   shona: 'Zvimwe',         risk: 1 },
];

// ── YEARS RANGES ──────────────────────────────────────────────
const YEARS_OPTIONS = [
  { code: 'under_1',  label: 'Less than 1 year', score: 1 },
  { code: '1_to_3',   label: '1 – 3 years',      score: 2 },
  { code: '3_to_5',   label: '3 – 5 years',      score: 3 },
  { code: '5_to_10',  label: '5 – 10 years',     score: 4 },
  { code: 'over_10',  label: 'Over 10 years',    score: 5 },
];

export default function IntakeScreen({ navigation }) {
  const [name, setName]           = useState('');
  const [phone, setPhone]         = useState('');
  const [mineSite, setMineSite]   = useState('Globe & Phoenix Mine');
  const [jobRole, setJobRole]     = useState(null);
  const [yearsCode, setYearsCode] = useState(null);
  const [errors, setErrors]       = useState({});

  const validate = () => {
    const e = {};
    if (!name.trim())    e.name    = 'Full name is required';
    if (!phone.trim())   e.phone   = 'Phone number is required';
    if (!jobRole)        e.jobRole = 'Select a job role';
    if (!yearsCode)      e.years   = 'Select years underground';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleNext = () => {
    if (!validate()) return;
    const selectedRole  = JOB_ROLES.find(r => r.code === jobRole);
    const selectedYears = YEARS_OPTIONS.find(y => y.code === yearsCode);

    navigation.navigate('Question', {
      miner: {
        name:      name.trim(),
        phone:     phone.trim(),
        mine_site: mineSite.trim(),
        job_role:  jobRole,
        job_label: selectedRole.label,
        job_risk:  selectedRole.risk,
        years_code:  yearsCode,
        years_label: selectedYears.label,
        years_score: selectedYears.score,
      },
    });
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

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
          <Text style={s.stepText}>1 of 3</Text>
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

          {/* ── SECTION: IDENTITY ── */}
          <Text style={s.sectionLabel}>MINER IDENTITY</Text>

          <View style={s.field}>
            <Text style={s.fieldLabel}>Full Name <Text style={s.required}>*</Text></Text>
            <TextInput
              style={[s.input, errors.name && s.inputError]}
              placeholder="e.g. Tendai Moyo"
              placeholderTextColor={colours.muted}
              value={name}
              onChangeText={t => { setName(t); setErrors(e => ({ ...e, name: null })); }}
              autoCapitalize="words"
            />
            {errors.name && <Text style={s.errorText}>{errors.name}</Text>}
          </View>

          <View style={s.field}>
            <Text style={s.fieldLabel}>Phone Number <Text style={s.required}>*</Text></Text>
            <TextInput
              style={[s.input, errors.phone && s.inputError]}
              placeholder="+263771234567"
              placeholderTextColor={colours.muted}
              value={phone}
              onChangeText={t => { setPhone(t); setErrors(e => ({ ...e, phone: null })); }}
              keyboardType="phone-pad"
            />
            {errors.phone && <Text style={s.errorText}>{errors.phone}</Text>}
            <Text style={s.fieldHint}>Phone is the miner's permanent ID in the system</Text>
          </View>

          <View style={s.field}>
            <Text style={s.fieldLabel}>Mine Site</Text>
            <TextInput
              style={s.input}
              value={mineSite}
              onChangeText={setMineSite}
              autoCapitalize="words"
            />
          </View>

          {/* ── SECTION: JOB ROLE ── */}
          <Text style={[s.sectionLabel, { marginTop: spacing.xl }]}>JOB ROLE <Text style={s.required}>*</Text></Text>
          {errors.jobRole && <Text style={s.errorText}>{errors.jobRole}</Text>}

          <View style={s.chipGrid}>
            {JOB_ROLES.map(r => {
              const selected = jobRole === r.code;
              return (
                <TouchableOpacity
                  key={r.code}
                  style={[s.chip, selected && s.chipSelected]}
                  onPress={() => { setJobRole(r.code); setErrors(e => ({ ...e, jobRole: null })); }}
                  activeOpacity={0.75}
                >
                  <Text style={[s.chipLabel, selected && s.chipLabelSelected]}>{r.label}</Text>
                  <Text style={[s.chipShona, selected && s.chipShonaSelected]}>{r.shona}</Text>
                  {/* Risk indicator dots */}
                  <View style={s.riskDots}>
                    {[1,2,3,4].map(i => (
                      <View
                        key={i}
                        style={[s.dot, { backgroundColor: i <= r.risk
                          ? (r.risk >= 4 ? colours.red : r.risk === 3 ? colours.orange : colours.yellow)
                          : colours.card }]}
                      />
                    ))}
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ── SECTION: YEARS UNDERGROUND ── */}
          <Text style={[s.sectionLabel, { marginTop: spacing.xl }]}>YEARS UNDERGROUND <Text style={s.required}>*</Text></Text>
          {errors.years && <Text style={s.errorText}>{errors.years}</Text>}

          <View style={s.yearsList}>
            {YEARS_OPTIONS.map(y => {
              const selected = yearsCode === y.code;
              return (
                <TouchableOpacity
                  key={y.code}
                  style={[s.yearRow, selected && s.yearRowSelected]}
                  onPress={() => { setYearsCode(y.code); setErrors(e => ({ ...e, years: null })); }}
                  activeOpacity={0.75}
                >
                  <View style={[s.radio, selected && s.radioSelected]}>
                    {selected && <View style={s.radioInner} />}
                  </View>
                  <Text style={[s.yearLabel, selected && s.yearLabelSelected]}>{y.label}</Text>
                  <View style={[s.scoreBadge, selected && s.scoreBadgeSelected]}>
                    <Text style={[s.scoreText, selected && s.scoreTextSelected]}>+{y.score}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ── NEXT BUTTON ── */}
          <TouchableOpacity style={s.nextBtn} onPress={handleNext} activeOpacity={0.88}>
            <View style={s.nextInner}>
              <Text style={s.nextText}>NEXT: HEALTH QUESTIONS</Text>
              <Text style={s.nextShona}>Mibvunzo yeUtano →</Text>
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
  root: {
    flex: 1,
    backgroundColor: colours.navy,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colours.card,
    gap: spacing.md,
  },
  backBtn: {
    width: 36, height: 36,
    borderRadius: radius.sm,
    backgroundColor: colours.card,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colours.teal,
  },
  backArrow: { fontSize: 18, color: colours.teal },
  headerText: { flex: 1 },
  headerTitle: {
    fontSize: typography.subtitle,
    fontWeight: typography.bold,
    color: colours.white,
  },
  headerShona: {
    fontSize: typography.micro,
    color: colours.muted,
    fontStyle: 'italic',
    marginTop: 1,
  },
  stepBadge: {
    backgroundColor: colours.tealFade,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: colours.teal,
  },
  stepText: {
    fontSize: typography.tiny,
    color: colours.teal,
    fontWeight: typography.bold,
  },

  // Scroll
  scroll: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
  },

  // Section labels
  sectionLabel: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
    marginBottom: spacing.md,
  },

  // Fields
  field: { marginBottom: spacing.lg },
  fieldLabel: {
    fontSize: typography.caption,
    color: colours.muted,
    fontWeight: typography.semibold,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  required: { color: colours.red },
  input: {
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colours.mid,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: typography.body,
    color: colours.white,
  },
  inputError: { borderColor: colours.red },
  errorText: {
    fontSize: typography.tiny,
    color: colours.red,
    marginTop: spacing.xs,
    fontWeight: typography.semibold,
  },
  fieldHint: {
    fontSize: typography.tiny,
    color: colours.muted,
    marginTop: spacing.xs,
  },

  // Job role chips
  chipGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    width: '47%',
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colours.mid,
    padding: spacing.md,
  },
  chipSelected: {
    borderColor: colours.teal,
    backgroundColor: colours.tealFade,
  },
  chipLabel: {
    fontSize: typography.caption,
    fontWeight: typography.bold,
    color: colours.muted,
  },
  chipLabelSelected: { color: colours.white },
  chipShona: {
    fontSize: typography.micro,
    color: colours.muted,
    fontStyle: 'italic',
    marginTop: 2,
  },
  chipShonaSelected: { color: colours.teal },
  riskDots: {
    flexDirection: 'row',
    gap: 3,
    marginTop: spacing.sm,
  },
  dot: {
    width: 7, height: 7, borderRadius: 4,
  },

  // Years list
  yearsList: { gap: spacing.sm },
  yearRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colours.mid,
    padding: spacing.md,
    gap: spacing.md,
  },
  yearRowSelected: {
    borderColor: colours.teal,
    backgroundColor: colours.tealFade,
  },
  radio: {
    width: 20, height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colours.muted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: colours.teal },
  radioInner: {
    width: 10, height: 10,
    borderRadius: 5,
    backgroundColor: colours.teal,
  },
  yearLabel: {
    flex: 1,
    fontSize: typography.body,
    color: colours.muted,
    fontWeight: typography.medium,
  },
  yearLabelSelected: { color: colours.white },
  scoreBadge: {
    backgroundColor: colours.mid,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  scoreBadgeSelected: { backgroundColor: colours.teal },
  scoreText: {
    fontSize: typography.tiny,
    color: colours.muted,
    fontWeight: typography.bold,
  },
  scoreTextSelected: { color: colours.white },

  // Next button
  nextBtn: { marginTop: spacing.xxl },
  nextInner: {
    backgroundColor: colours.teal,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: colours.mint,
    zIndex: 2,
  },
  nextShadow: {
    position: 'absolute',
    bottom: -5, right: -5, left: 5,
    height: '100%',
    borderRadius: radius.lg,
    backgroundColor: colours.mint,
    zIndex: 1,
    opacity: 0.3,
  },
  nextText: {
    fontSize: typography.body,
    fontWeight: typography.black,
    color: colours.white,
    letterSpacing: 0.5,
  },
  nextShona: {
    fontSize: typography.caption,
    color: 'rgba(255,255,255,0.7)',
    marginTop: spacing.xs,
    fontStyle: 'italic',
  },
});