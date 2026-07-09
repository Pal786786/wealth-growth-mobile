"""Copy-trading engine + broker adapter abstraction — Sprint 7B.1

BrokerAdapter is the interface every execution backend implements. Slice 7B.1
ships PaperBroker (mirrors trades into the app's own paper account) and
placeholder classes for MetaTrader 5 / DXtrade / cTrader / MatchTrader /
CustomBrokerAPI so the future plug-in path is obvious.

The Copy Engine persists ONE document per (follower_user_id, trader_id) with
the follower's settings + status (active | paused | stopped). Actual trade
mirroring is a Slice 7B.2 concern — this file exposes stubs so the routes can
call `start / stop / pause / resume` cleanly today.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Broker adapter interface
# ---------------------------------------------------------------------------
class BrokerAdapter:
    name: str = "base"

    async def open_position(self, user_id: str, symbol: str, side: str,
                            lot: float, sl: Optional[float] = None,
                            tp: Optional[float] = None,
                            source_trade_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    async def close_position(self, user_id: str, position_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": True}


class PaperBroker(BrokerAdapter):
    """Default adapter — mirrors into our own paper forex engine.

    Slice 7B.1 only implements the interface + no-op health. Real mirroring
    routes into backend.forex.engine.open_position() and is enabled in Slice
    7B.2 once we wire the copy-loop.
    """
    name = "paper"

    def __init__(self, forex_engine=None):
        self.forex_engine = forex_engine  # optional injection point

    async def open_position(self, user_id, symbol, side, lot, sl=None, tp=None, source_trade_id=None):
        # 7B.2 will actually call self.forex_engine.open_position(...)
        return {"status": "queued", "symbol": symbol, "side": side, "lot": lot,
                "source_trade_id": source_trade_id, "broker": self.name}

    async def close_position(self, user_id, position_id):
        return {"status": "queued", "position_id": position_id, "broker": self.name}


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


BROKERS: Dict[str, type] = {
    "paper":       PaperBroker,
    "mt5":         MetaTraderAdapter,
    "dxtrade":     DXtradeAdapter,
    "ctrader":     CTraderAdapter,
    "matchtrader": MatchTraderAdapter,
    "custom":      CustomBrokerAdapter,
}


def build_broker(name: str = "paper") -> BrokerAdapter:
    cls = BROKERS.get((name or "paper").lower(), PaperBroker)
    return cls()


# ---------------------------------------------------------------------------
# Copy Engine — persistence of follower → trader relationships + settings
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: Dict[str, Any] = {
    # Exactly one of {fixed_lot, multiplier, equity_percent} should be active;
    # frontend enforces the toggle but backend honours the priority below.
    "mode": "multiplier",                 # 'fixed_lot' | 'multiplier' | 'equity_percent'
    "fixed_lot": 0.10,
    "multiplier": 1.0,
    "equity_percent": 2.0,                # % of follower's equity per source lot
    "max_daily_loss_pct": 5.0,
    "max_drawdown_pct": 15.0,
    "max_open_trades": 5,
    "equity_protection_pct": 30.0,        # halt copy if follower equity drops below (100 - pct)% of start
    "auto_close_on_stop": False,
}
VALID_MODES = {"fixed_lot", "multiplier", "equity_percent"}
STATUSES = {"active", "paused", "stopped"}


class CopyEngine:
    def __init__(self, db, broker: BrokerAdapter):
        self.db = db
        self.broker = broker

    async def get_settings(self, user_id: str, trader_id: str) -> Dict[str, Any]:
        doc = await self.db.copy_relationships.find_one(
            {"user_id": user_id, "trader_id": trader_id}, {"_id": 0}
        )
        if not doc:
            return {"status": "stopped", "settings": {**DEFAULT_SETTINGS}, "started_at": None}
        return doc

    async def start_copy(self, user_id: str, trader_id: str,
                          settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged = {**DEFAULT_SETTINGS, **(settings or {})}
        merged["mode"] = merged.get("mode") if merged.get("mode") in VALID_MODES else "multiplier"
        now = datetime.now(timezone.utc)
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": {
                "user_id": user_id, "trader_id": trader_id,
                "settings": merged, "status": "active",
                "started_at": now, "updated_at": now,
            }},
            upsert=True,
        )
        return await self.get_settings(user_id, trader_id)

    async def update_settings(self, user_id: str, trader_id: str,
                              patch: Dict[str, Any]) -> Dict[str, Any]:
        # Sanitize
        clean: Dict[str, Any] = {}
        for k, v in patch.items():
            if k in DEFAULT_SETTINGS:
                if k == "mode":
                    if v in VALID_MODES:
                        clean[k] = v
                elif isinstance(v, (int, float)):
                    clean[k] = float(v) if isinstance(v, float) or k != "max_open_trades" else int(v)
                elif isinstance(v, bool):
                    clean[k] = v
        if not clean:
            return await self.get_settings(user_id, trader_id)
        set_ops = {f"settings.{k}": v for k, v in clean.items()}
        set_ops["updated_at"] = datetime.now(timezone.utc)
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": set_ops}, upsert=True,
        )
        return await self.get_settings(user_id, trader_id)

    async def set_status(self, user_id: str, trader_id: str, status: str) -> Dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"invalid status {status!r}")
        await self.db.copy_relationships.update_one(
            {"user_id": user_id, "trader_id": trader_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc),
                      "user_id": user_id, "trader_id": trader_id}},
            upsert=True,
        )
        return await self.get_settings(user_id, trader_id)

    async def list_copies(self, user_id: str) -> List[Dict[str, Any]]:
        cur = self.db.copy_relationships.find({"user_id": user_id}, {"_id": 0})
        return [d async for d in cur]
