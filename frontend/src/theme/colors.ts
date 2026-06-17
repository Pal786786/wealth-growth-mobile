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
    surfaceElevated: "#FFFFFF",
    textPrimary: "#0F172A",
    textSecondary: "#475569",
    textMuted: "#94A3B8",
    textInverse: "#FFFFFF",
    border: "#E2E8F0",
    borderStrong: "#CBD5E1",
    cardShadow: "rgba(15,23,42,0.08)",
    overlay: "rgba(15,23,42,0.4)",
    chipBg: "#F1F5F9",
    chipBorder: "#E2E8F0",
    successBg: "#DCFCE7",
    dangerBg: "#FEE2E2",
    warningBg: "#FEF3C7",
    infoBg: "#DBEAFE",
    heroGradStart: "#38BDF8",
    heroGradEnd: "#0EA5E9",
  },
  dark: {
    // Premium fintech-dark: deep navy with subtle blue tints, never pure black
    background: "#070B17",        // very deep navy
    surface: "#0F172A",           // card base
    surfaceAlt: "#1A2236",        // slightly lighter for nested cards
    surfaceGlass: "rgba(15,23,42,0.88)",
    surfaceElevated: "#1E293B",   // modals, sheets
    textPrimary: "#F1F5F9",       // 14.5:1 contrast — WCAG AAA
    textSecondary: "#94A3B8",     // 5.8:1 — WCAG AA
    textMuted: "#64748B",         // 3.9:1 — labels only
    textInverse: "#0F172A",
    border: "#1E293B",
    borderStrong: "#334155",
    cardShadow: "rgba(0,0,0,0.45)",
    overlay: "rgba(2,6,23,0.7)",
    chipBg: "#1E293B",
    chipBorder: "#334155",
    successBg: "rgba(16,185,129,0.18)",
    dangerBg: "rgba(239,68,68,0.18)",
    warningBg: "rgba(245,158,11,0.18)",
    infoBg: "rgba(56,189,248,0.18)",
    heroGradStart: "#0EA5E9",
    heroGradEnd: "#1E40AF",
  },
};

export type ThemeMode = "light" | "dark";

export function getPalette(mode: ThemeMode) {
  return {
    ...Colors.brand,
    ...Colors.semantic,
    ...Colors[mode],
    mode,
    isDark: mode === "dark",
  };
}

export type Palette = ReturnType<typeof getPalette>;

export const Radius = { sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, pill: 999 };
export const Spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
