import React from "react";
import { View, Text, StyleSheet, Image, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Button } from "@/src/components/Button";
import { BullLogo } from "@/src/components/BullLogo";
import { Smartphone, Mail, ChevronRight, Shield, TrendingUp, Zap } from "lucide-react-native";

export default function Welcome() {
  const { palette } = useTheme();
  const router = useRouter();
  return (
    <Screen>
      <View style={s.container}>
        <View style={s.heroWrap}>
          <View style={s.logoBlock}>
            <BullLogo size={104} />
            <Text style={[s.brandName, { color: palette.textPrimary }]}>My Funding Bank</Text>
            <Text style={[s.tagline, { color: palette.secondary }]}>
              ◆ Bank • Invest • Travel • Grow ◆
            </Text>
          </View>

          <View style={s.featuresGrid}>
            <FeatureCard icon={<Zap color={palette.primary} size={22} />} title="Instant" subtitle="UPI & QR payments" palette={palette} />
            <FeatureCard icon={<TrendingUp color={palette.success} size={22} />} title="Invest" subtitle="MF, Stocks, Gold" palette={palette} />
            <FeatureCard icon={<Shield color={palette.secondary} size={22} />} title="Secure" subtitle="Bank-grade safety" palette={palette} />
          </View>
        </View>

        <View style={s.actions}>
          <Button
            label="Continue with Mobile"
            icon={<Smartphone color="#fff" size={20} />}
            onPress={() => router.push("/(auth)/otp")}
            testID="welcome-mobile-btn"
          />
          <Button
            label="Continue with Email"
            variant="secondary"
            icon={<Mail color={palette.primary} size={20} />}
            onPress={() => router.push("/(auth)/login")}
            testID="welcome-email-btn"
          />
          <Pressable onPress={() => router.push("/(auth)/signup")} style={s.signupRow} testID="welcome-signup-link">
            <Text style={[s.signupTxt, { color: palette.textSecondary }]}>New here? </Text>
            <Text style={[s.signupLink, { color: palette.primary }]}>Create account</Text>
            <ChevronRight color={palette.primary} size={16} />
          </Pressable>
          <Text style={[s.terms, { color: palette.textMuted }]}>
            By continuing you agree to our Terms & Privacy Policy.
          </Text>
        </View>
      </View>
    </Screen>
  );
}

function FeatureCard({ icon, title, subtitle, palette }: any) {
  return (
    <View style={[fs.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <View style={[fs.iconWrap, { backgroundColor: palette.primary + "18" }]}>{icon}</View>
      <Text style={[fs.title, { color: palette.textPrimary }]}>{title}</Text>
      <Text style={[fs.subtitle, { color: palette.textSecondary }]}>{subtitle}</Text>
    </View>
  );
}

const fs = StyleSheet.create({
  card: {
    flex: 1, borderRadius: 16, padding: 12, borderWidth: 1, alignItems: "flex-start", gap: 6,
  },
  iconWrap: { padding: 8, borderRadius: 10 },
  title: { fontSize: 14, fontWeight: "700" },
  subtitle: { fontSize: 11, fontWeight: "500" },
});

const s = StyleSheet.create({
  container: { flex: 1, justifyContent: "space-between", paddingVertical: 24 },
  heroWrap: { flex: 1, gap: 32, paddingTop: 24 },
  logoBlock: { alignItems: "center", gap: 12 },
  brandName: { fontSize: 32, fontWeight: "800", letterSpacing: -0.8, marginTop: 8 },
  tagline: { fontSize: 14, fontWeight: "600", letterSpacing: 1.2, textTransform: "uppercase" },
  featuresGrid: { flexDirection: "row", gap: 10 },
  actions: { gap: 12 },
  signupRow: { flexDirection: "row", justifyContent: "center", alignItems: "center", paddingVertical: 12 },
  signupTxt: { fontSize: 14 },
  signupLink: { fontSize: 14, fontWeight: "700" },
  terms: { textAlign: "center", fontSize: 11, marginTop: 4, paddingHorizontal: 24 },
});
