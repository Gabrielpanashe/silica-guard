import {
  StyleSheet, Text, View, TouchableOpacity,
  SafeAreaView, ScrollView, Animated,
} from 'react-native';
import { useState, useRef, useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { colours, typography, spacing, radius } from '../theme';

// ─────────────────────────────────────────────────────────────
//  SCREENING QUESTIONS
//  question_code matches what POST /api/screen expects
//  answer_score feeds into the risk engine
// ─────────────────────────────────────────────────────────────
const QUESTIONS = [
  {
    code: 'DUST_SUPPRESSION',
    en: 'When drilling or crushing, is water used to suppress dust?',
    sn: 'Pakudhirira kana kupwanya, mvura inoshandiswa kudzvanya guruva here?',
    answers: [
      { label: 'Always',        shona: 'Nguva dzose',      value: 'always',    score: 0 },
      { label: 'Sometimes',     shona: 'Dzimwe nguva',     value: 'sometimes', score: 2 },
      { label: 'Rarely',        shona: 'Kazhinji kwete',   value: 'rarely',    score: 4 },
      { label: 'Never',         shona: 'Haina',            value: 'never',     score: 5 },
    ],
  },
  {
    code: 'PPE_USE',
    en: 'How often do you wear a dust mask or respirator underground?',
    sn: 'Kangani unoisa mask yeguruva kana respirator pasi pasi?',
    answers: [
      { label: 'Always',        shona: 'Nguva dzose',      value: 'always',    score: 0 },
      { label: 'Most of time',  shona: 'Kazhinji',         value: 'mostly',    score: 1 },
      { label: 'Sometimes',     shona: 'Dzimwe nguva',     value: 'sometimes', score: 3 },
      { label: 'Never',         shona: 'Haina',            value: 'never',     score: 5 },
    ],
  },
  {
    code: 'COUGH_DURATION',
    en: 'Do you have a cough that has lasted more than 3 weeks?',
    sn: 'Une chikosoro chakagara kupfuura mavhiki matatu here?',
    answers: [
      { label: 'No cough',      shona: 'Handina chikosoro', value: 'none',     score: 0 },
      { label: 'Yes, mild',     shona: 'Hongu, zvishoma',   value: 'mild',     score: 3 },
      { label: 'Yes, severe',   shona: 'Hongu, zvakanyanya',value: 'severe',   score: 5 },
    ],
  },
  {
    code: 'BREATHLESSNESS',
    en: 'Do you get short of breath when walking on flat ground?',
    sn: 'Unoshaya mweya pakufamba pasi pane goho here?',
    caption: 'MRC Dyspnoea Scale — Grade 2+',
    answers: [
      { label: 'No',            shona: 'Kwete',             value: 'no',       score: 0 },
      { label: 'Slight',        shona: 'Zvishoma',          value: 'slight',   score: 2 },
      { label: 'Yes, stops me', shona: 'Hongu, ndinomira',  value: 'yes',      score: 5 },
    ],
  },
  {
    code: 'CHEST_PAIN',
    en: 'Do you experience chest pain or tightness?',
    sn: 'Unorwadza chipfuva kana kunzwa kupfigwa here?',
    answers: [
      { label: 'Never',         shona: 'Haina',             value: 'never',    score: 0 },
      { label: 'Occasionally',  shona: 'Dzimwe nguva',      value: 'occasional',score: 2 },
      { label: 'Frequently',    shona: 'Kazhinji',          value: 'frequent', score: 4 },
    ],
  },
  {
    code: 'WEIGHT_LOSS',
    en: 'Have you lost significant weight in the last 3 months without trying?',
    sn: 'Warasika uzito pakati pemwedzi mitatu yapfuura pasina kuedza here?',
    answers: [
      { label: 'No',            shona: 'Kwete',             value: 'no',       score: 0 },
      { label: 'A little',      shona: 'Zvishoma',          value: 'little',   score: 2 },
      { label: 'Significantly', shona: 'Zvakanyanya',       value: 'significant',score: 4 },
    ],
  },
  {
    code: 'TB_HISTORY',
    en: 'Have you ever been treated for tuberculosis (TB)?',
    sn: 'Wakambobatwa chirwere cheTB (denda) here?',
    caption: 'TB raises silicosis risk ×3–5',
    answers: [
      { label: 'No',            shona: 'Kwete',             value: 'no',       score: 0 },
      { label: 'Yes, completed',shona: 'Hongu, ndapedza',   value: 'completed',score: 3 },
      { label: 'Yes, ongoing',  shona: 'Hongu, ndichiripo',  value: 'ongoing',  score: 5 },
    ],
  },
  {
    code: 'VENTILATION',
    en: 'Is there adequate ventilation or airflow in your work area underground?',
    sn: 'Pane mhepo yakakwana munzvimbo yako yekushanda pasi?',
    answers: [
      { label: 'Yes, good',     shona: 'Hongu, yakanaka',   value: 'good',     score: 0 },
      { label: 'Poor',          shona: 'Isina kunaka',      value: 'poor',     score: 3 },
      { label: 'None at all',   shona: 'Hapana zvachose',   value: 'none',     score: 5 },
    ],
  },
  {
    code: 'PRIOR_DIAGNOSIS',
    en: 'Has a doctor ever told you that you have a lung disease?',
    sn: 'Chiremba akambokuudza kuti une chirwere chemapfubvu here?',
    answers: [
      { label: 'No',            shona: 'Kwete',             value: 'no',       score: 0 },
      { label: 'Suspected',     shona: 'Anofunga',          value: 'suspected',score: 3 },
      { label: 'Yes, confirmed',shona: 'Hongu, yakasimbiswa',value: 'confirmed',score: 5 },
    ],
  },
  {
    code: 'FAMILY_HISTORY',
    en: 'Has anyone in your family died from a lung disease related to mining?',
    sn: 'Pane munhu wemhuri yako akafa nemapfubvu echirwere chemigodhi here?',
    answers: [
      { label: 'No',            shona: 'Kwete',             value: 'no',       score: 0 },
      { label: 'Not sure',      shona: 'Handizivi',         value: 'unsure',   score: 1 },
      { label: 'Yes',           shona: 'Hongu',             value: 'yes',      score: 2 },
    ],
  },
];

// ─────────────────────────────────────────────────────────────
//  OFFLINE SCORING — fallback when Claude API is unavailable
//  Returns GREEN / YELLOW / ORANGE / RED
// ─────────────────────────────────────────────────────────────
export const offlineScore = (miner, answers) => {
  const answerTotal = answers.reduce((sum, a) => sum + a.answer_score, 0);
  const exposureBase = (miner.years_score || 0) * (miner.job_risk || 1);
  const total = answerTotal + exposureBase;

  if (total <= 8)  return 'GREEN';
  if (total <= 16) return 'YELLOW';
  if (total <= 24) return 'ORANGE';
  return 'RED';
};

export default function QuestionScreen({ navigation, route }) {
  const { miner } = route.params;
  const [current, setCurrent]   = useState(0);
  const [answers, setAnswers]   = useState([]);
  const [selected, setSelected] = useState(null);
  const fadeAnim = useRef(new Animated.Value(1)).current;

  const question = QUESTIONS[current];
  const progress = (current + 1) / QUESTIONS.length;

  useEffect(() => {
    // Fade in when question changes
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
      // Fade out then advance
      Animated.timing(fadeAnim, {
        toValue: 0, duration: 180, useNativeDriver: true,
      }).start(() => {
        setAnswers(newAnswers);
        setCurrent(c => c + 1);
        setSelected(null);
      });
    } else {
      // All questions done → go to Result
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
          <Text style={s.minerSub}>{miner.job_label} · {miner.years_label}</Text>
        </View>
        <View style={s.stepBadge}>
          <Text style={s.stepText}>{current + 1} / {QUESTIONS.length}</Text>
        </View>
      </View>

      {/* ── PROGRESS BAR ── */}
      <View style={s.progressTrack}>
        <Animated.View style={[s.progressFill, { width: `${progress * 100}%` }]} />
      </View>

      {/* ── QUESTION ── */}
      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Animated.View style={{ opacity: fadeAnim }}>

          {/* Question number */}
          <Text style={s.qNumber}>QUESTION {current + 1}</Text>

          {/* English */}
          <Text style={s.qText}>{question.en}</Text>

          {/* Shona */}
          <Text style={s.qShona}>{question.sn}</Text>

          {/* Clinical caption if present */}
          {question.caption && (
            <View style={s.captionBadge}>
              <Text style={s.captionText}>⚕ {question.caption}</Text>
            </View>
          )}

          {/* ── ANSWER OPTIONS ── */}
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

          {/* ── NEXT BUTTON ── */}
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
  headerMeta: { flex: 1 },
  minerName: {
    fontSize: typography.caption,
    fontWeight: typography.bold,
    color: colours.white,
  },
  minerSub: {
    fontSize: typography.micro,
    color: colours.muted,
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

  // Progress bar
  progressTrack: {
    height: 4,
    backgroundColor: colours.card,
    marginHorizontal: spacing.xl,
    borderRadius: radius.pill,
    marginBottom: spacing.lg,
  },
  progressFill: {
    height: 4,
    backgroundColor: colours.teal,
    borderRadius: radius.pill,
  },

  // Scroll
  scroll: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
  },

  // Question
  qNumber: {
    fontSize: typography.micro,
    fontWeight: typography.bold,
    color: colours.teal,
    letterSpacing: 2,
    marginBottom: spacing.md,
  },
  qText: {
    fontSize: 22,
    fontWeight: typography.black,
    color: colours.white,
    lineHeight: 30,
    letterSpacing: -0.3,
    marginBottom: spacing.md,
  },
  qShona: {
    fontSize: typography.body,
    color: colours.muted,
    fontStyle: 'italic',
    lineHeight: 22,
    marginBottom: spacing.md,
  },
  captionBadge: {
    alignSelf: 'flex-start',
    backgroundColor: colours.tealFade,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: colours.teal,
    marginBottom: spacing.lg,
  },
  captionText: {
    fontSize: typography.tiny,
    color: colours.teal,
    fontWeight: typography.semibold,
  },

  // Answers
  answersContainer: {
    gap: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
  answerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colours.card,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colours.mid,
    padding: spacing.lg,
    gap: spacing.md,
  },
  answerCardSelected: {
    borderColor: colours.teal,
    backgroundColor: colours.tealFade,
  },
  answerRadio: {
    width: 22, height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colours.muted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  answerRadioSelected: { borderColor: colours.teal },
  answerRadioInner: {
    width: 11, height: 11,
    borderRadius: 6,
    backgroundColor: colours.teal,
  },
  answerText: { flex: 1 },
  answerLabel: {
    fontSize: typography.body,
    fontWeight: typography.semibold,
    color: colours.muted,
  },
  answerLabelSelected: { color: colours.white },
  answerShona: {
    fontSize: typography.tiny,
    color: colours.muted,
    fontStyle: 'italic',
    marginTop: 2,
  },
  answerShonaSelected: { color: colours.teal },
  selectedCheck: {
    width: 26, height: 26,
    borderRadius: 13,
    backgroundColor: colours.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkMark: {
    fontSize: 13,
    color: colours.white,
    fontWeight: typography.bold,
  },

  // Next button
  nextBtn: { marginTop: spacing.sm },
  nextBtnDisabled: { opacity: 0.4 },
  nextInner: {
    backgroundColor: colours.teal,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: colours.mint,
    zIndex: 2,
  },
  nextInnerDisabled: {
    backgroundColor: colours.mid,
    borderColor: colours.mid,
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