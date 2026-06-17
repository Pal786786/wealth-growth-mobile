import React from "react";
import { View, StyleSheet, Text } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Svg, {
  Path, Polyline, Circle, Defs, LinearGradient as SvgLinearGradient, Stop, RadialGradient,
} from "react-native-svg";
import { Colors } from "@/src/theme/colors";
import { shadow } from "@/src/utils/shadow";

/**
 * Premium investment-bull logo for My Funding Bank.
 * - Confident (not aggressive) bull head, head-up posture.
 * - Curved horns whose left tip is replaced by an upward stock-chart line ending in a gold arrow.
 * - Subtle gold horn tips and gold "M" monogram on the forehead — wealth + brand cues.
 * - Sky blue / deep blue body gradient with white highlights, no red.
 */
export function BullLogo({
  size = 80,
  withWordmark = false,
  variant = "boxed",
}: { size?: number; withWordmark?: boolean; variant?: "boxed" | "flat" }) {
  const inner = (
    <Svg width={size * 0.82} height={size * 0.82} viewBox="0 0 120 120" fill="none">
      <Defs>
        <SvgLinearGradient id="bullBody" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0%" stopColor="#7DD3FC" />
          <Stop offset="60%" stopColor="#38BDF8" />
          <Stop offset="100%" stopColor="#0EA5E9" />
        </SvgLinearGradient>
        <SvgLinearGradient id="hornBlue" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0%" stopColor="#FFFFFF" />
          <Stop offset="100%" stopColor="#7DD3FC" />
        </SvgLinearGradient>
        <SvgLinearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0%" stopColor="#FCD34D" />
          <Stop offset="100%" stopColor="#F59E0B" />
        </SvgLinearGradient>
        <RadialGradient id="shine" cx="35%" cy="30%" r="60%">
          <Stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.5" />
          <Stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </RadialGradient>
      </Defs>

      {/* Curved blue horns (left & right) */}
      <Path
        d="M22 38 C 14 28, 18 16, 30 14 C 38 14, 44 22, 46 32 C 38 30, 28 32, 22 38 Z"
        fill="url(#hornBlue)"
        stroke="#0F172A"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <Path
        d="M98 38 C 106 28, 102 16, 90 14 C 82 14, 76 22, 74 32 C 82 30, 92 32, 98 38 Z"
        fill="url(#hornBlue)"
        stroke="#0F172A"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      {/* Gold horn tips */}
      <Circle cx="22" cy="36" r="3" fill="url(#gold)" stroke="#92400E" strokeWidth="0.6" />
      <Circle cx="98" cy="36" r="3" fill="url(#gold)" stroke="#92400E" strokeWidth="0.6" />

      {/* Bull head — confident, smooth, head-up profile */}
      <Path
        d="M32 40
           C 36 32, 44 26, 54 26
           L 66 26
           C 76 26, 84 32, 88 40
           L 92 56
           C 92 64, 88 70, 82 74
           L 78 84
           C 76 90, 70 94, 60 94
           C 50 94, 44 90, 42 84
           L 38 74
           C 32 70, 28 64, 28 56 Z"
        fill="url(#bullBody)"
        stroke="#0F172A"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      {/* Soft top highlight */}
      <Path
        d="M36 38 C 42 30, 52 28, 60 28 C 68 28, 78 30, 84 38 L 80 48 C 72 42, 64 41, 60 41 C 56 41, 48 42, 40 48 Z"
        fill="url(#shine)"
      />

      {/* Calm dark eyes (small, not glowing) */}
      <Circle cx="46" cy="56" r="2.6" fill="#0F172A" />
      <Circle cx="74" cy="56" r="2.6" fill="#0F172A" />
      <Circle cx="46.8" cy="55.2" r="0.9" fill="#FFFFFF" />
      <Circle cx="74.8" cy="55.2" r="0.9" fill="#FFFFFF" />

      {/* Soft snout / nose ring */}
      <Path d="M48 76 C 48 70, 72 70, 72 76 L 70 84 C 70 88, 64 90, 60 90 C 56 90, 50 88, 50 84 Z" fill="#0F172A" />
      <Circle cx="60" cy="83" r="2.8" fill="none" stroke="#FCD34D" strokeWidth="1.4" />

      {/* Stock-market growth line rising from chest up & off to the right, with gold arrow tip */}
      <Polyline
        points="24,108 36,100 46,104 56,92 66,96 78,82 92,86"
        stroke="#10B981"
        strokeWidth="3.2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Gold arrowhead at the end of the chart line */}
      <Path d="M92 86 L 104 76 L 102 92 Z" fill="url(#gold)" stroke="#92400E" strokeWidth="0.8" strokeLinejoin="round" />

      {/* Subtle gold "M" monogram on forehead */}
      <Path
        d="M52 36 L 54 46 L 60 40 L 66 46 L 68 36"
        stroke="url(#gold)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </Svg>
  );

  if (variant === "flat") {
    return (
      <View style={s.row}>
        {inner}
        {withWordmark ? <Wordmark /> : null}
      </View>
    );
  }

  return (
    <View style={s.row}>
      <LinearGradient
        colors={[Colors.brand.navy, "#1E293B", Colors.brand.secondary]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[
          s.badge,
          {
            width: size,
            height: size,
            borderRadius: size * 0.26,
          },
          shadow({
            color: Colors.brand.primary,
            opacity: 0.45,
            radius: size * 0.18,
            offsetY: size * 0.05,
            elevation: 8,
          }),
        ]}
      >
        {inner}
      </LinearGradient>
      {withWordmark ? <Wordmark /> : null}
    </View>
  );
}

function Wordmark() {
  return (
    <View>
      <Text style={s.brand}>My Funding</Text>
      <Text style={s.brandSecondary}>BANK</Text>
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  badge: { alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#1E293B" },
  brand: { fontSize: 22, fontWeight: "800", color: "#0F172A", letterSpacing: -0.5 },
  brandSecondary: { fontSize: 12, fontWeight: "800", color: "#0EA5E9", letterSpacing: 3 },
});
