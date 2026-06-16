import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Switch, Image } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import {
  User as UserIcon, Moon, Sun, Shield, FileCheck, Gift, Users, LogOut, ChevronRight,
  ShieldCheck, Bell, CreditCard, Award, HelpCircle, Globe
} from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";

export default function ProfileTab() {
  const { palette, mode, toggle } = useTheme();
  const { user, signOut } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [rewardPoints, setRewardPoints] = useState(0);

  useFocusEffect(useCallback(() => {
    (async () => {
      try {
        const { data } = await api.get("/rewards");
        setRewardPoints(data.reward_points);
      } catch {}
    })();
  }, []));

  const initials = (user?.full_name || "U").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  const sections = [
    {
      title: "Account",
      items: [
        { icon: FileCheck, label: "KYC Verification", value: user?.kyc_status === "verified" ? "Verified" : "Pending", route: "/profile/kyc", color: user?.kyc_status === "verified" ? palette.success : palette.warning },
        { icon: CreditCard, label: "Linked Bank Accounts", value: "Manage", route: "/profile/banks", color: palette.primary },
        { icon: Award, label: "Rewards & Cashback", value: `${rewardPoints} pts`, route: "/rewards", color: palette.warning },
        { icon: Gift, label: "Refer & Earn", value: user?.referral_code || "—", route: "/referral", color: palette.success },
      ],
    },
    {
      title: "Security",
      items: [
        { icon: Shield, label: "Security Settings", route: "/profile/security", color: palette.danger },
        { icon: ShieldCheck, label: "Privacy Controls", route: "/profile/privacy", color: palette.secondary },
        { icon: Bell, label: "Notifications", route: "/notifications", color: palette.primary },
      ],
    },
    {
      title: "More",
      items: [
        { icon: Globe, label: "Language", value: "English", color: palette.primary },
        { icon: HelpCircle, label: "Help & Support", color: palette.secondary },
      ],
    },
  ];

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <ScrollView contentContainerStyle={[s.scroll, { paddingTop: insets.top + 16, paddingBottom: 32 }]}>
        <View style={s.userCard}>
          <View style={[s.avatar, { backgroundColor: palette.primary + "30", borderColor: palette.primary }]}>
            <Text style={[s.avatarTxt, { color: palette.primary }]}>{initials}</Text>
          </View>
          <Text style={[s.name, { color: palette.textPrimary }]} testID="profile-name">{user?.full_name || "Guest"}</Text>
          <Text style={[s.contact, { color: palette.textSecondary }]}>{user?.email}</Text>
          <Text style={[s.contact, { color: palette.textSecondary }]}>+91 {user?.mobile}</Text>
          <View style={[s.kycBadge, {
            backgroundColor: user?.kyc_status === "verified" ? palette.success + "20" : palette.warning + "20",
            borderColor: user?.kyc_status === "verified" ? palette.success : palette.warning,
          }]} testID="profile-kyc-badge">
            <ShieldCheck color={user?.kyc_status === "verified" ? palette.success : palette.warning} size={14} />
            <Text style={{
              color: user?.kyc_status === "verified" ? palette.success : palette.warning,
              fontSize: 12, fontWeight: "700",
            }}>
              {user?.kyc_status === "verified" ? "KYC Verified" : "Complete KYC"}
            </Text>
          </View>
        </View>

        <Card style={s.themeCard}>
          <View style={[s.iconWrap, { backgroundColor: palette.primary + "1A" }]}>
            {mode === "dark" ? <Moon color={palette.primary} size={20} /> : <Sun color={palette.primary} size={20} />}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[s.rowLabel, { color: palette.textPrimary }]}>Appearance</Text>
            <Text style={[s.rowMeta, { color: palette.textSecondary }]}>
              {mode === "dark" ? "Dark mode" : "Light mode"}
            </Text>
          </View>
          <Switch
            value={mode === "dark"}
            onValueChange={toggle}
            trackColor={{ false: palette.border, true: palette.primary }}
            thumbColor="#fff"
            testID="theme-toggle"
          />
        </Card>

        {sections.map((sec) => (
          <View key={sec.title} style={{ gap: 8 }}>
            <Text style={[s.section, { color: palette.textSecondary }]}>{sec.title.toUpperCase()}</Text>
            {sec.items.map((it: any) => (
              <Pressable
                key={it.label}
                onPress={() => it.route && router.push(it.route)}
                testID={`profile-row-${it.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <Card style={s.row}>
                  <View style={[s.iconWrap, { backgroundColor: it.color + "1A" }]}>
                    <it.icon color={it.color} size={20} />
                  </View>
                  <Text style={[s.rowLabel, { color: palette.textPrimary, flex: 1 }]}>{it.label}</Text>
                  {it.value ? (
                    <Text style={[s.rowValue, { color: palette.textSecondary }]}>{it.value}</Text>
                  ) : null}
                  <ChevronRight color={palette.textMuted} size={18} />
                </Card>
              </Pressable>
            ))}
          </View>
        ))}

        <Pressable
          onPress={async () => { await signOut(); router.replace("/(auth)/welcome"); }}
          style={[s.logoutBtn, { borderColor: palette.danger }]}
          testID="logout-btn"
        >
          <LogOut color={palette.danger} size={18} />
          <Text style={{ color: palette.danger, fontSize: 15, fontWeight: "700" }}>Sign out</Text>
        </Pressable>
        <Text style={[s.version, { color: palette.textMuted }]}>My Funding Bank v1.0.0</Text>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  scroll: { paddingHorizontal: 16, gap: 16 },
  userCard: { alignItems: "center", gap: 6, paddingVertical: 8 },
  avatar: { width: 80, height: 80, borderRadius: 40, alignItems: "center", justifyContent: "center", borderWidth: 2 },
  avatarTxt: { fontSize: 28, fontWeight: "800" },
  name: { fontSize: 22, fontWeight: "800", letterSpacing: -0.5, marginTop: 8 },
  contact: { fontSize: 13, fontWeight: "500" },
  kycBadge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1, marginTop: 6 },
  themeCard: { flexDirection: "row", alignItems: "center", gap: 12 },
  section: { fontSize: 11, fontWeight: "800", letterSpacing: 1.2, marginTop: 4, paddingHorizontal: 4 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  iconWrap: { padding: 10, borderRadius: 12 },
  rowLabel: { fontSize: 14, fontWeight: "600" },
  rowMeta: { fontSize: 11, marginTop: 2 },
  rowValue: { fontSize: 12, fontWeight: "600" },
  logoutBtn: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, padding: 14, borderRadius: 14, borderWidth: 1.5, marginTop: 4 },
  version: { textAlign: "center", fontSize: 11, marginTop: 8 },
});
