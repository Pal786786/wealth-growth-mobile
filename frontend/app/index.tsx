import React, { useEffect, useState } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/auth/AuthProvider";
import { useTheme } from "@/src/theme/ThemeProvider";
import { BullLogo } from "@/src/components/BullLogo";
import { storage } from "@/src/utils/storage";

export default function Index() {
  const { user, loading } = useAuth();
  const { palette } = useTheme();
  const router = useRouter();
  const [bootChecked, setBootChecked] = useState(false);
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const flag = await storage.getItem<boolean>("mfb_onboarded", false);
      setOnboarded(!!flag);
      setBootChecked(true);
    })();
  }, []);

  useEffect(() => {
    if (loading || !bootChecked) return;
    if (!onboarded) {
      router.replace("/onboarding");
      return;
    }
    if (user) router.replace("/(tabs)");
    else router.replace("/(auth)/welcome");
  }, [user, loading, router, bootChecked, onboarded]);

  return (
    <View style={[s.root, { backgroundColor: palette.background }]} testID="splash-screen">
      <BullLogo size={120} />
      <ActivityIndicator color={palette.primary} style={{ marginTop: 32 }} />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, alignItems: "center", justifyContent: "center" },
});
