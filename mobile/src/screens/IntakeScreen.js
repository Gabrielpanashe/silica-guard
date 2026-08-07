import {
  StyleSheet, Text, View, TextInput,
  TouchableOpacity, SafeAreaView, ScrollView,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';

export default function IntakeScreen({ navigation }) {
  const [name, setName]         = useState('');
  const [phone, setPhone]       = useState('');
  const [mineSite, setMineSite] = useState('Globe & Phoenix Mine');
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
              placeholderTextColor={colours.muted}
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
              placeholderTextColor={colours.muted}
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
            <TextInput
              style={s.input}
              value={mineSite}
              onChangeText={setMineSite}
              autoCapitalize="words"
            />
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
  root: { flex: 1, backgroundColor: colours.navy },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
    borderBottomWidth: 0.5, borderBottomColor: colours.card, gap: spacing.md,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.sm,
    backgroundColor: colours.card, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: colours.teal,
  },
  backArrow: { fontSize: 18, color: colours.teal },
  headerText: { flex: 1 },
  headerTitle: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  headerShona: { fontSize: typography.micro, color: colours.muted, fontStyle: 'italic', marginTop: 1 },
  stepBadge: {
    backgroundColor: colours.tealFade, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: colours.teal,
  },
  stepText: { fontSize: typography.tiny, color: colours.teal, fontWeight: typography.bold },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  sectionLabel: {
    fontSize: typography.micro, fontWeight: typography.bold,
    color: colours.teal, letterSpacing: 2, marginBottom: spacing.sm,
  },
  sectionHint: {
    fontSize: typography.caption, color: colours.muted,
    marginBottom: spacing.xl, lineHeight: 18,
  },
  field: { marginBottom: spacing.lg },
  fieldLabel: {
    fontSize: typography.caption, color: colours.muted,
    fontWeight: typography.semibold, marginBottom: spacing.xs,
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  required: { color: colours.red },
  input: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colours.mid,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    fontSize: typography.body, color: colours.white,
  },
  inputError: { borderColor: colours.red },
  errorText: { fontSize: typography.tiny, color: colours.red, marginTop: spacing.xs, fontWeight: typography.semibold },
  fieldHint: { fontSize: typography.tiny, color: colours.muted, marginTop: spacing.xs, lineHeight: 16 },
  infoCard: {
    flexDirection: 'row', gap: spacing.md,
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.teal,
    padding: spacing.lg, marginBottom: spacing.xl,
    borderLeftWidth: 4,
  },
  infoIcon: { fontSize: 18 },
  infoText: { flex: 1, fontSize: typography.caption, color: colours.muted, lineHeight: 18 },
  nextBtn: { marginTop: spacing.sm },
  nextInner: {
    backgroundColor: colours.teal, borderRadius: radius.lg,
    padding: spacing.xl, alignItems: 'center',
    borderWidth: 2, borderColor: colours.mint, zIndex: 2,
  },
  nextShadow: {
    position: 'absolute', bottom: -5, right: -5, left: 5,
    height: '100%', borderRadius: radius.lg,
    backgroundColor: colours.mint, zIndex: 1, opacity: 0.3,
  },
  nextText: { fontSize: typography.body, fontWeight: typography.black, color: colours.white, letterSpacing: 0.5 },
  nextShona: { fontSize: typography.caption, color: 'rgba(255,255,255,0.7)', marginTop: spacing.xs, fontStyle: 'italic' },
});
