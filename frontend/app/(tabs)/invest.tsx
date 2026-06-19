import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { TrendingUp, Coins, PiggyBank, Landmark, BarChart3, ChevronRight, RefreshCw, Sparkles, Calculator } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";
import { BullLogo } from "@/src/components/BullLogo";
import { AnimatedCounter } from "@/src/components/AnimatedCounter";
import { Sparkline } from "@/src/components/Sparkline";
import { formatINR } from "@/src/utils/format";
import { shadow } from "@/src/utils/shadow";

const TABS = [
  { id: "portfolio", label: "Portfolio" },
  { id: "mf", label: "Mutual Funds" },
  { id: "stocks", label: "Stocks" },
  { id: "gold", label: "Gold" },
  { id: "fd", label: "Fixed Deposit" },
  { id: "govt", label: "Govt Schemes" },
];

export default function InvestTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [active, setActive] = useState("portfolio");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setData(null);
    try {
      if (active === "portfolio") {
        const { data } = await api.get("/invest/portfolio");
        setData(data);
      } else if (active === "mf") {
        const { data } = await api.get("/invest/mutual-funds");
        setData(data);
      } else if (active === "stocks") {
        const { data } = await api.get("/invest/stocks");
        setData(data);
      } else if (active === "gold") {
        const { data } = await api.get("/invest/gold-price");
        setData(data);
      } else if (active === "fd") {
        const { data } = await api.get("/invest/fixed-deposits");
        setData(data);
      } else if (active === "govt") {
        const { data } = await api.get("/invest/govt-schemes");
        setData(data);
      }
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, [active]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const buy = (item: any, type: string, name: string) =>
    router.push({ pathname: "/invest/buy", params: { id: item.id, name, type } } as any);

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <View style={[s.hdr, { paddingTop: insets.top + 8 }]}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <BullLogo size={32} />
          <Text style={[s.title, { color: palette.textPrimary }]}>Investments</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabsRow}>
          {TABS.map((t) => (
            <Pressable
              key={t.id}
              onPress={() => setActive(t.id)}
              style={[
                s.chip,
                {
                  backgroundColor: active === t.id ? palette.primary : palette.surface,
                  borderColor: active === t.id ? palette.primary : palette.border,
                },
              ]}
              testID={`invest-tab-${t.id}`}
            >
              <Text style={{
                color: active === t.id ? "#fff" : palette.textPrimary,
                fontSize: 13, fontWeight: "700",
              }}>{t.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <ScrollView
        contentContainerStyle={[s.scroll, { paddingBottom: 110 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {loading ? <ActivityIndicator color={palette.primary} style={{ marginTop: 30 }} /> : null}

        {!loading && active === "portfolio" && (
          <>
            {/* Investment Calculator CTA */}
            <Pressable onPress={() => router.push("/invest/calculator")} testID="calculator-cta">
              <LinearGradient
                colors={["#0EA5E9", "#2563EB", "#0F172A"]}
                start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                style={[s.calcCta, shadow({ color: "#0EA5E9", opacity: 0.3, radius: 14, offsetY: 6, elevation: 4 })]}
              >
                <View style={s.calcCtaIcon}>
                  <Calculator color="#fff" size={22} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.calcCtaTitle}>📊 Investment Calculator</Text>
                  <Text style={s.calcCtaSub}>Plan your future returns instantly</Text>
                </View>
                <View style={s.calcCtaBtn}>
                  <Text style={s.calcCtaBtnText}>Open</Text>
                  <ChevronRight color="#0EA5E9" size={16} />
                </View>
              </LinearGradient>
            </Pressable>

            {/* AI Investment Coach teaser */}
            <Pressable onPress={() => router.push("/invest/ai-coach")} testID="ai-coach-teaser">
              <LinearGradient
                colors={["#7C3AED", "#EC4899", "#F59E0B"]}
                start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                style={[s.aiTeaser, shadow({ color: "#7C3AED", opacity: 0.25, radius: 14, offsetY: 6, elevation: 4 })]}
              >
                <View style={s.aiTeaserIcon}>
                  <Sparkles color="#fff" size={20} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.aiTeaserTitle}>AI Investment Coach</Text>
                  <Text style={s.aiTeaserSub}>
                    Personalised Buy/Hold/Sell calls powered by Claude Sonnet 4.6
                  </Text>
                </View>
                <ChevronRight color="#fff" size={20} />
              </LinearGradient>
            </Pressable>

            <LinearGradient
              colors={["#0F172A", "#0EA5E9", "#38BDF8"]}
              start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
              locations={[0, 0.65, 1]}
              style={s.portCard}
              testID="investment-portfolio-chart"
            >
              <View style={s.heroBullWrap} pointerEvents="none">
                <BullLogo size={130} variant="flat" />
              </View>
              <Text style={s.portLabel}>CURRENT PORTFOLIO VALUE</Text>
              <AnimatedCounter value={data?.total_current ?? 0} style={s.portValue} />
              <View style={s.portStats}>
                <View style={s.portStat}>
                  <Text style={s.portStatLabel}>Invested</Text>
                  <Text style={s.portStatValue}>{formatINR(data?.total_invested ?? 0, { compact: true })}</Text>
                </View>
                <View style={s.portStat}>
                  <Text style={s.portStatLabel}>Returns</Text>
                  <Text style={[s.portStatValue, { color: (data?.returns_pct ?? 0) >= 0 ? "#86efac" : "#fda4af" }]}>
                    {(data?.returns_pct ?? 0) >= 0 ? "+" : ""}{(data?.returns_pct ?? 0).toFixed(2)}%
                  </Text>
                </View>
                <View style={{ width: 80 }}>
                  <Sparkline width={80} height={36} positive={(data?.returns_pct ?? 0) >= 0} color={(data?.returns_pct ?? 0) >= 0 ? "#86efac" : "#fda4af"} />
                </View>
              </View>
            </LinearGradient>
            <Text style={[s.section, { color: palette.textPrimary }]}>Asset Allocation</Text>
            {Object.entries((data?.by_type ?? {}) as Record<string, any>).map(([k, v]) => (
              <Card key={k} style={s.row}>
                <View style={{ flex: 1 }}>
                  <Text style={[s.rowTitle, { color: palette.textPrimary }]}>{kPretty(k)}</Text>
                  <Text style={[s.rowMeta, { color: palette.textSecondary }]}>Invested {formatINR(v.invested)}</Text>
                </View>
                <Text style={[s.rowValue, { color: palette.textPrimary }]}>{formatINR(v.current)}</Text>
              </Card>
            ))}
            <Text style={[s.section, { color: palette.textPrimary }]}>Holdings</Text>
            {(data?.holdings ?? []).length === 0 ? (
              <Card><Text style={{ color: palette.textSecondary, textAlign: "center" }}>No holdings yet. Start investing!</Text></Card>
            ) : (data?.holdings ?? []).map((h: any) => (
              <Card key={h.holding_id} style={s.row}>
                <View style={{ flex: 1 }}>
                  <Text style={[s.rowTitle, { color: palette.textPrimary }]} numberOfLines={1}>{h.asset_name}</Text>
                  <Text style={[s.rowMeta, { color: palette.textSecondary }]}>
                    {kPretty(h.asset_type)} • Invested {formatINR(h.amount)}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[s.rowValue, { color: palette.textPrimary }]}>{formatINR(h.current_value)}</Text>
                  <Text style={{ fontSize: 11, fontWeight: "700", color: h.returns_pct >= 0 ? palette.success : palette.danger }}>
                    {h.returns_pct >= 0 ? "+" : ""}{h.returns_pct}%
                  </Text>
                </View>
              </Card>
            ))}
          </>
        )}

        {!loading && active === "mf" && Array.isArray(data) && data.map((f: any) => (
          <Pressable key={f.id} onPress={() => buy(f, "mutual_fund", f.name)} testID={`mf-${f.id}`}>
            <Card style={s.row}>
              <View style={[s.iconWrap, { backgroundColor: palette.primary + "1A" }]}>
                <TrendingUp color={palette.primary} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.rowTitle, { color: palette.textPrimary }]} numberOfLines={1}>{f.name}</Text>
                <Text style={[s.rowMeta, { color: palette.textSecondary }]}>{f.category} • NAV {formatINR(f.nav)} • {f.risk}</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={{ color: palette.success, fontWeight: "800", fontSize: 14 }}>+{f.returns_1y}%</Text>
                <Text style={[s.rowMeta, { color: palette.textMuted }]}>1Y</Text>
              </View>
            </Card>
          </Pressable>
        ))}

        {!loading && active === "stocks" && Array.isArray(data) && (
          <View style={s.stocksHeader}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: palette.success }} />
              <Text style={[s.liveLabel, { color: palette.textSecondary }]}>
                {data.filter((s: any) => s.live).length}/{data.length} live • BSE
              </Text>
            </View>
            <Pressable
              onPress={() => load(true)}
              style={[s.refreshBtn, { backgroundColor: palette.primary + "1A", borderColor: palette.primary + "40" }]}
              testID="stocks-refresh-btn"
            >
              <RefreshCw color={palette.primary} size={14} />
              <Text style={{ color: palette.primary, fontWeight: "700", fontSize: 12 }}>Refresh</Text>
            </Pressable>
          </View>
        )}

        {!loading && active === "stocks" && Array.isArray(data) && data.map((stk: any) => (
          <Pressable key={stk.id} onPress={() => buy(stk, "stock", stk.name)} testID={`stk-${stk.id}`}>
            <Card style={s.row}>
              <View style={[s.iconWrap, { backgroundColor: palette.secondary + "1A" }]}>
                <BarChart3 color={palette.secondary} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={[s.rowTitle, { color: palette.textPrimary }]}>{stk.symbol}</Text>
                  {stk.live ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: palette.success + "1A", paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
                      <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: palette.success }} />
                      <Text style={{ fontSize: 9, fontWeight: "800", color: palette.success, letterSpacing: 0.5 }}>LIVE</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={[s.rowMeta, { color: palette.textSecondary }]} numberOfLines={1}>{stk.name}</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={[s.rowValue, { color: palette.textPrimary }]}>{formatINR(stk.price)}</Text>
                <Text style={{ fontSize: 12, fontWeight: "700", color: stk.change >= 0 ? palette.success : palette.danger }}>
                  {stk.change >= 0 ? "▲" : "▼"} {Math.abs(stk.change).toFixed(2)}%
                </Text>
              </View>
            </Card>
          </Pressable>
        ))}

        {!loading && active === "gold" && data && (
          <Card style={{ gap: 12 }}>
            <View style={[s.iconWrap, { backgroundColor: palette.warning + "1A", alignSelf: "flex-start" }]}>
              <Coins color={palette.warning} size={26} />
            </View>
            <Text style={[s.rowTitle, { color: palette.textPrimary, fontSize: 20 }]}>Digital Gold</Text>
            <Text style={[s.rowMeta, { color: palette.textSecondary }]}>Live price • 24K certified</Text>
            <Text style={{ fontSize: 32, fontWeight: "800", color: palette.textPrimary, letterSpacing: -0.5 }}>
              {formatINR(data.price_per_gram)} / g
            </Text>
            <Pressable
              onPress={() => buy({ id: "gold" }, "gold", "Digital Gold")}
              style={[s.cta, { backgroundColor: palette.primary }]}
              testID="gold-buy-btn"
            >
              <Text style={{ color: "#fff", fontWeight: "800" }}>Buy Gold</Text>
            </Pressable>
          </Card>
        )}

        {!loading && active === "fd" && Array.isArray(data) && data.map((fd: any) => (
          <Pressable key={fd.id} onPress={() => buy(fd, "fd", fd.name)} testID={`fd-${fd.id}`}>
            <Card style={s.row}>
              <View style={[s.iconWrap, { backgroundColor: palette.success + "1A" }]}>
                <PiggyBank color={palette.success} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.rowTitle, { color: palette.textPrimary }]}>{fd.name}</Text>
                <Text style={[s.rowMeta, { color: palette.textSecondary }]}>{fd.tenure_months} months tenure</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={{ color: palette.success, fontWeight: "800", fontSize: 16 }}>{fd.interest_rate}%</Text>
                <Text style={[s.rowMeta, { color: palette.textMuted }]}>p.a.</Text>
              </View>
            </Card>
          </Pressable>
        ))}

        {!loading && active === "govt" && Array.isArray(data) && data.map((g: any) => (
          <Pressable key={g.id} onPress={() => buy(g, "govt", g.name)} testID={`govt-${g.id}`}>
            <Card style={s.row}>
              <View style={[s.iconWrap, { backgroundColor: palette.primary + "1A" }]}>
                <Landmark color={palette.primary} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.rowTitle, { color: palette.textPrimary }]} numberOfLines={1}>{g.name}</Text>
                <Text style={[s.rowMeta, { color: palette.textSecondary }]}>{g.tenure}</Text>
              </View>
              <Text style={{ color: palette.success, fontWeight: "800", fontSize: 16 }}>{g.rate}%</Text>
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function kPretty(k: string) {
  const m: Record<string, string> = {
    mutual_fund: "Mutual Funds", stock: "Stocks", gold: "Gold", fd: "Fixed Deposits", govt: "Govt Schemes",
  };
  return m[k] || k;
}

const s = StyleSheet.create({
  root: { flex: 1 },
  hdr: { paddingHorizontal: 16, paddingBottom: 8 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5, marginBottom: 12 },
  tabsRow: { gap: 8, paddingRight: 16 },
  chip: { paddingHorizontal: 14, height: 36, borderRadius: 18, borderWidth: 1, justifyContent: "center", flexShrink: 0 },
  scroll: { paddingHorizontal: 16, paddingTop: 12, gap: 10 },
  portCard: { borderRadius: 28, padding: 22, gap: 8, overflow: "hidden", position: "relative" },
  aiTeaser: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 20 },
  calcCta: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 20 },
  calcCtaIcon: { width: 42, height: 42, borderRadius: 12, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  calcCtaTitle: { color: "#fff", fontSize: 15, fontWeight: "800", letterSpacing: -0.2 },
  calcCtaSub: { color: "rgba(255,255,255,0.9)", fontSize: 11, fontWeight: "600", marginTop: 2 },
  calcCtaBtn: { flexDirection: "row", alignItems: "center", gap: 2, backgroundColor: "#fff", paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  calcCtaBtnText: { color: "#0EA5E9", fontWeight: "800", fontSize: 12 },
  aiTeaserIcon: { width: 38, height: 38, borderRadius: 12, backgroundColor: "rgba(255,255,255,0.2)", alignItems: "center", justifyContent: "center" },
  aiTeaserTitle: { color: "#fff", fontSize: 15, fontWeight: "800" },
  aiTeaserSub: { color: "rgba(255,255,255,0.92)", fontSize: 11, fontWeight: "600", marginTop: 2 },
  heroBullWrap: { position: "absolute", right: -28, top: -18, opacity: 0.16, transform: [{ rotate: "12deg" }] },
  portLabel: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  portValue: { color: "#fff", fontSize: 34, fontWeight: "800", letterSpacing: -1, marginTop: 2 },
  portStats: { flexDirection: "row", marginTop: 8, backgroundColor: "rgba(255,255,255,0.12)", borderRadius: 14, padding: 12, gap: 16, alignItems: "center" },
  portStat: { flex: 1 },
  portStatLabel: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontWeight: "600" },
  portStatValue: { color: "#fff", fontSize: 16, fontWeight: "800", marginTop: 2 },
  section: { fontSize: 16, fontWeight: "800", marginTop: 8, letterSpacing: -0.3 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  iconWrap: { padding: 10, borderRadius: 12 },
  rowTitle: { fontSize: 14, fontWeight: "700" },
  rowMeta: { fontSize: 11, marginTop: 2 },
  rowValue: { fontSize: 14, fontWeight: "800" },
  cta: { paddingVertical: 14, borderRadius: 14, alignItems: "center", marginTop: 8 },
  stocksHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  liveLabel: { fontSize: 12, fontWeight: "600", letterSpacing: 0.3 },
  refreshBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1 },
});
