// Brand theme tokens for My Funding Bank
export const Colors = {
  brand: {
    primary: "#38BDF8",      // Sky Blue
    secondary: "#0EA5E9",    // Deep Blue
    accent: "#7DD3FC",       // Light Blue
    navy: "#0F172A",
  },
  semantic: {
    success: "#10B981",
    danger: "#EF4444",
    warning: "#F59E0B",
    bullEye: "#FF2D2D",
  },
  light: {
    background: "#F8FAFC",
    surface: "#FFFFFF",
    surfaceAlt: "#F1F5F9",
    surfaceGlass: "rgba(255,255,255,0.85)",
    textPrimary: "#0F172A",
    textSecondary: "#475569",
    textMuted: "#94A3B8",
    border: "#E2E8F0",
    borderStrong: "#CBD5E1",
    cardShadow: "rgba(15,23,42,0.08)",
  },
  dark: {
    background: "#0B1220",
    surface: "#111827",
    surfaceAlt: "#1E293B",
    surfaceGlass: "rgba(15,23,42,0.85)",
    textPrimary: "#F8FAFC",
    textSecondary: "#CBD5E1",
    textMuted: "#64748B",
    border: "#1E293B",
    borderStrong: "#334155",
    cardShadow: "rgba(0,0,0,0.5)",
  },
};

export type ThemeMode = "light" | "dark";

export function getPalette(mode: ThemeMode) {
  return {
    ...Colors.brand,
    ...Colors.semantic,
    ...Colors[mode],
    mode,
  };
}

export type Palette = ReturnType<typeof getPalette>;

export const Radius = { sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, pill: 999 };
export const Spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
