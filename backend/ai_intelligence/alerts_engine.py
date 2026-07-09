"""AI Intelligence — Price Alerts Engine (Sprint 7C.1)

5 alert types:
  1. price_above    — trigger when live price crosses ABOVE `target_price`
  2. price_below    — trigger when live price crosses BELOW `target_price`
  3. percent_move   — trigger when price moves ±`target_percent` % from an anchor
  4. indicator_cross — trigger on EMA cross (fast/slow crossover)
  5. rsi_alert      — trigger when RSI crosses `threshold` in specified direction

Design:
  * CRUD via /api/ai/alerts endpoints (attached separately)
  * Background asyncio task scans every N seconds (default 30, admin-configurable)
  * On trigger → creates a notification (integrates with existing Notifications module)
  * `triggered_at` set
  alerts default to one-shot (`repeat=False`)
  * Fully independent from Signal Engine / TA Engine — this is a lightweight loop
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import feed
from . import ta_engine as ta

logger = logging.getLogger("ai.intel.alerts")

VALID_TYPES = {"price_above", "price_below", "percent_move",
               "indicator_cross", "rsi_alert"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AlertsEngine:
    """Owns alert CRUD + background evaluation loop."""

    _COLL = "ai_price_alerts"

    def __init__(self, db, interval_sec: int = 30):
        self.db = db
        self.interval_sec = interval_sec
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    # -------- lifecycle --------
    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("AlertsEngine started (interval=%ds)", self.interval_sec)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None

    def set_interval(self, seconds: int):
        self.interval_sec = max(5, int(seconds))

    # -------- CRUD --------
    async def create(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        atype = payload.get("type")
        if atype not in VALID_TYPES:
            raise ValueError(f"invalid type; valid={sorted(VALID_TYPES)}")
        symbol = (payload.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("symbol required")
        doc: Dict[str, Any] = {
            "alert_id": f"al_{uuid.uuid4().hex[:12]}",
            "user_id": user_id, "type": atype, "symbol": symbol,
            "created_at": _now(), "updated_at": _now(),
            "triggered_at": None, "status": "active",
            "repeat": bool(payload.get("repeat", False)),
            "note": (payload.get("note") or "")[:200],
        }
        # Per-type params + snapshot of current price for percent_move
        current_price = feed.current_price(symbol)
        doc["last_price"] = current_price
        if atype == "price_above" or atype == "price_below":
            tp = float(payload["target_price"])
            doc["target_price"] = tp
        elif atype == "percent_move":
            pct = float(payload["target_percent"])
            direction = (payload.get("direction") or "both").lower()
            if direction not in ("up", "down", "both"):
                raise ValueError("direction must be up|down|both")
            doc["target_percent"] = pct
            doc["direction"] = direction
            doc["anchor_price"] = float(payload.get("anchor_price") or current_price)
        elif atype == "indicator_cross":
            fast = int(payload.get("fast_ema", 20))
            slow = int(payload.get("slow_ema", 50))
            if fast >= slow:
                raise ValueError("fast_ema must be < slow_ema")
            doc["fast_ema"] = fast
            doc["slow_ema"] = slow
            doc["timeframe"] = payload.get("timeframe", "H1")
        elif atype == "rsi_alert":
            threshold = float(payload["threshold"])
            direction = (payload.get("direction") or "cross_above").lower()
            if direction not in ("cross_above", "cross_below"):
                raise ValueError("direction must be cross_above|cross_below")
            doc["threshold"] = threshold
            doc["direction"] = direction
            doc["timeframe"] = payload.get("timeframe", "H1")
        await self.db[self._COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if status:
            q["status"] = status
        cur = self.db[self._COLL].find(q, {"_id": 0}).sort("created_at", -1)
        return [d async for d in cur]

    async def delete(self, user_id: str, alert_id: str) -> bool:
        res = await self.db[self._COLL].delete_one(
            {"user_id": user_id, "alert_id": alert_id})
        return res.deleted_count > 0

    async def toggle(self, user_id: str, alert_id: str, active: bool) -> Optional[Dict[str, Any]]:
        await self.db[self._COLL].update_one(
            {"user_id": user_id, "alert_id": alert_id},
            {"$set": {"status": "active" if active else "paused", "updated_at": _now(),
                      "triggered_at": None if active else None}},
        )
        return await self.db[self._COLL].find_one(
            {"user_id": user_id, "alert_id": alert_id}, {"_id": 0})

    # -------- background evaluation --------
    async def _loop(self):
        while not self._stop.is_set():
            try:
                await self._evaluate_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("alerts loop error: %s", e)
            await asyncio.sleep(self.interval_sec)

    async def _evaluate_once(self):
        cur = self.db[self._COLL].find({"status": "active"}, {"_id": 0})
        alerts = [d async for d in cur]
        if not alerts:
            return
        # Group alerts by symbol to compute price/candles once per symbol
        by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for a in alerts:
            by_symbol.setdefault(a["symbol"], []).append(a)
        for sym, symbol_alerts in by_symbol.items():
            try:
                await self._eval_symbol(sym, symbol_alerts)
            except Exception as e:
                logger.warning("eval symbol %s failed: %s", sym, e)

    async def _eval_symbol(self, symbol: str, alerts: List[Dict[str, Any]]):
        price = feed.current_price(symbol)
        # Precompute indicator packs per (timeframe) that we need
        tf_needed = {a.get("timeframe", "H1") for a in alerts
                     if a["type"] in ("indicator_cross", "rsi_alert")}
        ind_by_tf: Dict[str, Dict[str, Any]] = {}
        for tf in tf_needed:
            candles = feed.get_candles(symbol, tf, count=250)
            ind_by_tf[tf] = ta.compute(candles) if candles else {}
        for a in alerts:
            fired = False
            delta_msg = ""
            atype = a["type"]
            last_price = float(a.get("last_price") or price)
            if atype == "price_above":
                # Level trigger: fire whenever price is currently above target.
                # `repeat=False` (default) ensures alert becomes 'triggered' → only fires once.
                if price >= a["target_price"]:
                    fired = True
                    delta_msg = f"crossed above {a['target_price']}"
            elif atype == "price_below":
                if price <= a["target_price"]:
                    fired = True
                    delta_msg = f"crossed below {a['target_price']}"
            elif atype == "percent_move":
                anchor = float(a["anchor_price"])
                if anchor:
                    move_pct = (price - anchor) / anchor * 100.0
                    tgt = float(a["target_percent"])
                    direction = a.get("direction", "both")
                    if direction in ("up", "both") and move_pct >= tgt:
                        fired = True
                        delta_msg = f"moved +{move_pct:.2f}% from {anchor}"
                    elif direction in ("down", "both") and move_pct <= -tgt:
                        fired = True
                        delta_msg = f"moved {move_pct:.2f}% from {anchor}"
            elif atype == "indicator_cross":
                ind = ind_by_tf.get(a.get("timeframe", "H1"), {})
                fast = a["fast_ema"]
                slow = a["slow_ema"]
                if fast == 20 and slow == 50:
                    diff_now = ind.get("ema20", 0) - ind.get("ema50", 0)
                elif fast == 50 and slow == 200:
                    diff_now = ind.get("ema50", 0) - ind.get("ema200", 0)
                else:
                    diff_now = 0
                prev_sign = a.get("_prev_diff_sign")
                cur_sign = 1 if diff_now > 0 else (-1 if diff_now < 0 else 0)
                if prev_sign is not None and prev_sign != 0 and cur_sign != 0 and prev_sign != cur_sign:
                    fired = True
                    delta_msg = f"EMA {fast}/{slow} {'golden' if cur_sign > 0 else 'death'} cross"
                # Persist current sign for next iteration
                await self.db[self._COLL].update_one(
                    {"alert_id": a["alert_id"]}, {"$set": {"_prev_diff_sign": cur_sign}}
                )
            elif atype == "rsi_alert":
                ind = ind_by_tf.get(a.get("timeframe", "H1"), {})
                rsi_val = ind.get("rsi", 50)
                prev_rsi = a.get("_prev_rsi", rsi_val)
                if a["direction"] == "cross_above":
                    if prev_rsi < a["threshold"] <= rsi_val:
                        fired = True
                        delta_msg = f"RSI crossed above {a['threshold']} (now {rsi_val:.1f})"
                else:
                    if prev_rsi > a["threshold"] >= rsi_val:
                        fired = True
                        delta_msg = f"RSI crossed below {a['threshold']} (now {rsi_val:.1f})"
                await self.db[self._COLL].update_one(
                    {"alert_id": a["alert_id"]}, {"$set": {"_prev_rsi": rsi_val}}
                )
            # Always update last_price for next tick
            await self.db[self._COLL].update_one(
                {"alert_id": a["alert_id"]},
                {"$set": {"last_price": price, "updated_at": _now()}}
            )
            if fired:
                await self._on_fire(a, price, delta_msg)

    async def _on_fire(self, alert: Dict[str, Any], price: float, delta_msg: str):
        title = f"Price alert · {alert['symbol']}"
        body = f"{alert['symbol']} {delta_msg} — now {price}"
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": alert["user_id"],
                "title": title, "body": body,
                "read": False, "created_at": _now(),
                "deeplink": f"/ai/signal/{alert['symbol']}",
                "category": "price_alert",
                "metadata": {"alert_id": alert["alert_id"], "type": alert["type"],
                             "symbol": alert["symbol"], "trigger_price": price},
            })
        except Exception as e:
            logger.warning("notification write failed for alert %s: %s", alert.get("alert_id"), e)
        # Update alert doc
        set_fields = {"triggered_at": _now(), "trigger_price": price, "trigger_note": delta_msg}
        if not alert.get("repeat"):
            set_fields["status"] = "triggered"
        await self.db[self._COLL].update_one(
            {"alert_id": alert["alert_id"]}, {"$set": set_fields}
        )
