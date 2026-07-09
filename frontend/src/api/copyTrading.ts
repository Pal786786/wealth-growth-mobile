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
  max_open_trades: number; equity_protection_pct: number; auto_close_on_stop: boolean;
};
export type CopyRelationship = {
  status: "active" | "paused" | "stopped";
  settings: CopySettings;
  started_at: string | null;
  trader?: Trader;
};

export const copyApi = {
  meta: async () => (await api.get("/copy_trading/meta")).data,
  leaderboard: async (opts: { sort?: string; search?: string; min_risk?: number; max_risk?: number; verified_only?: boolean; page?: number; limit?: number } = {}): Promise<{
    items: Trader[]; page: number; limit: number; total: number; has_more: boolean;
  }> => (await api.get("/copy_trading/traders", { params: opts })).data,
  trader: async (id: string): Promise<Trader> => (await api.get(`/copy_trading/traders/${id}`)).data,
  openTrades: async (id: string): Promise<{ trades: Trade[] }> => (await api.get(`/copy_trading/traders/${id}/open-trades`)).data,
  closedTrades: async (id: string, limit = 40): Promise<{ trades: Trade[] }> => (await api.get(`/copy_trading/traders/${id}/closed-trades`, { params: { limit } })).data,

  myCopies: async (): Promise<{ copies: CopyRelationship[] }> => (await api.get("/copy_trading/my/copies")).data,
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
