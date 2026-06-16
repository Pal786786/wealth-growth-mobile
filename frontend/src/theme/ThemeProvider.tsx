import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useColorScheme } from "react-native";
import { storage } from "@/src/utils/storage";
import { getPalette, Palette, ThemeMode } from "./colors";

type Ctx = {
  mode: ThemeMode;
  palette: Palette;
  toggle: () => void;
  setMode: (m: ThemeMode) => void;
};

const ThemeCtx = createContext<Ctx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>("light");

  useEffect(() => {
    (async () => {
      const stored = await storage.getItem<string>("mfb_theme", "");
      if (stored === "light" || stored === "dark") setModeState(stored);
      else if (system === "dark") setModeState("dark");
    })();
  }, [system]);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    storage.setItem("mfb_theme", m);
  }, []);

  const toggle = useCallback(() => setMode(mode === "light" ? "dark" : "light"), [mode, setMode]);

  return (
    <ThemeCtx.Provider value={{ mode, palette: getPalette(mode), toggle, setMode }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
