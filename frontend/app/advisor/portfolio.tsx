import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, TrendingUp, ShieldAlert, Sparkles, PieChart, ArrowUpRight, ArrowDownRight } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { advisorApi, type PortfolioAnalysis } from "@/src/api/advisor";
import { formatINR } from "@/src/utils/format";

const RISK_COLOR: Record<string, string> = {
  Low: "#10B981", Medium: "#F59E0B", High: "#EF4444", low: "#10B981", medium: "#F59E0B", high: "#EF4444",
};

export default function PortfolioScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const [data, setData] = useState<PortfolioAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setData(await advisorApi.portfolioAnalyze()); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading || !data) return (
    <Screen><ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} /></Screen>
  );

  const p = data.profile;
  const an = p.analytics;
  const alloc = p.portfolio.allocation_pct || {};
  const allocEntries = Object.entries(alloc).sort(([, a], [, b]) => (b as number) - (a as number));

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Portfolio Analysis</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 80 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}>

        <LinearGradient colors={["#0F172A", "#4F46E5"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <Text style={s.heroLabel}>PORTFOLIO HEALTH</Text>
          <Text style={s.heroScore}>{an.health_score}<Text style={{ fontSize: 20 }}>/100</Text></Text>
          <Text style={s.heroSub}>{data.insights.headline}</Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
            <Metric label="Risk" value={an.risk_bucket} tint={RISK_COLOR[an.risk_bucket] || "#38BDF8"} />
            <Metric label="Returns" value={`${p.portfolio.returns_pct}%`} tint={p.portfolio.returns_pct >= 0 ? "#10B981" : "#EF4444"} />
            <Metric label="Confidence" value={`${an.confidence_pct}%`} tint="#38BDF8" />
          </View>
        </LinearGradient>

        <View style={s.row2}>
          <StatCard label="Invested" value={formatINR(p.portfolio.total_invested)} palette={palette} />
          <StatCard label="Current" value={formatINR(p.portfolio.total_current)} palette={palette} tone={p.portfolio.returns_pct >= 0 ? palette.success : palette.danger} />
        </View>

        <Card>
          <Text style={[s.sectionLabel, { color: palette.textSecondary }]}>ASSET ALLOCATION</Text>
          {allocEntries.length === 0 ? (
            <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 4 }}>No investments yet. Start an SIP to build your portfolio.</Text>
          ) : (
            <View style={{ marginTop: 8, gap: 8 }}>
              {allocEntries.map(([k, v]) => (
                <View key={k} style={{ gap: 4 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                    <Text style={{ color: palette.textPrimary, fontWeight: "700", fontSize: 13 }}>{prettyType(k)}</Text>
                    <Text style={{ color: palette.textSecondary, fontWeight: "700", fontSize: 12 }}>{(v as number).toFixed(1)}%</Text>
                  </View>
                  <View style={{ height: 6, backgroundColor: palette.chipBg, borderRadius: 3, overflow: "hidden" }}>
                    <View style={{ height: 6, width: `${v as number}%`, backgroundColor: colorFor(k) }} />
                  </View>
                </View>
              ))}
            </View>
          )}
        </Card>

        {data.insights.highlights?.length > 0 && (
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <Sparkles color={palette.primary} size={16} />
              <Text style={[s.sectionLabel, { color: palette.textPrimary }]}>HIGHLIGHTS</Text>
            </View>
            {data.insights.highlights.map((h, i) => (
              <View key={i} style={{ flexDirection: "row", gap: 8, marginBottom: 4 }}>
                <Text style={{ color: palette.primary }}>•</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 13, flex: 1, lineHeight: 20 }}>{h}</Text>
              </View>
            ))}
          </Card>
        )}

        {data.insights.recommendations?.length > 0 && (
          <View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <TrendingUp color={palette.success} size={16} />
              <Text style={[s.sectionLabel, { color: palette.textPrimary }]}>RECOMMENDATIONS</Text>
            </View>
            {data.insights.recommendations.map((r, i) => (
              <Card key={i} style={{ marginBottom: 8 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14, flex: 1 }}>{r.action}</Text>
                  <View style={[s.riskChip, { backgroundColor: (RISK_COLOR[r.risk] || palette.primary) + "22", borderColor: (RISK_COLOR[r.risk] || palette.primary) + "55" }]}>
                    <Text style={{ color: RISK_COLOR[r.risk] || palette.primary, fontSize: 10, fontWeight: "800" }}>{r.risk}</Text>
                  </View>
                </View>
                <Text style={{ color: palette.textSecondary, fontSize: 12, marginTop: 4, lineHeight: 18 }}>{r.why}</Text>
                <View style={{ flexDirection: "row", gap: 12, marginTop: 8 }}>
                  <View style={{ flexDirection: "row", gap: 4, alignItems: "center" }}>
                    <ArrowUpRight color={palette.success} size={12} />
                    <Text style={{ color: palette.success, fontSize: 11, fontWeight: "700" }}>{r.return_range}</Text>
                  </View>
                  <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>⏱ {r.horizon}</Text>
                </View>
              </Card>
            ))}
          </View>
        )}

        {data.insights.risks?.length > 0 && (
          <Card style={{ borderColor: palette.danger + "55", borderWidth: 1 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <ShieldAlert color={palette.danger} size={16} />
              <Text style={[s.sectionLabel, { color: palette.danger }]}>RISK FACTORS</Text>
            </View>
            {data.insights.risks.map((r, i) => (
              <View key={i} style={{ flexDirection: "row", gap: 8, marginBottom: 4 }}>
                <Text style={{ color: palette.danger }}>!</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 12, flex: 1, lineHeight: 18 }}>{r}</Text>
              </View>
            ))}
          </Card>
        )}

        {data.insights.disclaimer && (
          <Text style={{ color: palette.textMuted, fontSize: 11, textAlign: "center", lineHeight: 16, marginTop: 4 }}>{data.insights.disclaimer}</Text>
        )}
      </ScrollView>
    </Screen>
  );
}

function prettyType(k: string) {
  return ({ mutual_fund: "Mutual Funds", stock: "Stocks", gold: "Gold", fd: "Fixed Deposits", govt: "Govt Schemes", sip: "SIPs" } as any)[k] || k;
}
function colorFor(k: string) {
  return ({ mutual_fund: "#0EA5E9", stock: "#8B5CF6", gold: "#F59E0B", fd: "#10B981", govt: "#EC4899", sip: "#6366F1" } as any)[k] || "#94A3B8";
}

function Metric({ label, value, tint }: { label: string; value: string | number; tint: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: "rgba(255,255,255,0.14)", borderRadius: 12, padding: 10, borderWidth: 1, borderColor: "rgba(255,255,255,0.22)" }}>
      <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 9, fontWeight: "800", letterSpacing: 0.6 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: tint, fontSize: 15, fontWeight: "900", marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function StatCard({ label, value, palette, tone }: { label: string; value: string; palette: any; tone?: string }) {
  return (
    <Card style={{ flex: 1 }}>
      <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 0.6 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: tone || palette.textPrimary, fontSize: 18, fontWeight: "900", marginTop: 4 }}>{value}</Text>
    </Card>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  hero: { padding: 20, borderRadius: 22, gap: 4 },
  heroLabel: { color: "rgba(255,255,255,0.7)", fontSize: 10, fontWeight: "800", letterSpacing: 1.2 },
  heroScore: { color: "#fff", fontSize: 48, fontWeight: "900", letterSpacing: -1.6 },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 12, marginTop: 6, lineHeight: 18 },
  row2: { flexDirection: "row", gap: 10 },
  sectionLabel: { fontSize: 11, fontWeight: "800", letterSpacing: 0.6 },
  riskChip: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1 },
});
