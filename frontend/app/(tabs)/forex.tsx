import React, { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl, StyleSheet } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { LineChart, Search, ArrowUpRight, ArrowDownRight, RefreshCw, Bitcoin, DollarSign, TrendingUp, TrendingDown, X as XIcon } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { forexApi, ForexSymbol, Position } from "@/src/api/forex";
import { useForexPrices } from "@/src/hooks/useForexPrices";
import { formatINR } from "@/src/utils/format";
import { ForexDemoBanner } from "@/src/components/ForexDemoBanner";

type Tab = "watch" | "open" | "closed";

const ASSET_ICON: Record<string, any> = {
  crypto: Bitcoin,
  metals: DollarSign,
  forex: TrendingUp,
};

export default function ForexTab() {
  const { palette, mode } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { quotes, loaded } = useForexPrices(2000);

  const [tab, setTab] = useState<Tab>("watch");
  const [symbols, setSymbols] = useState<ForexSymbol[]>([]);
  const [search, setSearch] = useState("");
  const [balance, setBalance] = useState<number>(0);
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [closedPositions, setClosedPositions] = useState<Position[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [moduleEnabled, setModuleEnabled] = useState(true);
  const [demoMode, setDemoMode] = useState(true);

  const loadAll = useCallback(async () => {
    // Symbols are public; balance/positions require auth — run them independently
    try {
      const cfg = await forexApi.symbols();
      setSymbols(cfg.symbols.filter((s) => s.enabled));
      setModuleEnabled(cfg.enabled);
      setDemoMode(cfg.demo_mode);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || e?.message || "Failed to load symbols");
    }
    try {
      const [bal, op, cl] = await Promise.all([
        forexApi.balance(),
        forexApi.listPositions("open"),
        forexApi.listPositions("closed"),
      ]);
      setBalance(bal.balance);
      setOpenPositions(op);
      setClosedPositions(cl);
    } catch (e: any) {
      // Likely not logged in — silently ignore so the watchlist still renders
      console.warn("[forex] private data load failed:", e?.message || e);
    } finally {
      setRefreshing(false);
    }
  }, [show]);

  useFocusEffect(useCallback(() => { loadAll(); }, [loadAll]));

  const totalUnrealizedPnl = openPositions.reduce((sum, p) => sum + (p.pnl_inr || 0), 0);
  const equity = balance + totalUnrealizedPnl;

  const filtered = symbols.filter((s) =>
    !search || s.id.includes(search.toUpperCase()) || s.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 100, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={palette.primary} onRefresh={() => { setRefreshing(true); loadAll(); }} />}
      >
        {/* Header */}
        <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
          <LineChart color={palette.primary} size={24} />
          <Text style={{ fontSize: 22, fontWeight: "800", color: palette.textPrimary, letterSpacing: -0.5, marginLeft: 6, flex: 1 }}>Forex Trading</Text>
          {demoMode && (
            <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: "#F59E0B20", borderWidth: 1, borderColor: "#F59E0B" }}>
              <Text style={{ color: "#F59E0B", fontSize: 10, fontWeight: "800" }}>DEMO</Text>
            </View>
          )}
        </View>

        {!moduleEnabled && (
          <Card style={{ backgroundColor: palette.danger + "15", borderColor: palette.danger + "50", borderWidth: 1 }}>
            <Text style={{ color: palette.danger, fontWeight: "800" }}>Forex trading is currently disabled by admin.</Text>
          </Card>
        )}

        <ForexDemoBanner />

        {/* Balance hero */}
        <Card style={s.hero}>
          <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700", letterSpacing: 1 }}>TRADING BALANCE (DEMO)</Text>
          <Text style={{ color: palette.textPrimary, fontSize: 28, fontWeight: "800", letterSpacing: -0.6, marginTop: 4 }}>{formatINR(balance)}</Text>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 12 }}>
            <View>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>UNREALIZED P&L</Text>
              <Text style={{ color: totalUnrealizedPnl >= 0 ? palette.success : palette.danger, fontSize: 16, fontWeight: "800", marginTop: 2 }}>
                {totalUnrealizedPnl >= 0 ? "+" : ""}{formatINR(totalUnrealizedPnl)}
              </Text>
            </View>
            <View>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>EQUITY</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "800", marginTop: 2 }}>{formatINR(equity)}</Text>
            </View>
            <View>
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>OPEN</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "800", marginTop: 2 }}>{openPositions.length}</Text>
            </View>
          </View>
        </Card>

        {/* Segmented control */}
        <View style={{ flexDirection: "row", backgroundColor: palette.surface, borderRadius: 12, padding: 4 }}>
          {([
            { id: "watch", label: `Watchlist (${symbols.length})` },
            { id: "open", label: `Open (${openPositions.length})` },
            { id: "closed", label: `Closed (${closedPositions.length})` },
          ] as const).map((t) => (
            <Pressable key={t.id} onPress={() => setTab(t.id)} testID={`tab-${t.id}`}
              style={{ flex: 1, paddingVertical: 9, borderRadius: 9, backgroundColor: tab === t.id ? palette.primary : "transparent", alignItems: "center" }}>
              <Text style={{ color: tab === t.id ? "#fff" : palette.textSecondary, fontWeight: "800", fontSize: 12 }}>{t.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Sprint 16.3 — Multi-Chart workspace entry */}
        <Pressable onPress={() => router.push("/forex/multi-chart")} testID="multi-chart-btn"
          style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: palette.primary, backgroundColor: palette.primary + "10" }}>
          <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>📊  Multi-Chart Workspace</Text>
        </Pressable>

        {tab === "watch" && (
          <>
            {/* Search */}
            <View style={{ flexDirection: "row", alignItems: "center", backgroundColor: palette.surface, borderRadius: 12, paddingHorizontal: 12, gap: 8 }}>
              <Search color={palette.textMuted} size={16} />
              <Pressable style={{ flex: 1, paddingVertical: 12 }} onPress={() => { /* keyboard focus would go here */ }}>
                <Text style={{ color: search ? palette.textPrimary : palette.textMuted, fontSize: 13 }}>{search || "Search symbols (XAU, EUR, BTC...)"}</Text>
              </Pressable>
              {search ? (
                <Pressable onPress={() => setSearch("")} hitSlop={10}><XIcon color={palette.textMuted} size={14} /></Pressable>
              ) : null}
            </View>
            {/* Quick filter chips */}
            <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
              {["", "forex", "metals", "crypto"].map((cls) => (
                <Pressable key={cls || "all"} onPress={() => setSearch(cls === "forex" ? "USD" : cls === "metals" ? "XAU" : cls === "crypto" ? "BTC" : "")} testID={`chip-${cls || "all"}`}
                  style={{ paddingHorizontal: 11, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.surface }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "700", textTransform: "capitalize" }}>{cls || "All"}</Text>
                </Pressable>
              ))}
            </View>

            {/* Watchlist */}
            {!loaded ? (
              <View style={{ paddingTop: 50, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
            ) : (
              filtered.map((sym) => {
                const q = quotes[sym.id];
                const Icon = ASSET_ICON[sym.asset_class] || TrendingUp;
                // Session-open anchor per symbol (updated to match backend starting_price)
                const ANCHOR: Record<string, number> = {
                  XAUUSD: 4070,
                  BTCUSD: 102000,
                  EURUSD: 1.145,
                  GBPUSD: 1.345,
                  USDJPY: 158.5,
                };
                const movement = q ? (q.mid - (ANCHOR[sym.id] ?? q.mid)) : 0;
                return (
                  <Pressable key={sym.id} onPress={() => router.push(`/forex/symbol/${sym.id}`)} testID={`row-${sym.id}`}>
                    <Card style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                      <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: palette.primary + "20", alignItems: "center", justifyContent: "center" }}>
                        <Icon color={palette.primary} size={18} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14 }}>{sym.display}</Text>
                        <Text style={{ color: palette.textSecondary, fontSize: 10, marginTop: 1 }}>{sym.name}</Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 15, fontVariant: ["tabular-nums"] }}>
                          {q ? q.mid.toFixed(sym.price_decimals) : "\u2014"}
                        </Text>
                        {q && (
                          <View style={{ flexDirection: "row", gap: 6, marginTop: 2 }}>
                            <Text style={{ color: palette.danger, fontSize: 10, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                              {q.bid.toFixed(sym.price_decimals)}
                            </Text>
                            <Text style={{ color: palette.success, fontSize: 10, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                              {q.ask.toFixed(sym.price_decimals)}
                            </Text>
                          </View>
                        )}
                      </View>
                      {movement >= 0
                        ? <ArrowUpRight color={palette.success} size={16} />
                        : <ArrowDownRight color={palette.danger} size={16} />}
                    </Card>
                  </Pressable>
                );
              })
            )}
          </>
        )}

        {tab === "open" && (
          <>
            {openPositions.length === 0 ? (
              <View style={{ paddingTop: 50, alignItems: "center", gap: 8 }}>
                <TrendingDown color={palette.textMuted} size={36} />
                <Text style={{ color: palette.textPrimary, fontWeight: "800" }}>No open positions</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 12, textAlign: "center" }}>Tap a symbol in the watchlist to place a trade.</Text>
              </View>
            ) : (
              openPositions.map((p) => <PositionCard key={p.position_id} p={p} quote={quotes[p.symbol_id]} onClose={loadAll} mode={mode} />)
            )}
          </>
        )}

        {tab === "closed" && (
          <>
            {closedPositions.length === 0 ? (
              <View style={{ paddingTop: 50, alignItems: "center", gap: 8 }}>
                <RefreshCw color={palette.textMuted} size={36} />
                <Text style={{ color: palette.textPrimary, fontWeight: "800" }}>No closed positions yet</Text>
              </View>
            ) : (
              closedPositions.map((p) => <ClosedCard key={p.position_id} p={p} />)
            )}
          </>
        )}
      </ScrollView>
    </Screen>
  );
}

function PositionCard({ p, quote, onClose, mode }: { p: Position; quote?: any; onClose: () => void; mode: "light"|"dark" }) {
  const { palette } = useTheme();
  const { show } = useToast();
  const [closing, setClosing] = useState(false);
  const pnlColor = p.pnl_inr >= 0 ? palette.success : palette.danger;
  const sideColor = p.side === "buy" ? palette.success : palette.danger;

  const onClick = async () => {
    setClosing(true);
    try {
      await forexApi.closePosition(p.position_id);
      show("success", `Closed ${p.symbol_id} at market`);
      onClose();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || e?.message || "Failed to close");
    } finally { setClosing(false); }
  };

  return (
    <Card style={{ gap: 8 }} testID={`pos-${p.position_id}`}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, backgroundColor: sideColor + "20" }}>
          <Text style={{ color: sideColor, fontWeight: "800", fontSize: 10, textTransform: "uppercase" }}>{p.side}</Text>
        </View>
        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14, flex: 1 }}>{p.symbol_id} · {p.lot_size} lot</Text>
        <Text style={{ color: pnlColor, fontWeight: "800", fontSize: 14, fontVariant: ["tabular-nums"] }}>
          {p.pnl_inr >= 0 ? "+" : ""}{formatINR(p.pnl_inr)}
        </Text>
      </View>
      <View style={{ flexDirection: "row", gap: 14, flexWrap: "wrap" }}>
        <Stat label="ENTRY" value={p.entry_price.toFixed(5)} />
        <Stat label="CURRENT" value={(quote?.mid ?? p.current_price).toFixed(5)} />
        <Stat label="TP" value={p.tp ? p.tp.toFixed(5) : "—"} />
        <Stat label="SL" value={p.sl ? p.sl.toFixed(5) : "—"} />
        <Stat label="MARGIN" value={formatINR(p.margin_inr)} />
      </View>
      <Pressable onPress={onClick} disabled={closing} testID={`close-${p.position_id}`}
        style={{ marginTop: 4, alignSelf: "flex-end", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: palette.danger + "15", borderWidth: 1, borderColor: palette.danger, opacity: closing ? 0.5 : 1 }}>
        {closing ? <ActivityIndicator color={palette.danger} size="small" /> : <Text style={{ color: palette.danger, fontWeight: "800", fontSize: 12 }}>Close Position</Text>}
      </Pressable>
    </Card>
  );
}

function ClosedCard({ p }: { p: Position }) {
  const { palette } = useTheme();
  const pnlColor = p.pnl_inr >= 0 ? palette.success : palette.danger;
  return (
    <Card style={{ gap: 6, opacity: 0.95 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border }}>
          <Text style={{ color: palette.textSecondary, fontWeight: "800", fontSize: 10, textTransform: "uppercase" }}>{p.side}</Text>
        </View>
        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13, flex: 1 }}>{p.symbol_id} · {p.lot_size} lot</Text>
        <Text style={{ color: pnlColor, fontWeight: "800", fontSize: 13, fontVariant: ["tabular-nums"] }}>
          {p.pnl_inr >= 0 ? "+" : ""}{formatINR(p.pnl_inr)}
        </Text>
      </View>
      <View style={{ flexDirection: "row", gap: 14, flexWrap: "wrap" }}>
        <Stat label="ENTRY" value={p.entry_price.toFixed(5)} />
        <Stat label="EXIT" value={(p.close_price || 0).toFixed(5)} />
        <Stat label="REASON" value={(p.close_reason || "").toUpperCase()} />
      </View>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  const { palette } = useTheme();
  return (
    <View>
      <Text style={{ color: palette.textSecondary, fontSize: 9, fontWeight: "700", letterSpacing: 0.8 }}>{label}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", marginTop: 1, fontVariant: ["tabular-nums"] }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  hero: { padding: 16, borderRadius: 16, gap: 4 },
});
