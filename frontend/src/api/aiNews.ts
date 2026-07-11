import { api } from "./client";

export type NewsCategory = "forex" | "crypto" | "indices" | "commodities" | "indian_market" | "global";
export type Sentiment = "bullish" | "mildly_bullish" | "neutral" | "mildly_bearish" | "bearish";
export type Impact = "low" | "medium" | "high";
export type SummaryType = "intraday" | "daily" | "weekly";

export type NewsItem = {
  news_id: string;
  category: NewsCategory;
  category_label: string;
  title: string;
  summary: string;
  body: string;
  sentiment: Sentiment;
  tags: string[];
  symbols: string[];
  symbol_snapshot: { symbol: string; price: number | null; change_pct: number | null };
  published_at: string;
  is_ai_generated: boolean;
  is_published: boolean;
  high_impact: boolean;
};

export type EconomicEvent = {
  event_id: string;
  title: string;
  country: string;
  currency: string;
  impact: Impact;
  category: string;
  event_time: string;
  countdown_sec: number | null;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  description: string;
};

export type MarketSummary = {
  summary_id: string;
  type: SummaryType;
  period_start: string;
  period_end: string;
  headline: string;
  sentiment: string;
  body: string;
  key_movers: Array<{ symbol: string; price: number | null; change_pct: number | null }>;
  is_ai_generated: boolean;
  generated_at: string;
};

export type AnalyticsOverview = {
  window_days: number | null;
  total_signals: number;
  resolved_signals: number;
  pending_signals: number;
  tp_hits: number;
  sl_hits: number;
  expired: number;
  win_rate_pct: number;
  tp1_hit_rate_pct: number;
  tp2_hit_rate_pct: number;
  tp3_hit_rate_pct: number;
  sum_roi_pct: number;
  avg_roi_pct: number;
  avg_confidence_pct: number;
  win_avg_confidence_pct: number;
  loss_avg_confidence_pct: number;
  confidence_edge_pct: number;
};

export type AnalyticsBySymbol = {
  symbol: string;
  resolved: number;
  wins: number;
  losses: number;
  sum_roi: number;
  avg_conf: number;
  win_rate_pct: number;
};

export type AnalyticsByTimeframe = {
  timeframe: string;
  resolved: number;
  wins: number;
  sum_roi: number;
  avg_conf: number;
  win_rate_pct: number;
};

export type SignalHistoryRow = {
  symbol: string;
  timeframe: string;
  side: "buy" | "sell";
  entry: number;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  tp3: number | null;
  confidence_pct: number;
  outcome: "pending" | "tp1_hit" | "tp2_hit" | "tp3_hit" | "sl_hit" | "expired";
  roi_pct: number | null;
  generated_at: string;
  resolved_at: string | null;
  exit_price: number | null;
};

export const aiNewsApi = {
  news: async (opts: { category?: NewsCategory | "all"; sentiment?: Sentiment; high_impact_only?: boolean; limit?: number } = {}) =>
    (await api.get("/ai/news", { params: opts })).data as { items: NewsItem[]; count: number; categories: NewsCategory[]; category_labels: Record<NewsCategory, string> },

  newsDetail: async (news_id: string) =>
    (await api.get(`/ai/news/${news_id}`)).data as NewsItem,

  calendarMeta: async () =>
    (await api.get("/ai/calendar/meta")).data as { impacts: Impact[]; impact_labels: Record<Impact, string> },

  calendar: async (opts: { impact?: Impact; country?: string; currency?: string; days_ahead?: number; include_past?: boolean; limit?: number } = {}) =>
    (await api.get("/ai/calendar", { params: opts })).data as { events: EconomicEvent[]; count: number },

  summary: async (type: SummaryType = "daily") =>
    (await api.get("/ai/summary", { params: { type } })).data as { summary: MarketSummary },

  summaryHistory: async (type?: SummaryType, limit: number = 20) =>
    (await api.get("/ai/summary/history", { params: { type, limit } })).data as { items: MarketSummary[]; count: number },

  analyticsOverview: async (window_days?: number) =>
    (await api.get("/ai/analytics/overview", { params: window_days ? { window_days } : {} })).data as AnalyticsOverview,

  analyticsBySymbol: async (window_days?: number, limit: number = 30) =>
    (await api.get("/ai/analytics/by-symbol", { params: { window_days, limit } })).data as { rows: AnalyticsBySymbol[]; count: number },

  analyticsByTimeframe: async (window_days?: number) =>
    (await api.get("/ai/analytics/by-timeframe", { params: window_days ? { window_days } : {} })).data as { rows: AnalyticsByTimeframe[]; count: number },

  analyticsHistory: async (limit: number = 40, outcome?: string) =>
    (await api.get("/ai/analytics/history", { params: { limit, outcome } })).data as { items: SignalHistoryRow[]; count: number },
};

// Helpers
export const sentimentColor = (s: string, palette: any) => {
  if (s?.includes("bullish")) return palette.success;
  if (s?.includes("bearish")) return palette.danger;
  return palette.textMuted;
};

export const impactColor = (i: Impact, palette: any) => {
  if (i === "high") return palette.danger;
  if (i === "medium") return "#F59E0B";
  return palette.textMuted;
};

export const formatCountdown = (seconds: number | null | undefined): string => {
  if (seconds == null) return "—";
  if (seconds <= 0) return "Now";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};

export const outcomeColor = (outcome: string, palette: any) => {
  if (outcome.startsWith("tp")) return palette.success;
  if (outcome === "sl_hit") return palette.danger;
  if (outcome === "expired") return palette.textMuted;
  return "#F59E0B";
};

export const outcomeLabel = (outcome: string) => {
  const map: Record<string, string> = {
    pending: "Open",
    tp1_hit: "TP1 hit",
    tp2_hit: "TP2 hit",
    tp3_hit: "TP3 hit",
    sl_hit: "SL hit",
    expired: "Expired",
  };
  return map[outcome] || outcome;
};
