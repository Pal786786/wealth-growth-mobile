"""MFB Rewards — Campaign Engine (admin CRUD + activation logic)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import wallet as W
from . import engine


async def create_campaign(db, *, name: str, reward: int, start_date: datetime,
                          end_date: datetime, conditions: Optional[Dict[str, Any]] = None,
                          description: str = "", max_users: Optional[int] = None,
                          target_users: Optional[List[str]] = None,
                          created_by: str = "admin") -> Dict[str, Any]:
    doc = {
        "campaign_id":   W.gen_id("camp"),
        "name":          name,
        "description":   description,
        "reward":        int(reward),
        "start_date":    start_date,
        "end_date":      end_date,
        "conditions":    conditions or {},
        "status":        "draft",
        "target_users": target_users or "all",
        "max_users":     max_users,
        "usage_count":   0,
        "created_by":    created_by,
        "created_at":    W.now_utc(),
        "updated_at":    W.now_utc(),
    }
    await db[W.COLL_CAMPAIGNS].insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_campaign(db, campaign_id: str, **patch) -> Optional[Dict[str, Any]]:
    patch = {k: v for k, v in patch.items() if v is not None}
    patch["updated_at"] = W.now_utc()
    updated = await db[W.COLL_CAMPAIGNS].find_one_and_update(
        {"campaign_id": campaign_id}, {"$set": patch}, return_document=True, projection={"_id": 0})
    return updated


async def set_status(db, campaign_id: str, status: str) -> Optional[Dict[str, Any]]:
    if status not in {"draft", "active", "paused", "ended"}:
        raise ValueError("invalid_status")
    return await update_campaign(db, campaign_id, status=status)


async def list_campaigns(db, *, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    q = {}
    if status:
        q["status"] = status
    cur = db[W.COLL_CAMPAIGNS].find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [d async for d in cur]


async def get_campaign(db, campaign_id: str) -> Optional[Dict[str, Any]]:
    return await db[W.COLL_CAMPAIGNS].find_one({"campaign_id": campaign_id}, {"_id": 0})


async def active_campaigns(db) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cur = db[W.COLL_CAMPAIGNS].find({
        "status": "active",
        "start_date": {"$lte": now},
        "end_date":   {"$gte": now},
    }, {"_id": 0}).sort("end_date", 1)
    return [d async for d in cur]


async def auto_close_expired(db) -> Dict[str, int]:
    """Set status='ended' on any active campaign whose end_date has passed."""
    now = datetime.now(timezone.utc)
    result = await db[W.COLL_CAMPAIGNS].update_many(
        {"status": "active", "end_date": {"$lt": now}},
        {"$set": {"status": "ended", "updated_at": now}},
    )
    return {"ended": result.modified_count}


async def claim_campaign(db, campaign_id: str, user_id: str) -> Dict[str, Any]:
    """User-triggered claim. Awards the campaign’s reward once per user."""
    camp = await get_campaign(db, campaign_id)
    if not camp:
        raise ValueError("campaign_not_found")
    if camp.get("status") != "active":
        raise ValueError("campaign_not_active")
    now = datetime.now(timezone.utc)
    def _aware(d):
        if isinstance(d, datetime) and d.tzinfo is None:
            return d.replace(tzinfo=timezone.utc)
        return d
    start = _aware(camp.get("start_date"))
    end   = _aware(camp.get("end_date"))
    if start and start > now:
        raise ValueError("campaign_not_started")
    if end and end < now:
        raise ValueError("campaign_ended")

    target = camp.get("target_users")
    if isinstance(target, list) and user_id not in target:
        raise ValueError("not_in_target")

    if camp.get("max_users") and int(camp["usage_count"]) >= int(camp["max_users"]):
        raise ValueError("campaign_full")

    tx = await engine.award(user_id, "campaign", f"camp:{campaign_id}",
                            amount=int(camp.get("reward", 0)),
                            reason=f"Campaign: {camp.get('name')}",
                            meta={"campaign_id": campaign_id, "campaign_name": camp.get("name")})
    if tx.get("skipped") and tx.get("reason") == "duplicate":
        return tx
    await db[W.COLL_CAMPAIGNS].update_one({"campaign_id": campaign_id},
                                           {"$inc": {"usage_count": 1}})
    return {"ok": True, "tx": tx}
