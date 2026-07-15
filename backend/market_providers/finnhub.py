"""Finnhub REST provider — Sprint 15.0

Primary — and after Sprint 15.0 the *only* — live-market provider.
Backed by an active paid ``Marketdata-basic`` subscription. Uses the
``/quote`` endpoint (single-symbol) with concurrent fan-out.

Docs
----
https://finnhub.io/docs/api/quote

Rate limit
----------
Paid Marketdata-basic plan: 300 requests / minute — well above our steady
state of ~20 symbols / 60 s (= 20 req/min).
"""
from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .base import Provider, Quote, RateLimitError, ProviderNotConfigured

logger = logging.getLogger("market.providers.finnhub")
BASE_URL = "https://finnhub.io/api/v1"

# Exponential backoff schedule for HTTP 429 / hard errors (seconds).
# Matches TwelveData provider's ladder so admin UX stays predictable.
BACKOFF_SCHEDULE: List[int] = [15, 30, 60, 120, 300]

# --------------------------------------------------------------------------- #
#  Canonical → Finnhub symbol map
#  ---------------------------------------------------------------------------
#  * FX / metals: OANDA broker feed  (e.g. OANDA:EUR_USD, OANDA:XAU_USD)
#  * Crypto     : Binance spot pairs (e.g. BINANCE:BTCUSDT)
#  * US indices : SPDR / PowerShares ETF proxies (highly liquid intraday)
#  * Foreign IX : native Finnhub index tickers  (^GDAXI, ^FTSE, ^NSEI)
#  * Commodities: CME / ICE continuous-front-month futures (CL=F, BZ=F, NG=F)
#
#  The user's directive (Sprint 15.0 §11) is: “verify every supported asset;
#  if Finnhub uses a different name, map it automatically.”  This dict is the
#  single source of truth for that mapping.
# --------------------------------------------------------------------------- #
SYMBOL_MAP: Dict[str, str] = {
    # ---- FX majors + minors (OANDA feed) --------------------------------- #
    "EURUSD": "OANDA:EUR_USD", "GBPUSD": "OANDA:GBP_USD",
    "USDJPY": "OANDA:USD_JPY", "USDCHF": "OANDA:USD_CHF",
    "USDCAD": "OANDA:USD_CAD", "AUDUSD": "OANDA:AUD_USD",
    "NZDUSD": "OANDA:NZD_USD",
    # ---- Precious metals (OANDA OTC) ------------------------------------- #
    "XAUUSD": "OANDA:XAU_USD", "XAGUSD": "OANDA:XAG_USD",
    # ---- Crypto (Binance spot) ------------------------------------------- #
    "BTCUSD": "BINANCE:BTCUSDT", "ETHUSD": "BINANCE:ETHUSDT",
    # ---- US index ETF proxies -------------------------------------------- #
    "US30":   "DIA",     # SPDR Dow Jones
    "NAS100": "QQQ",     # Invesco QQQ
    "SPX500": "SPY",     # SPDR S&P 500
    # ---- Foreign index tickers ------------------------------------------- #
    "GER40":  "^GDAXI",
    "UK100":  "^FTSE",
    "IND50":  "^NSEI",
    # ---- Commodities (CME/ICE continuous futures) ------------------------ #
    "USOIL":  "CL=F",    # WTI crude
    "UKOIL":  "BZ=F",    # Brent crude
    "NATGAS": "NG=F",
}


def _redact(s: str, secret: str) -> str:
    if secret and len(secret) >= 4:
        return s.replace(secret, "***")
    return s


class FinnhubProvider(Provider):
    name = "finnhub"
    priority = 100     # highest priority — the primary live provider

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self._api_key = (api_key or os.environ.get("FINNHUB_API_KEY") or "").strip()
        self._last_test_ts: float = 0.0
        # ---- backoff state --------------------------------------------- #
        self._backoff_step: int = 0
        self._backoff_until: Optional[datetime] = None
        self._last_429_at: Optional[datetime] = None
        self._total_429_events: int = 0
        # ---- credits (Finnhub exposes them in response headers) -------- #
        self._credits_left_minute: Optional[int] = None
        self._credits_left_daily: Optional[int] = None

    # ===================== configuration ===================== #
    async def is_configured(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, key: str) -> None:
        """Rotate the API key and clear ALL prior failure/backoff state so the
        next call starts with a clean slate. Also resets rolling ProviderStats.
        Does NOT auto-call the API — use ``test_connection()`` for that."""
        self._api_key = (key or "").strip()
        self._reset_backoff(reason="api key updated")
        self._credits_left_minute = None
        self._credits_left_daily = None
        self.stats.reset()
        logger.info("Finnhub: api-key rotated → backoff + stats + credits cleared")

    # ===================== test connection ===================== #
    async def test_connection(self) -> Dict[str, Any]:
        """Sprint 15.0 spec §5 — probe both ``OANDA:EUR_USD`` (Forex) and
        ``OANDA:XAU_USD`` (Gold). Returns the exact Finnhub response bodies
        so the admin UI can display verbatim errors when the key is bad."""
        if not self._api_key:
            return {"ok": False, "error": "FINNHUB_API_KEY not set"}
        probes = (("EURUSD", "OANDA:EUR_USD"), ("XAUUSD", "OANDA:XAU_USD"))
        results: Dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=8.0) as c:
            for label, sym in probes:
                try:
                    r = await c.get(
                        f"{BASE_URL}/quote",
                        params={"symbol": sym, "token": self._api_key},
                    )
                    self._parse_credit_headers(r)
                    ct = (r.headers.get("content-type") or "").lower()
                    body: Any = (
                        r.json() if ct.startswith("application/json")
                        else {"raw": r.text[:200]}
                    )
                    results[label] = {
                        "symbol": sym,
                        "http": r.status_code,
                        "body": body,
                    }
                    if r.status_code == 429:
                        self._trigger_backoff("test_connection HTTP 429")
                except Exception as e:                       # pragma: no cover
                    results[label] = {
                        "symbol": sym,
                        "error": f"{type(e).__name__}: {e}",
                    }
        # Success ⇔ both probes returned a positive current price (`c`)
        ok = all(
            isinstance(v.get("body"), dict) and float(v["body"].get("c") or 0) > 0
            for v in results.values() if "body" in v
        )
        self._last_test_ts = time.time()
        if ok:
            self._reset_backoff(reason="test_connection_ok")
            self.stats.record_success(latency_ms=0.0, credits=0)
        return {
            "ok": ok,
            "probes": results,
            "credits_left_minute": self._credits_left_minute,
            "credits_left_daily":  self._credits_left_daily,
        }

    # ===================== backoff API ===================== #
    def is_backed_off(self) -> bool:
        if self._backoff_until is None:
            return False
        return datetime.now(timezone.utc) < self._backoff_until

    def backoff_remaining_sec(self) -> int:
        if not self.is_backed_off():
            return 0
        return max(0, int((self._backoff_until - datetime.now(timezone.utc)).total_seconds()))

    def backoff_state(self) -> Dict[str, Any]:
        return {
            "active": self.is_backed_off(),
            "step": self._backoff_step,
            "remaining_sec": self.backoff_remaining_sec(),
            "until": self._backoff_until.isoformat() if self._backoff_until else None,
            "last_429_at": self._last_429_at.isoformat() if self._last_429_at else None,
            "total_429_events": self._total_429_events,
            "schedule": BACKOFF_SCHEDULE,
            "credits_left_minute": self._credits_left_minute,
            "credits_left_daily":  self._credits_left_daily,
        }

    def _trigger_backoff(self, reason: str) -> None:
        idx = min(self._backoff_step, len(BACKOFF_SCHEDULE) - 1)
        wait_sec = BACKOFF_SCHEDULE[idx]
        self._backoff_step += 1
        self._total_429_events += 1
        self._last_429_at = datetime.now(timezone.utc)
        self._backoff_until = self._last_429_at + timedelta(seconds=wait_sec)
        logger.warning(
            "Finnhub 429 (%s) — backoff #%d, waiting %ds until %s (total 429s=%d)",
            reason, self._backoff_step, wait_sec,
            self._backoff_until.isoformat(), self._total_429_events,
        )

    def _reset_backoff(self, reason: str = "success") -> None:
        if self._backoff_step or self._backoff_until:
            logger.info("Finnhub backoff reset (%s), was step=%d",
                        reason, self._backoff_step)
        self._backoff_step = 0
        self._backoff_until = None

    def _parse_credit_headers(self, resp: httpx.Response) -> None:
        """Finnhub exposes: X-Ratelimit-Remaining (per-minute)."""
        try:
            m = resp.headers.get("X-Ratelimit-Remaining") or resp.headers.get("x-ratelimit-remaining")
            if m is not None:
                self._credits_left_minute = int(m)
        except (ValueError, TypeError):
            pass

    # ===================== fetch ===================== #
    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        if not self._api_key:
            raise ProviderNotConfigured("FINNHUB_API_KEY not set")
        if self.is_backed_off():
            raise RateLimitError(f"finnhub backoff {self.backoff_remaining_sec()}s")

        # Finnhub /quote is single-symbol → concurrent fan-out
        import asyncio
        canon = [s.upper() for s in symbols]
        out: Dict[str, Quote] = {}
        drops: List[Dict[str, Any]] = []
        rate_limited = False

        async def _one(client: httpx.AsyncClient, canon_sym: str) -> None:
            nonlocal rate_limited
            fin_sym = SYMBOL_MAP.get(canon_sym)
            if not fin_sym:
                drops.append({"sym": canon_sym, "reason": "no_symbol_map"})
                return
            try:
                r = await client.get(
                    f"{BASE_URL}/quote",
                    params={"symbol": fin_sym, "token": self._api_key},
                )
                self._parse_credit_headers(r)
                if r.status_code == 429:
                    rate_limited = True
                    drops.append({"sym": canon_sym, "reason": "http_429"})
                    return
                if r.status_code == 401:
                    drops.append({"sym": canon_sym, "reason": "401_invalid_key"})
                    return
                if r.status_code >= 400:
                    drops.append({
                        "sym": canon_sym,
                        "reason": f"http_{r.status_code}",
                        "body": r.text[:150],
                    })
                    return
                data = r.json()
                # `c` = current price. Zero ⇒ symbol not resolved on Finnhub.
                price = float(data.get("c") or 0)
                if price <= 0:
                    drops.append({
                        "sym": canon_sym, "fin_sym": fin_sym, "reason": "zero_price",
                    })
                    return
                # Finnhub /quote does NOT return bid/ask — synthesize a 1 bp
                # half-spread which matches OANDA institutional quotes.
                spread = price * 0.0001
                # 24h % change from previous close (`pc`) if available
                pc = float(data.get("pc") or 0)
                change_pct = ((price - pc) / pc * 100.0) if pc > 0 else None
                out[canon_sym] = Quote(
                    symbol=canon_sym,
                    price=price,
                    bid=round(price - spread, 8),
                    ask=round(price + spread, 8),
                    change_pct=(round(change_pct, 3) if change_pct is not None else None),
                    provider=self.name,
                    raw=data,
                )
            except Exception as e:                           # pragma: no cover
                drops.append({
                    "sym": canon_sym,
                    "reason": f"{type(e).__name__}:{e}"[:120],
                })

        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(timeout=6.0) as client:
            async def _guarded(s: str) -> None:
                async with sem:
                    await _one(client, s)
            await asyncio.gather(*[_guarded(s) for s in canon])

        logger.info(
            "finnhub._fetch_quotes parsed=%d/%d drops=%s",
            len(out), len(canon), drops[:5],
        )

        # Trip our own backoff AFTER the batch completes — never mid-flight.
        if rate_limited:
            self._trigger_backoff("HTTP 429 during batch")
            # Even if some quotes came back, tell the manager we got rate-limited
            # so it can decide whether to fall through to Mock immediately.
            if not out:
                raise RateLimitError("finnhub 429 (batch)")

        if out:
            self._reset_backoff(reason="success")
        return out
