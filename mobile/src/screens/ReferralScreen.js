import {
  StyleSheet, Text, View, TouchableOpacity,
  SafeAreaView, ScrollView,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius, riskConfig } from '../theme';

// Generate a readable miner ID from phone + timestamp
const generateReferralId = (phone) => {
  const digits = phone.replace(/\D/g, '').slice(-4);
  const stamp  = Date.now().toString().slice(-5);
  return `SG-${digits}-${stamp}`;
};

const formatDeadline = (tier) => {
  const now = new Date();
  const hours = tier === 'RED' ? 48 : 14 * 24;
  now.setHours(now.getHours() + hours);
  return now.toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
};

export default function ReferralScreen({ navigation, route }) {
  const { miner, result } = route.params;
  const config     = riskConfig[result.tier] || riskConfig.RED;
  const referralId = generateReferralId(miner.phone);
  const deadline   = formatDeadline(result.tier);
  const isRed      = result.tier === 'RED';

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={s.backBtn}>
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={s.headerText}>
          <Text style={s.headerTitle}>Referral Card</Text>
          <Text style={s.headerShona}>Kadhi Rekutumwa Chipatara</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >

        {/* ── PRE-ALERT CONFIRMATION ── */}
        <View style={[s.alertBanner, { borderColor: config.colour, backgroundColor: config.background }]}>
          <Text style={s.alertIcon}>🏥</Text>
          <View style={s.alertText}>
            <Text style={[s.alertTitle, { color: config.colour }]}>
              Kwekwe District Hospital Notified
            </Text>
            <Text style={s.alertSub}>
              Pre-alert sent · {new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} today
            </Text>
          </View>
        </View>

        {/* ── REFERRAL CARD ── */}
        <View style={[s.referralCard, { borderColor: config.colour }]}>

          {/* Card header */}
          <View style={[s.cardHeader, { backgroundColor: config.colour }]}>
            <View style={s.cardHeaderLeft}>
              <Text style={s.cardHeaderLabel}>SILICAGUARD REFERRAL</Text>
              <Text style={s.cardHeaderId}>{referralId}</Text>
            </View>
            <Text style={s.cardHeaderEmoji}>{config.emoji}</Text>
          </View>

          {/* Risk level */}
          <View style={[s.riskBanner, { backgroundColor: config.background }]}>
            <Text style={[s.riskLabel, { color: config.colour }]}>{config.label}</Text>
            <Text style={[s.riskShona, { color: config.colour }]}>{config.shona}</Text>
          </View>

          {/* Miner details */}
          <View style={s.cardSection}>
            <Text style={s.cardSectionLabel}>PATIENT</Text>
            <Text style={s.cardValue}>{miner.name}</Text>
            <Text style={s.cardMeta}>{miner.phone} · {miner.mine_site}</Text>
          </View>

          <View style={s.cardDivider} />

          {/* Facility */}
          <View style={s.cardSection}>
            <Text style={s.cardSectionLabel}>REFER TO</Text>
            <Text style={s.cardValue}>Kwekwe District Hospital</Text>
            <Text style={s.cardMeta}>Occupational Health Department · Kwekwe, Midlands</Text>
          </View>

          <View style={s.cardDivider} />

          {/* Deadline */}
          <View style={[s.deadlineRow, { backgroundColor: isRed ? 'rgba(255,59,59,0.1)' : 'rgba(255,140,0,0.1)' }]}>
            <Text style={s.deadlineIcon}>⏱</Text>
            <View>
              <Text style={[s.deadlineLabel, { color: config.colour }]}>
                {isRed ? 'ATTEND WITHIN 48 HOURS' : 'ATTEND WITHIN 14 DAYS'}
              </Text>
              <Text style={s.deadlineDate}>By {deadline}</Text>
            </View>
          </View>

          <View style={s.cardDivider} />

          {/* Clinical note */}
          <View style={s.cardSection}>
            <Text style={s.cardSectionLabel}>CLINICAL NOTE</Text>
            <Text style={s.cardNote}>{result.explanation_english}</Text>
          </View>

          <View style={s.cardDivider} />

          {/* Date issued */}
          <View style={s.cardFooter}>
            <Text style={s.cardFooterText}>
              Issued: {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
            </Text>
            <Text style={s.cardFooterText}>SilicaGuard · Cimas Healthathon 3.0</Text>
          </View>
        </View>

        {/* ── INSTRUCTIONS FOR VHW ── */}
        <View style={s.instructionsCard}>
          <Text style={s.instructionsTitle}>📋  Instructions for Health Worker</Text>
          <View style={s.instructionsList}>
            {[
              'Hand this referral card to the miner — they must keep it.',
              'Explain the risk level and urgency in Shona.',
              `Tell the miner to attend Kwekwe District Hospital by ${isRed ? 'tomorrow' : 'within 14 days'}.`,
              'Record the miner\'s phone number so you can follow up if they don\'t attend.',
              'The hospital has already received a digital pre-alert.',
            ].map((step, i) => (
              <View key={i} style={s.instructionRow}>
                <View style={s.instructionNum}>
                  <Text style={s.instructionNumText}>{i + 1}</Text>
                </View>
                <Text style={s.instructionText}>{step}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── SHONA SCRIPT FOR VHW ── */}
        <View style={s.shonaCard}>
          <Text style={s.shonaTitle}>🗣  Say this to the miner (Shona)</Text>
          <Text style={s.shonaScript}>
            "{miner.name}, maongororo ako aratidza kuti {config.shona.toLowerCase()}. {result.explanation_shona} {isRed ? 'Enda kuchipatara nhasi kana mangwana.' : 'Enda kuchipatara mumazuva gumi nemana.'} Kwekwe District Hospital — vane ruzivo rwako."
          </Text>
        </View>

        {/* ── ACTIONS ── */}
        <View style={s.actionsRow}>
          <TouchableOpacity
            style={s.actionBtn}
            onPress={() => navigation.navigate('Home')}
            activeOpacity={0.75}
          >
            <Text style={s.actionBtnText}>🏠  Home</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.actionBtn, s.actionBtnPrimary]}
            onPress={() => {
              // Navigate back to intake for next miner
              navigation.navigate('Intake');
            }}
            activeOpacity={0.88}
          >
            <Text style={[s.actionBtnText, s.actionBtnTextPrimary]}>
              + Screen Next Miner
            </Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
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

  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },

  // Pre-alert banner
  alertBanner: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    borderRadius: radius.md, borderWidth: 1.5,
    padding: spacing.lg, marginBottom: spacing.lg,
  },
  alertIcon: { fontSize: 24 },
  alertText: { flex: 1 },
  alertTitle: { fontSize: typography.caption, fontWeight: typography.black },
  alertSub: { fontSize: typography.tiny, color: colours.muted, marginTop: 2 },

  // Referral card
  referralCard: {
    backgroundColor: colours.card, borderRadius: radius.lg,
    borderWidth: 2, overflow: 'hidden', marginBottom: spacing.lg,
  },
  cardHeader: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.lg,
  },
  cardHeaderLeft: { flex: 1 },
  cardHeaderLabel: { fontSize: typography.micro, color: 'rgba(255,255,255,0.8)', fontWeight: typography.bold, letterSpacing: 1 },
  cardHeaderId: { fontSize: typography.subtitle, fontWeight: typography.black, color: colours.white, marginTop: 2 },
  cardHeaderEmoji: { fontSize: 32 },

  riskBanner: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  riskLabel: { fontSize: 22, fontWeight: typography.black, letterSpacing: -0.3 },
  riskShona: { fontSize: typography.caption, fontStyle: 'italic', marginTop: 2 },

  cardSection: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  cardSectionLabel: { fontSize: typography.micro, color: colours.teal, fontWeight: typography.bold, letterSpacing: 2, marginBottom: spacing.xs },
  cardValue: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  cardMeta: { fontSize: typography.caption, color: colours.muted, marginTop: 2 },
  cardDivider: { height: 0.5, backgroundColor: colours.mid, marginHorizontal: spacing.lg },

  deadlineRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
  },
  deadlineIcon: { fontSize: 20 },
  deadlineLabel: { fontSize: typography.caption, fontWeight: typography.black, letterSpacing: 0.5 },
  deadlineDate: { fontSize: typography.caption, color: colours.muted, marginTop: 2 },

  cardNote: { fontSize: typography.caption, color: colours.muted, lineHeight: 18 },

  cardFooter: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    backgroundColor: 'rgba(0,0,0,0.2)',
  },
  cardFooterText: { fontSize: typography.micro, color: colours.muted },

  // Instructions
  instructionsCard: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.mid,
    padding: spacing.lg, marginBottom: spacing.lg,
  },
  instructionsTitle: { fontSize: typography.caption, fontWeight: typography.bold, color: colours.white, marginBottom: spacing.lg },
  instructionsList: { gap: spacing.md },
  instructionRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  instructionNum: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: colours.teal, alignItems: 'center', justifyContent: 'center',
    marginTop: 1,
  },
  instructionNumText: { fontSize: typography.tiny, fontWeight: typography.black, color: colours.white },
  instructionText: { flex: 1, fontSize: typography.caption, color: colours.muted, lineHeight: 18 },

  // Shona script
  shonaCard: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.teal, borderLeftWidth: 4,
    padding: spacing.lg, marginBottom: spacing.lg,
  },
  shonaTitle: { fontSize: typography.caption, fontWeight: typography.bold, color: colours.teal, marginBottom: spacing.md },
  shonaScript: { fontSize: typography.caption, color: colours.offwhite, fontStyle: 'italic', lineHeight: 20 },

  // Actions
  actionsRow: { flexDirection: 'row', gap: spacing.md },
  actionBtn: {
    flex: 1, backgroundColor: colours.card,
    borderRadius: radius.md, borderWidth: 1.5,
    borderColor: colours.mid, padding: spacing.lg,
    alignItems: 'center',
  },
  actionBtnPrimary: { backgroundColor: colours.teal, borderColor: colours.mint },
  actionBtnText: { fontSize: typography.caption, fontWeight: typography.bold, color: colours.muted },
  actionBtnTextPrimary: { color: colours.white },
});