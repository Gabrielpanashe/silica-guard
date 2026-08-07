import {
  StyleSheet, Text, View, TouchableOpacity,
  SafeAreaView, ScrollView, Animated,
} from 'react-native';
import { useState, useRef, useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';

// ─────────────────────────────────────────────────────────────
//  SCREENING QUESTIONS
//  Verbatim from backend/questions.py — DO NOT edit text or
//  codes without the doctor's sign-off AND backend update.
//  Last synced: 2026-08-05
// ─────────────────────────────────────────────────────────────
const QUESTIONS = [
  {
    code: 'YEARS_UNDERGROUND',
    en: 'How many years have you worked underground or near drilling?',
    sn: 'Makangoshanda mangani emakore pasi pevhu kana pedyo nekuchera?',
    answers: [
      { label: 'Under 2 years',  shona: 'Pasi pemakore 2', value: 'under_2',  score: 1 },
      { label: '2 – 5 years',    shona: 'Makore 2-5',      value: '2_to_5',   score: 2 },
      { label: '5 – 10 years',   shona: 'Makore 5-10',     value: '5_to_10',  score: 3 },
      { label: 'Over 10 years',  shona: 'Makore 10+',      value: 'over_10',  score: 5 },
    ],
  },
  {
    code: 'JOB_ROLE',
    en: 'What is your main job at the mine or quarry?',
    sn: 'Basa rako guru muhomwe kana mupurazi ndeiripi?',
    answers: [
      { label: 'Rock drilling / blasting', shona: 'Kudira mwena (Rock drilling/blasting)', value: 'drilling', score: 5 },
      { label: 'Loading / hauling',        shona: 'Kutakura/Kusaina (Loading/Hauling)',    value: 'loading',  score: 3 },
      { label: 'Processing / crushing',   shona: 'Kumisikidza (Processing/Crushing)',     value: 'crushing', score: 4 },
      { label: 'Surface / other',         shona: 'Panze / Mamwe (Surface / other)',       value: 'surface',  score: 1 },
    ],
  },
  {
    code: 'WET_DRILLING',
    en: 'Is water used during drilling at your site to suppress dust?',
    sn: 'Kushandiswa kwemvura pakudira mwena here (wet drilling)?',
    answers: [
      { label: 'Yes, always', shona: 'Hongu, nguva dzose', value: 'always',    score: 0 },
      { label: 'Sometimes',   shona: 'Dzimwe nguva',       value: 'sometimes', score: 2 },
      { label: 'No / I don\'t know', shona: 'Kwete/Handizivi', value: 'never', score: 4 },
    ],
  },
  {
    code: 'PPE_USE',
    en: 'Do you wear a dust mask or respiratory protection while working?',
    sn: 'Unopfeka mask kana chekuchengetedza kufefera (PPE) paunoshanda?',
    answers: [
      { label: 'Always (N95/FFP2 mask)', shona: 'Nguva dzose (N95/FFP2)', value: 'always_n95', score: 0 },
      { label: 'Sometimes',              shona: 'Dzimwe nguva',            value: 'sometimes',  score: 2 },
      { label: 'Cloth or surgical mask', shona: 'Mask yejira/surgical',   value: 'cloth_mask', score: 3 },
      { label: 'Never',                  shona: 'Handipfeki',              value: 'never',      score: 5 },
    ],
  },
  {
    code: 'COUGH_DURATION',
    en: 'Do you have a cough that has lasted more than 3 weeks?',
    sn: 'Une kuhema (cough) inoenderera kupfuura mavhiki matatu here?',
    answers: [
      { label: 'No',                    shona: 'Kwete',            value: 'no',    score: 0 },
      { label: 'Yes, mild',             shona: 'Hongu, zvishoma',  value: 'mild',  score: 3 },
      { label: 'Yes, persistent/severe',shona: 'Hongu, zvakanyanya',value: 'severe',score: 5 },
    ],
  },
  {
    code: 'BREATHLESSNESS',
    en: 'Do you get short of breath doing activities that didn\'t tire you before?',
    sn: 'Unorwadziwa kufema (shortness of breath) uchiita zvinhu zvawaiita nyore?',
    caption: 'MRC Dyspnoea Scale',
    answers: [
      { label: 'No',                          shona: 'Kwete',                          value: 'none',     score: 0 },
      { label: 'Walking on flat / climbing',  shona: 'Pakufamba chiuno/kukwira magumo', value: 'moderate', score: 3 },
      { label: 'Getting dressed / resting',   shona: 'Pakugeza/kupfeka',               value: 'severe',   score: 5 },
    ],
  },
  {
    code: 'TB_HISTORY',
    en: 'Have you ever been told you have TB or received TB treatment?',
    sn: 'Wakamborehwa TB (tuberculosis) kana kupihwa mishonga yaTB here?',
    caption: 'TB raises silicosis risk ×3–5',
    answers: [
      { label: 'No',           shona: 'Kwete',            value: 'no',      score: 0 },
      { label: 'Yes, completed',shona: 'Hongu, yakapera', value: 'past',    score: 3 },
      { label: 'Yes, ongoing', shona: 'Hongu, ndiri kurwa',value: 'current', score: 4 },
    ],
  },
  {
    code: 'WEIGHT_LOSS',
    en: 'Have you lost weight without trying in the past 3 months?',
    sn: 'Wakaonda (lost weight) usingade kuzviita mumwedzi mitatu yapfuura here?',
    answers: [
      { label: 'No',          shona: 'Kwete',        value: 'no',          score: 0 },
      { label: 'A little',    shona: 'Zvishoma',     value: 'some',        score: 2 },
      { label: 'Significant', shona: 'Zvakanyanya',  value: 'significant', score: 4 },
    ],
  },
  {
    code: 'CHEST_PAIN',
    en: 'Do you experience chest pain or chest tightness?',
    sn: 'Une kurwadziwa kwechifu (chest pain or tightness)?',
    answers: [
      { label: 'No',           shona: 'Kwete',                   value: 'no',        score: 0 },
      { label: 'Sometimes',    shona: 'Dzimwe nguva',             value: 'sometimes', score: 3 },
      { label: 'Often / severe',shona: 'Nguva dzose/zvakashata', value: 'severe',    score: 5 },
    ],
  },
  {
    code: 'PRIOR_LUNG_DIAGNOSIS',
    en: 'Has a doctor ever told you that you have a lung problem?',
    sn: 'Chiremba akakuudza here kuti une dambudziko repamapfubvu (lung problem)?',
    answers: [
      { label: 'No',  shona: 'Kwete', value: 'no',  score: 0 },
      { label: 'Yes', shona: 'Hongu', value: 'yes', score: 5 },
    ],
  },
];

// ─────────────────────────────────────────────────────────────
//  OFFLINE SCORING — fallback when backend is unavailable
//  Mirrors backend/services/ai_risk_engine.py thresholds
//  Returns GREEN / YELLOW / ORANGE / RED
// ─────────────────────────────────────────────────────────────
export const offlineScore = (answers) => {
  const total = answers.reduce((sum, a) => sum + a.answer_score, 0);
  // Safety override: PRIOR_LUNG_DIAGNOSIS = yes → minimum ORANGE
  const hasPriorDiagnosis = answers.find(
    a => a.question_code === 'PRIOR_LUNG_DIAGNOSIS' && a.answer_value === 'yes'
  );
  // Safety override: TB ongoing → minimum ORANGE
  const hasTBOngoing = answers.find(
    a => a.question_code === 'TB_HISTORY' && a.answer_value === 'current'
  );

  let tier;
  if (total <= 8)  tier = 'GREEN';
  else if (total <= 16) tier = 'YELLOW';
  else if (total <= 24) tier = 'ORANGE';
  else tier = 'RED';

  // Apply safety overrides — RED can never be missed
  if (hasPriorDiagnosis || hasTBOngoing) {
    if (tier === 'GREEN' || tier === 'YELLOW') tier = 'ORANGE';
  }

  return { tier, total, provisional: true };
};

export { QUESTIONS };

export default function QuestionScreen({ navigation, route }) {
  const { miner } = route.params;
  const [current, setCurrent]   = useState(0);
  const [answers, setAnswers]   = useState([]);
  const [selected, setSelected] = useState(null);
  const fadeAnim = useRef(new Animated.Value(1)).current;

  const question = QUESTIONS[current];
  const progress = (current + 1) / QUESTIONS.length;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1, duration: 250, useNativeDriver: true,
    }).start();
  }, [current]);

  const handleSelect = (answer) => setSelected(answer);

  const handleNext = () => {
    if (!selected) return;

    const newAnswers = [
      ...answers,
      {
        question_code: question.code,
        answer_value:  selected.value,
        answer_score:  selected.score,
      },
    ];

    if (current < QUESTIONS.length - 1) {
      Animated.timing(fadeAnim, {
        toValue: 0, duration: 180, useNativeDriver: true,
      }).start(() => {
        setAnswers(newAnswers);
        setCurrent(c => c + 1);
        setSelected(null);
      });
    } else {
      navigation.navigate('Result', { miner, answers: newAnswers });
    }
  };

  const handleBack = () => {
    if (current === 0) {
      navigation.goBack();
    } else {
      Animated.timing(fadeAnim, {
        toValue: 0, duration: 180, useNativeDriver: true,
      }).start(() => {
        setAnswers(a => a.slice(0, -1));
        setCurrent(c => c - 1);
        setSelected(null);
      });
    }
  };

  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />

      {/* ── HEADER ── */}
      <View style={s.header}>
        <TouchableOpacity onPress={handleBack} style={s.backBtn}>
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <View style={s.headerMeta}>
          <Text style={s.minerName}>{miner.name}</Text>
          <Text style={s.minerSub}>{miner.mine_site}</Text>
        </View>
        <View style={s.stepBadge}>
          <Text style={s.stepText}>{current + 1} / {QUESTIONS.length}</Text>
        </View>
      </View>

      {/* ── PROGRESS BAR ── */}
      <View style={s.progressTrack}>
        <View style={[s.progressFill, { width: `${progress * 100}%` }]} />
      </View>

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Animated.View style={{ opacity: fadeAnim }}>

          <Text style={s.qNumber}>QUESTION {current + 1} OF {QUESTIONS.length}</Text>
          <Text style={s.qText}>{question.en}</Text>
          <Text style={s.qShona}>{question.sn}</Text>

          {question.caption && (
            <View style={s.captionBadge}>
              <Text style={s.captionText}>⚕ {question.caption}</Text>
            </View>
          )}

          <View style={s.answersContainer}>
            {question.answers.map((ans) => {
              const isSelected = selected?.value === ans.value;
              return (
                <TouchableOpacity
                  key={ans.value}
                  style={[s.answerCard, isSelected && s.answerCardSelected]}
                  onPress={() => handleSelect(ans)}
                  activeOpacity={0.75}
                >
                  <View style={[s.answerRadio, isSelected && s.answerRadioSelected]}>
                    {isSelected && <View style={s.answerRadioInner} />}
                  </View>
                  <View style={s.answerText}>
                    <Text style={[s.answerLabel, isSelected && s.answerLabelSelected]}>
                      {ans.label}
                    </Text>
                    <Text style={[s.answerShona, isSelected && s.answerShonaSelected]}>
                      {ans.shona}
                    </Text>
                  </View>
                  {isSelected && (
                    <View style={s.selectedCheck}>
                      <Text style={s.checkMark}>✓</Text>
                    </View>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity
            style={[s.nextBtn, !selected && s.nextBtnDisabled]}
            onPress={handleNext}
            activeOpacity={selected ? 0.88 : 1}
          >
            <View style={[s.nextInner, !selected && s.nextInnerDisabled]}>
              <Text style={s.nextText}>
                {current < QUESTIONS.length - 1 ? 'NEXT QUESTION' : 'SUBMIT SCREENING'}
              </Text>
              <Text style={s.nextShona}>
                {current < QUESTIONS.length - 1 ? 'Mubvunzo Unotevera →' : 'Tuma Kuongorora →'}
              </Text>
            </View>
            {selected && <View style={s.nextShadow} />}
          </TouchableOpacity>

          <View style={{ height: spacing.xxl }} />
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colours.navy },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md, gap: spacing.md,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.sm,
    backgroundColor: colours.card, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: colours.teal,
  },
  backArrow: { fontSize: 18, color: colours.teal },
  headerMeta: { flex: 1 },
  minerName: { fontSize: typography.caption, fontWeight: typography.bold, color: colours.white },
  minerSub: { fontSize: typography.micro, color: colours.muted, marginTop: 1 },
  stepBadge: {
    backgroundColor: colours.tealFade, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: colours.teal,
  },
  stepText: { fontSize: typography.tiny, color: colours.teal, fontWeight: typography.bold },
  progressTrack: {
    height: 4, backgroundColor: colours.card,
    marginHorizontal: spacing.xl, borderRadius: radius.pill, marginBottom: spacing.lg,
  },
  progressFill: { height: 4, backgroundColor: colours.teal, borderRadius: radius.pill },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.sm },
  qNumber: {
    fontSize: typography.micro, fontWeight: typography.bold,
    color: colours.teal, letterSpacing: 2, marginBottom: spacing.md,
  },
  qText: {
    fontSize: 22, fontWeight: typography.black, color: colours.white,
    lineHeight: 30, letterSpacing: -0.3, marginBottom: spacing.md,
  },
  qShona: {
    fontSize: typography.body, color: colours.muted,
    fontStyle: 'italic', lineHeight: 22, marginBottom: spacing.md,
  },
  captionBadge: {
    alignSelf: 'flex-start', backgroundColor: colours.tealFade,
    borderRadius: radius.pill, paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs, borderWidth: 1,
    borderColor: colours.teal, marginBottom: spacing.lg,
  },
  captionText: { fontSize: typography.tiny, color: colours.teal, fontWeight: typography.semibold },
  answersContainer: { gap: spacing.md, marginTop: spacing.sm, marginBottom: spacing.xl },
  answerCard: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colours.mid, padding: spacing.lg, gap: spacing.md,
  },
  answerCardSelected: { borderColor: colours.teal, backgroundColor: colours.tealFade },
  answerRadio: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: colours.muted,
    alignItems: 'center', justifyContent: 'center',
  },
  answerRadioSelected: { borderColor: colours.teal },
  answerRadioInner: { width: 11, height: 11, borderRadius: 6, backgroundColor: colours.teal },
  answerText: { flex: 1 },
  answerLabel: { fontSize: typography.body, fontWeight: typography.semibold, color: colours.muted },
  answerLabelSelected: { color: colours.white },
  answerShona: { fontSize: typography.tiny, color: colours.muted, fontStyle: 'italic', marginTop: 2 },
  answerShonaSelected: { color: colours.teal },
  selectedCheck: {
    width: 26, height: 26, borderRadius: 13,
    backgroundColor: colours.teal, alignItems: 'center', justifyContent: 'center',
  },
  checkMark: { fontSize: 13, color: colours.white, fontWeight: typography.bold },
  nextBtn: { marginTop: spacing.sm },
  nextBtnDisabled: { opacity: 0.4 },
  nextInner: {
    backgroundColor: colours.teal, borderRadius: radius.lg,
    padding: spacing.xl, alignItems: 'center',
    borderWidth: 2, borderColor: colours.mint, zIndex: 2,
  },
  nextInnerDisabled: { backgroundColor: colours.mid, borderColor: colours.mid },
  nextShadow: {
    position: 'absolute', bottom: -5, right: -5, left: 5,
    height: '100%', borderRadius: radius.lg,
    backgroundColor: colours.mint, zIndex: 1, opacity: 0.3,
  },
  nextText: {
    fontSize: typography.body, fontWeight: typography.black,
    color: colours.white, letterSpacing: 0.5,
  },
  nextShona: {
    fontSize: typography.caption, color: 'rgba(255,255,255,0.7)',
    marginTop: spacing.xs, fontStyle: 'italic',
  },
});
