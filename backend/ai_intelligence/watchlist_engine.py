"""AI Intelligence — Watchlist Engine (Sprint 7C.1)

Simple user watchlist backed by `ai_watchlist` collection. Every entry is
enriched at read time with:
  * trend (bullish/bearish/neutral)
  * AI signal (buy/sell/hold) + confidence
  * volatility_pct (20-bar σ)
  * daily_change_pct (24h)
  * weekly_change_pct (7d)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from market_data.catalog import BY_ID
from . import feed, signal_engine


_COLL = "ai_watchlist"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def add(db, user_id: str, symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper().strip()
    if symbol not in BY_ID:
        raise ValueError(f"unknown symbol {symbol}")
    doc = {
        "item_id": f"wl_{uuid.uuid4().hex[:10]}",
        "user_id": user_id, "symbol": symbol, "created_at": _now(),
    }
    await db[_COLL].update_one(
        {"user_id": user_id, "symbol": symbol},
        {"$setOnInsert": doc}, upsert=True,
    )
    stored = await db[_COLL].find_one(
        {"user_id": user_id, "symbol": symbol}, {"_id": 0})
    return stored or doc


async def remove(db, user_id: str, symbol: str) -> bool:
    res = await db[_COLL].delete_one({"user_id": user_id, "symbol": symbol.upper()})
    return res.deleted_count > 0


async def list_symbols(db, user_id: str) -> List[str]:
    cur = db[_COLL].find({"user_id": user_id}, {"_id": 0, "symbol": 1}).sort("created_at", -1)
    return [d["symbol"] async for d in cur]


def _change_pct(symbol: str, bars_back: int, timeframe: str) -> float:
    candles = feed.get_candles(symbol, timeframe, count=bars_back + 1)
    if len(candles) < 2:
        return 0.0
    start = candles[0]["close"]
    end = candles[-1]["close"]
    if not start:
        return 0.0
    return round((end - start) / start * 100.0, 3)


def enrich(symbol: str) -> Dict[str, Any]:
    """Enrich a symbol with signal + change stats (no DB writes)."""
    symbol = symbol.upper()
    inst = BY_ID.get(symbol)
    if not inst:
        return {"symbol": symbol, "unknown": True}
    sig = signal_engine.generate_signal(symbol, timeframe="H1", include_summary=False)
    if not sig:
        return {"symbol": symbol, "unknown": True}
    daily_change = _change_pct(symbol, 24, "H1")
    weekly_change = _change_pct(symbol, 7, "D1")
    volatility = 0.0
    if sig.get("indicators"):
        volatility = sig["indicators"].get("volatility_pct", 0.0)
    else:
        # Compute on the fly since we skipped summary
        candles = feed.get_candles(symbol, "H1", count=250)
        if candles:
            from . import ta_engine as ta
            ind = ta.compute(candles)
            volatility = ind.get("volatility_pct", 0.0)
    return {
        "symbol": symbol,
        "display": inst.get("display", symbol),
        "name": inst.get("name", symbol),
        "category": inst.get("category"),
        "asset_class": signal_engine.CATEGORY_TO_ASSET_CLASS.get(inst.get("category", ""), inst.get("category", "")),
        "price": sig["entry"],
        "trend": sig["trend"],
        "signal": sig["side"],
        "confidence_pct": sig["confidence_pct"],
        "signal_strength": sig["signal_strength"],
        "volatility_pct": volatility,
        "daily_change_pct": daily_change,
        "weekly_change_pct": weekly_change,
    }


async def enriched_watchlist(db, user_id: str) -> List[Dict[str, Any]]:
    symbols = await list_symbols(db, user_id)
    if not symbols:
        return []
    return [enrich(s) for s in symbols]
