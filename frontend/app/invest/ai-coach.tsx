import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator,
  RefreshControl, Animated, Easing,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  Sparkles, RefreshCw, TrendingUp, TrendingDown, Minus, Info, Shield,
  ArrowLeft, Activity, AlertTriangle,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";

type Rec = {
  symbol: string;
  name?: string;
  action: "buy" | "hold" | "sell";
  confidence: "low" | "med" | "high";
  reason: string;
};
type Sip = { amount: number; scheme_type: string; reason: string } | null;
type AiResponse = {
  overall_summary: string;
  risk_score: number;
  risk_label: string;
  recommendations: Rec[];
  suggested_sip: Sip;
  next_steps?: string[];
  disclaimer: string;
  mode: "live" | "demo";
  generated_at?: string;
  cached?: boolean;
};

const ACTION_META: Record<Rec["action"], { color: string; bg: string; label: string; Icon: any }> = {
  buy: { color: "#15803D", bg: "#DCFCE7", label: "BUY", Icon: TrendingUp },
  hold: { color: "#0369A1", bg: "#DBEAFE", label: "HOLD", Icon: Minus },
  sell: { color: "#B91C1C", bg: "#FEE2E2", label: "SELL", Icon: TrendingDown },
};

const CONF_META: Record<Rec["confidence"], { label: string; cls: string }> = {
  high: { label: "High confidence", cls: "#10B981" },
  med: { label: "Medium confidence", cls: "#F59E0B" },
  low: { label: "Low confidence", cls: "#94A3B8" },
};

export default function AiCoachScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<AiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spin = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (loading || refreshing) {
      Animated.loop(
        Animated.timing(spin, { toValue: 1, duration: 1400, easing: Easing.linear, useNativeDriver: true }),
      ).start();
    } else {
      spin.stopAnimation();
      spin.setValue(0);
    }
  }, [loading, refreshing, spin]);

  const load = useCallback(async (force = false) => {
    setError(null);
    try {
      const { data } = await api.get<AiResponse>(`/invest/ai-suggestions${force ? "?refresh=true" : ""}`);
      setData(data);
    } catch (e: any) {
      setError("Couldn't load suggestions. Please try again.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);

  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <Stack.Screen options={{ headerShown: false }} />

      {/* Hero header */}
      <LinearGradient
        colors={["#0F172A", "#7C3AED", "#EC4899"]}
        start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
        style={[s.hero, { paddingTop: insets.top + 12 }]}
      >
        <View style={s.heroTopRow}>
          <Pressable onPress={() => router.back()} style={s.iconBtn} testID="ai-back">
            <ArrowLeft color="#fff" size={20} />
          </Pressable>
          <Pressable
            onPress={() => { setRefreshing(true); load(true); }}
            style={s.iconBtn}
            testID="ai-refresh"
          >
            <Animated.View style={{ transform: [{ rotate }] }}>
              <RefreshCw color="#fff" size={18} />
            </Animated.View>
          </Pressable>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 8 }}>
          <View style={s.heroIconWrap}>
            <Sparkles color="#fff" size={22} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.heroTitle}>AI Investment Coach</Text>
            <Text style={s.heroSub}>Personalised by Claude Sonnet 4.6</Text>
          </View>
        </View>
        {data?.mode === "demo" ? (
          <View style={s.demoChip}>
            <AlertTriangle color="#FDE68A" size={12} />
            <Text style={s.demoChipText}>Demo suggestions (LLM key not active)</Text>
          </View>
        ) : null}
      </LinearGradient>

      <ScrollView
        contentContainerStyle={[s.scroll, { paddingBottom: insets.bottom + 30 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(true); }} tintColor="#7C3AED" />}
      >
        {loading ? (
          <View style={{ paddingTop: 40, alignItems: "center" }}>
            <ActivityIndicator size="large" color="#7C3AED" />
            <Text style={{ color: palette.textSecondary, marginTop: 12, fontWeight: "600" }}>
              Analyzing your portfolio…
            </Text>
          </View>
        ) : null}

        {error ? (
          <Card style={{ borderColor: "#FCA5A5", borderWidth: 1 }}>
            <Text style={{ color: palette.danger, fontWeight: "600" }}>{error}</Text>
          </Card>
        ) : null}

        {data && !loading ? (
          <>
            {/* Summary card */}
            <Card style={s.summaryCard}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <Activity color="#7C3AED" size={16} />
                <Text style={[s.summaryTitle, { color: palette.textPrimary }]}>Today&apos;s snapshot</Text>
              </View>
              <Text style={[s.summaryBody, { color: palette.textPrimary }]}>{data.overall_summary}</Text>

              <View style={s.riskRow}>
                <Text style={[s.riskLabel, { color: palette.textSecondary }]}>Risk profile</Text>
                <View style={s.riskBar}>
                  {[1, 2, 3, 4, 5].map((i) => (
                    <View key={i} style={[
                      s.riskSeg,
                      { backgroundColor: i <= data.risk_score ? riskColor(i) : palette.border },
                    ]} />
                  ))}
                </View>
                <Text style={[s.riskBadge, { color: riskColor(data.risk_score) }]}>{data.risk_label}</Text>
              </View>

              {data.cached ? (
                <Text style={{ fontSize: 11, color: palette.textSecondary, marginTop: 8 }}>
                  Cached · refreshes every 30 min · pull to refresh
                </Text>
              ) : null}
            </Card>

            {/* Recommendations */}
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Recommendations</Text>
            {(data.recommendations || []).map((r, idx) => (
              <RecCard key={idx} rec={r} palette={palette} />
            ))}

            {/* Suggested SIP */}
            {data.suggested_sip ? (
              <Card style={s.sipCard}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <Shield color="#0EA5E9" size={16} />
                  <Text style={[s.sipTitle, { color: palette.textPrimary }]}>Suggested SIP</Text>
                </View>
                <Text style={s.sipAmount}>₹{data.suggested_sip.amount.toLocaleString("en-IN")}/mo</Text>
                <Text style={{ color: palette.textPrimary, fontWeight: "700", marginTop: 2 }}>
                  {data.suggested_sip.scheme_type}
                </Text>
                <Text style={{ color: palette.textSecondary, marginTop: 4, fontSize: 13 }}>
                  {data.suggested_sip.reason}
                </Text>
              </Card>
            ) : null}

            {/* Next steps */}
            {data.next_steps && data.next_steps.length > 0 ? (
              <>
                <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Next steps</Text>
                <Card style={{ paddingVertical: 6 }}>
                  {data.next_steps.map((step, i) => (
                    <View key={i} style={s.stepRow}>
                      <View style={s.stepDot} />
                      <Text style={[s.stepText, { color: palette.textPrimary }]}>{step}</Text>
                    </View>
                  ))}
                </Card>
              </>
            ) : null}

            {/* Disclaimer */}
            <View style={s.disclaimer}>
              <Info color="#94A3B8" size={14} />
              <Text style={[s.disclaimerText, { color: palette.textSecondary }]}>{data.disclaimer}</Text>
            </View>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function RecCard({ rec, palette }: { rec: Rec; palette: any }) {
  const m = ACTION_META[rec.action] || ACTION_META.hold;
  const conf = CONF_META[rec.confidence] || CONF_META.med;
  return (
    <Card style={s.recCard}>
      <View style={s.recHead}>
        <View style={{ flex: 1 }}>
          <Text style={[s.recSym, { color: palette.textPrimary }]}>{rec.symbol}</Text>
          {rec.name ? <Text style={{ fontSize: 12, color: palette.textSecondary, marginTop: 1 }}>{rec.name}</Text> : null}
        </View>
        <View style={[s.actionBadge, { backgroundColor: m.bg }]}>
          <m.Icon color={m.color} size={14} />
          <Text style={[s.actionBadgeText, { color: m.color }]}>{m.label}</Text>
        </View>
      </View>
      <Text style={[s.recReason, { color: palette.textPrimary }]}>{rec.reason}</Text>
      <View style={s.recFoot}>
        <View style={[s.confDot, { backgroundColor: conf.cls }]} />
        <Text style={{ fontSize: 11, fontWeight: "700", color: palette.textSecondary }}>{conf.label}</Text>
      </View>
    </Card>
  );
}

function riskColor(score: number) {
  if (score <= 1) return "#10B981";
  if (score === 2) return "#34D399";
  if (score === 3) return "#F59E0B";
  if (score === 4) return "#F97316";
  return "#EF4444";
}

const s = StyleSheet.create({
  root: { flex: 1 },
  hero: { paddingHorizontal: 16, paddingBottom: 22, borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  heroTopRow: { flexDirection: "row", justifyContent: "space-between" },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  heroIconWrap: { width: 44, height: 44, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  heroTitle: { color: "#fff", fontSize: 22, fontWeight: "800" },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontWeight: "600", marginTop: 2 },
  demoChip: { flexDirection: "row", alignSelf: "flex-start", alignItems: "center", gap: 6, marginTop: 14, backgroundColor: "rgba(0,0,0,0.25)", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  demoChipText: { color: "#FDE68A", fontSize: 11, fontWeight: "700" },

  scroll: { padding: 16, gap: 12 },

  summaryCard: { gap: 4 },
  summaryTitle: { fontSize: 14, fontWeight: "800" },
  summaryBody: { fontSize: 14, lineHeight: 20 },
  riskRow: { flexDirection: "row", alignItems: "center", marginTop: 12, gap: 10 },
  riskLabel: { fontSize: 12, fontWeight: "700" },
  riskBar: { flexDirection: "row", gap: 3, flex: 1 },
  riskSeg: { flex: 1, height: 6, borderRadius: 3 },
  riskBadge: { fontSize: 12, fontWeight: "800" },

  sectionTitle: { fontSize: 16, fontWeight: "800", marginTop: 6 },

  recCard: { gap: 6 },
  recHead: { flexDirection: "row", alignItems: "center" },
  recSym: { fontSize: 16, fontWeight: "800" },
  actionBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999 },
  actionBadgeText: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  recReason: { fontSize: 13, lineHeight: 18 },
  recFoot: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  confDot: { width: 8, height: 8, borderRadius: 4 },

  sipCard: { borderColor: "#BAE6FD", borderWidth: 1, backgroundColor: "#F0F9FF" },
  sipTitle: { fontSize: 14, fontWeight: "800" },
  sipAmount: { color: "#0EA5E9", fontSize: 26, fontWeight: "800", marginTop: 4 },

  stepRow: { flexDirection: "row", gap: 10, paddingVertical: 8, alignItems: "flex-start" },
  stepDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#7C3AED", marginTop: 7 },
  stepText: { flex: 1, fontSize: 13, lineHeight: 19 },

  disclaimer: { flexDirection: "row", gap: 6, marginTop: 18, paddingHorizontal: 4 },
  disclaimerText: { flex: 1, fontSize: 11, lineHeight: 15, fontStyle: "italic" },
});
