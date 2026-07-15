/**
 * Sprint 16.0 — Professional trading chart (TradingView Lightweight Charts
 * inside a WebView/iframe, served same-origin from the backend at /api/chart/).
 *
 * Data flow: this component fetches candles from /api/market/candles (unified
 * Finnhub engine + cached history) and pushes them into the chart via a JSON
 * message protocol. The chart posts back `ready` and `loadMore` (infinite
 * scroll → automatic historical backfill).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, Pressable, Platform, StyleSheet, ActivityIndicator, Modal, ScrollView, PanResponder } from "react-native";
import { WebView } from "react-native-webview";
import { CandlestickChart, LineChart as LineChartIcon, FunctionSquare, Pencil, X } from "lucide-react-native";
import { forexApi, Position, ForexQuote, PendingOrder } from "@/src/api/forex";
import { BACKEND_URL } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";

const CHART_URL = `${BACKEND_URL.replace(/\/+$/, "")}/api/chart/index.html`;
const TIMEFRAMES: { id: string; label: string }[] = [
  { id: "1m", label: "1m" }, { id: "5m", label: "5m" }, { id: "15m", label: "15m" },
  { id: "30m", label: "30m" }, { id: "1h", label: "1H" }, { id: "4h", label: "4H" },
  { id: "1d", label: "D1" },
];
const POLL_MS = 4000;

// Sprint 16.1/16.2 — indicator catalogue (window.Indicators registry in the chart)
const INDICATORS: { id: string; label: string; overlay: boolean; period?: number }[] = [
  { id: "ema", label: "EMA", overlay: true, period: 20 },
  { id: "sma", label: "SMA", overlay: true, period: 50 },
  { id: "bb", label: "Bollinger", overlay: true, period: 20 },
  { id: "vwap", label: "VWAP", overlay: true },
  { id: "rsi", label: "RSI", overlay: false, period: 14 },
  { id: "macd", label: "MACD", overlay: false },
  { id: "atr", label: "ATR", overlay: false, period: 14 },
];
const TOOLS: { id: string; label: string }[] = [
  { id: "trend", label: "Trend" }, { id: "hline", label: "H-Line" },
  { id: "vline", label: "V-Line" }, { id: "rect", label: "Rect" },
  { id: "fib", label: "Fib" }, { id: "text", label: "Text" },
  { id: "erase", label: "Erase" },
];

type Props = {
  symbolId: string;
  priceDecimals: number;
  quote?: ForexQuote | null;
  openPositions?: Position[];
  closedPositions?: Position[];
  pendingOrders?: PendingOrder[];
  chartKey?: string;
  compact?: boolean;
  height?: number;
  onBackendUpdate?: () => void;
};

function epoch(iso?: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? Math.floor(t / 1000) : null;
}

export function TradingChart({ symbolId, priceDecimals, quote, openPositions = [], closedPositions = [], pendingOrders = [], chartKey = "main", compact = false, height = 380, onBackendUpdate }: Props) {
  const webRef = useRef<WebView>(null);
  const iframeRef = useRef<any>(null);
  const readyRef = useRef(false);
  const oldestRef = useRef<number | null>(null);
  const loadingMoreRef = useRef(false);
  const [tf, setTf] = useState("1m");
  const [chartType, setChartType] = useState<"candles" | "line">("candles");
  const [loading, setLoading] = useState(true);
  const [indModal, setIndModal] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [activeInds, setActiveInds] = useState<Record<string, boolean>>({});
  const tfRef = useRef(tf);
  tfRef.current = tf;
  const saveObjTimer = useRef<any>(null);

  // Swipe on the toolbar cycles timeframes (mobile UX)
  const pan = useRef(PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 30 && Math.abs(g.dy) < 20,
    onPanResponderRelease: (_, g) => {
      if (Math.abs(g.dx) < 40) return;
      setTf((cur) => {
        const i = TIMEFRAMES.findIndex((t) => t.id === cur);
        const next = g.dx < 0 ? Math.min(i + 1, TIMEFRAMES.length - 1) : Math.max(i - 1, 0);
        return TIMEFRAMES[next].id;
      });
    },
  })).current;

  const send = useCallback((msg: any) => {
    if (Platform.OS === "web") {
      iframeRef.current?.contentWindow?.postMessage(msg, "*");
    } else {
      webRef.current?.injectJavaScript(`window.__chartRecv && window.__chartRecv(${JSON.stringify(msg)});true;`);
    }
  }, []);

  const loadCandles = useCallback(async (reset: boolean) => {
    try {
      if (reset) setLoading(true);
      const res = await forexApi.marketCandles(symbolId, tfRef.current, { limit: 300 });
      if (res.candles.length) oldestRef.current = res.candles[0].t;
      send({ type: "setCandles", candles: res.candles, volumeAvailable: res.volume_available });
    } catch (e: any) {
      console.warn("[chart] candles load failed:", e?.message || e);
    } finally {
      setLoading(false);
    }
  }, [symbolId, send]);

  const handleChartMessage = useCallback(async (msg: any) => {
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "ready") {
      readyRef.current = true;
      send({ type: "init", symbol: symbolId, decimals: priceDecimals });
      send({ type: "setChartType", value: chartType });
      loadCandles(true);
      // restore persisted drawings + indicator prefs
      try {
        const { objects } = await forexApi.getChartObjects(symbolId, chartKey);
        send({ type: "setObjects", objects });
      } catch {}
      try {
        const { prefs } = await forexApi.getChartPrefs();
        const saved = prefs?.indicators?.[chartKey] || {};
        const next: Record<string, boolean> = {};
        for (const ind of INDICATORS) {
          if (saved[ind.id]) {
            next[ind.id] = true;
            send({ type: "setIndicator", id: ind.id, enabled: true, params: { period: ind.period } });
          }
        }
        setActiveInds(next);
      } catch {}
    } else if (msg.type === "loadMore" && msg.oldestT && !loadingMoreRef.current) {
      loadingMoreRef.current = true;
      try {
        const res = await forexApi.marketCandles(symbolId, tfRef.current, { limit: 300, before: msg.oldestT });
        if (res.candles.length) oldestRef.current = Math.min(oldestRef.current || Infinity, res.candles[0].t);
        send({ type: "prepend", candles: res.candles });
      } catch {
        send({ type: "prepend", candles: [] });
      } finally {
        loadingMoreRef.current = false;
      }
    } else if (msg.type === "lineDragged" && msg.id && msg.price) {
      // Sprint 16.1 — dragging a TP/SL/pending line updates the backend instantly
      try {
        if (msg.kind === "tp" || msg.kind === "sl") {
          await forexApi.updateTPSL(msg.id, msg.kind === "tp" ? msg.price : undefined,
            msg.kind === "sl" ? msg.price : undefined);
        } else if (msg.kind === "pending") {
          await forexApi.modifyOrder(msg.id, { price: msg.price });
        }
        onBackendUpdate?.();
      } catch (e: any) {
        console.warn("[chart] drag update failed:", e?.response?.data?.detail || e?.message);
        onBackendUpdate?.(); // re-sync lines back to server truth
      }
    } else if (msg.type === "objectsChanged") {
      // debounce persistence of drawings
      if (saveObjTimer.current) clearTimeout(saveObjTimer.current);
      saveObjTimer.current = setTimeout(() => {
        forexApi.saveChartObjects(symbolId, msg.objects || [], chartKey).catch(() => {});
      }, 800);
    } else if (msg.type === "toolUsed") {
      setActiveTool(null);
      send({ type: "setTool", tool: null });
    }
  }, [symbolId, priceDecimals, chartType, chartKey, loadCandles, send, onBackendUpdate]);

  // web iframe inbound messages
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const onMsg = (ev: MessageEvent) => handleChartMessage(ev.data);
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [handleChartMessage]);

  // timeframe change
  useEffect(() => {
    if (readyRef.current) loadCandles(true);
  }, [tf, loadCandles]);

  // chart type toggle
  useEffect(() => {
    if (readyRef.current) send({ type: "setChartType", value: chartType });
  }, [chartType, send]);

  // live poll — update forming candle + bid/ask lines
  useEffect(() => {
    const t = setInterval(async () => {
      if (!readyRef.current) return;
      try {
        const res = await forexApi.marketCandles(symbolId, tfRef.current, { limit: 3 });
        send({
          type: "update",
          candles: res.candles,
          quote: res.quote ? { bid: res.quote.bid, ask: res.quote.ask } : null,
        });
      } catch {}
    }, POLL_MS);
    return () => clearInterval(t);
  }, [symbolId, send]);

  // fast bid/ask line refresh from the shared watchlist feed
  useEffect(() => {
    if (readyRef.current && quote) send({ type: "setQuote", quote: { bid: quote.bid, ask: quote.ask } });
  }, [quote?.bid, quote?.ask, send]); // eslint-disable-line react-hooks/exhaustive-deps

  // position entry lines + draggable TP/SL/pending + execution markers
  useEffect(() => {
    if (!readyRef.current) return;
    const open = openPositions.filter((p) => p.symbol_id === symbolId);
    const pending = pendingOrders.filter((o) => o.symbol_id === symbolId);
    // entry lines (static) with floating PnL
    send({
      type: "setPositions",
      positions: open.map((p) => ({
        side: p.side,
        entry: p.entry_price,
        title: `${p.side.toUpperCase()} ${p.lot_size} • ${p.pnl_inr >= 0 ? "+" : ""}${formatINR(p.pnl_inr)}`,
      })),
    });
    // draggable lines: TP/SL per position + pending order prices
    const items: any[] = [];
    open.forEach((p) => {
      if (p.tp) items.push({ id: p.position_id, kind: "tp", price: p.tp, title: `TP ${p.tp}` });
      if (p.sl) items.push({ id: p.position_id, kind: "sl", price: p.sl, title: `SL ${p.sl}` });
    });
    pending.forEach((o) => {
      items.push({
        id: o.order_id, kind: "pending", price: o.price,
        title: `${o.side.toUpperCase()} ${o.type.toUpperCase()} ${o.lot_size}`,
        color: "#29b6f6",
      });
    });
    send({ type: "setDraggable", items });
    const markers: any[] = [];
    const pushEntry = (p: Position) => {
      const t = epoch(p.opened_at);
      if (!t) return;
      markers.push({
        time: t,
        position: p.side === "buy" ? "belowBar" : "aboveBar",
        color: p.side === "buy" ? "#26a69a" : "#ef5350",
        shape: p.side === "buy" ? "arrowUp" : "arrowDown",
        text: `${p.side.toUpperCase()} ${p.lot_size}`,
      });
    };
    open.forEach(pushEntry);
    closedPositions.filter((p) => p.symbol_id === symbolId).slice(0, 20).forEach((p) => {
      pushEntry(p);
      const tc = epoch(p.closed_at);
      if (tc) markers.push({
        time: tc, position: "aboveBar", color: "#9aa0aa", shape: "circle",
        text: `CLOSE ${p.pnl_inr >= 0 ? "+" : ""}${Math.round(p.pnl_inr)}`,
      });
    });
    markers.sort((a, b) => a.time - b.time);
    send({ type: "setMarkers", markers });
  }, [openPositions, closedPositions, pendingOrders, symbolId, send]);

  // reload persisted drawings when symbol changes
  useEffect(() => {
    if (!readyRef.current) return;
    send({ type: "init", symbol: symbolId, decimals: priceDecimals });
    forexApi.getChartObjects(symbolId, chartKey)
      .then(({ objects }) => send({ type: "setObjects", objects }))
      .catch(() => send({ type: "setObjects", objects: [] }));
    loadCandles(true);
  }, [symbolId]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleIndicator = (id: string) => {
    const ind = INDICATORS.find((i) => i.id === id)!;
    const enabled = !activeInds[id];
    const next = { ...activeInds, [id]: enabled };
    setActiveInds(next);
    send({ type: "setIndicator", id, enabled, params: { period: ind.period } });
    // persist per chart
    forexApi.getChartPrefs().then(({ prefs }) => {
      const p = prefs || {};
      p.indicators = { ...(p.indicators || {}), [chartKey]: next };
      return forexApi.saveChartPrefs(p);
    }).catch(() => {});
  };

  const selectTool = (id: string) => {
    const next = activeTool === id ? null : id;
    setActiveTool(next);
    send({ type: "setTool", tool: next, text: next === "text" ? "note" : undefined });
  };

  return (
    <View style={[s.wrap, { height: height + (compact ? 40 : 44) + (toolsOpen ? 34 : 0) }]}>
      {/* Toolbar: timeframes (swipe to cycle) + indicators + tools + chart type */}
      <View style={s.toolbar} {...pan.panHandlers}>
        <View style={{ flexDirection: "row", flex: 1, gap: 2 }}>
          {TIMEFRAMES.map((t) => (
            <Pressable key={t.id} onPress={() => setTf(t.id)} testID={`tf-${t.id}`}
              style={[s.tfBtn, tf === t.id && s.tfBtnActive]}>
              <Text style={[s.tfTxt, tf === t.id && s.tfTxtActive]}>{t.label}</Text>
            </Pressable>
          ))}
        </View>
        <Pressable onPress={() => setIndModal(true)} testID="chart-indicators-btn" style={s.typeBtn}>
          <FunctionSquare size={15} color={Object.values(activeInds).some(Boolean) ? "#f0b90b" : "#7a828e"} />
        </Pressable>
        <Pressable onPress={() => setToolsOpen((v) => !v)} testID="chart-tools-btn" style={s.typeBtn}>
          <Pencil size={15} color={toolsOpen || activeTool ? "#f0b90b" : "#7a828e"} />
        </Pressable>
        <Pressable onPress={() => setChartType("candles")} testID="chart-type-candles"
          style={[s.typeBtn, chartType === "candles" && s.tfBtnActive]}>
          <CandlestickChart size={15} color={chartType === "candles" ? "#2962ff" : "#7a828e"} />
        </Pressable>
        <Pressable onPress={() => setChartType("line")} testID="chart-type-line"
          style={[s.typeBtn, chartType === "line" && s.tfBtnActive]}>
          <LineChartIcon size={15} color={chartType === "line" ? "#2962ff" : "#7a828e"} />
        </Pressable>
      </View>

      {/* Drawing tools row */}
      {toolsOpen ? (
        <View style={s.toolsRow}>
          {TOOLS.map((t) => (
            <Pressable key={t.id} onPress={() => selectTool(t.id)} testID={`tool-${t.id}`}
              style={[s.toolBtn, activeTool === t.id && s.tfBtnActive]}>
              <Text style={[s.tfTxt, activeTool === t.id && s.tfTxtActive]}>{t.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {/* Indicators modal */}
      <Modal visible={indModal} transparent animationType="fade" onRequestClose={() => setIndModal(false)}>
        <Pressable style={s.modalBg} onPress={() => setIndModal(false)}>
          <Pressable style={s.modalCard} onPress={() => {}}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={s.modalTitle}>Indicators</Text>
              <Pressable onPress={() => setIndModal(false)} hitSlop={10}><X size={18} color="#7a828e" /></Pressable>
            </View>
            <ScrollView style={{ maxHeight: 340 }}>
              {INDICATORS.map((ind) => (
                <Pressable key={ind.id} onPress={() => toggleIndicator(ind.id)} testID={`ind-${ind.id}`}
                  style={s.indRow}>
                  <View>
                    <Text style={{ color: "#d1d4dc", fontSize: 14, fontWeight: "600" }}>
                      {ind.label}{ind.period ? ` (${ind.period})` : ""}
                    </Text>
                    <Text style={{ color: "#5d6570", fontSize: 10 }}>
                      {ind.overlay ? "Overlay on price" : "Sub-pane oscillator"}
                    </Text>
                  </View>
                  <View style={[s.dot, { backgroundColor: activeInds[ind.id] ? "#26a69a" : "#2b3648" }]} />
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* Chart surface */}
      <View style={{ flex: 1, backgroundColor: "#0e1117" }}>
        {Platform.OS === "web" ? (
          React.createElement("iframe", {
            ref: iframeRef,
            src: CHART_URL,
            style: { border: 0, width: "100%", height: "100%", background: "#0e1117" },
            title: "trading-chart",
          })
        ) : (
          <WebView
            ref={webRef}
            source={{ uri: CHART_URL }}
            onMessage={(e) => {
              try { handleChartMessage(JSON.parse(e.nativeEvent.data)); } catch {}
            }}
            style={{ backgroundColor: "#0e1117" }}
            javaScriptEnabled
            domStorageEnabled
            bounces={false}
            scrollEnabled={false}
            overScrollMode="never"
            setBuiltInZoomControls={false}
            allowsInlineMediaPlayback
          />
        )}
        {loading ? (
          <View style={s.loader} pointerEvents="none">
            <ActivityIndicator color="#2962ff" />
          </View>
        ) : null}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { borderRadius: 14, overflow: "hidden", backgroundColor: "#0e1117", borderWidth: 1, borderColor: "#1c2230" },
  toolbar: { flexDirection: "row", alignItems: "center", paddingHorizontal: 6, paddingVertical: 6, gap: 4, backgroundColor: "#12161f" },
  tfBtn: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 7, minWidth: 32, alignItems: "center" },
  tfBtnActive: { backgroundColor: "#2962ff22" },
  tfTxt: { color: "#7a828e", fontSize: 11, fontWeight: "700" },
  tfTxtActive: { color: "#2962ff" },
  typeBtn: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 7 },
  toolsRow: { flexDirection: "row", gap: 4, paddingHorizontal: 6, paddingBottom: 6, backgroundColor: "#12161f", flexWrap: "wrap" },
  toolBtn: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 7, backgroundColor: "#1a2030" },
  modalBg: { flex: 1, backgroundColor: "#000a", justifyContent: "center", padding: 24 },
  modalCard: { backgroundColor: "#151a24", borderRadius: 14, padding: 16, gap: 8, borderWidth: 1, borderColor: "#232b3b" },
  modalTitle: { color: "#d1d4dc", fontSize: 16, fontWeight: "800", marginBottom: 6 },
  indRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#1c2230" },
  dot: { width: 14, height: 14, borderRadius: 7 },
  loader: { position: "absolute", inset: 0 as any, alignItems: "center", justifyContent: "center", backgroundColor: "#0e111788" },
});
