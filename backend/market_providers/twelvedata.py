"""TwelveData Provider — Sprint 7.5 (P0 Fix)

Free tier (as of 2026): 8 credits/min, 800 credits/day. Uses batch quote
endpoint `/quote?symbol=A,B,C` (1 credit per symbol, single HTTP roundtrip).
Symbol mapping is handled internally so consumers keep using our canonical
names (EURUSD, XAUUSD, US30, BTCUSD, USOIL …).

Rate-limit handling (per spec):
    * On any 429 (HTTP status OR JSON `code:429` body) we enter an
      exponential backoff: 30s → 60s → 120s → 240s → 600s (max cap).
    * The provider REJECTS calls while backed-off (raises RateLimitError
      without a network hit) so it never hammers the API.
    * Backoff resets IMMEDIATELY after the first successful request.
    * All 429 events are logged with a timestamp + cooldown seconds.
    * Response headers `api-credits-left` / `api-daily-credits-left` are
      parsed to track credits accurately.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from .base import Provider, Quote, RateLimitError, ProviderNotConfigured

logger = logging.getLogger("market.providers.twelvedata")

BASE_URL = "https://api.twelvedata.com"

# Exponential backoff schedule (seconds). Index into this list by consecutive 429 count.
BACKOFF_SCHEDULE = [30, 60, 120, 240, 600]


def _redact_api_key(text: str, api_key: str) -> str:
    """Return `text` with `api_key` replaced by <REDACTED> — used before we log
    or return API response bodies. Never trust upstream to omit our key."""
    if not text or not api_key:
        return text
    return text.replace(api_key, "<REDACTED>")

# Canonical symbol → TwelveData symbol
SYMBOL_MAP: Dict[str, str] = {
    # Forex majors
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF", "USDCAD": "USD/CAD", "AUDUSD": "AUD/USD",
    "NZDUSD": "NZD/USD", "EURGBP": "EUR/GBP", "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY",
    # Metals
    "XAUUSD": "XAU/USD", "XAGUSD": "XAG/USD",
    # Indices
    "US30": "DJI", "SPX500": "SPX", "NAS100": "NDX",
    "GER40": "DAX", "UK100": "UKX", "JPN225": "N225", "IND50": "NIFTY",
    # Crypto
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD", "XRPUSD": "XRP/USD", "ADAUSD": "ADA/USD",
    # Commodities / energy
    "USOIL": "WTI/USD", "UKOIL": "BRENT/USD", "NATGAS": "NG=F", "COPPER": "HG=F",
}


class TwelveDataProvider(Provider):
    name = "twelvedata"
    priority = 100      # highest priority

    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = (api_key or os.environ.get("TWELVEDATA_API_KEY") or "").strip()
        self.stats.daily_credits_limit = 800

        # Exponential backoff state
        self._backoff_step: int = 0          # 0 = no active backoff
        self._backoff_until: Optional[datetime] = None
        self._last_429_at: Optional[datetime] = None
        self._total_429_events: int = 0

        # Credits tracked from response headers (authoritative when available)
        self._credits_left_minute: Optional[int] = None
        self._credits_left_daily: Optional[int] = None

    # -------- configuration -------- #
    async def is_configured(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, key: str):
        """Rotate the API key and clear ALL prior failure/backoff state so the
        next call starts with a clean slate. Also resets rolling ProviderStats.
        Does NOT auto-call the API — use `test_connection()` for that.
        """
        self._api_key = (key or "").strip()
        # 1. Backoff state (step, until, last_429 timestamps kept as historical)
        self._reset_backoff(reason="api key updated")
        # 2. Credit-header cache
        self._credits_left_minute = None
        self._credits_left_daily = None
        # 3. Rolling health stats (failure_count, last_error, etc.)
        self.stats.reset()
        logger.info("TwelveData: api-key rotated → backoff + stats + credits cleared")

    async def test_connection(self) -> Dict[str, object]:
        """Perform a single lightweight probe of the API using the current key.

        Returns::
            {
              "ok": bool,
              "status_code": int | None,
              "response": <redacted-body-preview>,
              "error": str | None,
              "credits_left_minute": int | None,
              "credits_left_daily":  int | None,
            }

        The API key is never included in the returned payload or the log line.
        On success, this call is *also* counted toward `stats.successful_requests`
        via `_fetch_quotes → record_success`, so the admin banner clears immediately.
        On failure, `stats.last_error` is populated with the exact provider
        response message (not a generic "Failed").
        """
        if not self._api_key:
            return {"ok": False, "status_code": None, "response": None,
                    "error": "no_api_key", "credits_left_minute": None,
                    "credits_left_daily": None}

        params = {"symbol": "EUR/USD", "apikey": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{BASE_URL}/quote", params=params)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            err = f"network error: {type(e).__name__}: {e}"[:300]
            self.stats.record_failure(err)
            logger.warning("TwelveData test_connection: %s", err)
            return {"ok": False, "status_code": None, "response": None,
                    "error": err, "credits_left_minute": None,
                    "credits_left_daily": None}

        self._parse_credit_headers(r)
        body_preview = _redact_api_key(r.text[:600], self._api_key)

        try:
            data = r.json()
        except Exception:
            data = None

        # HTTP-level failure
        if r.status_code >= 400:
            err = (isinstance(data, dict) and (data.get("message") or data.get("status"))) \
                    or f"HTTP {r.status_code}"
            err = str(err)[:300]
            self.stats.record_failure(err, is_rate_limit=(r.status_code == 429))
            if r.status_code == 429:
                self._trigger_backoff("test_connection HTTP 429")
            logger.warning(
                "TwelveData test_connection FAILED status=%d body=%s",
                r.status_code, body_preview,
            )
            return {"ok": False, "status_code": r.status_code, "response": body_preview,
                    "error": err,
                    "credits_left_minute": self._credits_left_minute,
                    "credits_left_daily":  self._credits_left_daily}

        # 200 with an in-body error (401 wrong key, 429 rate limit, etc.)
        if isinstance(data, dict) and data.get("status") == "error":
            msg = str(data.get("message", "unknown error"))[:300]
            self.stats.record_failure(msg, is_rate_limit=("limit" in msg.lower() or "credit" in msg.lower()))
            if data.get("code") == 429 or "credit" in msg.lower() or "limit" in msg.lower():
                self._trigger_backoff(f"test_connection JSON error: {msg[:60]}")
            logger.warning("TwelveData test_connection JSON-error: %s (body=%s)", msg, body_preview)
            return {"ok": False, "status_code": r.status_code, "response": body_preview,
                    "error": msg,
                    "credits_left_minute": self._credits_left_minute,
                    "credits_left_daily":  self._credits_left_daily}

        # 200 OK and a quote present → healthy
        if isinstance(data, dict) and ("close" in data or "price" in data):
            self.stats.record_success(latency_ms=r.elapsed.total_seconds() * 1000)
            self._reset_backoff(reason="test_connection success")
            logger.info("TwelveData test_connection OK")
            return {"ok": True, "status_code": r.status_code, "response": body_preview,
                    "error": None,
                    "credits_left_minute": self._credits_left_minute,
                    "credits_left_daily":  self._credits_left_daily}

        # Unexpected body shape
        self.stats.record_failure("unexpected response shape")
        logger.warning("TwelveData test_connection UNEXPECTED body=%s", body_preview)
        return {"ok": False, "status_code": r.status_code, "response": body_preview,
                "error": "unexpected response shape",
                "credits_left_minute": self._credits_left_minute,
                "credits_left_daily":  self._credits_left_daily}

    # -------- backoff API -------- #
    def is_backed_off(self) -> bool:
        if self._backoff_until is None:
            return False
        if datetime.now(timezone.utc) >= self._backoff_until:
            return False
        return True

    def backoff_remaining_sec(self) -> int:
        if not self.is_backed_off():
            return 0
        return max(0, int((self._backoff_until - datetime.now(timezone.utc)).total_seconds()))

    def backoff_state(self) -> Dict[str, object]:
        return {
            "active": self.is_backed_off(),
            "step": self._backoff_step,
            "remaining_sec": self.backoff_remaining_sec(),
            "until": self._backoff_until.isoformat() if self._backoff_until else None,
            "last_429_at": self._last_429_at.isoformat() if self._last_429_at else None,
            "total_429_events": self._total_429_events,
            "schedule": BACKOFF_SCHEDULE,
            "credits_left_minute": self._credits_left_minute,
            "credits_left_daily": self._credits_left_daily,
        }

    def _trigger_backoff(self, reason: str):
        idx = min(self._backoff_step, len(BACKOFF_SCHEDULE) - 1)
        wait_sec = BACKOFF_SCHEDULE[idx]
        self._backoff_step += 1
        self._total_429_events += 1
        self._last_429_at = datetime.now(timezone.utc)
        self._backoff_until = self._last_429_at + timedelta(seconds=wait_sec)
        logger.warning(
            "TwelveData 429 (%s) — backoff #%d, waiting %ds until %s (total 429s=%d)",
            reason, self._backoff_step, wait_sec,
            self._backoff_until.isoformat(), self._total_429_events,
        )

    def _reset_backoff(self, reason: str = "success"):
        if self._backoff_step or self._backoff_until:
            logger.info("TwelveData backoff reset (%s), was step=%d",
                        reason, self._backoff_step)
        self._backoff_step = 0
        self._backoff_until = None

    def _parse_credit_headers(self, resp: httpx.Response):
        try:
            m = resp.headers.get("api-credits-left") or resp.headers.get("X-RateLimit-Remaining")
            d = resp.headers.get("api-daily-credits-left")
            if m is not None:
                self._credits_left_minute = int(m)
            if d is not None:
                self._credits_left_daily = int(d)
        except (ValueError, TypeError):
            pass

    async def fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Overrides base to reconcile authoritative credit headers AFTER
        the base class's `record_success` increments daily_credits_used."""
        result = await super().fetch_quotes(symbols)
        # If server told us how many credits remain, use it (authoritative).
        if self._credits_left_daily is not None:
            self.stats.daily_credits_used = max(
                0, self.stats.daily_credits_limit - self._credits_left_daily
            )
        return result

    # -------- fetch -------- #
    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        if not self._api_key:
            logger.info("TD._fetch_quotes: NOT CONFIGURED (empty api key) — raising ProviderNotConfigured")
            raise ProviderNotConfigured("TWELVEDATA_API_KEY not set")

        # Guard: don't hammer the API while in backoff
        if self.is_backed_off():
            remaining = self.backoff_remaining_sec()
            logger.info(
                "TD._fetch_quotes: BACKED OFF (step=%d, %ds remaining) — raising RateLimitError",
                self._backoff_step, remaining,
            )
            raise RateLimitError(
                f"backoff active — {remaining}s remaining "
                f"(step {self._backoff_step}, next attempt at "
                f"{self._backoff_until.isoformat() if self._backoff_until else 'n/a'})"
            )

        canon = [s.upper() for s in symbols]
        td_syms = [SYMBOL_MAP.get(s, s) for s in canon]
        # De-dup while preserving order (some canonicals map to same TD symbol)
        seen: Dict[str, None] = {}
        td_syms_unique = [s for s in td_syms if not (s in seen or seen.setdefault(s, None))]
        params = {"symbol": ",".join(td_syms_unique), "apikey": self._api_key}
        logger.info(
            "TD._fetch_quotes → GET /quote  canon=%s  td_syms_unique=%s  (n=%d, credits_left_min=%s, daily=%s)",
            canon, td_syms_unique, len(td_syms_unique),
            self._credits_left_minute, self._credits_left_daily,
        )

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{BASE_URL}/quote", params=params)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            # Network-level failure — let manager count toward circuit breaker
            logger.warning("TD._fetch_quotes: network error %s: %s", type(e).__name__, e)
            raise Exception(f"twelvedata network error: {type(e).__name__}: {e}")

        # Update credit trackers from headers regardless of status
        self._parse_credit_headers(r)
        logger.info(
            "TD._fetch_quotes ← HTTP %d  bytes=%d  credits_left_min=%s  daily=%s",
            r.status_code, len(r.content),
            self._credits_left_minute, self._credits_left_daily,
        )

        # HTTP-level 429
        if r.status_code == 429:
            self._trigger_backoff("HTTP 429")
            raise RateLimitError("TwelveData HTTP 429 rate limit hit")

        if r.status_code >= 500:
            raise Exception(f"TwelveData server error: HTTP {r.status_code}")

        # 200 but JSON body may still indicate an error / rate-limit
        try:
            data = r.json()
        except Exception:
            raise Exception(f"TwelveData invalid JSON: {r.text[:150]}")

        # Rate-limit signalled inside the body (very common with TwelveData)
        if isinstance(data, dict) and data.get("code") == 429:
            self._trigger_backoff(f"JSON 429: {data.get('message', '')[:80]}")
            raise RateLimitError(data.get("message", "TwelveData rate limit (JSON)"))

        # Some responses embed a "status": "error" per symbol; a global error looks like:
        # {"code": 401, "message": "You did not specify a valid api key.", "status": "error"}
        if isinstance(data, dict) and data.get("status") == "error" and "symbol" not in data:
            msg = str(data.get("message", ""))
            logger.warning(
                "TD._fetch_quotes: GLOBAL error status=error code=%s msg=%s (batch=%s) — "
                "this fails the entire batch and will cause manager to fall back",
                data.get("code"), msg[:150], td_syms_unique,
            )
            if "credit" in msg.lower() or "limit" in msg.lower() or "429" in msg:
                self._trigger_backoff(f"error message rate-limit: {msg[:60]}")
                raise RateLimitError(msg)
            raise Exception(f"TwelveData error: {msg[:150]}")

        # Successful response — parse quotes
        out: Dict[str, Quote] = {}
        drops: List[Dict[str, Any]] = []

        # Batch response is dict[td_symbol → payload] OR (single symbol) a flat payload
        if isinstance(data, dict) and "symbol" in data and "close" in data:
            data = {data["symbol"]: data}

        for i, td_sym in enumerate(td_syms):
            payload = data.get(td_sym) if isinstance(data, dict) else None
            if not payload:
                drops.append({"canon": canon[i], "td_sym": td_sym, "reason": "no payload in response"})
                continue
            if payload.get("status") == "error":
                msg = (payload.get("message") or "").lower()
                if "credit" in msg or "limit" in msg:
                    # Per-symbol rate-limit → treat as global 429
                    self._trigger_backoff(f"per-symbol RL: {msg[:60]}")
                    raise RateLimitError(payload.get("message", "rate limit"))
                drops.append({"canon": canon[i], "td_sym": td_sym,
                              "reason": f"per-symbol error: {msg[:80]}"})
                continue
            try:
                price = float(payload["close"])
            except (KeyError, ValueError, TypeError) as _e:
                drops.append({"canon": canon[i], "td_sym": td_sym,
                              "reason": f"unparseable close: {type(_e).__name__}"})
                continue
            change_pct = None
            try:
                change_pct = float(payload.get("percent_change") or 0) or None
            except (ValueError, TypeError):
                pass
            out[canon[i]] = Quote(
                symbol=canon[i], price=price,
                change_pct=change_pct, provider=self.name, raw=payload,
            )

        logger.info(
            "TD._fetch_quotes done: parsed=%d/%d  drops=%s",
            len(out), len(canon), drops[:8],
        )
        # Successful call → clear any backoff
        if out:
            self._reset_backoff(reason="success")
        return out
