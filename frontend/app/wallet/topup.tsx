/**
 * Wallet Top-up — Sprint 8 (Razorpay via WebView / Demo mode fallback)
 *
 * Flow:
 *  1. Client fetches /api/payments/config to know if demo mode is active.
 *  2. Client POSTs /api/payments/orders with Idempotency-Key.
 *  3. If demo_mode → local `demo/capture` fires (simulates webhook).
 *     Else       → opens Razorpay web checkout in an in-app browser.
 *  4. Client polls the order until status === "captured".
 *     Wallet credit is triggered by the webhook, never the client.
 */
import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Plus, CreditCard, CheckCircle2, Smartphone, Building2 } from "lucide-react-native";
import * as WebBrowser from "expo-web-browser";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

const PRESETS = [500, 1000, 2000, 5000, 10000];

type PayConfig = {
  demo_mode: boolean;
  configured: boolean;
  key_id_public: string;
  min_topup_paise: number;
  max_topup_paise: number;
  mode: string;
  payment_methods: string[];
};

type MethodHint = "upi" | "card" | "netbanking";

const METHOD_OPTIONS: Array<{ id: MethodHint; label: string; icon: any }> = [
  { id: "upi", label: "UPI", icon: Smartphone },
  { id: "card", label: "Card", icon: CreditCard },
  { id: "netbanking", label: "Net Banking", icon: Building2 },
];

function genIdempotencyKey() {
  return `mfb_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export default function TopUp() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [config, setConfig] = useState<PayConfig | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<MethodHint>("upi");
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [orderId, setOrderId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [creditedAmount, setCreditedAmount] = useState<number>(0);
  const pollRef = useRef<any>(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/payments/config");
        setConfig(data);
      } catch (e: any) {
        show("error", "Could not load payment config");
      }
    })();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [show]);

  const pollOrder = async (id: string, attempt: number) => {
    setPolling(true);
    try {
      const { data } = await api.get(`/payments/orders/${id}`);
      if (data.status === "captured") {
        setCreditedAmount((data.amount_paise ?? 0) / 100);
        setCompleted(true);
        setPolling(false);
        show("success", `₹${(data.amount_paise / 100).toLocaleString()} credited to wallet`);
        return;
      }
      if (data.status === "failed" || data.status === "expired") {
        setPolling(false);
        show("error", `Payment ${data.status}. Please try again.`);
        return;
      }
      if (attempt < 15) {
        pollRef.current = setTimeout(() => pollOrder(id, attempt + 1), 2000);
      } else {
        setPolling(false);
        show("info", "Still processing — check your wallet in a moment.");
      }
    } catch {
      setPolling(false);
      show("error", "Could not verify payment status");
    }
  };

  const pay = async () => {
    const num = parseFloat(amount);
    if (!num || num < 1) {
      show("error", "Enter a valid amount");
      return;
    }
    const paise = Math.round(num * 100);
    if (config && (paise < config.min_topup_paise || paise > config.max_topup_paise)) {
      show("error", `Amount must be ₹${config.min_topup_paise / 100} – ₹${config.max_topup_paise / 100}`);
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post(
        "/payments/orders",
        { amount_paise: paise, currency: "INR", method_hint: method },
        { headers: { "Idempotency-Key": genIdempotencyKey() } }
      );
      const oid: string = data.order.order_id;
      setOrderId(oid);

      // DEMO MODE: locally simulate the payment.captured webhook
      if (config?.demo_mode || data.order.is_demo) {
        show("info", "Demo mode — simulating payment…");
        try {
          await api.post(`/payments/demo/capture?order_id=${oid}&method=${method}`);
          pollOrder(oid, 0);
        } catch (e: any) {
          show("error", e?.response?.data?.detail || "Demo capture failed");
        }
        return;
      }

      // LIVE MODE: launch Razorpay web checkout with the order_id
      const checkoutUrl = buildRazorpayCheckoutUrl(
        data.checkout.key_id, data.checkout.provider_order_id,
        paise, method
      );
      const res = await WebBrowser.openAuthSessionAsync(checkoutUrl, undefined);
      // Regardless of dismiss/cancel/success — poll for webhook confirmation
      if (res.type === "success" || res.type === "dismiss" || res.type === "cancel") {
        pollOrder(oid, 0);
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
            ? `₹${creditedAmount.toLocaleString()} added successfully.`
            : "Pay securely via UPI, cards or net banking (Razorpay)"}
        </Text>
        {config?.demo_mode && !completed && (
          <View style={[s.demoChip, { borderColor: "#F59E0B", backgroundColor: "#F59E0B15" }]}>
            <Text style={{ color: "#F59E0B", fontSize: 11, fontWeight: "900", letterSpacing: 0.4 }}>
              🧪 DEMO MODE — payments are simulated locally
            </Text>
          </View>
        )}

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
                <Pressable key={p} onPress={() => setAmount(String(p))}
                  style={[s.preset, { borderColor: palette.border, backgroundColor: palette.surface }]}
                  testID={`topup-preset-${p}`}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>₹{p}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", letterSpacing: 0.5, marginTop: 6 }}>
              PAYMENT METHOD
            </Text>
            <View style={s.methodRow}>
              {METHOD_OPTIONS.map(({ id, label, icon: Icon }) => (
                <Pressable key={id} onPress={() => setMethod(id)}
                  style={[s.methodBtn, {
                    borderColor: method === id ? palette.primary : palette.border,
                    backgroundColor: method === id ? palette.primary + "12" : palette.surface,
                  }]}>
                  <Icon size={16} color={method === id ? palette.primary : palette.textMuted} />
                  <Text style={{ color: method === id ? palette.primary : palette.textPrimary, fontWeight: "700", fontSize: 12 }}>{label}</Text>
                </Pressable>
              ))}
            </View>

            <View style={[s.infoBox, { backgroundColor: palette.primary + "10", borderColor: palette.primary + "40" }]}>
              <CreditCard color={palette.primary} size={18} />
              <Text style={{ color: palette.textSecondary, fontSize: 12, flex: 1, lineHeight: 17 }}>
                {config?.demo_mode
                  ? "Demo mode: payments succeed instantly for testing."
                  : "You'll be redirected to Razorpay secure checkout. Wallet is credited only after webhook confirmation."}
              </Text>
            </View>

            <Button
              label={polling ? "Confirming payment…" : `Pay ₹${amount || "0"}`}
              onPress={pay}
              loading={loading || polling}
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

// Razorpay hosted checkout URL — usable inside a WebView / WebBrowser
function buildRazorpayCheckoutUrl(keyId: string, orderId: string,
                                    amountPaise: number, method: MethodHint): string {
  const opts = {
    key_id: keyId, order_id: orderId, amount: amountPaise, currency: "INR",
    prefer: method, name: "My Funding Bank", description: "Wallet top-up",
  };
  const q = new URLSearchParams(opts as any).toString();
  return `https://api.razorpay.com/v1/checkout/embedded?${q}`;
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 16, paddingBottom: 40 },
  iconHero: { alignSelf: "center", padding: 18, borderRadius: 20, marginTop: 12 },
  title: { fontSize: 24, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  subtitle: { fontSize: 13, textAlign: "center", paddingHorizontal: 16 },
  demoChip: { alignSelf: "center", paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, borderWidth: 1 },
  form: { gap: 14, marginTop: 12 },
  presets: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  preset: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12, borderWidth: 1 },
  methodRow: { flexDirection: "row", gap: 8 },
  methodBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 10, borderWidth: 1 },
  infoBox: { flexDirection: "row", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, borderWidth: 1 },
});
