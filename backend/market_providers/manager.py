"""Provider Manager — Sprint 7.5

Owns:
  * The ordered list of providers (TwelveData → AlphaVantage → Mock)
  * A per-provider circuit breaker
  * Background refresh worker (every 10 sec by default)
  * Automatic fallback on error / rate-limit
  * Admin controls (manual provider switch, auto-fallback toggle)

Thread safety: single asyncio task refreshes; consumers only READ from the
QuoteCache. No consumer calls providers directly.
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .base import Provider, ProviderNotConfigured, RateLimitError
from .cache import QuoteCache
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


class CircuitBreaker:
    """Very small circuit breaker: N consecutive failures → open for `open_secs`."""

    def __init__(self, name: str, fail_threshold: int = 3, open_secs: int = 60):
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
                 refresh_interval_sec: int = 10):
        self.db = db
        self.universe = list(universe or DEFAULT_UNIVERSE)
        self.refresh_interval_sec = refresh_interval_sec
        self.cache = QuoteCache(db, ttl_seconds=30)

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

    # ================ lifecycle ================
    async def start(self):
        await self._load_config()
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("ProviderManager started (interval=%ss, universe=%d)",
                    self.refresh_interval_sec, len(self.universe))

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
        self.refresh_interval_sec = int(doc.get("refresh_interval_sec") or self.refresh_interval_sec)
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

    async def refresh_once(self) -> Dict[str, Any]:
        """Fetch all symbols from best available provider and update cache."""
        t0 = time.perf_counter()
        chosen = await self._choose_provider()
        if not chosen:
            self._last_refresh_error = "no providers available"
            return {"provider": None, "count": 0, "error": self._last_refresh_error}
        try:
            quotes = await chosen.fetch_quotes(self.universe)
            await self.cache.put_many(quotes)
            # Sprint 7.5: also push to in-process memo so sync consumers
            # (ai_intelligence.feed / TA / signals) can read live prices without
            # an async round-trip.
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
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            await self._log_history(chosen.name, ok=True, count=len(quotes), latency_ms=elapsed_ms)
            return {"provider": chosen.name, "count": len(quotes),
                    "latency_ms": elapsed_ms, "auto_fallback": self._auto_fallback}
        except (RateLimitError, ProviderNotConfigured) as e:
            self._breakers[chosen.name].record_failure()
            self._last_refresh_error = f"{chosen.name}: {e}"
            await self._log_history(chosen.name, ok=False, error=str(e))
            if self._auto_fallback:
                # Recursively try next provider (breaker will filter out failed one)
                return await self.refresh_once()
            return {"provider": chosen.name, "count": 0, "error": str(e)}
        except Exception as e:
            self._breakers[chosen.name].record_failure()
            self._last_refresh_error = f"{chosen.name}: {e}"
            await self._log_history(chosen.name, ok=False, error=str(e))
            if self._auto_fallback:
                return await self.refresh_once()
            return {"provider": chosen.name, "count": 0, "error": str(e)}

    async def _choose_provider(self) -> Optional[Provider]:
        # Manual override wins
        if self._manual_provider:
            p = self._by_name.get(self._manual_provider)
            if p and await p.is_configured() and not self._breakers[p.name].open:
                return p
            if p and self._manual_provider == "mock":
                return p  # mock is always ok
        # Auto: pick the highest priority provider that is configured & not tripped
        for p in self.providers:
            if self._breakers[p.name].open:
                continue
            try:
                if await p.is_configured():
                    return p
            except Exception:
                continue
        # Ultimate fallback: mock always works
        return self._by_name.get("mock")

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

    # ================ admin API surface ================
    async def status(self) -> Dict[str, Any]:
        cache_stats = await self.cache.stats()
        active = self._last_active_provider or (await self._choose_provider()).name if any(self.providers) else None
        return {
            "active_provider": active,
            "last_active_provider": self._last_active_provider,
            "last_refresh_at": self._last_refresh.isoformat() if self._last_refresh else None,
            "last_refresh_error": self._last_refresh_error,
            "refresh_interval_sec": self.refresh_interval_sec,
            "auto_fallback": self._auto_fallback,
            "manual_provider": self._manual_provider,
            "universe": self.universe,
            "cache": cache_stats,
            "providers": [
                {**p.stats.to_dict(),
                 "priority": p.priority,
                 "configured": await p.is_configured(),
                 "circuit": self._breakers[p.name].state()}
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

    async def set_api_key(self, provider: str, key: str):
        p = self._by_name.get(provider)
        if not p or not hasattr(p, "set_api_key"):
            raise ValueError(f"provider {provider} does not accept API keys")
        p.set_api_key(key)  # type: ignore[attr-defined]
        field = f"{provider}_api_key"
        await self._save_config({field: (key or "").strip()})
        # Reset breaker so it retries immediately
        self._breakers[provider].opened_at = None
        self._breakers[provider].consecutive_failures = 0

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
