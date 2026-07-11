/**
 * Watchlist — saved funds with quick invest button.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFFund, RISK_META } from "@/src/api/mutualFunds";
import { Bookmark, ChevronRight, Star } from "lucide-react-native";

export default function Watchlist() {
  const { palette } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<MFFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setItems((await mfApi.watchlist()).items); } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async (id: string) => { try { await mfApi.watchlistRemove(id); load(); } catch {} };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: palette.background }}
      contentContainerStyle={{ padding: 16, gap: 8, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
    >
      {loading ? (
        <ActivityIndicator color={palette.primary} size="large" style={{ marginTop: 30 }} />
      ) : items.length === 0 ? (
        <View style={{ padding: 40, alignItems: "center", gap: 8 }}>
          <Bookmark color={palette.textMuted} size={44} />
          <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>Watchlist empty</Text>
          <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>Tap the bookmark icon on any fund to add.</Text>
        </View>
      ) : items.map((f) => (
        <Pressable
          key={f.fund_id}
          onPress={() => router.push({ pathname: "/mutual-funds/fund/[id]", params: { id: f.fund_id } })}
          style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}
        >
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }} numberOfLines={2}>{f.name}</Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
              <Text style={{ color: palette.textMuted, fontSize: 10 }}>{f.amc}</Text>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                {Array.from({ length: Math.round(f.star_rating) }).map((_, i) => (
                  <Star key={i} color="#F59E0B" fill="#F59E0B" size={9} />
                ))}
              </View>
            </View>
          </View>
          <View style={{ alignItems: "flex-end", gap: 2 }}>
            <Text style={{ color: (f.returns?.y1 ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 13, fontWeight: "800" }}>{(f.returns?.y1 ?? 0) >= 0 ? "+" : ""}{(f.returns?.y1 ?? 0).toFixed(2)}%</Text>
            <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700" }}>1Y</Text>
            <Pressable onPress={() => remove(f.fund_id)} hitSlop={6}>
              <Text style={{ color: palette.danger, fontSize: 10, fontWeight: "800" }}>Remove</Text>
            </Pressable>
          </View>
          <ChevronRight color={palette.textMuted} size={14} />
        </Pressable>
      ))}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 14, borderWidth: 1 },
});
