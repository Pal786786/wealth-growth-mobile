/**
 * Sprint 7 Slice 1 — Market Data API client
 * -----------------------------------------
 * Server: /api/market_data/*
 * Provider- and transport-agnostic. Same interface whether backend is on
 * mock, TwelveData, Alpha Vantage, WebSocket or polling.
 */
import { api } from "./client";

export type Category = {
  id: string;
  label: string;
  icon: string;
  desc: string;
  count: number;
};

export type Instrument = {
  symbol_id: string;
  display: string;
  name: string;
  category: string;
  currency: string;
  price_dp: number;
  seed?: number;
  vol?: number;
  trend?: number;
  provider_symbols?: Record<string, string | null>;
  extras?: Record<string, any>;
};

export type Quote = {
  symbol_id: string;
  display: string;
  name: string;
  category: string;
  currency: string;
  price_dp: number;
  mid: number;
  bid: number;
  ask: number;
  ts: number;
  source: string;
  change_pct: number | null;
};

export const marketDataApi = {
  categories: async (): Promise<{ categories: Category[] }> =>
    (await api.get("/market_data/categories")).data,

  catalog: async (opts: { category?: string; search?: string; page?: number; limit?: number } = {}): Promise<{
    items: Instrument[]; page: number; limit: number; total: number; has_more: boolean; total_pages: number;
  }> =>
    (await api.get("/market_data/catalog", {
      params: { category: opts.category, search: opts.search, page: opts.page ?? 1, limit: opts.limit ?? 50 },
    })).data,

  symbol: async (symbolId: string): Promise<Instrument> =>
    (await api.get(`/market_data/symbols/${encodeURIComponent(symbolId)}`)).data,

  quote: async (symbolId: string): Promise<Quote> =>
    (await api.get(`/market_data/quote/${encodeURIComponent(symbolId)}`)).data,

  quotes: async (symbolIds: string[]): Promise<{ quotes: Quote[]; ts: number }> =>
    (await api.get("/market_data/quotes", { params: { symbols: symbolIds.join(",") } })).data,

  history: async (symbolId: string, points = 60): Promise<{ symbol_id: string; points: { ts: number; mid: number }[] }> =>
    (await api.get(`/market_data/history/${encodeURIComponent(symbolId)}`, { params: { points } })).data,

  // Favorites
  favorites: async (): Promise<{ symbols: string[]; items: Instrument[] }> =>
    (await api.get("/market_data/favorites")).data,
  addFavorite: async (symbolId: string): Promise<{ ok: true; symbol_id: string }> =>
    (await api.post(`/market_data/favorites/${encodeURIComponent(symbolId)}`)).data,
  removeFavorite: async (symbolId: string): Promise<{ ok: true; symbol_id: string }> =>
    (await api.delete(`/market_data/favorites/${encodeURIComponent(symbolId)}`)).data,

  // Recently viewed
  logView: async (symbolId: string): Promise<{ ok: true }> =>
    (await api.post(`/market_data/recently-viewed/${encodeURIComponent(symbolId)}`)).data,
  recentlyViewed: async (): Promise<{ entries: { symbol_id: string; at: string }[]; items: Instrument[] }> =>
    (await api.get("/market_data/recently-viewed")).data,
};
