"""Investment Calculator — admin-configurable settings.
Singleton config doc (_id='active') in `calculator_config` collection.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

_db = None
_get_current_admin = None
_log_action = None

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "min_amount": 100,
    "max_amount": 1000000,
    "types": {
        "onetime":  {"enabled": True, "return_min": 0, "return_max": 100, "return_default": 12, "label": "One Time"},
        "sip":      {"enabled": True, "return_min": 0, "return_max": 30,  "return_default": 12, "label": "SIP"},
        "daily":    {"enabled": True, "return_min": 0, "return_max": 5,   "return_default": 0.5, "label": "Daily"},
        "compound": {"enabled": True, "return_min": 0, "return_max": 50,  "return_default": 15, "label": "Compound"},
    },
}

def _now(): return datetime.now(timezone.utc)

async def seed_config():
    if not await _db.calculator_config.find_one({"_id": "active"}):
        await _db.calculator_config.insert_one({"_id": "active", **DEFAULTS, "updated_at": _now()})

async def get_config() -> Dict[str, Any]:
    doc = await _db.calculator_config.find_one({"_id": "active"}) if _db is not None else None
    if not doc:
        return DEFAULTS
    doc.pop("_id", None)
    return doc

class TypeCfg(BaseModel):
    enabled: bool = True
    return_min: float = Field(0, ge=0)
    return_max: float = Field(100, ge=0)
    return_default: float = Field(10, ge=0)
    label: Optional[str] = None

class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_amount: Optional[float] = Field(None, ge=0)
    max_amount: Optional[float] = Field(None, ge=0)
    types: Optional[Dict[str, TypeCfg]] = None

def attach(api: APIRouter, db, get_current_admin_fn, log_action_fn):
    global _db, _get_current_admin, _log_action
    _db = db
    _get_current_admin = get_current_admin_fn
    _log_action = log_action_fn

    # User-facing (no auth required)
    @api.get("/calculator/config", tags=["calculator"])
    async def public_cfg():
        cfg = await get_config()
        cfg.pop("updated_at", None)
        cfg.pop("updated_by", None)
        return cfg

    r = APIRouter(prefix="/admin/calculator", tags=["admin-calculator"])

    @r.get("/config")
    async def get_admin_cfg(adm=Depends(_get_current_admin)):
        return await get_config()

    @r.put("/config")
    async def update_cfg(req: ConfigUpdate, adm=Depends(_get_current_admin)):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can edit calculator config")
        update: Dict[str, Any] = {"updated_at": _now(), "updated_by": adm["admin_id"]}
        if req.enabled is not None:
            update["enabled"] = req.enabled
        if req.min_amount is not None:
            update["min_amount"] = req.min_amount
        if req.max_amount is not None:
            update["max_amount"] = req.max_amount
        if req.min_amount is not None and req.max_amount is not None and req.min_amount >= req.max_amount:
            raise HTTPException(400, "min_amount must be less than max_amount")
        if req.types:
            for k, v in req.types.items():
                if v.return_min >= v.return_max:
                    raise HTTPException(400, f"{k}: return_min must be less than return_max")
            update["types"] = {k: v.model_dump() for k, v in req.types.items()}
        await _db.calculator_config.update_one({"_id": "active"}, {"$set": update}, upsert=True)
        await _log_action(adm["admin_id"], "calculator.updated", target="calculator_config", meta={"keys": list(update.keys())})
        return await get_config()

    api.include_router(r)
