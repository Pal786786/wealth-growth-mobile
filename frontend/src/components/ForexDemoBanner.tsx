import React from "react";
import { View, Text } from "react-native";
import { Shield } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";

/**
 * Persistent DEMO disclosure shown on every Forex screen.
 * Required by Phase 1 scope — paper trading only, no real money.
 */
export function ForexDemoBanner({ compact = false }: { compact?: boolean }) {
  const { palette } = useTheme();
  return (
    <View style={{
      backgroundColor: "#F59E0B15",
      borderColor: "#F59E0B",
      borderWidth: 1,
      borderRadius: 12,
      paddingVertical: compact ? 8 : 10,
      paddingHorizontal: 12,
      flexDirection: "row",
      alignItems: "center",
      gap: 10,
    }}>
      <Shield color="#F59E0B" size={compact ? 16 : 18} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: "#F59E0B", fontWeight: "800", fontSize: compact ? 11 : 12, letterSpacing: 0.4 }}>
          DEMO TRADING
        </Text>
        <Text style={{ color: palette.textPrimary, fontSize: compact ? 10 : 11, fontWeight: "600", marginTop: 1 }}>
          Virtual Balance ₹10,00,000 · No Real Money Involved
        </Text>
      </View>
    </View>
  );
}
