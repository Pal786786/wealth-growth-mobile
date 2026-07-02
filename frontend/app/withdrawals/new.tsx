import React, { useCallback, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Landmark, Plus, ChevronRight, CheckCircle2, AlertTriangle } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { withdrawalApi, type BankAccount, type WithdrawalSettings } from "@/src/api/withdrawal";
import { formatINR } from "@/src/utils/format";

export default function NewWithdrawalScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [banks, setBanks] = useState<BankAccount[]>([]);
  const [settings, setSettings] = useState<WithdrawalSettings | null>(null);
  const [balance, setBalance] = useState<number>(0);
  const [selectedBank, setSelectedBank] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const [b, s, w] = await Promise.all([
        withdrawalApi.listBanks(),
        withdrawalApi.settings(),
        api.get("/wallet").then((r) => r.data),
      ]);
      setBanks(b); setSettings(s); setBalance(w?.balance || 0);
      if (b.length && !selectedBank) setSelectedBank(b[0].bank_id);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to load");
    } finally { setLoading(false); }
     
  }, [show]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const amt = parseFloat(amount) || 0;
  const validation = useMemo(() => {
    if (!settings) return { ok: false, err: null as string | null };
    if (amt <= 0) return { ok: false, err: null };
    if (amt < settings.min_amount) return { ok: false, err: `Minimum ${formatINR(settings.min_amount)}` };
    if (amt > settings.max_amount) return { ok: false, err: `Max per txn ${formatINR(settings.max_amount)}` };
    if (amt > balance) return { ok: false, err: `Only ${formatINR(balance)} available` };
    if (!selectedBank) return { ok: false, err: "Select a bank account" };
    return { ok: true, err: null };
  }, [amt, settings, balance, selectedBank]);

  const charge = useMemo(() => {
    if (!settings || !amt) return 0;
    if (settings.promo_waiver) return 0;
    if (settings.free_threshold && amt >= settings.free_threshold) return 0;
    if (settings.charge_type === "percentage") return +(amt * (settings.charge_percent / 100)).toFixed(2);
    return settings.charge_flat;
  }, [amt, settings]);

  const netAmt = Math.max(0, amt - charge);

  const submit = async () => {
    if (!validation.ok || !selectedBank) return;
    setCreating(true);
    try {
      const r = await withdrawalApi.create(amt, selectedBank, reason.trim() || undefined);
      router.replace({
        pathname: "/withdrawals/verify",
        params: {
          wid: r.withdrawal_id,
          ref: r.reference_no,
          amount: String(amt),
          otpDemo: r.otp_demo || "",
          expires: String(r.otp_expires_in),
        },
      });
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to create withdrawal");
    } finally {
      setCreating(false);
    }
  };

  if (loading) return (
    <Screen>
      <ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} />
    </Screen>
  );

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>New Withdrawal</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 80 }} keyboardShouldPersistTaps="handled">
        {/* Balance card */}
        <Card>
          <Text style={[s.small, { color: palette.textSecondary }]}>Withdrawable balance</Text>
          <Text style={[s.balance, { color: palette.textPrimary }]}>{formatINR(balance)}</Text>
          {settings && <Text style={[s.small, { color: palette.textMuted }]}>Per-txn: {formatINR(settings.min_amount)} – {formatINR(settings.max_amount)}</Text>}
        </Card>

        {/* Amount input */}
        <Card>
          <Text style={[s.small, { color: palette.textSecondary, marginBottom: 6 }]}>ENTER AMOUNT (₹)</Text>
          <TextInput
            value={amount}
            onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
            keyboardType="decimal-pad"
            placeholder="0"
            placeholderTextColor={palette.textMuted}
            style={[s.amountInput, { color: palette.textPrimary }]}
            testID="input-amount"
          />
          <View style={s.presetsRow}>
            {[500, 1000, 2000, 5000].map((p) => (
              <Pressable key={p} onPress={() => setAmount(String(p))} style={[s.preset, { borderColor: palette.border, backgroundColor: palette.chipBg }]}>
                <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "700" }}>₹{p}</Text>
              </Pressable>
            ))}
          </View>
          {validation.err && amount.length > 0 && (
            <View style={s.errRow}>
              <AlertTriangle color={palette.danger} size={14} />
              <Text style={{ color: palette.danger, fontSize: 12, fontWeight: "700" }}>{validation.err}</Text>
            </View>
          )}
        </Card>

        {/* Bank picker */}
        <View style={s.sectionHead}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>To Bank Account</Text>
          <Pressable onPress={() => router.push("/withdrawals/add-bank")}>
            <Text style={[s.link, { color: palette.primary }]}>+ Add</Text>
          </Pressable>
        </View>

        {banks.length === 0 ? (
          <Pressable onPress={() => router.push("/withdrawals/add-bank")}>
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 6 }}>
                <View style={[s.bIcon, { backgroundColor: palette.primary + "22" }]}>
                  <Plus color={palette.primary} size={18} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>Add your first bank account</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 12 }}>Required for withdrawals</Text>
                </View>
                <ChevronRight color={palette.textMuted} size={18} />
              </View>
            </Card>
          </Pressable>
        ) : banks.map((b) => (
          <Pressable key={b.bank_id} onPress={() => setSelectedBank(b.bank_id)}>
            <Card style={{ ...(selectedBank === b.bank_id ? { borderColor: palette.primary, borderWidth: 2 } : {}) }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <View style={[s.bIcon, { backgroundColor: palette.primary + "22" }]}>
                  <Landmark color={palette.primary} size={18} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800" }} numberOfLines={1}>{b.bank_name}</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 11 }}>{b.account_masked} · {b.ifsc}</Text>
                </View>
                {selectedBank === b.bank_id && <CheckCircle2 color={palette.primary} size={20} />}
              </View>
            </Card>
          </Pressable>
        ))}

        {/* Quote breakdown */}
        {settings && amt > 0 && validation.ok && (
          <Card>
            <Text style={[s.small, { color: palette.textSecondary, marginBottom: 8 }]}>SUMMARY</Text>
            <QuoteRow label="Withdrawal amount" value={formatINR(amt)} palette={palette} />
            <QuoteRow label={`Charge${settings.promo_waiver ? " (waived)" : ""}`} value={charge > 0 ? `– ${formatINR(charge)}` : "FREE"} valueColor={charge > 0 ? palette.danger : palette.success} palette={palette} />
            <View style={[s.divider, { backgroundColor: palette.border }]} />
            <QuoteRow label="You'll receive" value={formatINR(netAmt)} bold palette={palette} />
            <Text style={[s.small, { color: palette.textMuted, marginTop: 8 }]}>Typically credited in ~{settings.processing_time_hours}h after admin approval.</Text>
          </Card>
        )}

        {/* Reason (optional) */}
        <Card>
          <Text style={[s.small, { color: palette.textSecondary, marginBottom: 6 }]}>REASON (OPTIONAL)</Text>
          <TextInput
            value={reason}
            onChangeText={setReason}
            placeholder="e.g. Personal expenses"
            placeholderTextColor={palette.textMuted}
            maxLength={100}
            style={[s.reasonInput, { color: palette.textPrimary, backgroundColor: palette.chipBg, borderColor: palette.border }]}
          />
        </Card>

        <Button
          label={creating ? "Sending OTP..." : `Continue · ${formatINR(amt || 0)}`}
          onPress={submit}
          disabled={!validation.ok || creating || banks.length === 0}
          loading={creating}
          testID="btn-continue"
        />

        <Text style={[s.small, { color: palette.textMuted, textAlign: "center" }]}>
          You&apos;ll be asked to verify a 6-digit OTP before we hold the funds.
        </Text>
      </ScrollView>
    </Screen>
  );
}

function QuoteRow({ label, value, bold, valueColor, palette }: { label: string; value: string; bold?: boolean; valueColor?: string; palette: any }) {
  return (
    <View style={s.qRow}>
      <Text style={{ color: palette.textSecondary, fontSize: 13, fontWeight: bold ? "800" : "600" }}>{label}</Text>
      <Text style={{ color: valueColor || palette.textPrimary, fontSize: bold ? 16 : 13, fontWeight: bold ? "900" : "700" }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  small: { fontSize: 11, fontWeight: "700", letterSpacing: 0.5 },
  balance: { fontSize: 28, fontWeight: "900", letterSpacing: -1, marginTop: 4 },
  amountInput: { fontSize: 36, fontWeight: "900", letterSpacing: -1, paddingVertical: 4 },
  presetsRow: { flexDirection: "row", gap: 8, marginTop: 6 },
  preset: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  errRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 2 },
  sectionTitle: { fontSize: 15, fontWeight: "800" },
  link: { fontSize: 13, fontWeight: "800" },
  bIcon: { padding: 10, borderRadius: 12 },
  qRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  divider: { height: 1, marginVertical: 6 },
  reasonInput: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 14 },
});
