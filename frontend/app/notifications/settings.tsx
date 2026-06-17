import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Switch, Pressable, ActivityIndicator } from "react-native";
import { Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ArrowLeft, Bell, CheckCircle2, AlertTriangle, ShieldCheck, Gift, Megaphone, ReceiptText } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";

type Prefs = {
  transactions: boolean;
  rewards: boolean;
  promotional: boolean;
  security: boolean;
  push_enabled: boolean;
};

const CATEGORIES: { key: keyof Prefs; label: string; sub: string; Icon: any }[] = [
  { key: "transactions", label: "Transactions", sub: "Wallet credits/debits, payments, refunds", Icon: ReceiptText },
  { key: "rewards", label: "Rewards & Cashback", sub: "Points earned, tier upgrades, special offers", Icon: Gift },
  { key: "security", label: "Security Alerts", sub: "Login attempts, KYC, password changes", Icon: ShieldCheck },
  { key: "promotional", label: "Promotional", sub: "New features, market trends, festive offers", Icon: Megaphone },
];

export default function NotificationSettings() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<Prefs>("/notifications/preferences");
      setPrefs(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggle = async (key: keyof Prefs) => {
    if (!prefs) return;
    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    setSaving(true);
    try {
      await api.put("/notifications/preferences", {
        transactions: next.transactions,
        rewards: next.rewards,
        promotional: next.promotional,
        security: next.security,
      });
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  return (
    <View style={[s.root, { backgroundColor: palette.background, paddingTop: insets.top }]}>
      <Stack.Screen options={{ headerShown: false }} />

      <View style={s.header}>
        <Pressable onPress={() => router.back()} style={s.iconBtn} testID="ns-back">
          <ArrowLeft color={palette.textPrimary} size={20} />
        </Pressable>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>Notifications</Text>
          <Text style={[s.sub, { color: palette.textSecondary }]}>Choose what you'd like to hear about</Text>
        </View>
        <Bell color={palette.primary} size={22} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: insets.bottom + 30 }}>
        {loading ? <ActivityIndicator color={palette.primary} /> : null}

        {/* FCM status banner */}
        {prefs ? (
          <Card style={{
            backgroundColor: prefs.push_enabled ? palette.successBg : palette.warningBg,
            borderColor: prefs.push_enabled ? palette.success : palette.warning,
            borderWidth: 1, gap: 6,
          }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              {prefs.push_enabled
                ? <CheckCircle2 color={palette.success} size={18} />
                : <AlertTriangle color={palette.warning} size={18} />}
              <Text style={{
                fontWeight: "800", color: prefs.push_enabled ? palette.success : palette.warning,
              }}>
                {prefs.push_enabled ? "Push Notifications Active" : "FCM Not Configured"}
              </Text>
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 12, lineHeight: 17 }}>
              {prefs.push_enabled
                ? "Your device will receive real-time alerts based on the categories below."
                : "Upload google-services.json and publish the app to enable real push notifications. Until then, you'll see in-app notifications only."}
            </Text>
          </Card>
        ) : null}

        {/* Category toggles */}
        {prefs ? CATEGORIES.map((c) => (
          <Card key={c.key} style={s.row}>
            <View style={[s.rowIcon, { backgroundColor: palette.surfaceAlt }]}>
              <c.Icon color={palette.primary} size={18} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.rowLabel, { color: palette.textPrimary }]}>{c.label}</Text>
              <Text style={[s.rowSub, { color: palette.textSecondary }]}>{c.sub}</Text>
            </View>
            <Switch
              value={prefs[c.key] as boolean}
              onValueChange={() => toggle(c.key)}
              trackColor={{ false: palette.border, true: palette.primary }}
              thumbColor="#fff"
              testID={`pref-${c.key}`}
            />
          </Card>
        )) : null}

        {saving ? (
          <Text style={{ textAlign: "center", color: palette.textMuted, fontSize: 11 }}>Saving…</Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 12, gap: 6 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800" },
  sub: { fontSize: 12, marginTop: 2 },

  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  rowIcon: { width: 36, height: 36, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  rowLabel: { fontSize: 14, fontWeight: "700" },
  rowSub: { fontSize: 11, marginTop: 2 },
});
