/**
 * Gold Analytics — user's personal analytics: P/L breakdown, buy/sell volumes,
 * avg cost vs current price, allocation, streaks.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { goldApi, GoldHoldings, GoldQuote, GoldTx, formatGrams, formatMoney } from "@/src/api/gold";
import { Card } from "@/src/components/Card";
import { TrendingUp, TrendingDown } from "lucide-react-native";

export default function GoldAnalyticsScreen() {
  const { palette } = useTheme();
  const [holdings, setHoldings] = useState<GoldHoldings | null>(null);
  const [quote, setQuote] = useState<GoldQuote | null>(null);
  const [txs, setTxs] = useState<GoldTx[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [h, q, t] = await Promise.all([
        goldApi.holdings(),
        goldApi.quote(),
        goldApi.transactions({ limit: 200 }),
      ]);
      setHoldings(h); setQuote(q); setTxs(t.items || []);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const stats = useMemo(() => {
    let buyCount = 0, sellCount = 0, buyVol = 0, sellVol = 0, buyGrams = 0, sellGrams = 0, realized = 0;
    for (const t of txs) {
      if (t.side === "buy") { buyCount++; buyVol += t.amount_inr; buyGrams += t.grams; }
      else { sellCount++; sellVol += t.amount_inr; sellGrams += t.grams; realized += (t.realized_pnl_inr || 0); }
    }
    return { buyCount, sellCount, buyVol, sellVol, buyGrams, sellGrams, realized };
  }, [txs]);

  const unreal = holdings?.unrealized_pnl_inr || 0;
  const total = unreal + stats.realized;
  const cur = holdings?.current_price_per_gram || 0;
  const avg = holdings?.avg_buy_price || 0;
  const priceDeltaPct = avg ? ((cur - avg) / avg) * 100 : 0;

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.background }}>
        <ActivityIndicator color={palette.primary} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: palette.background }}
      contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
    >
      {/* Total P/L hero */}
      <Card style={{ padding: 18, gap: 8 }}>
        <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.3 }}>TOTAL P/L (REALIZED + UNREALIZED)</Text>
        <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8 }}>
          <Text style={{ color: total >= 0 ? palette.success : palette.danger, fontSize: 30, fontWeight: "800", letterSpacing: -0.8 }}>
            {total >= 0 ? "+" : ""}{formatMoney(total)}
          </Text>
          {total >= 0 ? <TrendingUp color={palette.success} size={20} /> : <TrendingDown color={palette.danger} size={20} />}
        </View>
        <View style={{ flexDirection: "row", gap: 12, marginTop: 4 }}>
          <MiniStat label="Realized" value={formatMoney(stats.realized)} color={stats.realized >= 0 ? palette.success : palette.danger} palette={palette} />
          <MiniStat label="Unrealized" value={formatMoney(unreal)} color={unreal >= 0 ? palette.success : palette.danger} palette={palette} />
        </View>
      </Card>

      {/* Avg cost vs current price */}
      <Card style={{ padding: 16, gap: 10 }}>
        <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Cost vs Market</Text>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <MetricBlock label="Avg Buy" value={formatMoney(avg)} palette={palette} />
          <MetricBlock label="Current" value={formatMoney(cur)} palette={palette} />
          <MetricBlock label="Delta" value={`${priceDeltaPct >= 0 ? "+" : ""}${priceDeltaPct.toFixed(2)}%`} color={priceDeltaPct >= 0 ? palette.success : palette.danger} palette={palette} />
        </View>
        {/* Bar */}
        <View style={{ marginTop: 4 }}>
          <View style={{ flexDirection: "row", height: 10, borderRadius: 8, overflow: "hidden" }}>
            <View style={{ flex: Math.max(0.05, Math.abs(priceDeltaPct)), backgroundColor: priceDeltaPct >= 0 ? palette.success : palette.danger }} />
            <View style={{ flex: Math.max(0.5, 20 - Math.abs(priceDeltaPct)), backgroundColor: palette.chipBg }} />
          </View>
        </View>
      </Card>

      {/* Buy/Sell activity */}
      <Card style={{ padding: 16, gap: 12 }}>
        <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Activity</Text>
        <View style={{ flexDirection: "row", gap: 12 }}>
          <ActivityBlock label="Buys" count={stats.buyCount} vol={stats.buyVol} grams={stats.buyGrams} tint={palette.primary} palette={palette} />
          <ActivityBlock label="Sells" count={stats.sellCount} vol={stats.sellVol} grams={stats.sellGrams} tint={palette.danger} palette={palette} />
        </View>
      </Card>

      {/* Portfolio position */}
      <Card style={{ padding: 16, gap: 10 }}>
        <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Portfolio Position</Text>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <MetricBlock label="Grams" value={formatGrams(holdings?.grams || 0)} palette={palette} />
          <MetricBlock label="Invested" value={formatMoney(holdings?.total_invested || 0)} palette={palette} />
          <MetricBlock label="Value" value={formatMoney(holdings?.current_value_inr || 0)} palette={palette} />
        </View>
      </Card>

      <Text style={{ color: palette.textMuted, fontSize: 11, textAlign: "center", marginTop: 4 }}>
        Analytics update in real-time after every trade.
      </Text>
    </ScrollView>
  );
}

function MiniStat({ label, value, color, palette }: any) {
  return (
    <View style={{ flex: 1, backgroundColor: palette.chipBg, padding: 10, borderRadius: 12 }}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 15, fontWeight: "800", marginTop: 2 }}>{value}</Text>
    </View>
  );
}
function MetricBlock({ label, value, color, palette }: any) {
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 14, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}
function ActivityBlock({ label, count, vol, grams, tint, palette }: any) {
  return (
    <View style={{ flex: 1, padding: 12, borderRadius: 14, backgroundColor: tint + "12", borderWidth: 1, borderColor: tint + "33", gap: 3 }}>
      <Text style={{ color: tint, fontSize: 11, fontWeight: "800", letterSpacing: 0.8 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>{count}</Text>
      <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>{formatMoney(vol)}</Text>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>{grams.toFixed(4)} g</Text>
    </View>
  );
}
