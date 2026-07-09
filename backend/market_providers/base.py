"""Live Market Providers — Base contract (Sprint 7.5)

Every provider implements this interface. The Provider Manager treats them
identically. Providers own their own rate-limit tracking and HTTP client.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Quote:
    symbol: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    change_pct: Optional[float] = None      # 24h % change if provider offers it
    provider: str = "unknown"
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class ProviderStats:
    """Rolling health stats. Reset per-process; persisted snapshots go to mongo."""
    name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    last_error: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    avg_response_ms: float = 0.0
    daily_credits_used: int = 0             # provider-tracked
    daily_credits_limit: int = 0
    # Rolling window for latency (last 50 requests)
    _latency_ms: List[float] = field(default_factory=list)

    def record_success(self, latency_ms: float, credits: int = 1):
        self.total_requests += 1
        self.successful_requests += 1
        self.daily_credits_used += credits
        self.last_success_at = datetime.now(timezone.utc)
        self._latency_ms.append(latency_ms)
        if len(self._latency_ms) > 50:
            self._latency_ms = self._latency_ms[-50:]
        self.avg_response_ms = round(sum(self._latency_ms) / len(self._latency_ms), 2)

    def record_failure(self, err: str, is_rate_limit: bool = False):
        self.total_requests += 1
        self.failed_requests += 1
        if is_rate_limit:
            self.rate_limited_requests += 1
        self.last_error = err[:200]
        self.last_error_at = datetime.now(timezone.utc)

    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.failed_requests / self.total_requests * 100, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rate_limited_requests": self.rate_limited_requests,
            "error_rate_pct": self.error_rate(),
            "avg_response_ms": self.avg_response_ms,
            "daily_credits_used": self.daily_credits_used,
            "daily_credits_limit": self.daily_credits_limit,
            "credits_remaining": max(0, self.daily_credits_limit - self.daily_credits_used) if self.daily_credits_limit else None,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
        }


class Provider:
    """Abstract base — subclass and implement `_fetch_quotes`."""
    name: str = "base"
    priority: int = 100    # lower = higher priority

    def __init__(self):
        self.stats = ProviderStats(name=self.name)

    async def is_configured(self) -> bool:
        """Does this provider have the credentials needed to run?"""
        return True

    async def fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Return quotes for given symbols. Providers responsible for symbol translation."""
        t0 = time.perf_counter()
        try:
            result = await self._fetch_quotes(symbols)
            self.stats.record_success((time.perf_counter() - t0) * 1000, credits=len(symbols))
            return result
        except RateLimitError as e:
            self.stats.record_failure(str(e), is_rate_limit=True)
            raise
        except Exception as e:
            self.stats.record_failure(f"{type(e).__name__}: {e}")
            raise

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        raise NotImplementedError

    async def health_check(self) -> Dict[str, Any]:
        """Lightweight ping. Returns {ok:bool, latency_ms:float, note:str}."""
        try:
            t0 = time.perf_counter()
            q = await self.fetch_quotes(["EURUSD"])
            ms = round((time.perf_counter() - t0) * 1000, 2)
            return {"ok": "EURUSD" in q, "latency_ms": ms, "note": f"got {len(q)} quotes"}
        except Exception as e:
            return {"ok": False, "latency_ms": None, "note": f"{type(e).__name__}: {e}"}


class RateLimitError(Exception):
    pass


class ProviderNotConfigured(Exception):
    pass
