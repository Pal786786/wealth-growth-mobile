"""Copy Trading routes — Sprint 7B.2 (extends 7B.1)

Public:
  Leaderboard/profile     — /api/copy_trading/traders[...]
  My relationships        — /api/copy_trading/my/copies + traders/{id}/copy/*
  Copy execution history  — /api/copy_trading/my/trades, /my/summary
  Bulk actions            — /api/copy_trading/my/copies/pause-all|resume-all|close-all

Admin:
  Simulation control      — /api/copy_trading/admin/simulation/*
  Config defaults         — /api/copy_trading/admin/config
  Master trades listing   — /api/copy_trading/admin/master-trades
"""
from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import traders as tmod
from .engine import CopyEngine
from .config import DEFAULT_SETTINGS, VALID_MODES

_engine: Optional[CopyEngine] = None
_simulator = None


_SORT_KEYS = {
    "total_roi":    lambda t: t["stats"]["total_roi_pct"],
    "monthly_roi":  lambda t: t["stats"]["monthly_roi_pct"],
    "win_rate":     lambda t: t["stats"]["win_rate_pct"],
    "followers":    lambda t: t["stats"]["followers"],
    "risk":         lambda t: -t["risk"]["risk_score"],
    "new":          lambda t: -t["joined_days_ago"],
}


class CopySettingsIn(BaseModel):
    mode: Optional[str] = None
    fixed_lot: Optional[float] = None
    multiplier: Optional[float] = None
    equity_percent: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_open_trades: Optional[int] = None
    equity_protection_pct: Optional[float] = None
    auto_close_on_equity_protection: Optional[bool] = None
    auto_pause_on_daily_loss: Optional[bool] = None
    resume_mode: Optional[str] = None
    max_lot_size: Optional[float] = None
    min_lot_size: Optional[float] = None
    slippage_pips: Optional[float] = None
    auto_copy_new_trades: Optional[bool] = None
    copy_existing_open_trades: Optional[bool] = None


class StartCopyIn(BaseModel):
    settings: Optional[CopySettingsIn] = None


class SimSpeedIn(BaseModel):
    speed: str   # slow | normal | fast


class SimForceOpenIn(BaseModel):
    trader_id: str
    side: Optional[str] = None       # buy | sell (random if omitted)
    symbol: Optional[str] = None


class AdminConfigIn(BaseModel):
    defaults: Optional[CopySettingsIn] = None


def attach(app, db, get_current_user, engine: CopyEngine, simulator, get_current_admin=None):
    global _engine, _simulator
    _engine = engine
    _simulator = simulator

    r = APIRouter(prefix="/api/copy_trading", tags=["copy-trading"])

    # ----------------- Leaderboard -----------------
    @r.get("/traders")
    async def leaderboard(
        sort: str = Query("total_roi"),
        search: Optional[str] = None,
        min_risk: int = Query(1, ge=1, le=10),
        max_risk: int = Query(10, ge=1, le=10),
        verified_only: bool = False,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=50),
    ):
        items = tmod.list_traders()
        if search:
            q = search.lower().strip()
            items = [t for t in items if q in t["name"].lower() or q in t["country_name"].lower() or q in t["style"].lower()]
        items = [t for t in items if min_risk <= t["risk"]["risk_score"] <= max_risk]
        if verified_only:
            items = [t for t in items if t["verified"]]
        keyfn = _SORT_KEYS.get(sort, _SORT_KEYS["total_roi"])
        items.sort(key=keyfn, reverse=True)
        total = len(items)
        start = (page - 1) * limit
        return {
            "items": items[start:start + limit],
            "page": page, "limit": limit, "total": total,
            "has_more": start + limit < total,
        }

    @r.get("/traders/{trader_id}")
    async def trader_profile(trader_id: str):
        t = tmod.get_trader(trader_id, include_curve=True)
        if not t:
            raise HTTPException(404, "Trader not found")
        return t

    @r.get("/traders/{trader_id}/open-trades")
    async def trader_open(trader_id: str):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        return {"trades": tmod.open_trades(trader_id)}

    @r.get("/traders/{trader_id}/closed-trades")
    async def trader_closed(trader_id: str, limit: int = Query(40, ge=5, le=200)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        return {"trades": tmod.closed_trades(trader_id, limit=limit)}

    # ----------------- Live master trade feed (for demo transparency) -----------------
    @r.get("/traders/{trader_id}/master-trades")
    async def trader_master_trades(trader_id: str, limit: int = Query(50, ge=1, le=200)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        rows = await _simulator.recent_master_trades(trader_id=trader_id, limit=limit)
        return {"trades": rows}

    # ----------------- Copy relationship -----------------
    @r.get("/my/copies")
    async def my_copies(user=Depends(get_current_user)):
        copies = await _engine.my_copies_enriched(user["user_id"], tmod.get_trader)
        return {"copies": copies}

    @r.get("/my/summary")
    async def my_summary(user=Depends(get_current_user)):
        return await _engine.my_summary(user["user_id"])

    @r.get("/my/trades")
    async def my_trades(
        trader_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
        user=Depends(get_current_user),
    ):
        rows = await _engine.follower_trades(
            user["user_id"], trader_id=trader_id, status=status, limit=limit)
        return {"trades": rows}

    @r.post("/my/copies/pause-all")
    async def pause_all(user=Depends(get_current_user)):
        n = await _engine.pause_all(user["user_id"])
        return {"paused": n}

    @r.post("/my/copies/resume-all")
    async def resume_all(user=Depends(get_current_user)):
        n = await _engine.resume_all(user["user_id"])
        return {"resumed": n}

    @r.post("/my/copies/close-all")
    async def close_all(user=Depends(get_current_user)):
        n = await _engine.close_all(user["user_id"])
        return {"closed": n}

    @r.get("/traders/{trader_id}/copy")
    async def get_copy_relationship(trader_id: str, user=Depends(get_current_user)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        return await _engine.get_settings(user["user_id"], trader_id)

    @r.post("/traders/{trader_id}/copy/start")
    async def start_copy(trader_id: str, body: Optional[StartCopyIn] = None,
                         user=Depends(get_current_user)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        settings = None
        if body and body.settings:
            settings = body.settings.model_dump(exclude_none=True)
        return await _engine.start_copy(user["user_id"], trader_id, settings)

    @r.post("/traders/{trader_id}/copy/pause")
    async def pause_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "paused")

    @r.post("/traders/{trader_id}/copy/resume")
    async def resume_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "active",
                                        halt_reason=None)

    @r.post("/traders/{trader_id}/copy/stop")
    async def stop_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "stopped",
                                        close_open_trades=True)

    @r.put("/traders/{trader_id}/copy/settings")
    async def update_settings(trader_id: str, body: CopySettingsIn,
                              user=Depends(get_current_user)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        patch = body.model_dump(exclude_none=True)
        return await _engine.update_settings(user["user_id"], trader_id, patch)

    # ----------------- Meta / diagnostics -----------------
    @r.get("/meta")
    async def meta():
        defaults = await _engine.config.defaults()
        sim = await _engine.config.sim_state()
        return {
            "trader_count": len(tmod.list_trader_ids()),
            "sort_keys": list(_SORT_KEYS.keys()),
            "default_settings": defaults,
            "modes": sorted(VALID_MODES),
            "broker": _engine.broker.name if _engine else None,
            "simulator": {"enabled": sim.get("enabled"), "speed": sim.get("speed")},
        }

    # ----------------- Admin: simulation control -----------------
    if get_current_admin is not None:
        @r.get("/admin/simulation/status")
        async def sim_status(admin=Depends(get_current_admin)):
            return await _simulator.status()

        @r.post("/admin/simulation/pause")
        async def sim_pause(admin=Depends(get_current_admin)):
            await _simulator.pause()
            return await _simulator.status()

        @r.post("/admin/simulation/resume")
        async def sim_resume(admin=Depends(get_current_admin)):
            await _simulator.resume()
            return await _simulator.status()

        @r.post("/admin/simulation/speed")
        async def sim_speed(body: SimSpeedIn, admin=Depends(get_current_admin)):
            if body.speed not in ("slow", "normal", "fast"):
                raise HTTPException(400, "speed must be slow|normal|fast")
            await _simulator.set_speed(body.speed)
            return await _simulator.status()

        @r.post("/admin/simulation/force-open")
        async def sim_force_open(body: SimForceOpenIn, admin=Depends(get_current_admin)):
            trade = await _simulator.force_open(body.trader_id, side=body.side, symbol=body.symbol)
            return {"master_trade": trade}

        @r.post("/admin/simulation/force-close/{master_id}")
        async def sim_force_close(master_id: str, admin=Depends(get_current_admin)):
            return await _simulator.force_close(master_id)

        @r.get("/admin/master-trades")
        async def admin_master_trades(limit: int = Query(100, ge=1, le=500),
                                       admin=Depends(get_current_admin)):
            rows = await _simulator.recent_master_trades(limit=limit)
            return {"trades": rows}

        @r.get("/admin/config")
        async def get_admin_config(admin=Depends(get_current_admin)):
            defaults = await _engine.config.defaults()
            sim = await _engine.config.sim_state()
            return {"defaults": defaults, "sim": sim}

        @r.put("/admin/config/defaults")
        async def set_admin_defaults(body: CopySettingsIn,
                                      admin=Depends(get_current_admin)):
            patch = body.model_dump(exclude_none=True)
            merged = await _engine.config.update_defaults(patch)
            return {"defaults": merged}

    app.include_router(r)
    return r
