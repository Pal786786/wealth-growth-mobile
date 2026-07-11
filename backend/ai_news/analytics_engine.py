"""AI Signal Analytics Engine — Sprint 7C.2

Tracks the outcome of AI signals over time so users can see whether the
signals actually made money.

Workflow:
  * Every 5 minutes a background task calls the signal engine to snapshot
    the current BUY/SELL signals across the default universe.
  * If a signal for a (symbol, timeframe, bar_index) is not yet tracked, we
    record it into `ai_signal_history` with its entry / SL / TPs.
  * For each unresolved tracked signal we check current price vs. SL/TP levels
    and mark the outcome (`tp1_hit`, `tp2_hit`, `tp3_hit`, `sl_hit`, `expired`).
  * ROI is computed as (exit - entry) / entry * 100 for buys and negated for
    sells.

Aggregations exposed via /api/ai/analytics/*.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_news.analytics")

COLL = "ai_signal_history"
OUTCOMES = ["pending", "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "expired"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_roi(side: str, entry: float, exit_price: float) -> float:
    if not entry:
        return 0.0
    diff = (exit_price - entry) / entry * 100.0
    return round(diff if side == "buy" else -diff, 3)


class AnalyticsEngine:
    def __init__(self, db, interval_sec: int = 300):
        self.db = db
        self.interval_sec = int(interval_sec)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("AnalyticsEngine started (interval=%ds)", self.interval_sec)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None

    def set_interval(self, seconds: int):
        self.interval_sec = max(30, min(3600, int(seconds)))

    # ---------------- background loop ---------------- #
    async def _loop(self):
        await asyncio.sleep(5)  # warm-up
        while not self._stop.is_set():
            try:
                await self.tick_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("analytics loop error: %s", e)
            await asyncio.sleep(self.interval_sec)

    async def tick_once(self) -> Dict[str, int]:
        """Ingest new signals + resolve pending ones. Returns counts."""
        try:
            from ai_intelligence import signal_engine, feed
        except Exception as e:
            logger.warning("analytics: cannot import signal engine: %s", e)
            return {"tracked": 0, "resolved": 0}

        tracked = 0
        resolved = 0
        universe = signal_engine.DEFAULT_UNIVERSE
        for tf in ("H1", "H4"):
            for sym in universe:
                try:
                    sig = signal_engine.generate_signal(sym, timeframe=tf,
                                                        include_summary=False)
                except Exception:
                    sig = None
                if not sig or sig.get("side") not in ("buy", "sell"):
                    continue
                key = f"{sym}|{tf}|{sig.get('bar_index')}"
                exists = await self.db[COLL].find_one({"_id": key})
                if exists:
                    continue
                doc = {
                    "_id": key,
                    "symbol": sym, "timeframe": tf,
                    "bar_index": sig.get("bar_index"),
                    "side": sig["side"],
                    "entry": sig["entry"], "stop_loss": sig.get("stop_loss"),
                    "tp1": sig.get("tp1"), "tp2": sig.get("tp2"), "tp3": sig.get("tp3"),
                    "confidence_pct": sig.get("confidence_pct"),
                    "signal_strength": sig.get("signal_strength"),
                    "asset_class": sig.get("asset_class"),
                    "generated_at": _now(),
                    "expires_at": sig.get("expires_at"),
                    "outcome": "pending",
                    "resolved_at": None,
                    "exit_price": None,
                    "roi_pct": None,
                    "high_since": sig["entry"], "low_since": sig["entry"],
                }
                await self.db[COLL].insert_one(doc)
                tracked += 1

        # Resolve pending signals
        cur = self.db[COLL].find({"outcome": "pending"})
        async for row in cur:
            try:
                from ai_intelligence import feed  # noqa: F401
                price = feed.current_price(row["symbol"])
            except Exception:
                price = None
            if price is None:
                continue
            high = max(row.get("high_since") or price, price)
            low = min(row.get("low_since") or price, price)

            side = row["side"]
            outcome = None
            exit_price = None
            # BUY: SL below entry, TP above
            if side == "buy":
                if row.get("stop_loss") and low <= row["stop_loss"]:
                    outcome = "sl_hit"; exit_price = row["stop_loss"]
                elif row.get("tp3") and high >= row["tp3"]:
                    outcome = "tp3_hit"; exit_price = row["tp3"]
                elif row.get("tp2") and high >= row["tp2"]:
                    outcome = "tp2_hit"; exit_price = row["tp2"]
                elif row.get("tp1") and high >= row["tp1"]:
                    outcome = "tp1_hit"; exit_price = row["tp1"]
            else:  # sell
                if row.get("stop_loss") and high >= row["stop_loss"]:
                    outcome = "sl_hit"; exit_price = row["stop_loss"]
                elif row.get("tp3") and low <= row["tp3"]:
                    outcome = "tp3_hit"; exit_price = row["tp3"]
                elif row.get("tp2") and low <= row["tp2"]:
                    outcome = "tp2_hit"; exit_price = row["tp2"]
                elif row.get("tp1") and low <= row["tp1"]:
                    outcome = "tp1_hit"; exit_price = row["tp1"]

            expiry_ok = True
            exp = row.get("expires_at")
            if isinstance(exp, str):
                try:
                    exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                    if _now() > exp_dt + timedelta(hours=6):
                        expiry_ok = False
                except Exception:
                    pass

            update: Dict[str, Any] = {"high_since": high, "low_since": low}
            if outcome:
                update["outcome"] = outcome
                update["exit_price"] = exit_price
                update["resolved_at"] = _now()
                update["roi_pct"] = _compute_roi(side, row["entry"], exit_price)
                resolved += 1
            elif not expiry_ok:
                update["outcome"] = "expired"
                update["exit_price"] = price
                update["resolved_at"] = _now()
                update["roi_pct"] = _compute_roi(side, row["entry"], price)
                resolved += 1
            await self.db[COLL].update_one({"_id": row["_id"]}, {"$set": update})

        return {"tracked": tracked, "resolved": resolved}


# ---------------- aggregations ---------------- #

async def overview(db, window_days: Optional[int] = None) -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    if window_days:
        q["generated_at"] = {"$gte": _now() - timedelta(days=int(window_days))}
    total = await db[COLL].count_documents(q)
    resolved = await db[COLL].count_documents({**q, "outcome": {"$ne": "pending"}})
    tp_hits = await db[COLL].count_documents({**q, "outcome": {"$in": ["tp1_hit", "tp2_hit", "tp3_hit"]}})
    sl_hits = await db[COLL].count_documents({**q, "outcome": "sl_hit"})
    expired = await db[COLL].count_documents({**q, "outcome": "expired"})
    # Sum ROI
    pipeline = [{"$match": {**q, "outcome": {"$ne": "pending"}, "roi_pct": {"$ne": None}}},
                {"$group": {"_id": None,
                            "sum_roi": {"$sum": "$roi_pct"},
                            "avg_roi": {"$avg": "$roi_pct"},
                            "avg_conf": {"$avg": "$confidence_pct"}}}]
    agg = await db[COLL].aggregate(pipeline).to_list(1)
    sum_roi = round((agg[0]["sum_roi"] if agg else 0) or 0, 2)
    avg_roi = round((agg[0]["avg_roi"] if agg else 0) or 0, 3)
    avg_conf = round((agg[0]["avg_conf"] if agg else 0) or 0, 1)

    def _pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    win_rate_pct = _pct(tp_hits, resolved) if resolved else 0.0
    tp1_pct = _pct(
        await db[COLL].count_documents({**q, "outcome": {"$in": ["tp1_hit", "tp2_hit", "tp3_hit"]}}),
        resolved,
    ) if resolved else 0.0
    tp2_pct = _pct(
        await db[COLL].count_documents({**q, "outcome": {"$in": ["tp2_hit", "tp3_hit"]}}),
        resolved,
    ) if resolved else 0.0
    tp3_pct = _pct(await db[COLL].count_documents({**q, "outcome": "tp3_hit"}),
                   resolved) if resolved else 0.0

    # Confidence-vs-outcome accuracy: for TP hits, avg confidence should be
    # higher than for SL hits
    conf_agg = await db[COLL].aggregate([
        {"$match": {**q, "outcome": {"$ne": "pending"}}},
        {"$group": {"_id": {"$cond": [{"$in": ["$outcome", ["tp1_hit", "tp2_hit", "tp3_hit"]]}, "win", "loss"]},
                    "avg_conf": {"$avg": "$confidence_pct"},
                    "count": {"$sum": 1}}}
    ]).to_list(4)
    conf_by_outcome = {r["_id"]: r for r in conf_agg}
    win_avg_conf = round((conf_by_outcome.get("win", {}).get("avg_conf") or 0), 1)
    loss_avg_conf = round((conf_by_outcome.get("loss", {}).get("avg_conf") or 0), 1)
    confidence_edge_pct = round(win_avg_conf - loss_avg_conf, 1)

    return {
        "window_days": window_days,
        "total_signals": total,
        "resolved_signals": resolved,
        "pending_signals": total - resolved,
        "tp_hits": tp_hits, "sl_hits": sl_hits, "expired": expired,
        "win_rate_pct": win_rate_pct,
        "tp1_hit_rate_pct": tp1_pct,
        "tp2_hit_rate_pct": tp2_pct,
        "tp3_hit_rate_pct": tp3_pct,
        "sum_roi_pct": sum_roi,
        "avg_roi_pct": avg_roi,
        "avg_confidence_pct": avg_conf,
        "win_avg_confidence_pct": win_avg_conf,
        "loss_avg_confidence_pct": loss_avg_conf,
        "confidence_edge_pct": confidence_edge_pct,
    }


async def by_symbol(db, window_days: Optional[int] = None,
                    limit: int = 30) -> List[Dict[str, Any]]:
    match: Dict[str, Any] = {"outcome": {"$ne": "pending"}}
    if window_days:
        match["generated_at"] = {"$gte": _now() - timedelta(days=int(window_days))}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$symbol",
            "resolved": {"$sum": 1},
            "wins": {"$sum": {"$cond": [{"$in": ["$outcome", ["tp1_hit", "tp2_hit", "tp3_hit"]]}, 1, 0]}},
            "losses": {"$sum": {"$cond": [{"$eq": ["$outcome", "sl_hit"]}, 1, 0]}},
            "sum_roi": {"$sum": "$roi_pct"},
            "avg_conf": {"$avg": "$confidence_pct"},
        }},
        {"$sort": {"resolved": -1}}, {"$limit": int(limit)},
    ]
    rows = await db[COLL].aggregate(pipeline).to_list(int(limit))
    for r in rows:
        r["symbol"] = r.pop("_id")
        wins = r.get("wins") or 0
        resolved = r.get("resolved") or 0
        r["win_rate_pct"] = round(100.0 * wins / resolved, 1) if resolved else 0.0
        r["sum_roi"] = round(r.get("sum_roi") or 0, 2)
        r["avg_conf"] = round(r.get("avg_conf") or 0, 1)
    return rows


async def by_timeframe(db, window_days: Optional[int] = None) -> List[Dict[str, Any]]:
    match: Dict[str, Any] = {"outcome": {"$ne": "pending"}}
    if window_days:
        match["generated_at"] = {"$gte": _now() - timedelta(days=int(window_days))}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$timeframe",
            "resolved": {"$sum": 1},
            "wins": {"$sum": {"$cond": [{"$in": ["$outcome", ["tp1_hit", "tp2_hit", "tp3_hit"]]}, 1, 0]}},
            "sum_roi": {"$sum": "$roi_pct"},
            "avg_conf": {"$avg": "$confidence_pct"},
        }},
        {"$sort": {"resolved": -1}},
    ]
    rows = await db[COLL].aggregate(pipeline).to_list(20)
    for r in rows:
        r["timeframe"] = r.pop("_id")
        wins = r.get("wins") or 0
        resolved = r.get("resolved") or 0
        r["win_rate_pct"] = round(100.0 * wins / resolved, 1) if resolved else 0.0
        r["sum_roi"] = round(r.get("sum_roi") or 0, 2)
        r["avg_conf"] = round(r.get("avg_conf") or 0, 1)
    return rows


async def signal_history(db, limit: int = 40,
                         outcome: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if outcome:
        q["outcome"] = outcome
    cur = db[COLL].find(q, {"_id": 0}).sort("generated_at", -1).limit(int(limit))
    rows = [d async for d in cur]
    for d in rows:
        for k in ("generated_at", "resolved_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
    return rows
