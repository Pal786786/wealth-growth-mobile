/**
 * Forex API client + types.
 */
import { api } from "./client";

export type Side = "buy" | "sell";
export type PositionStatus = "open" | "closed" | "cancelled";

export type ForexSymbol = {
  id: string;
  display: string;
  name: string;
  asset_class: "forex" | "crypto" | "metals";
  pip_size: number;
  contract_size: number;
  price_decimals: number;
  enabled: boolean;
  spread_pips: number;
  min_lot: number;
  max_lot: number;
};

export type ForexConfig = {
  enabled: boolean;
  demo_mode: boolean;
  live_mode: boolean;
  margin_per_lot: number;
  usd_inr: number;
  symbols: ForexSymbol[];
};

export type ForexQuote = {
  symbol_id: string;
  display: string;
  bid: number;
  ask: number;
  mid: number;
  ts: number;
  source: string;
  age_ms: number;
  price_decimals: number;
};

export type Position = {
  position_id: string;
  user_id: string;
  symbol_id: string;
  side: Side;
  lot_size: number;
  entry_price: number;
  current_price: number;
  tp: number | null;
  sl: number | null;
  margin_inr: number;
  pnl_inr: number;
  status: PositionStatus;
  opened_at: string;
  closed_at: string | null;
  close_price: number | null;
  close_reason: string | null;
  contract_size: number;
};

export const forexApi = {
  symbols: async (): Promise<ForexConfig> => (await api.get("/forex/symbols")).data,
  prices: async (): Promise<{ prices: ForexQuote[]; ts_now: string; diagnostics: any }> =>
    (await api.get("/forex/prices")).data,
  candles: async (symbolId: string, limit = 100): Promise<{ symbol_id: string; points: { ts: number; mid: number }[]; price_decimals: number }> =>
    (await api.get(`/forex/candles/${encodeURIComponent(symbolId)}`, { params: { limit } })).data,
  balance: async (): Promise<{ balance: number; currency: string }> =>
    (await api.get("/forex/balance")).data,
  equity: async (): Promise<{ balance: number; unrealized_pnl: number; equity: number; margin_used: number; free_margin: number; open_position_count: number; currency: string }> =>
    (await api.get("/forex/equity")).data,
  resetBalance: async (): Promise<{ balance: number; currency: string; reset_id?: string }> =>
    (await api.post("/forex/balance/reset")).data,
  demoReset: async (): Promise<{
    reset_id: string; previous_balance: number; new_balance: number; currency: string;
    positions_closed: number; orders_cancelled: number; copy_trades_closed: number;
  }> => (await api.post("/demo/reset")).data,
  demoResetHistory: async (): Promise<{ items: any[] }> =>
    (await api.get("/demo/reset/history")).data,
  openPosition: async (p: {
    symbol_id: string; side: Side; lot_size: number; tp?: number | null; sl?: number | null;
  }): Promise<Position> => (await api.post("/forex/positions", p)).data,
  listPositions: async (status: PositionStatus = "open"): Promise<Position[]> =>
    (await api.get("/forex/positions", { params: { status } })).data,
  closePosition: async (positionId: string): Promise<Position> =>
    (await api.post(`/forex/positions/${positionId}/close`)).data,
  updateTPSL: async (positionId: string, tp?: number | null, sl?: number | null): Promise<Position> =>
    (await api.put(`/forex/positions/${positionId}`, { tp, sl })).data,
  history: async (limit = 100): Promise<any[]> =>
    (await api.get("/forex/history", { params: { limit } })).data,
};
