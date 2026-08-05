import {
  StyleSheet, Text, View, TouchableOpacity,
  SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native';
import { useState, useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius, riskConfig } from '../theme';
import { offlineScore } from './QuestionScreen';

// ── ANTHROPIC API CONFIG ───────────────────────────────────────
// Replace with your actual key — move to env var before production
const ANTHROPIC_API_KEY = 'YOUR_ANTHROPIC_API_KEY_HERE';

// ── CLAUDE SYSTEM PROMPT ───────────────────────────────────────
const SYSTEM_PROMPT = `You are SilicaGuard's AI risk engine for Zimbabwe's artisanal gold mining communities.

You assess silicosis risk for miners in Kwekwe, Midlands Province, Zimbabwe.

CLINICAL CONTEXT:
- Silicosis prevalence in Zimbabwe ASGM: 19% (peer-reviewed, Midlands Province)
- TB prevalence in this population: 6.8% — silicosis raises TB risk ×3–5
- HIV prevalence: 18% — raises silicosis risk ×1.25
- Mean age of affected miners: 35.5 years
- No cure exists — prevention and early detection are everything

RISK TIERS (match exactly):
- GREEN: Low risk. No significant exposure or symptoms. Continue education.
- YELLOW: Elevated risk. Significant exposure but no symptoms yet. Monitor closely.
- ORANGE: High risk. Exposure AND early symptoms. Refer within 14 days.
- RED: Critical risk. Severe symptoms or extreme exposure. Refer within 48 hours.

SCORING GUIDE:
- Job risk multiplier: drilling/crushing = ×4, blasting/processing = ×3, hauling = ×2, surface = ×1
- Years underground score: <1yr=1, 1-3yr=2, 3-5yr=3, 5-10yr=4, >10yr=5
- Exposure base = years_score × job_risk_multiplier
- Answer scores add to exposure base
- Total ≤8 = GREEN, 9-16 = YELLOW, 17-24 = ORANGE, >24 = RED
- TB history or prior diagnosis = always elevate by one tier minimum

Respond ONLY with valid JSON in this exact shape:
{
  "tier": "GREEN" | "YELLOW" | "ORANGE" | "RED",
  "confidence": 0.0-1.0,
  "explanation_english": "2-3 sentence plain language explanation for the healthcare worker",
  "explanation_shona": "2-3 sentence plain language explanation in Shona for the miner",
  "contributing_factors": ["factor 1", "factor 2", "factor 3"],
  "advice_line": "One specific action the miner should take today"
}`;

// ── CLAUDE API CALL ────────────────────────────────────────────
const callClaudeRiskEngine = async (miner, answers) => {
  const userMessage = `
MINER PROFILE:
- Name: ${miner.name}
- Job role: ${miner.job_label} (risk multiplier: ${miner.job_risk})
- Years underground: ${miner.years_label} (score: ${miner.years_score})
- Mine site: ${miner.mine_site}

SCREENING ANSWERS:
${answers.map(a => `- ${a.question_code}: ${a.answer_value} (score: ${a.answer_score})`).join('\n')}

EXPOSURE BASE: ${miner.years_score * miner.job_risk}
ANSWER TOTAL: ${answers.reduce((s, a) => s + a.answer_score, 0)}
COMBINED SCORE: ${(miner.years_score * miner.job_risk) + answers.reduce((s, a) => s + a.answer_score, 0)}

Assess this miner's silicosis risk and return JSON only.`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 1000,
      system: SYSTEM_PROMPT,
      messages: [{ role: 'user', content: userMessage }],
    }),
  });

  if (!response.ok) throw new Error(`API error ${response.status}`);
  const data = await response.json();
  const text = data.content[0].text.trim();
  const clean = text.replace(/```json|```/g, '').trim();
  return JSON.parse(clean);
};

// ── SCREEN ─────────────────────────────────────────────────────
export default function ResultScreen({ navigation, route }) {
  const { miner, answers } = route.params;

  const [loading, setLoading]   = useState(true);
  const [result, setResult]     = useState(null);
  const [offline, setOffline]   = useState(false);
  const [error, setError]       = useState(null);

  useEffect(() => {
    runRiskEngine();
  }, []);

  const runRiskEngine = async () => {
    setLoading(true);
    setError(null);

    try {
      const aiResult = await callClaudeRiskEngine(miner, answers);
      setResult(aiResult);
      setOffline(false);
    } catch (err) {
      console.warn('Claude API unavailable, using offline score:', err.message);
      const tier = offlineScore(miner, answers);
      const combined = (miner.years_score * miner.job_risk) + answers.reduce((s, a) => s + a.answer_score, 0);
      setResult({
        tier,
        confidence: 0.75,
        explanation_english: `Risk assessed offline. Combined exposure score: ${combined}. ${tier === 'GREEN' ? 'Low silicosis risk detected.' : tier === 'YELLOW' ? 'Elevated exposure — monitor closely.' : tier === 'ORANGE' ? 'High risk — referral recommended within 14 days.' : 'Critical risk — immediate referral required within 48 hours.'}`,
        explanation_shona: tier === 'RED' ? 'Njodzi huru — enda kuchipatara nhasi.' : tier === 'ORANGE' ? 'Njodzi — enda kuchipatara mumazuva gumi nemana.' : 'Ongorora utano hwako nguva dzose.',
        contributing_factors: [
          `${miner.years_label} underground (${miner.job_label})`,
          `Combined exposure score: ${combined}`,
          'Assessed using offline algorithm',
        ],
        advice_line: tier === 'RED' || tier === 'ORANGE'
          ? 'Report to Kwekwe District Hospital immediately.'
          : 'Continue wearing N95 respirator. Return for rescreening in 6 months.',
      });
      setOffline(true);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.loadingRoot}>
        <StatusBar style="light" />
        <View style={s.loadingContent}>
          <ActivityIndicator size="large" color={colours.teal} />
          <Text style={s.loadingTitle}>Analysing Screening</Text>
          <Text style={s.loadingShona}>Kuongorora Mhinduro...</Text>
          <Text style={s.loadingSub}>
            AI risk engine processing {miner.name}'s answers
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!result) return null;

  const config = riskConfig[result.tier] || riskConfig.GREEN;

  return (
    <SafeAreaView style={[s.root, { backgroundColor: colours.navy }]}>
      <StatusBar style="light" />

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* ── OFFLINE BADGE ── */}
        {offline && (
          <View style={s.offlineBanner}>
            <Text style={s.offlineText}>
              📵 Offline mode — AI unavailable. Scored algorithmically.
            </Text>
          </View>
        )}

        {/* ── RISK CARD ── */}
        <View style={[s.riskCard, { borderColor: config.colour, backgroundColor: config.background }]}>
          <Text style={s.riskEmoji}>{config.emoji}</Text>
          <Text style={[s.riskLabel, { color: config.colour }]}>{config.label}</Text>
          <Text style={[s.riskShona, { color: config.colour }]}>{config.shona}</Text>

          {result.urgency && (
            <View style={[s.urgencyPill, { borderColor: config.colour }]}>
              <Text style={[s.urgencyText, { color: config.colour }]}>
                ⏱ Refer within {config.urgency}
              </Text>
            </View>
          )}

          <Text style={s.confidence}>
            AI confidence: {Math.round(result.confidence * 100)}%
            {offline ? ' (offline)' : ''}
          </Text>
        </View>

        {/* ── MINER SUMMARY ── */}
        <View style={s.minerCard}>
          <Text style={s.cardEyebrow}>MINER</Text>
          <Text style={s.minerName}>{miner.name}</Text>
          <Text style={s.minerSub}>{miner.job_label} · {miner.years_label} · {miner.mine_site}</Text>
        </View>

        {/* ── EXPLANATION ── */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>CLINICAL EXPLANATION</Text>
          <Text style={s.explanationText}>{result.explanation_english}</Text>
        </View>

        <View style={s.section}>
          <Text style={s.sectionLabel}>CHERECHEDZO (SHONA)</Text>
          <Text style={[s.explanationText, { fontStyle: 'italic' }]}>
            {result.explanation_shona}
          </Text>
        </View>

        {/* ── CONTRIBUTING FACTORS ── */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>CONTRIBUTING FACTORS</Text>
          {result.contributing_factors?.map((f, i) => (
            <View key={i} style={s.factorRow}>
              <View style={[s.factorDot, { backgroundColor: config.colour }]} />
              <Text style={s.factorText}>{f}</Text>
            </View>
          ))}
        </View>

        {/* ── ADVICE LINE ── */}
        {result.advice_line && (
          <View style={[s.adviceCard, { borderColor: config.colour }]}>
            <Text style={s.adviceEyebrow}>ACTION TODAY</Text>
            <Text style={s.adviceText}>{result.advice_line}</Text>
          </View>
        )}

        {/* ── ACTIONS ── */}
        {(result.tier === 'RED' || result.tier === 'ORANGE') && (
          <TouchableOpacity
            style={[s.referBtn, { backgroundColor: config.colour }]}
            onPress={() => navigation.navigate('Referral', { miner, result })}
            activeOpacity={0.88}
          >
            <View style={s.referInner}>
              <Text style={s.referText}>GENERATE REFERRAL CARD</Text>
              <Text style={s.referShona}>Gadzira Kadhi Rekutumwa Chipatara →</Text>
            </View>
            <View style={[s.referShadow, { backgroundColor: config.colour }]} />
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={s.doneBtn}
          onPress={() => navigation.navigate('Home')}
          activeOpacity={0.75}
        >
          <Text style={s.doneBtnText}>← Screen Next Miner</Text>
          <Text style={s.doneBtnShona}>Ongorora Mushandi Unotevera</Text>
        </TouchableOpacity>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  // Loading
  loadingRoot: {
    flex: 1,
    backgroundColor: colours.navy,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingContent: { alignItems: 'center', gap: spacing.lg },
  loadingTitle: {
    fontSize: typography.title,
    fontWeight: typography.black,
    color: colours.white,
    marginTop: spacing.lg,
  },
  loadingShona: {
    fontSize: typography.body,
    color: colours.muted,
    fontStyle: 'italic',
  },
  loadingSub: {
    fontSize: typography.caption,
    color: colours.muted,
    textAlign: 'center',
    maxWidth: 260,
  },

  // Main
  root: { flex: 1 },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },

  // Offline banner
  offlineBanner: {
    backgroundColor: 'rgba(255,184,0,0.15)',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colours.yellow,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  offlineText: {
    fontSize: typography.caption,
    color: colours.yellow,
    textAlign: 'center',
  },

  // Risk card
  riskCard: {
    borderRadius: radius.xl,
    borderWidth: 2,
    padding: spacing.xxl,
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  riskEmoji: { fontSize: 52, marginBottom: spacing.md },
  riskLabel: {
    fontSize: 32,
    fontWeight: typography.black,
    letterSpacing: -0.5,
    textAlign: 'center',
  },
  riskShona: {
    fontSize: typography.body,
    fontWeight: typography.semibold,
    fontStyle: 'italic',
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  urgencyPill: {
    marginTop: spacing.lg,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  urgencyText: {
    fontSize: typography.caption,
    fontWeight: typography.bold,
  },
  confidence: {
    fontSize: typography.tiny,
    color: colours.muted,
    marginTop: spacing.md,
  },

  // Miner card
  minerCard: {
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colours.mid,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  cardEyebrow: {
    fontSize: typography.micro,
    color: colours.teal,
    fontWeight: typography.bold,
    letterSpacing: 2,
    marginBottom: spacing.xs,
  },
  minerName: {
    fontSize: typography.subtitle,
    fontWeight: typography.black,
    color: colours.white,
  },
  minerSub: {
    fontSize: typography.caption,
    color: colours.muted,
    marginTop: spacing.xs,
  },

  // Sections
  section: {
    marginBottom: spacing.lg,
  },
  sectionLabel: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
    marginBottom: spacing.md,
  },
  explanationText: {
    fontSize: typography.body,
    color: colours.offwhite,
    lineHeight: 22,
  },

  // Contributing factors
  factorRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  factorDot: {
    width: 8, height: 8,
    borderRadius: 4,
    marginTop: 6,
  },
  factorText: {
    flex: 1,
    fontSize: typography.body,
    color: colours.muted,
    lineHeight: 20,
  },

  // Advice card
  adviceCard: {
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderLeftWidth: 4,
    padding: spacing.lg,
    marginBottom: spacing.xl,
  },
  adviceEyebrow: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
    marginBottom: spacing.sm,
  },
  adviceText: {
    fontSize: typography.body,
    color: colours.white,
    fontWeight: typography.semibold,
    lineHeight: 22,
  },

  // Referral button
  referBtn: {
    marginBottom: spacing.lg,
    borderRadius: radius.lg,
  },
  referInner: {
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
    zIndex: 2,
  },
  referShadow: {
    position: 'absolute',
    bottom: -5, right: -5, left: 5,
    height: '100%',
    borderRadius: radius.lg,
    zIndex: 1,
    opacity: 0.3,
  },
  referText: {
    fontSize: typography.body,
    fontWeight: typography.black,
    color: colours.white,
    letterSpacing: 0.5,
  },
  referShona: {
    fontSize: typography.caption,
    color: 'rgba(255,255,255,0.75)',
    marginTop: spacing.xs,
    fontStyle: 'italic',
  },

  // Done button
  doneBtn: {
    backgroundColor: colours.card,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colours.mid,
    marginBottom: spacing.lg,
  },
  doneBtnText: {
    fontSize: typography.body,
    fontWeight: typography.bold,
    color: colours.muted,
  },
  doneBtnShona: {
    fontSize: typography.caption,
    color: colours.muted,
    fontStyle: 'italic',
    marginTop: spacing.xs,
  },
});