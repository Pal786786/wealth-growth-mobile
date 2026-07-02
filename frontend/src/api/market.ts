import { api } from "./client";

export type Quote = {
  symbol: string; name: string; category: string; currency: string; unit?: string;
  price: number; prev_close: number; change: number; change_pct: number;
  trend: "up" | "down" | "flat"; day_low: number; day_high: number;
  updated_at: string; provider: string; pinned?: boolean;
};
export type NewsItem = { id: string; category: string; headline: string; summary: string; source: string; published_at: string; url?: string };
export type CalEvent = { id: string; country: string; event: string; type: string; impact: string; when: string; prior?: string; forecast?: string };

export const marketApi = {
  dashboard: () => api.get<{ items: Quote[]; provider: string; as_of: string }>("/market/dashboard").then((r) => r.data),
  quote: (sym: string) => api.get<Quote>(`/market/quote/${sym}`).then((r) => r.data),
  history: (sym: string, points = 30) => api.get<{ symbol: string; points: { t: number; close: number }[] }>(`/market/history/${sym}?points=${points}`).then((r) => r.data),
  search: (q: string) => api.get<{ items: { symbol: string; name: string; category: string; currency: string }[] }>(`/market/search?q=${encodeURIComponent(q)}`).then((r) => r.data.items),
  watchlist: () => api.get<{ items: Quote[]; pinned: string[] }>("/market/watchlist").then((r) => r.data),
  addWatch: (symbol: string) => api.post("/market/watchlist/add", { symbol }).then((r) => r.data),
  removeWatch: (symbol: string) => api.delete(`/market/watchlist/${symbol}`).then((r) => r.data),
  pinWatch: (symbol: string, pinned: boolean) => api.post("/market/watchlist/pin", { symbol, pinned }).then((r) => r.data),
  news: (category?: string) => api.get<{ items: NewsItem[]; categories: string[] }>(`/market/news${category && category !== "all" ? `?category=${category}` : ""}`).then((r) => r.data),
  calendar: () => api.get<{ items: CalEvent[] }>("/market/calendar").then((r) => r.data.items),
};
