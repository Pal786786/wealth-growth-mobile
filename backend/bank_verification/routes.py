"""Routes for bank-verification (Sprint 12.1)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .engine import BankVerificationEngine
from .providers import REGISTRY


class ConfigPatch(BaseModel):
    provider: Optional[str] = None
    env: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    min_name_match_score: Optional[int] = None
    auto_switch_on_failure: Optional[bool] = None
    dedup_window_hours: Optional[int] = None


def attach(app, db, get_current_user, get_current_admin, engine: BankVerificationEngine):
    u = APIRouter(prefix="/api/bank-verification", tags=["bank-verification"])
    a = APIRouter(prefix="/api/admin/bank-verification", tags=["bank-verification-admin"])

    # ---------------- USER ----------------
    @u.get("/config")
    async def user_cfg(user=Depends(get_current_user)):
        return engine.public_config()

    @u.post("/verify/{bank_id}")
    async def verify(bank_id: str, force: bool = False, user=Depends(get_current_user)):
        try:
            return await engine.verify_bank(user["user_id"], bank_id, force=force)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @u.post("/primary/{bank_id}")
    async def set_primary(bank_id: str, user=Depends(get_current_user)):
        try:
            return await engine.set_primary(user["user_id"], bank_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @u.get("/history")
    async def my_history(bank_id: Optional[str] = None,
                          limit: int = Query(50, ge=1, le=200),
                          user=Depends(get_current_user)):
        rows = await engine.history(user_id=user["user_id"], bank_id=bank_id, limit=limit)
        return {"items": rows, "count": len(rows)}

    # ---------------- ADMIN ----------------
    @a.get("/config")
    async def cfg(admin=Depends(get_current_admin)):
        # Never return the secret in plaintext
        c = dict(engine.config)
        if c.get("client_secret"):
            c["client_secret"] = "•••" + c["client_secret"][-4:]
        return c

    @a.put("/config")
    async def cfg_put(body: ConfigPatch, admin=Depends(get_current_admin)):
        patch = body.model_dump(exclude_none=True)
        # If user posted the masked secret placeholder, drop it (don't overwrite)
        if patch.get("client_secret", "").startswith("•••"):
            patch.pop("client_secret", None)
        return await engine.patch_config(patch, admin_id=admin.get("admin_id") or "admin")

    @a.post("/test-connection")
    async def test(admin=Depends(get_current_admin)):
        return await engine.test_connection()

    @a.get("/providers")
    async def providers(admin=Depends(get_current_admin)):
        return {"registry": list(REGISTRY), "active": engine.config.get("provider")}

    @a.get("/history")
    async def all_history(user_id: Optional[str] = None,
                             bank_id: Optional[str] = None,
                             limit: int = Query(200, ge=1, le=1000),
                             skip: int = Query(0, ge=0),
                             admin=Depends(get_current_admin)):
        rows = await engine.history(user_id=user_id, bank_id=bank_id, limit=limit, skip=skip)
        return {"items": rows, "count": len(rows)}

    app.include_router(u)
    app.include_router(a)
    return {"user": u, "admin": a}
