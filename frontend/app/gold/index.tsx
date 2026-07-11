/**
 * Gold Dashboard — premium fintech home for the Gold module.
 * Live quote, holdings, P/L, quick Buy/Sell via TradeBottomSheet, mini chart.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, TextInput, Platform,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ArrowLeft, TrendingUp, TrendingDown, History, ChevronRight, Info,
  Coins, LineChart as LineChartIcon, PieChart, Sparkles, AlertTriangle,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { goldApi, GoldHoldings, GoldQuote, GoldChartPoint, GoldUserConfig, formatGrams, formatMoney } from "@/src/api/gold";
import { api } from "@/src/api/client";
import { FinancialChart } from "@/src/components/FinancialChart";
import { TradeBottomSheet, SheetState } from "@/src/components/TradeBottomSheet";
import { Card } from "@/src/components/Card";
import { shadow } from "@/src/utils/shadow";

const GOLD_GRAD_LIGHT = ["#F59E0B", "#D97706", "#78350F"] as const;
const GOLD_GRAD_DARK = ["#B45309", "#78350F", "#0F172A"] as const;

export default function GoldDashboard() {
  const { palette, mode } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [quote, setQuote] = useState<GoldQuote | null>(null);
  const [holdings, setHoldings] = useState<GoldHoldings | null>(null);
  const [cfg, setCfg] = useState<GoldUserConfig | null>(null);
  const [wallet, setWallet] = useState<number>(0);
  const [chart, setChart] = useState<GoldChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Sheet state
  const [openSheet, setOpenSheet] = useState<null | "buy" | "sell">(null);
  const [sheetState, setSheetState] = useState<SheetState>("idle");
  const [sheetError, setSheetError] = useState<string>("");
  const [amountInput, setAmountInput] = useState<string>("");
  const [gramsInput, setGramsInput] = useState<string>("");
  const [buyMode, setBuyMode] = useState<"amount" | "grams">("amount");

  const load = useCallback(async () => {
    try {
      const [q, h, c, ch, w] = await Promise.all([
        goldApi.quote(),
        goldApi.holdings(),
        goldApi.userConfig(),
        goldApi.chart("1D"),
        api.get("/wallet").then((r) => Number((r.data as any)?.balance || 0)).catch(() => 0),
      ]);
      setQuote(q);
      setHoldings(h);
      setCfg(c);
      setWallet(w);
      setChart(ch.points || []);
    } catch (e) {
      // logged by axios interceptor
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll quote every 8s while dashboard is visible
  useEffect(() => {
    const id = setInterval(async () => {
      try { const q = await goldApi.quote(); setQuote(q); } catch {}
    }, 8000);
    return () => clearInterval(id);
  }, []);

  const onRefresh = () => { setRefreshing(true); load(); };

  const pnlUp = (holdings?.unrealized_pnl_inr ?? 0) >= 0;
  const dayUp = (holdings?.daily_gain_inr ?? 0) >= 0;
  const chartPoints = useMemo(
    () => chart.map((p) => ({ ts: p.quoted_at, value: p.mid })),
    [chart],
  );

  // ------- buy / sell handlers -------
  const buyPrice = quote?.buy_price ?? 0;
  const sellPrice = quote?.sell_price ?? 0;
  const estGrams = useMemo(() => {
    if (buyMode === "amount") {
      const a = parseFloat(amountInput || "0");
      return buyPrice > 0 ? a / buyPrice : 0;
    }
    return parseFloat(gramsInput || "0");
  }, [buyMode, amountInput, gramsInput, buyPrice]);

  const estAmount = useMemo(() => {
    if (buyMode === "amount") return parseFloat(amountInput || "0");
    return (parseFloat(gramsInput || "0") || 0) * buyPrice;
  }, [buyMode, amountInput, gramsInput, buyPrice]);

  const sellGrams = useMemo(() => parseFloat(gramsInput || "0") || 0, [gramsInput]);
  const sellProceeds = useMemo(() => sellGrams * sellPrice, [sellGrams, sellPrice]);
  const sellCost = useMemo(() => sellGrams * (holdings?.avg_buy_price ?? 0), [sellGrams, holdings?.avg_buy_price]);
  const sellPnl = useMemo(() => sellProceeds - sellCost, [sellProceeds, sellCost]);

  const openBuy = () => {
    setBuyMode("amount");
    setAmountInput("");
    setGramsInput("");
    setSheetError("");
    setSheetState("idle");
    setOpenSheet("buy");
  };
  const openSell = () => {
    setAmountInput("");
    setGramsInput("");
    setSheetError("");
    setSheetState("idle");
    setOpenSheet("sell");
  };

  const doBuy = async () => {
    const amt = Number((estAmount || 0).toFixed(2));
    if (!amt || amt < (cfg?.min_buy_inr ?? 10)) {
      setSheetError(`Minimum purchase is ${formatMoney(cfg?.min_buy_inr ?? 10)}`);
      setSheetState("error");
      return;
    }
    if (amt > (cfg?.max_buy_inr ?? 200000)) {
      setSheetError(`Maximum purchase is ${formatMoney(cfg?.max_buy_inr ?? 200000)}`);
      setSheetState("error");
      return;
    }
    if (amt > wallet) {
      setSheetError(`Insufficient wallet balance (${formatMoney(wallet)})`);
      setSheetState("error");
      return;
    }
    setSheetState("submitting");
    try {
      const key = `gold-buy-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await goldApi.buy(amt, key);
      await load();
      setSheetState("success");
    } catch (e: any) {
      setSheetError(e?.response?.data?.detail || e?.message || "Unable to complete purchase");
      setSheetState("error");
    }
  };

  const doSell = async () => {
    if (!sellGrams || sellGrams <= 0) {
      setSheetError("Enter grams to sell");
      setSheetState("error");
      return;
    }
    if (sellGrams > (holdings?.grams ?? 0)) {
      setSheetError(`Only ${formatGrams(holdings?.grams ?? 0)} available`);
      setSheetState("error");
      return;
    }
    setSheetState("submitting");
    try {
      const key = `gold-sell-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await goldApi.sell(sellGrams, key);
      await load();
      setSheetState("success");
    } catch (e: any) {
      setSheetError(e?.response?.data?.detail || e?.message || "Unable to complete sale");
      setSheetState("error");
    }
  };

  const grad = mode === "dark" ? GOLD_GRAD_DARK : GOLD_GRAD_LIGHT;

  if (loading) {
    return (
      <View style={[s.root, { backgroundColor: palette.background, justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator color={palette.primary} size="large" />
      </View>
    );
  }

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120, paddingHorizontal: 16, gap: 14 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={palette.primary} />}
        testID="gold-dashboard-scroll"
      >
        {/* Header */}
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={[s.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="gold-back">
            <ArrowLeft color={palette.textPrimary} size={20} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={[s.pageEyebrow, { color: palette.textSecondary }]}>DIGITAL GOLD · 999.9 PURE</Text>
            <Text style={[s.pageTitle, { color: palette.textPrimary }]}>Gold Investment</Text>
          </View>
          <Pressable onPress={() => router.push("/gold/history")} style={[s.iconBtn, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="gold-history-btn">
            <History color={palette.textPrimary} size={20} />
          </Pressable>
        </View>

        {/* Maintenance banner */}
        {quote?.maintenance_mode ? (
          <View style={[s.warnBanner, { backgroundColor: palette.warningBg, borderColor: palette.warning }]}>
            <AlertTriangle color={palette.warning} size={16} />
            <Text style={{ color: palette.warning, fontSize: 12, fontWeight: "700", flex: 1 }}>
              Gold trading is temporarily paused for maintenance.
            </Text>
          </View>
        ) : null}
        {quote && !quote.trading_open && !quote.maintenance_mode ? (
          <View style={[s.warnBanner, { backgroundColor: palette.warningBg, borderColor: palette.warning }]}>
            <Info color={palette.warning} size={16} />
            <Text style={{ color: palette.warning, fontSize: 12, fontWeight: "700", flex: 1 }}>
              Trading window closed ({cfg?.trading_hours?.open_utc || "—"}–{cfg?.trading_hours?.close_utc || "—"} UTC).
            </Text>
          </View>
        ) : null}

        {/* Hero — Live price + holdings */}
        <LinearGradient colors={grad as unknown as [string, string, string]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <View style={s.heroTop}>
            <View>
              <Text style={s.heroEyebrow}>LIVE PRICE / gram</Text>
              <Text style={s.heroPrice}>{formatMoney(quote?.mid_price ?? 0)}</Text>
              <View style={s.heroChangeRow}>
                {dayUp ? <TrendingUp color="#86efac" size={14} /> : <TrendingDown color="#fda4af" size={14} />}
                <Text style={[s.heroChange, { color: dayUp ? "#86efac" : "#fda4af" }]}>
                  {holdings?.daily_gain_pct != null ? `${dayUp ? "+" : ""}${holdings.daily_gain_pct.toFixed(2)}%` : "--"} · 24h
                </Text>
              </View>
            </View>
            <View style={s.providerBadge}>
              <Sparkles color="#fff" size={12} />
              <Text style={s.providerTxt}>{(quote?.provider || "").toUpperCase()}</Text>
            </View>
          </View>

          {/* Bid/Ask */}
          <View style={s.baRow}>
            <View style={s.baBox}>
              <Text style={s.baLbl}>BUY (ASK)</Text>
              <Text style={s.baVal}>{formatMoney(quote?.buy_price ?? 0)}</Text>
            </View>
            <View style={[s.baBox, { alignItems: "flex-end" }]}>
              <Text style={s.baLbl}>SELL (BID)</Text>
              <Text style={s.baVal}>{formatMoney(quote?.sell_price ?? 0)}</Text>
            </View>
          </View>

          {/* CTAs */}
          <View style={{ flexDirection: "row", gap: 10, marginTop: 6 }}>
            <Pressable
              onPress={openBuy}
              disabled={quote?.maintenance_mode || !quote?.trading_open}
              style={[s.ctaBtn, { backgroundColor: "#fff", opacity: quote?.maintenance_mode || !quote?.trading_open ? 0.5 : 1 }]}
              testID="gold-buy-btn"
            >
              <Text style={[s.ctaTxt, { color: "#78350F" }]}>Buy Gold</Text>
            </Pressable>
            <Pressable
              onPress={openSell}
              disabled={quote?.maintenance_mode || !quote?.trading_open || !(holdings?.grams || 0)}
              style={[s.ctaBtn, { backgroundColor: "rgba(15,23,42,0.65)", opacity: quote?.maintenance_mode || !quote?.trading_open || !(holdings?.grams || 0) ? 0.5 : 1 }]}
              testID="gold-sell-btn"
            >
              <Text style={[s.ctaTxt, { color: "#fff" }]}>Sell Gold</Text>
            </Pressable>
          </View>
        </LinearGradient>

        {/* Holdings summary card */}
        <Card style={{ padding: 16, gap: 12 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Coins color={palette.warning} size={16} />
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Your Holdings</Text>
          </View>
          <View style={s.holdRow}>
            <StatBlock label="Grams" value={formatGrams(holdings?.grams || 0)} palette={palette} />
            <StatBlock label="Value" value={formatMoney(holdings?.current_value_inr || 0)} palette={palette} />
          </View>
          <View style={s.holdRow}>
            <StatBlock label="Invested" value={formatMoney(holdings?.total_invested || 0)} palette={palette} />
            <StatBlock
              label="P/L"
              value={`${pnlUp ? "+" : ""}${formatMoney(holdings?.unrealized_pnl_inr || 0)}`}
              sub={`${pnlUp ? "+" : ""}${(holdings?.unrealized_pnl_pct || 0).toFixed(2)}%`}
              palette={palette}
              color={pnlUp ? palette.success : palette.danger}
            />
          </View>
          <View style={[s.avgRow, { backgroundColor: palette.chipBg }]}>
            <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>
              Avg. buy price
            </Text>
            <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>
              {formatMoney(holdings?.avg_buy_price || 0)} / g
            </Text>
          </View>
        </Card>

        {/* Live mini chart */}
        <View>
          <View style={s.sectionHeader}>
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Live Chart · 1D</Text>
            <Pressable onPress={() => router.push("/gold/chart")} testID="gold-open-chart">
              <Text style={{ color: palette.primary, fontSize: 12, fontWeight: "800" }}>Full Chart ›</Text>
            </Pressable>
          </View>
          <FinancialChart
            points={chartPoints}
            height={200}
            livePrice={quote?.mid_price ?? null}
            title="LIVE · GOLD / INR"
            showWindowSwitcher={false}
          />
        </View>

        {/* Quick links */}
        <View style={{ flexDirection: "row", gap: 10 }}>
          <QuickTile icon={LineChartIcon} label="Chart" onPress={() => router.push("/gold/chart")} palette={palette} testID="tile-chart" />
          <QuickTile icon={History} label="History" onPress={() => router.push("/gold/history")} palette={palette} testID="tile-history" />
          <QuickTile icon={PieChart} label="Analytics" onPress={() => router.push("/gold/analytics")} palette={palette} testID="tile-analytics" />
        </View>

        {/* Wallet + info */}
        <View style={[s.walletRow, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
          <View>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>WALLET BALANCE</Text>
            <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>{formatMoney(wallet)}</Text>
          </View>
          <Pressable onPress={() => router.push("/wallet/topup")} style={[s.addBtn, { backgroundColor: palette.primary }]} testID="gold-add-money">
            <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>+ Add Money</Text>
          </Pressable>
        </View>
      </ScrollView>

      {/* ===== BUY sheet ===== */}
      <TradeBottomSheet
        visible={openSheet === "buy"}
        onClose={() => setOpenSheet(null)}
        title="Buy Digital Gold"
        subtitle={`Live buy price ${formatMoney(buyPrice)} / g · 24k · 999.9 pure`}
        snap="large"
        state={sheetState}
        errorMessage={sheetError}
        successMessage="Gold has been added to your holdings."
        onRetry={() => setSheetState("idle")}
        onSuccessClose={() => { setOpenSheet(null); setSheetState("idle"); }}
        confirmLabel={`Long-press · Buy ${estGrams ? formatGrams(estGrams) : "Gold"}`}
        confirmDisabled={!estAmount || estAmount < (cfg?.min_buy_inr ?? 10)}
        onConfirm={doBuy}
        accent={palette.warning}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: 8, gap: 14 }}>
          {/* Mode toggle */}
          <View style={s.segment}>
            {(["amount", "grams"] as const).map((m) => {
              const active = buyMode === m;
              return (
                <Pressable
                  key={m}
                  onPress={() => setBuyMode(m)}
                  style={[s.segBtn, { backgroundColor: active ? palette.primary : "transparent" }]}
                  testID={`buy-mode-${m}`}
                >
                  <Text style={{ color: active ? "#fff" : palette.textSecondary, fontWeight: "800", fontSize: 12, letterSpacing: 0.6 }}>
                    {m === "amount" ? "AMOUNT (₹)" : "GRAMS (g)"}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[s.bigInputBox, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>
              {buyMode === "amount" ? "AMOUNT" : "GRAMS"}
            </Text>
            {buyMode === "amount" ? (
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 28, fontWeight: "800" }}>₹</Text>
                <TextInput
                  value={amountInput}
                  onChangeText={setAmountInput}
                  keyboardType="decimal-pad"
                  placeholder="0"
                  placeholderTextColor={palette.textMuted}
                  style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", flex: 1, paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
                  testID="buy-amount-input"
                />
              </View>
            ) : (
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
                <TextInput
                  value={gramsInput}
                  onChangeText={setGramsInput}
                  keyboardType="decimal-pad"
                  placeholder="0.0000"
                  placeholderTextColor={palette.textMuted}
                  style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", flex: 1, paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
                  testID="buy-grams-input"
                />
                <Text style={{ color: palette.textPrimary, fontSize: 22, fontWeight: "800" }}>g</Text>
              </View>
            )}
          </View>

          {/* Quick amounts */}
          {buyMode === "amount" ? (
            <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
              {[100, 500, 1000, 5000, 10000].map((v) => (
                <Pressable key={v} onPress={() => setAmountInput(String(v))} style={[s.quickPill, { borderColor: palette.border, backgroundColor: palette.surface }]}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 11 }}>₹{v.toLocaleString("en-IN")}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          {/* Preview */}
          <View style={[s.previewCard, { borderColor: palette.border, backgroundColor: palette.surface }]}>
            <PreviewRow lbl="You get" val={formatGrams(estGrams || 0)} palette={palette} bold />
            <PreviewRow lbl="Price / g" val={formatMoney(buyPrice)} palette={palette} />
            <PreviewRow lbl="Spread" val={`${((cfg?.spread_bps || 0) / 100).toFixed(2)}%`} palette={palette} muted />
            <PreviewRow lbl="Amount" val={formatMoney(estAmount || 0)} palette={palette} />
            <PreviewRow lbl="Wallet balance" val={formatMoney(wallet)} palette={palette} muted />
          </View>

          <View style={s.disclaimer}>
            <Info size={12} color={palette.textMuted} />
            <Text style={{ color: palette.textMuted, fontSize: 11, flex: 1 }}>
              Prices refresh every few seconds. Final settlement is at execution price.
              Long-press to confirm and avoid accidental trades.
            </Text>
          </View>
        </ScrollView>
      </TradeBottomSheet>

      {/* ===== SELL sheet ===== */}
      <TradeBottomSheet
        visible={openSheet === "sell"}
        onClose={() => setOpenSheet(null)}
        title="Sell Digital Gold"
        subtitle={`Live sell price ${formatMoney(sellPrice)} / g`}
        snap="large"
        state={sheetState}
        errorMessage={sheetError}
        successMessage="Proceeds have been credited to your wallet."
        onRetry={() => setSheetState("idle")}
        onSuccessClose={() => { setOpenSheet(null); setSheetState("idle"); }}
        confirmLabel={`Long-press · Sell ${sellGrams ? formatGrams(sellGrams) : "Gold"}`}
        confirmDisabled={!sellGrams || sellGrams > (holdings?.grams || 0)}
        onConfirm={doSell}
        accent={palette.danger}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: 8, gap: 14 }}>
          <View style={[s.bigInputBox, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>GRAMS TO SELL</Text>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
              <TextInput
                value={gramsInput}
                onChangeText={setGramsInput}
                keyboardType="decimal-pad"
                placeholder="0.0000"
                placeholderTextColor={palette.textMuted}
                style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", flex: 1, paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
                testID="sell-grams-input"
              />
              <Text style={{ color: palette.textPrimary, fontSize: 22, fontWeight: "800" }}>g</Text>
            </View>
            <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
              Available: {formatGrams(holdings?.grams || 0)}
            </Text>
          </View>

          <View style={{ flexDirection: "row", gap: 8 }}>
            {[0.25, 0.5, 0.75, 1].map((f) => (
              <Pressable
                key={f}
                onPress={() => setGramsInput(((holdings?.grams || 0) * f).toFixed(4))}
                style={[s.quickPill, { borderColor: palette.border, backgroundColor: palette.surface, flex: 1, alignItems: "center" }]}
              >
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 11 }}>{f === 1 ? "MAX" : `${f * 100}%`}</Text>
              </Pressable>
            ))}
          </View>

          {/* Preview */}
          <View style={[s.previewCard, { borderColor: palette.border, backgroundColor: palette.surface }]}>
            <PreviewRow lbl="You receive" val={formatMoney(sellProceeds || 0)} palette={palette} bold />
            <PreviewRow lbl="Price / g" val={formatMoney(sellPrice)} palette={palette} />
            <PreviewRow lbl="Cost basis" val={formatMoney(sellCost || 0)} palette={palette} muted />
            <PreviewRow
              lbl="Realized P/L"
              val={`${sellPnl >= 0 ? "+" : ""}${formatMoney(sellPnl || 0)}`}
              palette={palette}
              color={sellPnl >= 0 ? palette.success : palette.danger}
              bold
            />
          </View>

          <View style={s.disclaimer}>
            <Info size={12} color={palette.textMuted} />
            <Text style={{ color: palette.textMuted, fontSize: 11, flex: 1 }}>
              Proceeds are credited instantly to your wallet. Long-press to confirm.
            </Text>
          </View>
        </ScrollView>
      </TradeBottomSheet>
    </View>
  );
}

function StatBlock({ label, value, sub, palette, color }: any) {
  return (
    <View style={{ flex: 1, gap: 3 }}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 16, fontWeight: "800" }}>{value}</Text>
      {sub ? <Text style={{ color: color || palette.textSecondary, fontSize: 11, fontWeight: "700" }}>{sub}</Text> : null}
    </View>
  );
}
function QuickTile({ icon: Icon, label, onPress, palette, testID }: any) {
  return (
    <Pressable
      onPress={onPress}
      style={[s.quickTile, { backgroundColor: palette.surface, borderColor: palette.border }, shadow({ color: palette.cardShadow, opacity: 1, radius: 6, offsetY: 3 })]}
      testID={testID}
    >
      <View style={[s.quickIcon, { backgroundColor: palette.primary + "1A" }]}>
        <Icon color={palette.primary} size={20} />
      </View>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{label}</Text>
      <ChevronRight color={palette.textMuted} size={16} />
    </Pressable>
  );
}
function PreviewRow({ lbl, val, palette, muted, bold, color }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 }}>
      <Text style={{ color: muted ? palette.textMuted : palette.textSecondary, fontSize: 12, fontWeight: bold ? "800" : "600" }}>{lbl}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 13, fontWeight: bold ? "800" : "700" }}>{val}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", gap: 10 },
  iconBtn: { padding: 8, borderRadius: 14, borderWidth: 1 },
  pageEyebrow: { fontSize: 10, fontWeight: "800", letterSpacing: 1.4 },
  pageTitle: { fontSize: 22, fontWeight: "800", letterSpacing: -0.4 },

  warnBanner: { flexDirection: "row", gap: 8, alignItems: "center", padding: 10, borderRadius: 12, borderWidth: 1 },

  hero: { borderRadius: 24, padding: 18, gap: 12 },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  heroEyebrow: { color: "rgba(255,255,255,0.75)", fontSize: 10, fontWeight: "800", letterSpacing: 1.3 },
  heroPrice: { color: "#fff", fontSize: 32, fontWeight: "800", letterSpacing: -1, marginTop: 2 },
  heroChangeRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  heroChange: { fontSize: 12, fontWeight: "800" },
  providerBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "rgba(255,255,255,0.18)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  providerTxt: { color: "#fff", fontSize: 9, fontWeight: "800", letterSpacing: 1.2 },
  baRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: "rgba(15,23,42,0.35)", padding: 12, borderRadius: 14 },
  baBox: { flex: 1 },
  baLbl: { color: "rgba(255,255,255,0.7)", fontSize: 10, fontWeight: "800", letterSpacing: 1.2 },
  baVal: { color: "#fff", fontSize: 16, fontWeight: "800", marginTop: 2 },
  ctaBtn: { flex: 1, paddingVertical: 14, borderRadius: 16, alignItems: "center" },
  ctaTxt: { fontSize: 14, fontWeight: "800", letterSpacing: 0.3 },

  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  sectionTitle: { fontSize: 16, fontWeight: "800", letterSpacing: -0.3 },

  holdRow: { flexDirection: "row", gap: 12 },
  avgRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 10, borderRadius: 10 },

  quickTile: { flex: 1, borderRadius: 16, borderWidth: 1, padding: 12, alignItems: "center", gap: 6, flexDirection: "row", justifyContent: "flex-start" },
  quickIcon: { padding: 8, borderRadius: 12 },

  walletRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 14, borderRadius: 16, borderWidth: 1 },
  addBtn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 },

  segment: { flexDirection: "row", backgroundColor: "rgba(148,163,184,0.15)", borderRadius: 12, padding: 4 },
  segBtn: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 10 },

  bigInputBox: { borderRadius: 18, borderWidth: 1, padding: 14, gap: 4 },
  quickPill: { paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderRadius: 999 },
  previewCard: { borderWidth: 1, borderRadius: 16, padding: 14, gap: 4 },
  disclaimer: { flexDirection: "row", gap: 6, alignItems: "flex-start" },
});
