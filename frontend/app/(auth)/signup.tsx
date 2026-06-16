import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, User, Mail, Lock, Smartphone, Gift } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";

export default function Signup() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [referral, setReferral] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name || !email || !mobile || !password) {
      show("error", "Please fill all required fields");
      return;
    }
    if (password.length < 6) {
      show("error", "Password must be at least 6 characters");
      return;
    }
    if (!/^[0-9]{10}$/.test(mobile)) {
      show("error", "Enter a valid 10-digit mobile number");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/signup", {
        full_name: name,
        email,
        mobile,
        password,
        referral_code: referral || null,
      });
      await signIn(data.token, data.user);
      show("success", "Welcome aboard! ₹5,000 wallet bonus credited 🎉");
      router.replace("/(tabs)");
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Signup failed");
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

        <Text style={[s.title, { color: palette.textPrimary }]}>Create your account</Text>
        <Text style={[s.subtitle, { color: palette.textSecondary }]}>
          Get ₹5,000 welcome bonus + ₹100 reward points
        </Text>

        <View style={s.form}>
          <Input
            label="Full Name"
            placeholder="John Doe"
            value={name}
            onChangeText={setName}
            leftIcon={<User color={palette.textMuted} size={18} />}
            testID="signup-name-input"
          />
          <Input
            label="Email"
            placeholder="you@email.com"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            leftIcon={<Mail color={palette.textMuted} size={18} />}
            testID="signup-email-input"
          />
          <Input
            label="Mobile (10 digits)"
            placeholder="9876543210"
            value={mobile}
            onChangeText={(v) => setMobile(v.replace(/[^0-9]/g, "").slice(0, 10))}
            keyboardType="number-pad"
            leftIcon={<Smartphone color={palette.textMuted} size={18} />}
            testID="signup-mobile-input"
          />
          <Input
            label="Password (min 6 chars)"
            placeholder="••••••••"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            leftIcon={<Lock color={palette.textMuted} size={18} />}
            testID="signup-password-input"
          />
          <Input
            label="Referral code (optional)"
            placeholder="MFB123ABC"
            value={referral}
            onChangeText={(v) => setReferral(v.toUpperCase())}
            autoCapitalize="characters"
            leftIcon={<Gift color={palette.textMuted} size={18} />}
            testID="signup-referral-input"
          />

          <Button label="Create account" onPress={submit} loading={loading} testID="signup-submit-button" />

          <Pressable onPress={() => router.replace("/(auth)/login")} style={s.row} testID="goto-login-link">
            <Text style={[s.muted, { color: palette.textSecondary }]}>Already have an account? </Text>
            <Text style={[s.link, { color: palette.primary }]}>Sign in</Text>
          </Pressable>
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  scroll: { paddingBottom: 32 },
  back: { paddingVertical: 8, alignSelf: "flex-start" },
  title: { fontSize: 28, fontWeight: "800", letterSpacing: -0.5, marginTop: 8 },
  subtitle: { fontSize: 14, marginTop: 4 },
  form: { gap: 14, marginTop: 24 },
  row: { flexDirection: "row", justifyContent: "center", paddingVertical: 4 },
  muted: { fontSize: 14 },
  link: { fontSize: 14, fontWeight: "700" },
});
