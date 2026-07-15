"""Finnhub REST provider — Sprint 15.0

Primary live provider after migration from TwelveData. Uses the paid All-in-One
tier's real-time /quote endpoint for FX (OANDA), crypto (Binance), gold
(OANDA), indices (US equity ETF proxies), and commodities (futures symbols).

Docs: https://finnhub.io/docs/api/quote
Rate limit on paid Q-plan: 300 req/min (well above our steady state).
"""
from __future__ import annotations
import logging, os, time
from typing import Any, Dict, List, Optional

import httpx
from .base import Provider, Quote, RateLimitError, ProviderNotConfigured

logger = logging.getLogger("market.providers.finnhub")
BASE_URL = "https://finnhub.io/api/v1"

# Canonical → Finnhub symbol map. FX via OANDA broker feed, crypto via Binance
# spot pairs, gold/silver as OTC OANDA metals, US indices via SPDR/PowerShares
# ETFs (highly-liquid intraday proxies), foreign indices via native codes,
# commodities via CME/ICE continuous futures.
SYMBOL_MAP: Dict[str, str] = {
    # FX
    "EURUSD": "OANDA:EUR_USD", "GBPUSD": "OANDA:GBP_USD",
    "USDJPY": "OANDA:USD_JPY", "USDCHF": "OANDA:USD_CHF",
    "USDCAD": "OANDA:USD_CAD", "AUDUSD": "OANDA:AUD_USD",
    "NZDUSD": "OANDA:NZD_USD",
    # Precious metals
    "XAUUSD": "OANDA:XAU_USD", "XAGUSD": "OANDA:XAG_USD",
    # Crypto (Binance spot)
    "BTCUSD": "BINANCE:BTCUSDT", "ETHUSD": "BINANCE:ETHUSDT",
    # US index ETF proxies
    "US30":  "DIA",   # SPDR Dow Jones
    "NAS100": "QQQ",  # Invesco QQQ
    "SPX500": "SPY",  # SPDR S&P 500
    # Foreign index tickers
    "GER40":  "^GDAXI",
    "UK100":  "^FTSE",
    "IND50":  "^NSEI",
    # Commodities (continuous futures)
    "USOIL":  "CL=F",   # WTI
    "UKOIL":  "BZ=F",   # Brent
    "NATGAS": "NG=F",
}


class FinnhubProvider(Provider):
    name = "finnhub"
    priority = 100     # highest — replaces TwelveData as primary
    _CB_THRESHOLD = 5

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self._api_key = (api_key or os.environ.get("FINNHUB_API_KEY") or "").strip()
        self._last_test_ts: float = 0

    # ------------- key management ------------- #
    def set_api_key(self, key: str) -> None:
        self._api_key = (key or "").strip()
        self._reset_backoff(reason="key_rotated")

    async def is_configured(self) -> bool:
        return bool(self._api_key)

    # ------------- test connection ------------- #
    async def test_connection(self) -> Dict[str, object]:
        """Sprint 15.0 — send TWO probes (FX + Gold) as user requested and
        return exact Finnhub responses / error messages verbatim."""
        if not self._api_key:
            return {"ok": False, "error": "FINNHUB_API_KEY not set"}
        results: Dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=8.0) as c:
            for label, sym in (("EURUSD", "OANDA:EUR_USD"),
                                ("XAUUSD", "OANDA:XAU_USD")):
                try:
                    r = await c.get(f"{BASE_URL}/quote",
                                     params={"symbol": sym, "token": self._api_key})
                    body = r.json() if r.headers.get("content-type","").startswith("application/json") else {"raw": r.text[:200]}
                    results[label] = {"symbol": sym, "http": r.status_code, "body": body}
                except Exception as e:
                    results[label] = {"symbol": sym, "error": f"{type(e).__name__}: {e}"}
        # Consider success only if both probes returned a positive `c` (current price)
        ok = all(isinstance(v.get("body"), dict) and v["body"].get("c", 0) > 0
                 for v in results.values() if "body" in v)
        self._last_test_ts = time.time()
        if ok:
            self._reset_backoff(reason="test_connection_ok")
        return {"ok": ok, "probes": results}

    # ------------- fetch ------------- #
    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        if not self._api_key:
            raise ProviderNotConfigured("FINNHUB_API_KEY not set")
        if self.is_backed_off():
            raise RateLimitError(f"backoff {self.backoff_remaining_sec()}s")

        # Finnhub /quote is single-symbol — issue concurrent requests.
        import asyncio
        canon = [s.upper() for s in symbols]
        out: Dict[str, Quote] = {}
        drops: List[Dict[str, Any]] = []

        async def _one(client: httpx.AsyncClient, canon_sym: str) -> None:
            fin_sym = SYMBOL_MAP.get(canon_sym)
            if not fin_sym:
                drops.append({"sym": canon_sym, "reason": "no_symbol_map"})
                return
            try:
                r = await client.get(f"{BASE_URL}/quote",
                                     params={"symbol": fin_sym, "token": self._api_key})
                if r.status_code == 429:
                    self._trigger_backoff("HTTP 429")
                    raise RateLimitError("finnhub 429")
                if r.status_code == 401:
                    drops.append({"sym": canon_sym, "reason": "401_invalid_key"})
                    return
                if r.status_code >= 400:
                    drops.append({"sym": canon_sym, "reason": f"http_{r.status_code}", "body": r.text[:150]})
                    return
                data = r.json()
                # `c` = current price. Zero means symbol not resolved on Finnhub.
                price = float(data.get("c") or 0)
                if price <= 0:
                    drops.append({"sym": canon_sym, "fin_sym": fin_sym, "reason": "zero_price"})
                    return
                # Finnhub /quote does not return bid/ask — synthesize from a
                # 0.02 % half-spread which matches typical OTC quotes.
                spread = price * 0.0001
                out[canon_sym] = Quote(
                    symbol=canon_sym, price=price,
                    bid=round(price - spread, 8),
                    ask=round(price + spread, 8),
                    provider=self.name, raw=data,
                )
            except RateLimitError:
                raise
            except Exception as e:
                drops.append({"sym": canon_sym, "reason": f"{type(e).__name__}:{e}"[:120]})

        # Concurrent fan-out, bounded to 8 to keep well under 300/min
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(timeout=6.0) as client:
            async def _guarded(s: str) -> None:
                async with sem:
                    await _one(client, s)
            await asyncio.gather(*[_guarded(s) for s in canon])

        logger.info("finnhub._fetch_quotes parsed=%d/%d drops=%s",
                    len(out), len(canon), drops[:5])
        if out:
            self._reset_backoff(reason="success")
        return out
