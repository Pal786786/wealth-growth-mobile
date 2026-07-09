import { api } from "./client";

export type Timeframe = "M5" | "M15" | "M30" | "H1" | "H4" | "D1";
export type Side = "buy" | "sell" | "hold";
export type SignalStrength = "weak" | "moderate" | "strong" | "very_strong";
export type AlertType = "price_above" | "price_below" | "percent_move" | "indicator_cross" | "rsi_alert";

export type SignalListRow = {
  symbol: string; display: string; asset_class: string; category: string;
  timeframe: Timeframe; side: Side;
  entry: number; stop_loss: number | null;
  tp1: number | null; tp2: number | null; tp3: number | null;
  risk_reward_ratio: number; confidence_pct: number;
  trend: "bullish" | "bearish" | "neutral";
  signal_strength: SignalStrength;
  expires_at: string | null; generated_at: string;
  bar_index: number; risk_pips?: number;
};

export type IndicatorPack = {
  price: number; ema20: number; ema50: number; ema200: number;
  rsi: number; adx: number; vwap: number; atr: number; volatility_pct: number;
  macd: { macd: number; signal: number; hist: number };
  bollinger: { upper: number; middle: number; lower: number; width_pct: number };
  supertrend: { value: number; direction: "up" | "down" };
  trend: "bullish" | "bearish" | "neutral";
};

export type IndicatorRow = { name: string; value: string; verdict: string };

export type SignalDetail = SignalListRow & {
  ai_explanation?: string | null;
  reason_hits?: string[];
  indicators?: IndicatorPack;
  indicator_summary?: IndicatorRow[];
};

export type WatchlistItem = {
  symbol: string; display: string; name: string;
  category: string; asset_class: string;
  price: number; trend: string; signal: Side;
  confidence_pct: number; signal_strength: SignalStrength;
  volatility_pct: number; daily_change_pct: number; weekly_change_pct: number;
};

export type Alert = {
  alert_id: string; user_id: string; symbol: string; type: AlertType;
  status: "active" | "paused" | "triggered";
  created_at: string; updated_at: string;
  triggered_at?: string | null; trigger_price?: number | null; trigger_note?: string;
  last_price?: number; note?: string; repeat?: boolean;
  // Type-specific
  target_price?: number; target_percent?: number; anchor_price?: number;
  fast_ema?: number; slow_ema?: number; threshold?: number;
  direction?: string; timeframe?: Timeframe;
};

export const aiApi = {
  meta: async () => (await api.get("/ai/meta")).data,

  signals: async (opts: { timeframe?: Timeframe; asset_class?: string; min_confidence?: number; side?: Side; limit?: number } = {}) =>
    (await api.get("/ai/signals", { params: opts })).data as { signals: SignalListRow[]; count: number; timeframe: Timeframe },

  signal: async (symbol: string, timeframe: Timeframe = "H1", with_ai: boolean = true) =>
    (await api.get(`/ai/signals/${symbol}`, { params: { timeframe, with_ai } })).data as SignalDetail,

  indicators: async (symbol: string, timeframe: Timeframe = "H1") =>
    (await api.get(`/ai/indicators/${symbol}`, { params: { timeframe } })).data,

  watchlist: async () => (await api.get("/ai/watchlist")).data as { items: WatchlistItem[] },
  addWatchlist: async (symbol: string) => (await api.post("/ai/watchlist", { symbol })).data,
  removeWatchlist: async (symbol: string) => (await api.delete(`/ai/watchlist/${symbol}`)).data,

  alerts: async (status?: string) =>
    (await api.get("/ai/alerts", { params: status ? { status } : {} })).data as { alerts: Alert[]; count: number },
  createAlert: async (payload: Partial<Alert>) =>
    (await api.post("/ai/alerts", payload)).data as { alert: Alert },
  deleteAlert: async (alert_id: string) => (await api.delete(`/ai/alerts/${alert_id}`)).data,
  pauseAlert: async (alert_id: string) => (await api.post(`/ai/alerts/${alert_id}/pause`)).data,
  resumeAlert: async (alert_id: string) => (await api.post(`/ai/alerts/${alert_id}/resume`)).data,
};

// Helpers
export const sideColor = (side: Side, palette: any) =>
  side === "buy" ? palette.success : side === "sell" ? palette.danger : palette.textMuted;

export const confidenceLabel = (n: number) =>
  n >= 85 ? "Very High" : n >= 70 ? "High" : n >= 55 ? "Medium" : "Low";
