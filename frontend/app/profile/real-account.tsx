import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  ActivityIndicator, Platform, Alert, KeyboardAvoidingView,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ArrowLeft, TrendingUp, CheckCircle2, Clock, XCircle, PauseCircle } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";

type AccountInfo = {
  application_id: string;
  email: string;
  mt5_account_number: string | null;
  mt5_server: string;
  account_type: string;
  currency: string;
  leverage: number;
  status: string;
  error_code?: string | null;
  error_message?: string | null;
};

const notify = (title: string, msg: string) => {
  if (Platform.OS === "web") window.alert(`${title}\n\n${msg}`);
  else Alert.alert(title, msg);
};

export default function RealAccountScreen() {
  const { palette } = useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string>("NOT_CREATED");
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState(user?.email || "");
  const [emailErr, setEmailErr] = useState("");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/real-account");
      setStatus(data.status);
      setAccount(data.account);
    } catch {} finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const validEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());

  const submit = async (retry = false) => {
    const em = email.trim().toLowerCase();
    if (!retry) {
      if (!em) { setEmailErr("Email is required"); return; }
      if (!validEmail(em)) { setEmailErr("Enter a valid email address"); return; }
    }
    setEmailErr("");
    setSubmitting(true);
    try {
      const { data } = retry
        ? await api.post("/real-account/retry")
        : await api.post("/real-account/apply", { email: em });
      setStatus(data.status);
      if (data.account) setAccount(data.account);
      setShowForm(false);
      if (data.success) {
        notify("Real Trading Account Created", `MT5 Account: ${data.account?.mt5_account_number}`);
      } else if (data.error_code === "DUPLICATE_ACCOUNT") {
        notify("Account Exists", data.message || "You already have a real account.");
      } else {
        notify("Account Creation Failed", data.message || "Please try again later.");
      }
    } catch (e: any) {
      notify("Error", e?.response?.data?.detail || e?.message || "Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const S = styles(palette);

  const statusMeta: Record<string, { icon: any; color: string; label: string }> = {
    ACTIVE: { icon: CheckCircle2, color: palette.success, label: "ACTIVE" },
    PENDING: { icon: Clock, color: palette.warning, label: "PENDING" },
    FAILED: { icon: XCircle, color: palette.danger, label: "FAILED" },
    SUSPENDED: { icon: PauseCircle, color: palette.warning, label: "SUSPENDED" },
  };

  const renderStatusBadge = () => {
    const m = statusMeta[status];
    if (!m) return null;
    const Icon = m.icon;
    return (
      <View style={[S.badge, { backgroundColor: m.color + "22" }]}>
        <Icon size={14} color={m.color} />
        <Text style={[S.badgeText, { color: m.color }]}>{m.label}</Text>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: palette.background }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={[S.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="ra-back">
          <ArrowLeft size={22} color={palette.text} />
        </Pressable>
        <Text style={S.title}>Real Trading Account</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 24 }}>
        {loading ? (
          <ActivityIndicator color={palette.primary} style={{ marginTop: 48 }} />
        ) : status === "NOT_CREATED" && !showForm ? (
          <Card>
            <View style={S.heroIcon}><TrendingUp size={28} color={palette.primary} /></View>
            <Text style={S.heroTitle}>Open Real Trading Account</Text>
            <Text style={S.heroDesc}>
              Create your live MT5 trading account and start trading with real funds.
            </Text>
            <Pressable style={S.primaryBtn} onPress={() => setShowForm(true)} testID="ra-open">
              <Text style={S.primaryBtnText}>Open Real Account</Text>
            </Pressable>
          </Card>
        ) : status === "NOT_CREATED" && showForm ? (
          <Card>
            <Text style={S.formTitle}>Confirm your email</Text>
            <Text style={S.heroDesc}>
              Your MT5 account credentials will be linked to this email.
            </Text>
            <TextInput
              style={[S.input, emailErr ? { borderColor: palette.danger } : null]}
              value={email}
              onChangeText={(v) => { setEmail(v); setEmailErr(""); }}
              placeholder="you@example.com"
              placeholderTextColor={palette.textMuted}
              autoCapitalize="none"
              keyboardType="email-address"
              testID="ra-email"
            />
            {emailErr ? <Text style={S.err}>{emailErr}</Text> : null}
            <Pressable style={[S.primaryBtn, submitting && { opacity: 0.6 }]}
              disabled={submitting} onPress={() => submit(false)} testID="ra-submit">
              {submitting
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={S.primaryBtnText}>Create Real Account</Text>}
            </Pressable>
            <Pressable onPress={() => setShowForm(false)} style={{ marginTop: 12, alignSelf: "center" }}>
              <Text style={{ color: palette.textMuted, fontSize: 13 }}>Cancel</Text>
            </Pressable>
          </Card>
        ) : (
          <Card>
            <View style={S.rowBetween}>
              <Text style={S.formTitle}>REAL ACCOUNT</Text>
              {renderStatusBadge()}
            </View>

            {status === "PENDING" && (
              <Text style={[S.heroDesc, { marginTop: 8 }]}>
                Your real trading account is being created.
              </Text>
            )}
            {status === "FAILED" && (
              <>
                <Text style={[S.heroDesc, { marginTop: 8, color: palette.danger }]}>
                  Account creation failed. Please try again.
                </Text>
                {account?.error_message ? (
                  <Text style={S.errDetail}>{account.error_message}</Text>
                ) : null}
                <Pressable style={[S.primaryBtn, submitting && { opacity: 0.6 }]}
                  disabled={submitting} onPress={() => submit(true)} testID="ra-retry">
                  {submitting
                    ? <ActivityIndicator color="#fff" size="small" />
                    : <Text style={S.primaryBtnText}>Retry</Text>}
                </Pressable>
              </>
            )}

            <View style={{ marginTop: 16 }}>
              {account?.mt5_account_number ? (
                <Row label="Account" value={account.mt5_account_number} palette={palette} bold />
              ) : null}
              <Row label="Server" value={account?.mt5_server || "—"} palette={palette} />
              <Row label="Account Type" value={(account?.account_type || "—").toUpperCase()} palette={palette} />
              <Row label="Currency" value={account?.currency || "—"} palette={palette} />
              <Row label="Leverage" value={account?.leverage ? `1:${account.leverage}` : "—"} palette={palette} />
              <Row label="Email" value={account?.email || "—"} palette={palette} />
            </View>
          </Card>
        )}

        <Text style={S.note}>
          Demo trading is not affected by your real account. Deposits, withdrawals and
          KYC verification will be enabled in a later update.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Row({ label, value, palette, bold }: { label: string; value: string; palette: any; bold?: boolean }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 8 }}>
      <Text style={{ color: palette.textMuted, fontSize: 13 }}>{label}</Text>
      <Text style={{ color: palette.text, fontSize: bold ? 16 : 13, fontWeight: bold ? "700" : "500" }}>
        {value}
      </Text>
    </View>
  );
}

const styles = (p: any) => StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 16, paddingBottom: 12, backgroundColor: p.background,
  },
  title: { color: p.text, fontSize: 17, fontWeight: "700" },
  heroIcon: {
    width: 56, height: 56, borderRadius: 16, alignItems: "center", justifyContent: "center",
    backgroundColor: p.primary + "18", marginBottom: 12,
  },
  heroTitle: { color: p.text, fontSize: 18, fontWeight: "700", marginBottom: 6 },
  heroDesc: { color: p.textMuted, fontSize: 13, lineHeight: 19 },
  formTitle: { color: p.text, fontSize: 15, fontWeight: "700" },
  input: {
    borderWidth: 1, borderColor: p.border, borderRadius: 12, paddingHorizontal: 14,
    paddingVertical: 12, color: p.text, fontSize: 15, marginTop: 14, backgroundColor: p.surface,
  },
  err: { color: p.danger, fontSize: 12, marginTop: 6 },
  errDetail: { color: p.textMuted, fontSize: 12, marginTop: 6, fontStyle: "italic" },
  primaryBtn: {
    backgroundColor: p.primary, borderRadius: 12, paddingVertical: 14,
    alignItems: "center", marginTop: 16, minHeight: 48, justifyContent: "center",
  },
  primaryBtnText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  badge: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20,
  },
  badgeText: { fontSize: 12, fontWeight: "700" },
  note: { color: p.textMuted, fontSize: 12, textAlign: "center", marginTop: 20, lineHeight: 17 },
});
