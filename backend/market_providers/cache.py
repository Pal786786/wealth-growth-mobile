"""Mongo-backed Quote Cache (Sprint 7.5)

Single source of truth for live prices. Every consumer (Forex, AI Signals,
Watchlist, Copy Trading, Price Alerts) reads from here. NO consumer should
call providers directly. The Provider Manager writes here after each refresh.

Cache TTL: 60 seconds (Sprint 7.5 P0 fix — free-tier friendly).
Freshness thresholds:
  * <30s   → LIVE   (green)
  * 30–300s → STALE  (amber — still serve, retry providers)
  * >300s  → EXPIRED (blue — force Mock fallback)
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

_COLL = "market_price_cache"

# Freshness thresholds (seconds)
FRESH_MAX_SEC = 30       # <30s → LIVE
STALE_MAX_SEC = 300      # 30–300s → STALE; >300s → EXPIRED (fallback)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QuoteCache:
    def __init__(self, db, ttl_seconds: int = 60):
        self.db = db
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def put_many(self, quotes: Dict[str, Any]):
        if not quotes:
            return
        now = _now()
        ops = []
        for symbol, q in quotes.items():
            doc = {
                "symbol": symbol.upper(),
                "price": float(q.price),
                "bid":   float(q.bid) if q.bid is not None else None,
                "ask":   float(q.ask) if q.ask is not None else None,
                "change_pct": float(q.change_pct) if q.change_pct is not None else None,
                "provider": q.provider,
                "updated_at": now,
            }
            ops.append(doc)
        # Bulk upsert
        for doc in ops:
            await self.db[_COLL].update_one(
                {"symbol": doc["symbol"]}, {"$set": doc}, upsert=True)

    async def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        doc = await self.db[_COLL].find_one({"symbol": symbol.upper()}, {"_id": 0})
        if not doc:
            return None
        doc["age_sec"] = round((_now() - doc["updated_at"].replace(tzinfo=timezone.utc)
                                if doc["updated_at"].tzinfo is None
                                else _now() - doc["updated_at"]).total_seconds(), 1)
        doc["stale"] = doc["age_sec"] > self.ttl_seconds
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
        """Batch lookup — returns {symbol: price} for whatever is cached."""
        syms = [s.upper() for s in symbols]
        cur = self.db[_COLL].find({"symbol": {"$in": syms}}, {"_id": 0})
        out: Dict[str, float] = {}
        async for d in cur:
            out[d["symbol"]] = float(d["price"])
        return out

    async def all_quotes(self) -> List[Dict[str, Any]]:
        cur = self.db[_COLL].find({}, {"_id": 0}).sort("symbol", 1)
        rows: List[Dict[str, Any]] = []
        now = _now()
        async for d in cur:
            ua = d["updated_at"]
            if ua.tzinfo is None:
                ua = ua.replace(tzinfo=timezone.utc)
            d["age_sec"] = round((now - ua).total_seconds(), 1)
            d["stale"] = d["age_sec"] > self.ttl_seconds
            d["updated_at"] = ua.isoformat()
            rows.append(d)
        return rows

    async def stats(self) -> Dict[str, Any]:
        total = await self.db[_COLL].estimated_document_count()
        # Freshness distribution
        now = _now()
        fresh_cutoff = now - timedelta(seconds=FRESH_MAX_SEC)
        stale_cutoff = now - timedelta(seconds=STALE_MAX_SEC)
        fresh = await self.db[_COLL].count_documents({"updated_at": {"$gte": fresh_cutoff}})
        stale = await self.db[_COLL].count_documents({
            "updated_at": {"$gte": stale_cutoff, "$lt": fresh_cutoff}})
        expired = await self.db[_COLL].count_documents({"updated_at": {"$lt": stale_cutoff}})
        # Oldest / newest ages
        oldest_age_sec = None
        newest_age_sec = None
        try:
            oldest = await self.db[_COLL].find_one({}, {"updated_at": 1, "_id": 0},
                                                    sort=[("updated_at", 1)])
            newest = await self.db[_COLL].find_one({}, {"updated_at": 1, "_id": 0},
                                                    sort=[("updated_at", -1)])
            if oldest and oldest.get("updated_at"):
                ua = oldest["updated_at"]
                if ua.tzinfo is None:
                    ua = ua.replace(tzinfo=timezone.utc)
                oldest_age_sec = round((now - ua).total_seconds(), 1)
            if newest and newest.get("updated_at"):
                ua = newest["updated_at"]
                if ua.tzinfo is None:
                    ua = ua.replace(tzinfo=timezone.utc)
                newest_age_sec = round((now - ua).total_seconds(), 1)
        except Exception:
            pass
        return {
            "total_symbols_cached": total,
            "fresh": fresh,
            "stale": stale,
            "expired": expired,
            "oldest_age_sec": oldest_age_sec,
            "newest_age_sec": newest_age_sec,
            "ttl_sec": self.ttl_seconds,
            "fresh_max_sec": FRESH_MAX_SEC,
            "stale_max_sec": STALE_MAX_SEC,
        }

    async def clear(self):
        await self.db[_COLL].delete_many({})

    async def invalidate_by_source(self, source: str) -> int:
        """Delete cached quotes that were last written by the given provider.
        Called after an api-key rotation so the follower cache doesn't keep
        serving prices from the previous key. Returns the number of deleted docs.
        """
        if not source:
            return 0
        result = await self.db[_COLL].delete_many({"source": source})
        return int(result.deleted_count or 0)
