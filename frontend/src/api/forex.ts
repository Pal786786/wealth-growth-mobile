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
  // Sprint 16.0 — professional chart candles (unified Finnhub engine)
  marketCandles: async (
    symbol: string, tf: string, opts?: { limit?: number; before?: number },
  ): Promise<{ symbol: string; tf: string; candles: Candle[]; volume_available: boolean; quote: any; sync: any }> =>
    (await api.get(`/market/candles/${encodeURIComponent(symbol)}`, { params: { tf, ...(opts || {}) } })).data,
  // Sprint 16.1 — pending orders (limit/stop)
  placePendingOrder: async (body: { symbol_id: string; side: Side; order_type: "limit" | "stop"; price: number; lot_size: number; tp?: number | null; sl?: number | null }): Promise<PendingOrder> =>
    (await api.post("/forex/orders", body)).data,
  listOrders: async (status = "pending"): Promise<PendingOrder[]> =>
    (await api.get("/forex/orders", { params: { status } })).data,
  modifyOrder: async (orderId: string, patch: { price?: number; tp?: number; sl?: number }): Promise<PendingOrder> =>
    (await api.put(`/forex/orders/${orderId}`, patch)).data,
  cancelOrder: async (orderId: string): Promise<PendingOrder> =>
    (await api.delete(`/forex/orders/${orderId}`)).data,
  // Sprint 16.1 — position ops
  partialClose: async (positionId: string, fraction: number): Promise<{ closed: Position; position: Position }> =>
    (await api.post(`/forex/positions/${positionId}/partial-close`, { fraction })).data,
  reversePosition: async (positionId: string): Promise<{ closed: Position; opened: Position }> =>
    (await api.post(`/forex/positions/${positionId}/reverse`)).data,
  doublePosition: async (positionId: string): Promise<{ opened: Position }> =>
    (await api.post(`/forex/positions/${positionId}/double`)).data,
  // Sprint 16.1 — costs + chart persistence
  tradingCosts: async (): Promise<{ commission_per_lot: number; commission_type: string; commission_currency: string; margin_per_lot: number; usd_inr: number }> =>
    (await api.get("/forex/trading-costs")).data,
  getChartObjects: async (symbolId: string, chartKey = "main"): Promise<{ objects: any[] }> =>
    (await api.get("/forex/chart-objects", { params: { symbol_id: symbolId, chart_key: chartKey } })).data,
  saveChartObjects: async (symbolId: string, objects: any[], chartKey = "main"): Promise<void> =>
    (await api.put("/forex/chart-objects", { symbol_id: symbolId, chart_key: chartKey, objects })).data,
  getChartPrefs: async (): Promise<{ prefs: any }> => (await api.get("/forex/chart-prefs")).data,
  saveChartPrefs: async (prefs: any): Promise<void> => (await api.put("/forex/chart-prefs", { prefs })).data,
};

export type PendingOrder = {
  order_id: string; symbol_id: string; side: Side; type: "limit" | "stop";
  price: number; lot_size: number; tp?: number | null; sl?: number | null;
  status: string; position_id?: string | null; ts: string;
};

export type Candle = {
  t: number; o: number; h: number; l: number; c: number; v: number;
  complete?: boolean; source?: string;
};
