"""Provider Manager — Sprint 7.5 (P0 Fix)

Owns:
  * The ordered list of providers (TwelveData → AlphaVantage → Mock)
  * A per-provider circuit breaker (NETWORK errors only — 429s handled by
    the provider's own exponential backoff)
  * Background refresh worker (every 60 sec by default — free-tier friendly)
  * Automatic fallback on error / rate-limit / backoff
  * Admin controls (manual provider switch, auto-fallback toggle)

Design principles (Sprint 7.5 P0):
  * ONE batch HTTP request per refresh interval (never N per interval)
  * 429s do NOT open the circuit breaker — they trigger provider backoff
  * Consumers ALWAYS read from cache — never fail because of a provider
  * Market health status reflects cache age + active provider

Thread safety: single asyncio task refreshes; consumers only READ from the
QuoteCache.
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .base import Provider, ProviderNotConfigured, RateLimitError
from .cache import QuoteCache, FRESH_MAX_SEC, STALE_MAX_SEC
from .mock import MockProvider
from .twelvedata import TwelveDataProvider
from .alphavantage import AlphaVantageProvider

logger = logging.getLogger("market.providers.manager")


# Default set — Sprint 7.5 top-20 universe (matches user-approved list)
DEFAULT_UNIVERSE = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "XAUUSD", "XAGUSD",
    "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500", "GER40", "UK100", "IND50",
    "USOIL", "UKOIL", "NATGAS",
]

# Default refresh cadence — free-tier friendly
DEFAULT_REFRESH_INTERVAL_SEC = 60
DEFAULT_CACHE_TTL_SEC = 60


class CircuitBreaker:
    """N consecutive *hard* failures → open for `open_secs`.

    NOTE: Rate-limit (429) events are NOT counted here — providers handle
    their own exponential backoff. Only network errors / 5xx trip this.
    """

    def __init__(self, name: str, fail_threshold: int = 3, open_secs: int = 120):
        self.name = name
        self.fail_threshold = fail_threshold
        self.open_secs = open_secs
        self.consecutive_failures = 0
        self.opened_at: Optional[datetime] = None

    @property
    def open(self) -> bool:
        if not self.opened_at:
            return False
        expiry = self.opened_at + timedelta(seconds=self.open_secs)
        if datetime.now(timezone.utc) >= expiry:
            # Auto-close for a retry
            self.opened_at = None
            self.consecutive_failures = 0
            return False
        return True

    def record_success(self):
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.fail_threshold:
            self.opened_at = datetime.now(timezone.utc)
            logger.warning("circuit %s opened for %ss", self.name, self.open_secs)

    def state(self) -> Dict[str, Any]:
        return {
            "open": self.open,
            "consecutive_failures": self.consecutive_failures,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
        }


class ProviderManager:
    _CONF_COLL = "market_provider_config"
    _HIST_COLL = "market_provider_history"

    def __init__(self, db, universe: Optional[List[str]] = None,
                 refresh_interval_sec: int = DEFAULT_REFRESH_INTERVAL_SEC):
        self.db = db
        self.universe = list(universe or DEFAULT_UNIVERSE)
        self.refresh_interval_sec = refresh_interval_sec
        self.cache = QuoteCache(db, ttl_seconds=DEFAULT_CACHE_TTL_SEC)

        # Build providers in priority order (lower priority number = tried first)
        self.providers: List[Provider] = [
            TwelveDataProvider(),
            AlphaVantageProvider(),
            MockProvider(),
        ]
        self.providers.sort(key=lambda p: p.priority)
        self._by_name = {p.name: p for p in self.providers}
        self._breakers = {p.name: CircuitBreaker(p.name) for p in self.providers}

        # Config (persisted)
        self._auto_fallback = True
        self._manual_provider: Optional[str] = None    # if set, ONLY use this one

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_refresh: Optional[datetime] = None
        self._last_active_provider: Optional[str] = None
        self._last_refresh_error: Optional[str] = None
        # Track when a real (non-mock) provider last succeeded — for market health
        self._last_real_success_at: Optional[datetime] = None
        self._last_real_provider: Optional[str] = None

    # ================ lifecycle ================
    async def start(self):
        await self._load_config()
        try:
            await self.cache.ensure_indexes()   # Sprint 14.1: audit + TTL index
        except Exception as e:
            logger.warning("cache ensure_indexes failed (non-fatal): %s", e)
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("ProviderManager started (interval=%ss, ttl=%ss, universe=%d)",
                    self.refresh_interval_sec, self.cache.ttl_seconds, len(self.universe))

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None

    async def _load_config(self):
        doc = await self.db[self._CONF_COLL].find_one({"_id": "active"})
        if not doc:
            return
        self._auto_fallback = bool(doc.get("auto_fallback", True))
        self._manual_provider = doc.get("manual_provider")
        self.universe = list(doc.get("universe") or self.universe)
        # Enforce free-tier friendly minimum (P0 fix — old configs with 10s
        # cadence would exhaust the free tier).
        stored_interval = int(doc.get("refresh_interval_sec") or self.refresh_interval_sec)
        if stored_interval < DEFAULT_REFRESH_INTERVAL_SEC:
            logger.info("upgrading stored refresh_interval_sec %ss → %ss (P0 free-tier safety)",
                        stored_interval, DEFAULT_REFRESH_INTERVAL_SEC)
            self.refresh_interval_sec = DEFAULT_REFRESH_INTERVAL_SEC
            await self._save_config({"refresh_interval_sec": DEFAULT_REFRESH_INTERVAL_SEC})
        else:
            self.refresh_interval_sec = stored_interval
        # Load API keys if stored
        td_key = doc.get("twelvedata_api_key")
        av_key = doc.get("alphavantage_api_key")
        if td_key:
            self._by_name["twelvedata"].set_api_key(td_key)  # type: ignore[attr-defined]
        if av_key:
            self._by_name["alphavantage"].set_api_key(av_key)  # type: ignore[attr-defined]

    async def _save_config(self, patch: Dict[str, Any]):
        await self.db[self._CONF_COLL].update_one(
            {"_id": "active"}, {"$set": patch}, upsert=True)

    # ================ refresh loop ================
    async def _refresh_loop(self):
        while not self._stop.is_set():
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("refresh loop crashed: %s", e)
            await asyncio.sleep(self.refresh_interval_sec)

    async def refresh_once(self, _visited: Optional[set] = None) -> Dict[str, Any]:
        """Fetch all symbols from best available provider and update cache.

        On 429: DO NOT trip circuit breaker — provider handles its own
        exponential backoff. Fall through to next provider if auto_fallback.
        On network/5xx: count toward circuit breaker.
        """
        _visited = _visited or set()
        t0 = time.perf_counter()
        chosen = await self._choose_provider(exclude=_visited)
        if not chosen:
            self._last_refresh_error = "no providers available"
            return {"provider": None, "count": 0, "error": self._last_refresh_error}
        _visited.add(chosen.name)
        try:
            quotes = await chosen.fetch_quotes(self.universe)
            write_result = await self.cache.put_many(quotes)
            # Sprint 7.5: also push to in-process memo so sync consumers
            # (ai_intelligence.feed / TA / signals) can read live prices
            # without an async round-trip.
            try:
                from ai_intelligence import feed as _ai_feed
                for sym, q in quotes.items():
                    _ai_feed.publish_price(sym, q.price)
            except Exception:
                pass
            self._breakers[chosen.name].record_success()
            self._last_refresh = datetime.now(timezone.utc)
            self._last_active_provider = chosen.name
            self._last_refresh_error = None
            if chosen.name != "mock":
                self._last_real_success_at = self._last_refresh
                self._last_real_provider = chosen.name
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            await self._log_history(chosen.name, ok=True, count=len(quotes), latency_ms=elapsed_ms)
            # Sprint 14.1: expose write accept/reject counts so admins see
            # when mock/stale writes are being blocked.
            if write_result.get("rejected", 0) > 0:
                logger.info(
                    "provider %s refresh: %d accepted, %d rejected by cache guard",
                    chosen.name, write_result["accepted"], write_result["rejected"],
                )
            return {"provider": chosen.name, "count": len(quotes),
                    "accepted": write_result.get("accepted", 0),
                    "rejected": write_result.get("rejected", 0),
                    "latency_ms": elapsed_ms, "auto_fallback": self._auto_fallback}
        except RateLimitError as e:
            # 429 → provider is now in backoff; do NOT trip circuit breaker.
            self._last_refresh_error = f"{chosen.name}: rate limited ({e})"
            logger.warning("provider %s rate-limited: %s", chosen.name, e)
            await self._log_history(chosen.name, ok=False,
                                    error=f"429/backoff: {e}")
            if self._auto_fallback:
                return await self.refresh_once(_visited=_visited)
            return {"provider": chosen.name, "count": 0, "error": str(e)}
        except ProviderNotConfigured as e:
            # Missing creds → don't trip breaker; try next provider
            self._last_refresh_error = f"{chosen.name}: not configured"
            await self._log_history(chosen.name, ok=False, error=str(e))
            if self._auto_fallback:
                return await self.refresh_once(_visited=_visited)
            return {"provider": chosen.name, "count": 0, "error": str(e)}
        except Exception as e:
            # Real failure (network / 5xx) → count toward circuit breaker
            self._breakers[chosen.name].record_failure()
            self._last_refresh_error = f"{chosen.name}: {e}"
            await self._log_history(chosen.name, ok=False, error=str(e))
            if self._auto_fallback:
                return await self.refresh_once(_visited=_visited)
            return {"provider": chosen.name, "count": 0, "error": str(e)}

    async def _choose_provider(self, exclude: Optional[set] = None) -> Optional[Provider]:
        exclude = exclude or set()
        # Manual override wins
        if self._manual_provider:
            p = self._by_name.get(self._manual_provider)
            if p and p.name not in exclude:
                if p.name == "mock":
                    return p
                if not self._breakers[p.name].open and not p.is_backed_off():
                    try:
                        if await p.is_configured():
                            return p
                    except Exception:
                        pass
        # Auto: pick the highest priority provider that is configured,
        # not tripped, and not in exponential backoff
        for p in self.providers:
            if p.name in exclude:
                continue
            if self._breakers[p.name].open:
                continue
            if p.is_backed_off():
                continue
            try:
                if await p.is_configured():
                    return p
            except Exception:
                continue
        # Ultimate fallback: mock always works (unless already visited)
        m = self._by_name.get("mock")
        if m and m.name not in exclude:
            return m
        return None

    async def _log_history(self, provider: str, ok: bool,
                           count: int = 0, latency_ms: float = 0.0,
                           error: Optional[str] = None):
        try:
            await self.db[self._HIST_COLL].insert_one({
                "provider": provider, "ok": bool(ok),
                "count": int(count), "latency_ms": float(latency_ms),
                "error": error, "at": datetime.now(timezone.utc),
            })
            # Trim to last 200 records (keep collection small)
            total = await self.db[self._HIST_COLL].estimated_document_count()
            if total > 500:
                cur = self.db[self._HIST_COLL].find({}, {"_id": 1}).sort("at", -1).skip(200).limit(1000)
                ids = [d["_id"] async for d in cur]
                if ids:
                    await self.db[self._HIST_COLL].delete_many({"_id": {"$in": ids}})
        except Exception as e:
            logger.debug("history log skipped: %s", e)

    # ================ market health status ================
    async def _market_status(self) -> Dict[str, Any]:
        """Derive LIVE / STALE / FALLBACK status for the admin panel.

        LIVE     — real provider active AND newest cache age <= (refresh_interval + 5s grace)
        STALE    — real provider recent but newest cache within 5min window
        FALLBACK — active provider is mock (no real provider available)
                   OR cache is >5 minutes old (real providers failing continuously)

        Note: The "LIVE" threshold matches the refresh cadence (so cache doesn't
        oscillate green→amber every cycle during healthy operation).
        """
        cache_stats = await self.cache.stats()
        newest = cache_stats.get("newest_age_sec") or 0
        active = self._last_active_provider
        # LIVE window = refresh_interval + 5s grace (min 30s)
        live_max = max(FRESH_MAX_SEC, self.refresh_interval_sec + 5)
        if active == "mock" or active is None:
            state = "FALLBACK"
            tint = "blue"
            reason = "using Mock provider — real providers unavailable"
        elif newest <= live_max:
            state = "LIVE"
            tint = "green"
            reason = f"{active} — fresh ({newest}s, refresh every {self.refresh_interval_sec}s)"
        elif newest <= STALE_MAX_SEC:
            state = "STALE"
            tint = "amber"
            reason = f"{active} — serving cache ({newest}s old)"
        else:
            state = "FALLBACK"
            tint = "blue"
            reason = f"cache too old ({newest}s) — falling back to Mock"
        return {
            "state": state,
            "tint": tint,
            "reason": reason,
            "newest_age_sec": newest,
            "oldest_age_sec": cache_stats.get("oldest_age_sec"),
            "live_max_sec": live_max,
            "stale_max_sec": STALE_MAX_SEC,
            "last_real_success_at": self._last_real_success_at.isoformat()
                if self._last_real_success_at else None,
            "last_real_provider": self._last_real_provider,
        }

    # ================ admin API surface ================
    async def status(self) -> Dict[str, Any]:
        cache_stats = await self.cache.stats()
        active = self._last_active_provider
        if not active:
            fallback = await self._choose_provider()
            active = fallback.name if fallback else None
        market_status = await self._market_status()
        return {
            "active_provider": active,
            "last_active_provider": self._last_active_provider,
            "last_real_provider": self._last_real_provider,
            "last_real_success_at": self._last_real_success_at.isoformat()
                if self._last_real_success_at else None,
            "last_refresh_at": self._last_refresh.isoformat() if self._last_refresh else None,
            "last_refresh_error": self._last_refresh_error,
            "refresh_interval_sec": self.refresh_interval_sec,
            "auto_fallback": self._auto_fallback,
            "manual_provider": self._manual_provider,
            "universe": self.universe,
            "cache": cache_stats,
            "market_status": market_status,
            "providers": [
                {**p.stats.to_dict(),
                 "priority": p.priority,
                 "configured": await p.is_configured(),
                 "circuit": self._breakers[p.name].state(),
                 "backoff": p.backoff_state()}
                for p in self.providers
            ],
        }

    async def health_check(self, name: Optional[str] = None) -> Dict[str, Any]:
        if name:
            p = self._by_name.get(name)
            if not p:
                return {"error": f"unknown provider {name}"}
            return {name: await p.health_check()}
        results: Dict[str, Any] = {}
        for p in self.providers:
            results[p.name] = await p.health_check()
        return results

    async def set_manual_provider(self, name: Optional[str]):
        if name and name not in self._by_name:
            raise ValueError(f"unknown provider {name}")
        self._manual_provider = name or None
        await self._save_config({"manual_provider": self._manual_provider})

    async def set_auto_fallback(self, enabled: bool):
        self._auto_fallback = bool(enabled)
        await self._save_config({"auto_fallback": self._auto_fallback})

    async def set_refresh_interval(self, seconds: int):
        seconds = max(5, min(300, int(seconds)))
        self.refresh_interval_sec = seconds
        await self._save_config({"refresh_interval_sec": seconds})

    async def set_universe(self, symbols: List[str]):
        clean = [s.upper() for s in symbols if s.strip()]
        self.universe = clean
        await self._save_config({"universe": clean})

    async def set_api_key(self, provider: str, key: str) -> Dict[str, Any]:
        """Rotate the API key of a provider and immediately test it.

        Returns the test-connection result so the admin UI can display the
        exact provider response (success or exact error text). Also clears:
          * provider backoff (failure_count, backoff_step, next_retry_at)
          * provider rolling stats (last_error, failed_requests, ...)
          * circuit breaker state (breaker.opened_at, consecutive_failures)
          * cached quotes for this provider's supported symbols (best-effort;
            the shared price cache is short-TTL so stale prices roll off
            within the next refresh cycle regardless)
        """
        p = self._by_name.get(provider)
        if not p or not hasattr(p, "set_api_key"):
            raise ValueError(f"provider {provider} does not accept API keys")

        # 1. Rotate key on provider (this also calls stats.reset + backoff reset)
        p.set_api_key(key)  # type: ignore[attr-defined]

        # 2. Persist to DB
        field = f"{provider}_api_key"
        await self._save_config({field: (key or "").strip()})

        # 3. Reset circuit breaker for this provider
        br = self._breakers.get(provider)
        if br is not None:
            br.opened_at = None
            br.consecutive_failures = 0

        # 4. Best-effort clear of any cached prices last-served BY this provider,
        # so followers stop seeing stale values from the old key run.
        try:
            await self.cache.invalidate_by_source(provider)   # type: ignore[attr-defined]
        except AttributeError:
            pass    # cache may not implement this — non-fatal

        # 5. Immediately probe the API with the new key
        test_result: Dict[str, Any] = {"ok": None, "skipped": "no test_connection"}
        if hasattr(p, "test_connection"):
            try:
                test_result = await p.test_connection()  # type: ignore[attr-defined]
            except Exception as e:                       # pragma: no cover
                test_result = {"ok": False, "error": f"probe raised: {type(e).__name__}: {e}"}

        # 6. Record a provider-history event for auditing
        try:
            await self.db[self._HIST_COLL].insert_one({
                "at": datetime.now(timezone.utc),
                "provider": provider,
                "event": "api_key_rotated",
                "test_ok": bool(test_result.get("ok")),
                "test_error": (test_result.get("error") or None) if not test_result.get("ok") else None,
            })
        except Exception:
            pass

        return {
            "provider": provider,
            "configured": bool((key or "").strip()),
            "test_ok": bool(test_result.get("ok")),
            "test_result": test_result,
        }

    async def recent_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.db[self._HIST_COLL].find({}, {"_id": 0}).sort("at", -1).limit(limit)
        rows = []
        async for d in cur:
            if isinstance(d.get("at"), datetime):
                d["at"] = d["at"].isoformat()
            rows.append(d)
        return rows

    # ================ Consumer read helpers ================
    async def get_price(self, symbol: str) -> Optional[float]:
        return await self.cache.get_price(symbol)

    async def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        return await self.cache.get_prices(symbols)
