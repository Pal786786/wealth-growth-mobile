/**
 * Mutual Funds Hub — landing screen with portfolio summary, quick actions,
 * top rated funds, and shortcut to Explorer / SIPs / Goals / Portfolio / AI Advisor.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ArrowLeft, Search, ChevronRight, PieChart, Repeat, Target,
  Sparkles, Star, TrendingUp, TrendingDown, GitCompare, Bookmark,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFFund, MFPortfolio, fmtINR, CATEGORIES } from "@/src/api/mutualFunds";
import { shadow } from "@/src/utils/shadow";

const HERO_LIGHT = ["#6366F1", "#4F46E5", "#312E81"] as const;
const HERO_DARK = ["#4338CA", "#312E81", "#0F172A"] as const;

export default function MutualFundsHome() {
  const { palette, mode } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [portfolio, setPortfolio] = useState<MFPortfolio | null>(null);
  const [topFunds, setTopFunds] = useState<MFFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, f] = await Promise.all([
        mfApi.portfolio(),
        mfApi.funds({ sort: "rating_desc", limit: 6 }),
      ]);
      setPortfolio(p);
      setTopFunds(f.items);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const grad = mode === "dark" ? HERO_DARK : HERO_LIGHT;
  const pnlUp = (portfolio?.unrealized_pnl ?? 0) >= 0;

  if (loading) {
    return (
      <View style={[s.root, { backgroundColor: palette.background, justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator color={palette.primary} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={[s.root, { backgroundColor: palette.background }]}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120, paddingHorizontal: 16, gap: 14 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      testID="mf-home-scroll"
    >
      <View style={s.header}>
        <Pressable onPress={() => router.back()} style={[s.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="mf-back">
          <ArrowLeft color={palette.textPrimary} size={20} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.pageEyebrow, { color: palette.textSecondary }]}>WEALTH · MUTUAL FUNDS</Text>
          <Text style={[s.pageTitle, { color: palette.textPrimary }]}>MF & SIP</Text>
        </View>
        <Pressable onPress={() => router.push("/mutual-funds/explore")} style={[s.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="mf-search-btn">
          <Search color={palette.textPrimary} size={20} />
        </Pressable>
      </View>

      {/* Hero portfolio card */}
      <LinearGradient colors={grad as unknown as [string, string, string]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
        <Text style={s.heroLabel}>PORTFOLIO VALUE</Text>
        <Text style={s.heroValue}>{fmtINR(portfolio?.current_value ?? 0)}</Text>
        <View style={s.heroChip}>
          {pnlUp ? <TrendingUp size={14} color="#86efac" /> : <TrendingDown size={14} color="#fda4af" />}
          <Text style={[s.heroChipTxt, { color: pnlUp ? "#86efac" : "#fda4af" }]}>
            {pnlUp ? "+" : ""}{fmtINR(portfolio?.unrealized_pnl || 0)} · {(portfolio?.unrealized_pnl_pct ?? 0).toFixed(2)}%
          </Text>
        </View>
        <View style={s.miniRow}>
          <MiniStat label="Invested" value={fmtINR(portfolio?.total_invested ?? 0)} />
          <MiniStat label="XIRR" value={portfolio?.xirr_pct != null ? `${portfolio.xirr_pct.toFixed(2)}%` : "—"} />
          <MiniStat label="Funds" value={String(portfolio?.count_funds ?? 0)} />
        </View>
        <View style={{ flexDirection: "row", gap: 10, marginTop: 6 }}>
          <Pressable onPress={() => router.push("/mutual-funds/explore")} style={[s.ctaBtn, { backgroundColor: "#fff" }]} testID="mf-invest-cta">
            <Text style={[s.ctaTxt, { color: "#312E81" }]}>Invest Now</Text>
          </Pressable>
          <Pressable onPress={() => router.push("/mutual-funds/portfolio")} style={[s.ctaBtn, { backgroundColor: "rgba(15,23,42,0.55)" }]} testID="mf-portfolio-cta">
            <Text style={[s.ctaTxt, { color: "#fff" }]}>View Portfolio</Text>
          </Pressable>
        </View>
      </LinearGradient>

      {/* Quick tiles */}
      <View style={s.tilesRow}>
        <QuickTile icon={PieChart}    label="Portfolio" testID="tile-portfolio" onPress={() => router.push("/mutual-funds/portfolio")} palette={palette} />
        <QuickTile icon={Repeat}      label="SIPs"      testID="tile-sips"      onPress={() => router.push("/mutual-funds/sips")}      palette={palette} />
        <QuickTile icon={Target}      label="Goals"     testID="tile-goals"     onPress={() => router.push("/mutual-funds/goals")}     palette={palette} />
      </View>
      <View style={s.tilesRow}>
        <QuickTile icon={GitCompare}  label="Compare"   testID="tile-compare"   onPress={() => router.push("/mutual-funds/compare")}   palette={palette} />
        <QuickTile icon={Bookmark}    label="Watchlist" testID="tile-watchlist" onPress={() => router.push("/mutual-funds/watchlist")} palette={palette} />
        <QuickTile icon={Sparkles}    label="AI Advisor" testID="tile-advisor"  onPress={() => router.push("/mutual-funds/advisor")}   palette={palette} />
      </View>

      {/* Categories */}
      <View style={s.sectionHead}>
        <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Explore by Category</Text>
        <Pressable onPress={() => router.push("/mutual-funds/explore")} testID="mf-see-all-cats">
          <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>See all ›</Text>
        </Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingRight: 16 }}>
        {CATEGORIES.map((c) => (
          <Pressable
            key={c.key}
            onPress={() => router.push({ pathname: "/mutual-funds/explore", params: { category: c.key } })}
            style={[s.catChip, { backgroundColor: palette.surface, borderColor: palette.border }]}
            testID={`cat-${c.key}`}
          >
            <View style={[s.catBubble, { backgroundColor: c.color + "22" }]}>
              <Text style={{ fontSize: 20 }}>{c.emoji}</Text>
            </View>
            <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{c.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {/* Top rated funds */}
      <View style={s.sectionHead}>
        <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>⭐ Top Rated</Text>
        <Pressable onPress={() => router.push({ pathname: "/mutual-funds/explore", params: { sort: "rating_desc" } })} testID="mf-see-all-top">
          <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>See all ›</Text>
        </Pressable>
      </View>
      {topFunds.map((f) => (
        <Pressable
          key={f.fund_id}
          onPress={() => router.push({ pathname: "/mutual-funds/fund/[id]", params: { id: f.fund_id } })}
          style={[s.fundRow, { backgroundColor: palette.surface, borderColor: palette.border }, shadow({ color: palette.cardShadow, opacity: 0.6, radius: 4, offsetY: 2 })]}
          testID={`mf-fund-row-${f.fund_id}`}
        >
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={[s.fundName, { color: palette.textPrimary }]} numberOfLines={2}>{f.name}</Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>{f.amc}</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 2 }}>
                {Array.from({ length: Math.round(f.star_rating) }).map((_, i) => (
                  <Star key={i} color="#F59E0B" fill="#F59E0B" size={10} />
                ))}
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 3 }}>
              <View style={[s.catTiny, { backgroundColor: palette.chipBg }]}>
                <Text style={{ color: palette.textSecondary, fontSize: 9, fontWeight: "800", letterSpacing: 0.6 }}>{(f.category || "").toUpperCase()}</Text>
              </View>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>Exp {f.expense_ratio}%</Text>
            </View>
          </View>
          <View style={{ alignItems: "flex-end", gap: 3 }}>
            <Text style={{ color: (f.returns?.y1 ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 15, fontWeight: "800" }}>
              {(f.returns?.y1 ?? 0) >= 0 ? "+" : ""}{(f.returns?.y1 ?? 0).toFixed(2)}%
            </Text>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>1Y RETURNS</Text>
            <ChevronRight color={palette.textMuted} size={16} />
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 9, fontWeight: "800", letterSpacing: 1 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: "#fff", fontSize: 13, fontWeight: "800", marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function QuickTile({ icon: Icon, label, onPress, palette, testID }: any) {
  return (
    <Pressable onPress={onPress} style={[s.tile, { backgroundColor: palette.surface, borderColor: palette.border }]} testID={testID}>
      <View style={[s.tileIcon, { backgroundColor: palette.primary + "1A" }]}>
        <Icon color={palette.primary} size={22} />
      </View>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", gap: 10 },
  iconBtn: { padding: 8, borderRadius: 14, borderWidth: 1 },
  pageEyebrow: { fontSize: 10, fontWeight: "800", letterSpacing: 1.4 },
  pageTitle: { fontSize: 22, fontWeight: "800", letterSpacing: -0.4 },
  hero: { borderRadius: 24, padding: 18, gap: 8 },
  heroLabel: { color: "rgba(255,255,255,0.7)", fontSize: 10, fontWeight: "800", letterSpacing: 1.4 },
  heroValue: { color: "#fff", fontSize: 34, fontWeight: "800", letterSpacing: -1, marginTop: 2 },
  heroChip: { alignSelf: "flex-start", backgroundColor: "rgba(15,23,42,0.35)", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, flexDirection: "row", alignItems: "center", gap: 4 },
  heroChipTxt: { fontSize: 12, fontWeight: "800" },
  miniRow: { flexDirection: "row", gap: 12, marginTop: 6, backgroundColor: "rgba(15,23,42,0.3)", padding: 12, borderRadius: 12 },
  ctaBtn: { flex: 1, paddingVertical: 12, borderRadius: 14, alignItems: "center" },
  ctaTxt: { fontSize: 13, fontWeight: "800", letterSpacing: 0.3 },
  tilesRow: { flexDirection: "row", gap: 10 },
  tile: { flex: 1, borderRadius: 16, borderWidth: 1, padding: 14, alignItems: "center", gap: 6 },
  tileIcon: { padding: 10, borderRadius: 12 },
  catChip: { padding: 10, borderRadius: 14, borderWidth: 1, alignItems: "center", gap: 6, width: 84 },
  catBubble: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6, marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: "800", letterSpacing: -0.3 },
  fundRow: { flexDirection: "row", gap: 12, padding: 14, borderRadius: 14, borderWidth: 1, alignItems: "center" },
  fundName: { fontSize: 13, fontWeight: "800", letterSpacing: -0.2 },
  catTiny: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
});
