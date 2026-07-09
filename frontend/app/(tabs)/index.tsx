import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, Dimensions } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import {
  Bell, Send, Plus, QrCode, Smartphone, Receipt, Wallet as WalletIcon,
  Plane, TrendingUp, ShieldCheck, Gift, ChevronRight, ArrowDownLeft, ArrowUpRight, Eye, EyeOff, TrendingDown,
  AlertTriangle, Bot, LineChart, Users, Copy as CopyIcon, Brain
} from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useAuth } from "@/src/auth/AuthProvider";
import { api } from "@/src/api/client";
import { BullLogo } from "@/src/components/BullLogo";
import { Card } from "@/src/components/Card";
import { AnimatedCounter } from "@/src/components/AnimatedCounter";
import { Sparkline } from "@/src/components/Sparkline";
import { formatINR, shortDate } from "@/src/utils/format";
import { shadow } from "@/src/utils/shadow";

type Summary = {
  wallet_balance: number;
  portfolio_value: number;
  portfolio_invested: number;
  gold_value: number;
  recent_transactions: any[];
  trending_stocks: any[];
  trending_funds: any[];
};

type Banner = { id: string; title: string; subtitle?: string; cta_label?: string; cta_route?: string };

const { width: SCREEN_W } = Dimensions.get("window");

export default function HomeTab() {
  const { palette } = useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [banners, setBanners] = useState<Banner[]>([]);
  const [apiStatus, setApiStatus] = useState<{ any_demo: boolean; demo_count: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [hideBalance, setHideBalance] = useState(false);

  const load = useCallback(async () => {
    try {
      const [{ data: s }, { data: b }, { data: st }] = await Promise.all([
        api.get<Summary>("/dashboard/summary"),
        api.get<Banner[]>("/app/banners").catch(() => ({ data: [] as Banner[] })),
        api.get<{ any_demo: boolean; demo_count: number }>("/app/api-status").catch(() => ({ data: { any_demo: false, demo_count: 0 } as any })),
      ]);
      setSummary(s); setBanners(b); setApiStatus(st);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
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
    { icon: Bot, label: "AI Advisor", route: "/advisor", color: "#4F46E5" },
    { icon: LineChart, label: "Markets", route: "/market", color: "#0EA5E9" },
    { icon: Users, label: "Copy Traders", route: "/traders", color: "#EC4899" },
    { icon: Brain, label: "AI Signals", route: "/ai", color: "#8B5CF6" },
    { icon: CopyIcon, label: "My Copies", route: "/copies", color: "#F59E0B" },
    { icon: Plane, label: "Travel", route: "/(tabs)/travel", color: palette.primary },
    { icon: ShieldCheck, label: "Insurance", route: "/insurance", color: palette.danger },
  ];

  const totalReturn = (summary?.portfolio_value ?? 0) - (summary?.portfolio_invested ?? 0);
  const returnPct = summary?.portfolio_invested
    ? (totalReturn / summary.portfolio_invested) * 100
    : 0;
  const isUp = totalReturn >= 0;

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <ScrollView
        contentContainerStyle={[s.scroll, { paddingTop: insets.top + 8, paddingBottom: 110 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={palette.primary} />}
        testID="home-dashboard-view"
      >
        {/* Header */}
        <View style={s.header}>
          <View style={s.headerLeft}>
            <BullLogo size={44} />
            <View>
              <Text style={[s.greeting, { color: palette.textSecondary }]}>WELCOME BACK</Text>
              <Text style={[s.name, { color: palette.textPrimary }]} numberOfLines={1}>
                {user?.full_name?.split(" ")[0] || "Trader"}
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

        {/* Demo Mode banner — shown when any 3rd-party API is missing */}
        {apiStatus?.any_demo ? (
          <View style={s.demoBanner} testID="demo-mode-banner">
            <AlertTriangle color="#92400E" size={16} />
            <View style={{ flex: 1 }}>
              <Text style={s.demoBannerTitle}>Demo Mode Active</Text>
              <Text style={s.demoBannerBody} numberOfLines={2}>
                Live API keys are not configured yet. Demo data is being used.
              </Text>
            </View>
            <View style={s.demoBadge}><Text style={s.demoBadgeText}>{apiStatus.demo_count}</Text></View>
          </View>
        ) : null}

        {/* Hero banner — bull, balance, sparkline */}
        <Pressable onPress={() => router.push("/(tabs)/wallet")} testID="balance-card">
          <LinearGradient
            colors={["#0F172A", "#0EA5E9", "#38BDF8"]}
            start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            locations={[0, 0.65, 1]}
            style={s.heroCard}
          >
            {/* Decorative bull silhouette */}
            <View style={s.heroBullWrap} pointerEvents="none">
              <BullLogo size={140} variant="flat" />
            </View>

            <View style={s.heroTop}>
              <View>
                <Text style={s.heroLabel}>TOTAL BALANCE</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
                  {hideBalance ? (
                    <Text style={s.heroAmount}>•••••••</Text>
                  ) : (
                    <AnimatedCounter
                      value={summary?.wallet_balance ?? 0}
                      style={s.heroAmount}
                      testID="home-wallet-balance"
                    />
                  )}
                  <Pressable
                    onPress={() => setHideBalance((v) => !v)}
                    hitSlop={10}
                    testID="hide-balance-btn"
                  >
                    {hideBalance
                      ? <EyeOff color="rgba(255,255,255,0.7)" size={20} />
                      : <Eye color="rgba(255,255,255,0.7)" size={20} />}
                  </Pressable>
                </View>
              </View>
              <WalletIcon color="rgba(255,255,255,0.85)" size={22} />
            </View>

            {/* Portfolio insight strip with mini chart */}
            <View style={s.portfolioStrip}>
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={s.portfolioLabel}>Portfolio Performance</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={s.portfolioValue}>{formatINR(summary?.portfolio_value ?? 0, { compact: true })}</Text>
                  <View style={s.portfolioBadge}>
                    {isUp ? <TrendingUp color="#86efac" size={12} /> : <TrendingDown color="#fda4af" size={12} />}
                    <Text style={[s.portfolioPct, { color: isUp ? "#86efac" : "#fda4af" }]}>
                      {isUp ? "+" : ""}{returnPct.toFixed(2)}%
                    </Text>
                  </View>
                </View>
              </View>
              <Sparkline width={92} height={36} positive={isUp} color={isUp ? "#86efac" : "#fda4af"} />
            </View>

            <View style={s.heroSubRow}>
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Gold</Text>
                <Text style={s.heroSubValue}>{formatINR(summary?.gold_value ?? 0, { compact: true })}</Text>
              </View>
              <View style={s.heroDivider} />
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Invested</Text>
                <Text style={s.heroSubValue}>{formatINR(summary?.portfolio_invested ?? 0, { compact: true })}</Text>
              </View>
              <View style={s.heroDivider} />
              <View style={s.heroSubItem}>
                <Text style={s.heroSubLabel}>Returns</Text>
                <Text style={[s.heroSubValue, { color: isUp ? "#86efac" : "#fda4af" }]}>
                  {isUp ? "+" : ""}{formatINR(totalReturn, { compact: true })}
                </Text>
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
              style={s.quickItem}
              testID={`quick-action-${a.label.toLowerCase().replace(" ", "-")}`}
            >
              <View style={[s.quickIcon, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <LinearGradient
                  colors={[a.color + "33", a.color + "11"]}
                  style={s.quickIconGrad}
                  start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                >
                  <a.icon color={a.color} size={22} />
                </LinearGradient>
              </View>
              <Text style={[s.quickLabel, { color: palette.textPrimary }]}>{a.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Rewards CTA */}
        <Pressable onPress={() => router.push("/rewards")} testID="rewards-cta">
          <LinearGradient
            colors={[palette.warning + "20", palette.surface]}
            start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
            style={[s.rewardsCard, { borderColor: palette.warning + "40" }]}
          >
            <View style={[s.rewardsIcon, { backgroundColor: palette.warning + "25" }]}>
              <Gift color={palette.warning} size={24} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.rewardsTitle, { color: palette.textPrimary }]}>Rewards & Cashback</Text>
              <Text style={[s.rewardsSubtitle, { color: palette.textSecondary }]}>
                Earn points on every transaction
              </Text>
            </View>
            <ChevronRight color={palette.textSecondary} size={20} />
          </LinearGradient>
        </Pressable>

        {/* Trending stocks */}
        <View style={s.sectionHeader}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Market Movers</Text>
          <Pressable onPress={() => router.push("/(tabs)/invest")} testID="view-all-stocks">
            <Text style={[s.viewAll, { color: palette.primary }]}>View all ›</Text>
          </Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.hScroll}>
          {(summary?.trending_stocks ?? []).map((stk) => {
            const up = stk.change >= 0;
            return (
              <View
                key={stk.id}
                style={[s.stockCard, { backgroundColor: palette.surface, borderColor: palette.border }, shadow({ color: palette.cardShadow, opacity: 1, radius: 8, offsetY: 4 })]}
              >
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <Text style={[s.stockSym, { color: palette.textPrimary }]}>{stk.symbol}</Text>
                  {stk.live ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
                      <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: palette.success }} />
                      <Text style={{ fontSize: 9, fontWeight: "800", color: palette.success, letterSpacing: 0.5 }}>LIVE</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={[s.stockName, { color: palette.textSecondary }]} numberOfLines={1}>{stk.name}</Text>
                <Sparkline width={120} height={32} positive={up} strokeWidth={1.8} />
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
                  <Text style={[s.stockPrice, { color: palette.textPrimary }]}>{formatINR(stk.price)}</Text>
                  <Text style={{ color: up ? palette.success : palette.danger, fontSize: 12, fontWeight: "800" }}>
                    {up ? "▲" : "▼"} {Math.abs(stk.change).toFixed(2)}%
                  </Text>
                </View>
              </View>
            );
          })}
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
            <Text style={[s.viewAll, { color: palette.primary }]}>View all ›</Text>
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
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  greeting: { fontSize: 10, fontWeight: "800", letterSpacing: 1.4 },
  name: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3, marginTop: 2 },
  bellBtn: { padding: 10, borderRadius: 14, borderWidth: 1, position: "relative" },
  bellDot: { position: "absolute", top: 8, right: 8, width: 8, height: 8, borderRadius: 4 },

  demoBanner: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#FEF3C7", borderColor: "#FBBF24", borderWidth: 1, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 10 },
  demoBannerTitle: { color: "#92400E", fontSize: 13, fontWeight: "800" },
  demoBannerBody: { color: "#92400E", fontSize: 11, fontWeight: "500", opacity: 0.9 },
  demoBadge: { backgroundColor: "#F59E0B", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  demoBadgeText: { color: "#fff", fontSize: 11, fontWeight: "800" },

  heroCard: { borderRadius: 28, padding: 20, gap: 14, overflow: "hidden", position: "relative" },
  heroBullWrap: { position: "absolute", right: -30, top: -20, opacity: 0.18, transform: [{ rotate: "12deg" }] },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  heroLabel: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontWeight: "800", letterSpacing: 1.6 },
  heroAmount: { color: "#FFFFFF", fontSize: 36, fontWeight: "800", letterSpacing: -1.2 },
  portfolioStrip: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "rgba(15,23,42,0.35)", borderRadius: 16, padding: 12, marginTop: 4 },
  portfolioLabel: { color: "rgba(255,255,255,0.75)", fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  portfolioValue: { color: "#fff", fontSize: 20, fontWeight: "800", letterSpacing: -0.5 },
  portfolioBadge: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: "rgba(255,255,255,0.12)", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  portfolioPct: { fontSize: 11, fontWeight: "800" },
  heroSubRow: { flexDirection: "row", backgroundColor: "rgba(255,255,255,0.12)", borderRadius: 14, padding: 12, marginTop: 2 },
  heroSubItem: { flex: 1, alignItems: "flex-start" },
  heroSubLabel: { color: "rgba(255,255,255,0.8)", fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  heroSubValue: { color: "#FFFFFF", fontSize: 14, fontWeight: "800", marginTop: 3 },
  heroDivider: { width: 1, backgroundColor: "rgba(255,255,255,0.25)" },

  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 4 },
  sectionTitle: { fontSize: 17, fontWeight: "800", letterSpacing: -0.3 },
  viewAll: { fontSize: 13, fontWeight: "700" },

  quickGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  quickItem: { width: "22%", alignItems: "center", gap: 8 },
  quickIcon: { width: 60, height: 60, borderRadius: 18, borderWidth: 1, padding: 6 },
  quickIconGrad: { flex: 1, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  quickLabel: { fontSize: 11, fontWeight: "700", textAlign: "center" },

  rewardsCard: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, borderRadius: 20, borderWidth: 1 },
  bannerScroll: { gap: 12, paddingRight: 4 },
  bannerCard: { width: 280, padding: 16, borderRadius: 20, gap: 6, overflow: "hidden" },
  bannerTitle: { color: "#fff", fontSize: 16, fontWeight: "800", letterSpacing: -0.3 },
  bannerSubtitle: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontWeight: "500" },
  bannerCta: { alignSelf: "flex-start", marginTop: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, backgroundColor: "rgba(255,255,255,0.2)" },
  bannerCtaTxt: { color: "#fff", fontSize: 11, fontWeight: "800", letterSpacing: 0.4 },
  rewardsIcon: { padding: 12, borderRadius: 14 },
  rewardsTitle: { fontSize: 15, fontWeight: "800" },
  rewardsSubtitle: { fontSize: 12, marginTop: 2 },

  hScroll: { gap: 12, paddingRight: 4 },
  stockCard: { width: 160, gap: 6, borderRadius: 18, padding: 14, borderWidth: 1 },
  stockSym: { fontSize: 14, fontWeight: "800" },
  stockName: { fontSize: 11, fontWeight: "500" },
  stockPrice: { fontSize: 15, fontWeight: "800" },

  fundRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  fundIcon: { padding: 10, borderRadius: 12 },
  fundName: { fontSize: 14, fontWeight: "800" },
  fundMeta: { fontSize: 11, marginTop: 2 },
  fundReturns: { fontSize: 14, fontWeight: "800" },

  txRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  txIcon: { padding: 10, borderRadius: 12 },
  txDesc: { fontSize: 14, fontWeight: "700" },
  txMeta: { fontSize: 11, marginTop: 2 },
  txAmount: { fontSize: 14, fontWeight: "800" },
});
