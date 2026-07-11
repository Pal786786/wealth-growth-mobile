"""Gold routes — user + admin (Sprint 10)."""
from __future__ import annotations
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field

from .engine import GoldEngine


class BuyIn(BaseModel):
    amount_inr: float = Field(..., ge=1)


class SellIn(BaseModel):
    grams: float = Field(..., gt=0)


class ConfigPatch(BaseModel):
    provider: Optional[str] = None
    spread_bps: Optional[float] = None
    min_buy_inr: Optional[float] = None
    max_buy_inr: Optional[float] = None
    maintenance_mode: Optional[bool] = None
    trading_hours: Optional[Dict[str, str]] = None
    manual_price_inr_per_gram: Optional[float] = None
    gst_bps: Optional[float] = None
    maker_fee_bps: Optional[float] = None
    redemption_kyc_required: Optional[bool] = None


def attach(app, db, get_current_user, get_current_admin, engine: GoldEngine):
    u = APIRouter(prefix="/api/gold", tags=["gold"])
    a = APIRouter(prefix="/api/admin/gold", tags=["gold-admin"])

    # ----------- USER ----------- #
    @u.get("/quote")
    async def quote(user=Depends(get_current_user)):
        q = await engine.quote()
        # Snapshot for chart on every quote call (cheap)
        try: await engine.snapshot_price()
        except Exception: pass
        return q

    @u.get("/chart")
    async def chart(window: str = Query("1D"), user=Depends(get_current_user)):
        return {"points": await engine.chart(window), "window": window.upper()}

    @u.get("/holdings")
    async def holdings(user=Depends(get_current_user)):
        return await engine.holdings(user["user_id"])

    @u.get("/transactions")
    async def transactions(side: Optional[str] = Query(None),
                             search: Optional[str] = Query(None),
                             limit: int = Query(50, ge=1, le=200),
                             skip: int = Query(0, ge=0),
                             user=Depends(get_current_user)):
        rows = await engine.transactions(user["user_id"], side=side,
                                          search=search, limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @u.post("/buy")
    async def buy(body: BuyIn, idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                    user=Depends(get_current_user)):
        try:
            return await engine.buy(user["user_id"], body.amount_inr, idempotency_key)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @u.post("/sell")
    async def sell(body: SellIn, idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                    user=Depends(get_current_user)):
        try:
            return await engine.sell(user["user_id"], body.grams, idempotency_key)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @u.get("/config")
    async def user_config(user=Depends(get_current_user)):
        # Client-safe subset
        c = engine.config
        return {"min_buy_inr": c["min_buy_inr"], "max_buy_inr": c["max_buy_inr"],
                "spread_bps": c["spread_bps"], "provider": c["provider"],
                "maintenance_mode": c["maintenance_mode"],
                "trading_hours": c["trading_hours"],
                "redemption_kyc_required": c["redemption_kyc_required"]}

    # ----------- ADMIN ----------- #
    @a.get("/dashboard")
    async def dashboard(admin=Depends(get_current_admin)):
        return await engine.dashboard()

    @a.get("/config")
    async def get_config(admin=Depends(get_current_admin)):
        return engine.config

    @a.put("/config")
    async def patch_config(body: ConfigPatch, admin=Depends(get_current_admin)):
        try:
            return await engine.patch_config(
                {k: v for k, v in body.dict().items() if v is not None},
                admin_id=admin.get("admin_id") or "admin")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @a.get("/transactions")
    async def admin_transactions(user_id: Optional[str] = Query(None),
                                    side: Optional[str] = Query(None),
                                    limit: int = Query(100, ge=1, le=500),
                                    skip: int = Query(0, ge=0),
                                    admin=Depends(get_current_admin)):
        rows = await engine.admin_transactions(user_id=user_id, side=side,
                                                 limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    @a.get("/users")
    async def admin_users(limit: int = Query(100, ge=1, le=500),
                             admin=Depends(get_current_admin)):
        rows = await engine.admin_users(limit=limit)
        return {"items": rows, "count": len(rows)}

    @a.get("/audit")
    async def admin_audit(limit: int = Query(100, ge=1, le=500),
                            admin=Depends(get_current_admin)):
        rows = await engine.audit(limit=limit)
        return {"items": rows, "count": len(rows)}

    @a.get("/providers")
    async def admin_providers(admin=Depends(get_current_admin)):
        from .providers import PROVIDER_REGISTRY, get_provider
        out = []
        for name in PROVIDER_REGISTRY:
            p = get_provider(db, name)
            out.append({"name": p.name, "real": getattr(p, "real", False),
                        "configured": p.is_configured(),
                        "active": (name == engine.config.get("provider"))})
        return {"providers": out, "active": engine.config.get("provider")}

    app.include_router(u); app.include_router(a)
    return {"user": u, "admin": a}
