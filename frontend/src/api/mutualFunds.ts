import { api } from "./client";

export type MFFund = {
  fund_id: string;
  scheme_code: string;
  isin?: string;
  name: string;
  amc: string;
  category: string;
  sub_category: string;
  risk: string;
  expense_ratio: number;
  exit_load?: string;
  aum_cr: number;
  min_lumpsum: number;
  min_sip: number;
  star_rating: number;
  fund_manager?: string;
  launch_date?: string;
  benchmark?: string;
  objective?: string;
  current_nav: number;
  returns: { m1: number; m3: number; m6: number; y1: number; y3: number; y5: number };
  holdings?: { name: string; weight: number }[];
  sector_allocation?: { name: string; weight: number }[];
  documents?: { kind: string; url: string; label: string }[];
};

export type MFNavPoint = { fund_id: string; scheme_code: string; nav: number; as_of: string };

export type MFOrder = {
  order_id: string;
  user_id: string;
  fund_id: string;
  fund_name: string;
  kind: "lumpsum" | "redeem";
  amount: number;
  units: number;
  nav: number;
  status: string;
  status_history: { status: string; at: string }[];
  created_at: string;
  realized_pnl?: number;
};

export type MFSip = {
  sip_id: string;
  user_id: string;
  fund_id: string;
  fund_name: string;
  amount: number;
  day_of_month: number;
  frequency: string;
  status: "active" | "paused" | "cancelled" | "failed" | "completed";
  retry_count: number;
  success_count: number;
  failure_count: number;
  next_run_at: string;
  last_execution_at?: string;
  created_at: string;
  goal_id?: string;
};

export type MFHolding = {
  fund_id: string;
  fund_name: string;
  amc: string;
  category: string;
  risk: string;
  units: number;
  total_invested: number;
  avg_nav: number;
  current_nav: number;
  current_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  returns_1y?: number;
  returns_3y?: number;
};

export type MFPortfolio = {
  as_of: string;
  total_invested: number;
  current_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  xirr_pct: number | null;
  cagr_pct: number | null;
  absolute_return_pct: number;
  daily_pl: number;
  weekly_pl: number;
  monthly_pl: number;
  dividend_income: number;
  holdings: MFHolding[];
  allocations: {
    asset: { name: string; value: number; pct: number }[];
    amc: { name: string; value: number; pct: number }[];
    category: { name: string; value: number; pct: number }[];
    risk: { name: string; value: number; pct: number }[];
  };
  top_performer: MFHolding | null;
  worst_performer: MFHolding | null;
  count_funds: number;
};

export type MFGoal = {
  goal_id: string;
  user_id: string;
  name: string;
  kind: string;
  target_amount: number;
  target_date: string;
  priority: string;
  expected_return_pct: number;
  linked_funds: string[];
  current_amount: number;
  remaining_amount: number;
  progress_pct: number;
  months_left: number;
  required_monthly_sip: number;
  estimated_completion: string;
};

export type MFWindow = "1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "MAX";

export const mfApi = {
  config: async () => (await api.get("/mf/config")).data,
  funds: async (opts: any = {}) =>
    (await api.get<{ items: MFFund[]; total: number }>("/mf/funds", { params: opts })).data,
  amcs: async () => (await api.get<{ items: string[] }>("/mf/amcs")).data,
  fund: async (fund_id: string) => (await api.get<MFFund>(`/mf/funds/${fund_id}`)).data,
  chart: async (fund_id: string, window: MFWindow) =>
    (await api.get<{ points: MFNavPoint[]; window: string }>(
      `/mf/funds/${fund_id}/chart`, { params: { window } },
    )).data,
  compare: async (fund_ids: string[]) =>
    (await api.post<{ funds: MFFund[] }>("/mf/compare", { fund_ids })).data,
  watchlist: async () => (await api.get<{ items: MFFund[] }>("/mf/watchlist")).data,
  watchlistAdd: async (fund_id: string) =>
    (await api.post("/mf/watchlist", { fund_id })).data,
  watchlistRemove: async (fund_id: string) =>
    (await api.delete(`/mf/watchlist/${fund_id}`)).data,
  invest: async (fund_id: string, amount: number, opts: { goal_id?: string; idempotencyKey?: string } = {}) =>
    (await api.post<MFOrder>("/mf/invest",
      { fund_id, amount, goal_id: opts.goal_id, payment_source: "wallet" },
      opts.idempotencyKey ? { headers: { "Idempotency-Key": opts.idempotencyKey } } : {})).data,
  redeem: async (fund_id: string, units: number) =>
    (await api.post<MFOrder>("/mf/redeem", { fund_id, units })).data,
  orders: async (kind?: string) =>
    (await api.get<{ items: MFOrder[]; count: number }>("/mf/orders", { params: { kind } })).data,
  sipCreate: async (fund_id: string, amount: number, day_of_month = 5, frequency = "monthly", goal_id?: string) =>
    (await api.post<MFSip>("/mf/sips", { fund_id, amount, day_of_month, frequency, goal_id })).data,
  sipList: async (status?: string) =>
    (await api.get<{ items: MFSip[]; count: number }>("/mf/sips", { params: { status } })).data,
  sipModify: async (sip_id: string, patch: Partial<{ amount: number; day_of_month: number; frequency: string }>) =>
    (await api.patch<MFSip>(`/mf/sips/${sip_id}`, patch)).data,
  sipStatus: async (sip_id: string, status: MFSip["status"]) =>
    (await api.post<MFSip>(`/mf/sips/${sip_id}/status`, { status })).data,
  sipExecs: async (sip_id: string) =>
    (await api.get(`/mf/sips/${sip_id}/executions`)).data,
  portfolio: async () => (await api.get<MFPortfolio>("/mf/portfolio")).data,
  goalsList: async () => (await api.get<{ items: MFGoal[] }>("/mf/goals")).data,
  goalCreate: async (goal: Omit<MFGoal, "goal_id" | "user_id" | "current_amount" | "remaining_amount" | "progress_pct" | "months_left" | "required_monthly_sip" | "estimated_completion">) =>
    (await api.post<MFGoal>("/mf/goals", goal)).data,
  goalPatch: async (goal_id: string, patch: any) =>
    (await api.patch(`/mf/goals/${goal_id}`, patch)).data,
  goalDelete: async (goal_id: string) => (await api.delete(`/mf/goals/${goal_id}`)).data,
  ai: async (kind: string) => (await api.post<{ kind: string; answer: string }>("/mf/ai", { kind })).data,
};

export const fmtINR = (n: number | null | undefined) =>
  n == null ? "—" : `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
export const fmtNum = (n: number | null | undefined, d = 4) =>
  n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d });
export const CATEGORIES: { key: string; label: string; color: string; emoji: string }[] = [
  { key: "large_cap", label: "Large Cap", color: "#3B82F6", emoji: "🏛" },
  { key: "mid_cap",   label: "Mid Cap",   color: "#8B5CF6", emoji: "🏢" },
  { key: "small_cap", label: "Small Cap", color: "#EF4444", emoji: "🌱" },
  { key: "elss",      label: "ELSS Tax",  color: "#10B981", emoji: "🛡" },
  { key: "index",     label: "Index",     color: "#0EA5E9", emoji: "📊" },
  { key: "hybrid",    label: "Hybrid",    color: "#F59E0B", emoji: "⚖️" },
  { key: "debt",      label: "Debt",      color: "#64748B", emoji: "💵" },
  { key: "liquid",    label: "Liquid",    color: "#22D3EE", emoji: "💧" },
  { key: "gold",      label: "Gold",      color: "#D97706", emoji: "🥇" },
  { key: "international", label: "Intl",  color: "#EC4899", emoji: "🌍" },
  { key: "equity",    label: "Equity",    color: "#14B8A6", emoji: "📈" },
];

export const RISK_META: Record<string, { label: string; color: string }> = {
  low:        { label: "Low",        color: "#10B981" },
  moderate:   { label: "Moderate",   color: "#F59E0B" },
  high:       { label: "High",       color: "#F97316" },
  very_high:  { label: "Very High",  color: "#EF4444" },
};

export const GOAL_KINDS: { key: string; label: string; emoji: string }[] = [
  { key: "retirement", label: "Retirement", emoji: "🌴" },
  { key: "house",      label: "House",      emoji: "🏠" },
  { key: "car",        label: "Car",        emoji: "🚗" },
  { key: "education",  label: "Education",  emoji: "🎓" },
  { key: "marriage",   label: "Marriage",   emoji: "💍" },
  { key: "emergency",  label: "Emergency",  emoji: "🛟" },
  { key: "custom",     label: "Custom",     emoji: "✨" },
];
