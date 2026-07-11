/**
 * AI Market News — Sprint 7C.2
 *
 * Category-filtered feed. AI-curated headlines across Forex, Crypto,
 * Indices, Commodities, Indian Market and Global.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, Newspaper, Zap, TrendingUp, TrendingDown, Minus } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiNewsApi, NewsItem, NewsCategory, sentimentColor } from "@/src/api/aiNews";
import { errText } from "@/src/utils/errors";

const CATS: Array<{ id: NewsCategory | "all"; label: string }> = [
  { id: "all", label: "All" },
  { id: "forex", label: "Forex" },
  { id: "crypto", label: "Crypto" },
  { id: "indices", label: "Indices" },
  { id: "commodities", label: "Commodities" },
  { id: "indian_market", label: "India" },
  { id: "global", label: "Global" },
];

function relTime(iso?: string) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function SentimentIcon({ s, palette }: { s: string; palette: any }) {
  if (s?.includes("bullish")) return <TrendingUp size={13} color={palette.success} />;
  if (s?.includes("bearish")) return <TrendingDown size={13} color={palette.danger} />;
  return <Minus size={13} color={palette.textMuted} />;
}

export default function AINews() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [category, setCategory] = useState<NewsCategory | "all">("all");
  const [highOnly, setHighOnly] = useState(false);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await aiNewsApi.news({
        category: category === "all" ? undefined : category,
        high_impact_only: highOnly, limit: 40,
      });
      setItems(r.items);
    } catch (e) { show("error", errText(e, "Failed to load news")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [category, highOnly, show]);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Newspaper size={18} color={palette.primary} />
            <Text style={[s.title, { color: palette.textPrimary }]}>Market News</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
            AI-curated · Claude Sonnet 4.5
          </Text>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 44 }} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 6 }}>
        {CATS.map((c) => (
          <Pressable key={c.id} onPress={() => setCategory(c.id)} style={[s.pill, { backgroundColor: category === c.id ? palette.primary : palette.surface, borderColor: category === c.id ? palette.primary : palette.border }]}>
            <Text style={{ color: category === c.id ? "#fff" : palette.textPrimary, fontSize: 12, fontWeight: "700" }}>{c.label}</Text>
          </Pressable>
        ))}
        <Pressable onPress={() => setHighOnly(!highOnly)} style={[s.pill, { backgroundColor: highOnly ? "#EF444420" : palette.surface, borderColor: highOnly ? palette.danger : palette.border, marginLeft: 4 }]}>
          <Zap size={12} color={highOnly ? palette.danger : palette.textMuted} />
          <Text style={{ color: highOnly ? palette.danger : palette.textPrimary, fontSize: 12, fontWeight: "700", marginLeft: 4 }}>High Impact</Text>
        </Pressable>
      </ScrollView>

      {loading ? (
        <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      ) : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />} contentContainerStyle={{ padding: 12, paddingBottom: 40 }}>
          {items.length === 0 && (
            <View style={{ padding: 40, alignItems: "center" }}>
              <Text style={{ color: palette.textMuted }}>No news items yet.</Text>
            </View>
          )}
          {items.map((it) => (
            <Pressable key={it.news_id} onPress={() => router.push(`/ai/news/${it.news_id}` as any)} style={[s.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <Text style={[s.tagChip, { color: palette.primary, backgroundColor: palette.primary + "15" }]}>{it.category_label}</Text>
                {it.high_impact && (
                  <Text style={[s.tagChip, { color: palette.danger, backgroundColor: palette.danger + "15" }]}>HIGH IMPACT</Text>
                )}
                <View style={{ flex: 1 }} />
                <SentimentIcon s={it.sentiment} palette={palette} />
                <Text style={{ fontSize: 10, color: sentimentColor(it.sentiment, palette), textTransform: "capitalize" }}>{(it.sentiment || "").replace(/_/g, " ")}</Text>
              </View>
              <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800", lineHeight: 20 }}>{it.title}</Text>
              <Text numberOfLines={2} style={{ color: palette.textMuted, fontSize: 12, marginTop: 6, lineHeight: 17 }}>{it.summary}</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 }}>
                <Text style={{ color: palette.textMuted, fontSize: 10 }}>{relTime(it.published_at)}</Text>
                {it.symbol_snapshot?.symbol && (
                  <Text style={{ color: palette.textMuted, fontSize: 10 }}>· {it.symbol_snapshot.symbol}</Text>
                )}
                {it.symbol_snapshot?.change_pct != null && (
                  <Text style={{ color: it.symbol_snapshot.change_pct >= 0 ? palette.success : palette.danger, fontSize: 10, fontWeight: "800" }}>
                    {it.symbol_snapshot.change_pct >= 0 ? "+" : ""}{it.symbol_snapshot.change_pct.toFixed(2)}%
                  </Text>
                )}
              </View>
            </Pressable>
          ))}
        </ScrollView>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 20, fontWeight: "800" },
  pill: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, height: 30, borderRadius: 15, borderWidth: 1 },
  card: { padding: 12, borderRadius: 12, borderWidth: 1, marginBottom: 10 },
  tagChip: { fontSize: 9, fontWeight: "900", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5, letterSpacing: 0.3 },
});
