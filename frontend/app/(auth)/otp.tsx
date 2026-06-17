import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Smartphone, User } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { BullLogo } from "@/src/components/BullLogo";
import { useToast } from "@/src/components/Toast";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";

export default function Otp() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { signIn } = useAuth();
  const [step, setStep] = useState<"mobile" | "otp">("mobile");
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [needsName, setNeedsName] = useState(false);

  const [demoMode, setDemoMode] = useState(false);

  const sendOtp = async () => {
    if (!/^[0-9]{10}$/.test(mobile)) {
      show("error", "Enter a valid 10-digit mobile number");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/otp/request", { mobile });
      setDemoMode(!!data?.demo);
      show("success", data?.demo
        ? "OTP sent (demo mode — ask admin for the code)"
        : "OTP sent to your mobile");
      setStep("otp");
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  };

  const verify = async () => {
    if (otp.length !== 6) {
      show("error", "Enter the 6-digit OTP");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/otp/verify", { mobile, otp, full_name: name || undefined });
      await signIn(data.token, data.user);
      show("success", `Welcome, ${data.user.full_name.split(" ")[0]}!`);
      router.replace("/(tabs)");
    } catch (e: any) {
      const msg = e?.response?.data?.detail || "Invalid OTP";
      if (msg.toLowerCase().includes("full name")) {
        setNeedsName(true);
        show("info", "Looks like you're new. Tell us your name.");
      } else {
        show("error", msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <Pressable onPress={() => (step === "otp" ? setStep("mobile") : router.back())} style={s.back} testID="back-btn">
          <ChevronLeft color={palette.textPrimary} size={26} />
        </Pressable>

        <View style={s.header}>
          <BullLogo size={64} />
          <Text style={[s.title, { color: palette.textPrimary }]}>
            {step === "mobile" ? "Login with Mobile" : "Verify OTP"}
          </Text>
          <Text style={[s.subtitle, { color: palette.textSecondary }]}>
            {step === "mobile"
              ? "We'll send a 6-digit code to your number"
              : demoMode
                ? `Code sent to +91 ${mobile}. (Demo mode — check admin logs for the code)`
                : `Code sent to +91 ${mobile}. It expires in 5 minutes.`}
          </Text>
        </View>

        <View style={s.form}>
          {step === "mobile" ? (
            <>
              <Input
                label="Mobile (10 digits)"
                placeholder="9876543210"
                value={mobile}
                onChangeText={(v) => setMobile(v.replace(/[^0-9]/g, "").slice(0, 10))}
                keyboardType="number-pad"
                leftIcon={<Smartphone color={palette.textMuted} size={18} />}
                testID="otp-mobile-input"
              />
              <Button label="Send OTP" onPress={sendOtp} loading={loading} testID="otp-send-button" />
            </>
          ) : (
            <>
              <Input
                label="OTP"
                placeholder="Enter 6-digit code"
                value={otp}
                onChangeText={(v) => setOtp(v.replace(/[^0-9]/g, "").slice(0, 6))}
                keyboardType="number-pad"
                testID="otp-code-input"
              />
              {needsName ? (
                <Input
                  label="Your Name"
                  placeholder="Full name"
                  value={name}
                  onChangeText={setName}
                  leftIcon={<User color={palette.textMuted} size={18} />}
                  testID="otp-name-input"
                />
              ) : null}
              <Button label="Verify & Continue" onPress={verify} loading={loading} testID="otp-verify-button" />
              <Pressable onPress={sendOtp} style={s.row} testID="otp-resend-link">
                <Text style={[s.link, { color: palette.primary }]}>Resend OTP</Text>
              </Pressable>
            </>
          )}
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  scroll: { paddingBottom: 32 },
  back: { paddingVertical: 8, alignSelf: "flex-start" },
  header: { alignItems: "center", gap: 8, marginVertical: 24 },
  title: { fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { fontSize: 14, textAlign: "center", paddingHorizontal: 24 },
  form: { gap: 16 },
  row: { alignItems: "center", paddingVertical: 8 },
  link: { fontSize: 14, fontWeight: "700" },
});
