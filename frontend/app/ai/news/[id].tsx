import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, Zap, TrendingUp, TrendingDown, Minus, Tag } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiNewsApi, NewsItem, sentimentColor } from "@/src/api/aiNews";
import { errText } from "@/src/utils/errors";

export default function NewsDetail() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [item, setItem] = useState<NewsItem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { setItem(await aiNewsApi.newsDetail(String(id))); }
      catch (e) { show("error", errText(e, "Failed to load news")); }
      finally { setLoading(false); }
    })();
  }, [id, show]);

  const senIcon = () => {
    const s = item?.sentiment || "";
    if (s.includes("bullish")) return <TrendingUp size={14} color={palette.success} />;
    if (s.includes("bearish")) return <TrendingDown size={14} color={palette.danger} />;
    return <Minus size={14} color={palette.textMuted} />;
  };

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary, flex: 1 }]} numberOfLines={1}>News detail</Text>
      </View>
      {loading ? (
        <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      ) : !item ? (
        <View style={{ padding: 40, alignItems: "center" }}><Text style={{ color: palette.textMuted }}>News not found.</Text></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <Text style={[s.chip, { color: palette.primary, backgroundColor: palette.primary + "15" }]}>{item.category_label}</Text>
            {item.high_impact && (
              <Text style={[s.chip, { color: palette.danger, backgroundColor: palette.danger + "15" }]}><Zap size={9} color={palette.danger} /> HIGH IMPACT</Text>
            )}
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              {senIcon()}
              <Text style={{ fontSize: 11, color: sentimentColor(item.sentiment, palette), textTransform: "capitalize" }}>{(item.sentiment || "neutral").replace(/_/g, " ")}</Text>
            </View>
          </View>
          <Text style={{ color: palette.textPrimary, fontSize: 20, fontWeight: "900", lineHeight: 27 }}>{item.title}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 6 }}>{new Date(item.published_at).toLocaleString()}</Text>

          {item.symbol_snapshot?.symbol && (
            <View style={[s.snapshot, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>PRICE SNAPSHOT</Text>
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8, marginTop: 4 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "900" }}>{item.symbol_snapshot.symbol}</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "700" }}>{item.symbol_snapshot.price?.toLocaleString(undefined, { maximumFractionDigits: 4 }) || "—"}</Text>
                {item.symbol_snapshot.change_pct != null && (
                  <Text style={{ color: item.symbol_snapshot.change_pct >= 0 ? palette.success : palette.danger, fontSize: 13, fontWeight: "800" }}>
                    {item.symbol_snapshot.change_pct >= 0 ? "+" : ""}{item.symbol_snapshot.change_pct.toFixed(2)}%
                  </Text>
                )}
              </View>
            </View>
          )}

          <Text style={{ color: palette.textPrimary, fontSize: 14, lineHeight: 21, marginTop: 16 }}>{item.summary}</Text>
          <Text style={{ color: palette.textPrimary, fontSize: 14, lineHeight: 22, marginTop: 12 }}>{item.body}</Text>

          {(item.tags || []).length > 0 && (
            <View style={{ marginTop: 20, flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              <Tag size={12} color={palette.textMuted} />
              {item.tags.map((t) => (
                <Text key={t} style={[s.chip, { color: palette.textMuted, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border }]}>#{t}</Text>
              ))}
            </View>
          )}

          <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 22, textAlign: "center" }}>
            {item.is_ai_generated ? "AI-generated by Claude Sonnet 4.5" : "Editorial content"} · Not investment advice
          </Text>
        </ScrollView>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 18, fontWeight: "800" },
  chip: { fontSize: 10, fontWeight: "900", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, letterSpacing: 0.4 },
  snapshot: { marginTop: 14, padding: 12, borderRadius: 10, borderWidth: 1 },
});
