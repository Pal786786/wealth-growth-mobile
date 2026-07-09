/**
 * AI Signal Detail — Sprint 7C.1
 *
 * Deep view of a signal with entry/SL/TP levels, all 10 indicator readings,
 * Claude AI narrative reasoning, quick alert creator, watchlist add.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Star, Bell, Sparkles } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiApi, SignalDetail, Timeframe, sideColor, confidenceLabel } from "@/src/api/aiIntel";
import { errText } from "@/src/utils/errors";

export default function AISignalDetail() {
  const { symbol, tf } = useLocalSearchParams<{ symbol: string; tf?: Timeframe }>();
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [timeframe, setTimeframe] = useState<Timeframe>((tf as Timeframe) || "H1");
  const [sig, setSig] = useState<SignalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyWatch, setBusyWatch] = useState(false);
  const [busyAlert, setBusyAlert] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await aiApi.signal(String(symbol), timeframe, true);
      setSig(s);
    } catch (e) { show("error", errText(e, "Failed to load signal")); }
    finally { setLoading(false); }
  }, [symbol, timeframe, show]);
  useEffect(() => { load(); }, [load]);

  const addToWatch = async () => {
    if (busyWatch) return;
    setBusyWatch(true);
    try {
      await aiApi.addWatchlist(String(symbol));
      show("success", `${symbol} added to watchlist`);
    } catch (e) { show("error", errText(e, "Add to watchlist failed")); }
    finally { setBusyWatch(false); }
  };
  const createAlert = async () => {
    if (busyAlert || !sig) return;
    setBusyAlert(true);
    try {
      // Simple default: price_above @ TP1 if buy, price_below @ TP1 if sell
      const type = sig.side === "buy" ? "price_above" : "price_below";
      const target = sig.side === "buy" ? sig.tp1 : sig.tp1;
      if (!target) throw new Error("no target price");
      await aiApi.createAlert({ type, symbol: String(symbol), target_price: target as any, note: `Auto: TP1 ${sig.side} ${symbol}` });
      show("success", "Alert created for TP1");
    } catch (e) { show("error", errText(e, "Create alert failed")); }
    finally { setBusyAlert(false); }
  };

  if (loading || !sig) {
    return (
      <Screen padded={false}>
        <View style={[s.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
          <Text style={[s.title, { color: palette.textPrimary }]}>{String(symbol)}</Text>
        </View>
        <View style={{ paddingTop: 80, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      </Screen>
    );
  }

  const sc = sideColor(sig.side, palette);
  const TrendIcon = sig.trend === "bullish" ? TrendingUp : sig.trend === "bearish" ? TrendingDown : Minus;

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[s.title, { color: palette.textPrimary }]} numberOfLines={1}>{sig.display}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{sig.asset_class.toUpperCase()} · {sig.timeframe}</Text>
        </View>
        <Pressable onPress={addToWatch} hitSlop={8} disabled={busyWatch}
          style={{ padding: 6, borderRadius: 999, backgroundColor: palette.surface }}>
          <Star size={16} color="#F59E0B" fill="#F59E0B" />
        </Pressable>
        <Pressable onPress={createAlert} hitSlop={8} disabled={busyAlert || !sig.tp1}
          style={{ padding: 6, borderRadius: 999, backgroundColor: palette.surface }}>
          <Bell size={16} color="#EC4899" />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        {/* HERO */}
        <View style={[s.hero, { backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <View style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6, backgroundColor: sc }}>
              <Text style={{ color: "#fff", fontSize: 13, fontWeight: "900" }}>{sig.side.toUpperCase()}</Text>
            </View>
            <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: confColor(sig.confidence_pct) }}>
              <Text style={{ color: "#fff", fontSize: 12, fontWeight: "900" }}>{sig.confidence_pct}% {confidenceLabel(sig.confidence_pct)}</Text>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <TrendIcon size={14} color={sig.trend === "bullish" ? palette.success : sig.trend === "bearish" ? palette.danger : palette.textMuted} />
              <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{sig.trend}</Text>
            </View>
          </View>

          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 8 }}>
            Signal strength: <Text style={{ color: palette.textPrimary, fontWeight: "900" }}>{sig.signal_strength.replace("_", " ")}</Text>{" · "}
            RR: <Text style={{ color: palette.textPrimary, fontWeight: "900" }}>1:{sig.risk_reward_ratio}</Text>
          </Text>

          {sig.side !== "hold" && (
            <View style={{ marginTop: 14 }}>
              <Row label="Entry"     value={sig.entry}     palette={palette} bold />
              <Row label="Stop Loss" value={sig.stop_loss} palette={palette} color={palette.danger} />
              <Row label="Take Profit 1" value={sig.tp1} palette={palette} color={palette.success} />
              <Row label="Take Profit 2" value={sig.tp2} palette={palette} color={palette.success} />
              <Row label="Take Profit 3" value={sig.tp3} palette={palette} color={palette.success} />
              {sig.risk_pips != null && <Row label="Risk" value={`${sig.risk_pips} pips`} palette={palette} />}
              {sig.expires_at && <Row label="Expires" value={new Date(sig.expires_at).toLocaleString()} palette={palette} small />}
            </View>
          )}
        </View>

        {/* Timeframe switcher */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 10, gap: 6 }}>
          {(["M15", "H1", "H4", "D1"] as Timeframe[]).map((t) => (
            <Pressable key={t} onPress={() => setTimeframe(t)}
              style={[s.chip, { backgroundColor: timeframe === t ? palette.primary : palette.surface, borderColor: palette.border }]}>
              <Text style={{ color: timeframe === t ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{t}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* AI Explanation */}
        {sig.ai_explanation && (
          <View style={[s.aiCard, { backgroundColor: palette.primary + "10", borderColor: palette.primary + "40" }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <Sparkles size={14} color={palette.primary} />
              <Text style={{ color: palette.primary, fontSize: 11, fontWeight: "900", letterSpacing: 0.5 }}>AI ANALYSIS · CLAUDE SONNET 4.5</Text>
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 12, lineHeight: 18 }}>
              {sig.ai_explanation}
            </Text>
          </View>
        )}

        {/* Reason hits */}
        {sig.reason_hits && sig.reason_hits.length > 0 && (
          <View style={{ paddingHorizontal: 14, marginTop: 12 }}>
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>WHY THIS SIGNAL</Text>
            {sig.reason_hits.map((h, i) => (
              <View key={i} style={{ flexDirection: "row", alignItems: "flex-start", gap: 6, marginBottom: 5 }}>
                <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: palette.primary, marginTop: 6 }} />
                <Text style={{ color: palette.textPrimary, fontSize: 12, flex: 1, lineHeight: 17 }}>{h}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Indicators */}
        {sig.indicator_summary && (
          <View style={{ paddingHorizontal: 14, marginTop: 16 }}>
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>TECHNICAL INDICATORS ({sig.timeframe})</Text>
            <View style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, overflow: "hidden" }}>
              {sig.indicator_summary.map((r, i) => (
                <View key={i} style={[s.indRow, { borderBottomColor: palette.border, borderBottomWidth: i < sig.indicator_summary!.length - 1 ? StyleSheet.hairlineWidth : 0 }]}>
                  <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", width: 100 }}>{r.name}</Text>
                  <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", flex: 1 }}>{r.value}</Text>
                  <Text style={{ color: verdictColor(r.verdict, palette), fontSize: 10, fontWeight: "800" }}>{r.verdict}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

function verdictColor(v: string, palette: any) {
  if (v.includes("bullish") || v.includes("up") || v === "strong trend" || v.includes("above")) return palette.success;
  if (v.includes("bearish") || v.includes("down") || v.includes("below") || v.includes("overbought")) return palette.danger;
  if (v.includes("oversold")) return palette.warning;
  return palette.textMuted;
}
function confColor(n: number) {
  if (n >= 85) return "#10B981"; if (n >= 70) return "#3B82F6"; if (n >= 55) return "#F59E0B"; return "#94A3B8";
}
function Row({ label, value, palette, color, bold, small }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 }}>
      <Text style={{ color: palette.textMuted, fontSize: small ? 10 : 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: small ? 11 : 13, fontWeight: bold ? "900" : "800", fontVariant: ["tabular-nums"] }}>
        {value}
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 18, fontWeight: "800" },
  hero: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  aiCard: { marginHorizontal: 14, padding: 12, borderRadius: 12, borderWidth: 1 },
  sectionTitle: { fontSize: 10, fontWeight: "900", letterSpacing: 0.5, marginBottom: 8 },
  indRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 9, gap: 8 },
});
