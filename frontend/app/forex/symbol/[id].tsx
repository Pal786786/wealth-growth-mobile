import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, TextInput, StyleSheet, Alert, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ChevronLeft, TrendingUp, TrendingDown, Info } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { forexApi, ForexSymbol, Side, Position } from "@/src/api/forex";
import { useForexPrices } from "@/src/hooks/useForexPrices";
import { formatINR } from "@/src/utils/format";
import { ForexDemoBanner } from "@/src/components/ForexDemoBanner";
import { TradingChart } from "@/src/components/TradingChart";

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
      const [op, cl] = await Promise.all([
        forexApi.listPositions("open"),
        forexApi.listPositions("closed"),
      ]);
      setOpenPositions(op);
      setClosedPositions(cl);
    } catch {
      // not logged in — chart simply shows no position overlays
    }
  }, []);

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

  const placeOrder = async () => {
    setPlacing(true);
    try {
      const tpNum = tp ? parseFloat(tp) : undefined;
      const slNum = sl ? parseFloat(sl) : undefined;
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

        {/* Trade ticket */}
        <Card style={{ gap: 12 }}>
          <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14 }}>Place Order (Market)</Text>

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

          {/* Order summary */}
          <View style={{ backgroundColor: palette.surface, padding: 10, borderRadius: 10, gap: 6 }}>
            <Row label="Margin required" value={formatINR(margin)} />
            <Row label="Balance after" value={formatINR(balance - margin)} />
            <Row label="Contract size" value={`${symbol.contract_size.toLocaleString()} units`} />
          </View>

          {/* Submit */}
          <Pressable onPress={placeOrder} disabled={!canTrade || placing} testID="place-order"
            style={{ backgroundColor: sideColor, paddingVertical: 14, borderRadius: 12, alignItems: "center", opacity: !canTrade || placing ? 0.5 : 1 }}>
            {placing ? <ActivityIndicator color="#fff" /> : <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>
              {side === "buy" ? `BUY ${lot} ${symbol.display}` : `SELL ${lot} ${symbol.display}`}
            </Text>}
          </Pressable>
          {!canTrade && q && balance < margin ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Info color={palette.danger} size={12} />
              <Text style={{ color: palette.danger, fontSize: 11 }}>Insufficient trading balance. Reset from main screen.</Text>
            </View>
          ) : null}
        </Card>

        <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center" }}>
          Paper trading only. Quotes from {q?.source || "…"} feed. No real money involved.
        </Text>
      </ScrollView>
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
