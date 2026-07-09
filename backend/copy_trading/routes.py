"""Copy Trading routes — Sprint 7B.1

Public: /api/copy_trading/*
Admin:  (Slice 7B.3 will add)
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import traders as tmod
from .engine import CopyEngine, PaperBroker, DEFAULT_SETTINGS, VALID_MODES


_engine: Optional[CopyEngine] = None
_db = None


# Sort key extractors — server-side sorting so pagination is stable
_SORT_KEYS = {
    "total_roi":    lambda t: t["stats"]["total_roi_pct"],
    "monthly_roi":  lambda t: t["stats"]["monthly_roi_pct"],
    "win_rate":     lambda t: t["stats"]["win_rate_pct"],
    "followers":    lambda t: t["stats"]["followers"],
    "risk":         lambda t: -t["risk"]["risk_score"],  # LOWER risk first
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
    auto_close_on_stop: Optional[bool] = None


class StartCopyIn(BaseModel):
    settings: Optional[CopySettingsIn] = None


def attach(app, db, get_current_user):
    global _engine, _db
    _db = db
    _engine = CopyEngine(db=db, broker=PaperBroker())

    r = APIRouter(prefix="/api/copy_trading", tags=["copy-trading"])

    # ----------------- Leaderboard -----------------
    @r.get("/traders")
    async def leaderboard(
        sort: str = Query("total_roi", description="total_roi|monthly_roi|win_rate|followers|risk|new"),
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

    # ----------------- Copy relationship -----------------
    @r.get("/my/copies")
    async def my_copies(user=Depends(get_current_user)):
        rels = await _engine.list_copies(user["user_id"])
        # Enrich each with trader summary for UI
        for rel in rels:
            t = tmod.get_trader(rel["trader_id"])
            rel["trader"] = t
        return {"copies": rels}

    @r.get("/traders/{trader_id}/copy")
    async def get_copy_relationship(trader_id: str, user=Depends(get_current_user)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        return await _engine.get_settings(user["user_id"], trader_id)

    @r.post("/traders/{trader_id}/copy/start")
    async def start_copy(trader_id: str, body: Optional[StartCopyIn] = None, user=Depends(get_current_user)):
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
        return await _engine.set_status(user["user_id"], trader_id, "active")

    @r.post("/traders/{trader_id}/copy/stop")
    async def stop_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "stopped")

    @r.put("/traders/{trader_id}/copy/settings")
    async def update_settings(trader_id: str, body: CopySettingsIn, user=Depends(get_current_user)):
        if not tmod.get_trader(trader_id):
            raise HTTPException(404, "Trader not found")
        patch = body.model_dump(exclude_none=True)
        return await _engine.update_settings(user["user_id"], trader_id, patch)

    # ----------------- Meta / diagnostics -----------------
    @r.get("/meta")
    async def meta():
        return {
            "trader_count": len(tmod.list_trader_ids()),
            "sort_keys": list(_SORT_KEYS.keys()),
            "default_settings": DEFAULT_SETTINGS,
            "modes": sorted(VALID_MODES),
            "broker": _engine.broker.name if _engine else None,
        }

    app.include_router(r)
    return r
