import { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, Modal, ScrollView,
  TextInput, StyleSheet,
} from 'react-native';
import { colours, typography, spacing, radius } from '../theme';
import { getMines } from '../services/api';

/**
 * MineSitePicker — dropdown for the outreach-site field, backed by
 * GET /api/mines (11 seeded Midlands sites). Built with only core
 * React Native (Modal + ScrollView + TouchableOpacity) rather than
 * @react-native-picker/picker — that package isn't in package.json, and
 * adding a new native dependency this close to the demo without being
 * able to test a rebuild here was judged too risky.
 *
 * Falls back to a plain text field if the mines list fails to load or is
 * empty (offline, cold Render instance, etc.) — the outreach-site field
 * has never been a hard requirement for a screening to proceed, and this
 * shouldn't become one now.
 *
 * Props:
 *   value      string   — current site name (free text — mines.id is a
 *                          suggestion list, not a foreign key; see
 *                          backend/routers/mines.py)
 *   onChange   function(string)
 */
export default function MineSitePicker({ value, onChange }) {
  const [mines, setMines]     = useState([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [modalOpen, setModalOpen]   = useState(false);
  const [customText, setCustomText] = useState(value || '');

  useEffect(() => {
    let cancelled = false;
    getMines()
      .then((list) => { if (!cancelled) setMines(list); })
      .catch(() => { if (!cancelled) setLoadFailed(true); });
    return () => { cancelled = true; };
  }, []);

  const select = (name) => {
    onChange(name);
    setModalOpen(false);
  };

  const submitCustom = () => {
    const trimmed = customText.trim();
    if (trimmed) onChange(trimmed);
    setModalOpen(false);
  };

  // Mines list unusable (offline / empty / error) — plain text input,
  // same behaviour as before this component existed.
  if (loadFailed || (mines.length === 0 && !modalOpen)) {
    return (
      <TextInput
        style={s.fallbackInput}
        value={value}
        onChangeText={onChange}
        autoCapitalize="words"
        placeholder="Type the mine site"
        placeholderTextColor={colours.muted}
      />
    );
  }

  return (
    <View>
      <TouchableOpacity style={s.trigger} onPress={() => setModalOpen(true)} activeOpacity={0.75}>
        <Text style={s.triggerText}>{value || 'Select a mine site'}</Text>
        <Text style={s.chevron}>▾</Text>
      </TouchableOpacity>

      <Modal visible={modalOpen} animationType="slide" transparent onRequestClose={() => setModalOpen(false)}>
        <View style={s.overlay}>
          <View style={s.sheet}>
            <View style={s.sheetHeader}>
              <Text style={s.sheetTitle}>Select Mine Site</Text>
              <TouchableOpacity onPress={() => setModalOpen(false)}>
                <Text style={s.closeText}>Done</Text>
              </TouchableOpacity>
            </View>

            <ScrollView style={s.list}>
              {mines.map((mine) => (
                <TouchableOpacity
                  key={mine.id}
                  style={s.option}
                  onPress={() => select(mine.name)}
                  activeOpacity={0.7}
                >
                  <View>
                    <Text style={s.optionName}>{mine.name}</Text>
                    {!!mine.district && <Text style={s.optionDistrict}>{mine.district}, {mine.province}</Text>}
                  </View>
                  {value === mine.name && <Text style={s.checkmark}>✓</Text>}
                </TouchableOpacity>
              ))}
            </ScrollView>

            <View style={s.customRow}>
              <Text style={s.customLabel}>Site not listed? Type it below:</Text>
              <View style={s.customInputRow}>
                <TextInput
                  style={s.customInput}
                  value={customText}
                  onChangeText={setCustomText}
                  placeholder="e.g. Mvuma Alluvial Site"
                  placeholderTextColor={colours.muted}
                  autoCapitalize="words"
                />
                <TouchableOpacity style={s.customBtn} onPress={submitCustom} activeOpacity={0.8}>
                  <Text style={s.customBtnText}>Use</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  fallbackInput: {
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colours.mid,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    fontSize: typography.body, color: colours.white,
  },
  trigger: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colours.mid,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
  },
  triggerText: { fontSize: typography.body, color: colours.white, flex: 1 },
  chevron: { fontSize: typography.body, color: colours.muted, marginLeft: spacing.sm },

  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colours.navy, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl,
    maxHeight: '75%', paddingTop: spacing.lg, borderWidth: 1, borderColor: colours.mid, borderBottomWidth: 0,
  },
  sheetHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: spacing.xl, paddingBottom: spacing.md,
    borderBottomWidth: 0.5, borderBottomColor: colours.card,
  },
  sheetTitle: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  closeText: { fontSize: typography.body, color: colours.teal, fontWeight: typography.semibold },

  list: { paddingHorizontal: spacing.xl },
  option: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colours.card,
  },
  optionName: { fontSize: typography.body, color: colours.white, fontWeight: typography.medium },
  optionDistrict: { fontSize: typography.tiny, color: colours.muted, marginTop: 2 },
  checkmark: { fontSize: typography.body, color: colours.mint, fontWeight: typography.black },

  customRow: {
    paddingHorizontal: spacing.xl, paddingVertical: spacing.lg,
    borderTopWidth: 0.5, borderTopColor: colours.card,
  },
  customLabel: { fontSize: typography.tiny, color: colours.muted, marginBottom: spacing.sm },
  customInputRow: { flexDirection: 'row', gap: spacing.sm },
  customInput: {
    flex: 1, backgroundColor: colours.card, borderRadius: radius.md,
    borderWidth: 1.5, borderColor: colours.mid,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    fontSize: typography.caption, color: colours.white,
  },
  customBtn: {
    backgroundColor: colours.teal, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, justifyContent: 'center',
  },
  customBtnText: { fontSize: typography.caption, color: colours.white, fontWeight: typography.bold },
});
