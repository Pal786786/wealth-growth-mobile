/** Sprint 16.3 — Multi-Chart workspace (Single / Dual V / Dual H / Quad).
 * Every pane is an independent TradingChart (own symbol, timeframe, indicators,
 * drawings — persisted per chartKey) but ALL panes read the same unified
 * ProviderManager candle/quote engine. Workspace persists per user. */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, Modal, useWindowDimensions } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, LayoutGrid, Rows2, Columns2, Square } from "lucide-react-native";
import { Screen } from "@/src/components/Screen";
import { useTheme } from "@/src/theme/ThemeProvider";
import { TradingChart } from "@/src/components/TradingChart";
import { forexApi, ForexSymbol } from "@/src/api/forex";
import { useForexPrices } from "@/src/hooks/useForexPrices";

type LayoutId = "single" | "dual_v" | "dual_h" | "quad";
const LAYOUTS: { id: LayoutId; label: string; count: number; Icon: any }[] = [
  { id: "single", label: "1", count: 1, Icon: Square },
  { id: "dual_v", label: "2⬍", count: 2, Icon: Rows2 },
  { id: "dual_h", label: "2⬌", count: 2, Icon: Columns2 },
  { id: "quad", label: "4", count: 4, Icon: LayoutGrid },
];
const DEFAULT_PANES = ["EURUSD", "XAUUSD", "BTCUSD", "GBPUSD"];

export default function MultiChartScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { height: winH } = useWindowDimensions();
  const [layout, setLayout] = useState<LayoutId>("single");
  const [panes, setPanes] = useState<string[]>(DEFAULT_PANES);
  const [symbols, setSymbols] = useState<ForexSymbol[]>([]);
  const [pickerFor, setPickerFor] = useState<number | null>(null);
  const { quotes } = useForexPrices();

  // restore last workspace
  useEffect(() => {
    forexApi.symbols().then((cfg) => setSymbols(cfg.symbols || [])).catch(() => {});
    forexApi.getChartPrefs().then(({ prefs }) => {
      const ws = prefs?.workspace;
      if (ws?.layout) setLayout(ws.layout);
      if (Array.isArray(ws?.panes) && ws.panes.length === 4) setPanes(ws.panes);
    }).catch(() => {});
  }, []);

  const persist = useCallback((nextLayout: LayoutId, nextPanes: string[]) => {
    forexApi.getChartPrefs().then(({ prefs }) => {
      const p = prefs || {};
      p.workspace = { layout: nextLayout, panes: nextPanes };
      return forexApi.saveChartPrefs(p);
    }).catch(() => {});
  }, []);

  const horizontal = layout === "dual_h";
  const chartH = layout === "single" ? Math.max(winH - 220, 320)
    : layout === "quad" ? Math.max((winH - 260) / 2, 220)
    : horizontal ? Math.max(winH - 260, 300)
    : Math.max((winH - 240) / 2, 240);

  const decimalsFor = (id: string) => symbols.find((s) => s.id === id)?.price_decimals ?? 5;

  const renderPane = (i: number) => (
    <View key={`${i}-${panes[i]}`} style={{ flex: 1, gap: 4 }}>
      <Pressable onPress={() => setPickerFor(i)} testID={`pane-symbol-${i}`}
        style={[s.paneHead, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 12 }}>{panes[i]}</Text>
        <Text style={{ color: palette.textMuted, fontSize: 10 }}>change ▾</Text>
      </Pressable>
      <TradingChart
        symbolId={panes[i]}
        priceDecimals={decimalsFor(panes[i])}
        quote={quotes[panes[i]]}
        chartKey={`pane${i}`}
        compact
        height={chartH}
      />
    </View>
  );

  return (
    <Screen>
      <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4, gap: 8 }}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="back-btn">
          <ChevronLeft color={palette.textPrimary} size={26} />
        </Pressable>
        <Text style={{ fontSize: 17, fontWeight: "800", color: palette.textPrimary, flex: 1 }}>Multi-Chart</Text>
        {LAYOUTS.map((l) => (
          <Pressable key={l.id} testID={`layout-${l.id}`}
            onPress={() => { setLayout(l.id); persist(l.id, panes); }}
            style={[s.layoutBtn, { borderColor: layout === l.id ? palette.primary : palette.border, backgroundColor: layout === l.id ? palette.primary + "15" : palette.surface }]}>
            <l.Icon size={16} color={layout === l.id ? palette.primary : palette.textSecondary} />
          </Pressable>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 30, paddingTop: 10, gap: 8 }}>
        {layout === "single" ? renderPane(0) : null}
        {layout === "dual_v" ? (<>{renderPane(0)}{renderPane(1)}</>) : null}
        {layout === "dual_h" ? (
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}>{renderPane(0)}</View>
            <View style={{ flex: 1 }}>{renderPane(1)}</View>
          </View>
        ) : null}
        {layout === "quad" ? (
          <>
            {renderPane(0)}
            {renderPane(1)}
            {renderPane(2)}
            {renderPane(3)}
          </>
        ) : null}
        <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center" }}>
          All panes stream from ONE unified market engine · workspace auto-saved
        </Text>
      </ScrollView>

      {/* symbol picker */}
      <Modal visible={pickerFor !== null} transparent animationType="fade" onRequestClose={() => setPickerFor(null)}>
        <Pressable style={s.modalBg} onPress={() => setPickerFor(null)}>
          <Pressable style={[s.modalCard, { backgroundColor: palette.card, borderColor: palette.border }]} onPress={() => {}}>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 15, marginBottom: 8 }}>Select symbol</Text>
            <ScrollView style={{ maxHeight: 380 }}>
              {symbols.map((sym) => (
                <Pressable key={sym.id} testID={`pick-${sym.id}`}
                  onPress={() => {
                    if (pickerFor === null) return;
                    const next = [...panes];
                    next[pickerFor] = sym.id;
                    setPanes(next);
                    persist(layout, next);
                    setPickerFor(null);
                  }}
                  style={{ paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: palette.border, flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "700", fontSize: 13 }}>{sym.display}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 11 }}>{sym.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </Screen>
  );
}

const s = StyleSheet.create({
  layoutBtn: { padding: 8, borderRadius: 8, borderWidth: 1 },
  paneHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1 },
  modalBg: { flex: 1, backgroundColor: "#000a", justifyContent: "center", padding: 24 },
  modalCard: { borderRadius: 14, padding: 16, borderWidth: 1 },
});
