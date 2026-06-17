import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Shield, Heart, Car, Plane, Calculator } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";

const ICONS: Record<string, any> = { health: Heart, life: Shield, motor: Car, travel: Plane };

export default function Insurance() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [plans, setPlans] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [filter, setFilter] = useState<string>("all");

  const load = async () => {
    try {
      const [{ data: p }, { data: my }] = await Promise.all([
        api.get("/insurance/plans"),
        api.get("/insurance/policies"),
      ]);
      setPlans(p); setPolicies(my);
    } catch {}
  };

  useEffect(() => { load(); }, []);

  const buy = async (plan: any) => {
    try {
      await api.post(`/insurance/buy?plan_id=${plan.id}`);
      show("success", `Policy active: ${plan.name}`);
      load();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not buy policy");
    }
  };

  const filtered = filter === "all" ? plans : plans.filter((p) => p.type === filter);

  const [calcType, setCalcType] = useState<string>("health");
  const [calcAge, setCalcAge] = useState("35");
  const [calcCover, setCalcCover] = useState("500000");
  const [calcResult, setCalcResult] = useState<any>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const runCalculator = async () => {
    setCalcLoading(true);
    try {
      const body: any = { plan_type: calcType, age: Number(calcAge) || 30, cover: Number(calcCover) || 500000 };
      if (calcType === "motor") body.vehicle_age = 3;
      if (calcType === "travel") body.trip_days = 7;
      const { data } = await api.post("/insurance/quote", body);
      setCalcResult(data);
    } catch {
      show("error", "Could not calculate premium");
    } finally { setCalcLoading(false); }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={[s.title, { color: palette.textPrimary }]}>Insurance</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Protect what matters most</Text>

        {/* Premium Calculator */}
        <Card style={{ gap: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Calculator color={palette.primary} size={18} />
            <Text style={{ fontSize: 14, fontWeight: "800", color: palette.textPrimary }}>Premium Calculator</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {["health", "life", "motor", "travel"].map((t) => (
              <Pressable key={t} onPress={() => { setCalcType(t); setCalcResult(null); }}
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 14, borderWidth: 1,
                  backgroundColor: calcType === t ? palette.primary : palette.surfaceAlt,
                  borderColor: calcType === t ? palette.primary : palette.border }}>
                <Text style={{ color: calcType === t ? "#fff" : palette.textPrimary, fontWeight: "700", textTransform: "capitalize", fontSize: 12 }}>{t}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "600" }}>Age</Text>
              <TextInput
                value={calcAge} onChangeText={setCalcAge} keyboardType="number-pad"
                style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 10, color: palette.textPrimary, marginTop: 4 }}
                testID="calc-age"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "600" }}>Cover ₹</Text>
              <TextInput
                value={calcCover} onChangeText={setCalcCover} keyboardType="number-pad"
                style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 10, color: palette.textPrimary, marginTop: 4 }}
                testID="calc-cover"
              />
            </View>
          </View>
          <Pressable
            onPress={runCalculator}
            disabled={calcLoading}
            style={{ backgroundColor: palette.primary, paddingVertical: 12, borderRadius: 12, alignItems: "center" }}
            testID="calc-quote-btn"
          >
            <Text style={{ color: "#fff", fontWeight: "800" }}>
              {calcLoading ? "Calculating…" : "Calculate Premium"}
            </Text>
          </Pressable>
          {calcResult ? (
            <View style={{ backgroundColor: palette.surfaceAlt, padding: 12, borderRadius: 12, gap: 4 }}>
              <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>ESTIMATED ANNUAL PREMIUM</Text>
              <Text style={{ color: palette.primary, fontSize: 22, fontWeight: "800" }}>
                {formatINR(calcResult.total_annual_premium)}
              </Text>
              <Text style={{ color: palette.textSecondary, fontSize: 12 }}>
                ≈ {formatINR(calcResult.monthly_emi)}/month · incl. GST {formatINR(calcResult.gst)}
              </Text>
              <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 4, fontStyle: "italic" }}>{calcResult.disclaimer}</Text>
            </View>
          ) : null}
        </Card>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipsRow}>
          {["all", "health", "life", "motor", "travel"].map((f) => (
            <Pressable
              key={f}
              onPress={() => setFilter(f)}
              style={[s.chip, {
                backgroundColor: filter === f ? palette.primary : palette.surface,
                borderColor: filter === f ? palette.primary : palette.border,
              }]}
              testID={`ins-filter-${f}`}
            >
              <Text style={{ color: filter === f ? "#fff" : palette.textPrimary, fontWeight: "700", textTransform: "capitalize" }}>{f}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {filtered.map((p) => {
          const Icon = ICONS[p.type] || Shield;
          return (
            <Card key={p.id} style={{ gap: 10 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <View style={[s.iconWrap, { backgroundColor: palette.primary + "1A" }]}>
                  <Icon color={palette.primary} size={22} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.planName, { color: palette.textPrimary }]}>{p.name}</Text>
                  <Text style={[s.planMeta, { color: palette.textSecondary }]}>Cover {formatINR(p.cover, { compact: true })}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[s.premium, { color: palette.primary }]}>{formatINR(p.premium)}</Text>
                  <Text style={[s.planMeta, { color: palette.textMuted }]}>per year</Text>
                </View>
              </View>
              <Pressable
                onPress={() => buy(p)}
                style={[s.buyBtn, { backgroundColor: palette.primary }]}
                testID={`buy-policy-${p.id}`}
              >
                <Text style={{ color: "#fff", fontWeight: "800" }}>Buy Policy</Text>
              </Pressable>
            </Card>
          );
        })}

        {policies.length > 0 ? (
          <>
            <Text style={[s.section, { color: palette.textPrimary }]}>Your Active Policies</Text>
            {policies.map((p) => (
              <Card key={p.policy_id} style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <View style={[s.iconWrap, { backgroundColor: palette.success + "1A" }]}>
                  <Shield color={palette.success} size={20} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.planName, { color: palette.textPrimary }]}>{p.plan_name}</Text>
                  <Text style={[s.planMeta, { color: palette.textSecondary }]}>Active • Cover {formatINR(p.cover, { compact: true })}</Text>
                </View>
                <Text style={{ color: palette.success, fontWeight: "800" }}>{formatINR(p.premium)}</Text>
              </Card>
            ))}
          </>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 12, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5, marginTop: 4 },
  sub: { fontSize: 13 },
  chipsRow: { gap: 8, paddingRight: 16, paddingBottom: 4 },
  chip: { paddingHorizontal: 14, height: 36, borderRadius: 18, borderWidth: 1, justifyContent: "center", flexShrink: 0 },
  iconWrap: { padding: 10, borderRadius: 12 },
  planName: { fontSize: 14, fontWeight: "700" },
  planMeta: { fontSize: 11, marginTop: 2 },
  premium: { fontSize: 16, fontWeight: "800" },
  buyBtn: { paddingVertical: 12, borderRadius: 12, alignItems: "center", marginTop: 4 },
  section: { fontSize: 16, fontWeight: "800", marginTop: 8, letterSpacing: -0.3 },
});
