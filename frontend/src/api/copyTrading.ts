/**
 * Copy Trading API client — Sprint 7B.1
 */
import { api } from "./client";

export type TraderStats = {
  total_roi_pct: number; monthly_roi_pct: number; weekly_roi_pct: number; annual_roi_pct: number;
  win_rate_pct: number; profit_factor: number; sharpe_ratio: number; recovery_factor: number;
  max_drawdown_pct: number; avg_holding_hours: number; avg_lot_size: number;
  avg_win_usd: number; avg_loss_usd: number; expectancy_usd: number;
  followers: number; aum_usd: number;
  total_trades: number; winning_trades: number; losing_trades: number;
};
export type TraderRisk = {
  risk_score: number; risk_tier: "Conservative" | "Moderate" | "Aggressive";
  components: Record<string, number>;
};
export type Trader = {
  id: string; name: string; country_code: string; country_name: string;
  style: string; experience_years: number; bio: string; verified: boolean;
  avatar_url: string; joined_days_ago: number;
  stats: TraderStats; risk: TraderRisk;
  monthly_returns_pct: number[];
  equity_curve?: { day: number; balance: number; equity: number }[];
};
export type Trade = {
  id: string; symbol: string; side: "buy" | "sell"; lot_size: number;
  entry_price: number; current_price?: number; exit_price?: number;
  pnl_pct: number; pnl_usd?: number; is_win?: boolean;
  opened_at: number; closed_at?: number;
};

export type CopySettings = {
  mode: "fixed_lot" | "multiplier" | "equity_percent";
  fixed_lot: number; multiplier: number; equity_percent: number;
  max_daily_loss_pct: number; max_drawdown_pct: number;
  max_open_trades: number; equity_protection_pct: number;
  auto_close_on_equity_protection?: boolean;
  auto_pause_on_daily_loss?: boolean;
  resume_mode?: "manual" | "auto";
  max_lot_size?: number; min_lot_size?: number; slippage_pips?: number;
  auto_copy_new_trades?: boolean; copy_existing_open_trades?: boolean;
};
export type CopyLiveStats = {
  open_positions: number; lifetime_pnl_usd: number;
  today_pnl_usd: number; today_trades: number;
  starting_equity_usd: number; current_equity_usd: number;
};
export type CopyRelationship = {
  user_id?: string;
  copy_id?: string;
  trader_id: string;
  status: "active" | "paused" | "stopped" | "halted";
  settings: CopySettings;
  started_at: string | null;
  starting_equity_usd?: number;
  halt_reason?: string | null;
  live?: CopyLiveStats;
  trader?: Trader;
};

export type FollowerTrade = {
  follower_trade_id: string;
  master_id: string;
  user_id: string;
  trader_id: string;
  copy_id?: string;
  symbol: string;
  side: "buy" | "sell";
  lot_size: number;
  entry_price: number;
  exit_price?: number | null;
  sl?: number | null;
  tp?: number | null;
  pnl_usd?: number;
  pnl_pct?: number;
  opened_at: string;
  closed_at?: string | null;
  status: "open" | "closed" | "skipped";
  skip_reason?: string | null;
  close_reason?: string | null;
  broker?: string;
};

export type CopySummary = {
  total_pnl_usd: number;
  today_pnl_usd: number;
  today_trades: number;
  open_positions: number;
  active_copies: number;
  paused_copies: number;
  halted_copies: number;
  total_trades: number;
  win_rate_pct: number;
};

export type MasterTrade = {
  master_id: string;
  trader_id: string;
  symbol: string;
  side: "buy" | "sell";
  lot_size: number;
  entry_price: number;
  exit_price?: number | null;
  sl?: number | null;
  tp?: number | null;
  status: "open" | "closed";
  opened_at: string;
  closed_at?: string | null;
  pnl_pct?: number | null;
  source?: string;
};

export const copyApi = {
  meta: async () => (await api.get("/copy_trading/meta")).data,
  leaderboard: async (opts: { sort?: string; search?: string; min_risk?: number; max_risk?: number; verified_only?: boolean; page?: number; limit?: number } = {}): Promise<{
    items: Trader[]; page: number; limit: number; total: number; has_more: boolean;
  }> => (await api.get("/copy_trading/traders", { params: opts })).data,
  trader: async (id: string): Promise<Trader> => (await api.get(`/copy_trading/traders/${id}`)).data,
  openTrades: async (id: string): Promise<{ trades: Trade[] }> => (await api.get(`/copy_trading/traders/${id}/open-trades`)).data,
  closedTrades: async (id: string, limit = 40): Promise<{ trades: Trade[] }> => (await api.get(`/copy_trading/traders/${id}/closed-trades`, { params: { limit } })).data,
  masterTrades: async (id: string, limit = 50): Promise<{ trades: MasterTrade[] }> =>
    (await api.get(`/copy_trading/traders/${id}/master-trades`, { params: { limit } })).data,

  myCopies: async (): Promise<{ copies: CopyRelationship[] }> => (await api.get("/copy_trading/my/copies")).data,
  mySummary: async (): Promise<CopySummary> => (await api.get("/copy_trading/my/summary")).data,
  myTrades: async (opts: { trader_id?: string; status?: string; limit?: number } = {}): Promise<{ trades: FollowerTrade[] }> =>
    (await api.get("/copy_trading/my/trades", { params: opts })).data,
  pauseAll: async (): Promise<{ paused: number }> => (await api.post("/copy_trading/my/copies/pause-all")).data,
  resumeAll: async (): Promise<{ resumed: number }> => (await api.post("/copy_trading/my/copies/resume-all")).data,
  closeAll: async (): Promise<{ closed: number }> => (await api.post("/copy_trading/my/copies/close-all")).data,

  getCopy: async (id: string): Promise<CopyRelationship> => (await api.get(`/copy_trading/traders/${id}/copy`)).data,
  startCopy: async (id: string, settings?: Partial<CopySettings>): Promise<CopyRelationship> => (await api.post(`/copy_trading/traders/${id}/copy/start`, { settings })).data,
  pauseCopy: async (id: string): Promise<CopyRelationship> => (await api.post(`/copy_trading/traders/${id}/copy/pause`)).data,
  resumeCopy: async (id: string): Promise<CopyRelationship> => (await api.post(`/copy_trading/traders/${id}/copy/resume`)).data,
  stopCopy: async (id: string): Promise<CopyRelationship> => (await api.post(`/copy_trading/traders/${id}/copy/stop`)).data,
  updateSettings: async (id: string, patch: Partial<CopySettings>): Promise<CopyRelationship> => (await api.put(`/copy_trading/traders/${id}/copy/settings`, patch)).data,
};

export function countryFlag(cc: string): string {
  if (!cc || cc.length !== 2) return "🌐";
  const A = 0x1F1E6, off = "A".charCodeAt(0);
  return String.fromCodePoint(A + cc.toUpperCase().charCodeAt(0) - off) +
         String.fromCodePoint(A + cc.toUpperCase().charCodeAt(1) - off);
}
