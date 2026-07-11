/**
 * Gold live chart — full-screen with timeframe switcher, delta ribbon, and stats grid.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { goldApi, GoldChartPoint, GoldQuote, formatMoney } from "@/src/api/gold";
import { FinancialChart, ChartWindow } from "@/src/components/FinancialChart";
import { Card } from "@/src/components/Card";
import { TrendingUp, TrendingDown } from "lucide-react-native";

export default function GoldChartScreen() {
  const { palette } = useTheme();
  const [window, setWindow] = useState<ChartWindow>("1D");
  const [points, setPoints] = useState<GoldChartPoint[]>([]);
  const [quote, setQuote] = useState<GoldQuote | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (w: ChartWindow = window) => {
    try {
      const [c, q] = await Promise.all([goldApi.chart(w), goldApi.quote()]);
      setPoints(c.points || []);
      setQuote(q);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, [window]);

  useEffect(() => { load(window); }, [window]);
  useEffect(() => {
    const id = setInterval(async () => {
      try { setQuote(await goldApi.quote()); } catch {}
    }, 8000);
    return () => clearInterval(id);
  }, []);

  const chartPoints = useMemo(() => points.map((p) => ({ ts: p.quoted_at, value: p.mid })), [points]);

  const first = points[0]?.mid ?? 0;
  const last = points[points.length - 1]?.mid ?? 0;
  const delta = last - first;
  const deltaPct = first ? (delta / first) * 100 : 0;
  const isUp = delta >= 0;

  const min = points.length ? Math.min(...points.map((p) => p.mid)) : 0;
  const max = points.length ? Math.max(...points.map((p) => p.mid)) : 0;

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(window); }} tintColor={palette.primary} />}
      >
        {/* Live price header */}
        <Card style={{ padding: 18, gap: 6 }}>
          <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 1.3 }}>GOLD · 999.9 · LIVE</Text>
          <Text style={{ color: palette.textPrimary, fontSize: 34, fontWeight: "800", letterSpacing: -1 }}>
            {formatMoney(quote?.mid_price ?? 0)}
            <Text style={{ fontSize: 14, color: palette.textMuted, fontWeight: "700" }}> / g</Text>
          </Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            {isUp ? <TrendingUp color={palette.success} size={16} /> : <TrendingDown color={palette.danger} size={16} />}
            <Text style={{ color: isUp ? palette.success : palette.danger, fontSize: 13, fontWeight: "800" }}>
              {isUp ? "+" : ""}{formatMoney(delta)} · {isUp ? "+" : ""}{deltaPct.toFixed(2)}%
            </Text>
            <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>· {window}</Text>
          </View>
        </Card>

        {/* Chart */}
        {loading ? (
          <View style={{ height: 320, justifyContent: "center", alignItems: "center" }}>
            <ActivityIndicator color={palette.primary} />
          </View>
        ) : (
          <FinancialChart
            points={chartPoints}
            height={320}
            window={window}
            onWindowChange={setWindow}
            livePrice={quote?.mid_price ?? null}
            title={`GOLD · ${window}`}
            isUp={isUp}
          />
        )}

        {/* Stats */}
        <View style={{ flexDirection: "row", gap: 10 }}>
          <StatCard label={`${window} High`} value={formatMoney(max)} palette={palette} />
          <StatCard label={`${window} Low`} value={formatMoney(min)} palette={palette} />
        </View>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <StatCard label="Buy Price" value={formatMoney(quote?.buy_price || 0)} palette={palette} />
          <StatCard label="Sell Price" value={formatMoney(quote?.sell_price || 0)} palette={palette} />
        </View>
        <StatCard label="Spread" value={`${((quote?.spread_bps || 0) / 100).toFixed(2)}%`} palette={palette} />

        {/* Legend */}
        <Card style={{ padding: 14, gap: 6 }}>
          <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "800" }}>ABOUT THIS CHART</Text>
          <Text style={{ color: palette.textMuted, fontSize: 11 }}>
            Long-press the chart to see the exact price at any point. Tap a timeframe pill to switch
            windows. Live price refreshes every 8 seconds.
          </Text>
        </Card>
      </ScrollView>
    </View>
  );
}

function StatCard({ label, value, palette }: any) {
  return (
    <Card style={{ flex: 1, padding: 12, gap: 4 }}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800" }}>{value}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({});
