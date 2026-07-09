"""Forex public + admin routes."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .engine import TradingEngine, DEFAULT_DEMO_BALANCE, DEFAULT_MARGIN_PER_LOT
from .feed import PriceFeed
from .symbols import SYMBOLS, SYMBOL_INDEX, USD_INR

logger = logging.getLogger("forex.routes")

# Globals set by attach()
_db = None
_engine: Optional[TradingEngine] = None
_feed: Optional[PriceFeed] = None
_get_current_user = None
_get_current_admin = None
_log_action = None


class OpenPositionRequest(BaseModel):
    symbol_id: str
    side: str = Field(..., pattern="^(buy|sell)$")
    lot_size: float = Field(..., gt=0)
    tp: Optional[float] = Field(None, gt=0)
    sl: Optional[float] = Field(None, gt=0)


class UpdateTPSLRequest(BaseModel):
    tp: Optional[float] = Field(None, gt=0)
    sl: Optional[float] = Field(None, gt=0)


class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    demo_mode: Optional[bool] = None
    live_mode: Optional[bool] = None  # admin switch (uses Twelve Data when on)
    twelve_data_api_key: Optional[str] = None
    default_demo_balance: Optional[float] = Field(None, ge=10000)
    margin_per_lot: Optional[float] = Field(None, ge=10)
    min_lot: Optional[float] = Field(None, gt=0)
    max_lot: Optional[float] = Field(None, gt=0)
    symbols: Optional[Dict[str, Dict[str, Any]]] = None


def _settings_doc_default() -> Dict[str, Any]:
    return {
        "_id": "active",
        "enabled": True,
        "demo_mode": True,
        "live_mode": False,
        "twelve_data_api_key": "",
        "default_demo_balance": DEFAULT_DEMO_BALANCE,
        "margin_per_lot": DEFAULT_MARGIN_PER_LOT,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "usd_inr": USD_INR,
        "symbols": {s["id"]: {
            "enabled": True,
            "spread_pips": s["spread_pips"],
            "min_lot": 0.01,
            "max_lot": 100.0,
        } for s in SYMBOLS},
    }


async def seed_settings(db):
    cur = await db.forex_settings.find_one({"_id": "active"})
    if not cur:
        await db.forex_settings.insert_one(_settings_doc_default())


async def get_feed_and_engine():
    return _feed, _engine


def attach(api: APIRouter, db, feed: PriceFeed, engine: TradingEngine,
           get_current_user_fn, get_current_admin_fn, log_action_fn):
    """Wire routes into FastAPI app."""
    global _db, _engine, _feed, _get_current_user, _get_current_admin, _log_action
    _db = db
    _engine = engine
    _feed = feed
    _get_current_user = get_current_user_fn
    _get_current_admin = get_current_admin_fn
    _log_action = log_action_fn

    public = APIRouter(prefix="/forex", tags=["forex"])
    admin = APIRouter(prefix="/admin/forex", tags=["forex-admin"])

    # ---------- public ----------
    @public.get("/symbols")
    async def list_symbols():
        cfg = await db.forex_settings.find_one({"_id": "active"}) or _settings_doc_default()
        sym_cfg = cfg.get("symbols") or {}
        out = []
        for spec in SYMBOLS:
            sc = sym_cfg.get(spec["id"], {})
            out.append({
                "id": spec["id"],
                "display": spec["display"],
                "name": spec["name"],
                "asset_class": spec["asset_class"],
                "pip_size": spec["pip_size"],
                "contract_size": spec["contract_size"],
                "price_decimals": spec["price_decimals"],
                "enabled": sc.get("enabled", True),
                "spread_pips": sc.get("spread_pips", spec["spread_pips"]),
                "min_lot": sc.get("min_lot", cfg.get("min_lot", 0.01)),
                "max_lot": sc.get("max_lot", cfg.get("max_lot", 100.0)),
            })
        return {
            "enabled": cfg.get("enabled", True),
            "demo_mode": cfg.get("demo_mode", True),
            "live_mode": cfg.get("live_mode", False),
            "margin_per_lot": cfg.get("margin_per_lot", DEFAULT_MARGIN_PER_LOT),
            "usd_inr": cfg.get("usd_inr", USD_INR),
            "symbols": out,
        }

    @public.get("/prices")
    async def get_prices():
        feed = _feed
        if not feed:
            raise HTTPException(503, "feed not running")
        out = []
        for spec in SYMBOLS:
            q = feed.get_quote(spec["id"])
            if not q:
                continue
            out.append({**q.to_dict(), "display": spec["display"], "price_decimals": spec["price_decimals"]})
        return {"prices": out, "ts_now": _now_iso(), "diagnostics": feed.diagnostics()}

    @public.get("/candles/{symbol_id}")
    async def get_candles(symbol_id: str, limit: int = 100):
        """Return recent (ts, mid) points from our simulated feed so the mobile
        chart is guaranteed to match the watchlist + order screen prices."""
        feed = _feed
        if not feed:
            raise HTTPException(503, "feed not running")
        sym_id = symbol_id.upper()
        if sym_id not in SYMBOL_INDEX:
            raise HTTPException(404, "unknown symbol")
        pts = feed.get_history(sym_id, limit=min(max(limit, 10), 300))
        return {
            "symbol_id": sym_id,
            "points": pts,
            "price_decimals": SYMBOL_INDEX[sym_id]["price_decimals"],
        }

    @public.get("/balance")
    async def get_balance(user=Depends(_get_current_user)):
        bal = await _engine.get_or_init_balance(user["user_id"])
        return {"balance": bal["balance"], "currency": bal["currency"]}

    @public.get("/equity")
    async def get_equity(user=Depends(_get_current_user)):
        """Real-time account state: balance + floating P&L (marked-to-market
        using our simulated feed). Same data source as /prices and /candles,
        so equity/P&L is guaranteed consistent with what the chart shows."""
        bal = await _engine.get_or_init_balance(user["user_id"])
        open_positions = await _engine.list_positions(user["user_id"], status="open", limit=500)
        unrealized = sum(float(p.get("pnl_inr") or 0) for p in open_positions)
        margin_used = sum(float(p.get("margin_inr") or 0) for p in open_positions)
        balance = float(bal["balance"])
        equity = balance + unrealized
        return {
            "balance": balance,
            "unrealized_pnl": round(unrealized, 2),
            "equity": round(equity, 2),
            "margin_used": round(margin_used, 2),
            "free_margin": round(max(equity - margin_used, 0.0), 2),
            "open_position_count": len(open_positions),
            "currency": bal["currency"],
        }

    @public.post("/balance/reset")
    async def reset_balance(user=Depends(_get_current_user)):
        bal = await _engine.reset_balance(user["user_id"])
        return {"balance": bal["balance"], "currency": bal["currency"]}

    @public.post("/positions")
    async def open_position(req: OpenPositionRequest, user=Depends(_get_current_user)):
        # KYC gate removed — Forex trading works without KYC per business flow.
        # KYC is only required at Withdrawal.
        try:
            return await _engine.open_position(user["user_id"], req.symbol_id, req.side,
                                                req.lot_size, req.tp, req.sl)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @public.get("/positions")
    async def list_positions(status: str = "open", user=Depends(_get_current_user)):
        if status not in ("open", "closed", "cancelled"):
            raise HTTPException(400, "status must be open|closed|cancelled")
        return await _engine.list_positions(user["user_id"], status=status)

    @public.get("/positions/{position_id}")
    async def get_position(position_id: str, user=Depends(_get_current_user)):
        try:
            return await _engine.get_position(user["user_id"], position_id)
        except ValueError as e:
            raise HTTPException(404, str(e))

    @public.post("/positions/{position_id}/close")
    async def close_position(position_id: str, user=Depends(_get_current_user)):
        try:
            return await _engine.close_position(user["user_id"], position_id, reason="manual")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @public.put("/positions/{position_id}")
    async def update_position(position_id: str, req: UpdateTPSLRequest, user=Depends(_get_current_user)):
        try:
            return await _engine.update_position_tpsl(user["user_id"], position_id, req.tp, req.sl)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @public.get("/history")
    async def history(limit: int = 100, user=Depends(_get_current_user)):
        return await _engine.list_history(user["user_id"], limit=min(max(limit, 1), 500))

    # ---------- admin ----------
    @admin.get("/settings")
    async def get_settings(admin_user=Depends(_get_current_admin)):
        cfg = await db.forex_settings.find_one({"_id": "active"})
        if not cfg:
            cfg = _settings_doc_default()
            await db.forex_settings.insert_one(cfg)
        cfg = {k: v for k, v in cfg.items() if k != "_id"}
        # Mask API key in response
        if cfg.get("twelve_data_api_key"):
            k = cfg["twelve_data_api_key"]
            cfg["twelve_data_api_key_masked"] = f"{k[:4]}\u2026{k[-2:]}" if len(k) > 6 else "set"
            cfg["twelve_data_api_key"] = ""  # never expose
        cfg["diagnostics"] = _feed.diagnostics() if _feed else {}
        return cfg

    @admin.put("/settings")
    async def update_settings(req: SettingsUpdate, admin_user=Depends(_get_current_admin)):
        patch = req.dict(exclude_unset=True)
        if "min_lot" in patch and "max_lot" in patch and patch["min_lot"] >= patch["max_lot"]:
            raise HTTPException(400, "min_lot must be less than max_lot")
        if not patch:
            raise HTTPException(400, "Nothing to update")
        await db.forex_settings.update_one({"_id": "active"}, {"$set": patch}, upsert=True)
        cfg = await db.forex_settings.find_one({"_id": "active"})
        # Apply live_mode change to feed immediately
        if "live_mode" in patch or "twelve_data_api_key" in patch:
            key = cfg.get("twelve_data_api_key") or ""
            _feed.set_live_mode(bool(cfg.get("live_mode")), td_api_key=key)
        try:
            await _log_action(admin_user["admin_id"], "forex_settings_update", {"keys": list(patch.keys())})
        except Exception:  # pragma: no cover
            pass
        return {"ok": True}

    @admin.get("/positions")
    async def admin_list_positions(status: str = "open", limit: int = 200,
                                   admin_user=Depends(_get_current_admin)):
        if status not in ("open", "closed", "cancelled"):
            raise HTTPException(400, "status must be open|closed|cancelled")
        cur = db.forex_positions.find({"status": status}).sort("opened_at", -1).limit(min(max(limit, 1), 500))
        out = []
        async for d in cur:
            doc = {k: v for k, v in d.items() if k != "_id"}
            for k, v in list(doc.items()):
                if hasattr(v, "isoformat"):
                    doc[k] = v.isoformat()
            out.append(doc)
        return out

    @admin.get("/stats")
    async def admin_stats(admin_user=Depends(_get_current_admin)):
        users = await db.forex_balances.count_documents({})
        open_pos = await db.forex_positions.count_documents({"status": "open"})
        closed_pos = await db.forex_positions.count_documents({"status": "closed"})
        cur = db.forex_positions.aggregate([
            {"$match": {"status": "closed"}},
            {"$group": {"_id": None, "total_pnl": {"$sum": "$pnl_inr"}, "n": {"$sum": 1}}},
        ])
        agg = await cur.to_list(length=1)
        return {
            "active_traders": users,
            "open_positions": open_pos,
            "closed_positions": closed_pos,
            "total_realized_pnl_inr": (agg[0]["total_pnl"] if agg else 0.0),
            "feed_diagnostics": _feed.diagnostics() if _feed else {},
        }

    api.include_router(public)
    api.include_router(admin)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
