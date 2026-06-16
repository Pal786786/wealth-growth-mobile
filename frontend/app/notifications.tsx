import React from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Bell, TrendingUp, Wallet, Gift, ShieldAlert } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";

const NOTIFICATIONS = [
  { id: "1", icon: TrendingUp, color: "#10B981", title: "SIP installment due", body: "Your monthly SIP for Axis Bluechip is due tomorrow.", time: "2h ago" },
  { id: "2", icon: Wallet, color: "#38BDF8", title: "Wallet credited", body: "₹5,000 welcome bonus added to your wallet.", time: "5h ago" },
  { id: "3", icon: Gift, color: "#F59E0B", title: "Refer & Earn", body: "Invite friends and earn ₹50 each.", time: "1d ago" },
  { id: "4", icon: TrendingUp, color: "#0EA5E9", title: "Market update", body: "NIFTY up 1.2% today. Check your portfolio.", time: "1d ago" },
  { id: "5", icon: ShieldAlert, color: "#EF4444", title: "KYC pending", body: "Complete KYC to unlock all features.", time: "2d ago" },
];

export default function Notifications() {
  const { palette } = useTheme();
  const router = useRouter();
  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <Text style={[s.title, { color: palette.textPrimary }]}>Notifications</Text>
      <ScrollView contentContainerStyle={{ gap: 10, paddingBottom: 32 }}>
        {NOTIFICATIONS.map((n) => {
          const Icon = n.icon;
          return (
            <Card key={n.id} style={s.row}>
              <View style={[s.icon, { backgroundColor: n.color + "1A" }]}>
                <Icon color={n.color} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.heading, { color: palette.textPrimary }]}>{n.title}</Text>
                <Text style={[s.body, { color: palette.textSecondary }]}>{n.body}</Text>
                <Text style={[s.time, { color: palette.textMuted }]}>{n.time}</Text>
              </View>
            </Card>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5, marginBottom: 12 },
  row: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  icon: { padding: 10, borderRadius: 12 },
  heading: { fontSize: 14, fontWeight: "700" },
  body: { fontSize: 12, marginTop: 2 },
  time: { fontSize: 11, marginTop: 4 },
});
