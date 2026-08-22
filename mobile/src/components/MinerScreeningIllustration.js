import Svg, { Circle, Ellipse, Rect, Path, G } from 'react-native-svg';
import { colours, light } from '../theme';

/**
 * MinerScreeningIllustration — flat vector scene of a health worker
 * screening a miner (hard hat, stethoscope, clipboard), for LandingScreen's
 * hero (16 August). There's no image-generation tool available in this
 * environment, so this is hand-authored SVG rather than a generated raster
 * photo — same flat-illustration technique the medical-booking-app
 * reference mock itself uses for its onboarding screen (a drawn
 * stethoscope, not a photo), just on-topic for SilicaGuard specifically.
 *
 * Bust-style (shoulders-up) pair, no full limbs — the reference mock's own
 * illustration is similarly abstracted (floating stethoscope + decorative
 * icons, no full body), so this matches that level of stylisation rather
 * than reaching for anatomical realism.
 */
export default function MinerScreeningIllustration({ width = 300, height = 208 }) {
  return (
    <Svg width={width} height={height} viewBox="0 0 320 220">
      {/* ground shadow */}
      <Ellipse cx={160} cy={204} rx={124} ry={11} fill="rgba(11,61,145,0.08)" />

      {/* scattered accent dots, echoing the reference mock's decorative dots */}
      <Circle cx={30} cy={40} r={4} fill={light.accentEnd} opacity={0.3} />
      <Circle cx={44} cy={54} r={2.5} fill={light.accentEnd} opacity={0.25} />
      <Circle cx={292} cy={36} r={3.5} fill={colours.mint} opacity={0.35} />
      <Circle cx={16} cy={150} r={3} fill={light.accentEnd} opacity={0.25} />

      {/* ── MINER (left) ── */}
      <G>
        {/* jumpsuit / shoulders */}
        <Rect x={44} y={122} width={102} height={84} rx={36} fill="#16305C" />
        {/* reflective safety stripe */}
        <Rect x={44} y={150} width={102} height={9} fill={colours.watch} opacity={0.9} />
        {/* neck */}
        <Rect x={83} y={110} width={24} height={20} fill="#8D5B3F" />
        {/* head */}
        <Circle cx={95} cy={86} r={30} fill="#8D5B3F" />
        {/* hard hat dome + brim */}
        <Path d="M64 66 Q95 22 126 66 Z" fill={colours.watch} />
        <Ellipse cx={95} cy={66} rx={37} ry={7.5} fill={colours.watch} />
        <Circle cx={95} cy={38} r={3.5} fill="#E0A400" />
        {/* face */}
        <Circle cx={85} cy={90} r={2.6} fill="#16305C" />
        <Circle cx={106} cy={90} r={2.6} fill="#16305C" />
        <Path d="M84 100 Q95 107 107 100" stroke="#16305C" strokeWidth={2.5} fill="none" strokeLinecap="round" />
      </G>

      {/* ── HEALTH WORKER (right) ── */}
      <G>
        {/* uniform / shoulders */}
        <Rect x={174} y={118} width={102} height={84} rx={36} fill={light.accentEnd} />
        {/* collar */}
        <Path d="M210 118 L225 136 L240 118 Z" fill="#FFFFFF" opacity={0.9} />
        {/* neck */}
        <Rect x={213} y={104} width={24} height={18} fill="#C6875A" />
        {/* head */}
        <Circle cx={225} cy={80} r={28} fill="#C6875A" />
        {/* short hair */}
        <Path d="M197 76 A28 25 0 0 1 253 76 L253 66 A28 22 0 0 0 197 66 Z" fill="#2E1C10" />
        {/* face */}
        <Circle cx={216} cy={83} r={2.4} fill="#2E1C10" />
        <Circle cx={235} cy={83} r={2.4} fill="#2E1C10" />
        <Path d="M215 92 Q225 98 236 92" stroke="#2E1C10" strokeWidth={2.3} fill="none" strokeLinecap="round" />
        {/* ID badge with medical-cross accent */}
        <Rect x={213} y={142} width={22} height={16} rx={3} fill="#FFFFFF" />
        <Rect x={222} y={145} width={4} height={10} fill={colours.mint} />
        <Rect x={219} y={148} width={10} height={4} fill={colours.mint} />
      </G>

      {/* ── STETHOSCOPE, worker's ear to miner's chest ── */}
      <Path
        d="M207 128 C178 150 158 138 132 152"
        stroke={light.accentStart}
        strokeWidth={4}
        fill="none"
        strokeLinecap="round"
      />
      <Circle cx={207} cy={126} r={4.5} fill={light.accentStart} />
      <Circle cx={132} cy={152} r={9} fill="#FFFFFF" stroke={light.accentStart} strokeWidth={2.5} />
      <Circle cx={132} cy={152} r={16} stroke={light.accentEnd} strokeWidth={1.5} fill="none" opacity={0.45} />
      <Circle cx={132} cy={152} r={23} stroke={light.accentEnd} strokeWidth={1} fill="none" opacity={0.22} />

      {/* ── CLIPBOARD, screening result ── */}
      <G transform="rotate(8 262 172)">
        <Rect x={245} y={150} width={34} height={44} rx={4} fill="#FFFFFF" stroke={light.border} strokeWidth={1.5} />
        <Rect x={255} y={146} width={14} height={8} rx={2} fill={light.accentStart} />
        <Rect x={251} y={160} width={22} height={3} rx={1.5} fill={light.border} />
        <Rect x={251} y={167} width={22} height={3} rx={1.5} fill={light.border} />
        <Path d="M251 179 L257 185 L269 171" stroke={colours.mint} strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </G>
    </Svg>
  );
}
