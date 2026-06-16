import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Mail, Lock, Eye, EyeOff } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { BullLogo } from "@/src/components/BullLogo";
import { useToast } from "@/src/components/Toast";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";

export default function Login() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { signIn } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!identifier || !password) {
      show("error", "Please enter your email/mobile and password");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { identifier, password });
      await signIn(data.token, data.user);
      show("success", `Welcome back, ${data.user.full_name.split(" ")[0]}!`);
      router.replace("/(tabs)");
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <Pressable onPress={() => router.back()} style={s.back} testID="back-btn">
          <ChevronLeft color={palette.textPrimary} size={26} />
        </Pressable>

        <View style={s.header}>
          <BullLogo size={64} />
          <Text style={[s.title, { color: palette.textPrimary }]}>Welcome back</Text>
          <Text style={[s.subtitle, { color: palette.textSecondary }]}>
            Sign in to continue managing your finances
          </Text>
        </View>

        <View style={s.form}>
          <Input
            label="Email or Mobile"
            placeholder="you@email.com or 9876543210"
            value={identifier}
            onChangeText={setIdentifier}
            autoCapitalize="none"
            keyboardType="email-address"
            leftIcon={<Mail color={palette.textMuted} size={18} />}
            testID="login-identifier-input"
          />
          <Input
            label="Password"
            placeholder="Your password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!showPw}
            leftIcon={<Lock color={palette.textMuted} size={18} />}
            rightSlot={
              <Pressable onPress={() => setShowPw((v) => !v)} testID="toggle-password-btn">
                {showPw ? <EyeOff color={palette.textMuted} size={18} /> : <Eye color={palette.textMuted} size={18} />}
              </Pressable>
            }
            testID="login-password-input"
          />

          <Button label="Sign in" onPress={submit} loading={loading} testID="login-submit-button" />

          <Pressable onPress={() => router.push("/(auth)/signup")} style={s.row} testID="goto-signup-link">
            <Text style={[s.muted, { color: palette.textSecondary }]}>Don&apos;t have an account? </Text>
            <Text style={[s.link, { color: palette.primary }]}>Sign up</Text>
          </Pressable>

          <View style={[s.divider, { backgroundColor: palette.border }]} />

          <Button
            label="Use Mobile OTP"
            variant="ghost"
            onPress={() => router.replace("/(auth)/otp")}
            testID="login-otp-link"
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  scroll: { paddingBottom: 32 },
  back: { paddingVertical: 8, alignSelf: "flex-start" },
  header: { alignItems: "center", gap: 8, marginVertical: 24 },
  title: { fontSize: 28, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { fontSize: 14, textAlign: "center", paddingHorizontal: 24 },
  form: { gap: 16, marginTop: 12 },
  row: { flexDirection: "row", justifyContent: "center", paddingVertical: 4 },
  muted: { fontSize: 14 },
  link: { fontSize: 14, fontWeight: "700" },
  divider: { height: 1, marginVertical: 4 },
});
