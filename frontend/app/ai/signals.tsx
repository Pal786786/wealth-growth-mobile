/**
 * AI Signals List — Sprint 7C.1
 *
 * Filterable list of signals across all asset classes. 2-second-agnostic
 * (data is deterministic per bar). Pull-to-refresh + tap → detail.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, TrendingUp, TrendingDown, Minus } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiApi, SignalListRow, Timeframe, Side, sideColor, confidenceLabel } from "@/src/api/aiIntel";
import { errText } from "@/src/utils/errors";

const TF: Timeframe[] = ["M15", "H1", "H4", "D1"];
const CLASSES = [
  { id: "", label: "All" }, { id: "forex", label: "FX" }, { id: "metals", label: "Metals" },
  { id: "indices", label: "Indices" }, { id: "crypto", label: "Crypto" }, { id: "energies", label: "Energy" },
];

export default function AISignals() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [timeframe, setTimeframe] = useState<Timeframe>("H1");
  const [assetClass, setAssetClass] = useState<string>("");
  const [sideFilter, setSideFilter] = useState<Side | "">("");
  const [minConf, setMinConf] = useState<number>(0);
  const [rows, setRows] = useState<SignalListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await aiApi.signals({
        timeframe, asset_class: assetClass || undefined,
        side: sideFilter || undefined, min_confidence: minConf, limit: 30,
      });
      setRows(r.signals);
    } catch (e) { show("error", errText(e, "Failed to load signals")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [timeframe, assetClass, sideFilter, minConf, show]);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>AI Signals</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{rows.length} live · {timeframe}</Text>
        </View>
      </View>

      {/* Filter row */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 6 }}>
        {TF.map((tf) => (
          <Pressable key={tf} onPress={() => setTimeframe(tf)}
            style={[s.chip, { backgroundColor: timeframe === tf ? palette.primary : palette.surface, borderColor: palette.border }]}>
            <Text style={{ color: timeframe === tf ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{tf}</Text>
          </Pressable>
        ))}
        <View style={{ width: 1, backgroundColor: palette.border, marginHorizontal: 6 }} />
        {CLASSES.map((c) => (
          <Pressable key={c.id || "all"} onPress={() => setAssetClass(c.id)}
            style={[s.chip, { backgroundColor: assetClass === c.id ? palette.primary : palette.surface, borderColor: palette.border }]}>
            <Text style={{ color: assetClass === c.id ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{c.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 6, gap: 6 }}>
        {[
          { id: "", label: "BUY & SELL" }, { id: "buy" as Side, label: "BUY only" }, { id: "sell" as Side, label: "SELL only" },
        ].map((o) => (
          <Pressable key={o.id || "all"} onPress={() => setSideFilter(o.id as any)}
            style={[s.chipSmall, { backgroundColor: sideFilter === o.id ? palette.textPrimary : palette.surface, borderColor: palette.border }]}>
            <Text style={{ color: sideFilter === o.id ? palette.background : palette.textPrimary, fontSize: 10, fontWeight: "800" }}>{o.label}</Text>
          </Pressable>
        ))}
        {[0, 60, 75, 85].map((mc) => (
          <Pressable key={mc} onPress={() => setMinConf(mc)}
            style={[s.chipSmall, { backgroundColor: minConf === mc ? "#F59E0B" : palette.surface, borderColor: palette.border }]}>
            <Text style={{ color: minConf === mc ? "#fff" : palette.textPrimary, fontSize: 10, fontWeight: "800" }}>Conf ≥ {mc || "any"}%</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {loading && <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>}
        {!loading && rows.length === 0 && (
          <View style={{ padding: 40, alignItems: "center" }}>
            <Text style={{ color: palette.textMuted, fontSize: 13 }}>No signals match your filters</Text>
          </View>
        )}
        {rows.map((r) => <SignalCard key={`${r.symbol}-${r.bar_index}`} sig={r} palette={palette}
          onPress={() => router.push(`/ai/signal/${r.symbol}?tf=${r.timeframe}` as any)} />)}
      </ScrollView>
    </Screen>
  );
}

function SignalCard({ sig, palette, onPress }: { sig: SignalListRow; palette: any; onPress: () => void }) {
  const sc = sideColor(sig.side, palette);
  const trendIc = sig.trend === "bullish" ? TrendingUp : sig.trend === "bearish" ? TrendingDown : Minus;
  const TrendIcon = trendIc;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.card, { backgroundColor: pressed ? palette.surface : palette.background, borderBottomColor: palette.border }]}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "900" }}>{sig.display}</Text>
          <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4, backgroundColor: sc + "22" }}>
            <Text style={{ color: sc, fontSize: 10, fontWeight: "900" }}>{sig.side.toUpperCase()}</Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
            <TrendIcon size={11} color={sig.trend === "bullish" ? palette.success : sig.trend === "bearish" ? palette.danger : palette.textMuted} />
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>{sig.trend}</Text>
          </View>
        </View>
        <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 3 }}>
          {sig.asset_class.toUpperCase()} · {sig.timeframe} · {sig.signal_strength.replace("_", " ")}
        </Text>
        {sig.side !== "hold" && (
          <View style={{ flexDirection: "row", gap: 10, marginTop: 6 }}>
            <MiniLabel label="Entry" value={String(sig.entry)} palette={palette} />
            <MiniLabel label="SL" value={String(sig.stop_loss)} palette={palette} color={palette.danger} />
            <MiniLabel label="TP1" value={String(sig.tp1)} palette={palette} color={palette.success} />
          </View>
        )}
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: confColor(sig.confidence_pct) + "22" }}>
          <Text style={{ color: confColor(sig.confidence_pct), fontSize: 13, fontWeight: "900" }}>
            {sig.confidence_pct}%
          </Text>
        </View>
        <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700", marginTop: 2 }}>{confidenceLabel(sig.confidence_pct)}</Text>
        {sig.risk_reward_ratio > 0 && (
          <Text style={{ color: palette.textMuted, fontSize: 9, marginTop: 2 }}>RR 1:{sig.risk_reward_ratio}</Text>
        )}
      </View>
    </Pressable>
  );
}
function MiniLabel({ label, value, palette, color }: any) {
  return (
    <View>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 11, fontWeight: "900" }}>{value}</Text>
    </View>
  );
}
function confColor(n: number) {
  if (n >= 85) return "#10B981";
  if (n >= 70) return "#3B82F6";
  if (n >= 55) return "#F59E0B";
  return "#94A3B8";
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 18, fontWeight: "800" },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  chipSmall: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: 1 },
  card: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
});
