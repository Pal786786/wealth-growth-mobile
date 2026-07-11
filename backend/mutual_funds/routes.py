"""Mutual Fund routes — user + admin (Sprint 11)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field, field_validator

from .engine import MutualFundEngine
from . import ai as ai_mod


# ---------- Schemas ---------- #
class InvestIn(BaseModel):
    fund_id: str
    amount: float = Field(..., gt=0)
    goal_id: Optional[str] = None
    payment_source: str = "wallet"


class SipCreateIn(BaseModel):
    fund_id: str
    amount: float = Field(..., gt=0)
    day_of_month: int = Field(5, ge=1, le=28)
    frequency: str = "monthly"
    goal_id: Optional[str] = None
    payment_source: str = "wallet"


class SipPatchIn(BaseModel):
    amount: Optional[float] = None
    day_of_month: Optional[int] = None
    frequency: Optional[str] = None


class SipStatusIn(BaseModel):
    status: str  # active | paused | cancelled | failed | completed


class RedeemIn(BaseModel):
    fund_id: str
    units: float = Field(..., gt=0)


class GoalIn(BaseModel):
    name: str
    kind: str  # retirement | house | car | education | marriage | emergency | custom
    target_amount: float = Field(..., gt=0)
    target_date: str  # ISO
    priority: str = "medium"
    expected_return_pct: float = 12.0
    linked_funds: List[str] = []


class GoalPatchIn(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[str] = None
    priority: Optional[str] = None
    expected_return_pct: Optional[float] = None
    linked_funds: Optional[List[str]] = None


class WatchlistIn(BaseModel):
    fund_id: str


class CompareIn(BaseModel):
    fund_ids: List[str] = Field(..., min_length=2, max_length=4)


class AIQueryIn(BaseModel):
    kind: str = "analyze_portfolio"


class ConfigPatch(BaseModel):
    provider: Optional[str] = None
    min_lumpsum_inr: Optional[float] = None
    min_sip_inr: Optional[float] = None
    sip_retry_max: Optional[int] = None
    sip_retry_hours: Optional[int] = None
    redemption_kyc_required: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    platform_fee_bps: Optional[float] = None
    nav_sync_interval_hours: Optional[int] = None


def _parse_dt(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def attach(app, db, get_current_user, get_current_admin, engine: MutualFundEngine):
    u = APIRouter(prefix="/api/mf", tags=["mutual-funds"])
    a = APIRouter(prefix="/api/admin/mf", tags=["mutual-funds-admin"])

    # =====================================================================
    # USER
    # =====================================================================
    @u.get("/config")
    async def user_config(user=Depends(get_current_user)):
        c = engine.config
        return {"min_lumpsum_inr": c["min_lumpsum_inr"], "min_sip_inr": c["min_sip_inr"],
                "maintenance_mode": c["maintenance_mode"],
                "redemption_kyc_required": c["redemption_kyc_required"]}

    @u.get("/funds")
    async def list_funds(q: Optional[str] = None, amc: Optional[str] = None,
                          category: Optional[str] = None, risk: Optional[str] = None,
                          min_rating: Optional[int] = None,
                          sort: str = "aum_desc",
                          limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0),
                          user=Depends(get_current_user)):
        return await engine.list_funds(q=q, amc=amc, category=category, risk=risk,
                                          min_rating=min_rating, sort=sort,
                                          limit=limit, skip=skip)

    @u.get("/amcs")
    async def amcs(user=Depends(get_current_user)):
        return {"items": await engine.amcs()}

    @u.get("/funds/{fund_id}")
    async def get_fund(fund_id: str, user=Depends(get_current_user)):
        f = await engine.get_fund(fund_id)
        if not f: raise HTTPException(404, "fund not found")
        return f

    @u.get("/funds/{fund_id}/chart")
    async def fund_chart(fund_id: str, window: str = Query("1Y"),
                          user=Depends(get_current_user)):
        rows = await engine.nav_history(fund_id, window)
        return {"points": rows, "window": window.upper()}

    @u.post("/compare")
    async def compare(body: CompareIn, user=Depends(get_current_user)):
        return {"funds": await engine.compare(body.fund_ids)}

    # -- watchlist
    @u.get("/watchlist")
    async def watchlist(user=Depends(get_current_user)):
        return {"items": await engine.watchlist(user["user_id"])}

    @u.post("/watchlist")
    async def watchlist_add(body: WatchlistIn, user=Depends(get_current_user)):
        try: return await engine.watchlist_add(user["user_id"], body.fund_id)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.delete("/watchlist/{fund_id}")
    async def watchlist_del(fund_id: str, user=Depends(get_current_user)):
        return await engine.watchlist_remove(user["user_id"], fund_id)

    # -- invest
    @u.post("/invest")
    async def invest(body: InvestIn,
                      idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                      user=Depends(get_current_user)):
        try:
            return await engine.invest_lumpsum(user["user_id"], body.fund_id, body.amount,
                                                idempotency_key=idempotency_key,
                                                goal_id=body.goal_id,
                                                payment_source=body.payment_source)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.post("/redeem")
    async def redeem(body: RedeemIn,
                      idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                      user=Depends(get_current_user)):
        try:
            return await engine.redeem(user["user_id"], body.fund_id, body.units,
                                         idempotency_key=idempotency_key)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.get("/orders")
    async def orders(kind: Optional[str] = None,
                      limit: int = Query(100, ge=1, le=500), skip: int = Query(0, ge=0),
                      user=Depends(get_current_user)):
        rows = await engine.user_orders(user["user_id"], kind=kind, limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    # -- SIPs
    @u.post("/sips")
    async def sip_create(body: SipCreateIn, user=Depends(get_current_user)):
        try:
            return await engine.create_sip(user["user_id"], body.fund_id, body.amount,
                                             day_of_month=body.day_of_month,
                                             frequency=body.frequency,
                                             goal_id=body.goal_id,
                                             payment_source=body.payment_source)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.get("/sips")
    async def sip_list(status: Optional[str] = None, user=Depends(get_current_user)):
        rows = await engine.list_sips(user["user_id"], status=status)
        return {"items": rows, "count": len(rows)}

    @u.patch("/sips/{sip_id}")
    async def sip_patch(sip_id: str, body: SipPatchIn, user=Depends(get_current_user)):
        try:
            return await engine.modify_sip(user["user_id"], sip_id,
                                             body.model_dump(exclude_none=True))
        except ValueError as e: raise HTTPException(400, str(e))

    @u.post("/sips/{sip_id}/status")
    async def sip_status(sip_id: str, body: SipStatusIn, user=Depends(get_current_user)):
        try:
            return await engine.set_sip_status(user["user_id"], sip_id, body.status)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.get("/sips/{sip_id}/executions")
    async def sip_execs(sip_id: str, user=Depends(get_current_user)):
        rows = await engine.sip_executions(user["user_id"], sip_id=sip_id)
        return {"items": rows, "count": len(rows)}

    # -- portfolio
    @u.get("/portfolio")
    async def portfolio(user=Depends(get_current_user)):
        return await engine.portfolio(user["user_id"])

    # -- goals
    @u.get("/goals")
    async def goals_list(user=Depends(get_current_user)):
        return {"items": await engine.list_goals(user["user_id"])}

    @u.post("/goals")
    async def goal_create(body: GoalIn, user=Depends(get_current_user)):
        try:
            return await engine.create_goal(user["user_id"], name=body.name, kind=body.kind,
                                              target_amount=body.target_amount,
                                              target_date=_parse_dt(body.target_date),
                                              priority=body.priority,
                                              expected_return_pct=body.expected_return_pct,
                                              linked_funds=body.linked_funds)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.patch("/goals/{goal_id}")
    async def goal_patch(goal_id: str, body: GoalPatchIn, user=Depends(get_current_user)):
        try:
            patch = body.model_dump(exclude_none=True)
            if "target_date" in patch: patch["target_date"] = _parse_dt(patch["target_date"])
            return await engine.update_goal(user["user_id"], goal_id, patch)
        except ValueError as e: raise HTTPException(400, str(e))

    @u.delete("/goals/{goal_id}")
    async def goal_delete(goal_id: str, user=Depends(get_current_user)):
        return await engine.delete_goal(user["user_id"], goal_id)

    # -- AI Advisor
    @u.post("/ai")
    async def ai(body: AIQueryIn, user=Depends(get_current_user)):
        portfolio = await engine.portfolio(user["user_id"])
        goals = await engine.list_goals(user["user_id"])
        # Small subset of funds to keep context lean
        funds = await engine.list_funds(limit=15, sort="rating_desc")
        ctx = {"user_id": user["user_id"], "portfolio": portfolio, "goals": goals,
               "holdings": portfolio.get("holdings"),
               "total_invested": portfolio.get("total_invested"),
               "current_value": portfolio.get("current_value"),
               "top_funds_available": funds.get("items", [])[:15]}
        return await ai_mod.advise(body.kind, ctx)

    # =====================================================================
    # ADMIN
    # =====================================================================
    @a.get("/dashboard")
    async def dashboard(admin=Depends(get_current_admin)):
        return await engine.admin_dashboard()

    @a.get("/config")
    async def cfg(admin=Depends(get_current_admin)):
        return engine.config

    @a.put("/config")
    async def patch_cfg(body: ConfigPatch, admin=Depends(get_current_admin)):
        try:
            return await engine.patch_config(body.model_dump(exclude_none=True),
                                                admin_id=admin.get("admin_id") or "admin")
        except ValueError as e: raise HTTPException(400, str(e))

    @a.get("/providers")
    async def providers(admin=Depends(get_current_admin)):
        from .providers import PROVIDER_REGISTRY, get_provider
        out = []
        for n in PROVIDER_REGISTRY:
            p = get_provider(db, n)
            out.append({"name": p.name, "real": getattr(p, "real", False),
                        "configured": p.is_configured(),
                        "active": n == engine.config.get("provider")})
        return {"providers": out, "active": engine.config.get("provider")}

    @a.get("/funds")
    async def afunds(limit: int = Query(200, ge=1, le=1000), skip: int = 0,
                       q: Optional[str] = None, category: Optional[str] = None,
                       admin=Depends(get_current_admin)):
        return await engine.list_funds(q=q, category=category, limit=limit, skip=skip)

    @a.post("/funds")
    async def afund_upsert(body: Dict[str, Any], admin=Depends(get_current_admin)):
        return await engine.upsert_fund(body)

    @a.put("/funds/{fund_id}")
    async def afund_put(fund_id: str, body: Dict[str, Any], admin=Depends(get_current_admin)):
        return await engine.upsert_fund({**body, "fund_id": fund_id})

    @a.get("/investors")
    async def ainvestors(limit: int = Query(200, ge=1, le=1000),
                            admin=Depends(get_current_admin)):
        rows = await engine.admin_investors(limit=limit)
        return {"items": rows, "count": len(rows)}

    @a.get("/orders")
    async def aorders(kind: Optional[str] = None, status: Optional[str] = None,
                        user_id: Optional[str] = None,
                        limit: int = Query(200, ge=1, le=1000), skip: int = 0,
                        admin=Depends(get_current_admin)):
        rows = await engine.admin_orders(kind=kind, status=status, user_id=user_id,
                                            limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @a.get("/sips")
    async def asips(status: Optional[str] = None, limit: int = Query(200, ge=1, le=1000),
                     admin=Depends(get_current_admin)):
        rows = await engine.admin_sips(status=status, limit=limit)
        return {"items": rows, "count": len(rows)}

    @a.post("/sips/execute-due")
    async def asips_run(dry_run: bool = False, admin=Depends(get_current_admin)):
        return await engine.execute_due_sips(actor=admin.get("admin_id") or "admin", dry_run=dry_run)

    app.include_router(u)
    app.include_router(a)
    return {"user": u, "admin": a}
