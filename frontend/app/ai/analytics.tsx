/**
 * Signal Analytics Dashboard — Sprint 7C.2
 * Win rate, TP hit rate, confidence accuracy, ROI.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, BarChart3 } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiNewsApi, AnalyticsOverview, AnalyticsBySymbol, AnalyticsByTimeframe, SignalHistoryRow, outcomeColor, outcomeLabel } from "@/src/api/aiNews";
import { errText } from "@/src/utils/errors";

const WINDOWS: Array<{ id: number | null; label: string }> = [
  { id: null, label: "All-time" },
  { id: 7, label: "7 days" },
  { id: 30, label: "30 days" },
  { id: 90, label: "90 days" },
];

function StatCard({ label, value, sub, palette, tint }: any) {
  return (
    <View style={[st.stat, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700", letterSpacing: 0.4 }}>{label}</Text>
      <Text style={{ color: tint || palette.textPrimary, fontSize: 20, fontWeight: "900", marginTop: 4 }}>{value}</Text>
      {sub ? <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 2 }}>{sub}</Text> : null}
    </View>
  );
}

export default function SignalAnalytics() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [windowDays, setWindowDays] = useState<number | null>(30);
  const [ov, setOv] = useState<AnalyticsOverview | null>(null);
  const [bySym, setBySym] = useState<AnalyticsBySymbol[]>([]);
  const [byTf, setByTf] = useState<AnalyticsByTimeframe[]>([]);
  const [history, setHistory] = useState<SignalHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [o, s1, t1, h1] = await Promise.all([
        aiNewsApi.analyticsOverview(windowDays ?? undefined),
        aiNewsApi.analyticsBySymbol(windowDays ?? undefined, 10),
        aiNewsApi.analyticsByTimeframe(windowDays ?? undefined),
        aiNewsApi.analyticsHistory(15),
      ]);
      setOv(o); setBySym(s1.rows); setByTf(t1.rows); setHistory(h1.items);
    } catch (e) { show("error", errText(e, "Failed to load analytics")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [windowDays, show]);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen padded={false}>
      <View style={[st.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <BarChart3 size={18} color={palette.primary} />
            <Text style={[st.title, { color: palette.textPrimary }]}>Signal Analytics</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
            Live outcomes tracked for all AI signals
          </Text>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 44 }} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 6 }}>
        {WINDOWS.map((w) => (
          <Pressable key={String(w.id)} onPress={() => setWindowDays(w.id)} style={[st.pill, { backgroundColor: windowDays === w.id ? palette.primary : palette.surface, borderColor: windowDays === w.id ? palette.primary : palette.border }]}>
            <Text style={{ color: windowDays === w.id ? "#fff" : palette.textPrimary, fontSize: 12, fontWeight: "700" }}>{w.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {loading ? (
        <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      ) : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />} contentContainerStyle={{ padding: 12, paddingBottom: 40 }}>
          <View style={st.grid}>
            <StatCard label="WIN RATE" value={`${ov?.win_rate_pct ?? 0}%`} sub={`${ov?.tp_hits ?? 0} wins / ${ov?.resolved_signals ?? 0} resolved`} palette={palette} tint={palette.success} />
            <StatCard label="TP1 HIT RATE" value={`${ov?.tp1_hit_rate_pct ?? 0}%`} sub={`TP2 ${ov?.tp2_hit_rate_pct ?? 0}% · TP3 ${ov?.tp3_hit_rate_pct ?? 0}%`} palette={palette} />
            <StatCard label="SUM ROI" value={`${(ov?.sum_roi_pct ?? 0) >= 0 ? "+" : ""}${ov?.sum_roi_pct ?? 0}%`} sub={`avg ${(ov?.avg_roi_pct ?? 0) >= 0 ? "+" : ""}${ov?.avg_roi_pct ?? 0}% / signal`} palette={palette} tint={(ov?.sum_roi_pct ?? 0) >= 0 ? palette.success : palette.danger} />
            <StatCard label="CONF. EDGE" value={`${(ov?.confidence_edge_pct ?? 0) >= 0 ? "+" : ""}${ov?.confidence_edge_pct ?? 0}%`} sub={`wins ${ov?.win_avg_confidence_pct ?? 0}% vs losses ${ov?.loss_avg_confidence_pct ?? 0}%`} palette={palette} tint={(ov?.confidence_edge_pct ?? 0) >= 0 ? palette.success : palette.danger} />
          </View>

          <View style={[st.summary, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", letterSpacing: 0.4, marginBottom: 8 }}>OUTCOME BREAKDOWN</Text>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ alignItems: "center" }}><Text style={{ color: palette.success, fontSize: 18, fontWeight: "900" }}>{ov?.tp_hits ?? 0}</Text><Text style={{ color: palette.textMuted, fontSize: 10 }}>TP hits</Text></View>
              <View style={{ alignItems: "center" }}><Text style={{ color: palette.danger, fontSize: 18, fontWeight: "900" }}>{ov?.sl_hits ?? 0}</Text><Text style={{ color: palette.textMuted, fontSize: 10 }}>SL hits</Text></View>
              <View style={{ alignItems: "center" }}><Text style={{ color: palette.textMuted, fontSize: 18, fontWeight: "900" }}>{ov?.expired ?? 0}</Text><Text style={{ color: palette.textMuted, fontSize: 10 }}>Expired</Text></View>
              <View style={{ alignItems: "center" }}><Text style={{ color: "#F59E0B", fontSize: 18, fontWeight: "900" }}>{ov?.pending_signals ?? 0}</Text><Text style={{ color: palette.textMuted, fontSize: 10 }}>Open</Text></View>
              <View style={{ alignItems: "center" }}><Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "900" }}>{ov?.total_signals ?? 0}</Text><Text style={{ color: palette.textMuted, fontSize: 10 }}>Total</Text></View>
            </View>
          </View>

          {byTf.length > 0 && (
            <View style={{ marginTop: 14 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", marginBottom: 6, letterSpacing: 0.5 }}>BY TIMEFRAME</Text>
              {byTf.map((r) => (
                <View key={r.timeframe} style={[st.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "900", fontSize: 13, width: 60 }}>{r.timeframe}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 11, width: 60 }}>{r.resolved} sig</Text>
                  <Text style={{ color: palette.success, fontSize: 13, fontWeight: "800", width: 60 }}>{r.win_rate_pct}%</Text>
                  <Text style={{ color: (r.sum_roi ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 12, fontWeight: "800", flex: 1, textAlign: "right" }}>
                    {(r.sum_roi ?? 0) >= 0 ? "+" : ""}{r.sum_roi}%
                  </Text>
                </View>
              ))}
            </View>
          )}

          {bySym.length > 0 && (
            <View style={{ marginTop: 14 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", marginBottom: 6, letterSpacing: 0.5 }}>TOP SYMBOLS</Text>
              {bySym.map((r) => (
                <View key={r.symbol} style={[st.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "900", fontSize: 13, width: 90 }}>{r.symbol}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 11, width: 60 }}>{r.resolved} sig</Text>
                  <Text style={{ color: palette.success, fontSize: 13, fontWeight: "800", width: 60 }}>{r.win_rate_pct}%</Text>
                  <Text style={{ color: (r.sum_roi ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 12, fontWeight: "800", flex: 1, textAlign: "right" }}>
                    {(r.sum_roi ?? 0) >= 0 ? "+" : ""}{r.sum_roi}%
                  </Text>
                </View>
              ))}
            </View>
          )}

          {history.length > 0 && (
            <View style={{ marginTop: 14 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", marginBottom: 6, letterSpacing: 0.5 }}>RECENT SIGNALS</Text>
              {history.map((h) => (
                <View key={`${h.symbol}-${h.timeframe}-${h.generated_at}`} style={[st.histRow, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Text style={{ color: palette.textPrimary, fontWeight: "900", fontSize: 13 }}>{h.symbol}</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 10 }}>· {h.timeframe}</Text>
                      <Text style={{ color: h.side === "buy" ? palette.success : palette.danger, fontSize: 10, fontWeight: "800" }}>{h.side.toUpperCase()}</Text>
                    </View>
                    <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 2 }}>Entry {h.entry} · conf {h.confidence_pct}%</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={{ color: outcomeColor(h.outcome, palette), fontSize: 11, fontWeight: "800" }}>{outcomeLabel(h.outcome)}</Text>
                    {h.roi_pct != null && (
                      <Text style={{ color: (h.roi_pct ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 11, fontWeight: "800", marginTop: 2 }}>
                        {(h.roi_pct ?? 0) >= 0 ? "+" : ""}{h.roi_pct}%
                      </Text>
                    )}
                  </View>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </Screen>
  );
}

const st = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 20, fontWeight: "800" },
  pill: { paddingHorizontal: 12, height: 30, borderRadius: 15, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  stat: { flexBasis: "48%", flexGrow: 1, padding: 12, borderRadius: 10, borderWidth: 1 },
  summary: { padding: 14, borderRadius: 10, borderWidth: 1, marginTop: 12 },
  row: { flexDirection: "row", alignItems: "center", padding: 10, borderRadius: 8, borderWidth: 1, marginBottom: 6 },
  histRow: { flexDirection: "row", alignItems: "center", padding: 10, borderRadius: 8, borderWidth: 1, marginBottom: 6 },
});
