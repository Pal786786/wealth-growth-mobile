import { api } from "./client";

export type GoldQuote = {
  ok: boolean;
  provider: string;
  source?: string;
  price_per_gram_inr?: number;
  buy_price: number;
  sell_price: number;
  mid_price: number;
  spread_bps: number;
  maintenance_mode: boolean;
  trading_open: boolean;
  quoted_at?: string;
  note?: string;
};

export type GoldChartPoint = {
  quoted_at: string;
  mid: number;
  buy: number;
  sell: number;
  provider: string;
  source?: string;
};

export type GoldHoldings = {
  user_id: string;
  grams: number;
  total_invested: number;
  avg_buy_price: number;
  current_price_per_gram: number;
  current_sell_price_per_gram: number;
  current_value_inr: number;
  unrealized_pnl_inr: number;
  unrealized_pnl_pct: number;
  daily_gain_inr: number | null;
  daily_gain_pct: number | null;
  as_of: string;
};

export type GoldTx = {
  tx_id: string;
  user_id: string;
  side: "buy" | "sell";
  amount_inr: number;
  grams: number;
  price_per_gram: number;
  mid_price: number;
  spread_bps: number;
  provider: string;
  status: string;
  created_at: string;
  realized_pnl_inr?: number;
  cost_basis_inr?: number;
};

export type GoldUserConfig = {
  min_buy_inr: number;
  max_buy_inr: number;
  spread_bps: number;
  provider: string;
  maintenance_mode: boolean;
  trading_hours: { open_utc: string; close_utc: string };
  redemption_kyc_required: boolean;
};

export type GoldWindow = "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";

export const goldApi = {
  quote: async () => (await api.get<GoldQuote>("/gold/quote")).data,
  chart: async (window: GoldWindow = "1D") =>
    (await api.get<{ points: GoldChartPoint[]; window: string }>("/gold/chart", { params: { window } })).data,
  holdings: async () => (await api.get<GoldHoldings>("/gold/holdings")).data,
  transactions: async (opts: { side?: "buy" | "sell"; search?: string; limit?: number; skip?: number } = {}) =>
    (await api.get<{ items: GoldTx[]; count: number }>("/gold/transactions", { params: opts })).data,
  buy: async (amount_inr: number, idempotencyKey?: string) =>
    (await api.post<GoldTx>("/gold/buy", { amount_inr }, idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {})).data,
  sell: async (grams: number, idempotencyKey?: string) =>
    (await api.post<GoldTx>("/gold/sell", { grams }, idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {})).data,
  userConfig: async () => (await api.get<GoldUserConfig>("/gold/config")).data,
};

// Helpers
export const formatGrams = (g: number) => `${(g ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 4 })} g`;
export const formatMoney = (n: number) =>
  `₹${(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
