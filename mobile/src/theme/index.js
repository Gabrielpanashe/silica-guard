// ─────────────────────────────────────────────
//  SilicaGuard Design Tokens
//  Import this everywhere. Never hardcode values.
// ─────────────────────────────────────────────

export const colours = {
  // Brand
  navy:     '#0A1628',
  mid:      '#111F33',
  card:     '#111F33',
  teal:     '#028090',
  mint:     '#02C39A',
  purple:   '#7B2FBE',

  // Semantic
  white:    '#FFFFFF',
  offwhite: '#F0EDE8',
  muted:    '#8BA0B0',

  // Risk levels
  low:      '#02C39A',   // mint — Low Risk
  watch:    '#FFB800',   // amber — Watch
  refer:    '#FF3B3B',   // red — Refer Now

  // Transparent overlays
  tealFade:   'rgba(2,128,144,0.15)',
  mintFade:   'rgba(2,195,154,0.12)',
  purpleFade: 'rgba(123,47,190,0.15)',
  whiteFade:  'rgba(255,255,255,0.07)',
};

export const typography = {
  // Weights
  black:      '900',
  bold:       '700',
  semibold:   '600',
  medium:     '500',
  regular:    '400',
  light:      '300',

  // Sizes
  display:    58,   // giant stat numbers
  hero:       34,   // brand name, location name
  title:      24,   // screen titles, CTA text
  subtitle:   18,   // card headers
  body:       14,   // normal text
  caption:    12,   // supporting text, Shona subtitles
  tiny:       10,   // labels, eyebrows
  micro:       9,   // ALL CAPS tags
};

export const spacing = {
  xs:   4,
  sm:   8,
  md:  12,
  lg:  16,
  xl:  20,
  xxl: 28,
};

export const radius = {
  sm:   8,
  md:  12,
  lg:  16,
  xl:  24,
  pill: 999,
};

export const riskConfig = {
  GREEN: {
    colour:      colours.low,
    background:  'rgba(2,195,154,0.12)',
    label:       'LOW RISK',
    shona:       'HAPANA NJODZI HURU',
    emoji:       '✅',
    urgency:     null,
    action:      'No immediate referral needed. Rescreen in 6 months.',
    actionShona: 'Hakuna kutumwa chipatara. Dzokera mushure memwedzi 6.',
  },
  YELLOW: {
    colour:      colours.watch,
    background:  'rgba(255,184,0,0.12)',
    label:       'ELEVATED RISK',
    shona:       'TARISA ZVAKANYANYA',
    emoji:       '⚠️',
    urgency:     '3 months',
    action:      'Monitor closely. Rescreen in 3 months.',
    actionShona: 'Tarira zvakanyanya. Ongororwa zvakare mumwedzi mitatu.',
  },
  ORANGE: {
    colour:      '#FF8C00', // Amber/Orange
    background:  'rgba(255,140,0,0.12)',
    label:       'HIGH RISK',
    shona:       'NJODZI YEKUCHIPATARA',
    emoji:       '🟧',
    urgency:     '14 days',
    action:      'Referral recommended within 14 days.',
    actionShona: 'Enda kuchipatara mumazuva gumi nemana.',
  },
  RED: {
    colour:      colours.refer,
    background:  'rgba(255,59,59,0.12)',
    label:       'CRITICAL RISK',
    shona:       'TUMIRA CHIPATARA NHASI',
    emoji:       '🚨',
    urgency:     '48 hours',
    action:      'Immediate referral to Kwekwe District Hospital required.',
    actionShona: 'Tumira chipatara nhasi. Kwekwe District Hospital.',
  },
};

export default { colours, typography, spacing, radius, riskConfig };
