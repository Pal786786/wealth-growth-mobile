import { useCallback, useEffect, useRef, useState } from "react";
import { forexApi, ForexQuote } from "@/src/api/forex";

/**
 * Polls /api/forex/prices at the given interval. Returns a map keyed by
 * symbol id and a lastUpdate timestamp for UI feedback.
 */
export function useForexPrices(intervalMs = 2000) {
  const [quotes, setQuotes] = useState<Record<string, ForexQuote>>({});
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const timerRef = useRef<any>(null);
  const mountedRef = useRef(true);

  const tick = useCallback(async () => {
    try {
      const { prices } = await forexApi.prices();
      if (!mountedRef.current) return;
      const map: Record<string, ForexQuote> = {};
      prices.forEach((p) => { map[p.symbol_id] = p; });
      setQuotes(map);
      setError(null);
      setLoaded(true);
    } catch (e: any) {
      if (mountedRef.current) setError(e?.message || String(e));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    tick();
    timerRef.current = setInterval(tick, intervalMs);
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [intervalMs, tick]);

  return { quotes, error, loaded, refresh: tick };
}
