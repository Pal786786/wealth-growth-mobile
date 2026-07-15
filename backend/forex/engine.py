"""Paper trading engine — market orders, TP/SL, P&L mark-to-market.

P&L formula (in INR):
    pnl_usd = (close - open) * contract_size * lot_size * dir
    pnl_inr = pnl_usd * USD_INR

Margin (simplified for MVP):
    margin_inr = lot_size * margin_per_lot_inr (default ₹1000/lot, admin-editable)

Default starting balance: ₹10,00,000 per user (configurable).
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .feed import PriceFeed
from .symbols import SYMBOL_INDEX, USD_INR
from .costs import snapshot_for_trade, settle, commission_inr

logger = logging.getLogger("forex.engine")
DEFAULT_DEMO_BALANCE = 1_000_000.0  # ₹10,00,000 = ₹10 lakh
DEFAULT_MARGIN_PER_LOT = 1_000.0    # ₹1,000 per lot (simple MVP rule)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


class TradingEngine:
    def __init__(self, db, feed: PriceFeed):
        self.db = db
        self.feed = feed
        self._mark_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._mark_task and not self._mark_task.done():
            return
        self._stop.clear()
        self._mark_task = asyncio.create_task(self._mark_forever())

    async def stop(self):
        self._stop.set()
        if self._mark_task:
            try:
                await asyncio.wait_for(self._mark_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover
                pass

    # ---------- balances ----------

    async def get_or_init_balance(self, user_id: str) -> Dict[str, Any]:
        doc = await self.db.forex_balances.find_one({"user_id": user_id})
        if doc:
            return doc
        # Read default from settings (if set)
        cfg = await self.db.forex_settings.find_one({"_id": "active"}) or {}
        starting = float(cfg.get("default_demo_balance", DEFAULT_DEMO_BALANCE))
        new = {
            "user_id": user_id,
            "balance": starting,
            "currency": "INR",
            "updated_at": _now(),
        }
        await self.db.forex_balances.insert_one(new)
        return new

    async def reset_balance(self, user_id: str) -> Dict[str, Any]:
        cfg = await self.db.forex_settings.find_one({"_id": "active"}) or {}
        starting = float(cfg.get("default_demo_balance", DEFAULT_DEMO_BALANCE))
        # Also close all open positions silently (reset cancels them)
        await self.db.forex_positions.update_many(
            {"user_id": user_id, "status": "open"},
            {"$set": {"status": "cancelled", "close_reason": "reset", "closed_at": _now()}},
        )
        await self.db.forex_balances.update_one(
            {"user_id": user_id},
            {"$set": {"balance": starting, "currency": "INR", "updated_at": _now()}},
            upsert=True,
        )
        return await self.get_or_init_balance(user_id)

    # ---------- positions ----------

    def _margin_per_lot(self, cfg: Dict[str, Any]) -> float:
        return float(cfg.get("margin_per_lot", DEFAULT_MARGIN_PER_LOT))

    def _pnl_inr(self, side: str, entry: float, current: float, contract_size: float, lot_size: float) -> float:
        direction = 1 if side == "buy" else -1
        pnl_usd = (current - entry) * contract_size * lot_size * direction
        return pnl_usd * USD_INR

    async def open_position(self, user_id: str, symbol_id: str, side: str, lot_size: float,
                            tp: Optional[float], sl: Optional[float]) -> Dict[str, Any]:
        symbol_id = symbol_id.upper()
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        spec = SYMBOL_INDEX.get(symbol_id)
        if not spec:
            raise ValueError(f"unknown symbol {symbol_id}")
        if lot_size <= 0:
            raise ValueError("lot_size must be > 0")
        cfg = await self.db.forex_settings.find_one({"_id": "active"}) or {}
        if not cfg.get("enabled", True):
            raise ValueError("Forex trading is disabled by admin")
        sym_cfg = (cfg.get("symbols") or {}).get(symbol_id, {})
        if not sym_cfg.get("enabled", True):
            raise ValueError(f"{symbol_id} is disabled by admin")
        min_lot = float(sym_cfg.get("min_lot", cfg.get("min_lot", 0.01)))
        max_lot = float(sym_cfg.get("max_lot", cfg.get("max_lot", 100.0)))
        if lot_size < min_lot or lot_size > max_lot:
            raise ValueError(f"lot_size must be between {min_lot} and {max_lot}")

        q = await self.feed.get_quote(symbol_id)
        if not q:
            raise ValueError("No live price for symbol")
        entry = q.ask if side == "buy" else q.bid
        margin = lot_size * self._margin_per_lot(cfg)

        bal = await self.get_or_init_balance(user_id)
        if bal["balance"] < margin:
            raise ValueError(f"Insufficient balance. Need ₹{margin:,.0f}, have ₹{bal['balance']:,.0f}")

        position = {
            "position_id": str(uuid.uuid4()),
            "user_id": user_id,
            "symbol_id": symbol_id,
            "side": side,
            "lot_size": float(lot_size),
            "entry_price": float(entry),
            "current_price": float(q.mid),
            "tp": float(tp) if tp else None,
            "sl": float(sl) if sl else None,
            "margin_inr": float(margin),
            "pnl_inr": 0.0,
            "status": "open",
            "opened_at": _now(),
            "closed_at": None,
            "close_price": None,
            "close_reason": None,
            "contract_size": spec["contract_size"],
            # Sprint 16.1 — commission snapshot (immutable for this trade)
            **snapshot_for_trade(cfg),
        }
        await self.db.forex_positions.insert_one(position)
        # Audit
        await self.db.forex_orders.insert_one({
            "order_id": str(uuid.uuid4()),
            "position_id": position["position_id"],
            "user_id": user_id,
            "symbol_id": symbol_id,
            "side": side,
            "lot_size": lot_size,
            "type": "market",
            "price": entry,
            "status": "filled",
            "ts": _now(),
        })
        await self.db.forex_history.insert_one({
            "user_id": user_id, "event": "open",
            "position_id": position["position_id"],
            "symbol_id": symbol_id, "side": side,
            "lot_size": lot_size, "price": entry, "ts": _now(),
        })
        # Deduct margin
        await self.db.forex_balances.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": -margin}, "$set": {"updated_at": _now()}},
        )
        return _serialize(position)

    async def close_position(self, user_id: str, position_id: str, reason: str = "manual") -> Dict[str, Any]:
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos:
            raise ValueError("Position not found")
        if pos["status"] != "open":
            raise ValueError("Position is not open")
        spec = SYMBOL_INDEX.get(pos["symbol_id"])
        q = await self.feed.get_quote(pos["symbol_id"])
        if not q or not spec:
            raise ValueError("No live price for symbol")
        # Closing a buy uses bid; closing a sell uses ask
        close_px = q.bid if pos["side"] == "buy" else q.ask
        pnl = self._pnl_inr(pos["side"], pos["entry_price"], close_px,
                            spec["contract_size"], pos["lot_size"])
        # Sprint 16.1 — settle with the trade's OWN commission snapshot
        stl = settle(pos, pos["lot_size"], pnl)
        await self.db.forex_positions.update_one(
            {"position_id": position_id},
            {"$set": {
                "status": "closed",
                "close_price": float(close_px),
                "current_price": float(q.mid),
                "pnl_inr": stl["net_pnl"],
                **stl,
                "closed_at": _now(),
                "close_reason": reason,
            }},
        )
        # Refund margin + NET pnl (gross − commission − swap)
        await self.db.forex_balances.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": pos["margin_inr"] + stl["net_pnl"]},
             "$set": {"updated_at": _now()}},
        )
        await self.db.forex_history.insert_one({
            "user_id": user_id, "event": "close",
            "position_id": position_id,
            "symbol_id": pos["symbol_id"], "side": pos["side"],
            "lot_size": pos["lot_size"], "price": close_px,
            "pnl_inr": stl["net_pnl"], **stl, "reason": reason, "ts": _now(),
        })
        return await self.get_position(user_id, position_id)

    async def partial_close(self, user_id: str, position_id: str, fraction: float) -> Dict[str, Any]:
        """Close `fraction` (0..1) of an open position (MT5 partial close).
        Creates a closed child record; the parent keeps the remaining lots."""
        if not (0 < fraction < 1):
            raise ValueError("fraction must be between 0 and 1 (exclusive)")
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos:
            raise ValueError("Position not found")
        if pos["status"] != "open":
            raise ValueError("Position is not open")
        closed_lot = round(pos["lot_size"] * fraction, 2)
        remaining = round(pos["lot_size"] - closed_lot, 2)
        if closed_lot < 0.01:
            raise ValueError("Closed portion is below minimum lot 0.01")
        if remaining < 0.01:
            # Nothing meaningful would remain — full close instead
            return await self.close_position(user_id, position_id, reason="partial_close")
        spec = SYMBOL_INDEX.get(pos["symbol_id"])
        q = await self.feed.get_quote(pos["symbol_id"])
        if not q or not spec:
            raise ValueError("No live price for symbol")
        close_px = q.bid if pos["side"] == "buy" else q.ask
        pnl = self._pnl_inr(pos["side"], pos["entry_price"], close_px,
                            spec["contract_size"], closed_lot)
        stl = settle(pos, closed_lot, pnl)
        margin_released = round(pos["margin_inr"] * closed_lot / pos["lot_size"], 2)
        now = _now()
        child = {
            **{k: v for k, v in pos.items() if k != "_id"},
            "position_id": str(uuid.uuid4()),
            "parent_position_id": position_id,
            "lot_size": closed_lot,
            "margin_inr": margin_released,
            "status": "closed",
            "close_price": float(close_px),
            "current_price": float(q.mid),
            "pnl_inr": stl["net_pnl"],
            **stl,
            "closed_at": now,
            "close_reason": "partial_close",
        }
        await self.db.forex_positions.insert_one(child)
        await self.db.forex_positions.update_one(
            {"position_id": position_id},
            {"$set": {"lot_size": remaining,
                      "margin_inr": round(pos["margin_inr"] - margin_released, 2)}},
        )
        await self.db.forex_balances.update_one(
            {"user_id": user_id},
            {"$inc": {"balance": margin_released + stl["net_pnl"]},
             "$set": {"updated_at": now}},
        )
        await self.db.forex_history.insert_one({
            "user_id": user_id, "event": "partial_close",
            "position_id": position_id, "child_position_id": child["position_id"],
            "symbol_id": pos["symbol_id"], "side": pos["side"],
            "lot_size": closed_lot, "remaining_lot": remaining,
            "price": close_px, "pnl_inr": stl["net_pnl"], **stl, "ts": now,
        })
        return {"closed": _serialize(child),
                "position": await self.get_position(user_id, position_id)}

    async def reverse_position(self, user_id: str, position_id: str) -> Dict[str, Any]:
        """Close at market and immediately open the opposite side, same lots."""
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos or pos["status"] != "open":
            raise ValueError("Position not found or not open")
        closed = await self.close_position(user_id, position_id, reason="reverse")
        new_side = "sell" if pos["side"] == "buy" else "buy"
        opened = await self.open_position(user_id, pos["symbol_id"], new_side,
                                          pos["lot_size"], None, None)
        return {"closed": closed, "opened": opened}

    async def double_position(self, user_id: str, position_id: str) -> Dict[str, Any]:
        """Open an additional market position with the same side & lots."""
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos or pos["status"] != "open":
            raise ValueError("Position not found or not open")
        opened = await self.open_position(user_id, pos["symbol_id"], pos["side"],
                                          pos["lot_size"], pos.get("tp"), pos.get("sl"))
        return {"opened": opened}

    # ---------- pending orders (Sprint 16.1: limit / stop) ----------

    @staticmethod
    def _pending_trigger(order_side: str, order_type: str, price: float, bid: float, ask: float) -> bool:
        if order_side == "buy":
            return ask <= price if order_type == "limit" else ask >= price
        return bid >= price if order_type == "limit" else bid <= price

    async def place_pending(self, user_id: str, symbol_id: str, side: str, order_type: str,
                            price: float, lot_size: float,
                            tp: Optional[float], sl: Optional[float]) -> Dict[str, Any]:
        symbol_id = symbol_id.upper()
        side = side.lower()
        order_type = order_type.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if order_type not in ("limit", "stop"):
            raise ValueError("order type must be limit or stop")
        spec = SYMBOL_INDEX.get(symbol_id)
        if not spec:
            raise ValueError(f"unknown symbol {symbol_id}")
        if lot_size <= 0 or price <= 0:
            raise ValueError("lot_size and price must be > 0")
        q = await self.feed.get_quote(symbol_id)
        if not q:
            raise ValueError("No live price for symbol")
        # MT5 placement validation
        if side == "buy" and order_type == "limit" and price >= q.ask:
            raise ValueError("Buy Limit price must be below the current ask")
        if side == "buy" and order_type == "stop" and price <= q.ask:
            raise ValueError("Buy Stop price must be above the current ask")
        if side == "sell" and order_type == "limit" and price <= q.bid:
            raise ValueError("Sell Limit price must be above the current bid")
        if side == "sell" and order_type == "stop" and price >= q.bid:
            raise ValueError("Sell Stop price must be below the current bid")
        order = {
            "order_id": str(uuid.uuid4()),
            "user_id": user_id,
            "symbol_id": symbol_id,
            "side": side,
            "type": order_type,
            "price": float(price),
            "lot_size": float(lot_size),
            "tp": float(tp) if tp else None,
            "sl": float(sl) if sl else None,
            "status": "pending",
            "position_id": None,
            "ts": _now(),
        }
        await self.db.forex_orders.insert_one(order)
        await self.db.forex_history.insert_one({
            "user_id": user_id, "event": "pending_placed",
            "order_id": order["order_id"], "symbol_id": symbol_id,
            "side": side, "order_type": order_type, "price": price,
            "lot_size": lot_size, "ts": _now(),
        })
        return _serialize(order)

    async def modify_pending(self, user_id: str, order_id: str,
                             price: Optional[float] = None,
                             tp: Optional[float] = None,
                             sl: Optional[float] = None) -> Dict[str, Any]:
        order = await self.db.forex_orders.find_one({"order_id": order_id, "user_id": user_id})
        if not order or order.get("status") != "pending":
            raise ValueError("Pending order not found")
        patch: Dict[str, Any] = {}
        if price is not None:
            if price <= 0:
                raise ValueError("price must be > 0")
            patch["price"] = float(price)
        if tp is not None:
            patch["tp"] = float(tp) if tp else None
        if sl is not None:
            patch["sl"] = float(sl) if sl else None
        if not patch:
            raise ValueError("Nothing to update")
        await self.db.forex_orders.update_one({"order_id": order_id}, {"$set": patch})
        doc = await self.db.forex_orders.find_one({"order_id": order_id})
        return _serialize(doc)

    async def cancel_pending(self, user_id: str, order_id: str) -> Dict[str, Any]:
        order = await self.db.forex_orders.find_one({"order_id": order_id, "user_id": user_id})
        if not order or order.get("status") != "pending":
            raise ValueError("Pending order not found")
        await self.db.forex_orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": "cancelled", "cancel_reason": "user", "cancelled_at": _now()}})
        doc = await self.db.forex_orders.find_one({"order_id": order_id})
        return _serialize(doc)

    async def list_orders(self, user_id: str, status: str = "pending", limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.db.forex_orders.find(
            {"user_id": user_id, "status": status, "archived": {"$ne": True}}
        ).sort("ts", -1).limit(limit)
        return [_serialize(d) async for d in cur]

    async def update_position_tpsl(self, user_id: str, position_id: str,
                                    tp: Optional[float], sl: Optional[float]) -> Dict[str, Any]:
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos:
            raise ValueError("Position not found")
        if pos["status"] != "open":
            raise ValueError("Position is not open")
        patch: Dict[str, Any] = {}
        if tp is not None:
            patch["tp"] = float(tp)
        if sl is not None:
            patch["sl"] = float(sl)
        if not patch:
            raise ValueError("Nothing to update")
        await self.db.forex_positions.update_one(
            {"position_id": position_id},
            {"$set": patch},
        )
        await self.db.forex_history.insert_one({
            "user_id": user_id, "event": "modify",
            "position_id": position_id, "patch": patch, "ts": _now(),
        })
        return await self.get_position(user_id, position_id)

    async def get_position(self, user_id: str, position_id: str) -> Dict[str, Any]:
        pos = await self.db.forex_positions.find_one({"position_id": position_id, "user_id": user_id})
        if not pos:
            raise ValueError("Position not found")
        return await self._enrich(pos)

    async def list_positions(self, user_id: str, status: str = "open", limit: int = 200) -> List[Dict[str, Any]]:
        # Sprint 15.1 — archived positions (pre demo-reset) are hidden but retained.
        cur = self.db.forex_positions.find(
            {"user_id": user_id, "status": status, "archived": {"$ne": True}}
        ).sort("opened_at", -1).limit(limit)
        out: List[Dict[str, Any]] = []
        async for d in cur:
            out.append(await self._enrich(d))
        return out

    async def list_history(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        # Sprint 15.1 — archived history (pre demo-reset) is hidden but retained.
        cur = self.db.forex_history.find(
            {"user_id": user_id, "archived": {"$ne": True}}).sort("ts", -1).limit(limit)
        return [_serialize(d) async for d in cur]

    async def _enrich(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        """Add live price and current P&L for open positions.
        Sprint 14.1.4 — now async; reads from unified ProviderManager cache
        via the shared PriceFeed adapter."""
        out = _serialize(pos)
        if out["status"] == "open":
            q = await self.feed.get_quote(pos["symbol_id"])
            spec = SYMBOL_INDEX.get(pos["symbol_id"])
            if q and spec:
                live_close = q.bid if pos["side"] == "buy" else q.ask
                out["current_price"] = q.mid
                out["pnl_inr"] = round(self._pnl_inr(
                    pos["side"], pos["entry_price"], live_close,
                    spec["contract_size"], pos["lot_size"]), 2)
            # Sprint 16.1 — floating commission estimate + net PnL preview
            est_comm = commission_inr(pos, pos["lot_size"])
            out["est_commission"] = est_comm
            out["est_net_pnl"] = round(out["pnl_inr"] - est_comm, 2)
        return out

    # ---------- mark-to-market loop ----------

    async def _mark_forever(self):
        while not self._stop.is_set():
            try:
                await self._mark_once()
            except Exception as e:  # pragma: no cover
                logger.exception("mark-to-market error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                continue

    async def _mark_once(self):
        """Mark all open positions to market, trigger TP/SL and pending orders."""
        # Sprint 16.1 — pending limit/stop orders trigger from the SAME feed
        pcur = self.db.forex_orders.find({"status": "pending"})
        async for order in pcur:
            q = await self.feed.get_quote(order["symbol_id"])
            if not q:
                continue
            if self._pending_trigger(order["side"], order["type"], order["price"], q.bid, q.ask):
                try:
                    pos = await self.open_position(
                        order["user_id"], order["symbol_id"], order["side"],
                        order["lot_size"], order.get("tp"), order.get("sl"))
                    await self.db.forex_orders.update_one(
                        {"order_id": order["order_id"]},
                        {"$set": {"status": "filled", "position_id": pos["position_id"],
                                  "filled_price": pos["entry_price"], "filled_at": _now()}})
                    await self.db.forex_history.insert_one({
                        "user_id": order["user_id"], "event": "pending_filled",
                        "order_id": order["order_id"], "position_id": pos["position_id"],
                        "symbol_id": order["symbol_id"], "side": order["side"],
                        "order_type": order["type"], "price": pos["entry_price"],
                        "lot_size": order["lot_size"], "ts": _now(),
                    })
                except ValueError as e:
                    await self.db.forex_orders.update_one(
                        {"order_id": order["order_id"]},
                        {"$set": {"status": "rejected", "reject_reason": str(e),
                                  "rejected_at": _now()}})
        cur = self.db.forex_positions.find({"status": "open"})
        async for pos in cur:
            q = await self.feed.get_quote(pos["symbol_id"])
            spec = SYMBOL_INDEX.get(pos["symbol_id"])
            if not q or not spec:
                continue
            mid = q.mid
            live_close = q.bid if pos["side"] == "buy" else q.ask
            pnl = self._pnl_inr(pos["side"], pos["entry_price"], live_close,
                                 spec["contract_size"], pos["lot_size"])
            await self.db.forex_positions.update_one(
                {"position_id": pos["position_id"]},
                {"$set": {"current_price": mid, "pnl_inr": pnl}},
            )
            # TP/SL trigger (compare against mid; close at appropriate side)
            tp, sl = pos.get("tp"), pos.get("sl")
            triggered: Optional[str] = None
            if pos["side"] == "buy":
                if tp and mid >= tp:
                    triggered = "tp"
                elif sl and mid <= sl:
                    triggered = "sl"
            else:  # sell
                if tp and mid <= tp:
                    triggered = "tp"
                elif sl and mid >= sl:
                    triggered = "sl"
            if triggered:
                try:
                    await self.close_position(pos["user_id"], pos["position_id"], reason=triggered)
                except Exception:  # pragma: no cover
                    logger.exception("auto-close failed")
