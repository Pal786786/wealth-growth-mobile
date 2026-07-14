import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { rewardsApi, RewardWallet, Badge, Campaign } from "@/src/api/rewards";

export default function RewardsDashboard() {
  const router = useRouter();
  const [wallet, setWallet] = useState<RewardWallet | null>(null);
  const [badges, setBadges] = useState<Badge[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [claiming, setClaiming] = useState(false);

  const load = useCallback(async () => {
    try {
      const [w, b, c] = await Promise.all([
        rewardsApi.wallet(),
        rewardsApi.achievements(),
        rewardsApi.activeCampaigns(),
      ]);
      setWallet(w); setBadges(b); setCampaigns(c);
    } catch (e: any) {
      // Non-fatal; keep UI functional
      console.warn("rewards load failed", e?.message);
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const claimDaily = async () => {
    setClaiming(true);
    try {
      const r: any = await rewardsApi.claimDailyLogin();
      if (r.skipped) Alert.alert("Already claimed", "Come back tomorrow 😊");
      else Alert.alert("Daily reward!", `+${r.amount} MFB (streak day ${r.streak})`);
      await load();
    } catch (e: any) { Alert.alert("Error", e?.message || "Failed to claim"); }
    finally { setClaiming(false); }
  };

  if (loading) return (
    <SafeAreaView style={styles.center}><ActivityIndicator size="large" color="#FFB100" /></SafeAreaView>
  );

  const unlocked = badges.filter(b => b.unlocked).length;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.wrap}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
      >
        <View style={styles.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn}>
            <Ionicons name="chevron-back" size={24} color="#EAEAF0" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>MFB Rewards</Text>
          <TouchableOpacity onPress={() => router.push("/mfb-rewards/history")}>
            <Ionicons name="time-outline" size={22} color="#EAEAF0" />
          </TouchableOpacity>
        </View>

        {/* Balance card */}
        <View style={styles.balanceCard}>
          <Text style={styles.tierEmoji}>{wallet?.tier?.emoji || "🥉"}</Text>
          <Text style={styles.tierName}>{wallet?.tier?.name || "Bronze"}</Text>
          <Text style={styles.balance}>{wallet?.balance ?? 0}</Text>
          <Text style={styles.balanceLabel}>MFB Tokens</Text>

          <View style={styles.xpRow}>
            <Text style={styles.xpText}>Level {wallet?.level ?? 1}</Text>
            <View style={styles.xpBar}>
              <View style={[styles.xpFill, { width: `${wallet?.progress_pct ?? 0}%` }]} />
            </View>
            <Text style={styles.xpText}>{wallet?.xp ?? 0} / {wallet?.next_level_xp ?? 100}</Text>
          </View>

          <View style={styles.metaRow}>
            <View style={styles.metaCell}><Text style={styles.metaVal}>{wallet?.lifetime_earned ?? 0}</Text><Text style={styles.metaLbl}>Earned</Text></View>
            <View style={styles.metaCell}><Text style={styles.metaVal}>{wallet?.streak_current ?? 0}</Text><Text style={styles.metaLbl}>Streak</Text></View>
            <View style={styles.metaCell}><Text style={styles.metaVal}>{wallet?.referral_count ?? 0}</Text><Text style={styles.metaLbl}>Referrals</Text></View>
            <View style={styles.metaCell}><Text style={styles.metaVal}>{unlocked}/9</Text><Text style={styles.metaLbl}>Badges</Text></View>
          </View>

          <TouchableOpacity style={styles.claimBtn} onPress={claimDaily} disabled={claiming}>
            <Ionicons name="gift-outline" size={18} color="#0E0F14" />
            <Text style={styles.claimText}>{claiming ? "Claiming…" : "Claim Daily Reward"}</Text>
          </TouchableOpacity>
        </View>

        {/* Quick actions */}
        <View style={styles.actionsRow}>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push("/mfb-rewards/referrals")}>
            <Ionicons name="share-social" size={22} color="#FFB100" />
            <Text style={styles.actionText}>Refer</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push("/mfb-rewards/leaderboard")}>
            <Ionicons name="trophy" size={22} color="#FFB100" />
            <Text style={styles.actionText}>Leaders</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => router.push("/mfb-rewards/history")}>
            <Ionicons name="receipt" size={22} color="#FFB100" />
            <Text style={styles.actionText}>History</Text>
          </TouchableOpacity>
        </View>

        {/* Active campaigns */}
        {campaigns.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>🔥 Active Campaigns</Text>
            {campaigns.map((c) => (
              <TouchableOpacity
                key={c.campaign_id} style={styles.campaignCard}
                onPress={async () => {
                  try {
                    await rewardsApi.claimCampaign(c.campaign_id);
                    Alert.alert("Campaign claimed", `+${c.reward} MFB from ${c.name}`);
                    load();
                  } catch (e: any) {
                    Alert.alert("Cannot claim", e?.response?.data?.detail || e?.message);
                  }
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.campaignName}>{c.name}</Text>
                  {c.description ? <Text style={styles.campaignDesc}>{c.description}</Text> : null}
                </View>
                <View style={styles.campaignReward}>
                  <Text style={styles.campaignRewardTxt}>+{c.reward}</Text>
                  <Text style={styles.campaignRewardUnit}>MFB</Text>
                </View>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Achievements grid */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🏆 Achievements ({unlocked}/{badges.length})</Text>
          <View style={styles.badgeGrid}>
            {badges.map((b) => (
              <View key={b.code} style={[styles.badgeCard, !b.unlocked && styles.badgeLocked]}>
                <Text style={styles.badgeEmoji}>{b.emoji}</Text>
                <Text style={styles.badgeTitle}>{b.title}</Text>
                <Text style={styles.badgeStatus}>{b.unlocked ? "Unlocked" : "Locked"}</Text>
              </View>
            ))}
          </View>
        </View>

        <Text style={styles.footNote}>
          MFB Tokens are internal reward points. They cannot be withdrawn or transferred.
          Ready for future blockchain migration.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0E0F14" },
  center: { flex: 1, backgroundColor: "#0E0F14", justifyContent: "center", alignItems: "center" },
  wrap: { padding: 16, paddingBottom: 40 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  iconBtn: { padding: 4 },
  headerTitle: { color: "#EAEAF0", fontSize: 18, fontWeight: "700" },
  balanceCard: {
    backgroundColor: "#171922", borderRadius: 20, padding: 20, alignItems: "center",
    borderWidth: 1, borderColor: "#2A2D3A",
  },
  tierEmoji: { fontSize: 40, marginBottom: 4 },
  tierName: { color: "#FFB100", fontSize: 14, fontWeight: "700", letterSpacing: 1 },
  balance: { color: "#EAEAF0", fontSize: 44, fontWeight: "800", marginTop: 4 },
  balanceLabel: { color: "#8B8F9E", fontSize: 13, marginBottom: 12 },
  xpRow: { flexDirection: "row", alignItems: "center", width: "100%", marginBottom: 12, gap: 8 },
  xpText: { color: "#8B8F9E", fontSize: 11 },
  xpBar: { flex: 1, height: 6, borderRadius: 3, backgroundColor: "#2A2D3A", overflow: "hidden" },
  xpFill: { height: 6, backgroundColor: "#FFB100" },
  metaRow: { flexDirection: "row", width: "100%", justifyContent: "space-between", marginBottom: 16 },
  metaCell: { flex: 1, alignItems: "center" },
  metaVal: { color: "#EAEAF0", fontSize: 16, fontWeight: "700" },
  metaLbl: { color: "#8B8F9E", fontSize: 11, marginTop: 2 },
  claimBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: "#FFB100", paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12,
  },
  claimText: { color: "#0E0F14", fontWeight: "800", fontSize: 14 },
  actionsRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 16, gap: 10 },
  actionBtn: {
    flex: 1, backgroundColor: "#171922", padding: 14, borderRadius: 14, alignItems: "center",
    borderWidth: 1, borderColor: "#2A2D3A", gap: 6,
  },
  actionText: { color: "#EAEAF0", fontSize: 12, fontWeight: "600" },
  section: { marginTop: 24 },
  sectionTitle: { color: "#EAEAF0", fontSize: 16, fontWeight: "700", marginBottom: 12 },
  campaignCard: {
    flexDirection: "row", backgroundColor: "#171922", borderRadius: 12, padding: 14, marginBottom: 8,
    alignItems: "center", borderWidth: 1, borderColor: "#2A2D3A",
  },
  campaignName: { color: "#EAEAF0", fontSize: 14, fontWeight: "700" },
  campaignDesc: { color: "#8B8F9E", fontSize: 12, marginTop: 2 },
  campaignReward: { alignItems: "center" },
  campaignRewardTxt: { color: "#FFB100", fontSize: 18, fontWeight: "800" },
  campaignRewardUnit: { color: "#8B8F9E", fontSize: 10 },
  badgeGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  badgeCard: {
    width: "31%", backgroundColor: "#171922", borderRadius: 12, padding: 10,
    alignItems: "center", marginBottom: 10, borderWidth: 1, borderColor: "#2A2D3A",
  },
  badgeLocked: { opacity: 0.35 },
  badgeEmoji: { fontSize: 28, marginBottom: 4 },
  badgeTitle: { color: "#EAEAF0", fontSize: 11, fontWeight: "700", textAlign: "center" },
  badgeStatus: { color: "#8B8F9E", fontSize: 9, marginTop: 2 },
  footNote: { color: "#5A5D6B", fontSize: 11, textAlign: "center", marginTop: 28, paddingHorizontal: 20, lineHeight: 16 },
});
