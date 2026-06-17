"""Editable tier configuration — replaces hardcoded TIERS list.

Schema:
  tier_config (singleton doc, _id="active"):
    { _id, tiers: [{id, name, min, rate, color, emoji, tagline, points_multiplier,
                    perks: [{text, enabled}], max_cashback_rate}], updated_at, updated_by }
  tier_config_history (rollback log):
    { history_id, snapshot, action, updated_by, at, reason }
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

_db = None
_get_current_admin = None
_log_action = None

MAX_CASHBACK_RATE_PCT = 10.0  # safety cap: no tier can exceed 10% cashback

DEFAULT_TIERS: List[Dict[str, Any]] = [
    {"id": "bronze",   "name": "Bronze",   "min": 0,     "rate": 0.005, "color": "#CD7F32", "emoji": "🥉",
     "tagline": "Welcome to the family!", "points_multiplier": 1.0,
     "perks": [{"text": "0.5% cashback on every spend", "enabled": True},
               {"text": "Basic email support", "enabled": True},
               {"text": "Birthday wish from us 🎂", "enabled": True}]},
    {"id": "silver",   "name": "Silver",   "min": 500,   "rate": 0.008, "color": "#94A3B8", "emoji": "🥈",
     "tagline": "You're moving up — keep going!", "points_multiplier": 1.0,
     "perks": [{"text": "0.8% cashback on every spend", "enabled": True},
               {"text": "Priority email support", "enabled": True},
               {"text": "Free virtual debit card", "enabled": True},
               {"text": "Birthday bonus ₹100", "enabled": True}]},
    {"id": "gold",     "name": "Gold",     "min": 2000,  "rate": 0.012, "color": "#F59E0B", "emoji": "🥇",
     "tagline": "You've struck Gold! 🌟", "points_multiplier": 2.0,
     "perks": [{"text": "1.2% cashback on every spend", "enabled": True},
               {"text": "2× points on travel & insurance", "enabled": True},
               {"text": "24/7 chat support", "enabled": True},
               {"text": "Birthday bonus ₹250", "enabled": True}]},
    {"id": "platinum", "name": "Platinum", "min": 5000,  "rate": 0.018, "color": "#0EA5E9", "emoji": "💎",
     "tagline": "Elite status unlocked! 💎", "points_multiplier": 3.0,
     "perks": [{"text": "1.8% cashback on every spend", "enabled": True},
               {"text": "3× points on travel & insurance", "enabled": True},
               {"text": "Dedicated relationship manager", "enabled": True},
               {"text": "2 free airport lounge visits / yr", "enabled": True},
               {"text": "Zero ATM withdrawal charges", "enabled": True},
               {"text": "Birthday bonus ₹500", "enabled": True}]},
    {"id": "diamond",  "name": "Diamond",  "min": 10000, "rate": 0.025, "color": "#A78BFA", "emoji": "👑",
     "tagline": "The pinnacle of luxury banking 👑", "points_multiplier": 5.0,
     "perks": [{"text": "2.5% cashback on every spend", "enabled": True},
               {"text": "5× points on travel & insurance", "enabled": True},
               {"text": "Premium 24/7 concierge service", "enabled": True},
               {"text": "Unlimited free transfers (IMPS/NEFT/UPI)", "enabled": True},
               {"text": "Exclusive curated investment products", "enabled": True},
               {"text": "Unlimited airport lounge access", "enabled": True},
               {"text": "Birthday bonus ₹1,000", "enabled": True}]},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_config():
    """Insert default config if none exists. Never overwrites."""
    doc = await _db.tier_config.find_one({"_id": "active"})
    if not doc:
        await _db.tier_config.insert_one({
            "_id": "active", "tiers": DEFAULT_TIERS,
            "updated_at": _now(), "updated_by": "__system__",
        })


async def get_tiers() -> List[Dict[str, Any]]:
    """Returns active tiers list (live from MongoDB). Falls back to defaults if missing."""
    doc = await _db.tier_config.find_one({"_id": "active"}) if _db is not None else None
    return (doc or {}).get("tiers") or DEFAULT_TIERS


class Perk(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    enabled: bool = True


class TierIn(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=40)
    min: int = Field(..., ge=0)
    rate: float = Field(..., ge=0, le=1)  # 0..1 (0.025 = 2.5%)
    color: str = "#94A3B8"
    emoji: str = ""
    tagline: str = ""
    points_multiplier: float = Field(1.0, ge=0, le=20)
    perks: List[Perk] = []


class TiersUpdateReq(BaseModel):
    tiers: List[TierIn]
    reason: Optional[str] = "Admin update"


def _validate_tiers(tiers: List[Dict[str, Any]]):
    if len(tiers) < 2:
        raise HTTPException(400, "At least 2 tiers required")
    # Cashback cap
    for t in tiers:
        if t["rate"] * 100 > MAX_CASHBACK_RATE_PCT:
            raise HTTPException(400, f"Tier '{t['name']}' cashback {t['rate']*100}% exceeds max {MAX_CASHBACK_RATE_PCT}%")
    # Strictly increasing thresholds
    sorted_t = sorted(tiers, key=lambda x: x["min"])
    seen = set()
    prev = -1
    for t in sorted_t:
        if t["min"] <= prev and t["min"] != 0:
            raise HTTPException(400, f"Tier thresholds must be strictly increasing (got {t['name']}={t['min']} after {prev})")
        if t["id"] in seen:
            raise HTTPException(400, f"Duplicate tier id '{t['id']}'")
        seen.add(t["id"])
        prev = t["min"]
    # Cashback should generally also be increasing with threshold
    for i in range(1, len(sorted_t)):
        if sorted_t[i]["rate"] < sorted_t[i-1]["rate"]:
            raise HTTPException(400, f"Cashback for '{sorted_t[i]['name']}' ({sorted_t[i]['rate']*100}%) is lower than '{sorted_t[i-1]['name']}' ({sorted_t[i-1]['rate']*100}%)")


def attach(api: APIRouter, db, get_current_admin_fn, log_action_fn):
    global _db, _get_current_admin, _log_action
    _db = db
    _get_current_admin = get_current_admin_fn
    _log_action = log_action_fn

    r = APIRouter(prefix="/admin/tier-config", tags=["admin-tier-config"])

    def _ensure(adm):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can edit tier config")

    @r.get("")
    async def get_config(adm=Depends(_get_current_admin)):
        # finance/support can view (read-only)
        doc = await _db.tier_config.find_one({"_id": "active"})
        if not doc:
            await seed_config()
            doc = await _db.tier_config.find_one({"_id": "active"})
        # Users affected per tier
        agg = await _db.users.aggregate([
            {"$group": {"_id": {"$ifNull": ["$tier_id", "bronze"]}, "c": {"$sum": 1}}},
        ]).to_list(20)
        users_by_tier = {a["_id"]: a["c"] for a in agg}
        for t in doc["tiers"]:
            t["users_affected"] = users_by_tier.get(t["id"], 0)
        return {
            "tiers": doc["tiers"],
            "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by"),
            "max_cashback_rate_pct": MAX_CASHBACK_RATE_PCT,
        }

    @r.put("")
    async def update_config(req: TiersUpdateReq, adm=Depends(_get_current_admin)):
        _ensure(adm)
        new_tiers = [t.model_dump() for t in req.tiers]
        _validate_tiers(new_tiers)

        # Snapshot current config to history before overwriting
        current = await _db.tier_config.find_one({"_id": "active"})
        if current:
            await _db.tier_config_history.insert_one({
                "history_id": f"tch_{uuid.uuid4().hex[:12]}",
                "snapshot": current.get("tiers", []),
                "action": "replaced",
                "updated_by": adm["admin_id"],
                "at": _now(),
                "reason": req.reason or "",
            })
        # Compute impact: which fields changed for each tier
        impact: List[Dict[str, Any]] = []
        prev_by_id = {t["id"]: t for t in (current or {}).get("tiers", [])}
        for t in new_tiers:
            old = prev_by_id.get(t["id"]) or {}
            changes = []
            for k in ("rate", "min", "points_multiplier"):
                if old.get(k) != t.get(k):
                    changes.append({"field": k, "old": old.get(k), "new": t.get(k)})
            if changes:
                impact.append({"tier": t["name"], "changes": changes})

        await _db.tier_config.update_one(
            {"_id": "active"},
            {"$set": {"tiers": new_tiers, "updated_at": _now(), "updated_by": adm["admin_id"]}},
            upsert=True,
        )
        await _log_action(adm["admin_id"], "tier.updated", target="tier_config",
                          meta={"impact": impact, "reason": req.reason})
        return {"ok": True, "tiers": new_tiers, "impact": impact, "history_recorded": bool(current)}

    @r.get("/history")
    async def list_history(adm=Depends(_get_current_admin), limit: int = 20):
        rows = await _db.tier_config_history.find({}, {"_id": 0}).sort("at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
        return {"items": rows, "total": len(rows)}

    @r.post("/rollback/{history_id}")
    async def rollback(history_id: str, adm=Depends(_get_current_admin)):
        _ensure(adm)
        snap = await _db.tier_config_history.find_one({"history_id": history_id})
        if not snap:
            raise HTTPException(404, "History entry not found")
        # Save current as new history before rollback
        current = await _db.tier_config.find_one({"_id": "active"})
        if current:
            await _db.tier_config_history.insert_one({
                "history_id": f"tch_{uuid.uuid4().hex[:12]}", "snapshot": current.get("tiers", []),
                "action": "pre_rollback", "updated_by": adm["admin_id"], "at": _now(),
                "reason": f"Rolling back to {history_id}",
            })
        await _db.tier_config.update_one(
            {"_id": "active"},
            {"$set": {"tiers": snap["snapshot"], "updated_at": _now(), "updated_by": adm["admin_id"]}},
            upsert=True,
        )
        await _log_action(adm["admin_id"], "tier.rollback", target=history_id, meta={"reason": "rollback"})
        return {"ok": True, "rolled_back_to": history_id}

    api.include_router(r)
