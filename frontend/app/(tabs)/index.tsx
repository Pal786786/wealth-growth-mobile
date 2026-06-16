import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import {
  Bell, Send, Plus, QrCode, Smartphone, Receipt, Wallet as WalletIcon,
  Plane, TrendingUp, Coins, ShieldCheck, Gift, ChevronRight, ArrowDownLeft, ArrowUpRight
} from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";
import { BullLogo } from "@/src/components/BullLogo";
import { Card } from "@/src/components/Card";
import { formatINR, shortDate } from "@/src/utils/format";

type Summary = {
  wallet_balance: number;
  portfolio_value: number;
  portfolio_invested: number;
  gold_value: number;
  recent_transactions: any[];
  trending_stocks: any[];
  trending_funds: any[];
};

export default function HomeTab() {
  const { palette } = useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<Summary>("/dashboard/summary");
      setSummary(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = () => { setRefreshing(true); load(); };

  const quickActions = [
    { icon: Send, label: "Send", route: "/wallet/send", color: palette.primary },
    { icon: Plus, label: "Add Money", route: "/wallet/topup", color: palette.success },
    { icon: QrCode, label: "Scan QR", route: "/wallet/qr", color: palette.secondary },
    { icon: Smartphone, label: "Recharge", route: "/recharge", color: palette.warning },
    { icon: Receipt, label: "Bills", route: "/bills", color: "#8B5CF6" },
    { icon: TrendingUp, label: "Invest", route: "/(tabs)/invest", color: palette.success },
    { icon: Plane, label: "Travel", route: "/(tabs)/travel", color: palette.primary },
    { icon: ShieldCheck, label: "Insurance", route: "/insurance", color: palette.danger },
  ];

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <ScrollView
        contentContainerStyle={[s.scroll, { paddingTop: insets.top + 8, paddingBottom: 24 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={palette.primary} />}
        testID="home-dashboard-view"
      >
        {/* Header */}
        <View style={s.header}>
          <View style={s.headerLeft}>
            <BullLogo size={42} />
            <View>
              <Text style={[s.greeting, { color: palette.textSecondary }]}>Hi, welcome back</Text>
              <Text style={[s.name, { color: palette.textPrimary }]} numberOfLines={1}>
                {user?.full_name?.split(" ")[0] || "Friend"} 👋
              </Text>
            </View>
          </View>
          <Pressable
            onPress={() => router.push("/notifications")}
            style={[s.bellBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}
            testID="notifications-btn"
          >
            <Bell color={palette.textPrimary} size={20} />
            <View style={[s.bellDot, { backgroundColor: palette.danger }]} />
          </Pressable>
        </View>

        {/* Hero balance card */}
        <Pressable onPress={() => router.push("/(tabs)/wallet")} testID="balance-card">
          <LinearGradient
            colors={[palette.primary, palette.secondary]}
            start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            style={s.heroCard}
          >
            <View style={s.heroTop}>
              <Text style={s.heroLabel}>Total Wallet Balance</Text>
              <WalletIcon color="rgba(255,255,255,0.85)" size={20} />
            </View>
            <Text style={s.heroAmount} testID="home-wallet-balance">
              {loading ? "—" : formatINR(summary?.wallet_balance ?? 0)}
            </Text>
            <View style={s.heroSubRow}>
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Portfolio</Text>
                <Text style={s.heroSubValue}>{formatINR(summary?.portfolio_value ?? 0, { compact: true })}</Text>
              </View>
              <View style={s.heroDivider} />
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Gold</Text>
                <Text style={s.heroSubValue}>{formatINR(summary?.gold_value ?? 0, { compact: true })}</Text>
              </View>
              <View style={s.heroDivider} />
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Invested</Text>
                <Text style={s.heroSubValue}>{formatINR(summary?.portfolio_invested ?? 0, { compact: true })}</Text>
              </View>
            </View>
          </LinearGradient>
        </Pressable>

        {/* Quick actions */}
        <View style={s.sectionHeader}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Quick Actions</Text>
        </View>
        <View style={s.quickGrid} testID="quick-actions-grid">
          {quickActions.map((a) => (
            <Pressable
              key={a.label}
              onPress={() => router.push(a.route as any)}
              style={[s.quickItem]}
              testID={`quick-action-${a.label.toLowerCase().replace(" ", "-")}`}
            >
              <View style={[s.quickIcon, { backgroundColor: a.color + "1A" }]}>
                <a.icon color={a.color} size={22} />
              </View>
              <Text style={[s.quickLabel, { color: palette.textPrimary }]}>{a.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Rewards CTA */}
        <Pressable onPress={() => router.push("/rewards")} testID="rewards-cta">
          <Card style={[s.rewardsCard, { borderColor: palette.primary + "40" }]}>
            <View style={[s.rewardsIcon, { backgroundColor: palette.warning + "20" }]}>
              <Gift color={palette.warning} size={24} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.rewardsTitle, { color: palette.textPrimary }]}>Rewards & Cashback</Text>
              <Text style={[s.rewardsSubtitle, { color: palette.textSecondary }]}>
                Earn points on every transaction
              </Text>
            </View>
            <ChevronRight color={palette.textSecondary} size={20} />
          </Card>
        </Pressable>

        {/* Trending stocks */}
        <View style={s.sectionHeader}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Trending Stocks</Text>
          <Pressable onPress={() => router.push("/(tabs)/invest")} testID="view-all-stocks">
            <Text style={[s.viewAll, { color: palette.primary }]}>View all</Text>
          </Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.hScroll}>
          {(summary?.trending_stocks ?? []).map((stk) => (
            <Card key={stk.id} style={s.stockCard}>
              <Text style={[s.stockSym, { color: palette.textPrimary }]}>{stk.symbol}</Text>
              <Text style={[s.stockName, { color: palette.textSecondary }]} numberOfLines={1}>{stk.name}</Text>
              <Text style={[s.stockPrice, { color: palette.textPrimary }]}>{formatINR(stk.price)}</Text>
              <View style={[s.stockChange, { backgroundColor: (stk.change >= 0 ? palette.success : palette.danger) + "1A" }]}>
                <Text style={{ color: stk.change >= 0 ? palette.success : palette.danger, fontSize: 12, fontWeight: "700" }}>
                  {stk.change >= 0 ? "▲" : "▼"} {Math.abs(stk.change).toFixed(2)}%
                </Text>
              </View>
            </Card>
          ))}
        </ScrollView>

        {/* Trending Funds */}
        <View style={s.sectionHeader}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Top Mutual Funds</Text>
        </View>
        {(summary?.trending_funds ?? []).map((f) => (
          <Pressable
            key={f.id}
            onPress={() => router.push({ pathname: "/invest/buy", params: { id: f.id, name: f.name, type: "mutual_fund", category: f.category } } as any)}
            testID={`fund-card-${f.id}`}
          >
            <Card style={s.fundRow}>
              <View style={[s.fundIcon, { backgroundColor: palette.primary + "1A" }]}>
                <TrendingUp color={palette.primary} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.fundName, { color: palette.textPrimary }]} numberOfLines={1}>{f.name}</Text>
                <Text style={[s.fundMeta, { color: palette.textSecondary }]}>{f.category} • {f.risk} risk</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={[s.fundReturns, { color: palette.success }]}>+{f.returns_1y}%</Text>
                <Text style={[s.fundMeta, { color: palette.textMuted }]}>1Y</Text>
              </View>
            </Card>
          </Pressable>
        ))}

        {/* Recent transactions */}
        <View style={s.sectionHeader}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Recent Transactions</Text>
          <Pressable onPress={() => router.push("/(tabs)/wallet")} testID="view-all-tx">
            <Text style={[s.viewAll, { color: palette.primary }]}>View all</Text>
          </Pressable>
        </View>
        {loading ? (
          <ActivityIndicator color={palette.primary} style={{ marginVertical: 20 }} />
        ) : (summary?.recent_transactions ?? []).length === 0 ? (
          <Card><Text style={{ color: palette.textSecondary, textAlign: "center", paddingVertical: 12 }}>No transactions yet</Text></Card>
        ) : (
          (summary?.recent_transactions ?? []).map((t) => (
            <Card key={t.tx_id} style={s.txRow}>
              <View
                style={[
                  s.txIcon,
                  { backgroundColor: (t.type === "credit" ? palette.success : palette.danger) + "1A" },
                ]}
              >
                {t.type === "credit" ? (
                  <ArrowDownLeft color={palette.success} size={20} />
                ) : (
                  <ArrowUpRight color={palette.danger} size={20} />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.txDesc, { color: palette.textPrimary }]} numberOfLines={1}>{t.description}</Text>
                <Text style={[s.txMeta, { color: palette.textSecondary }]}>{shortDate(t.created_at)} • {t.category}</Text>
              </View>
              <Text style={[s.txAmount, { color: t.type === "credit" ? palette.success : palette.textPrimary }]}>
                {t.type === "credit" ? "+" : "−"}{formatINR(t.amount)}
              </Text>
            </Card>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  scroll: { paddingHorizontal: 16, gap: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  greeting: { fontSize: 12, fontWeight: "500" },
  name: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  bellBtn: { padding: 10, borderRadius: 14, borderWidth: 1, position: "relative" },
  bellDot: { position: "absolute", top: 8, right: 8, width: 8, height: 8, borderRadius: 4 },

  heroCard: { borderRadius: 24, padding: 20, gap: 14 },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  heroLabel: { color: "rgba(255,255,255,0.85)", fontSize: 13, fontWeight: "600", letterSpacing: 0.4 },
  heroAmount: { color: "#FFFFFF", fontSize: 36, fontWeight: "800", letterSpacing: -1 },
  heroSubRow: { flexDirection: "row", marginTop: 4, backgroundColor: "rgba(255,255,255,0.15)", borderRadius: 14, padding: 12 },
  heroSubItem: { flex: 1, alignItems: "flex-start" },
  heroSubLabel: { color: "rgba(255,255,255,0.8)", fontSize: 11, fontWeight: "600" },
  heroSubValue: { color: "#FFFFFF", fontSize: 14, fontWeight: "800", marginTop: 2 },
  heroDivider: { width: 1, backgroundColor: "rgba(255,255,255,0.25)" },

  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  sectionTitle: { fontSize: 17, fontWeight: "800", letterSpacing: -0.3 },
  viewAll: { fontSize: 13, fontWeight: "700" },

  quickGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  quickItem: { width: "22%", alignItems: "center", gap: 6, marginBottom: 4 },
  quickIcon: { width: 56, height: 56, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  quickLabel: { fontSize: 11, fontWeight: "600", textAlign: "center" },

  rewardsCard: { flexDirection: "row", alignItems: "center", gap: 12 },
  rewardsIcon: { padding: 12, borderRadius: 14 },
  rewardsTitle: { fontSize: 15, fontWeight: "700" },
  rewardsSubtitle: { fontSize: 12, marginTop: 2 },

  hScroll: { gap: 12, paddingRight: 4 },
  stockCard: { width: 140, gap: 4 },
  stockSym: { fontSize: 14, fontWeight: "800" },
  stockName: { fontSize: 11, fontWeight: "500" },
  stockPrice: { fontSize: 16, fontWeight: "800", marginTop: 4 },
  stockChange: { alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, marginTop: 4 },

  fundRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  fundIcon: { padding: 10, borderRadius: 12 },
  fundName: { fontSize: 14, fontWeight: "700" },
  fundMeta: { fontSize: 11, marginTop: 2 },
  fundReturns: { fontSize: 14, fontWeight: "800" },

  txRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  txIcon: { padding: 10, borderRadius: 12 },
  txDesc: { fontSize: 14, fontWeight: "700" },
  txMeta: { fontSize: 11, marginTop: 2 },
  txAmount: { fontSize: 14, fontWeight: "800" },
});
