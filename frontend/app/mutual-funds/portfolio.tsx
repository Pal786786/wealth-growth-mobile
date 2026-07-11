/**
 * Portfolio — Sprint 11.
 * Shows total P/L, XIRR/CAGR/Absolute, Daily/Weekly/Monthly P/L,
 * allocation pies (asset/AMC/category/risk), top & worst performer, holdings list.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, RefreshControl, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { TrendingUp, TrendingDown, PieChart, Sparkles } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFPortfolio, fmtINR, RISK_META } from "@/src/api/mutualFunds";
import { Card } from "@/src/components/Card";

const COLORS = ["#6366F1", "#F59E0B", "#10B981", "#EF4444", "#0EA5E9", "#8B5CF6", "#EC4899", "#14B8A6"];

export default function PortfolioScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const [port, setPort] = useState<MFPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<"asset" | "amc" | "category" | "risk">("asset");

  const load = useCallback(async () => {
    try { setPort(await mfApi.portfolio()); } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.background }}><ActivityIndicator color={palette.primary} size="large" /></View>;
  if (!port) return null;

  const pnlUp = port.unrealized_pnl >= 0;
  const alloc = port.allocations[tab] || [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: palette.background }}
      contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 14 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
    >
      {/* Total Value */}
      <Card style={{ padding: 16, gap: 6 }}>
        <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "800", letterSpacing: 1 }}>CURRENT VALUE</Text>
        <Text style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", letterSpacing: -0.6 }}>{fmtINR(port.current_value)}</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          {pnlUp ? <TrendingUp color={palette.success} size={16} /> : <TrendingDown color={palette.danger} size={16} />}
          <Text style={{ color: pnlUp ? palette.success : palette.danger, fontSize: 14, fontWeight: "800" }}>
            {pnlUp ? "+" : ""}{fmtINR(port.unrealized_pnl)} · {port.unrealized_pnl_pct.toFixed(2)}%
          </Text>
        </View>
        <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>Invested · {fmtINR(port.total_invested)}</Text>
      </Card>

      {/* KPI row */}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <KPI label="XIRR" value={port.xirr_pct != null ? `${port.xirr_pct.toFixed(2)}%` : "—"} palette={palette} tint={palette.primary} />
        <KPI label="CAGR" value={port.cagr_pct != null ? `${port.cagr_pct.toFixed(2)}%` : "—"} palette={palette} tint={palette.success} />
        <KPI label="Abs Ret" value={`${port.absolute_return_pct.toFixed(2)}%`} palette={palette} tint={palette.warning} />
      </View>

      <View style={{ flexDirection: "row", gap: 10 }}>
        <KPI label="Daily P/L"   value={fmtINR(port.daily_pl)}   palette={palette} tint={port.daily_pl >= 0 ? palette.success : palette.danger} />
        <KPI label="Weekly P/L"  value={fmtINR(port.weekly_pl)}  palette={palette} tint={port.weekly_pl >= 0 ? palette.success : palette.danger} />
        <KPI label="Monthly P/L" value={fmtINR(port.monthly_pl)} palette={palette} tint={port.monthly_pl >= 0 ? palette.success : palette.danger} />
      </View>

      {/* Allocation tabs */}
      <Card style={{ padding: 14, gap: 10 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <PieChart color={palette.primary} size={16} />
          <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Allocation</Text>
        </View>
        <View style={{ flexDirection: "row", gap: 6 }}>
          {(["asset", "amc", "category", "risk"] as const).map((t) => {
            const active = tab === t;
            return (
              <Pressable key={t} onPress={() => setTab(t)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: active ? palette.primary : palette.chipBg }}>
                <Text style={{ color: active ? "#fff" : palette.textSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 0.5 }}>{t.toUpperCase()}</Text>
              </Pressable>
            );
          })}
        </View>
        {alloc.length === 0 ? (
          <Text style={{ color: palette.textMuted, textAlign: "center", paddingVertical: 20 }}>No allocation yet.</Text>
        ) : (
          <>
            {/* Simple horizontal bar stack */}
            <View style={{ flexDirection: "row", height: 14, borderRadius: 8, overflow: "hidden" }}>
              {alloc.map((a, i) => (
                <View key={a.name} style={{ flex: a.pct, backgroundColor: COLORS[i % COLORS.length] }} />
              ))}
            </View>
            {alloc.map((a, i) => (
              <View key={a.name} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, paddingVertical: 4 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS[i % COLORS.length] }} />
                  <Text style={{ color: palette.textSecondary, fontSize: 12, flex: 1 }} numberOfLines={1}>{a.name}</Text>
                </View>
                <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{a.pct.toFixed(1)}%</Text>
                <Text style={{ color: palette.textMuted, fontSize: 11, minWidth: 70, textAlign: "right" }}>{fmtINR(a.value)}</Text>
              </View>
            ))}
          </>
        )}
      </Card>

      {/* Best / Worst */}
      {port.top_performer || port.worst_performer ? (
        <View style={{ flexDirection: "row", gap: 10 }}>
          {port.top_performer ? (
            <Card style={{ flex: 1, padding: 12, gap: 4 }}>
              <Text style={{ color: palette.success, fontSize: 10, fontWeight: "800", letterSpacing: 1 }}>TOP PERFORMER</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }} numberOfLines={2}>{port.top_performer.fund_name}</Text>
              <Text style={{ color: palette.success, fontSize: 14, fontWeight: "800" }}>{port.top_performer.unrealized_pnl_pct >= 0 ? "+" : ""}{port.top_performer.unrealized_pnl_pct.toFixed(2)}%</Text>
            </Card>
          ) : null}
          {port.worst_performer && port.worst_performer.fund_id !== port.top_performer?.fund_id ? (
            <Card style={{ flex: 1, padding: 12, gap: 4 }}>
              <Text style={{ color: palette.danger, fontSize: 10, fontWeight: "800", letterSpacing: 1 }}>WORST PERFORMER</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }} numberOfLines={2}>{port.worst_performer.fund_name}</Text>
              <Text style={{ color: palette.danger, fontSize: 14, fontWeight: "800" }}>{port.worst_performer.unrealized_pnl_pct >= 0 ? "+" : ""}{port.worst_performer.unrealized_pnl_pct.toFixed(2)}%</Text>
            </Card>
          ) : null}
        </View>
      ) : null}

      {/* Holdings list */}
      <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800" }}>Holdings ({port.count_funds})</Text>
      {port.holdings.map((h) => (
        <Pressable
          key={h.fund_id}
          onPress={() => router.push({ pathname: "/mutual-funds/fund/[id]", params: { id: h.fund_id } })}
          style={{ padding: 12, borderRadius: 14, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border, gap: 6 }}
        >
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800", flex: 1 }} numberOfLines={2}>{h.fund_name}</Text>
            <Text style={{ color: h.unrealized_pnl >= 0 ? palette.success : palette.danger, fontSize: 14, fontWeight: "800" }}>
              {h.unrealized_pnl >= 0 ? "+" : ""}{h.unrealized_pnl_pct.toFixed(2)}%
            </Text>
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={{ color: palette.textMuted, fontSize: 11 }}>{h.units.toFixed(4)} units · avg NAV {fmtINR(h.avg_nav)}</Text>
            <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{fmtINR(h.current_value)}</Text>
          </View>
        </Pressable>
      ))}

      <Pressable onPress={() => router.push("/mutual-funds/advisor")} style={[styles.aiBtn, { backgroundColor: palette.primary + "1A", borderColor: palette.primary }]}>
        <Sparkles color={palette.primary} size={16} />
        <Text style={{ color: palette.primary, fontSize: 12, fontWeight: "800" }}>Ask AI Advisor about my portfolio</Text>
      </Pressable>
    </ScrollView>
  );
}

function KPI({ label, value, palette, tint }: any) {
  return (
    <View style={{ flex: 1, backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1, padding: 10, borderRadius: 12, gap: 3 }}>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800", letterSpacing: 1 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: tint, fontSize: 14, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  aiBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: 12, borderWidth: 1, paddingVertical: 12 },
});
