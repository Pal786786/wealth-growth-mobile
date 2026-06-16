import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Zap, Droplets, Flame, Tv, Wifi, Car, Shield, Smartphone, Receipt } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const ICONS: Record<string, any> = {
  electricity: Zap, water: Droplets, gas: Flame, dth: Tv, broadband: Wifi,
  fastag: Car, insurance: Shield, mobile: Smartphone,
};

export default function Bills() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [types, setTypes] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [biller, setBiller] = useState("");
  const [consumer, setConsumer] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get("/bills/types").then(({ data }) => setTypes(data)).catch(() => {}); }, []);

  const submit = async () => {
    const num = parseFloat(amount);
    if (!selected || !biller || !consumer || !num) {
      show("error", "Please fill all fields"); return;
    }
    setLoading(true);
    try {
      await api.post("/wallet/billpay", {
        biller_type: selected.id, biller_name: biller, consumer_number: consumer, amount: num,
      });
      show("success", `Bill paid! ₹${num} to ${biller}`);
      router.back();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Payment failed");
    } finally { setLoading(false); }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={[s.iconHero, { backgroundColor: "#8B5CF6" + "1A" }]}>
          <Receipt color="#8B5CF6" size={30} />
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>Pay Bills</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Choose a bill category</Text>

        <View style={s.grid}>
          {types.map((t) => {
            const Icon = ICONS[t.id] || Zap;
            const isSel = selected?.id === t.id;
            return (
              <Pressable
                key={t.id}
                onPress={() => setSelected(t)}
                style={[s.tile, {
                  backgroundColor: isSel ? palette.primary + "15" : palette.surface,
                  borderColor: isSel ? palette.primary : palette.border,
                }]}
                testID={`bill-type-${t.id}`}
              >
                <View style={[s.tileIcon, { backgroundColor: palette.primary + "1A" }]}>
                  <Icon color={palette.primary} size={22} />
                </View>
                <Text style={[s.tileLabel, { color: palette.textPrimary }]} numberOfLines={1}>{t.name}</Text>
              </Pressable>
            );
          })}
        </View>

        {selected ? (
          <Card style={{ gap: 12, marginTop: 8 }}>
            <Text style={[s.formTitle, { color: palette.textPrimary }]}>{selected.name} bill</Text>
            <Input label="Biller / Provider" placeholder={`e.g. ${selected.name} Board`} value={biller} onChangeText={setBiller} testID="bill-biller-input" />
            <Input label="Consumer / Account Number" placeholder="ABCD1234" value={consumer} onChangeText={setConsumer} autoCapitalize="characters" testID="bill-consumer-input" />
            <Input label="Amount (₹)" placeholder="0" keyboardType="decimal-pad" value={amount} onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))} testID="bill-amount-input" />
            <Button label="Pay Bill" onPress={submit} loading={loading} testID="bill-submit-btn" />
          </Card>
        ) : null}
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
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8 },
  tile: { width: "30%", padding: 12, borderRadius: 16, borderWidth: 1, alignItems: "center", gap: 8 },
  tileIcon: { padding: 10, borderRadius: 12 },
  tileLabel: { fontSize: 12, fontWeight: "700", textAlign: "center" },
  formTitle: { fontSize: 16, fontWeight: "800" },
});
