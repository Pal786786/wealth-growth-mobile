import React, { useMemo } from "react";
import { View, StyleSheet } from "react-native";
import Svg, { Path, Defs, LinearGradient as SvgLinearGradient, Stop, Circle } from "react-native-svg";
import { useTheme } from "@/src/theme/ThemeProvider";

// Tiny inline area sparkline (used in hero cards, stock cards)
export function Sparkline({
  data,
  width = 140,
  height = 50,
  positive = true,
  strokeWidth = 2.2,
  color,
}: {
  data?: number[];
  width?: number;
  height?: number;
  positive?: boolean;
  strokeWidth?: number;
  color?: string;
}) {
  const { palette } = useTheme();
  const stroke = color || (positive ? palette.success : palette.danger);

  const points = useMemo(() => {
    const series = data && data.length >= 2 ? data : autoSeries(positive);
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = max - min || 1;
    const n = series.length;
    const stepX = width / (n - 1);
    return series.map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 8) - 4;
      return { x, y };
    });
  }, [data, width, height, positive]);

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(" ");

  const areaPath = `${linePath} L ${width} ${height} L 0 ${height} Z`;

  const id = `sparkfill-${positive ? "up" : "dn"}`;

  return (
    <View style={[s.wrap, { width, height }]}>
      <Svg width={width} height={height}>
        <Defs>
          <SvgLinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0%" stopColor={stroke} stopOpacity="0.32" />
            <Stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </SvgLinearGradient>
        </Defs>
        <Path d={areaPath} fill={`url(#${id})`} />
        <Path d={linePath} stroke={stroke} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        {points.length ? (
          <Circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={3} fill={stroke} />
        ) : null}
      </Svg>
    </View>
  );
}

function autoSeries(positive: boolean): number[] {
  // deterministic-ish "stock-like" series so the line looks alive without re-rendering randomly
  const base = positive ? [10, 12, 11, 14, 13, 17, 16, 19, 22, 24, 23, 27] : [27, 25, 26, 22, 23, 19, 20, 17, 14, 13, 15, 11];
  return base;
}

const s = StyleSheet.create({
  wrap: { overflow: "hidden" },
});
