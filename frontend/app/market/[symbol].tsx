import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { ChevronLeft, TrendingUp, TrendingDown, Star } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { marketApi, type Quote } from "@/src/api/market";

export default function SymbolDetail() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { symbol } = useLocalSearchParams<{ symbol: string }>();
  const [q, setQ] = useState<Quote | null>(null);
  const [hist, setHist] = useState<{ t: number; close: number }[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [quote, history] = await Promise.all([marketApi.quote(String(symbol)), marketApi.history(String(symbol), 48)]);
      setQ(quote); setHist(history.points);
    } catch (e: any) { show("error", e?.response?.data?.detail || "Failed to load"); router.back(); }
    finally { setLoading(false); }
  }, [symbol, show, router]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading || !q) return <Screen><ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} /></Screen>;

  const isUp = q.change_pct >= 0;
  const tint = isUp ? "#10B981" : "#EF4444";
  const min = Math.min(...hist.map((x) => x.close));
  const max = Math.max(...hist.map((x) => x.close));
  const range = Math.max(1, max - min);

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>{q.name}</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 80 }}>
        <LinearGradient colors={isUp ? ["#052E1F", "#065F46"] : ["#3B0A0A", "#7F1D1D"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <Text style={s.heroLabel}>{q.symbol} · {String(q.category ?? "market").toUpperCase()}</Text>
          <Text style={s.heroPrice}>{q.currency === "INR" ? "₹" : "$"}{q.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
            {isUp ? <TrendingUp color="#fff" size={18} /> : <TrendingDown color="#fff" size={18} />}
            <Text style={s.heroChange}>{q.change > 0 ? "+" : ""}{q.change} ({q.change_pct > 0 ? "+" : ""}{q.change_pct}%)</Text>
          </View>
          <Text style={s.heroSub}>Day range: {q.day_low.toFixed(2)} — {q.day_high.toFixed(2)} · Provider: {q.provider}</Text>
        </LinearGradient>

        <Card>
          <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "800", marginBottom: 10 }}>PRICE TREND (last {hist.length} bars)</Text>
          <View style={{ height: 140, flexDirection: "row", alignItems: "flex-end", gap: 2 }}>
            {hist.map((pt, i) => {
              const h = ((pt.close - min) / range) * 130 + 6;
              return <View key={i} style={{ flex: 1, height: h, backgroundColor: tint, borderRadius: 2 }} />;
            })}
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 6 }}>
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>{min.toFixed(2)}</Text>
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>{max.toFixed(2)}</Text>
          </View>
        </Card>

        <Card>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Info label="Prev Close" value={q.prev_close} palette={palette} />
            <Info label="Day High" value={q.day_high} palette={palette} />
            <Info label="Day Low" value={q.day_low} palette={palette} />
          </View>
        </Card>

        <Button label="Add to Watchlist" icon={<Star color="#fff" size={16} />} onPress={async () => {
          try { await marketApi.addWatch(q.symbol); show("success", "Added to watchlist"); }
          catch (e: any) { show("error", e?.response?.data?.detail || "Failed"); }
        }} />
      </ScrollView>
    </Screen>
  );
}

function Info({ label, value, palette }: { label: string; value: number; palette: any }) {
  return (<View style={{ alignItems: "center", flex: 1 }}>
    <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800" }}>{label.toUpperCase()}</Text>
    <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "900", marginTop: 4 }}>{value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
  </View>);
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { flex: 1, fontSize: 18, fontWeight: "800" },
  hero: { padding: 22, borderRadius: 22, gap: 2 },
  heroLabel: { color: "rgba(255,255,255,0.75)", fontSize: 10, fontWeight: "800", letterSpacing: 1.2 },
  heroPrice: { color: "#fff", fontSize: 36, fontWeight: "900", marginTop: 4, letterSpacing: -1 },
  heroChange: { color: "#fff", fontSize: 14, fontWeight: "800" },
  heroSub: { color: "rgba(255,255,255,0.7)", fontSize: 11, marginTop: 10 },
});
