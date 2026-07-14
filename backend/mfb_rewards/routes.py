"""MFB Rewards — FastAPI routes (user + admin).

All endpoints are mounted at /api/mfb-rewards/*.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import wallet as W
from . import engine, referrals, campaigns, achievements, analytics


# -------------------------- Request/response models -----------------------
class ClaimCampaignReq(BaseModel):
    campaign_id: str


class AdminCreateCampaignReq(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = ""
    reward: int = Field(..., ge=1)
    start_date: datetime
    end_date: datetime
    conditions: Optional[Dict[str, Any]] = None
    max_users: Optional[int] = None
    target_users: Optional[List[str]] = None


class AdminUpdateCampaignReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    reward: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    conditions: Optional[Dict[str, Any]] = None
    max_users: Optional[int] = None
    target_users: Optional[List[str]] = None
    status: Optional[str] = None


class AdminGrantReq(BaseModel):
    user_id: str
    amount: int = Field(..., ge=1)
    reason: str = "admin_grant"


class AdminBurnReq(BaseModel):
    user_id: str
    amount: int = Field(..., ge=1)
    reason: str = "admin_burn"


class AdminReverseReq(BaseModel):
    user_id: str
    tx_id: str
    reason: str = "admin_reversal"


class AdminSettingReq(BaseModel):
    key: str
    value: Any


# -------------------------- Attach ----------------------------------------
def attach(api: APIRouter, *, db, get_current_user, get_current_admin, logger=None) -> None:
    user_r = APIRouter(prefix="/mfb-rewards", tags=["mfb-rewards"])
    admin_r = APIRouter(prefix="/admin/mfb-rewards", tags=["mfb-rewards-admin"])

    # ==================== USER endpoints =============================
    @user_r.get("/wallet")
    async def my_wallet(current=Depends(get_current_user)):
        uid = current["user_id"]
        w = await W.ensure_wallet(db, uid,
                                    referred_by=current.get("referred_by"),
                                    referral_code=current.get("referral_code"))
        prog = W.next_level_xp(int(w.get("xp", 0)))
        tier = W.level_to_tier(prog["current_level"])
        return {
            "balance":         int(w.get("balance", 0)),
            "lifetime_earned": int(w.get("lifetime_earned", 0)),
            "lifetime_spent":  int(w.get("lifetime_spent", 0)),
            "pending_rewards": int(w.get("pending_rewards", 0)),
            "locked_rewards":  int(w.get("locked_rewards", 0)),
            "referral_count": int(w.get("referral_count", 0)),
            "referral_code":  w.get("referral_code"),
            "level":           prog["current_level"],
            "xp":              prog["current_xp"],
            "next_level":     prog["next_level"],
            "next_level_xp": prog["next_level_xp"],
            "progress_pct":   prog["progress_pct"],
            "tier":            tier,
            "streak_current": int(w.get("streak_current", 0)),
            "streak_best":    int(w.get("streak_best", 0)),
        }

    @user_r.get("/history")
    async def my_history(limit: int = Query(50, ge=1, le=200),
                         skip: int = Query(0, ge=0),
                         source: Optional[str] = None,
                         current=Depends(get_current_user)):
        items = await engine.list_transactions(db, current["user_id"],
                                                 limit=limit, skip=skip, source=source)
        return {"items": items, "count": len(items)}

    @user_r.get("/rules")
    async def rules():
        settings = await W.list_settings(db)
        return {"settings": settings, "tiers": [
            {"min_level": t[0], "name": t[1], "emoji": t[2]} for t in W.TIER_TABLE
        ]}

    @user_r.post("/daily-login")
    async def claim_daily(current=Depends(get_current_user)):
        return await engine.record_daily_login(current["user_id"])

    @user_r.get("/referrals")
    async def my_referrals(current=Depends(get_current_user)):
        uid = current["user_id"]
        w = await W.ensure_wallet(db, uid)
        code = w.get("referral_code")
        links = referrals.build_deep_link(code)
        listing = await referrals.list_user_referrals(db, uid)
        return {
            "code":  code,
            "link":  links["web"],
            "deep_link": links["deep_link"],
            "qr_png_base64": referrals.generate_qr_png_b64(code),
            **listing,
        }

    @user_r.get("/achievements")
    async def my_achievements(current=Depends(get_current_user)):
        return {"items": await achievements.list_user_badges(db, current["user_id"])}

    @user_r.get("/campaigns/active")
    async def active_campaigns_endpoint(_=Depends(get_current_user)):
        return {"items": await campaigns.active_campaigns(db)}

    @user_r.post("/campaigns/claim")
    async def claim_campaign(req: ClaimCampaignReq, current=Depends(get_current_user)):
        try:
            return await campaigns.claim_campaign(db, req.campaign_id, current["user_id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @user_r.get("/leaderboard")
    async def leaderboard(period: str = "weekly", category: str = "earners",
                          _=Depends(get_current_user)):
        if period not in analytics.PERIODS:
            raise HTTPException(status_code=400, detail="invalid_period")
        if category not in analytics.CATEGORIES:
            raise HTTPException(status_code=400, detail="invalid_category")
        doc = await analytics.get_leaderboard(db, period, category)
        if not doc:
            # lazy build if not yet cached
            doc = await analytics.rebuild_leaderboard(db, period, category)
        return doc

    # ==================== ADMIN endpoints ============================
    @admin_r.get("/overview")
    async def admin_overview(_=Depends(get_current_admin)):
        return await analytics.kpis(db)

    @admin_r.get("/analytics/daily")
    async def admin_daily(days: int = 30, _=Depends(get_current_admin)):
        return {"items": await analytics.daily_series(db, days=days)}

    @admin_r.get("/analytics/distribution")
    async def admin_distribution(_=Depends(get_current_admin)):
        return {"items": await analytics.source_distribution(db)}

    @admin_r.get("/users")
    async def admin_users(limit: int = 100, skip: int = 0,
                          sort: str = "lifetime_earned",
                          _=Depends(get_current_admin)):
        sort_field = sort if sort in {"lifetime_earned", "xp", "balance",
                                        "referral_count", "level"} else "lifetime_earned"
        cur = db[W.COLL_WALLETS].find({}, {"_id": 0}).sort(sort_field, -1) \
                                 .skip(skip).limit(limit)
        return {"items": [d async for d in cur]}

    @admin_r.get("/transactions")
    async def admin_txs(limit: int = 100, skip: int = 0,
                        user_id: Optional[str] = None, source: Optional[str] = None,
                        _=Depends(get_current_admin)):
        q: Dict[str, Any] = {}
        if user_id:
            q["user_id"] = user_id
        if source:
            q["source"] = source
        cur = db[W.COLL_TX].find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        return {"items": [d async for d in cur]}

    # -------- Campaign CRUD --------
    @admin_r.post("/campaigns")
    async def create_campaign(req: AdminCreateCampaignReq, current=Depends(get_current_admin)):
        if req.end_date <= req.start_date:
            raise HTTPException(status_code=400, detail="end_date_must_be_after_start_date")
        return await campaigns.create_campaign(
            db, name=req.name, description=req.description, reward=req.reward,
            start_date=req.start_date, end_date=req.end_date,
            conditions=req.conditions, max_users=req.max_users,
            target_users=req.target_users,
            created_by=current.get("user_id", "admin"),
        )

    @admin_r.get("/campaigns")
    async def list_campaigns_endpoint(status: Optional[str] = None,
                                       _=Depends(get_current_admin)):
        return {"items": await campaigns.list_campaigns(db, status=status)}

    @admin_r.patch("/campaigns/{campaign_id}")
    async def update_campaign_endpoint(campaign_id: str, req: AdminUpdateCampaignReq,
                                        _=Depends(get_current_admin)):
        patch = req.model_dump(exclude_none=True) if hasattr(req, "model_dump") else req.dict(exclude_none=True)
        if "status" in patch and patch["status"] not in {"draft", "active", "paused", "ended"}:
            raise HTTPException(status_code=400, detail="invalid_status")
        doc = await campaigns.update_campaign(db, campaign_id, **patch)
        if not doc:
            raise HTTPException(status_code=404, detail="campaign_not_found")
        return doc

    @admin_r.delete("/campaigns/{campaign_id}")
    async def delete_campaign_endpoint(campaign_id: str, _=Depends(get_current_admin)):
        result = await db[W.COLL_CAMPAIGNS].delete_one({"campaign_id": campaign_id})
        return {"deleted": result.deleted_count}

    # -------- Achievements listing --------
    @admin_r.get("/achievements")
    async def admin_achievement_defs(_=Depends(get_current_admin)):
        return {"items": achievements.list_definitions()}

    # -------- Leaderboards trigger --------
    @admin_r.post("/leaderboards/rebuild")
    async def admin_rebuild_leaderboards(_=Depends(get_current_admin)):
        return await analytics.rebuild_all(db)

    # -------- Settings CRUD --------
    @admin_r.get("/settings")
    async def admin_list_settings(_=Depends(get_current_admin)):
        return {"items": await W.list_settings(db)}

    @admin_r.post("/settings")
    async def admin_set_setting(req: AdminSettingReq, current=Depends(get_current_admin)):
        return await W.set_setting(db, req.key, req.value,
                                     updated_by=current.get("user_id", "admin"))

    # -------- Grant / Burn / Reverse --------
    @admin_r.post("/grant")
    async def admin_grant(req: AdminGrantReq, _=Depends(get_current_admin)):
        tx = await engine.award(req.user_id, "admin_grant", W.gen_id("grant"),
                                amount=req.amount, reason=req.reason)
        return tx

    @admin_r.post("/burn")
    async def admin_burn(req: AdminBurnReq, _=Depends(get_current_admin)):
        try:
            return await engine.debit(req.user_id, req.amount,
                                       source="admin_burn", reason=req.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @admin_r.post("/reverse")
    async def admin_reverse(req: AdminReverseReq, _=Depends(get_current_admin)):
        try:
            return await engine.reverse(req.user_id, req.tx_id, reason=req.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    api.include_router(user_r)
    api.include_router(admin_r)
