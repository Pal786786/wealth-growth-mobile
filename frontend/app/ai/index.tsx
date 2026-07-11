/**
 * AI Intelligence Hub — Sprint 7C.1
 * Entry point with 3 sub-modules: Signals, Watchlist, Alerts.
 */
import React from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, TrendingUp, Star, Bell, Brain, Zap, LineChart, Newspaper, CalendarClock, FileText, BarChart3 } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";

export default function AIHub() {
  const { palette } = useTheme();
  const router = useRouter();

  const modules = [
    { id: "signals", label: "AI Signals", desc: "BUY/SELL signals across FX, metals, crypto & indices",
      icon: TrendingUp, route: "/ai/signals", color: "#8B5CF6" },
    { id: "news", label: "Market News", desc: "AI-curated news across Forex, Crypto, Indices & more",
      icon: Newspaper, route: "/ai/news", color: "#3B82F6" },
    { id: "calendar", label: "Economic Calendar", desc: "Fed, ECB, RBI & CPI events with live countdown",
      icon: CalendarClock, route: "/ai/calendar", color: "#10B981" },
    { id: "summary", label: "AI Market Summary", desc: "Intraday / daily / weekly narrative from Claude",
      icon: FileText, route: "/ai/summary", color: "#EF4444" },
    { id: "analytics", label: "Signal Analytics", desc: "Win rate, TP hit rate, confidence edge, ROI",
      icon: BarChart3, route: "/ai/analytics", color: "#0EA5E9" },
    { id: "watchlist", label: "Watchlist", desc: "Track symbols with AI-enriched trend & confidence",
      icon: Star, route: "/ai/watchlist", color: "#F59E0B" },
    { id: "alerts", label: "Price Alerts", desc: "Get notified on price, %, EMA cross, RSI",
      icon: Bell, route: "/ai/alerts", color: "#EC4899" },
  ];

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Brain size={18} color={palette.primary} />
            <Text style={[s.title, { color: palette.textPrimary }]}>AI Intelligence</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
            Powered by Claude Sonnet 4.5 · Deterministic TA Engine
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14 }}>
        <View style={[s.banner, { backgroundColor: palette.primary + "15", borderColor: palette.primary + "30" }]}>
          <Zap size={16} color={palette.primary} />
          <Text style={{ color: palette.textPrimary, fontSize: 12, flex: 1, marginLeft: 8, lineHeight: 17 }}>
            <Text style={{ fontWeight: "800" }}>Sprint 7C.2</Text> — News, Economic Calendar, AI Market Summary and Signal Analytics now live. Powered by Claude Sonnet 4.5.
          </Text>
        </View>

        {modules.map((m) => {
          const Ic = m.icon;
          return (
            <Pressable
              key={m.id}
              onPress={() => router.push(m.route as any)}
              style={({ pressed }) => [s.card, { backgroundColor: pressed ? palette.surface : palette.background, borderColor: palette.border }]}
            >
              <View style={[s.iconBox, { backgroundColor: m.color + "20" }]}>
                <Ic size={22} color={m.color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "900" }}>{m.label}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 3, lineHeight: 15 }}>{m.desc}</Text>
              </View>
              <LineChart size={16} color={palette.textMuted} />
            </Pressable>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 20, fontWeight: "800" },
  banner: { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: 12, borderWidth: 1, marginBottom: 14 },
  card: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 10 },
  iconBox: { width: 46, height: 46, borderRadius: 12, alignItems: "center", justifyContent: "center" },
});
