/**
 * Gold Transactions History — filters (all/buy/sell), infinite pagination, empty state.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { goldApi, GoldTx, formatGrams, formatMoney } from "@/src/api/gold";
import { ArrowDownLeft, ArrowUpRight, Coins } from "lucide-react-native";
import { shortDate } from "@/src/utils/format";

type Filter = "all" | "buy" | "sell";

export default function GoldHistoryScreen() {
  const { palette } = useTheme();
  const [filter, setFilter] = useState<Filter>("all");
  const [rows, setRows] = useState<GoldTx[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [end, setEnd] = useState(false);

  const PAGE = 30;

  const load = useCallback(async (opts: { reset?: boolean } = {}) => {
    const skip = opts.reset ? 0 : rows.length;
    if (opts.reset) { setEnd(false); }
    try {
      const r = await goldApi.transactions({
        side: filter === "all" ? undefined : filter,
        limit: PAGE,
        skip,
      });
      const items = r.items || [];
      if (items.length < PAGE) setEnd(true);
      setRows((prev) => (opts.reset ? items : [...prev, ...items]));
    } catch {}
    finally { setLoading(false); setRefreshing(false); setLoadingMore(false); }
  }, [filter, rows.length]);

  useEffect(() => { setLoading(true); load({ reset: true }); }, [filter]);

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={{ paddingHorizontal: 16, paddingTop: 8, paddingBottom: 6, flexDirection: "row", gap: 8 }}>
        {((["all", "buy", "sell"] as Filter[])).map((f) => {
          const active = filter === f;
          return (
            <Pressable
              key={f}
              onPress={() => setFilter(f)}
              style={[s.pill, { backgroundColor: active ? palette.primary : palette.surface, borderColor: active ? palette.primary : palette.border }]}
              testID={`filter-${f}`}
            >
              <Text style={{ color: active ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 11, letterSpacing: 0.6 }}>
                {f.toUpperCase()}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={palette.primary} size="large" />
        </View>
      ) : (
        <FlatList
          contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
          data={rows}
          keyExtractor={(t) => t.tx_id}
          onEndReachedThreshold={0.4}
          onEndReached={() => { if (!end && !loadingMore && rows.length > 0) { setLoadingMore(true); load(); } }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load({ reset: true }); }} tintColor={palette.primary} />}
          renderItem={({ item }) => {
            const isBuy = item.side === "buy";
            const Icon = isBuy ? ArrowUpRight : ArrowDownLeft;
            const color = isBuy ? palette.danger : palette.success;
            return (
              <View style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <View style={[s.rowIcon, { backgroundColor: color + "1A" }]}>
                  <Icon color={color} size={20} />
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>
                      {isBuy ? "Bought Gold" : "Sold Gold"}
                    </Text>
                    <View style={[s.provider, { backgroundColor: palette.chipBg }]}>
                      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800", letterSpacing: 0.8 }}>{(item.provider || "").toUpperCase()}</Text>
                    </View>
                  </View>
                  <Text style={{ color: palette.textSecondary, fontSize: 11 }}>
                    {formatGrams(item.grams)} @ {formatMoney(item.price_per_gram)} · {shortDate(item.created_at)}
                  </Text>
                  {!isBuy && item.realized_pnl_inr != null ? (
                    <Text style={{ color: item.realized_pnl_inr >= 0 ? palette.success : palette.danger, fontSize: 11, fontWeight: "800" }}>
                      P/L {item.realized_pnl_inr >= 0 ? "+" : ""}{formatMoney(item.realized_pnl_inr)}
                    </Text>
                  ) : null}
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={{ color: isBuy ? palette.textPrimary : palette.success, fontSize: 14, fontWeight: "800" }}>
                    {isBuy ? "-" : "+"}{formatMoney(item.amount_inr)}
                  </Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>{item.status?.toUpperCase()}</Text>
                </View>
              </View>
            );
          }}
          ListEmptyComponent={
            <View style={{ padding: 40, alignItems: "center", gap: 8 }}>
              <Coins color={palette.textMuted} size={44} />
              <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No transactions yet</Text>
              <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>
                Buy your first gold from the Gold Dashboard.
              </Text>
            </View>
          }
          ListFooterComponent={loadingMore ? <ActivityIndicator color={palette.primary} style={{ marginVertical: 20 }} /> : null}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  pill: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 16, borderWidth: 1 },
  rowIcon: { padding: 10, borderRadius: 12 },
  provider: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
});
