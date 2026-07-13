/**
 * Bank Accounts screen (Sprint 12.1) — add / list / verify / delete / primary.
 * Verification uses the Cashfree penny-drop provider abstraction. A verified
 * bank is required only for withdrawals; other flows are unaffected.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator,
  RefreshControl, Alert, Modal, Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { ArrowLeft, Plus, ShieldCheck, ShieldAlert, Trash2, Star, RefreshCw, X, Info } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { bankApi, BankAccount } from "@/src/api/bankAccounts";
import { Card } from "@/src/components/Card";

const IFSC_RE = /^[A-Z]{4}0[A-Z0-9]{6}$/;

export default function BankAccountsScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<BankAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [providerName, setProviderName] = useState<string>("demo");

  const load = useCallback(async () => {
    try {
      const [r, cfg] = await Promise.all([bankApi.list(), bankApi.bvConfig()]);
      setItems(r.items || []);
      setProviderName(cfg.provider);
    } catch {} finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const verify = async (bank: BankAccount) => {
    setBusyId(bank.bank_id);
    try {
      const r = await bankApi.verify(bank.bank_id);
      if (r.ok) {
        Alert.alert("Verified ✓",
          `Bank verified via ${r.provider}\nName at bank: ${r.matched_name || "—"}\nMatch score: ${r.name_match_score}%`);
      } else {
        Alert.alert("Verification failed",
          r.reason || `Status: ${r.status}\nProvider: ${r.provider}`);
      }
      await load();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.detail || e?.message || "Verification failed");
    } finally { setBusyId(null); }
  };

  const setPrimary = async (bank: BankAccount) => {
    setBusyId(bank.bank_id);
    try {
      await bankApi.setPrimary(bank.bank_id);
      await load();
    } catch (e: any) {
      Alert.alert("Cannot set primary", e?.response?.data?.detail || "Bank must be verified first.");
    } finally { setBusyId(null); }
  };

  const remove = (bank: BankAccount) => Alert.alert(
    "Delete bank account?", `${bank.bank_name} · ****${bank.account_number.slice(-4)}`,
    [
      { text: "Keep", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        setBusyId(bank.bank_id);
        try { await bankApi.remove(bank.bank_id); await load(); } finally { setBusyId(null); }
      } },
    ],
  );

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120, paddingHorizontal: 16, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <Pressable onPress={() => router.back()} style={[s.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="ba-back">
            <ArrowLeft color={palette.textPrimary} size={20} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 1.4 }}>PAYMENTS · WITHDRAWAL</Text>
            <Text style={{ color: palette.textPrimary, fontSize: 22, fontWeight: "800" }}>Bank Accounts</Text>
          </View>
        </View>

        <View style={[s.info, { backgroundColor: palette.primary + "12", borderColor: palette.primary + "44" }]}>
          <Info size={14} color={palette.primary} />
          <Text style={{ color: palette.textSecondary, fontSize: 11, flex: 1, lineHeight: 16 }}>
            Verified bank accounts are only required to withdraw funds. Deposits, trading, gold and mutual funds do not require this.
          </Text>
        </View>

        <Pressable onPress={() => setShowAdd(true)} style={[s.addBtn, { backgroundColor: palette.primary }]} testID="ba-add">
          <Plus color="#fff" size={18} />
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>Add Bank Account</Text>
        </Pressable>

        {loading ? (
          <ActivityIndicator color={palette.primary} size="large" style={{ marginTop: 40 }} />
        ) : items.length === 0 ? (
          <View style={{ alignItems: "center", padding: 40, gap: 8 }}>
            <ShieldCheck color={palette.textMuted} size={44} />
            <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No bank accounts yet</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>
              Add and verify a bank account to enable withdrawals.
            </Text>
          </View>
        ) : items.map((b) => (
          <Card key={b.bank_id} style={{ padding: 14, gap: 8 }}>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <View style={[s.logo, { backgroundColor: (b.verified ? palette.success : palette.warning) + "1A" }]}>
                {b.verified ? <ShieldCheck color={palette.success} size={22} /> : <ShieldAlert color={palette.warning} size={22} />}
              </View>
              <View style={{ flex: 1, gap: 3 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>{b.bank_name}</Text>
                  {b.is_primary ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: palette.primary + "22", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                      <Star color={palette.primary} size={10} fill={palette.primary} />
                      <Text style={{ color: palette.primary, fontSize: 9, fontWeight: "800", letterSpacing: 0.6 }}>PRIMARY</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={{ color: palette.textMuted, fontSize: 11 }}>{b.holder_name} · {b.ifsc}</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>A/C ****{b.account_number.slice(-4)}</Text>
                {b.verified ? (
                  <Text style={{ color: palette.success, fontSize: 10, fontWeight: "800" }}>
                    Verified via {b.last_verified_provider || b.verification_method || "penny drop"}
                    {b.name_match_score != null ? ` · ${b.name_match_score}% match` : ""}
                  </Text>
                ) : (
                  <Text style={{ color: palette.warning, fontSize: 10, fontWeight: "800" }}>Not verified</Text>
                )}
              </View>
              <Pressable onPress={() => remove(b)} hitSlop={8} style={{ padding: 4 }}>
                <Trash2 color={palette.textMuted} size={16} />
              </Pressable>
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              {!b.verified ? (
                <Pressable
                  onPress={() => verify(b)} disabled={busyId === b.bank_id}
                  style={[s.action, { backgroundColor: palette.primary }]}
                  testID={`ba-verify-${b.bank_id}`}
                >
                  {busyId === b.bank_id ? (
                    <ActivityIndicator color="#fff" size="small" />
                  ) : (
                    <>
                      <ShieldCheck color="#fff" size={14} />
                      <Text style={{ color: "#fff", fontSize: 12, fontWeight: "800" }}>Verify (Penny Drop)</Text>
                    </>
                  )}
                </Pressable>
              ) : !b.is_primary ? (
                <Pressable
                  onPress={() => setPrimary(b)} disabled={busyId === b.bank_id}
                  style={[s.action, { backgroundColor: palette.warning + "1A", borderWidth: 1, borderColor: palette.warning }]}
                  testID={`ba-primary-${b.bank_id}`}
                >
                  <Star color={palette.warning} size={14} />
                  <Text style={{ color: palette.warning, fontSize: 12, fontWeight: "800" }}>Make Primary</Text>
                </Pressable>
              ) : null}
              {b.verified ? (
                <Pressable
                  onPress={() => verify({ ...b, verified: false })} disabled={busyId === b.bank_id}
                  style={[s.action, { backgroundColor: palette.chipBg }]}
                >
                  <RefreshCw color={palette.textSecondary} size={12} />
                  <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>Re-verify</Text>
                </Pressable>
              ) : null}
            </View>
          </Card>
        ))}

        <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center", marginTop: 6 }}>
          Verification uses {providerName === "cashfree" ? "Cashfree Penny Drop" : "Demo Provider"}. ₹1 deposit is refunded automatically.
        </Text>
      </ScrollView>

      <AddBankSheet visible={showAdd} onClose={() => setShowAdd(false)} onAdded={() => { setShowAdd(false); load(); }} />
    </View>
  );
}

function AddBankSheet({ visible, onClose, onAdded }: any) {
  const { palette } = useTheme();
  const [holder, setHolder] = useState("");
  const [bankName, setBankName] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [acct, setAcct] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!holder.trim()) return Alert.alert("Holder name required");
    if (!bankName.trim()) return Alert.alert("Bank name required");
    const ifU = ifsc.trim().toUpperCase();
    if (!IFSC_RE.test(ifU)) return Alert.alert("Invalid IFSC (e.g. HDFC0001234)");
    if (!/^\d{6,20}$/.test(acct.trim())) return Alert.alert("Account number must be 6–20 digits");
    setBusy(true);
    try {
      await bankApi.add({ holder_name: holder.trim(), bank_name: bankName.trim(),
                            ifsc: ifU, account_number: acct.trim() });
      setHolder(""); setBankName(""); setIfsc(""); setAcct("");
      onAdded?.();
    } catch (e: any) {
      Alert.alert("Failed", e?.response?.data?.detail || e?.message || "Could not add");
    } finally { setBusy(false); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: palette.overlay }} onPress={onClose} />
      <View style={[m.sheet, { backgroundColor: palette.surfaceElevated }]}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>Add Bank Account</Text>
          <Pressable onPress={onClose}><X color={palette.textPrimary} size={20} /></Pressable>
        </View>
        <Text style={m.lbl(palette)}>ACCOUNT HOLDER NAME</Text>
        <TextInput value={holder} onChangeText={setHolder} placeholder="As per bank records" placeholderTextColor={palette.textMuted} style={m.input(palette)} testID="add-holder" />
        <Text style={m.lbl(palette)}>BANK NAME</Text>
        <TextInput value={bankName} onChangeText={setBankName} placeholder="e.g. HDFC Bank" placeholderTextColor={palette.textMuted} style={m.input(palette)} testID="add-bank-name" />
        <Text style={m.lbl(palette)}>IFSC</Text>
        <TextInput value={ifsc} onChangeText={(v) => setIfsc(v.toUpperCase())} autoCapitalize="characters" placeholder="HDFC0001234" placeholderTextColor={palette.textMuted} style={[m.input(palette), { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" }]} testID="add-ifsc" />
        <Text style={m.lbl(palette)}>ACCOUNT NUMBER</Text>
        <TextInput value={acct} onChangeText={setAcct} keyboardType="number-pad" placeholder="10–16 digit account number" placeholderTextColor={palette.textMuted} style={m.input(palette)} testID="add-account" />

        <View style={{ flexDirection: "row", gap: 6, alignItems: "flex-start", marginTop: 4 }}>
          <Info size={11} color={palette.textMuted} />
          <Text style={{ color: palette.textMuted, fontSize: 11, flex: 1 }}>
            Verification happens right after adding. A ₹1 penny drop is credited (and refunded) by the bank to confirm ownership.
          </Text>
        </View>
        <Pressable onPress={submit} disabled={busy} style={[m.save, { backgroundColor: palette.primary, opacity: busy ? 0.6 : 1 }]} testID="add-save">
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={{ color: "#fff", fontSize: 15, fontWeight: "800" }}>Save Account</Text>}
        </Pressable>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  iconBtn: { padding: 8, borderRadius: 14, borderWidth: 1 },
  info: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 12, borderWidth: 1 },
  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 14 },
  logo: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  action: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 10, paddingHorizontal: 10, borderRadius: 10, flex: 1 },
});

const m = {
  sheet: { padding: 16, borderTopLeftRadius: 22, borderTopRightRadius: 22, gap: 6, maxHeight: "90%" } as any,
  input: (p: any) => ({ backgroundColor: p.chipBg, borderColor: p.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: p.textPrimary, fontSize: 15, fontWeight: "700" }) as any,
  lbl: (p: any) => ({ color: p.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1, marginTop: 6 } as any),
  save: { paddingVertical: 14, borderRadius: 14, alignItems: "center", marginTop: 12 } as any,
};
