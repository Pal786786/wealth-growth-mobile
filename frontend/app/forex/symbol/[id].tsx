import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, TextInput, StyleSheet, Alert, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ChevronLeft, TrendingUp, TrendingDown, Info } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { forexApi, ForexSymbol, Side, Position, PendingOrder } from "@/src/api/forex";
import { useForexPrices } from "@/src/hooks/useForexPrices";
import { formatINR } from "@/src/utils/format";
import { ForexDemoBanner } from "@/src/components/ForexDemoBanner";
import { TradingChart } from "@/src/components/TradingChart";
import { PositionSheet } from "@/src/components/PositionSheet";

const LOT_PRESETS = [0.01, 0.1, 1, 5, 10];

export default function SymbolDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { quotes } = useForexPrices(2000);

  const [symbol, setSymbol] = useState<ForexSymbol | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [balance, setBalance] = useState<number>(0);
  const [marginPerLot, setMarginPerLot] = useState<number>(1000);
  const [side, setSide] = useState<Side>("buy");
  const [lot, setLot] = useState<number>(0.1);
  const [tp, setTp] = useState("");
  const [sl, setSl] = useState("");
  const [placing, setPlacing] = useState(false);
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [closedPositions, setClosedPositions] = useState<Position[]>([]);
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop">("market");
  const [pendingPrice, setPendingPrice] = useState("");
  const [costs, setCosts] = useState<{ commission_per_lot: number; commission_type: string; commission_currency: string; usd_inr: number } | null>(null);
  const [sheetPos, setSheetPos] = useState<Position | null>(null);

  // Load symbol (public) — must always succeed; balance is loaded separately so an
  // auth/network failure never leaves the screen stuck on a spinner.
  const loadSymbol = useCallback(async () => {
    try {
      const cfg = await forexApi.symbols();
      const sym = cfg.symbols.find((s) => s.id.toUpperCase() === String(id).toUpperCase()) || null;
      setSymbol(sym);
      setMarginPerLot(cfg.margin_per_lot);
      if (!sym) setLoadError(`Symbol ${id} is not enabled.`);
    } catch (e: any) {
      setLoadError(e?.message || "Failed to load symbol");
      show("error", e?.message || "Failed to load symbol");
    }
  }, [id, show]);

  const loadBalance = useCallback(async () => {
    try {
      const bal = await forexApi.balance();
      setBalance(bal.balance);
    } catch (e: any) {
      // Silent — user might not be logged in yet. UI shows a login CTA below.
      console.warn("[forex] balance load failed:", e?.message || e);
    }
  }, []);

  const loadPositions = useCallback(async () => {
    try {
      const [op, cl, po] = await Promise.all([
        forexApi.listPositions("open"),
        forexApi.listPositions("closed"),
        forexApi.listOrders("pending"),
      ]);
      setOpenPositions(op);
      setClosedPositions(cl);
      setPendingOrders(po);
    } catch {
      // not logged in — chart simply shows no position overlays
    }
  }, []);

  useEffect(() => { forexApi.tradingCosts().then(setCosts).catch(() => {}); }, []);

  useEffect(() => { loadSymbol(); loadBalance(); loadPositions(); }, [loadSymbol, loadBalance, loadPositions]);
  // Poll positions so entry-line floating PnL stays live on the chart
  useEffect(() => {
    const t = setInterval(loadPositions, 5000);
    return () => clearInterval(t);
  }, [loadPositions]);

  if (!symbol) {
    return (
      <Screen>
        <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
          <Pressable onPress={() => router.back()} hitSlop={10} testID="back-btn">
            <ChevronLeft color={palette.textPrimary} size={26} />
          </Pressable>
          <Text style={{ marginLeft: 4, fontSize: 18, fontWeight: "800", color: palette.textPrimary }}>
            {String(id || "").toUpperCase()}
          </Text>
        </View>
        <View style={{ paddingTop: 80, alignItems: "center", gap: 12 }}>
          {loadError ? (
            <>
              <Info color={palette.danger} size={28} />
              <Text style={{ color: palette.textPrimary, fontWeight: "800" }}>{loadError}</Text>
              <Pressable onPress={loadSymbol} style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: palette.primary }}>
                <Text style={{ color: "#fff", fontWeight: "800" }}>Retry</Text>
              </Pressable>
            </>
          ) : (
            <ActivityIndicator color={palette.primary} />
          )}
        </View>
      </Screen>
    );
  }

  const q = quotes[symbol.id];
  const margin = lot * marginPerLot;
  const canTrade = q && lot > 0 && balance >= margin;
  const sideColor = side === "buy" ? palette.success : palette.danger;

  // Sprint 16.1 — estimated costs (from admin trading-costs config)
  const commissionEst = (() => {
    if (!costs) return 0;
    let c = costs.commission_per_lot * lot;
    if (costs.commission_type === "per_side") c *= 2;
    if (costs.commission_currency === "USD") c *= costs.usd_inr;
    return c;
  })();
  const spreadCostEst = q ? (q.ask - q.bid) * symbol.contract_size * lot * (costs?.usd_inr || 83) : 0;
  const entryEst = orderType === "market"
    ? (q ? (side === "buy" ? q.ask : q.bid) : 0)
    : parseFloat(pendingPrice) || 0;
  const tpNumEst = parseFloat(tp) || 0;
  const slNumEst = parseFloat(sl) || 0;
  const riskReward = (() => {
    if (!entryEst || !tpNumEst || !slNumEst) return null;
    const reward = Math.abs(tpNumEst - entryEst);
    const risk = Math.abs(entryEst - slNumEst);
    return risk > 0 ? reward / risk : null;
  })();

  const placeOrder = async () => {
    setPlacing(true);
    try {
      const tpNum = tp ? parseFloat(tp) : undefined;
      const slNum = sl ? parseFloat(sl) : undefined;
      if (orderType !== "market") {
        const px = parseFloat(pendingPrice);
        if (!px || px <= 0) throw new Error("Enter a valid pending price");
        const order = await forexApi.placePendingOrder({
          symbol_id: symbol.id, side, order_type: orderType, price: px,
          lot_size: lot, tp: tpNum, sl: slNum,
        });
        show("success", `${side.toUpperCase()} ${orderType.toUpperCase()} placed @ ${order.price}`);
        setPendingPrice(""); setTp(""); setSl("");
        await loadPositions();
        return;
      }
      const pos = await forexApi.openPosition({
        symbol_id: symbol.id, side, lot_size: lot, tp: tpNum, sl: slNum,
      });
      show("success", `${side.toUpperCase()} ${lot} lot ${symbol.display} @ ${pos.entry_price}`);
      // Refresh balance + chart overlays, then navigate back
      await loadBalance();
      await loadPositions();
      setTp(""); setSl("");
      if (Platform.OS === "web") {
        if (typeof window !== "undefined" && window.confirm(`Position opened.\n\n${side.toUpperCase()} ${lot} ${symbol.display} @ ${pos.entry_price}\n\nView open positions?`)) {
          router.replace("/(tabs)/forex");
        }
      } else {
        Alert.alert("Position opened", `${side.toUpperCase()} ${lot} ${symbol.display}\nEntry: ${pos.entry_price}\nMargin: ${formatINR(pos.margin_inr)}`, [
          { text: "Trade more", style: "cancel" },
          { text: "View positions", onPress: () => router.replace("/(tabs)/forex") },
        ]);
      }
    } catch (e: any) {
      show("error", e?.response?.data?.detail || e?.message || "Order failed");
    } finally {
      setPlacing(false);
    }
  };

  return (
    <Screen>
      <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ marginLeft: 4, flex: 1 }}>
          <Text style={{ fontSize: 18, fontWeight: "800", color: palette.textPrimary }}>{symbol.display}</Text>
          <Text style={{ fontSize: 11, color: palette.textSecondary }}>{symbol.name}</Text>
        </View>
        <Text style={{ fontSize: 18, fontWeight: "800", color: palette.textPrimary, fontVariant: ["tabular-nums"] }}>
          {q ? q.mid.toFixed(symbol.price_decimals) : "—"}
        </Text>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40, gap: 12, paddingTop: 12 }}>
        <ForexDemoBanner compact />
        {/* Sprint 16.0 — professional candlestick chart (TradingView Lightweight
            Charts) fed by the unified Finnhub engine + cached history */}
        <TradingChart
          symbolId={symbol.id}
          priceDecimals={symbol.price_decimals}
          quote={q}
          openPositions={openPositions}
          closedPositions={closedPositions}
          pendingOrders={pendingOrders}
          onBackendUpdate={loadPositions}
          height={380}
        />

        {/* Quote summary */}
        {q && (
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Card style={{ flex: 1, alignItems: "center", paddingVertical: 12 }}>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>BID</Text>
              <Text style={{ color: palette.danger, fontSize: 18, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{q.bid.toFixed(symbol.price_decimals)}</Text>
              <Text style={{ color: palette.textMuted, fontSize: 9, marginTop: 2 }}>(Sell)</Text>
            </Card>
            <Card style={{ flex: 1, alignItems: "center", paddingVertical: 12 }}>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>ASK</Text>
              <Text style={{ color: palette.success, fontSize: 18, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{q.ask.toFixed(symbol.price_decimals)}</Text>
              <Text style={{ color: palette.textMuted, fontSize: 9, marginTop: 2 }}>(Buy)</Text>
            </Card>
            <Card style={{ flex: 1, alignItems: "center", paddingVertical: 12 }}>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>SPREAD</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800", fontVariant: ["tabular-nums"] }}>
                {((q.ask - q.bid) / symbol.pip_size).toFixed(1)}
              </Text>
              <Text style={{ color: palette.textMuted, fontSize: 9, marginTop: 2 }}>pips</Text>
            </Card>
          </View>
        )}

        {/* Trade ticket — Sprint 16.1 MT5-style */}
        <Card style={{ gap: 12 }}>
          <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14 }}>Place Order</Text>

          {/* Order type */}
          <View style={{ flexDirection: "row", gap: 6 }}>
            {(["market", "limit", "stop"] as const).map((ot) => (
              <Pressable key={ot} onPress={() => setOrderType(ot)} testID={`order-type-${ot}`}
                style={{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: "center", borderWidth: 1, borderColor: orderType === ot ? palette.primary : palette.border, backgroundColor: orderType === ot ? palette.primary + "15" : palette.surface }}>
                <Text style={{ color: orderType === ot ? palette.primary : palette.textSecondary, fontWeight: "800", fontSize: 12 }}>
                  {ot.toUpperCase()}
                </Text>
              </Pressable>
            ))}
          </View>

          {/* Buy/Sell */}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Pressable onPress={() => setSide("sell")} testID="side-sell"
              style={[t.sideBtn, { backgroundColor: side === "sell" ? palette.danger : palette.surface, borderColor: side === "sell" ? palette.danger : palette.border }]}>
              <TrendingDown color={side === "sell" ? "#fff" : palette.danger} size={16} />
              <View>
                <Text style={{ color: side === "sell" ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 13 }}>SELL</Text>
                <Text style={{ color: side === "sell" ? "#fff" : palette.textSecondary, fontSize: 10, fontVariant: ["tabular-nums"] }}>{q ? q.bid.toFixed(symbol.price_decimals) : "—"}</Text>
              </View>
            </Pressable>
            <Pressable onPress={() => setSide("buy")} testID="side-buy"
              style={[t.sideBtn, { backgroundColor: side === "buy" ? palette.success : palette.surface, borderColor: side === "buy" ? palette.success : palette.border }]}>
              <TrendingUp color={side === "buy" ? "#fff" : palette.success} size={16} />
              <View>
                <Text style={{ color: side === "buy" ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 13 }}>BUY</Text>
                <Text style={{ color: side === "buy" ? "#fff" : palette.textSecondary, fontSize: 10, fontVariant: ["tabular-nums"] }}>{q ? q.ask.toFixed(symbol.price_decimals) : "—"}</Text>
              </View>
            </Pressable>
          </View>

          {/* Lot size */}
          <View>
            <Text style={t.label}>LOT SIZE</Text>
            <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              {LOT_PRESETS.map((preset) => (
                <Pressable key={preset} onPress={() => setLot(preset)} testID={`lot-${preset}`}
                  style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: lot === preset ? palette.primary : palette.border, backgroundColor: lot === preset ? palette.primary + "15" : palette.surface }}>
                  <Text style={{ color: lot === preset ? palette.primary : palette.textPrimary, fontWeight: "800", fontSize: 12 }}>{preset}</Text>
                </Pressable>
              ))}
            </View>
            <TextInput value={String(lot)} onChangeText={(v) => setLot(parseFloat(v) || 0)} keyboardType="decimal-pad" testID="lot-input"
              style={[t.input, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface, marginTop: 6 }]} />
          </View>

          {/* TP / SL */}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={t.label}>TAKE PROFIT (price)</Text>
              <TextInput value={tp} onChangeText={setTp} keyboardType="decimal-pad" placeholder="e.g. 1.0900" placeholderTextColor={palette.textMuted} testID="tp-input"
                style={[t.input, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface }]} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={t.label}>STOP LOSS (price)</Text>
              <TextInput value={sl} onChangeText={setSl} keyboardType="decimal-pad" placeholder="e.g. 1.0800" placeholderTextColor={palette.textMuted} testID="sl-input"
                style={[t.input, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface }]} />
            </View>
          </View>

          {/* Order summary — Sprint 16.1 estimated cost breakdown */}
          <View style={{ backgroundColor: palette.surface, padding: 10, borderRadius: 10, gap: 6 }}>
            <Row label="Margin required" value={formatINR(margin)} />
            <Row label="Est. commission" value={formatINR(commissionEst)} />
            <Row label="Est. spread cost" value={formatINR(spreadCostEst)} />
            <Row label="Swap" value={formatINR(0)} />
            <Row label="Total est. cost" value={formatINR(commissionEst + spreadCostEst)} />
            {riskReward != null ? (
              <Row label="Risk / Reward" value={`1 : ${riskReward.toFixed(2)}`} />
            ) : null}
            <Row label="Balance after margin" value={formatINR(balance - margin)} />
            <Row label="Contract size" value={`${symbol.contract_size.toLocaleString()} units`} />
          </View>

          {/* Submit */}
          <Pressable onPress={placeOrder} disabled={!canTrade || placing} testID="place-order"
            style={{ backgroundColor: sideColor, paddingVertical: 14, borderRadius: 12, alignItems: "center", opacity: !canTrade || placing ? 0.5 : 1 }}>
            {placing ? <ActivityIndicator color="#fff" /> : <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>
              {`${side === "buy" ? "BUY" : "SELL"}${orderType !== "market" ? ` ${orderType.toUpperCase()}` : ""} ${lot} ${symbol.display}`}
            </Text>}
          </Pressable>
          {!canTrade && q && balance < margin ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Info color={palette.danger} size={12} />
              <Text style={{ color: palette.danger, fontSize: 11 }}>Insufficient trading balance. Reset from main screen.</Text>
            </View>
          ) : null}
        </Card>

        {/* Sprint 16.1 — open positions on this symbol (tap → manage) */}
        {openPositions.filter((p) => p.symbol_id === symbol.id).length > 0 ? (
          <Card style={{ gap: 8 }}>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>Open Positions</Text>
            {openPositions.filter((p) => p.symbol_id === symbol.id).map((p) => (
              <Pressable key={p.position_id} onPress={() => setSheetPos(p)} testID={`pos-${p.position_id}`}
                style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: palette.border }}>
                <View>
                  <Text style={{ color: p.side === "buy" ? palette.success : palette.danger, fontWeight: "800", fontSize: 12 }}>
                    {p.side.toUpperCase()} {p.lot_size} @ {p.entry_price}
                  </Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10 }}>
                    TP {p.tp ?? "—"} · SL {p.sl ?? "—"} · tap to manage
                  </Text>
                </View>
                <Text style={{ color: p.pnl_inr >= 0 ? palette.success : palette.danger, fontWeight: "800", fontVariant: ["tabular-nums"] }}>
                  {p.pnl_inr >= 0 ? "+" : ""}{formatINR(p.pnl_inr)}
                </Text>
              </Pressable>
            ))}
          </Card>
        ) : null}

        {/* Sprint 16.1 — pending orders on this symbol */}
        {pendingOrders.filter((o) => o.symbol_id === symbol.id).length > 0 ? (
          <Card style={{ gap: 8 }}>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>Pending Orders</Text>
            {pendingOrders.filter((o) => o.symbol_id === symbol.id).map((o) => (
              <View key={o.order_id} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: palette.border }}>
                <View>
                  <Text style={{ color: "#29b6f6", fontWeight: "800", fontSize: 12 }}>
                    {o.side.toUpperCase()} {o.type.toUpperCase()} {o.lot_size} @ {o.price}
                  </Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10 }}>drag the blue line on the chart to move</Text>
                </View>
                <Pressable testID={`cancel-order-${o.order_id}`}
                  onPress={async () => { try { await forexApi.cancelOrder(o.order_id); await loadPositions(); show("success", "Order cancelled"); } catch (e: any) { show("error", e?.response?.data?.detail || "Cancel failed"); } }}
                  style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: palette.danger }}>
                  <Text style={{ color: palette.danger, fontSize: 11, fontWeight: "700" }}>Cancel</Text>
                </Pressable>
              </View>
            ))}
          </Card>
        ) : null}

        <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center" }}>
          Paper trading only. Quotes from {q?.source || "…"} feed. No real money involved.
        </Text>
      </ScrollView>

      {/* Sprint 16.1 — position management sheet */}
      <PositionSheet
        position={sheetPos}
        priceDecimals={symbol.price_decimals}
        onClose={() => setSheetPos(null)}
        onChanged={async () => { await loadPositions(); await loadBalance(); }}
      />
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const { palette } = useTheme();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
      <Text style={{ color: palette.textSecondary, fontSize: 11 }}>{label}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{value}</Text>
    </View>
  );
}

const t = StyleSheet.create({
  sideBtn: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 12, borderWidth: 1.5 },
  label: { fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, fontWeight: "600" },
});
