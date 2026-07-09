/**
 * AI Watchlist — Sprint 7C.1
 * Symbols with trend/signal/confidence/volatility/daily+weekly change.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, Modal, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, Star, Trash2, Plus, X, TrendingUp, TrendingDown, Minus, Search } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiApi, WatchlistItem, sideColor } from "@/src/api/aiIntel";
import { errText } from "@/src/utils/errors";

const SUGGESTIONS = [
  "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
  "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "SOLUSD",
  "US30", "SPX500", "NAS100", "GER40", "USOIL",
];

export default function AIWatchlist() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [customSym, setCustomSym] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await aiApi.watchlist();
      setItems(r.items || []);
    } catch (e) { show("error", errText(e, "Failed to load watchlist")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [show]);
  useEffect(() => { load(); }, [load]);

  const addSym = async (sym: string) => {
    if (!sym) return;
    try {
      await aiApi.addWatchlist(sym.toUpperCase());
      show("success", `${sym.toUpperCase()} added`);
      setAdding(false); setCustomSym("");
      await load();
    } catch (e) { show("error", errText(e, "Failed to add symbol")); }
  };

  const remove = async (sym: string) => {
    try {
      await aiApi.removeWatchlist(sym);
      setItems((prev) => prev.filter((i) => i.symbol !== sym));
    } catch (e) { show("error", errText(e, "Failed to remove")); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>Watchlist</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{items.length} symbol{items.length === 1 ? "" : "s"}</Text>
        </View>
        <Pressable onPress={() => setAdding(true)} hitSlop={8} style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primary }}>
          <Plus size={13} color="#fff" />
          <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>Add</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {loading && <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>}
        {!loading && items.length === 0 && (
          <View style={{ padding: 40, alignItems: "center" }}>
            <Star size={40} color={palette.textMuted} />
            <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800", marginTop: 10 }}>No symbols watched</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center", marginTop: 6, lineHeight: 18 }}>
              Add symbols to see live trend, AI signal, volatility and % change at a glance.
            </Text>
            <Pressable onPress={() => setAdding(true)} style={{ marginTop: 16, backgroundColor: palette.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 999 }}>
              <Text style={{ color: "#fff", fontWeight: "900", fontSize: 13 }}>Add your first symbol</Text>
            </Pressable>
          </View>
        )}
        {items.map((it) => <Row key={it.symbol} it={it} palette={palette}
          onPress={() => router.push(`/ai/signal/${it.symbol}` as any)} onRemove={() => remove(it.symbol)} />)}
      </ScrollView>

      <Modal visible={adding} animationType="slide" transparent onRequestClose={() => setAdding(false)}>
        <View style={{ flex: 1, backgroundColor: "#0006", justifyContent: "flex-end" }}>
          <View style={[s.sheet, { backgroundColor: palette.background }]}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "900" }}>Add Symbol</Text>
              <Pressable onPress={() => setAdding(false)} hitSlop={8}><X size={20} color={palette.textPrimary} /></Pressable>
            </View>
            <View style={[s.inputWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Search size={14} color={palette.textMuted} />
              <TextInput
                value={customSym}
                onChangeText={setCustomSym}
                placeholder="Enter symbol (e.g., XAUUSD)"
                placeholderTextColor={palette.textMuted}
                autoCapitalize="characters"
                autoCorrect={false}
                onSubmitEditing={() => addSym(customSym)}
                style={{ flex: 1, color: palette.textPrimary, fontSize: 14, marginLeft: 8, paddingVertical: 8 }}
              />
              {customSym.length > 0 && (
                <Pressable onPress={() => addSym(customSym)} style={{ paddingHorizontal: 10, paddingVertical: 6, backgroundColor: palette.primary, borderRadius: 8 }}>
                  <Text style={{ color: "#fff", fontWeight: "900", fontSize: 12 }}>Add</Text>
                </Pressable>
              )}
            </View>
            <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 12, fontWeight: "800", letterSpacing: 0.5 }}>QUICK PICKS</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
              {SUGGESTIONS.map((sym) => (
                <Pressable key={sym} onPress={() => addSym(sym)}
                  style={[s.chip, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{sym}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

function Row({ it, palette, onPress, onRemove }: any) {
  const sc = sideColor(it.signal, palette);
  const TrendIc = it.trend === "bullish" ? TrendingUp : it.trend === "bearish" ? TrendingDown : Minus;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.row, { backgroundColor: pressed ? palette.surface : palette.background, borderBottomColor: palette.border }]}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "900" }}>{it.display}</Text>
          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: sc + "22" }}>
            <Text style={{ color: sc, fontSize: 9, fontWeight: "900" }}>{it.signal.toUpperCase()}</Text>
          </View>
          <TrendIc size={11} color={it.trend === "bullish" ? palette.success : it.trend === "bearish" ? palette.danger : palette.textMuted} />
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{it.trend}</Text>
        </View>
        <View style={{ flexDirection: "row", gap: 12, marginTop: 4 }}>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>
            Vol {it.volatility_pct.toFixed(2)}%
          </Text>
          <Text style={{ color: it.daily_change_pct >= 0 ? palette.success : palette.danger, fontSize: 10, fontWeight: "700" }}>
            1D {it.daily_change_pct >= 0 ? "+" : ""}{it.daily_change_pct.toFixed(2)}%
          </Text>
          <Text style={{ color: it.weekly_change_pct >= 0 ? palette.success : palette.danger, fontSize: 10, fontWeight: "700" }}>
            1W {it.weekly_change_pct >= 0 ? "+" : ""}{it.weekly_change_pct.toFixed(2)}%
          </Text>
        </View>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "900", fontVariant: ["tabular-nums"] }}>
          {typeof it.price === "number" ? it.price.toLocaleString(undefined, { maximumFractionDigits: 5 }) : it.price}
        </Text>
        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, marginTop: 3, backgroundColor: confColor(it.confidence_pct) + "22" }}>
          <Text style={{ color: confColor(it.confidence_pct), fontSize: 9, fontWeight: "900" }}>{it.confidence_pct}%</Text>
        </View>
      </View>
      <Pressable onPress={onRemove} hitSlop={6} style={{ padding: 6 }}>
        <Trash2 size={14} color={palette.textMuted} />
      </Pressable>
    </Pressable>
  );
}
function confColor(n: number) {
  if (n >= 85) return "#10B981"; if (n >= 70) return "#3B82F6"; if (n >= 55) return "#F59E0B"; return "#94A3B8";
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 18, fontWeight: "800" },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  sheet: { padding: 18, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingBottom: 34 },
  inputWrap: { flexDirection: "row", alignItems: "center", paddingHorizontal: 10, borderWidth: 1, borderRadius: 10 },
});
