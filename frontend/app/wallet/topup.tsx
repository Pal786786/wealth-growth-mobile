import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, AppState, AppStateStatus } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { ChevronLeft, Plus, CreditCard, CheckCircle2 } from "lucide-react-native";
import * as WebBrowser from "expo-web-browser";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const PRESETS = [500, 1000, 2000, 5000, 10000];

export default function TopUp() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const params = useLocalSearchParams();
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const pollRef = useRef<any>(null);

  // If user lands here via success deep link, verify session
  useEffect(() => {
    const sid = params.session_id as string | undefined;
    if (sid) {
      setSessionId(sid);
      verify(sid, 0);
    }
  }, []);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  const verify = async (sid: string, attempt: number) => {
    setVerifying(true);
    try {
      const { data } = await api.get(`/wallet/topup/status/${sid}`);
      if (data.status === "completed") {
        show("success", `₹${data.amount} added to wallet!`);
        setCompleted(true);
        setVerifying(false);
        return;
      }
      if (attempt < 8) {
        pollRef.current = setTimeout(() => verify(sid, attempt + 1), 2000);
      } else {
        setVerifying(false);
        show("info", "Payment is being processed. Check back in a moment.");
      }
    } catch (e: any) {
      setVerifying(false);
      show("error", "Could not verify payment");
    }
  };

  const create = async () => {
    const num = parseFloat(amount);
    if (!num || num < 10) {
      show("error", "Minimum top-up is ₹10");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/wallet/topup/create-session", { amount: num, platform: "native" });
      setSessionId(data.session_id);
      if (data.demo) {
        // Demo mode: instantly verify
        show("info", "Demo mode: simulating successful payment…");
        await new Promise((r) => setTimeout(r, 800));
        verify(data.session_id, 0);
        return;
      }
      const res = await WebBrowser.openAuthSessionAsync(data.checkout_url, undefined);
      // when user returns
      if (res.type === "success" || res.type === "dismiss" || res.type === "cancel") {
        verify(data.session_id, 0);
      }
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not start payment");
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
        <View style={[s.iconHero, { backgroundColor: palette.success + "1A" }]}>
          {completed ? <CheckCircle2 color={palette.success} size={32} /> : <Plus color={palette.success} size={32} />}
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>
          {completed ? "Payment Successful" : "Add Money to Wallet"}
        </Text>
        <Text style={[s.subtitle, { color: palette.textSecondary }]}>
          {completed
            ? "Your wallet has been credited."
            : "Pay securely with credit/debit card via Stripe"}
        </Text>

        {!completed && (
          <View style={s.form}>
            <Input
              label="Amount (₹)"
              placeholder="e.g. 1000"
              value={amount}
              onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
              keyboardType="decimal-pad"
              testID="topup-amount-input"
            />
            <View style={s.presets}>
              {PRESETS.map((p) => (
                <Pressable
                  key={p}
                  onPress={() => setAmount(String(p))}
                  style={[s.preset, { borderColor: palette.border, backgroundColor: palette.surface }]}
                  testID={`topup-preset-${p}`}
                >
                  <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>₹{p}</Text>
                </Pressable>
              ))}
            </View>
            <View style={[s.infoBox, { backgroundColor: palette.primary + "10", borderColor: palette.primary + "40" }]}>
              <CreditCard color={palette.primary} size={18} />
              <Text style={{ color: palette.textSecondary, fontSize: 12, flex: 1 }}>
                Use Stripe test card 4242 4242 4242 4242 with any future expiry & any CVC.
              </Text>
            </View>
            <Button
              label={verifying ? "Verifying payment…" : "Pay with Card"}
              onPress={create}
              loading={loading || verifying}
              testID="topup-pay-btn"
            />
          </View>
        )}

        {completed && (
          <Button label="Back to Wallet" onPress={() => router.replace("/(tabs)/wallet")} testID="topup-done-btn" />
        )}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 16, paddingBottom: 40 },
  iconHero: { alignSelf: "center", padding: 18, borderRadius: 20, marginTop: 12 },
  title: { fontSize: 24, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  subtitle: { fontSize: 13, textAlign: "center", paddingHorizontal: 16 },
  form: { gap: 14, marginTop: 12 },
  presets: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  preset: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12, borderWidth: 1 },
  infoBox: { flexDirection: "row", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, borderWidth: 1 },
});
