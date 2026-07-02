import React, { useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ScrollView, ActivityIndicator, Platform } from "react-native";
import { Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ArrowLeft, Mail, Smartphone, KeyRound, ShieldCheck } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";
import { errText, safeStr } from "@/src/utils/errors";

export default function ForgotPassword() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState<"identifier" | "reset">("identifier");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const requestCode = async () => {
    if (!identifier.trim()) return setErr("Enter email or mobile");
    setLoading(true); setErr(null);
    try {
      await api.post("/auth/forgot-password", { identifier: identifier.trim() });
      setMsg("If the account exists, a reset code has been sent. Check your email or SMS.");
      setStep("reset");
    } catch (e: any) {
      setErr(errText(e, "Could not send reset code"));
    } finally { setLoading(false); }
  };

  const resetPw = async () => {
    if (newPassword.length < 8) return setErr("Password must be at least 8 characters");
    if (newPassword !== confirm) return setErr("Passwords do not match");
    setLoading(true); setErr(null);
    try {
      await api.post("/auth/reset-password", { identifier: identifier.trim(), code: code.trim(), new_password: newPassword });
      setMsg("Password reset successfully! Please log in with your new password.");
      setTimeout(() => router.replace("/(auth)/welcome"), 1500);
    } catch (e: any) {
      setErr(errText(e, "Reset failed"));
    } finally { setLoading(false); }
  };

  const isMobile = /^[+]?[0-9]{8,}$/.test(identifier.replace(/\s+/g, ""));

  return (
    <View style={[s.root, { backgroundColor: palette.background, paddingTop: insets.top }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <Pressable onPress={() => router.back()} style={s.iconBtn} testID="fp-back">
          <ArrowLeft color={palette.textPrimary} size={20} />
        </Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Forgot Password</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16, paddingBottom: insets.bottom + 30 }}>
        <Card style={{ alignItems: "center", gap: 8, paddingVertical: 22 }}>
          <View style={[s.iconCircle, { backgroundColor: palette.primary + "20" }]}>
            <KeyRound color={palette.primary} size={28} />
          </View>
          <Text style={[s.h2, { color: palette.textPrimary }]}>
            {step === "identifier" ? "Reset your password" : "Enter reset code"}
          </Text>
          <Text style={[s.body, { color: palette.textSecondary, textAlign: "center" }]}>
            {step === "identifier"
              ? "Enter your email or mobile number and we'll send you a 6-digit reset code."
              : `We sent a code to ${identifier}. It expires in 15 minutes.`}
          </Text>
        </Card>

        {step === "identifier" ? (
          <Card style={{ gap: 12 }}>
            <View>
              <Text style={[s.label, { color: palette.textSecondary }]}>Email or Mobile Number</Text>
              <View style={[s.inputRow, { borderColor: palette.border, backgroundColor: palette.surfaceAlt }]}>
                {isMobile ? <Smartphone color={palette.primary} size={18} /> : <Mail color={palette.primary} size={18} />}
                <TextInput
                  value={identifier} onChangeText={setIdentifier}
                  placeholder="yourname@example.com or 9876543210"
                  placeholderTextColor={palette.textMuted}
                  autoCapitalize="none"
                  keyboardType={Platform.OS === "web" ? "default" : "email-address"}
                  style={[s.input, { color: palette.textPrimary }]}
                  testID="fp-identifier"
                />
              </View>
            </View>
            <Pressable onPress={requestCode} disabled={loading} style={[s.btn, { backgroundColor: palette.primary }]} testID="fp-send">
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>Send Reset Code</Text>}
            </Pressable>
          </Card>
        ) : (
          <Card style={{ gap: 12 }}>
            <View>
              <Text style={[s.label, { color: palette.textSecondary }]}>6-digit Reset Code</Text>
              <TextInput value={code} onChangeText={setCode}
                placeholder="123456" placeholderTextColor={palette.textMuted}
                keyboardType="number-pad" maxLength={6}
                style={[s.input, s.singleInput, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surfaceAlt }]}
                testID="fp-code"
              />
            </View>
            <View>
              <Text style={[s.label, { color: palette.textSecondary }]}>New Password (min 8 chars)</Text>
              <TextInput value={newPassword} onChangeText={setNewPassword}
                placeholder="••••••••" placeholderTextColor={palette.textMuted}
                secureTextEntry
                style={[s.input, s.singleInput, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surfaceAlt }]}
                testID="fp-pw"
              />
            </View>
            <View>
              <Text style={[s.label, { color: palette.textSecondary }]}>Confirm Password</Text>
              <TextInput value={confirm} onChangeText={setConfirm}
                placeholder="••••••••" placeholderTextColor={palette.textMuted}
                secureTextEntry
                style={[s.input, s.singleInput, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surfaceAlt }]}
                testID="fp-confirm"
              />
            </View>
            <Pressable onPress={resetPw} disabled={loading} style={[s.btn, { backgroundColor: palette.primary }]} testID="fp-reset">
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>Reset Password</Text>}
            </Pressable>
            <Pressable onPress={requestCode} disabled={loading}>
              <Text style={{ color: palette.primary, fontSize: 13, fontWeight: "700", textAlign: "center" }}>Resend code</Text>
            </Pressable>
          </Card>
        )}

        {msg ? (
          <View style={[s.alert, { backgroundColor: palette.successBg, borderColor: palette.success }]}>
            <ShieldCheck color={palette.success} size={16} />
            <Text style={{ flex: 1, color: palette.success, fontSize: 12 }}>{msg}</Text>
          </View>
        ) : null}
        {err ? (
          <View style={[s.alert, { backgroundColor: palette.dangerBg, borderColor: palette.danger }]}>
            <Text style={{ flex: 1, color: palette.danger, fontSize: 12 }}>{safeStr(err)}</Text>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 14, gap: 10 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 18, fontWeight: "800" },
  iconCircle: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  h2: { fontSize: 18, fontWeight: "800" },
  body: { fontSize: 13, lineHeight: 19 },
  label: { fontSize: 12, fontWeight: "700", marginBottom: 6 },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1 },
  input: { flex: 1, paddingVertical: 12, fontSize: 14 },
  singleInput: { borderRadius: 12, borderWidth: 1, paddingHorizontal: 14 },
  btn: { paddingVertical: 14, borderRadius: 12, alignItems: "center", marginTop: 6 },
  btnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  alert: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 12, borderWidth: 1 },
});
