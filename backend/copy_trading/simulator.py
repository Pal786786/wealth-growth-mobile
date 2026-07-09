"""Copy Trading — Master Trade Simulator (Sprint 7B.2/7B.3)

Sprint 7B.3 extends the simulator:
  * Includes custom traders (from copy_custom_traders) alongside the 28 seeded personas.
  * Skips traders that are `disabled=True` in overlay or custom doc.
  * Emits SIM_STATE_CHANGED events on pause/resume/speed changes.
  * Records lightweight metrics — active_traders / open_master_trades / lifetime.
"""
from __future__ import annotations
import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import traders as tmod
from . import admin_traders as at
from .events import EventBus, TradeEvent, TRADE_OPENED, TRADE_CLOSED, SIM_STATE_CHANGED

logger = logging.getLogger("copy.simulator")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MasterSimulator:
    _COLLECTION = "copy_master_trades"

    def __init__(self, db, bus: EventBus, config):
        self.db = db
        self.bus = bus
        self.config = config
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stop = asyncio.Event()
        self._paused = asyncio.Event()
        self._started = False

    # -------------- lifecycle --------------
    async def start(self):
        if self._started:
            return
        self._started = True
        self._stop.clear()
        sim = await self.config.sim_state()
        if not sim.get("enabled", True):
            self._paused.set()
        # Seeded traders always spawn (obey disabled overlay in loop)
        for p in tmod._PERSONAS:
            self._spawn_trader(p["id"])
        # Custom traders too
        for tid in await at.list_custom_trader_ids(self.db):
            self._spawn_trader(tid)
        logger.info("MasterSimulator started with %d traders", len(self._tasks))

    async def stop(self):
        self._stop.set()
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()
        self._started = False

    def _spawn_trader(self, trader_id: str):
        if trader_id in self._tasks and not self._tasks[trader_id].done():
            return
        self._tasks[trader_id] = asyncio.create_task(self._trader_loop(trader_id))

    async def sync_traders(self):
        """Ensure a task exists for every enabled trader (called after custom creates)."""
        all_ids = await at.all_trader_ids(self.db)
        for tid in all_ids:
            self._spawn_trader(tid)

    async def remove_trader(self, trader_id: str):
        t = self._tasks.pop(trader_id, None)
        if t and not t.done():
            t.cancel()

    # -------------- admin controls --------------
    async def pause(self):
        self._paused.set()
        await self.config.update_sim({"enabled": False})
        await self.bus.publish(TradeEvent(kind=SIM_STATE_CHANGED, trader_id="", master_id="",
                                          symbol="", side="", lot_size=0, entry_price=0,
                                          payload={"enabled": False}))

    async def resume(self):
        self._paused.clear()
        await self.config.update_sim({"enabled": True})
        await self.sync_traders()
        await self.bus.publish(TradeEvent(kind=SIM_STATE_CHANGED, trader_id="", master_id="",
                                          symbol="", side="", lot_size=0, entry_price=0,
                                          payload={"enabled": True}))

    async def set_speed(self, speed: str) -> Dict[str, Any]:
        return await self.config.update_sim({"speed": speed})

    async def status(self) -> Dict[str, Any]:
        sim = await self.config.sim_state()
        open_count = await self.db[self._COLLECTION].count_documents({"status": "open"})
        total = await self.db[self._COLLECTION].estimated_document_count()
        active_traders = sum(1 for t in self._tasks.values() if not t.done())
        return {
            "enabled": sim.get("enabled", True),
            "speed": sim.get("speed", "normal"),
            "active_traders": active_traders,
            "open_master_trades": open_count,
            "lifetime_master_trades": total,
            "paused_flag": self._paused.is_set(),
        }

    async def force_open(self, trader_id: str, side: Optional[str] = None,
                         symbol: Optional[str] = None) -> Dict[str, Any]:
        persona = await self._resolve_persona(trader_id)
        if not persona:
            raise ValueError(f"Unknown trader {trader_id}")
        return await self._open_trade(persona, force_side=side, force_symbol=symbol,
                                      source="admin")

    async def force_close(self, master_id: str) -> Dict[str, Any]:
        doc = await self.db[self._COLLECTION].find_one({"master_id": master_id, "status": "open"})
        if not doc:
            raise ValueError("Master trade not found or already closed")
        return await self._close_trade(doc, source="admin")

    # -------------- persona resolution --------------
    async def _resolve_persona(self, trader_id: str) -> Optional[Dict[str, Any]]:
        """Return a persona-dict with truth/style/seed for either seeded or custom."""
        p = tmod._persona_by_id(trader_id)
        if p:
            return p
        doc = await self.db[at._CUSTOM_COLL].find_one({"trader_id": trader_id}, {"_id": 0})
        return doc.get("persona") if doc else None

    # -------------- trader loop --------------
    async def _trader_loop(self, trader_id: str):
        persona = await self._resolve_persona(trader_id)
        if not persona:
            return
        await asyncio.sleep(random.uniform(1, 8))
        while not self._stop.is_set():
            try:
                sim = await self.config.sim_state()
                if not sim.get("enabled", True) or self._paused.is_set():
                    await asyncio.sleep(3)
                    continue
                # Respect disabled state
                if not await at.is_trader_active_for_sim(self.db, trader_id):
                    await asyncio.sleep(5)
                    continue
                lo, hi = self._interval_range(persona["style"], sim)
                await asyncio.sleep(random.uniform(lo, hi))
                if self._stop.is_set():
                    return
                master = await self._open_trade(persona, source="sim")
                if not master:
                    continue
                hold_lo, hold_hi = self._hold_range(persona["style"], sim)
                await asyncio.sleep(random.uniform(hold_lo, hold_hi))
                if self._stop.is_set():
                    return
                doc = await self.db[self._COLLECTION].find_one(
                    {"master_id": master["master_id"]})
                if doc and doc.get("status") == "open":
                    await self._close_trade(doc, source="sim")
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("simulator loop [%s] error: %s", trader_id, e)
                await asyncio.sleep(5)

    def _interval_range(self, style: str, sim: Dict[str, Any]):
        base = sim.get("style_intervals", {}).get(style) or [180, 600]
        mult = {"slow": 2.0, "normal": 1.0, "fast": 0.3}.get(sim.get("speed", "normal"), 1.0)
        return base[0] * mult, base[1] * mult

    def _hold_range(self, style: str, sim: Dict[str, Any]):
        base = sim.get("style_hold", {}).get(style) or [60, 240]
        mult = {"slow": 2.0, "normal": 1.0, "fast": 0.3}.get(sim.get("speed", "normal"), 1.0)
        return base[0] * mult, base[1] * mult

    async def _open_trade(self, persona: Dict[str, Any], force_side: Optional[str] = None,
                          force_symbol: Optional[str] = None, source: str = "sim") -> Dict[str, Any]:
        symbols = tmod._SYMBOLS_BY_STYLE.get(persona["style"], ["EURUSD", "GBPUSD", "XAUUSD"])
        symbol = (force_symbol or "").upper() if force_symbol else random.choice(symbols)
        if symbol not in symbols and force_symbol:
            symbols = [symbol]
        side = force_side if force_side in ("buy", "sell") else ("buy" if random.random() < 0.55 else "sell")
        base_price = tmod._mock_price_for_symbol(symbol) * random.uniform(0.998, 1.002)
        truth = persona["truth"]
        lot = round(truth["avg_lot"] * random.uniform(0.7, 1.3), 2)
        risk_pct = 0.004 * random.uniform(0.8, 1.2)
        reward_pct = risk_pct * truth["payoff_ratio"]
        if side == "buy":
            sl = base_price * (1 - risk_pct)
            tp = base_price * (1 + reward_pct)
        else:
            sl = base_price * (1 + risk_pct)
            tp = base_price * (1 - reward_pct)
        master = {
            "master_id": f"mt_{uuid.uuid4().hex[:12]}",
            "trader_id": persona["id"],
            "symbol": symbol, "side": side, "lot_size": lot,
            "entry_price": round(base_price, 5),
            "sl": round(sl, 5), "tp": round(tp, 5),
            "status": "open", "opened_at": _now(),
            "closed_at": None, "exit_price": None, "pnl_pct": None,
            "source": source,
        }
        await self.db[self._COLLECTION].insert_one(master)
        master.pop("_id", None)
        await self.bus.publish(TradeEvent(
            kind=TRADE_OPENED, trader_id=persona["id"], master_id=master["master_id"],
            symbol=symbol, side=side, lot_size=lot, entry_price=master["entry_price"],
            sl=master["sl"], tp=master["tp"], source=source, opened_at=master["opened_at"],
        ))
        return master

    async def _close_trade(self, doc: Dict[str, Any], source: str = "sim") -> Dict[str, Any]:
        persona = await self._resolve_persona(doc["trader_id"])
        if not persona:
            return {}
        truth = persona["truth"]
        entry = float(doc["entry_price"])
        is_win = random.random() < truth["win_rate"]
        base_pct = (0.002 * truth["payoff_ratio"] if is_win else -0.002) * random.uniform(0.5, 1.6)
        exit_price = entry * (1 + base_pct) if doc["side"] == "buy" else entry * (1 - base_pct)
        pnl_pct = ((exit_price - entry) / entry) * (1 if doc["side"] == "buy" else -1) * 100.0
        await self.db[self._COLLECTION].update_one(
            {"master_id": doc["master_id"]},
            {"$set": {
                "status": "closed", "closed_at": _now(),
                "exit_price": round(exit_price, 5),
                "pnl_pct": round(pnl_pct, 3),
                "close_source": source,
            }},
        )
        await self.bus.publish(TradeEvent(
            kind=TRADE_CLOSED, trader_id=doc["trader_id"], master_id=doc["master_id"],
            symbol=doc["symbol"], side=doc["side"], lot_size=doc["lot_size"],
            entry_price=entry, exit_price=round(exit_price, 5), pnl_pct=round(pnl_pct, 3),
            source=source, closed_at=_now(),
        ))
        return await self.db[self._COLLECTION].find_one(
            {"master_id": doc["master_id"]}, {"_id": 0}) or {}

    async def recent_master_trades(self, trader_id: Optional[str] = None,
                                   limit: int = 50) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if trader_id:
            q["trader_id"] = trader_id
        cur = self.db[self._COLLECTION].find(q, {"_id": 0}).sort("opened_at", -1).limit(limit)
        return [d async for d in cur]

    async def recent_master_trades_with_follower_count(self, limit: int = 100) -> List[Dict[str, Any]]:
        trades = await self.recent_master_trades(limit=limit)
        for t in trades:
            t["followers_copied"] = await self.db.copy_follower_trades.count_documents(
                {"master_id": t["master_id"]})
        return trades
