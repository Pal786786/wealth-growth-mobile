import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Alert } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { ChevronLeft, Trash2, Sparkles, PieChart, Lightbulb } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { advisorApi, type Goal } from "@/src/api/advisor";
import { formatINR } from "@/src/utils/format";

export default function GoalDetail() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [g, setG] = useState<Goal | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setG(await advisorApi.getGoal(String(id))); } finally { setLoading(false); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const del = () => Alert.alert("Delete goal?", undefined, [
    { text: "Cancel", style: "cancel" },
    { text: "Delete", style: "destructive", onPress: async () => {
      try { await advisorApi.deleteGoal(String(id)); show("success", "Goal deleted"); router.replace("/advisor/goals"); }
      catch { show("error", "Could not delete"); }
    } },
  ]);

  if (loading || !g) return <Screen><ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} /></Screen>;

  const notes = g.ai_notes;
  const monthlySip = notes?.monthly_sip ?? g.recommended_monthly_sip;
  const expRet = notes?.expected_return_pct ?? g.expected_return_pct;
  const prob = notes?.probability ?? g.probability_pct;

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>{g.title}</Text>
        <Pressable onPress={del} hitSlop={10}><Trash2 color={palette.danger} size={20} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 80 }}>
        <LinearGradient colors={["#1E3A8A", "#0EA5E9"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <Text style={s.heroLabel}>TARGET</Text>
          <Text style={s.heroAmount}>{formatINR(g.target_amount)}</Text>
          <Text style={s.heroSub}>in {g.horizon_years} years · {g.risk_appetite} risk</Text>
          <View style={s.metricsRow}>
            <View style={s.metric}>
              <Text style={s.metricLabel}>Monthly SIP</Text>
              <Text style={s.metricValue}>{formatINR(monthlySip)}</Text>
            </View>
            <View style={s.metric}>
              <Text style={s.metricLabel}>Expected p.a.</Text>
              <Text style={s.metricValue}>{expRet}%</Text>
            </View>
            <View style={s.metric}>
              <Text style={s.metricLabel}>Success</Text>
              <Text style={[s.metricValue, { color: prob >= 70 ? "#10B981" : prob >= 50 ? "#F59E0B" : "#EF4444" }]}>{prob}%</Text>
            </View>
          </View>
        </LinearGradient>

        {notes?.strategy && (
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <Sparkles color={palette.primary} size={16} />
              <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", letterSpacing: 0.6 }}>STRATEGY</Text>
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 13, lineHeight: 20 }}>{notes.strategy}</Text>
          </Card>
        )}

        {notes?.asset_mix && notes.asset_mix.length > 0 && (
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 10 }}>
              <PieChart color={palette.primary} size={16} />
              <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", letterSpacing: 0.6 }}>ASSET MIX</Text>
            </View>
            {notes.asset_mix.map((a, i) => (
              <View key={i} style={{ marginBottom: 10 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }}>{a.asset}</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 12, fontWeight: "800" }}>{a.pct}%</Text>
                </View>
                <View style={{ height: 6, backgroundColor: palette.chipBg, borderRadius: 3, overflow: "hidden" }}>
                  <View style={{ height: 6, width: `${a.pct}%`, backgroundColor: palette.primary }} />
                </View>
                <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 4, lineHeight: 16 }}>{a.why}</Text>
              </View>
            ))}
          </Card>
        )}

        {notes?.tips && notes.tips.length > 0 && (
          <Card>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 }}>
              <Lightbulb color={palette.warning} size={16} />
              <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", letterSpacing: 0.6 }}>TIPS</Text>
            </View>
            {notes.tips.map((t, i) => (
              <View key={i} style={{ flexDirection: "row", gap: 8, marginBottom: 4 }}>
                <Text style={{ color: palette.warning }}>•</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 12, flex: 1, lineHeight: 18 }}>{t}</Text>
              </View>
            ))}
          </Card>
        )}

        <Button label="Chat about this goal" onPress={() => router.push("/advisor")} />

        {(notes?.disclaimer) && (
          <Text style={{ color: palette.textMuted, fontSize: 11, textAlign: "center", lineHeight: 16 }}>{notes.disclaimer}</Text>
        )}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { flex: 1, fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  hero: { padding: 22, borderRadius: 22, gap: 4 },
  heroLabel: { color: "rgba(255,255,255,0.7)", fontSize: 10, fontWeight: "800", letterSpacing: 1.2 },
  heroAmount: { color: "#fff", fontSize: 34, fontWeight: "900", letterSpacing: -1 },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 12, marginTop: 2 },
  metricsRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  metric: { flex: 1, backgroundColor: "rgba(255,255,255,0.14)", padding: 10, borderRadius: 12, borderWidth: 1, borderColor: "rgba(255,255,255,0.22)" },
  metricLabel: { color: "rgba(255,255,255,0.7)", fontSize: 9, fontWeight: "800", letterSpacing: 0.6 },
  metricValue: { color: "#fff", fontSize: 15, fontWeight: "900", marginTop: 2 },
});
