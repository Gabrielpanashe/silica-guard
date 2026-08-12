import {
  StyleSheet, Text, View, TouchableOpacity,
  ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useState, useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius, riskConfig } from '../theme';
import { offlineScore } from './QuestionScreen';
import { registerWorker, getWorkerByPhone, submitScreening } from '../services/api';

// Backend timestamps are SQLite-style "YYYY-MM-DD HH:MM:SS" (space-
// separated, no 'Z') — append it so Date() parses as UTC rather than
// guessing local time, same fix as the web dashboard's relativeTime().
function formatHistoryDate(isoLike) {
  if (!isoLike) return '—';
  const iso = isoLike.includes('T') ? isoLike : isoLike.replace(' ', 'T') + 'Z';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return isoLike;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function ResultScreen({ navigation, route }) {
  const { miner, answers } = route.params;

  const [loading, setLoading] = useState(true);
  const [result, setResult]   = useState(null);
  const [offline, setOffline] = useState(false);
  // Full screening history for this miner (10 August) — every screening
  // this system has ever recorded for them is already kept (nothing is
  // ever overwritten), this just surfaces it. Best-effort: fetched after
  // the screening itself succeeds, never blocks or fails the result
  // screen if it can't load. Absent entirely in the offline-fallback path
  // (no way to look anything up without the backend).
  const [history, setHistory] = useState([]);

  useEffect(() => { runScreening(); }, []);

  const runScreening = async () => {
    setLoading(true);
    try {
      // Step 1: Register miner (409 = already exists — look them up instead)
      let minerId;
      try {
        const worker = await registerWorker({
          name: miner.name,
          phone: miner.phone,
          mine_site: miner.mine_site,
        });
        minerId = worker.id;
      } catch (e) {
        const msg = e.message?.toLowerCase() || "";
        if (msg.includes("already registered") || msg.includes("409")) {
          const existing = await getWorkerByPhone(miner.phone);
          minerId = existing.id;
        } else {
          throw e; // genuine failure — fall through to offline, as today
        }
      }

      // Step 2: Submit screening to backend
      let screening;
      try {
        screening = await submitScreening({
          miner_id: minerId,
          answers,
          screened_by: "VHW",
          offline_fallback_used: false,
        });
      } catch (e) {
        console.warn("Registration/lookup succeeded but submitScreening failed:", e.message);
        throw e;
      }

      setResult({
        tier: screening.tier,
        confidence: screening.confidence,
        explanation_english: screening.explanation_english,
        explanation_shona:
          screening.explanation_shona || "Ongorora mhinduro nenguva.",
        contributing_factors: screening.contributing_factors || [],
        advice_line: screening.advice_line,
        provisional: screening.provisional,
        previous_screening_id: screening.previous_screening_id,
        // Longitudinal Deterioration Detection — the backend has always
        // returned this (5 August), it was just never captured here, so
        // a re-screened miner never showed anything different from a
        // brand-new one. { compared_to_screening_id, changed, summary }.
        deterioration: screening.deterioration,
      });
      setOffline(false);

      // Full comparative history (10 August) — best-effort, never lets a
      // failure here affect the result already shown above.
      try {
        const worker = await getWorkerByPhone(miner.phone);
        setHistory(worker.screenings || []);
      } catch (histErr) {
        console.warn("Could not load screening history:", histErr.message);
      }
    } catch (err) {
      console.warn("Backend unavailable, using offline score:", err.message);
      const scored = offlineScore(answers);
      const tier = scored?.tier || "GREEN";
      const total = scored?.total || 0;

      setResult({
        tier,
        confidence: 0.75,
        explanation_english: `Offline assessment. Combined score: ${total}. ${
          tier === "GREEN"
            ? "Low silicosis risk detected."
            : tier === "YELLOW"
              ? "Elevated exposure — monitor closely."
              : tier === "ORANGE"
                ? "High risk — referral recommended within 14 days."
                : "Critical risk — immediate referral required within 48 hours."
        }`,
        explanation_shona:
          tier === "RED"
            ? "Njodzi huru — enda kuchipatara nhasi."
            : tier === "ORANGE"
              ? "Njodzi — enda kuchipatara mumazuva gumi nemana."
              : tier === "YELLOW"
                ? "Tarira zvakanyanya. Dzokera kuongorwa mushure memwedzi mitatu."
                : "Hapana njodzi huru. Ramba uchidzidziswa nezve utano.",
        contributing_factors: [
          `Total score: ${total}`,
          "Assessed using offline algorithm",
          "Safety overrides applied",
        ],
        advice_line:
          tier === "RED" || tier === "ORANGE"
            ? "Report to Kwekwe District Hospital immediately."
            : "Continue wearing N95 respirator. Return for rescreening in 6 months.",
        provisional: true,
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
          <Text style={s.loadingSub}>Processing {miner.name}'s answers</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!result) return null;
  const tier = result?.tier;
  const config =
    tier && riskConfig[tier] ? riskConfig[tier] : riskConfig["GREEN"];

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Offline banner */}
        {offline && (
          <View style={s.offlineBanner}>
            <Text style={s.offlineText}>
              📵 Offline mode — backend unavailable. Scored algorithmically with safety overrides.
            </Text>
          </View>
        )}

        {/* ── RISK CARD ── */}
        <View style={[s.riskCard, { borderColor: config.colour, backgroundColor: config.background }]}>
          <Text style={s.riskEmoji}>{config.emoji}</Text>
          <Text style={[s.riskLabel, { color: config.colour }]}>{config.label}</Text>
          <Text style={[s.riskShona, { color: config.colour }]}>{config.shona}</Text>
          {config.urgency && (
            <View style={[s.urgencyPill, { borderColor: config.colour }]}>
              <Text style={[s.urgencyText, { color: config.colour }]}>
                ⏱ Refer within {config.urgency}
              </Text>
            </View>
          )}
          <Text style={s.confidence}>
            Confidence: {Math.round((result.confidence || 0.75) * 100)}%
            {result.provisional ? ' · provisional' : ''}
            {offline ? ' · offline' : ''}
          </Text>
        </View>

        {/* Miner summary */}
        <View style={s.minerCard}>
          <Text style={s.cardEyebrow}>MINER</Text>
          <Text style={s.minerName}>{miner.name}</Text>
          <Text style={s.minerSub}>{miner.mine_site} · {miner.phone}</Text>
        </View>

        {/* Longitudinal Deterioration Detection — only shows on a re-screen
            (previous_screening_id is null on a worker's first-ever screening,
            and absent entirely in the offline-fallback path, which has no
            way to look up a previous screening locally). */}
        {result.deterioration && result.previous_screening_id && (
          <View
            style={[
              s.deteriorationCard,
              { borderColor: result.deterioration.changed ? colours.watch : colours.mint },
            ]}
          >
            <Text style={s.cardEyebrow}>SINCE LAST SCREENING</Text>
            <Text
              style={[
                s.deteriorationText,
                { color: result.deterioration.changed ? colours.watch : colours.offwhite },
              ]}
            >
              {result.deterioration.changed ? '⚠ ' : '✓ '}
              {result.deterioration.summary}
            </Text>
          </View>
        )}

        {/* Screening history (10 August) — every screening this system has
            ever recorded for this miner, most recent (today's) first.
            The one-line deterioration summary above is the headline;
            this is the actual comparative record it's summarising —
            tier progression across every visit, not just the latest pair.
            Only shows once there's more than just today's entry. */}
        {history.length > 1 && (
          <View style={s.historyCard}>
            <Text style={s.cardEyebrow}>SCREENING HISTORY · {history.length} VISITS</Text>
            {history.map((h, i) => {
              const hConfig = h.tier && riskConfig[h.tier] ? riskConfig[h.tier] : riskConfig['GREEN'];
              return (
                <View key={h.id} style={[s.historyRow, i === history.length - 1 && s.historyRowLast]}>
                  <View style={[s.historyTierDot, { backgroundColor: hConfig.colour }]} />
                  <View style={s.historyMain}>
                    <View style={s.historyTopLine}>
                      <Text style={[s.historyTier, { color: hConfig.colour }]}>{h.tier || '—'}</Text>
                      <Text style={s.historyDate}>{i === 0 ? 'TODAY' : formatHistoryDate(h.created_at)}</Text>
                    </View>
                    {!!h.advice_line && <Text style={s.historyAdvice}>{h.advice_line}</Text>}
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* English explanation */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>CLINICAL EXPLANATION</Text>
          <Text style={s.explanationText}>{result.explanation_english}</Text>
        </View>

        {/* Shona explanation */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>CHERECHEDZO (SHONA)</Text>
          <Text style={[s.explanationText, { fontStyle: 'italic' }]}>
            {result.explanation_shona}
          </Text>
        </View>

        {/* Contributing factors */}
        {result.contributing_factors?.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionLabel}>CONTRIBUTING FACTORS</Text>
            {result.contributing_factors.map((f, i) => (
              <View key={i} style={s.factorRow}>
                <View style={[s.factorDot, { backgroundColor: config.colour }]} />
                <Text style={s.factorText}>{f}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Advice */}
        {result.advice_line && (
          <View style={[s.adviceCard, { borderColor: config.colour }]}>
            <Text style={s.adviceEyebrow}>ACTION TODAY</Text>
            <Text style={s.adviceText}>{result.advice_line}</Text>
          </View>
        )}

        {/* Referral button — only for ORANGE and RED */}
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

        {/* Done */}
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
  loadingRoot: { flex: 1, backgroundColor: colours.navy, justifyContent: 'center', alignItems: 'center' },
  loadingContent: { alignItems: 'center', gap: spacing.lg },
  loadingTitle: { fontSize: typography.title, fontWeight: typography.black, color: colours.white, marginTop: spacing.lg },
  loadingShona: { fontSize: typography.body, color: colours.muted, fontStyle: 'italic' },
  loadingSub: { fontSize: typography.caption, color: colours.muted, textAlign: 'center', maxWidth: 260 },
  root: { flex: 1, backgroundColor: colours.navy },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  offlineBanner: {
    backgroundColor: 'rgba(255,184,0,0.15)', borderRadius: radius.md,
    borderWidth: 1, borderColor: colours.yellow,
    padding: spacing.md, marginBottom: spacing.lg,
  },
  offlineText: { fontSize: typography.caption, color: colours.yellow, textAlign: 'center' },
  riskCard: {
    borderRadius: radius.xl, borderWidth: 2,
    padding: spacing.xxl, alignItems: 'center', marginBottom: spacing.lg,
  },
  riskEmoji: { fontSize: 52, marginBottom: spacing.md },
  riskLabel: { fontSize: 32, fontWeight: typography.black, letterSpacing: -0.5, textAlign: 'center' },
  riskShona: { fontSize: typography.body, fontWeight: typography.semibold, fontStyle: 'italic', marginTop: spacing.xs, textAlign: 'center' },
  urgencyPill: { marginTop: spacing.lg, borderRadius: radius.pill, borderWidth: 1.5, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  urgencyText: { fontSize: typography.caption, fontWeight: typography.bold },
  confidence: { fontSize: typography.tiny, color: colours.muted, marginTop: spacing.md },
  minerCard: { backgroundColor: colours.card, borderRadius: radius.md, borderWidth: 1, borderColor: colours.mid, padding: spacing.lg, marginBottom: spacing.lg },
  cardEyebrow: { fontSize: typography.micro, color: colours.teal, fontWeight: typography.bold, letterSpacing: 2, marginBottom: spacing.xs },
  minerName: { fontSize: typography.subtitle, fontWeight: typography.black, color: colours.white },
  minerSub: { fontSize: typography.caption, color: colours.muted, marginTop: spacing.xs },
  deteriorationCard: { backgroundColor: colours.card, borderRadius: radius.md, borderWidth: 1.5, borderLeftWidth: 4, padding: spacing.lg, marginBottom: spacing.lg },
  deteriorationText: { fontSize: typography.body, fontWeight: typography.semibold, lineHeight: 21, marginTop: spacing.xs },
  historyCard: { backgroundColor: colours.card, borderRadius: radius.md, borderWidth: 1, borderColor: colours.mid, padding: spacing.lg, marginBottom: spacing.lg },
  historyRow: { flexDirection: 'row', gap: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 0.5, borderBottomColor: colours.mid },
  historyRowLast: { borderBottomWidth: 0, paddingBottom: 0 },
  historyTierDot: { width: 9, height: 9, borderRadius: 5, marginTop: 5 },
  historyMain: { flex: 1 },
  historyTopLine: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  historyTier: { fontSize: typography.caption, fontWeight: typography.black, letterSpacing: 0.5 },
  historyDate: { fontSize: typography.tiny, color: colours.muted, fontWeight: typography.semibold, fontVariant: ['tabular-nums'] },
  historyAdvice: { fontSize: typography.tiny, color: colours.muted, marginTop: 2, lineHeight: 15 },
  section: { marginBottom: spacing.lg },
  sectionLabel: { fontSize: typography.micro, fontWeight: typography.bold, color: colours.teal, letterSpacing: 2, marginBottom: spacing.md },
  explanationText: { fontSize: typography.body, color: colours.offwhite, lineHeight: 22 },
  factorRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md, marginBottom: spacing.sm },
  factorDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
  factorText: { flex: 1, fontSize: typography.body, color: colours.muted, lineHeight: 20 },
  adviceCard: { borderRadius: radius.md, borderWidth: 1.5, borderLeftWidth: 4, padding: spacing.lg, marginBottom: spacing.xl },
  adviceEyebrow: { fontSize: typography.micro, fontWeight: typography.bold, color: colours.teal, letterSpacing: 2, marginBottom: spacing.sm },
  adviceText: { fontSize: typography.body, color: colours.white, fontWeight: typography.semibold, lineHeight: 22 },
  referBtn: { marginBottom: spacing.lg, borderRadius: radius.lg },
  referInner: { borderRadius: radius.lg, padding: spacing.xl, alignItems: 'center', borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)', zIndex: 2 },
  referShadow: { position: 'absolute', bottom: -5, right: -5, left: 5, height: '100%', borderRadius: radius.lg, zIndex: 1, opacity: 0.3 },
  referText: { fontSize: typography.body, fontWeight: typography.black, color: colours.white, letterSpacing: 0.5 },
  referShona: { fontSize: typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: spacing.xs, fontStyle: 'italic' },
  doneBtn: { backgroundColor: colours.card, borderRadius: radius.lg, padding: spacing.xl, alignItems: 'center', borderWidth: 1.5, borderColor: colours.mid, marginBottom: spacing.lg },
  doneBtnText: { fontSize: typography.body, fontWeight: typography.bold, color: colours.muted },
  doneBtnShona: { fontSize: typography.caption, color: colours.muted, fontStyle: 'italic', marginTop: spacing.xs },
});