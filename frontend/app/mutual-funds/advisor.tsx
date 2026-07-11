/**
 * AI Advisor for MF — 6 quick prompt tiles, chat-style answer render.
 */
import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi } from "@/src/api/mutualFunds";
import { Sparkles, TrendingUp, PiggyBank, ShieldCheck, GitBranch, PieChart, LineChart } from "lucide-react-native";
import { Card } from "@/src/components/Card";

const KINDS = [
  { key: "analyze_portfolio", label: "Analyze My Portfolio", icon: LineChart, tint: "#6366F1" },
  { key: "suggest_funds",     label: "Suggest Better Funds", icon: Sparkles, tint: "#F59E0B" },
  { key: "sip_increase",      label: "Suggest SIP Increase", icon: TrendingUp, tint: "#10B981" },
  { key: "tax_saving",        label: "Tax Saving Suggestions", icon: PiggyBank, tint: "#EF4444" },
  { key: "risk_analysis",     label: "Risk Analysis", icon: ShieldCheck, tint: "#8B5CF6" },
  { key: "diversification",   label: "Diversification Advice", icon: GitBranch, tint: "#0EA5E9" },
];

export default function AiAdvisor() {
  const { palette } = useTheme();
  const [loading, setLoading] = useState(false);
  const [answers, setAnswers] = useState<{ kind: string; answer: string }[]>([]);

  const ask = useCallback(async (kind: string) => {
    setLoading(true);
    try {
      const r = await mfApi.ai(kind);
      setAnswers((prev) => [{ kind, answer: r.answer }, ...prev]);
    } catch (e: any) {
      setAnswers((prev) => [{ kind, answer: "Failed to fetch advice. Try again." }, ...prev]);
    } finally { setLoading(false); }
  }, []);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: palette.background }} contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 12 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <Sparkles color={palette.primary} size={20} />
        <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>MF AI Advisor</Text>
      </View>
      <Text style={{ color: palette.textMuted, fontSize: 12 }}>Ask the AI to analyze your portfolio and give personalised suggestions.</Text>

      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        {KINDS.map((k) => (
          <Pressable key={k.key} onPress={() => ask(k.key)} style={[st.tile, { backgroundColor: palette.surface, borderColor: palette.border, width: "48%" }]} testID={`ai-${k.key}`}>
            <View style={{ padding: 10, borderRadius: 10, backgroundColor: k.tint + "22" }}>
              <k.icon color={k.tint} size={18} />
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", textAlign: "center" }}>{k.label}</Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <Card style={{ padding: 20, alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "center" }}>
          <ActivityIndicator color={palette.primary} />
          <Text style={{ color: palette.textSecondary, fontSize: 13 }}>Thinking…</Text>
        </Card>
      ) : null}

      {answers.map((a, i) => {
        const meta = KINDS.find((k) => k.key === a.kind);
        return (
          <Card key={i} style={{ padding: 14, gap: 8 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              {meta ? <meta.icon color={meta.tint} size={16} /> : null}
              <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }}>{meta?.label || a.kind}</Text>
            </View>
            <Text style={{ color: palette.textSecondary, fontSize: 13, lineHeight: 20 }}>{a.answer}</Text>
          </Card>
        );
      })}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  tile: { padding: 14, borderRadius: 16, borderWidth: 1, alignItems: "center", gap: 8 },
});
