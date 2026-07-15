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
import { View, Text, Pressable, Platform, StyleSheet, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";
import { CandlestickChart, LineChart as LineChartIcon } from "lucide-react-native";
import { forexApi, Position, ForexQuote } from "@/src/api/forex";
import { BACKEND_URL } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";

const CHART_URL = `${BACKEND_URL.replace(/\/+$/, "")}/api/chart/index.html`;
const TIMEFRAMES: { id: string; label: string }[] = [
  { id: "1m", label: "1m" }, { id: "5m", label: "5m" }, { id: "15m", label: "15m" },
  { id: "30m", label: "30m" }, { id: "1h", label: "1H" }, { id: "4h", label: "4H" },
  { id: "1d", label: "D1" },
];
const POLL_MS = 4000;

type Props = {
  symbolId: string;
  priceDecimals: number;
  quote?: ForexQuote | null;
  openPositions?: Position[];
  closedPositions?: Position[];
  height?: number;
};

function epoch(iso?: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? Math.floor(t / 1000) : null;
}

export function TradingChart({ symbolId, priceDecimals, quote, openPositions = [], closedPositions = [], height = 380 }: Props) {
  const webRef = useRef<WebView>(null);
  const iframeRef = useRef<any>(null);
  const readyRef = useRef(false);
  const oldestRef = useRef<number | null>(null);
  const loadingMoreRef = useRef(false);
  const [tf, setTf] = useState("1m");
  const [chartType, setChartType] = useState<"candles" | "line">("candles");
  const [loading, setLoading] = useState(true);
  const tfRef = useRef(tf);
  tfRef.current = tf;

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
    }
  }, [symbolId, priceDecimals, chartType, loadCandles, send]);

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

  // position entry/TP/SL lines + buy/sell execution markers
  useEffect(() => {
    if (!readyRef.current) return;
    const open = openPositions.filter((p) => p.symbol_id === symbolId);
    send({
      type: "setPositions",
      positions: open.map((p) => ({
        side: p.side,
        entry: p.entry_price,
        tp: p.tp,
        sl: p.sl,
        title: `${p.side.toUpperCase()} ${p.lot_size} • ${p.pnl_inr >= 0 ? "+" : ""}${formatINR(p.pnl_inr)}`,
      })),
    });
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
  }, [openPositions, closedPositions, symbolId, send]);

  return (
    <View style={[s.wrap, { height: height + 44 }]}>
      {/* Toolbar: timeframes + chart type */}
      <View style={s.toolbar}>
        <View style={{ flexDirection: "row", flex: 1, gap: 2 }}>
          {TIMEFRAMES.map((t) => (
            <Pressable key={t.id} onPress={() => setTf(t.id)} testID={`tf-${t.id}`}
              style={[s.tfBtn, tf === t.id && s.tfBtnActive]}>
              <Text style={[s.tfTxt, tf === t.id && s.tfTxtActive]}>{t.label}</Text>
            </Pressable>
          ))}
        </View>
        <Pressable onPress={() => setChartType("candles")} testID="chart-type-candles"
          style={[s.typeBtn, chartType === "candles" && s.tfBtnActive]}>
          <CandlestickChart size={15} color={chartType === "candles" ? "#2962ff" : "#7a828e"} />
        </Pressable>
        <Pressable onPress={() => setChartType("line")} testID="chart-type-line"
          style={[s.typeBtn, chartType === "line" && s.tfBtnActive]}>
          <LineChartIcon size={15} color={chartType === "line" ? "#2962ff" : "#7a828e"} />
        </Pressable>
      </View>

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
  loader: { position: "absolute", inset: 0 as any, alignItems: "center", justifyContent: "center", backgroundColor: "#0e111788" },
});
