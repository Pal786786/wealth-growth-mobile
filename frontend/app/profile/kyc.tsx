import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, FileCheck, ShieldCheck } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthProvider";

export default function KYC() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { user, refresh } = useAuth();
  const [pan, setPan] = useState("");
  const [aadhaar, setAadhaar] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) { show("error", "Enter valid PAN (e.g. ABCDE1234F)"); return; }
    if (!/^[0-9]{12}$/.test(aadhaar)) { show("error", "Enter valid 12-digit Aadhaar"); return; }
    setLoading(true);
    try {
      await api.post("/profile/kyc", { pan, aadhaar });
      await refresh();
      show("success", "KYC verified! You unlocked all features.");
      router.back();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "KYC failed");
    } finally { setLoading(false); }
  };

  if (user?.kyc_status === "verified") {
    return (
      <Screen>
        <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={s.successBox}>
          <View style={[s.iconHero, { backgroundColor: palette.success + "1A" }]}>
            <ShieldCheck color={palette.success} size={48} />
          </View>
          <Text style={[s.title, { color: palette.textPrimary }]}>KYC Verified</Text>
          <Text style={[s.sub, { color: palette.textSecondary }]}>Your identity is verified. All features are unlocked.</Text>
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={[s.iconHero, { backgroundColor: palette.primary + "1A" }]}>
          <FileCheck color={palette.primary} size={32} />
        </View>
        <Text style={[s.title, { color: palette.textPrimary }]}>Complete KYC</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Required to invest, transfer larger amounts</Text>
        <Card style={{ gap: 14, marginTop: 12 }}>
          <Input
            label="PAN Card Number"
            placeholder="ABCDE1234F"
            value={pan}
            onChangeText={(v) => setPan(v.toUpperCase().slice(0, 10))}
            autoCapitalize="characters"
            testID="kyc-pan-input"
          />
          <Input
            label="Aadhaar Number"
            placeholder="123412341234"
            keyboardType="number-pad"
            value={aadhaar}
            onChangeText={(v) => setAadhaar(v.replace(/[^0-9]/g, "").slice(0, 12))}
            testID="kyc-aadhaar-input"
          />
          <Button label="Verify Now" onPress={submit} loading={loading} testID="kyc-submit-btn" />
        </Card>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 14, paddingBottom: 40 },
  iconHero: { alignSelf: "center", padding: 18, borderRadius: 18, marginTop: 12 },
  title: { fontSize: 24, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  sub: { fontSize: 13, textAlign: "center", paddingHorizontal: 24 },
  successBox: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, paddingHorizontal: 24 },
});
