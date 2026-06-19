"""Investment Calculator — saved plans CRUD (per user).
Collection: `saved_plans` with `plan_id` unique.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

_db = None
_get_current_user = None

CALC_TYPES = {"onetime", "sip", "daily", "compound"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    calc_type: str
    amount: float = Field(..., gt=0)
    duration: float = Field(..., gt=0)
    rate_pct: float = Field(..., ge=0)
    reinvest: bool = False
    # Computed result snapshot (client-computed, stored for display)
    invested: float = Field(..., ge=0)
    profit: float = Field(..., ge=0)
    maturity: float = Field(..., ge=0)
    growth: float = Field(..., ge=0)
    notes: Optional[str] = Field(None, max_length=300)


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    notes: Optional[str] = Field(None, max_length=300)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for key in ("created_at", "updated_at"):
        if isinstance(out.get(key), datetime):
            out[key] = out[key].isoformat()
    return out


def attach(api: APIRouter, db, get_current_user_fn):
    global _db, _get_current_user
    _db = db
    _get_current_user = get_current_user_fn

    r = APIRouter(prefix="/calculator/plans", tags=["calculator-plans"])

    @r.post("")
    async def create_plan(req: PlanCreate, user=Depends(_get_current_user)):
        if req.calc_type not in CALC_TYPES:
            raise HTTPException(400, f"Invalid calc_type. Allowed: {sorted(CALC_TYPES)}")
        # Enforce per-user cap (50 plans)
        count = await _db.saved_plans.count_documents({"user_id": user["user_id"]})
        if count >= 50:
            raise HTTPException(400, "Plan limit (50) reached. Delete some plans first.")
        plan = {
            "plan_id": str(uuid.uuid4()),
            "user_id": user["user_id"],
            "name": req.name.strip(),
            "calc_type": req.calc_type,
            "amount": float(req.amount),
            "duration": float(req.duration),
            "rate_pct": float(req.rate_pct),
            "reinvest": bool(req.reinvest),
            "invested": float(req.invested),
            "profit": float(req.profit),
            "maturity": float(req.maturity),
            "growth": float(req.growth),
            "notes": (req.notes or "").strip() or None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await _db.saved_plans.insert_one(plan)
        return _serialize(plan)

    @r.get("")
    async def list_plans(user=Depends(_get_current_user)) -> List[Dict[str, Any]]:
        cur = _db.saved_plans.find({"user_id": user["user_id"]}).sort("created_at", -1)
        return [_serialize(d) async for d in cur]

    @r.get("/{plan_id}")
    async def get_plan(plan_id: str, user=Depends(_get_current_user)):
        doc = await _db.saved_plans.find_one({"plan_id": plan_id, "user_id": user["user_id"]})
        if not doc:
            raise HTTPException(404, "Plan not found")
        return _serialize(doc)

    @r.put("/{plan_id}")
    async def update_plan(plan_id: str, req: PlanUpdate, user=Depends(_get_current_user)):
        patch: Dict[str, Any] = {"updated_at": _now()}
        if req.name is not None:
            patch["name"] = req.name.strip()
        if req.notes is not None:
            patch["notes"] = req.notes.strip() or None
        if len(patch) == 1:
            raise HTTPException(400, "Nothing to update")
        res = await _db.saved_plans.find_one_and_update(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$set": patch},
            return_document=ReturnDocument.AFTER,
        )
        if not res:
            raise HTTPException(404, "Plan not found")
        return _serialize(res)

    @r.delete("/{plan_id}")
    async def delete_plan(plan_id: str, user=Depends(_get_current_user)):
        res = await _db.saved_plans.delete_one({"plan_id": plan_id, "user_id": user["user_id"]})
        if res.deleted_count == 0:
            raise HTTPException(404, "Plan not found")
        return {"ok": True, "plan_id": plan_id}

    api.include_router(r)
