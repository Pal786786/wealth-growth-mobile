import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Send } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const PRESETS = [100, 500, 1000, 5000];

export default function SendMoney() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const num = parseFloat(amount);
    if (!recipient || !num || num <= 0) {
      show("error", "Enter recipient and a valid amount");
      return;
    }
    setLoading(true);
    try {
      await api.post("/wallet/send", { recipient, amount: num, note });
      show("success", `Sent ₹${num} to ${recipient}`);
      router.back();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Send failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn">
        <ChevronLeft color={palette.textPrimary} size={26} />
      </Pressable>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={[s.iconHero, { backgroundColor: palette.primary + "1A" }]}>
          <Send color={palette.primary} size={32} />
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>Send Money</Text>
        <Text style={[s.subtitle, { color: palette.textSecondary }]}>UPI ID, mobile number or bank a/c</Text>
        <View style={s.form}>
          <Input
            label="Recipient"
            placeholder="9876543210 or name@upi"
            value={recipient}
            onChangeText={setRecipient}
            autoCapitalize="none"
            testID="send-recipient-input"
          />
          <Input
            label="Amount (₹)"
            placeholder="0"
            value={amount}
            onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
            keyboardType="decimal-pad"
            testID="send-amount-input"
          />
          <View style={s.presets}>
            {PRESETS.map((p) => (
              <Pressable
                key={p}
                onPress={() => setAmount(String(p))}
                style={[s.preset, { borderColor: palette.border, backgroundColor: palette.surface }]}
                testID={`send-preset-${p}`}
              >
                <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>₹{p}</Text>
              </Pressable>
            ))}
          </View>
          <Input label="Note (optional)" placeholder="What's it for?" value={note} onChangeText={setNote} testID="send-note-input" />
          <Button label="Send Money" loading={loading} onPress={submit} testID="send-submit-btn" />
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 16, paddingBottom: 40 },
  iconHero: { alignSelf: "center", padding: 18, borderRadius: 20, marginTop: 12 },
  title: { fontSize: 24, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  subtitle: { fontSize: 13, textAlign: "center" },
  form: { gap: 14, marginTop: 12 },
  presets: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  preset: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12, borderWidth: 1 },
});
