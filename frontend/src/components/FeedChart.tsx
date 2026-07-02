/**
 * FeedChart — lightweight SVG line/area chart driven by our OWN forex feed.
 *
 * Why not TradingView?
 *   TradingView widgets show REAL live market data. Our watchlist and order
 *   screens use the simulated feed (`/api/forex/prices`). That guaranteed a
 *   price mismatch (e.g. XAU/USD 2340 on our feed vs 4070 live on chart).
 *
 * How this stays in sync:
 *   1. On mount we fetch the last N (ts, mid) points from `/api/forex/candles/{id}`.
 *   2. Every 2s we append the current `quote.mid` we get from the polling hook.
 *   3. Same feed → same numbers everywhere.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator } from "react-native";
import Svg, { Path, Line, Defs, LinearGradient, Stop, Circle, Text as SvgText } from "react-native-svg";
import { forexApi, ForexQuote } from "@/src/api/forex";
import { useTheme } from "@/src/theme/ThemeProvider";

type Point = { ts: number; mid: number };

export function FeedChart({
  symbolId,
  quote,
  priceDecimals = 2,
  height = 220,
}: {
  symbolId: string;
  quote?: ForexQuote;
  priceDecimals?: number;
  height?: number;
}) {
  const { palette, mode } = useTheme();
  const [points, setPoints] = useState<Point[]>([]);
  const [loading, setLoading] = useState(true);
  const [width, setWidth] = useState(0);
  const lastTsRef = useRef<number>(0);

  // Initial load of history
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await forexApi.candles(symbolId, 150);
        if (cancelled) return;
        setPoints(r.points || []);
        if (r.points && r.points.length) {
          lastTsRef.current = r.points[r.points.length - 1].ts;
        }
      } catch (e) {
        console.warn("[FeedChart] history load failed", e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [symbolId]);

  // Append new live points from the shared price hook
  const qMid = quote?.mid;
  const qTs = quote?.ts;
  useEffect(() => {
    if (!qMid) return;
    const ts = qTs || Date.now() / 1000;
    if (ts <= lastTsRef.current) return;
    lastTsRef.current = ts;
    setPoints((prev) => {
      const next = [...prev, { ts, mid: qMid }];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
  }, [qTs, qMid]);

  const view = useMemo(() => {
    if (points.length < 2) {
      return null;
    }
    const w = width;
    const h = height;
    const padTop = 18;
    const padBottom = 22;
    const padLeft = 8;
    const padRight = 44; // room for the price label on the right
    const iw = Math.max(1, w - padLeft - padRight);
    const ih = Math.max(1, h - padTop - padBottom);

    const mids = points.map((p) => p.mid);
    const min = Math.min(...mids);
    const max = Math.max(...mids);
    const range = Math.max(1e-9, max - min);
    // Add a bit of vertical breathing space
    const yMin = min - range * 0.05;
    const yMax = max + range * 0.05;
    const yRange = yMax - yMin;

    const x = (i: number) => padLeft + (i / (points.length - 1)) * iw;
    const y = (v: number) => padTop + (1 - (v - yMin) / yRange) * ih;

    const linePath = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(p.mid).toFixed(2)}`)
      .join(" ");
    const areaPath =
      `M ${x(0).toFixed(2)} ${y(points[0].mid).toFixed(2)} ` +
      points.map((p, i) => `L ${x(i).toFixed(2)} ${y(p.mid).toFixed(2)}`).join(" ") +
      ` L ${x(points.length - 1).toFixed(2)} ${(padTop + ih).toFixed(2)}` +
      ` L ${padLeft} ${(padTop + ih).toFixed(2)} Z`;

    const first = points[0].mid;
    const last = points[points.length - 1].mid;
    const up = last >= first;
    const lineColor = up ? palette.success : palette.danger;
    const areaColor = up ? "#10B981" : "#EF4444";

    const lastX = x(points.length - 1);
    const lastY = y(last);

    // Y-axis reference lines (3 horizontal grid lines)
    const gridLines = [0.25, 0.5, 0.75].map((f) => padTop + f * ih);
    const gridValues = [0.25, 0.5, 0.75].map((f) => yMin + (1 - f) * yRange);

    return {
      w, h, padLeft, padTop, ih, padBottom, padRight,
      linePath, areaPath, areaColor, lineColor,
      lastX, lastY, last, first, up,
      gridLines, gridValues,
      yMin, yMax,
    };
  }, [points, width, height, palette]);

  return (
    <View
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      style={[styles.container, { height, backgroundColor: mode === "dark" ? "#0F172A" : "#F8FAFC" }]}
    >
      {/* Corner labels */}
      <View style={styles.badge}>
        <View style={[styles.dot, { backgroundColor: palette.primary }]} />
        <Text style={[styles.badgeText, { color: palette.textPrimary }]}>DEMO FEED · LIVE</Text>
      </View>

      {loading || !view || width === 0 ? (
        <View style={styles.center}><ActivityIndicator color={palette.primary} /></View>
      ) : (
        <Svg width={view.w} height={view.h}>
          <Defs>
            <LinearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={view.areaColor} stopOpacity="0.35" />
              <Stop offset="1" stopColor={view.areaColor} stopOpacity="0" />
            </LinearGradient>
          </Defs>
          {/* Grid */}
          {view.gridLines.map((gy, idx) => (
            <React.Fragment key={idx}>
              <Line
                x1={view.padLeft}
                x2={view.w - view.padRight}
                y1={gy}
                y2={gy}
                stroke={mode === "dark" ? "#1E293B" : "#E2E8F0"}
                strokeDasharray="3 4"
                strokeWidth={1}
              />
              <SvgText
                x={view.w - view.padRight + 4}
                y={gy + 3}
                fontSize="9"
                fontWeight="700"
                fill={palette.textMuted}
              >
                {view.gridValues[idx].toFixed(priceDecimals)}
              </SvgText>
            </React.Fragment>
          ))}
          {/* Area */}
          <Path d={view.areaPath} fill="url(#grad)" />
          {/* Line */}
          <Path d={view.linePath} stroke={view.lineColor} strokeWidth={2} fill="none" strokeLinejoin="round" />
          {/* Latest point marker */}
          <Circle cx={view.lastX} cy={view.lastY} r={4} fill={view.lineColor} />
          <Circle cx={view.lastX} cy={view.lastY} r={9} fill={view.lineColor} opacity={0.18} />
          {/* Latest price label */}
          <SvgText
            x={view.w - view.padRight + 4}
            y={view.lastY + 3}
            fontSize="11"
            fontWeight="800"
            fill={view.lineColor}
          >
            {view.last.toFixed(priceDecimals)}
          </SvgText>
        </Svg>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 16,
    overflow: "hidden",
    justifyContent: "center",
    position: "relative",
  },
  center: { alignItems: "center", justifyContent: "center", flex: 1 },
  badge: {
    position: "absolute",
    top: 8,
    left: 10,
    zIndex: 2,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
    backgroundColor: "rgba(0,0,0,0.06)",
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  badgeText: { fontSize: 9, fontWeight: "800", letterSpacing: 0.6 },
});
