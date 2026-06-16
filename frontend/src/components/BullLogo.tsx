import React from "react";
import { View, StyleSheet, Text } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Svg, {
  Path, Polyline, Circle, Defs, LinearGradient as SvgLinearGradient, Stop, RadialGradient, G, Filter, FeGaussianBlur, FeMerge, FeMergeNode,
} from "react-native-svg";
import { Colors } from "@/src/theme/colors";

// Aggressive stock-market bull with glowing red eyes
export function BullLogo({
  size = 80,
  withWordmark = false,
  variant = "boxed",
}: { size?: number; withWordmark?: boolean; variant?: "boxed" | "flat" }) {
  const inner = (
    <Svg width={size * 0.8} height={size * 0.8} viewBox="0 0 120 120" fill="none">
      <Defs>
        <SvgLinearGradient id="bullFill" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0%" stopColor="#F8FAFC" />
          <Stop offset="55%" stopColor="#CBD5E1" />
          <Stop offset="100%" stopColor="#64748B" />
        </SvgLinearGradient>
        <SvgLinearGradient id="hornGradient" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0%" stopColor="#FFFFFF" />
          <Stop offset="100%" stopColor="#94A3B8" />
        </SvgLinearGradient>
        <RadialGradient id="eyeGlow" cx="50%" cy="50%" r="50%">
          <Stop offset="0%" stopColor="#FF6B6B" stopOpacity="1" />
          <Stop offset="50%" stopColor="#FF2D2D" stopOpacity="1" />
          <Stop offset="100%" stopColor="#FF2D2D" stopOpacity="0" />
        </RadialGradient>
        <SvgLinearGradient id="arrowGradient" x1="0" y1="1" x2="1" y2="0">
          <Stop offset="0%" stopColor="#10B981" />
          <Stop offset="100%" stopColor="#34D399" />
        </SvgLinearGradient>
      </Defs>

      {/* Subtle red glow halo behind eyes */}
      <Circle cx="42" cy="58" r="11" fill="url(#eyeGlow)" opacity="0.6" />
      <Circle cx="78" cy="58" r="11" fill="url(#eyeGlow)" opacity="0.6" />

      {/* Sharp curved horns (aggressive, swept back & up) */}
      <Path
        d="M14 30 C 8 18, 22 8, 32 14 C 38 18, 42 24, 44 32 C 38 28, 30 27, 22 30 C 18 31, 16 31, 14 30 Z"
        fill="url(#hornGradient)"
        stroke="#0F172A"
        strokeWidth="1.5"
      />
      <Path
        d="M106 30 C 112 18, 98 8, 88 14 C 82 18, 78 24, 76 32 C 82 28, 90 27, 98 30 C 102 31, 104 31, 106 30 Z"
        fill="url(#hornGradient)"
        stroke="#0F172A"
        strokeWidth="1.5"
      />

      {/* Muscular bull head (forward-charging, angular) */}
      <Path
        d="M28 34
           C 32 28, 40 22, 50 22
           L 70 22
           C 80 22, 88 28, 92 34
           L 96 50
           C 96 58, 92 64, 86 68
           L 82 80
           C 80 88, 72 94, 60 94
           C 48 94, 40 88, 38 80
           L 34 68
           C 28 64, 24 58, 24 50 Z"
        fill="url(#bullFill)"
        stroke="#0F172A"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {/* Forehead shadow / muscle definition */}
      <Path d="M44 36 L 60 32 L 76 36 L 72 46 L 60 42 L 48 46 Z" fill="#0F172A" opacity="0.12" />
      <Path d="M38 60 L 44 64 L 42 72 Z" fill="#0F172A" opacity="0.1" />
      <Path d="M82 60 L 76 64 L 78 72 Z" fill="#0F172A" opacity="0.1" />

      {/* Glowing red eyes (intense, angular) */}
      <Path d="M36 54 L 48 52 L 46 62 L 36 60 Z" fill="#0F172A" />
      <Path d="M84 54 L 72 52 L 74 62 L 84 60 Z" fill="#0F172A" />
      <Circle cx="42" cy="57" r="3.2" fill="#FF2D2D" />
      <Circle cx="78" cy="57" r="3.2" fill="#FF2D2D" />
      <Circle cx="41" cy="56" r="1" fill="#FFE5E5" />
      <Circle cx="77" cy="56" r="1" fill="#FFE5E5" />

      {/* Snout / nose ring */}
      <Path d="M48 76 C 48 70, 72 70, 72 76 L 70 86 C 70 90, 64 92, 60 92 C 56 92, 50 90, 50 86 Z" fill="#0F172A" opacity="0.85" />
      <Circle cx="60" cy="84" r="3" fill="none" stroke="#F8FAFC" strokeWidth="1.6" />
      <Circle cx="54" cy="80" r="1.2" fill="#0F172A" />
      <Circle cx="66" cy="80" r="1.2" fill="#0F172A" />

      {/* Rising stock chart arrow across chin */}
      <Polyline
        points="22,104 36,96 48,100 60,88 72,92 84,80 98,84"
        stroke="url(#arrowGradient)"
        strokeWidth="3.2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Arrowhead */}
      <Path d="M98 84 L 106 78 L 104 88 Z" fill="#10B981" />
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
            shadowColor: Colors.brand.primary,
            shadowOpacity: 0.5,
            shadowRadius: size * 0.2,
            shadowOffset: { width: 0, height: size * 0.06 },
            elevation: 8,
          },
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
