import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Gift, Award, Trophy, Users, Sparkles } from "lucide-react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";

export default function Rewards() {
  const { palette } = useTheme();
  const router = useRouter();
  const [data, setData] = useState<any>(null);

  useEffect(() => { api.get("/rewards").then(({ data }) => setData(data)).catch(() => {}); }, []);

  const BADGE_ICONS: Record<string, any> = { Award, Trophy, Users, Gift };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll}>
        <LinearGradient colors={[palette.primary, palette.secondary]} style={s.hero}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <Sparkles color="#fff" size={22} />
            <Text style={s.heroLabel}>Reward Points</Text>
          </View>
          <Text style={s.heroValue} testID="reward-points">{data?.reward_points ?? 0}</Text>
          <Text style={s.heroSub}>Total cashback earned • {formatINR(data?.cashback_earned ?? 0)}</Text>
        </LinearGradient>

        <View style={s.statsRow}>
          <Card style={s.statBox}>
            <Users color={palette.success} size={18} />
            <Text style={[s.statValue, { color: palette.textPrimary }]}>{data?.referrals_count ?? 0}</Text>
            <Text style={[s.statLabel, { color: palette.textSecondary }]}>Referrals</Text>
          </Card>
          <Card style={s.statBox}>
            <Gift color={palette.warning} size={18} />
            <Text style={[s.statValue, { color: palette.textPrimary }]}>{formatINR(data?.referral_earnings ?? 0)}</Text>
            <Text style={[s.statLabel, { color: palette.textSecondary }]}>Earned</Text>
          </Card>
        </View>

        <Text style={[s.section, { color: palette.textPrimary }]}>Achievement Badges</Text>
        {(data?.badges ?? []).length === 0 ? (
          <Card><Text style={{ color: palette.textSecondary, textAlign: "center" }}>Make transactions to unlock badges</Text></Card>
        ) : (
          <View style={s.badgesRow}>
            {(data?.badges ?? []).map((b: any) => {
              const Icon = BADGE_ICONS[b.icon] || Award;
              return (
                <View key={b.id} style={[s.badge, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <View style={[s.badgeIcon, { backgroundColor: palette.warning + "1A" }]}>
                    <Icon color={palette.warning} size={26} />
                  </View>
                  <Text style={[s.badgeName, { color: palette.textPrimary }]}>{b.name}</Text>
                </View>
              );
            })}
          </View>
        )}

        <Pressable onPress={() => router.push("/referral")} testID="goto-referral">
          <Card style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            <View style={[s.badgeIcon, { backgroundColor: palette.primary + "1A" }]}>
              <Gift color={palette.primary} size={22} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.row, { color: palette.textPrimary }]}>Refer & Earn ₹50</Text>
              <Text style={[s.rowSub, { color: palette.textSecondary }]}>Per friend who signs up • {data?.referrals_count ?? 0} referred</Text>
            </View>
            <Text style={[s.row, { color: palette.primary }]}>›</Text>
          </Card>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 14, paddingBottom: 40 },
  hero: { borderRadius: 24, padding: 22, gap: 6, marginTop: 8 },
  heroLabel: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase" },
  heroValue: { color: "#fff", fontSize: 56, fontWeight: "800", letterSpacing: -2, marginTop: 4 },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 13, fontWeight: "600" },
  statsRow: { flexDirection: "row", gap: 12 },
  statBox: { flex: 1, gap: 8, alignItems: "flex-start" },
  statValue: { fontSize: 20, fontWeight: "800" },
  statLabel: { fontSize: 11, fontWeight: "600" },
  section: { fontSize: 16, fontWeight: "800", marginTop: 4, letterSpacing: -0.3 },
  badgesRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  badge: { width: "30%", borderRadius: 16, padding: 12, alignItems: "center", borderWidth: 1, gap: 6 },
  badgeIcon: { padding: 10, borderRadius: 14 },
  badgeName: { fontSize: 12, fontWeight: "700", textAlign: "center" },
  row: { fontSize: 15, fontWeight: "800" },
  rowSub: { fontSize: 12, marginTop: 2 },
});
