"""Copy-trading Fan-Out Engine — Sprint 7B.2

Event-driven mirroring:
   MasterSimulator      ──► EventBus ──►  CopyEngine.on_trade_opened  ──► BrokerAdapter
   (or admin, or real                     CopyEngine.on_trade_closed
    broker in future)

NO polling. When a master trade opens, the CopyEngine receives the event once
and fans out to every active follower in a single async gather. Risk
protection is enforced per-follower before execution.

Persistence:
    copy_relationships   — one doc per (user_id, trader_id) with settings/status
    copy_follower_trades — mirrored trades (managed by BrokerAdapter)
    copy_master_trades   — master trades (managed by MasterSimulator)
    copy_daily_stats     — per-user daily P&L tracking for risk halts
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .events import EventBus, TradeEvent, TRADE_OPENED, TRADE_CLOSED
from .broker import BrokerAdapter, PaperBroker
from .config import CopyConfig, DEFAULT_SETTINGS, VALID_MODES, STATUSES

logger = logging.getLogger("copy.engine")

_STARTING_EQUITY_USD = 10_000.0   # paper equity per user (per-trader accounting)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CopyEngine:
    def __init__(self, db, bus: EventBus, broker: BrokerAdapter, config: CopyConfig):
        self.db = db
        self.bus = bus
        self.broker = broker
        self.config = config
        # Sprint 7B.3: in-memory health metrics
        self._fanout_ms = deque(maxlen=200)
        self._exec_ms = deque(maxlen=500)
        self._failed_mirrors = 0
        self._retry_queue: List[Dict[str, Any]] = []
        self._events_processed = 0
        # Subscribe once
        self.bus.subscribe(TRADE_OPENED, self.on_trade_opened)
        self.bus.subscribe(TRADE_CLOSED, self.on_trade_closed)

    # ----- Sprint 7B.3 health snapshot -----
    def health_snapshot(self) -> Dict[str, Any]:
        def avg(dq: deque) -> float:
            return round(sum(dq) / len(dq), 2) if dq else 0.0
        return {
            "broker": self.broker.name,
            "broker_ok": True,
            "avg_fanout_ms": avg(self._fanout_ms),
            "avg_exec_ms": avg(self._exec_ms),
            "events_processed": self._events_processed,
            "failed_mirrors": self._failed_mirrors,
            "retry_queue_size": len(self._retry_queue),
            "fanout_samples": len(self._fanout_ms),
        }

    # ==================================================================
    # Relationship management
    # ==================================================================

    async def get_settings(self, user_id: str, trader_id: str) -> Dict[str, Any]:
        doc = await self.db.copy_relationships.find_one(
            {"user_id": user_id, "trader_id": trader_id}, {"_id": 0}
        )
        defaults = await self.config.defaults()
        if not doc:
            return {"user_id": user_id, "trader_id": trader_id,
                    "status": "stopped", "settings": defaults,
                    "started_at": None, "starting_equity_usd": _STARTING_EQUITY_USD,
                    "halt_reason": None}
        # Ensure new keys always exist
        doc["settings"] = {**defaults, **(doc.get("settings") or {})}
        return doc

    async def start_copy(self, user_id: str, trader_id: str,
                         settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        defaults = await self.config.defaults()
        clean = _sanitize_settings(settings or {})
        merged = {**defaults, **clean}
        merged["mode"] = merged.get("mode") if merged.get("mode") in VALID_MODES else "multiplier"
        now = _now()
        existing = await self.db.copy_relationships.find_one(
            {"user_id": user_id, "trader_id": trader_id}) or {}
        starting_equity = float(existing.get("starting_equity_usd") or _STARTING_EQUITY_USD)
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": {
                "user_id": user_id, "trader_id": trader_id,
                "copy_id": existing.get("copy_id") or f"cp_{uuid.uuid4().hex[:12]}",
                "settings": merged, "status": "active",
                "started_at": existing.get("started_at") or now,
                "updated_at": now,
                "starting_equity_usd": starting_equity,
                "halt_reason": None,
            }},
            upsert=True,
        )
        return await self.get_settings(user_id, trader_id)

    async def update_settings(self, user_id: str, trader_id: str,
                              patch: Dict[str, Any]) -> Dict[str, Any]:
        clean = _sanitize_settings(patch)
        if not clean:
            return await self.get_settings(user_id, trader_id)
        set_ops = {f"settings.{k}": v for k, v in clean.items()}
        set_ops["updated_at"] = _now()
        set_ops["user_id"] = user_id
        set_ops["trader_id"] = trader_id
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": set_ops}, upsert=True,
        )
        return await self.get_settings(user_id, trader_id)

    async def set_status(self, user_id: str, trader_id: str, status: str,
                         halt_reason: Optional[str] = None,
                         close_open_trades: bool = False) -> Dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"invalid status {status!r}")
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": {"status": status, "updated_at": _now(),
                      "user_id": user_id, "trader_id": trader_id,
                      "halt_reason": halt_reason}},
            upsert=True,
        )
        if close_open_trades or status == "stopped":
            await self.broker.close_all(user_id, trader_id, reason=f"copy_{status}")
        return await self.get_settings(user_id, trader_id)

    async def pause_all(self, user_id: str) -> int:
        res = await self.db.copy_relationships.update_many(
            {"user_id": user_id, "status": "active"},
            {"$set": {"status": "paused", "updated_at": _now()}},
        )
        return res.modified_count

    async def resume_all(self, user_id: str) -> int:
        res = await self.db.copy_relationships.update_many(
            {"user_id": user_id, "status": {"$in": ["paused", "halted"]}},
            {"$set": {"status": "active", "updated_at": _now(), "halt_reason": None}},
        )
        return res.modified_count

    async def close_all(self, user_id: str) -> int:
        # Stop all relationships + flat-close all open positions
        await self.db.copy_relationships.update_many(
            {"user_id": user_id},
            {"$set": {"status": "stopped", "updated_at": _now()}},
        )
        return await self.broker.close_all(user_id, reason="user_close_all")

    async def list_copies(self, user_id: str) -> List[Dict[str, Any]]:
        cur = self.db.copy_relationships.find({"user_id": user_id}, {"_id": 0}).sort("started_at", -1)
        return [d async for d in cur]

    # ==================================================================
    # Event handlers
    # ==================================================================

    async def on_trade_opened(self, event: TradeEvent):
        """Master TRADE_OPENED → fan out to every active follower."""
        t0 = time.perf_counter()
        cur = self.db.copy_relationships.find(
            {"trader_id": event.trader_id, "status": "active"}, {"_id": 0})
        followers = [d async for d in cur]
        if not followers:
            self._events_processed += 1
            self._fanout_ms.append(round((time.perf_counter() - t0) * 1000, 2))
            return
        results = await asyncio.gather(
            *[self._mirror_open(f, event) for f in followers], return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                self._failed_mirrors += 1
                logger.warning("mirror_open error: %s", r)
        self._events_processed += 1
        self._fanout_ms.append(round((time.perf_counter() - t0) * 1000, 2))

    async def on_trade_closed(self, event: TradeEvent):
        """Master TRADE_CLOSED → close ALL follower trades for that master_id."""
        cur = self.db.copy_follower_trades.find(
            {"master_id": event.master_id, "status": "open"}, {"_id": 0})
        openers = [d async for d in cur]
        if not openers:
            return
        exit_price = event.exit_price or event.entry_price
        results = await asyncio.gather(
            *[self._mirror_close(t, exit_price, event) for t in openers],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.warning("mirror_close error: %s", r)

    async def _mirror_open(self, rel: Dict[str, Any], event: TradeEvent):
        t0 = time.perf_counter()
        settings = rel.get("settings") or await self.config.defaults()
        user_id = rel["user_id"]
        trader_id = rel["trader_id"]

        # 1. Auto-copy new trades check
        if not settings.get("auto_copy_new_trades", True):
            return

        # 2. Risk protection halts
        halted = await self._check_risk_halts(user_id, trader_id, settings, rel)
        if halted:
            return

        # 3. Compute follower lot size
        follower_lot = self._compute_lot(event.lot_size, settings, rel)
        if follower_lot <= 0:
            await self._record_skip(user_id, trader_id, event, "lot_too_small")
            return

        # 4. Slippage-adjusted entry price
        entry = self._apply_slippage(event.entry_price, event.side,
                                     settings.get("slippage_pips", 5))

        try:
            trade = await self.broker.open_position(
                user_id=user_id, symbol=event.symbol, side=event.side,
                lot=follower_lot, entry_price=entry,
                sl=event.sl, tp=event.tp,
                source_trade_id=event.master_id,
                trader_id=trader_id, copy_id=rel.get("copy_id"),
            )
            await self._notify(user_id, "Copy trade opened",
                               f"{event.symbol} {event.side.upper()} {follower_lot} lot mirrored from {trader_id}",
                               deeplink=f"/copies/{trader_id}")
            return trade
        except Exception as e:
            self._failed_mirrors += 1
            self._retry_queue.append({
                "user_id": user_id, "trader_id": trader_id,
                "master_id": event.master_id, "error": str(e),
                "queued_at": _now().isoformat(),
            })
            # Cap retry queue to last 100 entries so it doesn't grow unbounded
            if len(self._retry_queue) > 100:
                self._retry_queue = self._retry_queue[-100:]
            logger.warning("mirror open failed [%s/%s]: %s", user_id, trader_id, e)
        finally:
            self._exec_ms.append(round((time.perf_counter() - t0) * 1000, 2))

    async def _mirror_close(self, follower_trade: Dict[str, Any],
                            exit_price: float, event: TradeEvent):
        user_id = follower_trade["user_id"]
        trader_id = follower_trade["trader_id"]
        # Apply reverse slippage
        rel = await self.db.copy_relationships.find_one(
            {"user_id": user_id, "trader_id": trader_id}, {"_id": 0})
        settings = (rel or {}).get("settings") or await self.config.defaults()
        exit_adj = self._apply_slippage(
            exit_price, "sell" if follower_trade["side"] == "buy" else "buy",
            settings.get("slippage_pips", 5))
        closed = await self.broker.close_position(
            user_id, follower_trade["follower_trade_id"], exit_adj, reason="master_close")
        # Update daily stats + trigger auto-halt if breached
        if closed and closed.get("pnl_usd") is not None:
            await self._record_daily_pnl(user_id, trader_id, float(closed["pnl_usd"]))
            if closed["pnl_usd"] >= 0:
                await self._notify(user_id, "Copy trade closed — profit",
                                   f"{follower_trade['symbol']} +${closed['pnl_usd']:.2f}",
                                   deeplink=f"/copies/{trader_id}")
            else:
                await self._notify(user_id, "Copy trade closed",
                                   f"{follower_trade['symbol']} ${closed['pnl_usd']:.2f}",
                                   deeplink=f"/copies/{trader_id}")
            await self._check_risk_halts(user_id, trader_id, settings, rel)
        return closed

    # ==================================================================
    # Helpers
    # ==================================================================

    def _compute_lot(self, master_lot: float, settings: Dict[str, Any],
                     rel: Dict[str, Any]) -> float:
        mode = settings.get("mode", "multiplier")
        min_lot = float(settings.get("min_lot_size", 0.01))
        max_lot = float(settings.get("max_lot_size", 5.0))

        if mode == "fixed_lot":
            lot = float(settings.get("fixed_lot", 0.10))
        elif mode == "equity_percent":
            equity_pct = float(settings.get("equity_percent", 2.0)) / 100.0
            equity = float(rel.get("starting_equity_usd") or _STARTING_EQUITY_USD)
            # 1 lot of master ≈ $100k notional → follower size = (equity * pct) / $100k
            lot = round((equity * equity_pct) / 100_000 * max(1.0, master_lot), 2)
        else:  # multiplier
            mult = float(settings.get("multiplier", 1.0))
            lot = round(master_lot * mult, 2)
        # Clamp
        lot = max(min_lot, min(max_lot, lot))
        # Round to 2 decimals
        return round(lot, 2)

    def _apply_slippage(self, price: float, side: str, pips: float) -> float:
        # Approximate: 1 pip = 0.0001 for FX; use 0.0001 as heuristic
        adj = pips * 0.0001
        return price * (1 + adj) if side == "buy" else price * (1 - adj)

    async def _record_skip(self, user_id: str, trader_id: str,
                           event: TradeEvent, reason: str):
        await self.db.copy_follower_trades.insert_one({
            "follower_trade_id": f"sk_{uuid.uuid4().hex[:12]}",
            "user_id": user_id, "trader_id": trader_id,
            "master_id": event.master_id, "symbol": event.symbol, "side": event.side,
            "lot_size": 0.0, "entry_price": event.entry_price,
            "opened_at": _now(), "closed_at": _now(),
            "status": "skipped", "skip_reason": reason,
            "pnl_usd": 0.0, "pnl_pct": 0.0, "broker": self.broker.name,
        })

    async def _record_daily_pnl(self, user_id: str, trader_id: str, pnl_usd: float):
        today = _now().strftime("%Y-%m-%d")
        await self.db.copy_daily_stats.update_one(
            {"user_id": user_id, "trader_id": trader_id, "day": today},
            {"$inc": {"pnl_usd": pnl_usd, "trade_count": 1},
             "$set": {"updated_at": _now()},
             "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )

    async def _check_risk_halts(self, user_id: str, trader_id: str,
                                settings: Dict[str, Any], rel: Dict[str, Any]) -> bool:
        """Returns True if the copy was HALTED (further trades should be blocked)."""
        if not rel:
            return False
        # 1. Max open trades
        open_count = await self.db.copy_follower_trades.count_documents(
            {"user_id": user_id, "trader_id": trader_id, "status": "open"})
        if open_count >= int(settings.get("max_open_trades", 10)):
            return True  # skip this trade, don't halt permanently
        # 2. Max daily loss
        today = _now().strftime("%Y-%m-%d")
        starting_equity = float(rel.get("starting_equity_usd") or _STARTING_EQUITY_USD)
        stat = await self.db.copy_daily_stats.find_one(
            {"user_id": user_id, "trader_id": trader_id, "day": today}) or {}
        daily_pnl = float(stat.get("pnl_usd", 0.0))
        max_daily_loss = float(settings.get("max_daily_loss_pct", 10.0))
        if daily_pnl < 0 and abs(daily_pnl) / starting_equity * 100 >= max_daily_loss:
            if settings.get("auto_pause_on_daily_loss", True):
                await self.set_status(user_id, trader_id, "halted",
                                      halt_reason=f"max_daily_loss ({max_daily_loss}%)",
                                      close_open_trades=False)
                await self._notify(user_id, "Copy paused — daily loss limit",
                                   f"Daily loss limit reached ({max_daily_loss}%). Copy of {trader_id} halted.",
                                   deeplink=f"/copies/{trader_id}")
            return True
        # 3. Max drawdown / equity protection
        total_pnl = await self._lifetime_pnl(user_id, trader_id)
        equity_now = starting_equity + total_pnl
        dd_pct = ((starting_equity - equity_now) / starting_equity) * 100.0 if equity_now < starting_equity else 0.0
        max_dd = float(settings.get("max_drawdown_pct", 20.0))
        eq_prot = float(settings.get("equity_protection_pct", 30.0))
        if dd_pct >= max_dd:
            await self.set_status(user_id, trader_id, "halted",
                                  halt_reason=f"max_drawdown ({max_dd}%)",
                                  close_open_trades=False)
            await self._notify(user_id, "Copy halted — max drawdown",
                               f"Max drawdown {max_dd}% reached on {trader_id}.",
                               deeplink=f"/copies/{trader_id}")
            return True
        if dd_pct >= eq_prot and settings.get("auto_close_on_equity_protection", True):
            await self.set_status(user_id, trader_id, "halted",
                                  halt_reason=f"equity_protection ({eq_prot}%)",
                                  close_open_trades=True)
            await self._notify(user_id, "Copy halted — equity protection",
                               f"Equity protection triggered ({eq_prot}%). All positions closed.",
                               deeplink=f"/copies/{trader_id}")
            return True
        return False

    async def _lifetime_pnl(self, user_id: str, trader_id: str) -> float:
        pipeline = [
            {"$match": {"user_id": user_id, "trader_id": trader_id,
                        "status": {"$in": ["closed", "open"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$pnl_usd"}}},
        ]
        cur = self.db.copy_follower_trades.aggregate(pipeline)
        docs = await cur.to_list(1)
        return float(docs[0]["total"]) if docs else 0.0

    async def _notify(self, user_id: str, title: str, body: str, deeplink: str = "/copies"):
        try:
            await self.db.notifications.insert_one({
                "notif_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id, "title": str(title), "body": str(body),
                "read": False, "created_at": _now(),
                "deeplink": deeplink, "category": "copy_trading",
            })
        except Exception:
            pass

    # ==================================================================
    # Query helpers (used by /my/copies + summary + history)
    # ==================================================================

    async def my_copies_enriched(self, user_id: str,
                                 trader_lookup) -> List[Dict[str, Any]]:
        rels = await self.list_copies(user_id)
        for rel in rels:
            # Live stats
            open_pos = await self.db.copy_follower_trades.count_documents(
                {"user_id": user_id, "trader_id": rel["trader_id"], "status": "open"})
            lifetime_pnl = await self._lifetime_pnl(user_id, rel["trader_id"])
            today = _now().strftime("%Y-%m-%d")
            stat = await self.db.copy_daily_stats.find_one(
                {"user_id": user_id, "trader_id": rel["trader_id"], "day": today}) or {}
            rel["live"] = {
                "open_positions": open_pos,
                "lifetime_pnl_usd": round(lifetime_pnl, 2),
                "today_pnl_usd": round(float(stat.get("pnl_usd", 0.0)), 2),
                "today_trades": int(stat.get("trade_count", 0)),
                "starting_equity_usd": float(rel.get("starting_equity_usd") or _STARTING_EQUITY_USD),
                "current_equity_usd": round(float(rel.get("starting_equity_usd") or _STARTING_EQUITY_USD) + lifetime_pnl, 2),
            }
            rel["trader"] = trader_lookup(rel["trader_id"])
        return rels

    async def my_summary(self, user_id: str) -> Dict[str, Any]:
        # Aggregate lifetime + today P&L across all copies
        pipe_all = [
            {"$match": {"user_id": user_id, "status": {"$in": ["closed", "open"]}}},
            {"$group": {"_id": None,
                        "lifetime": {"$sum": "$pnl_usd"},
                        "trades":   {"$sum": 1},
                        "wins":     {"$sum": {"$cond": [{"$gt": ["$pnl_usd", 0]}, 1, 0]}}}}
        ]
        cur = self.db.copy_follower_trades.aggregate(pipe_all)
        docs = await cur.to_list(1)
        agg = docs[0] if docs else {"lifetime": 0, "trades": 0, "wins": 0}
        today = _now().strftime("%Y-%m-%d")
        pipe_today = [
            {"$match": {"user_id": user_id, "day": today}},
            {"$group": {"_id": None, "today": {"$sum": "$pnl_usd"},
                        "today_trades": {"$sum": "$trade_count"}}}
        ]
        cur2 = self.db.copy_daily_stats.aggregate(pipe_today)
        docs2 = await cur2.to_list(1)
        today_agg = docs2[0] if docs2 else {"today": 0, "today_trades": 0}
        open_pos = await self.db.copy_follower_trades.count_documents(
            {"user_id": user_id, "status": "open"})
        active = await self.db.copy_relationships.count_documents(
            {"user_id": user_id, "status": "active"})
        paused = await self.db.copy_relationships.count_documents(
            {"user_id": user_id, "status": "paused"})
        halted = await self.db.copy_relationships.count_documents(
            {"user_id": user_id, "status": "halted"})
        wins = int(agg.get("wins", 0))
        total = int(agg.get("trades", 0))
        return {
            "total_pnl_usd": round(float(agg.get("lifetime", 0)), 2),
            "today_pnl_usd": round(float(today_agg.get("today", 0)), 2),
            "today_trades": int(today_agg.get("today_trades", 0)),
            "open_positions": open_pos,
            "active_copies": active,
            "paused_copies": paused,
            "halted_copies": halted,
            "total_trades": total,
            "win_rate_pct": round((wins / total * 100) if total > 0 else 0, 1),
        }

    async def follower_trades(self, user_id: str, trader_id: Optional[str] = None,
                              status: Optional[str] = None,
                              limit: int = 100) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if trader_id:
            q["trader_id"] = trader_id
        if status:
            q["status"] = status
        cur = self.db.copy_follower_trades.find(q, {"_id": 0}).sort("opened_at", -1).limit(limit)
        return [d async for d in cur]


def _sanitize_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for k, v in patch.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if k == "mode":
            if v in VALID_MODES:
                clean[k] = v
        elif k == "resume_mode":
            if v in ("manual", "auto"):
                clean[k] = v
        elif isinstance(v, bool):
            clean[k] = v
        elif isinstance(v, (int, float)):
            if k in ("max_open_trades",):
                clean[k] = int(v)
            else:
                clean[k] = float(v)
    return clean
