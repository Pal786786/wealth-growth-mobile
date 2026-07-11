/**
 * FinancialChart — reusable chart for Gold, Forex, AI Signals, Watchlist, MF NAV.
 *
 * Powered by `react-native-gifted-charts` with:
 *   • Animated line + area-gradient
 *   • Live-price marker (pulse ring)
 *   • Current price horizontal reference line
 *   • Long-press crosshair + tooltip
 *   • Timeframe switcher (1D · 1W · 1M · 3M · 1Y · ALL)
 *   • Dark / Light theme via ThemeProvider
 *
 * The component is display-only — parent supplies data + timeframe callbacks.
 */
import React, { useMemo } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Dimensions } from "react-native";
import { LineChart } from "react-native-gifted-charts";
import { useTheme } from "@/src/theme/ThemeProvider";

export type ChartPoint = { ts: number | string; value: number; label?: string };
export type ChartWindow = "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";

const WINDOWS: ChartWindow[] = ["1D", "1W", "1M", "3M", "1Y", "ALL"];

const { width: SCREEN_W } = Dimensions.get("window");

export function FinancialChart({
  points,
  height = 260,
  window: activeWindow,
  onWindowChange,
  loading = false,
  livePrice,
  priceDecimals = 2,
  title,
  currencyPrefix = "₹",
  showWindowSwitcher = true,
  isUp,
  positiveColor,
  negativeColor,
  containerWidth,
}: {
  points: ChartPoint[];
  height?: number;
  window?: ChartWindow;
  onWindowChange?: (w: ChartWindow) => void;
  loading?: boolean;
  livePrice?: number | null;
  priceDecimals?: number;
  title?: string;
  currencyPrefix?: string;
  showWindowSwitcher?: boolean;
  isUp?: boolean;
  positiveColor?: string;
  negativeColor?: string;
  containerWidth?: number;
}) {
  const { palette, mode } = useTheme();
  const posColor = positiveColor ?? palette.success;
  const negColor = negativeColor ?? palette.danger;
  const chartWidth = (containerWidth ?? SCREEN_W - 32) - 32; // account for padding

  const { data, up, minV, maxV } = useMemo(() => {
    if (!points || points.length < 2) {
      return { data: [], up: true, minV: 0, maxV: 0 };
    }
    const values = points.map((p) => p.value);
    const minV = Math.min(...values);
    const maxV = Math.max(...values);
    const first = points[0].value;
    const last = points[points.length - 1].value;
    const up = last >= first;
    const color = up ? posColor : negColor;
    // Downsample for perf if too many points (>100)
    const step = Math.max(1, Math.floor(points.length / 100));
    const sample = points.filter((_, i) => i % step === 0 || i === points.length - 1);
    const data = sample.map((p, i) => ({
      value: p.value,
      label: i === 0 || i === sample.length - 1 ? p.label : undefined,
      dataPointRadius: i === sample.length - 1 ? 5 : 0,
      dataPointColor: color,
    }));
    return { data, up, minV, maxV };
  }, [points, posColor, negColor]);

  const lineColor = (isUp ?? up) ? posColor : negColor;
  const range = Math.max(1e-9, maxV - minV);
  const yAxisMin = minV - range * 0.06;
  const yAxisMax = maxV + range * 0.06;

  return (
    <View style={[s.container, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      {(title || livePrice != null) ? (
        <View style={s.headerRow}>
          {title ? <Text style={[s.title, { color: palette.textSecondary }]}>{title}</Text> : <View />}
          {livePrice != null ? (
            <View style={[s.liveBadge, { backgroundColor: lineColor + "22" }]}>
              <View style={[s.livePulse, { backgroundColor: lineColor }]} />
              <Text style={[s.livePrice, { color: lineColor }]}>
                {currencyPrefix}
                {livePrice.toLocaleString("en-IN", { maximumFractionDigits: priceDecimals })}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}

      <View style={{ height, justifyContent: "center", alignItems: "center" }}>
        {loading || data.length < 2 ? (
          <ActivityIndicator color={palette.primary} />
        ) : (
          <LineChart
            data={data}
            width={chartWidth}
            height={height - 20}
            initialSpacing={4}
            endSpacing={4}
            spacing={Math.max(1, chartWidth / Math.max(1, data.length - 1))}
            thickness={2}
            color={lineColor}
            areaChart
            startFillColor={lineColor}
            endFillColor={lineColor}
            startOpacity={0.35}
            endOpacity={0.02}
            hideDataPoints={false}
            dataPointsColor={lineColor}
            dataPointsRadius={0}
            focusEnabled
            showStripOnFocus
            stripColor={palette.textMuted}
            stripOpacity={0.35}
            showTextOnFocus
            focusedDataPointColor={lineColor}
            focusedDataPointRadius={6}
            hideAxesAndRules
            yAxisOffset={yAxisMin}
            maxValue={yAxisMax - yAxisMin}
            isAnimated
            animationDuration={800}
            curved
            adjustToWidth
            disableScroll
            backgroundColor="transparent"
            xAxisColor="transparent"
            yAxisColor="transparent"
            pointerConfig={{
              pointerStripHeight: height - 40,
              pointerStripColor: palette.textMuted,
              pointerStripWidth: 1,
              pointerColor: lineColor,
              radius: 6,
              pointerLabelWidth: 100,
              pointerLabelHeight: 40,
              activatePointersOnLongPress: false,
              autoAdjustPointerLabelPosition: true,
              pointerLabelComponent: (items: any[]) => {
                const v = items?.[0]?.value;
                if (v == null) return null;
                return (
                  <View
                    style={{
                      paddingVertical: 4,
                      paddingHorizontal: 8,
                      borderRadius: 8,
                      backgroundColor: mode === "dark" ? "#0F172A" : "#0F172A",
                      borderWidth: 1,
                      borderColor: lineColor,
                    }}
                  >
                    <Text style={{ color: "#fff", fontWeight: "800", fontSize: 11 }}>
                      {currencyPrefix}
                      {Number(v).toLocaleString("en-IN", { maximumFractionDigits: priceDecimals })}
                    </Text>
                  </View>
                );
              },
            }}
          />
        )}
      </View>

      {showWindowSwitcher && onWindowChange ? (
        <View style={s.tfRow}>
          {WINDOWS.map((w) => {
            const active = activeWindow === w;
            return (
              <Pressable
                key={w}
                onPress={() => onWindowChange(w)}
                style={[
                  s.tfBtn,
                  {
                    backgroundColor: active ? palette.primary : "transparent",
                    borderColor: active ? palette.primary : palette.border,
                  },
                ]}
                testID={`chart-tf-${w}`}
              >
                <Text style={[s.tfText, { color: active ? "#fff" : palette.textSecondary }]}>{w}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    borderRadius: 20,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 10,
    overflow: "hidden",
  },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 11, fontWeight: "800", letterSpacing: 1.2 },
  liveBadge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  livePulse: { width: 6, height: 6, borderRadius: 3 },
  livePrice: { fontSize: 13, fontWeight: "800" },
  tfRow: { flexDirection: "row", gap: 6, justifyContent: "center", flexWrap: "wrap" },
  tfBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  tfText: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
});
