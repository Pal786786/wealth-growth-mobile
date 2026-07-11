/**
 * AI Market Summary — Sprint 7C.2
 * Intraday / Daily / Weekly narrative + top movers.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, FileText, TrendingUp, TrendingDown, Sparkles } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiNewsApi, MarketSummary, SummaryType, sentimentColor } from "@/src/api/aiNews";
import { errText } from "@/src/utils/errors";

const TYPES: Array<{ id: SummaryType; label: string; desc: string }> = [
  { id: "intraday", label: "Intraday", desc: "Last 6 hours" },
  { id: "daily", label: "Daily", desc: "Past 24 hours" },
  { id: "weekly", label: "Weekly", desc: "Past 7 days" },
];

export default function MarketSummaryPage() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [type, setType] = useState<SummaryType>("daily");
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await aiNewsApi.summary(type);
      setSummary(r.summary);
    } catch (e) { show("error", errText(e, "Failed to load summary")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [type, show]);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <FileText size={18} color={palette.primary} />
            <Text style={[s.title, { color: palette.textPrimary }]}>AI Market Summary</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
            Powered by Claude Sonnet 4.5
          </Text>
        </View>
      </View>

      <View style={{ flexDirection: "row", gap: 6, padding: 12 }}>
        {TYPES.map((t) => (
          <Pressable key={t.id} onPress={() => setType(t.id)} style={[s.tab, { backgroundColor: type === t.id ? palette.primary : palette.surface, borderColor: type === t.id ? palette.primary : palette.border, flex: 1 }]}>
            <Text style={{ color: type === t.id ? "#fff" : palette.textPrimary, fontSize: 13, fontWeight: "800" }}>{t.label}</Text>
            <Text style={{ color: type === t.id ? "#fff" : palette.textMuted, fontSize: 9, marginTop: 2 }}>{t.desc}</Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      ) : !summary ? (
        <View style={{ padding: 40, alignItems: "center" }}><Text style={{ color: palette.textMuted }}>No summary available.</Text></View>
      ) : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />} contentContainerStyle={{ padding: 14, paddingBottom: 40 }}>
          <View style={[s.headerCard, { backgroundColor: palette.primary + "12", borderColor: palette.primary + "30" }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <Sparkles size={13} color={palette.primary} />
              <Text style={{ color: palette.primary, fontSize: 10, fontWeight: "900", letterSpacing: 0.6 }}>
                {type.toUpperCase()} · {summary.is_ai_generated ? "AI" : "AUTO"}
              </Text>
              <View style={{ flex: 1 }} />
              <Text style={{ color: sentimentColor(summary.sentiment, palette), fontSize: 10, fontWeight: "900", textTransform: "uppercase" }}>
                {summary.sentiment}
              </Text>
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 17, fontWeight: "900", lineHeight: 23 }}>{summary.headline}</Text>
            <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 6 }}>Generated {new Date(summary.generated_at).toLocaleString()}</Text>
          </View>

          <Text style={{ color: palette.textPrimary, fontSize: 14, lineHeight: 22, marginTop: 12 }}>{summary.body}</Text>

          {(summary.key_movers?.length || 0) > 0 && (
            <View style={{ marginTop: 20 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", marginBottom: 8, letterSpacing: 0.5 }}>KEY MOVERS</Text>
              {summary.key_movers.map((m) => {
                const pos = (m.change_pct || 0) >= 0;
                return (
                  <View key={m.symbol} style={[s.moverRow, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                    <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13, width: 90 }}>{m.symbol}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 12, flex: 1 }}>{m.price?.toLocaleString(undefined, { maximumFractionDigits: 4 }) || "—"}</Text>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
                      {pos ? <TrendingUp size={13} color={palette.success} /> : <TrendingDown size={13} color={palette.danger} />}
                      <Text style={{ color: pos ? palette.success : palette.danger, fontWeight: "900", fontSize: 13 }}>
                        {pos ? "+" : ""}{(m.change_pct ?? 0).toFixed(2)}%
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center", marginTop: 22 }}>Not investment advice</Text>
        </ScrollView>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 20, fontWeight: "800" },
  tab: { paddingVertical: 10, borderRadius: 10, borderWidth: 1, alignItems: "center" },
  headerCard: { padding: 14, borderRadius: 12, borderWidth: 1 },
  moverRow: { flexDirection: "row", alignItems: "center", padding: 10, borderRadius: 10, borderWidth: 1, marginBottom: 6 },
});
