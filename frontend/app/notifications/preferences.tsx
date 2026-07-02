import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Switch } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Bell, Wallet, TrendingUp, Bot, Gift, ShieldCheck, Info, Smartphone, Mail, MessageCircle } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { notifApi, type NotifPrefs } from "@/src/api/notifications";

const GROUPS: { key: keyof NotifPrefs; label: string; sub: string; icon: any; tint: string }[] = [
  { key: "wallet_alerts", label: "Wallet Alerts", sub: "Top-ups, withdrawals, transfers", icon: Wallet, tint: "#0EA5E9" },
  { key: "investment_alerts", label: "Investment Alerts", sub: "Mutual funds, SIP, gold", icon: TrendingUp, tint: "#6366F1" },
  { key: "ai_alerts", label: "AI Alerts", sub: "Portfolio insights, goal reminders", icon: Bot, tint: "#8B5CF6" },
  { key: "marketing", label: "Marketing", sub: "Cashback, promotions, offers", icon: Gift, tint: "#EC4899" },
  { key: "security_alerts", label: "Security Alerts", sub: "Login, password, suspicious activity", icon: ShieldCheck, tint: "#EF4444" },
  { key: "system_notifications", label: "System Notifications", sub: "KYC, service updates, announcements", icon: Info, tint: "#64748B" },
];
const CHANNELS: { key: keyof NotifPrefs; label: string; sub: string; icon: any }[] = [
  { key: "push_enabled", label: "Push Notifications", sub: "On your device", icon: Smartphone },
  { key: "email_enabled", label: "Email", sub: "Delivered to your inbox", icon: Mail },
  { key: "sms_enabled", label: "SMS", sub: "On your registered number", icon: MessageCircle },
];

export default function NotifPrefsScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [prefs, setPrefs] = useState<NotifPrefs | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const d = await notifApi.getPrefs(); setPrefs(d.preferences); }
    finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggle = async (k: keyof NotifPrefs, v: boolean) => {
    if (!prefs) return;
    setPrefs({ ...prefs, [k]: v });
    try { await notifApi.putPrefs({ [k]: v } as any); show("success", `${k.replace(/_/g, " ")} → ${v ? "ON" : "OFF"}`); }
    catch (e: any) { show("error", "Failed to update"); setPrefs({ ...prefs, [k]: !v }); }
  };

  if (loading || !prefs) return (
    <Screen><ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} /></Screen>
  );

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Preferences</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 20, paddingBottom: 40 }}>
        <Text style={[s.section, { color: palette.textSecondary }]}>WHAT DO YOU WANT TO HEAR ABOUT</Text>
        {GROUPS.map(({ key, label, sub, icon: Icon, tint }) => (
          <View key={key} style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[s.iconWrap, { backgroundColor: tint + "22" }]}>
              <Icon color={tint} size={20} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.rowLabel, { color: palette.textPrimary }]}>{label}</Text>
              <Text style={[s.rowSub, { color: palette.textSecondary }]}>{sub}</Text>
            </View>
            <Switch value={!!prefs[key]} onValueChange={(v) => toggle(key, v)} trackColor={{ true: palette.primary, false: palette.chipBg }} />
          </View>
        ))}

        <Text style={[s.section, { color: palette.textSecondary, marginTop: 10 }]}>DELIVERY CHANNELS</Text>
        {CHANNELS.map(({ key, label, sub, icon: Icon }) => (
          <View key={key} style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[s.iconWrap, { backgroundColor: palette.primary + "22" }]}>
              <Icon color={palette.primary} size={20} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.rowLabel, { color: palette.textPrimary }]}>{label}</Text>
              <Text style={[s.rowSub, { color: palette.textSecondary }]}>{sub}</Text>
            </View>
            <Switch value={!!prefs[key]} onValueChange={(v) => toggle(key, v)} trackColor={{ true: palette.primary, false: palette.chipBg }} />
          </View>
        ))}

        <View style={[s.tip, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
          <Bell color={palette.primary} size={16} />
          <Text style={{ color: palette.textSecondary, fontSize: 11, flex: 1, lineHeight: 16 }}>Security & critical system alerts may still be delivered even if categories are muted. This keeps your account safe.</Text>
        </View>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  section: { fontSize: 11, fontWeight: "800", letterSpacing: 0.6 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: 14, borderWidth: 1 },
  iconWrap: { padding: 8, borderRadius: 10 },
  rowLabel: { fontSize: 14, fontWeight: "800" },
  rowSub: { fontSize: 11, marginTop: 2 },
  tip: { flexDirection: "row", gap: 8, padding: 12, borderRadius: 12, borderWidth: 1, marginTop: 10 },
});
