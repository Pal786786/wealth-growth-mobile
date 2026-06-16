import React from "react";
import { View, StyleSheet, Text } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Svg, { Path, Polyline, Circle } from "react-native-svg";

// Stylized bull head + rising chart logo for "My Funding Bank"
export function BullLogo({ size = 80, withWordmark = false }: { size?: number; withWordmark?: boolean }) {
  return (
    <View style={s.row}>
      <LinearGradient
        colors={["#38BDF8", "#0EA5E9"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[s.badge, { width: size, height: size, borderRadius: size * 0.28 }]}
      >
        <Svg width={size * 0.7} height={size * 0.7} viewBox="0 0 100 100" fill="none">
          {/* Bull horns */}
          <Path d="M14 28 C 20 18, 32 18, 38 28 L 36 36 C 28 30, 22 30, 16 36 Z" fill="#FFFFFF" />
          <Path d="M86 28 C 80 18, 68 18, 62 28 L 64 36 C 72 30, 78 30, 84 36 Z" fill="#FFFFFF" />
          {/* Bull face */}
          <Path d="M28 38 C 28 28, 40 24, 50 24 C 60 24, 72 28, 72 38 L 72 58 C 72 70, 62 78, 50 78 C 38 78, 28 70, 28 58 Z" fill="#FFFFFF" />
          {/* Eyes */}
          <Circle cx="42" cy="48" r="3" fill="#0F172A" />
          <Circle cx="58" cy="48" r="3" fill="#0F172A" />
          {/* Nose ring */}
          <Circle cx="50" cy="64" r="4" fill="#0F172A" />
          {/* Rising chart arrow inside */}
          <Polyline points="34,70 42,62 48,66 56,56 64,60" stroke="#0EA5E9" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </Svg>
      </LinearGradient>
      {withWordmark ? (
        <View>
          <Text style={s.brand}>My Funding</Text>
          <Text style={s.brandSecondary}>Bank</Text>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  badge: { alignItems: "center", justifyContent: "center" },
  brand: { fontSize: 22, fontWeight: "800", color: "#0F172A", letterSpacing: -0.5 },
  brandSecondary: { fontSize: 14, fontWeight: "700", color: "#0EA5E9", letterSpacing: 1, textTransform: "uppercase" },
});
