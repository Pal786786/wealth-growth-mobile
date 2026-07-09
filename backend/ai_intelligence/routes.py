"""AI Intelligence — Routes (Sprint 7C.1)

Public endpoints (auth required unless noted):
  Signals:
    GET  /api/ai/signals[?timeframe&asset_class&min_confidence&side&limit]
    GET  /api/ai/signals/{symbol}[?timeframe]           — detailed signal + indicators + AI explanation
    GET  /api/ai/indicators/{symbol}[?timeframe]        — TA breakdown only
  Watchlist:
    GET  /api/ai/watchlist                              — enriched
    POST /api/ai/watchlist  {symbol}
    DELETE /api/ai/watchlist/{symbol}
  Alerts:
    GET    /api/ai/alerts[?status]
    POST   /api/ai/alerts
    DELETE /api/ai/alerts/{alert_id}
    POST   /api/ai/alerts/{alert_id}/pause
    POST   /api/ai/alerts/{alert_id}/resume
  Meta:
    GET  /api/ai/meta                                    — timeframes, asset classes, alert types
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import signal_engine, feed, ta_engine, watchlist_engine, ai_engine
from .alerts_engine import AlertsEngine, VALID_TYPES

_alerts: Optional[AlertsEngine] = None


class WatchlistAddIn(BaseModel):
    symbol: str


class AlertIn(BaseModel):
    type: str
    symbol: str
    target_price: Optional[float] = None
    target_percent: Optional[float] = None
    anchor_price: Optional[float] = None
    direction: Optional[str] = None
    fast_ema: Optional[int] = None
    slow_ema: Optional[int] = None
    threshold: Optional[float] = None
    timeframe: Optional[str] = None
    repeat: Optional[bool] = None
    note: Optional[str] = None


def attach(app, db, get_current_user, alerts: AlertsEngine, get_current_admin=None):
    global _alerts
    _alerts = alerts
    r = APIRouter(prefix="/api/ai", tags=["ai-intelligence"])

    # ---------------- META ----------------
    @r.get("/meta")
    async def meta():
        return {
            "timeframes": list(feed.TF_SECONDS.keys()),
            "default_timeframe": feed.DEFAULT_TF,
            "asset_classes": ["forex", "metals", "indices", "crypto", "commodities", "energies"],
            "alert_types": sorted(VALID_TYPES),
            "universe": signal_engine.DEFAULT_UNIVERSE,
            "signal_expiry_bars": signal_engine.EXPIRY_BARS,
            "eval_interval_sec": _alerts.interval_sec if _alerts else 30,
        }

    # ---------------- SIGNALS ----------------
    @r.get("/signals")
    async def list_signals(
        timeframe: str = Query("H1"),
        asset_class: Optional[str] = None,
        min_confidence: int = Query(0, ge=0, le=100),
        side: Optional[str] = Query(None, regex="^(buy|sell|hold)?$"),
        limit: int = Query(30, ge=1, le=60),
    ):
        rows = signal_engine.list_signals(
            timeframe=timeframe, asset_class=asset_class,
            min_confidence=min_confidence, side=side, limit=limit)
        return {"signals": rows, "count": len(rows), "timeframe": timeframe}

    @r.get("/signals/{symbol}")
    async def signal_detail(symbol: str, timeframe: str = Query("H1"),
                            with_ai: bool = Query(True)):
        sig = signal_engine.signal_for(symbol, timeframe=timeframe)
        if not sig:
            raise HTTPException(404, f"Unknown or unsupported symbol: {symbol}")
        if with_ai:
            sig["ai_explanation"] = await ai_engine.explanation_for(db, sig)
        return sig

    @r.get("/indicators/{symbol}")
    async def indicators(symbol: str, timeframe: str = Query("H1")):
        candles = feed.get_candles(symbol, timeframe, count=250)
        if not candles:
            raise HTTPException(404, "unknown symbol")
        ind = ta_engine.compute(candles)
        return {
            "symbol": symbol.upper(), "timeframe": timeframe,
            "indicators": ind,
            "summary": ta_engine.summarise(ind),
        }

    @r.get("/candles/{symbol}")
    async def candles(symbol: str, timeframe: str = Query("H1"),
                       count: int = Query(120, ge=20, le=500)):
        rows = feed.get_candles(symbol, timeframe, count=count)
        if not rows:
            raise HTTPException(404, "unknown symbol")
        return {"symbol": symbol.upper(), "timeframe": timeframe, "candles": rows}

    # ---------------- WATCHLIST ----------------
    @r.get("/watchlist")
    async def get_watchlist(user=Depends(get_current_user)):
        rows = await watchlist_engine.enriched_watchlist(db, user["user_id"])
        return {"items": rows}

    @r.post("/watchlist")
    async def add_watchlist(body: WatchlistAddIn, user=Depends(get_current_user)):
        try:
            item = await watchlist_engine.add(db, user["user_id"], body.symbol)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"item": item, "enriched": watchlist_engine.enrich(body.symbol)}

    @r.delete("/watchlist/{symbol}")
    async def remove_watchlist(symbol: str, user=Depends(get_current_user)):
        ok = await watchlist_engine.remove(db, user["user_id"], symbol)
        return {"removed": ok}

    # ---------------- ALERTS ----------------
    @r.get("/alerts")
    async def list_alerts(status: Optional[str] = None, user=Depends(get_current_user)):
        rows = await _alerts.list(user["user_id"], status=status)
        return {"alerts": rows, "count": len(rows)}

    @r.post("/alerts")
    async def create_alert(body: AlertIn, user=Depends(get_current_user)):
        try:
            row = await _alerts.create(user["user_id"], body.model_dump(exclude_none=True))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
        return {"alert": row}

    @r.delete("/alerts/{alert_id}")
    async def delete_alert(alert_id: str, user=Depends(get_current_user)):
        ok = await _alerts.delete(user["user_id"], alert_id)
        if not ok:
            raise HTTPException(404, "alert not found")
        return {"deleted": True}

    @r.post("/alerts/{alert_id}/pause")
    async def pause_alert(alert_id: str, user=Depends(get_current_user)):
        row = await _alerts.toggle(user["user_id"], alert_id, active=False)
        if not row:
            raise HTTPException(404, "alert not found")
        return {"alert": row}

    @r.post("/alerts/{alert_id}/resume")
    async def resume_alert(alert_id: str, user=Depends(get_current_user)):
        row = await _alerts.toggle(user["user_id"], alert_id, active=True)
        if not row:
            raise HTTPException(404, "alert not found")
        return {"alert": row}

    # ---------------- ADMIN (config-only in 7C.1; full console in 7C.2) ----------------
    if get_current_admin is not None:
        @r.get("/admin/alerts/config")
        async def alerts_config(admin=Depends(get_current_admin)):
            return {"eval_interval_sec": _alerts.interval_sec}

        @r.put("/admin/alerts/config")
        async def set_alerts_config(payload: Dict[str, Any], admin=Depends(get_current_admin)):
            n = int(payload.get("eval_interval_sec") or _alerts.interval_sec)
            n = max(5, min(600, n))
            _alerts.set_interval(n)
            # Persist so subsequent restarts keep the setting
            await db.ai_config.update_one(
                {"_id": "active"}, {"$set": {"alerts_eval_interval_sec": n}}, upsert=True)
            return {"eval_interval_sec": n}

    app.include_router(r)
    return r
