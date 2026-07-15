"""Copy Trading — Broker Adapter abstraction (Sprint 7B.2)

Every execution backend (paper today; MT5 / DXtrade / cTrader / MatchTrader /
custom broker APIs tomorrow) implements the same 3-method interface:

    open_position(user_id, symbol, side, lot, sl, tp, source_trade_id) -> dict
    close_position(user_id, follower_trade_id, exit_price) -> dict
    health() -> dict

The Copy Engine (engine.py) is broker-agnostic. This isolation is critical:
switching to a real MT5 gateway is done by swapping the adapter registered
in the module bootstrap.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BrokerAdapter:
    name: str = "base"

    async def open_position(self, user_id: str, symbol: str, side: str,
                            lot: float, entry_price: float,
                            sl: Optional[float] = None,
                            tp: Optional[float] = None,
                            source_trade_id: Optional[str] = None,
                            trader_id: Optional[str] = None,
                            copy_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    async def close_position(self, user_id: str, follower_trade_id: str,
                             exit_price: float, reason: str = "master_close") -> Dict[str, Any]:
        raise NotImplementedError

    async def close_all(self, user_id: str, trader_id: Optional[str] = None,
                        reason: str = "user_stop") -> int:
        raise NotImplementedError

    async def open_positions(self, user_id: str, trader_id: Optional[str] = None) -> list:
        raise NotImplementedError

    async def health(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": True}


class PaperBroker(BrokerAdapter):
    """Default broker — persists follower trades directly in mongo.

    This is a self-contained paper execution: we don't route through the
    live Forex engine (whose symbols are a strict subset of the master
    trader symbols). Instead we mark-to-market against the master's exit
    price, which is what a reasonable copy platform does for demo/paper.
    """
    name = "paper"

    _COLLECTION = "copy_follower_trades"

    def __init__(self, db):
        self.db = db

    async def open_position(self, user_id, symbol, side, lot, entry_price,
                            sl=None, tp=None, source_trade_id=None,
                            trader_id=None, copy_id=None) -> Dict[str, Any]:
        # Sprint 16.1 — identical commission engine as demo trading:
        # snapshot settings at open so later admin changes never affect this trade.
        from forex.costs import snapshot_for_trade
        cfg = await self.db.forex_settings.find_one({"_id": "active"}) or {}
        trade = {
            "follower_trade_id": f"ct_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "trader_id": trader_id,
            "copy_id": copy_id,
            "master_id": source_trade_id,
            "symbol": symbol,
            "side": side,
            "lot_size": float(lot),
            "entry_price": float(entry_price),
            "sl": float(sl) if sl else None,
            "tp": float(tp) if tp else None,
            "opened_at": _now(),
            "closed_at": None,
            "exit_price": None,
            "pnl_usd": 0.0,
            "pnl_pct": 0.0,
            "status": "open",
            "broker": self.name,
            **snapshot_for_trade(cfg),
        }
        await self.db[self._COLLECTION].insert_one(trade)
        trade.pop("_id", None)
        return trade

    async def close_position(self, user_id, follower_trade_id, exit_price,
                             reason="master_close") -> Dict[str, Any]:
        doc = await self.db[self._COLLECTION].find_one(
            {"follower_trade_id": follower_trade_id, "user_id": user_id})
        if not doc or doc.get("status") != "open":
            return {}
        side = doc["side"]
        entry = float(doc["entry_price"])
        lot = float(doc["lot_size"])
        pnl_pct = ((exit_price - entry) / entry) * (1 if side == "buy" else -1) * 100.0
        # Simplified $ P&L per lot at 100k contract for FX-ish. For non-FX we
        # approximate at $1 per pip-equivalent * lot. Good enough for paper.
        pnl_usd = round(pnl_pct * lot * 10, 2)  # 0.1% * 1 lot = $1  (paper scale)
        # Sprint 16.1 — settle with the SAME commission engine (USD conversion)
        from forex.costs import commission_inr
        from forex.symbols import USD_INR
        commission_amount_inr = commission_inr(doc, lot)
        commission_usd = round(commission_amount_inr / USD_INR, 2)
        net_pnl_usd = round(pnl_usd - commission_usd, 2)
        await self.db[self._COLLECTION].update_one(
            {"follower_trade_id": follower_trade_id},
            {"$set": {
                "status": "closed",
                "closed_at": _now(),
                "exit_price": float(exit_price),
                "pnl_pct": round(pnl_pct, 3),
                "pnl_usd": pnl_usd,
                "gross_pnl": pnl_usd,
                "commission_amount": commission_usd,
                "commission_amount_inr": commission_amount_inr,
                "swap_amount": 0.0,
                "net_pnl": net_pnl_usd,
                "close_reason": reason,
            }},
        )
        doc = await self.db[self._COLLECTION].find_one(
            {"follower_trade_id": follower_trade_id}, {"_id": 0})
        return doc or {}

    async def close_all(self, user_id, trader_id=None, reason="user_stop") -> int:
        q: Dict[str, Any] = {"user_id": user_id, "status": "open"}
        if trader_id:
            q["trader_id"] = trader_id
        cur = self.db[self._COLLECTION].find(q, {"_id": 0})
        docs = [d async for d in cur]
        count = 0
        for d in docs:
            # Close at entry price (mark-to-market unavailable here → flat close)
            await self.close_position(user_id, d["follower_trade_id"], d["entry_price"], reason=reason)
            count += 1
        return count

    async def open_positions(self, user_id, trader_id=None):
        q: Dict[str, Any] = {"user_id": user_id, "status": "open"}
        if trader_id:
            q["trader_id"] = trader_id
        cur = self.db[self._COLLECTION].find(q, {"_id": 0}).sort("opened_at", -1)
        return [d async for d in cur]


# Placeholder future adapters — same interface, real network calls added later.
class MetaTraderAdapter(BrokerAdapter):
    name = "mt5"


class DXtradeAdapter(BrokerAdapter):
    name = "dxtrade"


class CTraderAdapter(BrokerAdapter):
    name = "ctrader"


class MatchTraderAdapter(BrokerAdapter):
    name = "matchtrader"


class CustomBrokerAdapter(BrokerAdapter):
    name = "custom"


BROKERS = {
    "paper":       PaperBroker,
    "mt5":         MetaTraderAdapter,
    "dxtrade":     DXtradeAdapter,
    "ctrader":     CTraderAdapter,
    "matchtrader": MatchTraderAdapter,
    "custom":      CustomBrokerAdapter,
}


def build_broker(name: str, db) -> BrokerAdapter:
    cls = BROKERS.get((name or "paper").lower(), PaperBroker)
    try:
        return cls(db)  # type: ignore[call-arg]
    except TypeError:
        return cls()
