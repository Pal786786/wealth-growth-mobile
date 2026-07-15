"""Mongo-backed Quote Cache (Sprint 7.5 / 14.1 hardened)

Single source of truth for live prices. Every consumer (Forex, AI Signals,
Watchlist, Copy Trading, Price Alerts, Gold) reads from here. NO consumer
should call providers directly. The Provider Manager writes here after each
refresh.

Cache TTL: 60 seconds (Sprint 7.5 P0 fix — free-tier friendly).

Freshness thresholds:
  * <30s   → LIVE   (green)
  * 30–300s → STALE  (amber — still serve, retry providers)
  * >300s  → EXPIRED (blue — force Mock fallback)

Sprint 14.1 hardening (prevents mock/stale overwrites of live prices):
  * Every write is now `_put_one` guarded by source-priority + timestamp rules
  * `source` field added: "LIVE" | "STALE" | "MOCK" | "CACHE"
  * Every write emits a structured audit log (`market_cache_writes` collection)
    including timestamp, provider, symbol, old price, new price, reason,
    and whether the write was ACCEPTED or REJECTED.
  * Full trace of who last touched each row (`last_write_reason`).
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

_COLL = "market_price_cache"
_AUDIT_COLL = "market_cache_writes"

# Freshness thresholds (seconds)
FRESH_MAX_SEC = 30       # <30s → LIVE
STALE_MAX_SEC = 300      # 30–300s → STALE; >300s → EXPIRED (fallback)

# Provider priority for "who wins on conflict" (lower = higher priority).
# MUST stay in sync with each provider class's `priority` attribute.
# Sprint 15.0 — Finnhub is the sole primary. TwelveData & AlphaVantage
# entries retained (code not deleted, just disabled at manager level) so
# any legacy rows already in the cache classify sanely on read.
_PROVIDER_PRIORITY = {
    "finnhub":      100,     # PRIMARY (Sprint 15.0)
    "twelvedata":   150,     # legacy — disabled at manager level
    "alphavantage": 200,     # legacy — disabled at manager level
    "binance":      110,     # for BTCUSD only, treated as LIVE
    "mock":         999,     # last-resort fallback
    "unknown":      500,
}

# "LIVE" bucket = any real provider (priority < 300). Mock is degraded.
_LIVE_PROVIDERS = {"finnhub", "twelvedata", "alphavantage", "binance"}

logger = logging.getLogger("market.cache")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _classify(provider: str, age_sec: float) -> str:
    """Compute the `source` label for the cached row given its age + provider."""
    p = (provider or "unknown").lower()
    if p == "mock":
        return "MOCK"
    if age_sec <= FRESH_MAX_SEC:
        return "LIVE"
    if age_sec <= STALE_MAX_SEC:
        return "STALE"
    return "CACHE"      # too old — will be treated as expired by consumers


class QuoteCache:
    def __init__(self, db, ttl_seconds: int = 60, *,
                 audit_enabled: bool = True, audit_retention_hours: int = 24):
        self.db = db
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._audit_enabled = audit_enabled
        self._audit_retention_hours = audit_retention_hours
        # In-process counters for quick health snapshot
        self._writes_accepted = 0
        self._writes_rejected = 0
        self._writes_by_provider: Dict[str, int] = {}

    # =========================================================================
    #  WRITE PATH  (all writes MUST go through _put_one for the guard to apply)
    # =========================================================================
    async def put_many(self, quotes: Dict[str, Any]) -> Dict[str, int]:
        """Upsert many quotes. Returns {"accepted": N, "rejected": M}.
        Uses the source-priority guard so a low-priority (e.g. Mock) provider
        cannot clobber a fresh LIVE row served by TwelveData/AlphaVantage.
        """
        if not quotes:
            return {"accepted": 0, "rejected": 0}
        acc = rej = 0
        for symbol, q in quotes.items():
            ok = await self._put_one(symbol, q)
            if ok:
                acc += 1
            else:
                rej += 1
        return {"accepted": acc, "rejected": rej}

    async def _put_one(self, symbol: str, q: Any) -> bool:
        """Atomic upsert with priority + timestamp guard.

        A write is REJECTED (and audit-logged as such) when:
          * an existing row has a HIGHER-priority provider AND is younger than
            `STALE_MAX_SEC` (i.e. a real live quote hasn't gone stale yet), OR
          * the incoming quote's provider timestamp is OLDER than the stored one.

        Returns True on ACCEPTED, False on REJECTED.
        """
        sym = symbol.upper()
        now = _now()
        new_provider = (getattr(q, "provider", "unknown") or "unknown").lower()
        new_price    = float(q.price)
        new_prov_ts  = getattr(q, "ts", None) or now
        new_prio     = _PROVIDER_PRIORITY.get(new_provider, 500)

        existing = await self.db[_COLL].find_one({"symbol": sym}, {"_id": 0})

        # ------- guard 1: priority ------
        if existing:
            old_provider = (existing.get("provider") or "unknown").lower()
            old_prio     = _PROVIDER_PRIORITY.get(old_provider, 500)
            old_updated  = existing.get("updated_at")
            if isinstance(old_updated, datetime) and old_updated.tzinfo is None:
                old_updated = old_updated.replace(tzinfo=timezone.utc)
            age_sec = (now - old_updated).total_seconds() if old_updated else 999999

            # Same/lower-priority provider? Only allow overwrite if the existing
            # row has aged past STALE window OR incoming is same/higher priority.
            if new_prio > old_prio and age_sec <= STALE_MAX_SEC:
                await self._audit_write(
                    symbol=sym, provider=new_provider,
                    old_price=existing.get("price"), new_price=new_price,
                    accepted=False,
                    reason=(f"REJECTED: lower-priority provider "
                             f"'{new_provider}' (prio={new_prio}) cannot overwrite "
                             f"fresh '{old_provider}' (prio={old_prio}, age={age_sec:.1f}s)"),
                )
                self._writes_rejected += 1
                logger.info(
                    "market_cache REJECT sym=%s in=%s(prio=%d,px=%s) "
                    "vs existing=%s(prio=%d,px=%s,age=%.1fs)",
                    sym, new_provider, new_prio, new_price,
                    old_provider, old_prio, existing.get("price"), age_sec,
                )
                return False

            # ------- guard 2: timestamp regression ------
            old_provider_ts = existing.get("provider_ts") or old_updated
            if isinstance(old_provider_ts, datetime) and old_provider_ts.tzinfo is None:
                old_provider_ts = old_provider_ts.replace(tzinfo=timezone.utc)
            if isinstance(new_prov_ts, datetime) and new_prov_ts.tzinfo is None:
                new_prov_ts = new_prov_ts.replace(tzinfo=timezone.utc)
            if isinstance(new_prov_ts, datetime) and isinstance(old_provider_ts, datetime) \
                    and new_prov_ts < old_provider_ts - timedelta(seconds=2):
                await self._audit_write(
                    symbol=sym, provider=new_provider,
                    old_price=existing.get("price"), new_price=new_price,
                    accepted=False,
                    reason=(f"REJECTED: incoming provider_ts {new_prov_ts.isoformat()} "
                             f"< existing provider_ts {old_provider_ts.isoformat()}"),
                )
                self._writes_rejected += 1
                return False

        # ------- ACCEPT: perform the write ------
        source = "MOCK" if new_provider == "mock" else "LIVE"
        doc = {
            "symbol": sym,
            "price":  new_price,
            "bid":    float(q.bid) if getattr(q, "bid", None) is not None else None,
            "ask":    float(q.ask) if getattr(q, "ask", None) is not None else None,
            "change_pct": float(q.change_pct) if getattr(q, "change_pct", None) is not None else None,
            "provider":    new_provider,
            "priority":    new_prio,
            "source":      source,
            "provider_ts": new_prov_ts if isinstance(new_prov_ts, datetime) else now,
            "updated_at":  now,
            "last_write_reason": (
                f"accepted from {new_provider}"
                + (f" (overwrote {existing.get('provider')}"
                   f" px={existing.get('price')}"
                   f" age={(now - existing.get('updated_at').replace(tzinfo=timezone.utc) if isinstance(existing.get('updated_at'), datetime) and existing.get('updated_at').tzinfo is None else now - existing.get('updated_at')).total_seconds():.1f}s)"
                    if existing else "")
            ),
        }
        await self.db[_COLL].update_one({"symbol": sym}, {"$set": doc}, upsert=True)

        old_price = (existing or {}).get("price")
        await self._audit_write(
            symbol=sym, provider=new_provider,
            old_price=old_price, new_price=new_price,
            accepted=True,
            reason=f"ACCEPTED from {new_provider} (source={source})",
        )
        self._writes_accepted += 1
        self._writes_by_provider[new_provider] = self._writes_by_provider.get(new_provider, 0) + 1

        # Down-sample logs for non-mock writes (log every mock write since that's
        # the failure mode we're chasing).
        if new_provider == "mock":
            logger.info("market_cache ACCEPT sym=%s provider=%s px=%s old_px=%s",
                        sym, new_provider, new_price, old_price)
        else:
            logger.debug("market_cache ACCEPT sym=%s provider=%s px=%s old_px=%s",
                          sym, new_provider, new_price, old_price)
        return True

    async def _audit_write(self, *, symbol: str, provider: str,
                            old_price: Optional[float], new_price: float,
                            accepted: bool, reason: str) -> None:
        if not self._audit_enabled:
            return
        doc = {
            "at":         _now(),
            "symbol":     symbol,
            "provider":   provider,
            "old_price":  float(old_price) if old_price is not None else None,
            "new_price":  float(new_price),
            "accepted":   bool(accepted),
            "reason":     reason,
        }
        try:
            await self.db[_AUDIT_COLL].insert_one(doc)
        except Exception as e:                    # pragma: no cover
            logger.warning("cache audit insert failed: %s", e)

    # =========================================================================
    #  READ PATH
    # =========================================================================
    async def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        doc = await self.db[_COLL].find_one({"symbol": symbol.upper()}, {"_id": 0})
        if not doc:
            return None
        updated_at = doc.get("updated_at")
        if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_sec = round((_now() - updated_at).total_seconds(), 1) if updated_at else 999999
        doc["age_sec"] = age_sec
        doc["stale"]   = age_sec > self.ttl_seconds
        # Re-derive source label per current age (a LIVE row aging past
        # FRESH_MAX_SEC becomes STALE at read-time even without a rewrite).
        stored_source = doc.get("source") or _classify(doc.get("provider", ""), age_sec)
        if stored_source == "LIVE" and age_sec > FRESH_MAX_SEC:
            doc["source"] = "STALE" if age_sec <= STALE_MAX_SEC else "CACHE"
        else:
            doc["source"] = stored_source
        return doc

    async def get_price(self, symbol: str, max_age_sec: Optional[int] = None) -> Optional[float]:
        """Convenience — returns just the numeric price if fresh enough."""
        doc = await self.get(symbol)
        if not doc:
            return None
        if max_age_sec is not None and doc["age_sec"] > max_age_sec:
            return None
        return float(doc["price"])

    async def get_prices(self, symbols: Iterable[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for s in symbols:
            p = await self.get_price(s)
            if p is not None:
                out[s.upper()] = p
        return out

    async def all_quotes(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        async for d in self.db[_COLL].find({}, {"_id": 0}):
            updated_at = d.get("updated_at")
            if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            age_sec = round((_now() - updated_at).total_seconds(), 1) if updated_at else 999999
            d["age_sec"] = age_sec
            d["stale"]   = age_sec > self.ttl_seconds
            out.append(d)
        return out

    async def stats(self) -> Dict[str, Any]:
        total = await self.db[_COLL].estimated_document_count()
        recent_writes = await self.db[_AUDIT_COLL].count_documents({
            "at": {"$gte": _now() - timedelta(hours=1)}
        })
        recent_rejected = await self.db[_AUDIT_COLL].count_documents({
            "at": {"$gte": _now() - timedelta(hours=1)}, "accepted": False,
        })
        # Age bucket counts (LIVE / STALE / EXPIRED) — required by Sprint 7.5 tests
        now = _now()
        fresh = stale = expired = 0
        newest_age = None
        oldest_age = None
        async for d in self.db[_COLL].find({}, {"updated_at": 1}):
            ua = d.get("updated_at")
            if isinstance(ua, datetime) and ua.tzinfo is None:
                ua = ua.replace(tzinfo=timezone.utc)
            age = (now - ua).total_seconds() if ua else 999999
            if newest_age is None or age < newest_age:
                newest_age = age
            if oldest_age is None or age > oldest_age:
                oldest_age = age
            if age <= FRESH_MAX_SEC:
                fresh += 1
            elif age <= STALE_MAX_SEC:
                stale += 1
            else:
                expired += 1
        return {
            "coll": _COLL,
            "total_symbols":         total,
            "total_symbols_cached": total,   # legacy alias (kept for Sprint 7.5 tests)
            "fresh":   fresh,
            "stale":    stale,
            "expired": expired,
            "newest_age_sec": round(newest_age, 1) if newest_age is not None else None,
            "oldest_age_sec": round(oldest_age, 1) if oldest_age is not None else None,
            "ttl_sec":       self.ttl_seconds,
            "fresh_max_sec": FRESH_MAX_SEC,
            "stale_max_sec": STALE_MAX_SEC,
            "writes_accepted_process": self._writes_accepted,
            "writes_rejected_process": self._writes_rejected,
            "writes_by_provider_process": dict(self._writes_by_provider),
            "audit_last_hour":          recent_writes,
            "audit_rejected_last_hour": recent_rejected,
        }

    async def clear(self):
        await self.db[_COLL].delete_many({})

    async def invalidate_by_source(self, source: str) -> int:
        """Delete cached quotes that were last written by the given provider.
        Called after an api-key rotation so the follower cache doesn't keep
        serving prices from the previous key.
        """
        if not source:
            return 0
        result = await self.db[_COLL].delete_many({"provider": source.lower()})
        return int(result.deleted_count or 0)

    async def recent_writes(self, symbol: Optional[str] = None,
                              limit: int = 50) -> List[Dict[str, Any]]:
        """Trace endpoint helper — returns the most recent cache-write attempts."""
        q: Dict[str, Any] = {}
        if symbol:
            q["symbol"] = symbol.upper()
        cur = self.db[_AUDIT_COLL].find(q, {"_id": 0}).sort("at", -1).limit(limit)
        out = []
        async for d in cur:
            if isinstance(d.get("at"), datetime):
                d["at"] = d["at"].isoformat()
            out.append(d)
        return out

    async def ensure_indexes(self) -> None:
        await self.db[_COLL].create_index("symbol", unique=True, background=True)
        await self.db[_COLL].create_index([("updated_at", -1)], background=True)
        await self.db[_AUDIT_COLL].create_index([("at", -1)], background=True)
        # TTL on the audit log so it doesn't grow unbounded
        try:
            await self.db[_AUDIT_COLL].create_index(
                "at", expireAfterSeconds=self._audit_retention_hours * 3600,
                background=True, name="audit_ttl",
            )
        except Exception:
            pass    # index may already exist with a different TTL
