import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Smartphone } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const PRESET_AMOUNTS = [149, 199, 299, 399, 499, 699];

export default function Recharge() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [operators, setOperators] = useState<string[]>([]);
  const [operator, setOperator] = useState<string>("Jio");
  const [mobile, setMobile] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/bills/operators").then(({ data }) => { setOperators(data); setOperator(data[0]); }).catch(() => {});
  }, []);

  const submit = async () => {
    const num = parseFloat(amount);
    if (!/^[0-9]{10}$/.test(mobile)) { show("error", "Enter valid 10-digit mobile"); return; }
    if (!num || num < 10) { show("error", "Min recharge ₹10"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/wallet/recharge", { operator, mobile, amount: num, plan_name: "Custom" });
      show("success", `Recharge successful! 2% cashback ₹${data.cashback} credited`);
      router.back();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Recharge failed");
    } finally { setLoading(false); }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={[s.iconHero, { backgroundColor: palette.warning + "1A" }]}>
          <Smartphone color={palette.warning} size={30} />
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>Mobile Recharge</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Prepaid recharge with 2% instant cashback</Text>
        <View style={s.form}>
          <Input
            label="Mobile Number"
            placeholder="9876543210"
            keyboardType="number-pad"
            value={mobile}
            onChangeText={(v) => setMobile(v.replace(/[^0-9]/g, "").slice(0, 10))}
            testID="recharge-mobile-input"
          />
          <Text style={[s.label, { color: palette.textSecondary }]}>Operator</Text>
          <View style={s.chipsRow}>
            {operators.map((op) => (
              <Pressable
                key={op}
                onPress={() => setOperator(op)}
                style={[s.chip, { backgroundColor: operator === op ? palette.primary : palette.surface, borderColor: operator === op ? palette.primary : palette.border }]}
                testID={`recharge-op-${op}`}
              >
                <Text style={{ color: operator === op ? "#fff" : palette.textPrimary, fontWeight: "700" }}>{op}</Text>
              </Pressable>
            ))}
          </View>
          <Input
            label="Amount (₹)"
            placeholder="e.g. 199"
            keyboardType="decimal-pad"
            value={amount}
            onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
            testID="recharge-amount-input"
          />
          <View style={s.chipsRow}>
            {PRESET_AMOUNTS.map((p) => (
              <Pressable
                key={p}
                onPress={() => setAmount(String(p))}
                style={[s.amountChip, { backgroundColor: palette.surface, borderColor: palette.border }]}
              >
                <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>₹{p}</Text>
              </Pressable>
            ))}
          </View>
          <Button label="Recharge Now" onPress={submit} loading={loading} testID="recharge-submit-btn" />
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 14, paddingBottom: 40 },
  iconHero: { alignSelf: "center", padding: 16, borderRadius: 18, marginTop: 12 },
  title: { fontSize: 24, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  sub: { fontSize: 13, textAlign: "center" },
  form: { gap: 14, marginTop: 8 },
  label: { fontSize: 13, fontWeight: "600", letterSpacing: 0.3 },
  chipsRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  chip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12, borderWidth: 1 },
  amountChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
});
