"""Copy Trading routes — Sprint 7B.3 (extends 7B.2)

Public:
  Leaderboard/profile     — /api/copy_trading/traders[...]
  My relationships        — /api/copy_trading/my/copies + traders/{id}/copy/*
  Copy execution history  — /api/copy_trading/my/trades, /my/summary
  Bulk actions            — /api/copy_trading/my/copies/pause-all|resume-all|close-all

Admin (Sprint 7B.3):
  Trader Management       — /admin/traders[...]           (CRUD + verify/disable/enable/reset-overlay)
  Simulation control      — /admin/simulation/*
  Master Trade Explorer   — /admin/master-trades (with follower_count each)
  Follower Monitor        — /admin/followers/summary, /admin/traders/{id}/followers
  Copy Analytics          — /admin/analytics
  System Health           — /admin/system-health
  Configuration           — /admin/config, /admin/config/defaults
"""
from __future__ import annotations
import platform
import time
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import traders as tmod
from . import admin_traders as at
from .engine import CopyEngine
from .config import DEFAULT_SETTINGS, VALID_MODES, DEFAULT_SIM_STATE

_engine: Optional[CopyEngine] = None
_simulator = None
_STARTUP_TS = time.time()


_SORT_KEYS = {
    "total_roi":    lambda t: t["stats"]["total_roi_pct"],
    "monthly_roi":  lambda t: t["stats"]["monthly_roi_pct"],
    "win_rate":     lambda t: t["stats"]["win_rate_pct"],
    "followers":    lambda t: t["stats"]["followers"],
    "risk":         lambda t: -t["risk"]["risk_score"],
    "new":          lambda t: -t["joined_days_ago"],
    "aum":          lambda t: t["stats"]["aum_usd"],
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
    side: Optional[str] = None
    symbol: Optional[str] = None


class TraderCreateIn(BaseModel):
    name: str
    country_code: Optional[str] = "US"
    country_name: Optional[str] = None
    style: Optional[str] = "Day Trading"
    experience_years: Optional[int] = 3
    bio: Optional[str] = ""
    verified: Optional[bool] = False
    approval_level: Optional[str] = "verified"
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    truth: Optional[Dict[str, Any]] = None


class TraderPatchIn(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    style: Optional[str] = None
    experience_years: Optional[int] = None
    verified: Optional[bool] = None
    approval_level: Optional[str] = None
    risk_tier: Optional[str] = None    # only for system overlays
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    visible: Optional[bool] = None
    disabled: Optional[bool] = None
    truth: Optional[Dict[str, Any]] = None


def _base64_to_data_url(b64: str) -> str:
    b64 = b64.strip()
    if b64.startswith("data:"):
        return b64
    # naive mime detection — default to png
    return f"data:image/png;base64,{b64}"


def _filter_leaderboard(items: List[Dict[str, Any]], *, search: Optional[str],
                        min_risk: int, max_risk: int, verified_only: bool) -> List[Dict[str, Any]]:
    if search:
        q = search.lower().strip()
        items = [t for t in items if q in t["name"].lower() or q in (t.get("country_name") or "").lower() or q in t["style"].lower()]
    items = [t for t in items if min_risk <= t["risk"]["risk_score"] <= max_risk]
    if verified_only:
        items = [t for t in items if t.get("verified")]
    return items


def attach(app, db, get_current_user, engine: CopyEngine, simulator, get_current_admin=None):
    global _engine, _simulator
    _engine = engine
    _simulator = simulator

    r = APIRouter(prefix="/api/copy_trading", tags=["copy-trading"])

    # ----------------- Leaderboard (public) -----------------
    @r.get("/traders")
    async def leaderboard(
        sort: str = Query("total_roi"),
        search: Optional[str] = None,
        min_risk: int = Query(1, ge=1, le=10),
        max_risk: int = Query(10, ge=1, le=10),
        verified_only: bool = False,
        include_disabled: bool = False,
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=50),
    ):
        items = await at.all_traders(db, include_disabled=include_disabled, include_hidden=False)
        items = _filter_leaderboard(items, search=search, min_risk=min_risk,
                                    max_risk=max_risk, verified_only=verified_only)
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
        t = await at.get_trader(db, trader_id, include_curve=True)
        if not t or t.get("disabled") or not t.get("visible", True):
            raise HTTPException(404, "Trader not found")
        return t

    @r.get("/traders/{trader_id}/open-trades")
    async def trader_open(trader_id: str):
        if not await at.get_trader(db, trader_id):
            raise HTTPException(404, "Trader not found")
        # For seeded traders keep the deterministic pseudo-open feed.
        # For custom traders, use master trades from mongo.
        if tmod._persona_by_id(trader_id):
            return {"trades": tmod.open_trades(trader_id)}
        cur = db.copy_master_trades.find(
            {"trader_id": trader_id, "status": "open"}, {"_id": 0}).sort("opened_at", -1).limit(20)
        return {"trades": [d async for d in cur]}

    @r.get("/traders/{trader_id}/closed-trades")
    async def trader_closed(trader_id: str, limit: int = Query(40, ge=5, le=200)):
        if not await at.get_trader(db, trader_id):
            raise HTTPException(404, "Trader not found")
        if tmod._persona_by_id(trader_id):
            return {"trades": tmod.closed_trades(trader_id, limit=limit)}
        cur = db.copy_master_trades.find(
            {"trader_id": trader_id, "status": "closed"}, {"_id": 0}).sort("closed_at", -1).limit(limit)
        return {"trades": [d async for d in cur]}

    @r.get("/traders/{trader_id}/master-trades")
    async def trader_master_trades(trader_id: str, limit: int = Query(50, ge=1, le=200)):
        if not await at.get_trader(db, trader_id):
            raise HTTPException(404, "Trader not found")
        rows = await _simulator.recent_master_trades(trader_id=trader_id, limit=limit)
        return {"trades": rows}

    # ----------------- Copy relationship (user) -----------------
    @r.get("/my/copies")
    async def my_copies(user=Depends(get_current_user)):
        # Lookup wrapper for enrichment — sync fallback to seeded
        def tlookup(tid):
            p = tmod.get_trader(tid)
            return p
        # Async loader that handles custom traders too
        rels = await _engine.list_copies(user["user_id"])
        for rel in rels:
            open_pos = await db.copy_follower_trades.count_documents(
                {"user_id": user["user_id"], "trader_id": rel["trader_id"], "status": "open"})
            lifetime_pnl = await _engine._lifetime_pnl(user["user_id"], rel["trader_id"])
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stat = await db.copy_daily_stats.find_one(
                {"user_id": user["user_id"], "trader_id": rel["trader_id"], "day": today}) or {}
            rel["live"] = {
                "open_positions": open_pos,
                "lifetime_pnl_usd": round(lifetime_pnl, 2),
                "today_pnl_usd": round(float(stat.get("pnl_usd", 0.0)), 2),
                "today_trades": int(stat.get("trade_count", 0)),
                "starting_equity_usd": float(rel.get("starting_equity_usd") or 10000),
                "current_equity_usd": round(float(rel.get("starting_equity_usd") or 10000) + lifetime_pnl, 2),
            }
            rel["trader"] = await at.get_trader(db, rel["trader_id"])
        return {"copies": rels}

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
        if not await at.get_trader(db, trader_id):
            raise HTTPException(404, "Trader not found")
        return await _engine.get_settings(user["user_id"], trader_id)

    @r.post("/traders/{trader_id}/copy/start")
    async def start_copy(trader_id: str, body: Optional[StartCopyIn] = None,
                         user=Depends(get_current_user)):
        t = await at.get_trader(db, trader_id)
        if not t or t.get("disabled"):
            raise HTTPException(404, "Trader not available")
        settings = None
        if body and body.settings:
            settings = body.settings.model_dump(exclude_none=True)
        return await _engine.start_copy(user["user_id"], trader_id, settings)

    @r.post("/traders/{trader_id}/copy/pause")
    async def pause_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "paused")

    @r.post("/traders/{trader_id}/copy/resume")
    async def resume_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "active", halt_reason=None)

    @r.post("/traders/{trader_id}/copy/stop")
    async def stop_copy(trader_id: str, user=Depends(get_current_user)):
        return await _engine.set_status(user["user_id"], trader_id, "stopped",
                                        close_open_trades=True)

    @r.put("/traders/{trader_id}/copy/settings")
    async def update_settings(trader_id: str, body: CopySettingsIn,
                              user=Depends(get_current_user)):
        if not await at.get_trader(db, trader_id):
            raise HTTPException(404, "Trader not found")
        patch = body.model_dump(exclude_none=True)
        return await _engine.update_settings(user["user_id"], trader_id, patch)

    # ----------------- Meta / diagnostics -----------------
    @r.get("/meta")
    async def meta():
        defaults = await _engine.config.defaults()
        sim = await _engine.config.sim_state()
        return {
            "trader_count": len(tmod.list_trader_ids()) + len(await at.list_custom_trader_ids(db)),
            "sort_keys": list(_SORT_KEYS.keys()),
            "default_settings": defaults,
            "modes": sorted(VALID_MODES),
            "styles": sorted(tmod._SYMBOLS_BY_STYLE.keys()),
            "approval_levels": list(at.APPROVAL_LEVELS),
            "risk_tiers": list(at.RISK_TIERS),
            "categories": list(at.CATEGORIES),
            "broker": _engine.broker.name if _engine else None,
            "simulator": {"enabled": sim.get("enabled"), "speed": sim.get("speed")},
        }

    # ==================================================================
    # ADMIN — Sprint 7B.3
    # ==================================================================
    if get_current_admin is not None:
        # -------- Trader Management --------
        @r.get("/admin/traders")
        async def admin_list_traders(
            category: Optional[str] = Query(None, description="system|verified|custom|disabled"),
            search: Optional[str] = None,
            approval_level: Optional[str] = None,
            page: int = Query(1, ge=1),
            limit: int = Query(50, ge=1, le=200),
            admin=Depends(get_current_admin),
        ):
            items = await at.all_traders(db, include_disabled=True, include_hidden=True)
            if category == "system":
                items = [t for t in items if t.get("kind") == "system"]
            elif category == "custom":
                items = [t for t in items if t.get("kind") == "custom"]
            elif category == "verified":
                items = [t for t in items if t.get("verified")]
            elif category == "disabled":
                items = [t for t in items if t.get("disabled")]
            if approval_level in at.APPROVAL_LEVELS:
                items = [t for t in items if t.get("approval_level") == approval_level]
            if search:
                q = search.lower().strip()
                items = [t for t in items if q in t["name"].lower() or q in (t.get("country_name") or "").lower()]
            # Sort: custom first, then by ROI desc
            items.sort(key=lambda t: (0 if t.get("kind") == "custom" else 1,
                                      -t["stats"]["total_roi_pct"]))
            total = len(items)
            start = (page - 1) * limit
            return {"items": items[start:start + limit], "total": total,
                    "page": page, "limit": limit}

        @r.get("/admin/traders/{trader_id}")
        async def admin_get_trader(trader_id: str, admin=Depends(get_current_admin)):
            t = await at.get_trader(db, trader_id, include_curve=True)
            if not t:
                raise HTTPException(404, "Trader not found")
            return t

        @r.post("/admin/traders")
        async def admin_create_trader(body: TraderCreateIn, admin=Depends(get_current_admin)):
            payload = body.model_dump(exclude_none=True)
            if body.avatar_base64:
                payload["avatar_url"] = _base64_to_data_url(body.avatar_base64)
                payload.pop("avatar_base64", None)
            try:
                t = await at.create_custom_trader(db, payload)
            except ValueError as e:
                raise HTTPException(400, str(e))
            # Spawn simulator task for new trader
            try:
                await _simulator.sync_traders()
            except Exception:
                pass
            return t

        @r.put("/admin/traders/{trader_id}")
        async def admin_update_trader(trader_id: str, body: TraderPatchIn,
                                       admin=Depends(get_current_admin)):
            patch = body.model_dump(exclude_none=True)
            if body.avatar_base64:
                patch["avatar_url"] = _base64_to_data_url(body.avatar_base64)
                patch.pop("avatar_base64", None)
            if tmod._persona_by_id(trader_id):
                # System trader → write overlay
                try:
                    await at.upsert_overlay(db, trader_id, patch)
                except ValueError as e:
                    raise HTTPException(400, str(e))
            else:
                # Custom trader → update
                res = await at.update_custom_trader(db, trader_id, patch)
                if not res:
                    raise HTTPException(404, "Custom trader not found")
            return await at.get_trader(db, trader_id)

        @r.delete("/admin/traders/{trader_id}")
        async def admin_delete_trader(trader_id: str, admin=Depends(get_current_admin)):
            if tmod._persona_by_id(trader_id):
                raise HTTPException(400, "Cannot delete a system trader — use disable instead")
            deleted = await at.delete_custom_trader(db, trader_id)
            if not deleted:
                raise HTTPException(404, "Trader not found")
            try:
                await _simulator.remove_trader(trader_id)
            except Exception:
                pass
            return {"deleted": True, "trader_id": trader_id}

        @r.post("/admin/traders/{trader_id}/verify")
        async def admin_verify_trader(trader_id: str, admin=Depends(get_current_admin)):
            if tmod._persona_by_id(trader_id):
                await at.upsert_overlay(db, trader_id, {"verified": True, "approval_level": "verified"})
            else:
                await at.update_custom_trader(db, trader_id, {"verified": True, "approval_level": "verified"})
            return await at.get_trader(db, trader_id)

        @r.post("/admin/traders/{trader_id}/unverify")
        async def admin_unverify_trader(trader_id: str, admin=Depends(get_current_admin)):
            if tmod._persona_by_id(trader_id):
                await at.upsert_overlay(db, trader_id, {"verified": False})
            else:
                await at.update_custom_trader(db, trader_id, {"verified": False})
            return await at.get_trader(db, trader_id)

        @r.post("/admin/traders/{trader_id}/disable")
        async def admin_disable_trader(trader_id: str, admin=Depends(get_current_admin)):
            if tmod._persona_by_id(trader_id):
                await at.upsert_overlay(db, trader_id, {"disabled": True})
            else:
                await at.update_custom_trader(db, trader_id, {"disabled": True})
            return await at.get_trader(db, trader_id)

        @r.post("/admin/traders/{trader_id}/enable")
        async def admin_enable_trader(trader_id: str, admin=Depends(get_current_admin)):
            if tmod._persona_by_id(trader_id):
                await at.upsert_overlay(db, trader_id, {"disabled": False})
            else:
                await at.update_custom_trader(db, trader_id, {"disabled": False})
            return await at.get_trader(db, trader_id)

        @r.post("/admin/traders/{trader_id}/reset-overlay")
        async def admin_reset_overlay(trader_id: str, admin=Depends(get_current_admin)):
            if not tmod._persona_by_id(trader_id):
                raise HTTPException(400, "Not a system trader")
            await at.reset_overlay(db, trader_id)
            return await at.get_trader(db, trader_id)

        # -------- Simulation control --------
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
            try:
                trade = await _simulator.force_open(body.trader_id, side=body.side, symbol=body.symbol)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"master_trade": trade}

        @r.post("/admin/simulation/force-close/{master_id}")
        async def sim_force_close(master_id: str, admin=Depends(get_current_admin)):
            try:
                return await _simulator.force_close(master_id)
            except ValueError as e:
                raise HTTPException(404, str(e))

        # -------- Master Trade Explorer --------
        @r.get("/admin/master-trades")
        async def admin_master_trades(
            limit: int = Query(100, ge=1, le=500),
            status: Optional[str] = None,
            trader_id: Optional[str] = None,
            admin=Depends(get_current_admin),
        ):
            q: Dict[str, Any] = {}
            if status:
                q["status"] = status
            if trader_id:
                q["trader_id"] = trader_id
            cur = db.copy_master_trades.find(q, {"_id": 0}).sort("opened_at", -1).limit(limit)
            rows = [d async for d in cur]
            for row in rows:
                row["followers_copied"] = await db.copy_follower_trades.count_documents(
                    {"master_id": row["master_id"]})
            return {"trades": rows}

        # -------- Follower Monitor --------
        @r.get("/admin/followers/summary")
        async def admin_followers_summary(admin=Depends(get_current_admin)):
            active = await db.copy_relationships.count_documents({"status": "active"})
            paused = await db.copy_relationships.count_documents({"status": "paused"})
            stopped = await db.copy_relationships.count_documents({"status": "stopped"})
            halted = await db.copy_relationships.count_documents({"status": "halted"})
            distinct_users = await db.copy_relationships.distinct("user_id")
            # Top traders by follower count
            pipeline = [
                {"$match": {"status": {"$ne": "stopped"}}},
                {"$group": {"_id": "$trader_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ]
            top = await db.copy_relationships.aggregate(pipeline).to_list(10)
            top_enriched = []
            for row in top:
                tr = await at.get_trader(db, row["_id"])
                top_enriched.append({
                    "trader_id": row["_id"],
                    "trader_name": tr.get("name") if tr else row["_id"],
                    "follower_count": row["count"],
                })
            return {
                "total_relationships": active + paused + stopped + halted,
                "active": active, "paused": paused, "stopped": stopped, "halted": halted,
                "unique_followers": len(distinct_users),
                "top_traders": top_enriched,
            }

        @r.get("/admin/traders/{trader_id}/followers")
        async def admin_trader_followers(trader_id: str,
                                          status: Optional[str] = None,
                                          limit: int = Query(200, ge=1, le=1000),
                                          admin=Depends(get_current_admin)):
            q: Dict[str, Any] = {"trader_id": trader_id}
            if status:
                q["status"] = status
            cur = db.copy_relationships.find(q, {"_id": 0}).sort("started_at", -1).limit(limit)
            rels = [d async for d in cur]
            # Enrich with user name + live stats
            for rel in rels:
                u = await db.users.find_one({"user_id": rel["user_id"]},
                                            {"_id": 0, "full_name": 1, "email": 1, "mobile": 1})
                rel["user"] = u or {}
                lifetime = await _engine._lifetime_pnl(rel["user_id"], trader_id)
                open_count = await db.copy_follower_trades.count_documents(
                    {"user_id": rel["user_id"], "trader_id": trader_id, "status": "open"})
                rel["live"] = {"lifetime_pnl_usd": round(lifetime, 2),
                               "open_positions": open_count}
            trader = await at.get_trader(db, trader_id)
            return {"trader": trader, "followers": rels}

        # -------- Analytics --------
        @r.get("/admin/analytics")
        async def admin_analytics(admin=Depends(get_current_admin)):
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            day_ago = now - timedelta(days=1)
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)

            total_master = await db.copy_master_trades.estimated_document_count()
            total_mirrored = await db.copy_follower_trades.estimated_document_count()
            open_positions = await db.copy_follower_trades.count_documents({"status": "open"})
            active_copies = await db.copy_relationships.count_documents({"status": "active"})
            daily_copies = await db.copy_relationships.count_documents({"started_at": {"$gte": day_ago}})
            monthly_copies = await db.copy_relationships.count_documents({"started_at": {"$gte": month_ago}})
            total_followers = len(await db.copy_relationships.distinct("user_id"))
            # P&L aggregates
            pipe_pnl = [
                {"$match": {"status": "closed"}},
                {"$group": {"_id": None,
                            "total_profit": {"$sum": {"$cond": [{"$gt": ["$pnl_usd", 0]}, "$pnl_usd", 0]}},
                            "total_loss":   {"$sum": {"$cond": [{"$lt": ["$pnl_usd", 0]}, "$pnl_usd", 0]}},
                            "trades":       {"$sum": 1},
                            "wins":         {"$sum": {"$cond": [{"$gt": ["$pnl_usd", 0]}, 1, 0]}}}}
            ]
            pnl_docs = await db.copy_follower_trades.aggregate(pipe_pnl).to_list(1)
            pnl = pnl_docs[0] if pnl_docs else {"total_profit": 0, "total_loss": 0, "trades": 0, "wins": 0}
            total_profit = float(pnl.get("total_profit", 0))
            total_loss = float(pnl.get("total_loss", 0))
            closed_trades = int(pnl.get("trades", 0))
            wins = int(pnl.get("wins", 0))
            win_rate = round((wins / closed_trades * 100) if closed_trades > 0 else 0, 2)

            # ROI windows on follower P&L
            async def roi_window(since):
                pipe = [
                    {"$match": {"status": "closed", "closed_at": {"$gte": since}}},
                    {"$group": {"_id": None, "sum": {"$sum": "$pnl_usd"},
                                "eq": {"$sum": "$lot_size"}}},
                ]
                docs = await db.copy_follower_trades.aggregate(pipe).to_list(1)
                if not docs:
                    return 0.0
                return round(float(docs[0]["sum"]), 2)
            daily_roi = await roi_window(day_ago)
            weekly_roi = await roi_window(week_ago)
            monthly_roi = await roi_window(month_ago)

            # Top traders
            all_traders = await at.all_traders(db, include_disabled=True, include_hidden=True)
            highest_roi = max(all_traders, key=lambda t: t["stats"]["total_roi_pct"], default=None)
            highest_wr = max(all_traders, key=lambda t: t["stats"]["win_rate_pct"], default=None)
            highest_aum = max(all_traders, key=lambda t: t["stats"]["aum_usd"], default=None)

            # Most copied
            pipe_mc = [
                {"$match": {"status": {"$ne": "stopped"}}},
                {"$group": {"_id": "$trader_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}, {"$limit": 1},
            ]
            mc_docs = await db.copy_relationships.aggregate(pipe_mc).to_list(1)
            most_copied = None
            if mc_docs:
                most_copied_t = await at.get_trader(db, mc_docs[0]["_id"])
                if most_copied_t:
                    most_copied = {"trader_id": mc_docs[0]["_id"],
                                   "name": most_copied_t["name"], "follower_count": mc_docs[0]["count"]}

            def _brief(t):
                if not t:
                    return None
                return {"id": t["id"], "name": t["name"], "style": t["style"],
                        "total_roi_pct": t["stats"]["total_roi_pct"],
                        "win_rate_pct": t["stats"]["win_rate_pct"],
                        "aum_usd": t["stats"]["aum_usd"]}

            avg_risk = round(sum(t["risk"]["risk_score"] for t in all_traders) / max(1, len(all_traders)), 2)
            avg_roi = round(sum(t["stats"]["total_roi_pct"] for t in all_traders) / max(1, len(all_traders)), 2)

            return {
                "trades": {
                    "total_master": total_master,
                    "total_mirrored": total_mirrored,
                    "open_positions": open_positions,
                    "closed_trades": closed_trades,
                },
                "pnl": {
                    "total_profit_usd": round(total_profit, 2),
                    "total_loss_usd": round(total_loss, 2),
                    "net_usd": round(total_profit + total_loss, 2),
                    "win_rate_pct": win_rate,
                },
                "roi": {
                    "daily_usd": daily_roi,
                    "weekly_usd": weekly_roi,
                    "monthly_usd": monthly_roi,
                    "avg_trader_roi_pct": avg_roi,
                    "avg_trader_risk": avg_risk,
                },
                "copies": {
                    "active": active_copies,
                    "daily_new": daily_copies,
                    "monthly_new": monthly_copies,
                    "unique_followers": total_followers,
                    "most_copied": most_copied,
                },
                "leaders": {
                    "highest_roi": _brief(highest_roi),
                    "highest_win_rate": _brief(highest_wr),
                    "highest_aum": _brief(highest_aum),
                },
            }

        # -------- System Health --------
        @r.get("/admin/system-health")
        async def admin_system_health(admin=Depends(get_current_admin)):
            sim = await _simulator.status()
            engine_h = _engine.health_snapshot()
            # DB ping
            db_ok = True
            try:
                await db.command("ping")
            except Exception:
                db_ok = False
            # Server uptime
            uptime = round(time.time() - _STARTUP_TS, 0)
            # Active copy sessions and followers
            active_sessions = await db.copy_relationships.count_documents({"status": {"$in": ["active", "paused"]}})
            active_followers = len(await db.copy_relationships.distinct(
                "user_id", {"status": {"$in": ["active", "paused"]}}))
            return {
                "event_queue_size": 0,   # in-process bus is synchronous fan-out; no persistent queue
                "active_simulators": sim.get("active_traders", 0),
                "active_followers": active_followers,
                "active_copy_sessions": active_sessions,
                "broker": {"name": engine_h["broker"], "ok": engine_h["broker_ok"]},
                "avg_fanout_ms": engine_h["avg_fanout_ms"],
                "avg_exec_ms": engine_h["avg_exec_ms"],
                "failed_mirrors": engine_h["failed_mirrors"],
                "retry_queue_size": engine_h["retry_queue_size"],
                "events_processed": engine_h["events_processed"],
                "server": {"ok": True, "uptime_sec": uptime,
                            "platform": platform.python_version()},
                "database": {"ok": db_ok},
                "simulator": sim,
            }

        # -------- Configuration --------
        @r.get("/admin/config")
        async def get_admin_config(admin=Depends(get_current_admin)):
            defaults = await _engine.config.defaults()
            sim = await _engine.config.sim_state()
            return {"defaults": defaults, "sim": sim,
                    "schema": {
                        "modes": sorted(VALID_MODES),
                        "resume_modes": ["manual", "auto"],
                        "speeds": ["slow", "normal", "fast"],
                    }}

        @r.put("/admin/config/defaults")
        async def set_admin_defaults(body: CopySettingsIn,
                                      admin=Depends(get_current_admin)):
            patch = body.model_dump(exclude_none=True)
            merged = await _engine.config.update_defaults(patch)
            return {"defaults": merged}

    app.include_router(r)
    return r
