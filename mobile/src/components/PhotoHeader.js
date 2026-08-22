import { StyleSheet, Text, View, TouchableOpacity, ImageBackground } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { colours, typography, spacing, radius } from '../theme';

// Same photo LandingScreen.js uses full-bleed, reused here as a compact
// header band (16 August) so the photo treatment isn't only on Landing —
// see ReferralScreen.js and WorklistScreen.js for where this shows up.
const BG_IMAGE = require('../../assets/landing-page.jpg');

/**
 * PhotoHeader — drop-in replacement for a screen's plain back-button/title
 * header row, with the outreach photo + a dark scrim behind it instead of
 * a flat surface colour. Text stays white regardless of the app's light
 * theme, same reasoning as Landing's own copy — it's sitting on the photo,
 * not the page surface.
 *
 * Props:
 *   title       string
 *   shonaTitle  string (optional)
 *   onBack      function — omit to hide the back button (rare; every
 *               current caller supplies one)
 *   right       ReactNode (optional) — e.g. a count badge
 */
export default function PhotoHeader({ title, shonaTitle, onBack, right }) {
  return (
    <ImageBackground source={BG_IMAGE} resizeMode="cover" style={s.root}>
      <LinearGradient
        colors={['rgba(6,13,28,0.5)', 'rgba(6,13,28,0.75)']}
        style={StyleSheet.absoluteFill}
      />
      <View style={s.row}>
        {onBack ? (
          <TouchableOpacity onPress={onBack} style={s.backBtn} activeOpacity={0.75}>
            <Ionicons name="arrow-back" size={18} color={colours.white} />
          </TouchableOpacity>
        ) : (
          <View style={s.backBtnGhost} />
        )}
        <View style={s.text}>
          <Text style={s.title} numberOfLines={1}>{title}</Text>
          {!!shonaTitle && <Text style={s.shona} numberOfLines={1}>{shonaTitle}</Text>}
        </View>
        {right}
      </View>
    </ImageBackground>
  );
}

const s = StyleSheet.create({
  root: { height: 118, justifyContent: 'flex-end' },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: radius.sm,
    backgroundColor: 'rgba(255,255,255,0.16)', alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(255,255,255,0.35)',
  },
  backBtnGhost: { width: 36, height: 36 },
  text: { flex: 1 },
  title: { fontSize: typography.subtitle, fontWeight: typography.bold, color: colours.white },
  shona: { fontSize: typography.micro, color: 'rgba(255,255,255,0.75)', fontStyle: 'italic', marginTop: 1 },
});
