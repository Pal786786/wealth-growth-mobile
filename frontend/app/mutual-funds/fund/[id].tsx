/**
 * Fund Detail — NAV chart with 1M/3M/6M/1Y/3Y/5Y/MAX toggles,
 * Invest CTA (opens TradeBottomSheet with Lumpsum + SIP tabs),
 * key stats, portfolio allocation (holdings + sectors), risk meter, docs.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable, TextInput, Platform, Linking, RefreshControl,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Star, TrendingUp, TrendingDown, Info, Bookmark, FileText } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import {
  mfApi, MFFund, MFWindow, fmtINR, RISK_META, MFHolding,
} from "@/src/api/mutualFunds";
import { FinancialChart } from "@/src/components/FinancialChart";
import { TradeBottomSheet, SheetState } from "@/src/components/TradeBottomSheet";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";

export default function FundDetail() {
  const { palette } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [fund, setFund] = useState<MFFund | null>(null);
  const [chartWin, setChartWin] = useState<MFWindow>("1Y");
  const [chartPts, setChartPts] = useState<{ ts: number | string; value: number }[]>([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [wallet, setWallet] = useState(0);
  const [inWatchlist, setInWatchlist] = useState(false);
  const [holding, setHolding] = useState<MFHolding | null>(null);

  // Trade sheet
  const [sheet, setSheet] = useState<null | "invest" | "redeem">(null);
  const [tradeKind, setTradeKind] = useState<"lumpsum" | "sip">("lumpsum");
  const [amountInput, setAmountInput] = useState("");
  const [sipDay, setSipDay] = useState("5");
  const [redeemUnitsInput, setRedeemUnitsInput] = useState("");
  const [sheetState, setSheetState] = useState<SheetState>("idle");
  const [sheetErr, setSheetErr] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [f, w, wl, port] = await Promise.all([
        mfApi.fund(id),
        api.get("/wallet").then((r) => Number((r.data as any)?.balance || 0)).catch(() => 0),
        mfApi.watchlist().then((r) => r.items.some((x) => x.fund_id === id)).catch(() => false),
        mfApi.portfolio().then((p) => p.holdings.find((h) => h.fund_id === id) || null).catch(() => null),
      ]);
      setFund(f); setWallet(w); setInWatchlist(wl); setHolding(port);
    } catch {}
  }, [id]);

  const loadChart = useCallback(async (w: MFWindow) => {
    if (!id) return;
    setChartLoading(true);
    try {
      const r = await mfApi.chart(id, w);
      setChartPts(r.points.map((p) => ({ ts: p.as_of, value: p.nav })));
    } catch {} finally { setChartLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadChart(chartWin); }, [chartWin, loadChart]);

  const first = chartPts[0]?.value ?? 0;
  const last = chartPts[chartPts.length - 1]?.value ?? 0;
  const delta = last - first;
  const isUp = delta >= 0;

  // --- Invest handler ---
  const doInvest = async () => {
    const amt = Number(amountInput);
    if (!amt || amt < 500) {
      setSheetErr(`Minimum ${tradeKind === "sip" ? "SIP" : "lumpsum"} is ₹500`);
      setSheetState("error"); return;
    }
    if (tradeKind === "lumpsum" && amt > wallet) {
      setSheetErr(`Insufficient wallet (${fmtINR(wallet)})`);
      setSheetState("error"); return;
    }
    setSheetState("submitting");
    try {
      if (tradeKind === "lumpsum") {
        await mfApi.invest(id!, amt, { idempotencyKey: `mfi-${Date.now()}` });
      } else {
        const day = Math.max(1, Math.min(28, Number(sipDay) || 5));
        await mfApi.sipCreate(id!, amt, day, "monthly");
      }
      await load();
      setSheetState("success");
    } catch (e: any) {
      setSheetErr(e?.response?.data?.detail || e?.message || "Something went wrong");
      setSheetState("error");
    }
  };

  const doRedeem = async () => {
    const u = Number(redeemUnitsInput);
    if (!u || u <= 0) { setSheetErr("Enter units to redeem"); setSheetState("error"); return; }
    if (u > (holding?.units || 0)) { setSheetErr(`Only ${holding?.units || 0} units held`); setSheetState("error"); return; }
    setSheetState("submitting");
    try {
      await mfApi.redeem(id!, u);
      await load();
      setSheetState("success");
    } catch (e: any) {
      setSheetErr(e?.response?.data?.detail || e?.message || "Redemption failed");
      setSheetState("error");
    }
  };

  const toggleWatchlist = async () => {
    if (!id) return;
    try {
      if (inWatchlist) { await mfApi.watchlistRemove(id); setInWatchlist(false); }
      else { await mfApi.watchlistAdd(id); setInWatchlist(true); }
    } catch {}
  };

  if (!fund) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: palette.background }}>
        <ActivityIndicator color={palette.primary} size="large" />
      </View>
    );
  }

  const riskColor = RISK_META[fund.risk]?.color ?? palette.textMuted;
  const estUnitsInvest = Number(amountInput) > 0 && fund.current_nav > 0 ? Number(amountInput) / fund.current_nav : 0;
  const redeemProceeds = Number(redeemUnitsInput) > 0 ? Number(redeemUnitsInput) * fund.current_nav : 0;

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); Promise.all([load(), loadChart(chartWin)]).finally(() => setRefreshing(false)); }} tintColor={palette.primary} />}
      >
        {/* Header row */}
        <View style={{ gap: 6 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>{fund.amc}</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800", letterSpacing: -0.4 }}>{fund.name}</Text>
              <View style={{ flexDirection: "row", gap: 8, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
                <View style={[s.tag, { backgroundColor: palette.chipBg }]}>
                  <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800" }}>{fund.sub_category.toUpperCase()}</Text>
                </View>
                <View style={[s.tag, { backgroundColor: riskColor + "22" }]}>
                  <Text style={{ color: riskColor, fontSize: 10, fontWeight: "800" }}>{(RISK_META[fund.risk]?.label || fund.risk).toUpperCase()} RISK</Text>
                </View>
                <View style={{ flexDirection: "row", gap: 1, alignItems: "center" }}>
                  {Array.from({ length: Math.round(fund.star_rating) }).map((_, i) => (
                    <Star key={i} color="#F59E0B" fill="#F59E0B" size={11} />
                  ))}
                </View>
              </View>
            </View>
            <Pressable onPress={toggleWatchlist} style={[s.iconBtn, { backgroundColor: inWatchlist ? palette.primary : palette.surface, borderColor: palette.border }]} testID="mf-watch-toggle">
              <Bookmark color={inWatchlist ? "#fff" : palette.textPrimary} size={18} fill={inWatchlist ? "#fff" : "transparent"} />
            </Pressable>
          </View>
        </View>

        {/* NAV + live chart */}
        <Card style={{ padding: 14, gap: 6 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
            <View>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>NAV</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 26, fontWeight: "800", letterSpacing: -0.6 }}>{fmtINR(fund.current_nav)}</Text>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              {isUp ? <TrendingUp size={16} color={palette.success} /> : <TrendingDown size={16} color={palette.danger} />}
              <Text style={{ color: isUp ? palette.success : palette.danger, fontSize: 13, fontWeight: "800" }}>
                {isUp ? "+" : ""}{delta.toFixed(2)} · {chartWin}
              </Text>
            </View>
          </View>
        </Card>

        {chartLoading ? (
          <View style={{ height: 260, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={palette.primary} /></View>
        ) : (
          <FinancialChart
            points={chartPts}
            height={260}
            window={chartWin as any}
            windows={["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"] as any}
            onWindowChange={(w) => setChartWin(w as MFWindow)}
            livePrice={fund.current_nav}
            title="NAV HISTORY"
            isUp={isUp}
          />
        )}

        {/* Returns grid */}
        <View>
          <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800", marginBottom: 6 }}>Historical Returns</Text>
          <View style={{ flexDirection: "row", gap: 6 }}>
            {[
              ["1M", fund.returns.m1], ["3M", fund.returns.m3], ["6M", fund.returns.m6],
              ["1Y", fund.returns.y1], ["3Y", fund.returns.y3], ["5Y", fund.returns.y5],
            ].map(([lbl, val]: any) => (
              <View key={lbl} style={[s.retBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800" }}>{lbl}</Text>
                <Text style={{ color: (val ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 13, fontWeight: "800" }}>
                  {(val ?? 0) >= 0 ? "+" : ""}{(val ?? 0).toFixed(2)}%
                </Text>
              </View>
            ))}
          </View>
        </View>

        {/* Key stats */}
        <Card style={{ padding: 14, gap: 8 }}>
          <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800", marginBottom: 4 }}>Key Details</Text>
          <KV lbl="Expense Ratio" val={`${fund.expense_ratio}%`} palette={palette} />
          <KV lbl="Exit Load" val={fund.exit_load || "Nil"} palette={palette} />
          <KV lbl="AUM" val={`₹${(fund.aum_cr / 1000).toFixed(1)}k Cr`} palette={palette} />
          <KV lbl="Fund Manager" val={fund.fund_manager || "—"} palette={palette} />
          <KV lbl="Benchmark" val={fund.benchmark || "—"} palette={palette} />
          <KV lbl="Min Lumpsum" val={fmtINR(fund.min_lumpsum)} palette={palette} />
          <KV lbl="Min SIP" val={fmtINR(fund.min_sip)} palette={palette} />
          {fund.objective ? (
            <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 6 }}>{fund.objective}</Text>
          ) : null}
        </Card>

        {/* Holdings */}
        {fund.holdings && fund.holdings.length ? (
          <Card style={{ padding: 14, gap: 8 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Top Holdings</Text>
            {fund.holdings.slice(0, 8).map((h) => (
              <View key={h.name} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={{ color: palette.textSecondary, fontSize: 12, flex: 1 }}>{h.name}</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{h.weight}%</Text>
              </View>
            ))}
          </Card>
        ) : null}

        {/* Sector allocation */}
        {fund.sector_allocation && fund.sector_allocation.length ? (
          <Card style={{ padding: 14, gap: 8 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>Sector Allocation</Text>
            {fund.sector_allocation.map((sec) => (
              <View key={sec.name} style={{ gap: 3 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={{ color: palette.textSecondary, fontSize: 11 }}>{sec.name}</Text>
                  <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{sec.weight}%</Text>
                </View>
                <View style={{ height: 5, backgroundColor: palette.chipBg, borderRadius: 3, overflow: "hidden" }}>
                  <View style={{ width: `${Math.min(100, sec.weight)}%`, height: 5, backgroundColor: palette.primary }} />
                </View>
              </View>
            ))}
          </Card>
        ) : null}

        {/* Holding info */}
        {holding ? (
          <Card style={{ padding: 14, gap: 6 }}>
            <Text style={{ color: palette.primary, fontSize: 12, fontWeight: "800", letterSpacing: 1 }}>YOUR HOLDING</Text>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <KVBlock lbl="Units" val={holding.units.toFixed(4)} palette={palette} />
              <KVBlock lbl="Invested" val={fmtINR(holding.total_invested)} palette={palette} />
              <KVBlock lbl="Value" val={fmtINR(holding.current_value)} palette={palette} />
            </View>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <KVBlock lbl="P/L" val={`${holding.unrealized_pnl >= 0 ? "+" : ""}${fmtINR(holding.unrealized_pnl)}`} palette={palette} color={holding.unrealized_pnl >= 0 ? palette.success : palette.danger} />
              <KVBlock lbl="Avg NAV" val={fmtINR(holding.avg_nav)} palette={palette} />
            </View>
          </Card>
        ) : null}

        {/* Docs */}
        {fund.documents && fund.documents.length ? (
          <Card style={{ padding: 12, gap: 6 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800", marginBottom: 4 }}>Documents</Text>
            {fund.documents.map((d) => (
              <Pressable key={d.kind} onPress={() => Linking.openURL(d.url)} style={{ flexDirection: "row", gap: 8, paddingVertical: 6, alignItems: "center" }}>
                <FileText color={palette.primary} size={14} />
                <Text style={{ color: palette.textSecondary, fontSize: 12, flex: 1 }}>{d.label}</Text>
                <Text style={{ color: palette.primary, fontSize: 11, fontWeight: "800" }}>Open ›</Text>
              </Pressable>
            ))}
          </Card>
        ) : null}

        <View style={{ flexDirection: "row", gap: 10 }}>
          <Pressable onPress={() => { setSheet("invest"); setSheetState("idle"); setAmountInput(""); }}
                       style={[s.bigCta, { backgroundColor: palette.primary }]} testID="mf-invest-btn">
            <Text style={{ color: "#fff", fontSize: 14, fontWeight: "800" }}>Invest Now</Text>
          </Pressable>
          {(holding?.units || 0) > 0 ? (
            <Pressable onPress={() => { setSheet("redeem"); setSheetState("idle"); setRedeemUnitsInput(""); }}
                          style={[s.bigCta, { backgroundColor: palette.danger }]} testID="mf-redeem-btn">
              <Text style={{ color: "#fff", fontSize: 14, fontWeight: "800" }}>Redeem</Text>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>

      {/* Invest sheet */}
      <TradeBottomSheet
        visible={sheet === "invest"}
        onClose={() => setSheet(null)}
        title={`${tradeKind === "lumpsum" ? "Lumpsum" : "SIP"} — ${fund.name}`}
        subtitle={`NAV ${fmtINR(fund.current_nav)} · ${fund.amc}`}
        snap="large"
        state={sheetState}
        errorMessage={sheetErr}
        successMessage={tradeKind === "lumpsum" ? "Investment successful. Units will reflect on next NAV cycle." : "SIP scheduled successfully."}
        onRetry={() => setSheetState("idle")}
        onSuccessClose={() => { setSheet(null); setSheetState("idle"); }}
        confirmLabel={`Long-press · ${tradeKind === "lumpsum" ? "Invest" : "Start SIP"} ${amountInput ? fmtINR(Number(amountInput)) : ""}`}
        confirmDisabled={!amountInput || Number(amountInput) < 500}
        onConfirm={doInvest}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: 6, gap: 12 }}>
          <View style={s.segment}>
            {(["lumpsum", "sip"] as const).map((k) => {
              const active = tradeKind === k;
              return (
                <Pressable key={k} onPress={() => setTradeKind(k)} style={[s.segBtn, { backgroundColor: active ? palette.primary : "transparent" }]} testID={`trade-mode-${k}`}>
                  <Text style={{ color: active ? "#fff" : palette.textSecondary, fontWeight: "800", fontSize: 12, letterSpacing: 0.6 }}>
                    {k === "lumpsum" ? "LUMPSUM" : "MONTHLY SIP"}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[s.bigInput, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>AMOUNT</Text>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4 }}>
              <Text style={{ color: palette.textPrimary, fontSize: 28, fontWeight: "800" }}>₹</Text>
              <TextInput
                value={amountInput}
                onChangeText={setAmountInput}
                keyboardType="decimal-pad"
                placeholder="0"
                placeholderTextColor={palette.textMuted}
                style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", flex: 1, paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
                testID="mf-amount-input"
              />
            </View>
          </View>

          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
            {(tradeKind === "sip" ? [500, 1000, 2500, 5000, 10000] : [1000, 5000, 10000, 25000, 50000]).map((v) => (
              <Pressable key={v} onPress={() => setAmountInput(String(v))} style={[s.quickPill, { borderColor: palette.border, backgroundColor: palette.surface }]}>
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 11 }}>₹{v.toLocaleString("en-IN")}</Text>
              </Pressable>
            ))}
          </View>

          {tradeKind === "sip" ? (
            <View style={[s.bigInput, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>SIP DATE (day of month · 1-28)</Text>
              <TextInput
                value={sipDay}
                onChangeText={setSipDay}
                keyboardType="number-pad"
                style={{ color: palette.textPrimary, fontSize: 22, fontWeight: "800", paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
                testID="mf-sip-day"
              />
            </View>
          ) : null}

          <View style={[s.preview, { borderColor: palette.border, backgroundColor: palette.surface }]}>
            {tradeKind === "lumpsum" ? (
              <>
                <Row lbl="You get (approx)" val={`${estUnitsInvest.toFixed(4)} units`} palette={palette} bold />
                <Row lbl="NAV used" val={fmtINR(fund.current_nav)} palette={palette} />
                <Row lbl="Wallet balance" val={fmtINR(wallet)} palette={palette} muted />
              </>
            ) : (
              <>
                <Row lbl="Frequency" val="Monthly" palette={palette} bold />
                <Row lbl="Next run" val={`Day ${sipDay} of month`} palette={palette} />
                <Row lbl="Wallet source" val="Wallet (auto-debit later)" palette={palette} muted />
              </>
            )}
          </View>
          <View style={{ flexDirection: "row", gap: 6, alignItems: "flex-start" }}>
            <Info size={12} color={palette.textMuted} />
            <Text style={{ color: palette.textMuted, fontSize: 11, flex: 1 }}>
              Mutual fund investments are subject to market risk. Read all scheme related documents carefully. Long-press to confirm.
            </Text>
          </View>
        </ScrollView>
      </TradeBottomSheet>

      {/* Redeem sheet */}
      <TradeBottomSheet
        visible={sheet === "redeem"}
        onClose={() => setSheet(null)}
        title={`Redeem — ${fund.name}`}
        subtitle={`NAV ${fmtINR(fund.current_nav)}`}
        snap="large"
        state={sheetState}
        errorMessage={sheetErr}
        successMessage="Redemption request placed. Proceeds credited to wallet."
        onRetry={() => setSheetState("idle")}
        onSuccessClose={() => { setSheet(null); setSheetState("idle"); }}
        confirmLabel={`Long-press · Redeem ${Number(redeemUnitsInput) ? redeemUnitsInput + " units" : ""}`}
        confirmDisabled={!redeemUnitsInput || Number(redeemUnitsInput) <= 0}
        onConfirm={doRedeem}
        accent={palette.danger}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingVertical: 6, gap: 12 }}>
          <View style={[s.bigInput, { backgroundColor: palette.chipBg, borderColor: palette.border }]}>
            <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }}>UNITS TO REDEEM</Text>
            <TextInput
              value={redeemUnitsInput}
              onChangeText={setRedeemUnitsInput}
              keyboardType="decimal-pad"
              placeholder="0.0000"
              placeholderTextColor={palette.textMuted}
              style={{ color: palette.textPrimary, fontSize: 30, fontWeight: "800", paddingVertical: Platform.OS === "ios" ? 4 : 0 }}
              testID="mf-redeem-units"
            />
            <Text style={{ color: palette.textMuted, fontSize: 11 }}>Available: {holding?.units || 0} units</Text>
          </View>
          <View style={{ flexDirection: "row", gap: 8 }}>
            {[0.25, 0.5, 0.75, 1].map((f) => (
              <Pressable key={f}
                            onPress={() => setRedeemUnitsInput(((holding?.units || 0) * f).toFixed(4))}
                            style={[s.quickPill, { flex: 1, alignItems: "center", borderColor: palette.border, backgroundColor: palette.surface }]}>
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 11 }}>{f === 1 ? "MAX" : `${f * 100}%`}</Text>
              </Pressable>
            ))}
          </View>
          <View style={[s.preview, { borderColor: palette.border, backgroundColor: palette.surface }]}>
            <Row lbl="You receive (approx)" val={fmtINR(redeemProceeds)} palette={palette} bold />
            <Row lbl="NAV used" val={fmtINR(fund.current_nav)} palette={palette} />
            <Row lbl="Exit load" val={fund.exit_load || "Nil"} palette={palette} muted />
          </View>
        </ScrollView>
      </TradeBottomSheet>
    </View>
  );
}

function Row({ lbl, val, palette, muted, bold, color }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 }}>
      <Text style={{ color: muted ? palette.textMuted : palette.textSecondary, fontSize: 12, fontWeight: bold ? "800" : "600" }}>{lbl}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 13, fontWeight: bold ? "800" : "700" }}>{val}</Text>
    </View>
  );
}
function KV({ lbl, val, palette }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 }}>
      <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>{lbl}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{val}</Text>
    </View>
  );
}
function KVBlock({ lbl, val, palette, color }: any) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800", letterSpacing: 1 }}>{lbl.toUpperCase()}</Text>
      <Text style={{ color: color || palette.textPrimary, fontSize: 13, fontWeight: "800" }}>{val}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  tag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  iconBtn: { padding: 10, borderRadius: 12, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  retBox: { flex: 1, padding: 10, borderRadius: 10, borderWidth: 1, alignItems: "center", gap: 4 },
  bigCta: { flex: 1, paddingVertical: 14, borderRadius: 16, alignItems: "center" },
  segment: { flexDirection: "row", backgroundColor: "rgba(148,163,184,0.15)", borderRadius: 12, padding: 4 },
  segBtn: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 10 },
  bigInput: { borderRadius: 16, borderWidth: 1, padding: 14, gap: 4 },
  quickPill: { paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderRadius: 999 },
  preview: { borderWidth: 1, borderRadius: 14, padding: 14, gap: 2 },
});
