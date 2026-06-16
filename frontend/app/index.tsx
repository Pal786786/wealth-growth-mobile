import React, { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/auth/AuthProvider";
import { useTheme } from "@/src/theme/ThemeProvider";
import { BullLogo } from "@/src/components/BullLogo";

export default function Index() {
  const { user, loading } = useAuth();
  const { palette } = useTheme();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) router.replace("/(tabs)");
    else router.replace("/(auth)/welcome");
  }, [user, loading, router]);

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
