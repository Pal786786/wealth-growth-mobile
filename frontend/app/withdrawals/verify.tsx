import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, Keyboard } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { ChevronLeft, ShieldCheck, RefreshCw, Clock, KeyRound } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { withdrawalApi } from "@/src/api/withdrawal";
import { formatINR } from "@/src/utils/format";

export default function VerifyOtpScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const params = useLocalSearchParams<{ wid: string; ref: string; amount: string; otpDemo?: string; expires?: string }>();
  const wid = String(params.wid || "");
  const ref = String(params.ref || "");
  const amount = Number(params.amount || 0);
  const [otp, setOtp] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [demoOtp, setDemoOtp] = useState<string>(String(params.otpDemo || ""));
  const [expiresIn, setExpiresIn] = useState<number>(Number(params.expires) || 300);
  const [cooldown, setCooldown] = useState(30);
  const inputRef = useRef<TextInput>(null);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  useEffect(() => {
    if (expiresIn <= 0) return;
    const t = setInterval(() => setExpiresIn((x) => Math.max(0, x - 1)), 1000);
    return () => clearInterval(t);
  }, [expiresIn > 0]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((x) => Math.max(0, x - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown > 0]);

  const mmss = useMemo(() => {
    const m = Math.floor(expiresIn / 60);
    const s = expiresIn % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }, [expiresIn]);

  const submit = async (finalOtp?: string) => {
    const code = (finalOtp ?? otp).trim();
    if (code.length !== 6) return;
    setVerifying(true);
    Keyboard.dismiss();
    try {
      const r = await withdrawalApi.verifyOtp(wid, code);
      if (r.ok) {
        // Sprint 12.2 — auto-approve path returns terminal / near-terminal state
        if (r.auto_approved) {
          if (r.status === "completed" && r.utr) {
            show("success", `Sent! UTR ${r.utr}`);
          } else if (r.status === "processing") {
            show("success", "Auto-approved. Processing at bank…");
          } else if (r.status === "failed") {
            show("error", "Payout failed. Refunded to wallet.");
          } else {
            show("success", "OTP verified. Auto-approved.");
          }
        } else {
          show("success", "OTP verified. Withdrawal under review.");
        }
        router.replace({ pathname: "/withdrawals/[id]", params: { id: wid } });
      }
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "OTP verification failed");
      setOtp("");
    } finally { setVerifying(false); }
  };

  const resend = async () => {
    if (cooldown > 0) return;
    setResending(true);
    try {
      const r = await withdrawalApi.resendOtp(wid);
      show("success", "New OTP sent");
      setExpiresIn(r.otp_expires_in || 300);
      setDemoOtp(r.otp_demo || "");
      setCooldown(30);
      setOtp("");
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Couldn't resend OTP");
    } finally { setResending(false); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Verify OTP</Text>
      </View>

      <View style={{ padding: 20, alignItems: "center", gap: 6 }}>
        <View style={[s.iconRing, { borderColor: palette.primary + "55", backgroundColor: palette.primary + "15" }]}>
          <ShieldCheck color={palette.primary} size={32} />
        </View>
        <Text style={[s.big, { color: palette.textPrimary }]}>Enter 6-digit OTP</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Confirm withdrawal of {formatINR(amount)} · {ref}</Text>
      </View>

      <View style={{ paddingHorizontal: 20, gap: 14 }}>
        <View style={[s.otpWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          {Array.from({ length: 6 }).map((_, i) => (
            <View key={i} style={[s.otpBox, { borderColor: otp[i] ? palette.primary : palette.border, backgroundColor: palette.chipBg }]}>
              <Text style={[s.otpTxt, { color: palette.textPrimary }]}>{otp[i] || ""}</Text>
            </View>
          ))}
          <TextInput
            ref={inputRef}
            style={s.hiddenInput}
            keyboardType="number-pad"
            maxLength={6}
            value={otp}
            onChangeText={(v) => {
              const digits = v.replace(/\D/g, "").slice(0, 6);
              setOtp(digits);
              if (digits.length === 6) submit(digits);
            }}
            testID="input-otp"
            autoFocus
            caretHidden
          />
        </View>

        <View style={[s.timerRow, { backgroundColor: palette.chipBg }]}>
          <Clock color={expiresIn > 30 ? palette.textSecondary : palette.danger} size={14} />
          <Text style={[s.timerTxt, { color: expiresIn > 30 ? palette.textSecondary : palette.danger }]}>
            {expiresIn > 0 ? `Expires in ${mmss}` : "OTP expired — please resend"}
          </Text>
        </View>

        {demoOtp ? (
          <View style={[s.demoBanner, { backgroundColor: palette.warningBg }]}>
            <KeyRound color={palette.warning} size={14} />
            <Text style={[s.demoTxt, { color: palette.warning }]}>DEV mode OTP: {demoOtp}</Text>
          </View>
        ) : null}

        <Button
          label={verifying ? "Verifying..." : "Verify & Confirm Withdrawal"}
          onPress={() => submit()}
          disabled={otp.length !== 6 || verifying || expiresIn <= 0}
          loading={verifying}
          testID="btn-verify"
        />

        <Pressable
          onPress={resend}
          disabled={cooldown > 0 || resending}
          style={s.resendBtn}
          testID="btn-resend"
        >
          {resending ? (
            <ActivityIndicator color={palette.primary} />
          ) : (
            <>
              <RefreshCw color={cooldown > 0 ? palette.textMuted : palette.primary} size={14} />
              <Text style={[s.resendTxt, { color: cooldown > 0 ? palette.textMuted : palette.primary }]}>
                {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend OTP"}
              </Text>
            </>
          )}
        </Pressable>

        <Text style={[s.disclaimer, { color: palette.textMuted }]}>
          Funds will be reserved from your wallet on OTP verification and released back on cancellation/rejection.
        </Text>
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  iconRing: { width: 76, height: 76, borderRadius: 76, borderWidth: 2, alignItems: "center", justifyContent: "center", marginTop: 10 },
  big: { fontSize: 20, fontWeight: "800", marginTop: 12 },
  sub: { fontSize: 12, textAlign: "center" },
  otpWrap: { flexDirection: "row", justifyContent: "space-between", padding: 8, borderRadius: 16, borderWidth: 1, position: "relative" },
  otpBox: { width: 44, height: 56, borderRadius: 12, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  otpTxt: { fontSize: 22, fontWeight: "900" },
  hiddenInput: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, opacity: 0.001, textAlign: "center", fontSize: 22 },
  timerRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8, borderRadius: 999 },
  timerTxt: { fontSize: 12, fontWeight: "800" },
  demoBanner: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 12 },
  demoTxt: { fontSize: 12, fontWeight: "800" },
  resendBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, padding: 8 },
  resendTxt: { fontSize: 13, fontWeight: "800" },
  disclaimer: { fontSize: 11, textAlign: "center", marginTop: 6, lineHeight: 16 },
});
