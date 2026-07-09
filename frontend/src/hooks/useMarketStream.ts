/**
 * useMarketStream — Sprint 7 Slice 1
 * ----------------------------------
 * Transport-agnostic price subscription hook.
 *
 * Under the hood it opens a WebSocket to /api/market_data/ws/stream and
 * subscribes to the symbols passed in. Whenever the backend's active
 * transport (polling or websocket) pushes a tick, we get a fresh quote.
 *
 * If the WebSocket connection fails (running in Expo Go without WS support,
 * network blocked, etc.) we transparently fall back to REST polling every
 * 3s via marketDataApi.quotes(). The consuming component never notices.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Platform } from "react-native";
import { marketDataApi, Quote } from "@/src/api/marketData";

const POLL_INTERVAL_MS = 3000;
const RECONNECT_BACKOFF_MS = [1000, 2000, 5000, 10000];

function wsBase(): string | null {
  const http = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/$/, "");
  if (!http) return null;
  const url = http.replace(/^http/, "ws");
  return `${url}/api/market_data/ws/stream`;
}

export function useMarketStream(symbolIds: string[]): { quotes: Record<string, Quote>; status: "connecting" | "ws" | "polling" | "idle" } {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [status, setStatus] = useState<"connecting" | "ws" | "polling" | "idle">("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const pollTimerRef = useRef<any>(null);
  const attemptRef = useRef(0);
  const activeSyms = useRef<string[]>([]);

  activeSyms.current = symbolIds;

  const upsert = useCallback((q: Quote) => {
    if (!q || !q.symbol_id) return;
    setQuotes((prev) => ({ ...prev, [q.symbol_id]: q }));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    setStatus("polling");
    const tick = async () => {
      const ids = activeSyms.current;
      if (!ids.length) return;
      try {
        const r = await marketDataApi.quotes(ids);
        for (const q of r.quotes) upsert(q);
      } catch { /* ignore transient errors */ }
    };
    tick();
    pollTimerRef.current = setInterval(tick, POLL_INTERVAL_MS);
  }, [upsert, stopPolling]);

  const closeWs = useCallback(() => {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    // Ignore empty subscription
    if (!symbolIds.length) {
      setStatus("idle");
      stopPolling();
      closeWs();
      return;
    }

    // If WS already open, just push updated subscriptions
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ action: "subscribe", symbols: symbolIds }));
      } catch { /* ignore */ }
    }
  }, [symbolIds.join(",")]);

  useEffect(() => {
    let cancelled = false;

    const openWs = () => {
      const url = wsBase();
      // On web Expo dev, WS URL construction can be tricky — for MVP we always
      // attempt WS first, and fall back to polling on error.
      if (!url) { startPolling(); return; }
      setStatus("connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        startPolling();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) { try { ws.close(); } catch { /* ignore */ } return; }
        attemptRef.current = 0;
        setStatus("ws");
        try {
          ws.send(JSON.stringify({ action: "subscribe", symbols: activeSyms.current }));
        } catch { /* ignore */ }
      };

      ws.onmessage = (ev) => {
        try {
          const data = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data;
          if (data?.type === "quote") upsert(data as Quote);
        } catch { /* ignore parse errors */ }
      };

      const scheduleReconnect = () => {
        if (cancelled) return;
        wsRef.current = null;
        // Start polling immediately while we back off on WS
        startPolling();
        const wait = RECONNECT_BACKOFF_MS[Math.min(attemptRef.current, RECONNECT_BACKOFF_MS.length - 1)];
        attemptRef.current += 1;
        setTimeout(() => { if (!cancelled) openWs(); }, wait);
      };

      ws.onerror = () => { scheduleReconnect(); };
      ws.onclose = () => { if (wsRef.current === ws) scheduleReconnect(); };
    };

    openWs();
    return () => {
      cancelled = true;
      stopPolling();
      closeWs();
    };
    // Only reconnect when the "set" of symbols changes meaningfully
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { quotes, status };
}
