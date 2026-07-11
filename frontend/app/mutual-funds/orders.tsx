/**
 * Order History — lumpsum and redemption orders with status pipeline.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFOrder, fmtINR } from "@/src/api/mutualFunds";
import { CheckCircle2, XCircle, Loader, Package } from "lucide-react-native";
import { shortDate } from "@/src/utils/format";

type Filter = "all" | "lumpsum" | "redeem";

export default function OrdersScreen() {
  const { palette } = useTheme();
  const [filter, setFilter] = useState<Filter>("all");
  const [items, setItems] = useState<MFOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setItems((await mfApi.orders(filter === "all" ? undefined : filter)).items); } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, [filter]);

  useEffect(() => { setLoading(true); load(); }, [filter]);

  const statusColor = (s: string) =>
    s === "completed" ? palette.success :
    s === "failed" ? palette.danger :
    s === "processing" || s === "pending_payment" || s === "allocated" ? palette.warning :
    palette.textMuted;

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={{ flexDirection: "row", padding: 16, paddingBottom: 4, gap: 6 }}>
        {(["all", "lumpsum", "redeem"] as const).map((f) => {
          const active = filter === f;
          return (
            <Pressable key={f} onPress={() => setFilter(f)} style={[s.pill, { backgroundColor: active ? palette.primary : palette.surface, borderColor: active ? palette.primary : palette.border }]}>
              <Text style={{ color: active ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800", letterSpacing: 0.6 }}>{f.toUpperCase()}</Text>
            </Pressable>
          );
        })}
      </View>
      {loading ? <ActivityIndicator color={palette.primary} size="large" style={{ marginTop: 40 }} /> : (
        <FlatList
          data={items}
          keyExtractor={(o) => o.order_id}
          contentContainerStyle={{ padding: 16, gap: 8, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
          renderItem={({ item }) => {
            const c = statusColor(item.status);
            const Icon = item.status === "completed" ? CheckCircle2 : item.status === "failed" ? XCircle : Loader;
            return (
              <View style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <View style={[s.rowIcon, { backgroundColor: c + "1A" }]}>
                  <Icon color={c} size={18} />
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }} numberOfLines={2}>{item.fund_name}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 11 }}>
                    {item.kind === "lumpsum" ? "Lumpsum" : "Redemption"} · {item.units.toFixed(4)} u · NAV ₹{item.nav} · {shortDate(item.created_at)}
                  </Text>
                  {item.realized_pnl != null ? (
                    <Text style={{ color: item.realized_pnl >= 0 ? palette.success : palette.danger, fontSize: 11, fontWeight: "800" }}>P/L {item.realized_pnl >= 0 ? "+" : ""}{fmtINR(item.realized_pnl)}</Text>
                  ) : null}
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={{ color: item.kind === "lumpsum" ? palette.textPrimary : palette.success, fontSize: 14, fontWeight: "800" }}>
                    {item.kind === "lumpsum" ? "-" : "+"}{fmtINR(item.amount)}
                  </Text>
                  <Text style={{ color: c, fontSize: 10, fontWeight: "800" }}>{item.status.replace(/_/g, " ").toUpperCase()}</Text>
                </View>
              </View>
            );
          }}
          ListEmptyComponent={
            <View style={{ padding: 40, alignItems: "center", gap: 8 }}>
              <Package color={palette.textMuted} size={44} />
              <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No orders yet</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  pill: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: 14, borderWidth: 1 },
  rowIcon: { padding: 10, borderRadius: 10 },
});
