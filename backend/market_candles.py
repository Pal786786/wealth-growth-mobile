"""Sprint 16.0 — Market candle engine (OHLCV) for the professional trading chart.

Single source of truth rules:
  * Live ticks come ONLY from the unified ProviderManager refresh cycle
    (`ingest_ticks` is called from ProviderManager.refresh_once — no second
    scheduler, no second price engine).
  * Historical OHLC comes ONLY from Finnhub REST (/forex/candle,
    /crypto/candle, /stock/candle) and is cached in `market_price_history`.
    Cached ranges are NEVER re-downloaded; only missing candles are appended
    incrementally. Completed candles are never regenerated locally.
  * The currently-forming candle is built from live ticks (tick-count volume,
    MT4/MT5 style) and is replaced by the official Finnhub bar on the next
    historical sync.

Collections:
  market_price_history: {symbol, tf, t, o, h, l, c, v, source, updated_at}
                        unique index (symbol, tf, t)
  market_history_meta:  {_id: "SYMBOL:tf", oldest_t, newest_t, last_sync_at}

Endpoint:
  GET /api/market/candles/{symbol}?tf=1m|5m|15m|30m|1h|4h|1d&limit=300&before=<epoch>
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

logger = logging.getLogger("market_candles")

# ---------------------------------------------------------------- constants
TIMEFRAMES: Dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}
# Finnhub-native resolutions. 4h is aggregated from cached 1h bars (Finnhub
# has no 240 resolution) — this is bucket aggregation of REAL Finnhub OHLC,
# never local price generation.
FINNHUB_RES: Dict[str, str] = {
    "1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D",
}
BASE_TF: Dict[str, str] = {tf: ("1h" if tf == "4h" else tf) for tf in TIMEFRAMES}

DAY = 86400
# Preload windows (per stored/base timeframe) — user-approved Sprint 16.0.
PRELOAD_SEC: Dict[str, int] = {
    "1m": 2 * DAY,
    "5m": 7 * DAY,
    "15m": 30 * DAY,
    "30m": 30 * DAY,
    "1h": 365 * DAY,      # covers both 1H (180d) and 4H (1y) requirements
    "1d": 5 * 365 * DAY,
}
SYNC_MIN_INTERVAL_SEC = 60          # never hit Finnhub for the same series more often
BACKFILL_CHUNK_BARS = 600           # bars fetched per infinite-scroll backfill
MAX_LIMIT = 1000

HIST_COLL = "market_price_history"
META_COLL = "market_history_meta"

_db = None  # set by attach()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _bucket(ts: float, sec: int) -> int:
    return int(ts // sec) * sec


async def ensure_indexes(db) -> None:
    try:
        await db[HIST_COLL].create_index(
            [("symbol", 1), ("tf", 1), ("t", 1)], unique=True, name="sym_tf_t")
    except Exception as e:  # pragma: no cover
        logger.warning("candle index init failed: %s", e)


# ================================================================== ingest
async def ingest_ticks(quotes: Dict[str, Any]) -> int:
    """Called by ProviderManager.refresh_once after every unified cache write.

    Updates the forming 1m candle for each symbol. Tick-count volume is only
    used while the bar is live-built; official Finnhub bars keep their volume.
    """
    if _db is None or not quotes:
        return 0
    now = time.time()
    t = _bucket(now, 60)
    now_dt = _now_dt()
    ops: List[UpdateOne] = []
    for sym, q in quotes.items():
        price = float(getattr(q, "price", 0) or 0)
        if price <= 0:
            continue
        ops.append(UpdateOne(
            {"symbol": sym.upper(), "tf": "1m", "t": t},
            [{"$set": {
                "o": {"$ifNull": ["$o", price]},
                "h": {"$max": [{"$ifNull": ["$h", price]}, price]},
                "l": {"$min": [{"$ifNull": ["$l", price]}, price]},
                "c": price,
                "v": {"$cond": [
                    {"$eq": [{"$ifNull": ["$source", "live"]}, "live"]},
                    {"$add": [{"$ifNull": ["$v", 0]}, 1]},
                    {"$ifNull": ["$v", 0]},
                ]},
                "source": {"$ifNull": ["$source", "live"]},
                "updated_at": now_dt,
            }}],
            upsert=True,
        ))
    if not ops:
        return 0
    res = await _db[HIST_COLL].bulk_write(ops, ordered=False)
    return (res.upserted_count or 0) + (res.modified_count or 0)


# ============================================================ aggregation
def aggregate_candles(rows: List[Dict[str, Any]], tf_sec: int) -> List[Dict[str, Any]]:
    """Pure bucket aggregation (asc-sorted input rows → asc-sorted buckets).

    o = first bar's open, h = max, l = min, c = last bar's close, v = sum.
    Used for 4h (from cached Finnhub 1h bars) and for the live 1m tail.
    """
    out: Dict[int, Dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: x["t"]):
        b = _bucket(r["t"], tf_sec)
        cur = out.get(b)
        if cur is None:
            out[b] = {"t": b, "o": r["o"], "h": r["h"], "l": r["l"],
                      "c": r["c"], "v": float(r.get("v") or 0),
                      "source": r.get("source", "live")}
        else:
            cur["h"] = max(cur["h"], r["h"])
            cur["l"] = min(cur["l"], r["l"])
            cur["c"] = r["c"]
            cur["v"] += float(r.get("v") or 0)
            if r.get("source") == "finnhub":
                cur["source"] = "finnhub"
    return [out[k] for k in sorted(out)]


async def _read_base_rows(symbol: str, base_tf: str, limit: int,
                          before: Optional[int]) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"symbol": symbol, "tf": base_tf}
    if before is not None:
        q["t"] = {"$lt": before}
    cur = _db[HIST_COLL].find(q, {"_id": 0}).sort("t", -1).limit(limit)
    rows = [d async for d in cur]
    rows.reverse()
    return rows


async def get_candles(symbol: str, tf: str, limit: int = 300,
                      before: Optional[int] = None) -> List[Dict[str, Any]]:
    """Read candles for a timeframe: cached Finnhub bars + live 1m tail."""
    tf_sec = TIMEFRAMES[tf]
    base_tf = BASE_TF[tf]
    base_sec = TIMEFRAMES[base_tf]
    factor = tf_sec // base_sec

    base_rows = await _read_base_rows(symbol, base_tf, limit * factor, before)
    candles = aggregate_candles(base_rows, tf_sec) if factor > 1 else [
        {"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
         "v": float(r.get("v") or 0), "source": r.get("source", "live")}
        for r in base_rows
    ]

    # Live tail — aggregate recent 1m rows newer than the last stored base bar
    # (only for the "latest" page; historical pages are immutable).
    if before is None and tf != "1m":
        last_t = candles[-1]["t"] + tf_sec if candles else _bucket(time.time(), tf_sec) - 50 * tf_sec
        q = {"symbol": symbol, "tf": "1m", "t": {"$gte": last_t}}
        cur = _db[HIST_COLL].find(q, {"_id": 0}).sort("t", 1).limit(3000)
        tail_1m = [d async for d in cur]
        for c in aggregate_candles(tail_1m, tf_sec):
            if not candles or c["t"] > candles[-1]["t"]:
                candles.append(c)
            elif c["t"] == candles[-1]["t"] and candles[-1].get("source") != "finnhub":
                candles[-1] = c

    now_bucket = _bucket(time.time(), tf_sec)
    for c in candles:
        c["complete"] = c["t"] < now_bucket
    return candles[-limit:]


# ======================================================= finnhub history
def _finnhub_provider():
    try:
        import market_providers
        mgr = market_providers.get_manager()
        if mgr is None:
            return None
        return mgr._by_name.get("finnhub")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        return None


def _candle_path(fin_sym: str) -> str:
    if fin_sym.startswith("OANDA:"):
        return "/forex/candle"
    if fin_sym.startswith("BINANCE:"):
        return "/crypto/candle"
    return "/stock/candle"


async def _fetch_finnhub_bars(symbol: str, res: str, t_from: int,
                              t_to: int) -> Optional[List[Dict[str, Any]]]:
    """One Finnhub REST candle request. Returns list of bars or None on error."""
    from market_providers.finnhub import BASE_URL, SYMBOL_MAP
    prov = _finnhub_provider()
    if prov is None or not getattr(prov, "_api_key", ""):
        return None
    if prov.is_backed_off():
        return None
    fin_sym = SYMBOL_MAP.get(symbol)
    if not fin_sym:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                f"{BASE_URL}{_candle_path(fin_sym)}",
                params={"symbol": fin_sym, "resolution": res,
                        "from": t_from, "to": t_to, "token": prov._api_key},
            )
        prov._parse_credit_headers(r)
        if r.status_code == 429:
            prov._trigger_backoff("candle HTTP 429")
            return None
        if r.status_code != 200:
            logger.warning("finnhub candle %s res=%s http=%d %s",
                           symbol, res, r.status_code, r.text[:120])
            return None
        data = r.json()
        if data.get("s") != "ok":
            return []
        bars = []
        for i, ts in enumerate(data.get("t") or []):
            bars.append({
                "t": int(ts), "o": float(data["o"][i]), "h": float(data["h"][i]),
                "l": float(data["l"][i]), "c": float(data["c"][i]),
                "v": float((data.get("v") or [0] * len(data["t"]))[i] or 0),
            })
        return bars
    except Exception as e:  # pragma: no cover
        logger.warning("finnhub candle fetch failed %s: %s", symbol, e)
        return None


async def _store_bars(symbol: str, base_tf: str, bars: List[Dict[str, Any]]) -> int:
    if not bars:
        return 0
    # Sprint 16.3 — de-duplicate by bucket timestamp. Finnhub can return
    # repeated stamps in one payload; two upserts targeting the same
    # (symbol, tf, t) inside a single unordered bulk race to INSERT and the
    # loser raises E11000 under the unique sym_tf_t index. One op per t.
    dedup: Dict[int, Dict[str, Any]] = {}
    for b in bars:
        dedup[b["t"]] = b
    now_dt = _now_dt()
    ops = [UpdateOne(
        {"symbol": symbol, "tf": base_tf, "t": t},
        {"$set": {**b, "symbol": symbol, "tf": base_tf,
                  "source": "finnhub", "updated_at": now_dt}},
        upsert=True,
    ) for t, b in sorted(dedup.items())]
    try:
        res = await _db[HIST_COLL].bulk_write(ops, ordered=False)
        return (res.upserted_count or 0) + (res.modified_count or 0)
    except BulkWriteError as e:
        # Salvage partial success (unordered bulk applies every op it can).
        # Log the exact per-op errors verbatim so production issues are named.
        d = e.details or {}
        applied = int(d.get("nUpserted") or 0) + int(d.get("nModified") or 0)
        logger.error(
            "candle store %s %s: BulkWriteError — %d/%d ops applied; writeErrors: %s",
            symbol, base_tf, applied, len(ops),
            [str(w.get("errmsg", ""))[:160] for w in (d.get("writeErrors") or [])[:3]],
        )
        return applied


async def _update_meta(symbol: str, base_tf: str, t_from: int, t_to: int) -> None:
    mid = f"{symbol}:{base_tf}"
    meta = await _db[META_COLL].find_one({"_id": mid}) or {}
    await _db[META_COLL].update_one(
        {"_id": mid},
        {"$set": {
            "oldest_t": min(int(meta.get("oldest_t") or t_from), t_from),
            "newest_t": max(int(meta.get("newest_t") or t_to), t_to),
            "last_sync_at": _now_dt(),
        }},
        upsert=True,
    )


async def ensure_history(symbol: str, tf: str) -> Dict[str, Any]:
    """Lazy incremental sync. Fetches ONLY missing ranges:
      * no meta        → full preload window (one time)
      * meta exists    → [newest_t, now] append (throttled to 60s)
    Never re-downloads cached ranges. No-op without a configured key."""
    base_tf = BASE_TF[tf]
    res = FINNHUB_RES[base_tf]
    base_sec = TIMEFRAMES[base_tf]
    now = int(time.time())
    mid = f"{symbol}:{base_tf}"
    meta = await _db[META_COLL].find_one({"_id": mid})

    if meta:
        last_sync = meta.get("last_sync_at")
        # Sprint 16.3 — Mongo returns naive UTC datetimes (motor default
        # tz_aware=False); subtracting one from tz-aware _now_dt() raised
        # TypeError and 500'd every request once a meta doc existed.
        if isinstance(last_sync, datetime) and last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        if last_sync and (_now_dt() - last_sync).total_seconds() < SYNC_MIN_INTERVAL_SEC:
            return {"synced": False, "reason": "throttled"}
        t_from = int(meta["newest_t"])
        if now - t_from < base_sec:
            # Just refresh throttle stamp — the forming candle comes from live ticks.
            await _db[META_COLL].update_one({"_id": mid}, {"$set": {"last_sync_at": _now_dt()}})
            return {"synced": False, "reason": "up_to_date"}
    else:
        t_from = now - PRELOAD_SEC[base_tf]

    bars = await _fetch_finnhub_bars(symbol, res, t_from, now)
    if bars is None:
        return {"synced": False, "reason": "provider_unavailable"}
    stored = await _store_bars(symbol, base_tf, bars)
    await _update_meta(symbol, base_tf, t_from, bars[-1]["t"] if bars else t_from)
    logger.info("candle sync %s %s: fetched=%d stored=%d from=%d", symbol, base_tf, len(bars), stored, t_from)
    return {"synced": True, "fetched": len(bars), "stored": stored}


async def backfill_older(symbol: str, tf: str, before: int) -> Dict[str, Any]:
    """Infinite-scroll backfill: fetch one older chunk when the user pans past
    the oldest cached bar. Range is fetched at most once."""
    base_tf = BASE_TF[tf]
    base_sec = TIMEFRAMES[base_tf]
    mid = f"{symbol}:{base_tf}"
    meta = await _db[META_COLL].find_one({"_id": mid})
    oldest = int(meta["oldest_t"]) if meta else int(time.time())
    if before > oldest:
        return {"synced": False, "reason": "range_cached"}
    t_to = oldest
    t_from = t_to - BACKFILL_CHUNK_BARS * base_sec
    bars = await _fetch_finnhub_bars(symbol, FINNHUB_RES[base_tf], t_from, t_to)
    if bars is None:
        return {"synced": False, "reason": "provider_unavailable"}
    stored = await _store_bars(symbol, base_tf, bars)
    await _update_meta(symbol, base_tf, t_from, t_to)
    return {"synced": True, "fetched": len(bars), "stored": stored}


# ================================================================ routes
def attach(app, db) -> None:
    """Mount candle routes directly on the FastAPI app (called after the main
    /api router has already been included)."""
    global _db
    _db = db
    r = APIRouter(prefix="/api/market", tags=["market-candles"])

    @r.get("/candles/{symbol}")
    async def candles(symbol: str,
                      tf: str = Query("1m"),
                      limit: int = Query(300, ge=1, le=MAX_LIMIT),
                      before: Optional[int] = Query(None)):
        from market_providers.finnhub import SYMBOL_MAP
        sym = symbol.upper()
        if tf not in TIMEFRAMES:
            raise HTTPException(400, f"tf must be one of {sorted(TIMEFRAMES)}")
        if sym not in SYMBOL_MAP:
            raise HTTPException(404, f"unknown symbol {sym}")

        # Sprint 16.3 — a sync failure must NEVER take down the read path;
        # cached candles are always served. The full traceback is logged and
        # the exception class/message surfaces in sync.reason for diagnosis.
        if before is None:
            try:
                sync = await ensure_history(sym, tf)
            except Exception as e:
                logger.exception("candle sync failed %s %s", sym, tf)
                sync = {"synced": False,
                        "reason": f"sync_error:{type(e).__name__}: {str(e)[:180]}"}
        else:
            try:
                sync = await backfill_older(sym, tf, before)
            except Exception as e:
                logger.exception("candle backfill failed %s %s", sym, tf)
                sync = {"synced": False,
                        "reason": f"sync_error:{type(e).__name__}: {str(e)[:180]}"}

        items = await get_candles(sym, tf, limit=limit, before=before)

        quote = None
        try:
            import market_providers
            mgr = market_providers.get_manager()
            if mgr is not None:
                quote = await mgr.cache.get(sym)
        except Exception:  # pragma: no cover
            pass

        volume_available = any(c.get("v", 0) > 0 for c in items)
        return {
            "symbol": sym, "tf": tf, "candles": items,
            "volume_available": volume_available,
            "quote": quote, "sync": sync,
        }

    app.include_router(r)
