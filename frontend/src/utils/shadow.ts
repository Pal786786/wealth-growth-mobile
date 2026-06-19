import { Platform } from "react-native";

/**
 * Cross-platform shadow helper.
 *
 * React Native Web has deprecated `shadow*` props in favour of CSS `boxShadow`.
 * On native (iOS/Android) we still need the legacy props plus `elevation`.
 *
 * Usage:
 *   ...shadow({ color: "#7C3AED", opacity: 0.25, radius: 14, offsetY: 6, elevation: 4 })
 */
export function shadow(opts: {
  color?: string;
  opacity?: number;
  radius?: number;
  offsetX?: number;
  offsetY?: number;
  elevation?: number;
} = {}) {
  const {
    color = "#000",
    opacity = 0.1,
    radius = 8,
    offsetX = 0,
    offsetY = 4,
    elevation,
  } = opts;

  if (Platform.OS === "web") {
    const rgba = hexToRgba(color, opacity);
    return { boxShadow: `${offsetX}px ${offsetY}px ${radius}px ${rgba}` } as const;
  }

  return {
    shadowColor: color,
    shadowOpacity: opacity,
    shadowRadius: radius,
    shadowOffset: { width: offsetX, height: offsetY },
    elevation: elevation ?? Math.max(1, Math.round(radius / 2)),
  } as const;
}

/**
 * Cross-platform text glow helper.
 * On web maps to `text-shadow` via the `textShadow` style; on native uses
 * the legacy textShadow* props.
 */
export function textGlow(opts: { color?: string; radius?: number; opacity?: number } = {}) {
  const { color = "#fff", radius = 10, opacity = 0.6 } = opts;
  if (Platform.OS === "web") {
    return { textShadow: `0px 0px ${radius}px ${hexToRgba(color, opacity)}` } as const;
  }
  return {
    textShadowColor: color,
    textShadowRadius: radius,
    textShadowOffset: { width: 0, height: 0 },
  } as const;
}

function hexToRgba(hex: string, alpha: number): string {
  // Already rgba/rgb? Use as-is.
  if (hex.startsWith("rgb")) return hex;
  let h = hex.replace("#", "");
  if (h.length === 3) {
    h = h.split("").map((c) => c + c).join("");
  }
  if (h.length !== 6) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
