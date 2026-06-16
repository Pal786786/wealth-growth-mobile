import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { ChevronLeft, TrendingUp, CalendarDays } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const PRESETS = [500, 1000, 5000, 10000, 25000];

export default function InvestBuy() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const params = useLocalSearchParams<{ id: string; name: string; type: string }>();
  const [amount, setAmount] = useState("");
  const [sip, setSip] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const num = parseFloat(amount);
    if (!num || num < 100) { show("error", "Min investment ₹100"); return; }
    setLoading(true);
    try {
      await api.post("/invest/buy", {
        asset_id: params.id,
        asset_type: params.type,
        asset_name: params.name,
        amount: num,
        sip,
      });
      show("success", `${sip ? "SIP started" : "Investment placed"} • ₹${num} in ${params.name}`);
      router.back();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Investment failed");
    } finally { setLoading(false); }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={[s.hero, { backgroundColor: palette.primary + "1A" }]}>
          <TrendingUp color={palette.primary} size={30} />
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>{params.name}</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>{prettyType(params.type as string)}</Text>

        <Card style={{ gap: 14, marginTop: 12 }}>
          <Input
            label="Investment Amount (₹)"
            placeholder="500"
            keyboardType="decimal-pad"
            value={amount}
            onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
            testID="invest-amount-input"
          />
          <View style={s.chipsRow}>
            {PRESETS.map((p) => (
              <Pressable
                key={p}
                onPress={() => setAmount(String(p))}
                style={[s.chip, { backgroundColor: palette.surface, borderColor: palette.border }]}
              >
                <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>₹{p}</Text>
              </Pressable>
            ))}
          </View>

          {(params.type === "mutual_fund" || params.type === "gold") && (
            <Pressable
              onPress={() => setSip((v) => !v)}
              style={[s.sipBox, { borderColor: sip ? palette.primary : palette.border, backgroundColor: sip ? palette.primary + "10" : palette.surface }]}
              testID="invest-sip-toggle"
            >
              <CalendarDays color={sip ? palette.primary : palette.textMuted} size={20} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "700" }}>Monthly SIP</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 2 }}>Invest the same amount every month</Text>
              </View>
              <View style={[s.checkbox, { borderColor: sip ? palette.primary : palette.border, backgroundColor: sip ? palette.primary : "transparent" }]}>
                {sip ? <Text style={{ color: "#fff", fontSize: 12, fontWeight: "800" }}>✓</Text> : null}
              </View>
            </Pressable>
          )}

          <Button label={sip ? "Start SIP" : "Invest Now"} onPress={submit} loading={loading} testID="invest-submit-btn" />
        </Card>
      </ScrollView>
    </Screen>
  );
}

function prettyType(t: string) {
  return {
    mutual_fund: "Mutual Fund", stock: "Stock", gold: "Digital Gold",
    fd: "Fixed Deposit", govt: "Government Scheme",
  }[t] || t;
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 12, paddingBottom: 40 },
  hero: { alignSelf: "center", padding: 18, borderRadius: 18, marginTop: 12 },
  title: { fontSize: 22, fontWeight: "800", textAlign: "center", letterSpacing: -0.5, paddingHorizontal: 12 },
  sub: { fontSize: 13, textAlign: "center" },
  chipsRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  sipBox: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 14, borderWidth: 1 },
  checkbox: { width: 24, height: 24, borderRadius: 8, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
});
