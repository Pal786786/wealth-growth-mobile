import React, { useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Landmark, User, Hash, Building2, CheckCircle2, AlertCircle } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { withdrawalApi, lookupIfsc, type IfscInfo } from "@/src/api/withdrawal";

const IFSC_RE = /^[A-Z]{4}0[A-Z0-9]{6}$/;

export default function AddBankScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [ifsc, setIfsc] = useState("");
  const [holder, setHolder] = useState("");
  const [account, setAccount] = useState("");
  const [confirmAccount, setConfirmAccount] = useState("");
  const [bankName, setBankName] = useState("");
  const [ifscInfo, setIfscInfo] = useState<IfscInfo | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const debounce = useRef<any>(null);
  const onIfscChange = (raw: string) => {
    const v = raw.toUpperCase().replace(/\s/g, "").slice(0, 11);
    setIfsc(v);
    setIfscInfo(null); setLookupError(null);
    if (debounce.current) clearTimeout(debounce.current);
    if (IFSC_RE.test(v)) {
      setLookingUp(true);
      debounce.current = setTimeout(async () => {
        try {
          const info = await lookupIfsc(v);
          if (info) {
            setIfscInfo(info);
            setBankName(info.BANK);
            setLookupError(null);
          } else {
            setIfscInfo(null);
            setLookupError("Couldn't auto-detect. Please enter bank name manually.");
          }
        } finally { setLookingUp(false); }
      }, 500);
    } else if (v.length === 11) {
      setLookupError("Invalid IFSC format (e.g. HDFC0001234)");
    }
  };

  const acctMismatch = !!confirmAccount && account !== confirmAccount;
  const isValid = useMemo(() => {
    return holder.trim().length >= 2 &&
      IFSC_RE.test(ifsc) &&
      account.length >= 8 && account.length <= 25 &&
      account === confirmAccount &&
      bankName.trim().length >= 2;
  }, [holder, ifsc, account, confirmAccount, bankName]);

  const submit = async () => {
    if (!isValid) return;
    setSaving(true);
    try {
      const r = await withdrawalApi.addBank({
        holder_name: holder.trim(),
        bank_name: bankName.trim(),
        ifsc: ifsc.toUpperCase(),
        account_number: account.trim(),
      });
      if (r?.duplicate) show("info", "This bank account is already saved");
      else show("success", "Bank account added");
      router.replace("/withdrawals/banks");
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to add bank");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Add Bank Account</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
        <View style={[s.tip, { backgroundColor: palette.infoBg, borderColor: palette.primary + "55" }]}>
          <Text style={[s.tipTxt, { color: palette.textPrimary }]}>🔐 Your account number is never shown back to you — keep it safe.</Text>
        </View>

        <Input
          label="IFSC Code"
          placeholder="e.g. HDFC0001234"
          value={ifsc}
          onChangeText={onIfscChange}
          autoCapitalize="characters"
          maxLength={11}
          leftIcon={<Hash color={palette.textMuted} size={18} />}
          rightSlot={lookingUp ? <ActivityIndicator color={palette.primary} /> : ifscInfo ? <CheckCircle2 color={palette.success} size={20} /> : lookupError ? <AlertCircle color={palette.danger} size={20} /> : null}
          error={lookupError && !ifscInfo ? lookupError : undefined}
        />

        {ifscInfo && (
          <View style={[s.bankCard, { backgroundColor: palette.surfaceAlt, borderColor: palette.primary + "55" }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <Building2 color={palette.primary} size={18} />
              <Text style={[s.bankName, { color: palette.textPrimary }]}>{ifscInfo.BANK}</Text>
            </View>
            <Text style={[s.bankMeta, { color: palette.textSecondary }]}>{ifscInfo.BRANCH}</Text>
            <Text style={[s.bankMeta, { color: palette.textMuted }]}>{ifscInfo.CITY}, {ifscInfo.STATE}</Text>
            {ifscInfo.ADDRESS && <Text style={[s.bankAddr, { color: palette.textMuted }]} numberOfLines={2}>{ifscInfo.ADDRESS}</Text>}
          </View>
        )}

        <Input
          label="Bank Name"
          placeholder="e.g. HDFC BANK"
          value={bankName}
          onChangeText={setBankName}
          leftIcon={<Landmark color={palette.textMuted} size={18} />}
        />

        <Input
          label="Account Holder Name (as per bank)"
          placeholder="Full name"
          value={holder}
          onChangeText={setHolder}
          leftIcon={<User color={palette.textMuted} size={18} />}
          autoCapitalize="words"
        />

        <Input
          label="Account Number"
          placeholder="Enter account number"
          value={account}
          onChangeText={(v) => setAccount(v.replace(/\D/g, ""))}
          keyboardType="number-pad"
          maxLength={25}
          secureTextEntry
          leftIcon={<Hash color={palette.textMuted} size={18} />}
        />

        <Input
          label="Confirm Account Number"
          placeholder="Re-enter account number"
          value={confirmAccount}
          onChangeText={(v) => setConfirmAccount(v.replace(/\D/g, ""))}
          keyboardType="number-pad"
          maxLength={25}
          leftIcon={<Hash color={palette.textMuted} size={18} />}
          error={acctMismatch ? "Account numbers don't match" : undefined}
        />

        <Button label={saving ? "Saving..." : "Save Bank Account"} onPress={submit} disabled={!isValid || saving} loading={saving} testID="btn-save-bank" />

        <Text style={[s.disclaimer, { color: palette.textMuted }]}>
          By adding this bank you confirm the account belongs to you. Beneficiary verification is performed manually by our operations team.
        </Text>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  tip: { padding: 12, borderRadius: 12, borderWidth: 1 },
  tipTxt: { fontSize: 12, fontWeight: "600" },
  bankCard: { padding: 14, borderRadius: 16, borderWidth: 1 },
  bankName: { fontSize: 15, fontWeight: "800" },
  bankMeta: { fontSize: 12, fontWeight: "600" },
  bankAddr: { fontSize: 10, marginTop: 6 },
  disclaimer: { fontSize: 11, textAlign: "center", marginTop: 6, lineHeight: 16 },
});
