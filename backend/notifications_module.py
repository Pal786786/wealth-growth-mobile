"""Sprint 5 — Push Notification Center
Extends existing db.notifications with:
  - Rich categories & preferences
  - Admin compose w/ segments, scheduling, image, deeplink, priority, expiry
  - Auto-notification helpers exposed as emit(...)
  - Analytics (delivered, opened, CTR)
  - Audit log & duplicate/rate-limit protection
"""
from __future__ import annotations

import asyncio
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

# --- module-level state (injected by attach) ---
_db = None
_get_current_user: Optional[Callable] = None
_get_current_admin: Optional[Callable] = None
_send_push: Optional[Callable] = None
_log_action: Optional[Callable] = None
_logger = None

# Categories used across the app (extend as new modules land)
CATEGORIES = [
    "wallet", "withdrawals", "kyc", "ai", "investments",
    "gold", "sip", "promotions", "security", "announcements", "system",
    "market_news", "payment", "price_alert",
]
CATEGORY_LABELS = {
    "wallet": "Wallet", "withdrawals": "Withdrawals", "kyc": "KYC",
    "ai": "AI Advisor", "investments": "Investments", "gold": "Gold",
    "sip": "SIP", "promotions": "Promotions", "security": "Security",
    "announcements": "Announcements", "system": "System",
    "market_news": "Market News", "payment": "Payments",
    "price_alert": "Price Alerts",
}

# Preference group each category maps to (so a user disabling "marketing" mutes all promo categories)
CATEGORY_TO_GROUP = {
    "wallet": "wallet_alerts", "withdrawals": "wallet_alerts", "kyc": "system_notifications",
    "ai": "ai_alerts", "investments": "investment_alerts", "gold": "investment_alerts",
    "sip": "investment_alerts", "promotions": "marketing", "security": "security_alerts",
    "announcements": "system_notifications", "system": "system_notifications",
    "market_news": "ai_alerts", "payment": "wallet_alerts",
    "price_alert": "ai_alerts",
}
DEFAULT_PREFS = {
    "wallet_alerts": True, "investment_alerts": True, "ai_alerts": True,
    "marketing": True, "security_alerts": True, "system_notifications": True,
    "push_enabled": True, "email_enabled": False, "sms_enabled": False,
}

TARGET_TYPES = ["all", "user", "segment"]
SEGMENTS = ["kyc_pending", "kyc_approved", "wallet_users", "premium_users"]
PRIORITIES = ["low", "normal", "high", "critical"]

def _now() -> datetime: return datetime.utcnow()


def _as_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# ================= Public helper: emit(...) — called from other modules =================
async def emit(
    user_id: str, *,
    category: str,
    title: str,
    body: str,
    deeplink: str = "/",
    image: Optional[str] = None,
    action_label: Optional[str] = None,
    priority: str = "normal",
    dedupe_key: Optional[str] = None,
    send_push: bool = True,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Create + push a notification for a single user honouring preferences.
    Returns notif_id (or None if skipped due to prefs / dedupe)."""
    if _db is None:
        return None
    cat = category if category in CATEGORIES else "system"
    group = CATEGORY_TO_GROUP.get(cat, "system_notifications")

    prefs = await get_user_prefs(user_id)
    if not prefs.get(group, True):
        return None  # user disabled this category

    if dedupe_key:
        # Prevent duplicate within 5 minutes
        recent = await _db.notifications.find_one({
            "user_id": user_id, "dedupe_key": dedupe_key,
            "created_at": {"$gte": _now() - timedelta(minutes=5)}
        })
        if recent:
            return None

    nid = f"nf_{secrets.token_hex(6)}"
    doc = {
        "notif_id": nid, "user_id": user_id,
        "category": cat, "title": title, "body": body,
        "deeplink": deeplink, "image": image,
        "action_label": action_label, "priority": priority if priority in PRIORITIES else "normal",
        "read": False, "delivered": True, "opened_at": None,
        "meta": meta or {}, "dedupe_key": dedupe_key,
        "campaign_id": None, "source": "auto",
        "created_at": _now(), "expires_at": None,
    }
    try:
        await _db.notifications.insert_one(doc)
    except Exception as e:  # pragma: no cover
        if _logger: _logger.warning(f"notif insert fail: {e}")
        return None

    # Push (if enabled + delivery method allowed)
    if send_push and prefs.get("push_enabled", True) and _send_push:
        try:
            await _send_push(recipients=[user_id],
                             data={"title": title, "message": body, "action_url": deeplink,
                                   "image": image or "", "notif_id": nid, "category": cat})
        except Exception:
            pass
    return nid


async def get_user_prefs(user_id: str) -> Dict[str, Any]:
    doc = await _db.notification_prefs.find_one({"user_id": user_id}) or {}
    merged = {**DEFAULT_PREFS}
    for k in DEFAULT_PREFS:
        if k in doc:
            merged[k] = bool(doc[k])
    return merged


# ================= Pydantic models =================
class PrefsPatch(BaseModel):
    wallet_alerts: Optional[bool] = None
    investment_alerts: Optional[bool] = None
    ai_alerts: Optional[bool] = None
    marketing: Optional[bool] = None
    security_alerts: Optional[bool] = None
    system_notifications: Optional[bool] = None
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None


class MarkReadBatch(BaseModel):
    ids: Optional[List[str]] = None  # if None => mark all


class ComposeReq(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1, max_length=1000)
    category: str = "announcements"
    priority: str = "normal"
    deeplink: str = "/"
    image: Optional[str] = None
    action_label: Optional[str] = None
    # target
    target_type: str = "all"  # all|user|segment
    target_user_id: Optional[str] = None
    target_segment: Optional[str] = None
    # scheduling
    schedule_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    send_push: bool = True


# ================= User routes =================
user_router = APIRouter(prefix="/notifications", tags=["notifications-user"])
admin_router = APIRouter(prefix="/admin/notifications", tags=["notifications-admin"])


async def _user_dep(request: Request):
    if _get_current_user is None:
        raise HTTPException(status_code=503, detail="Auth not attached")
    return await _get_current_user(request.headers.get("authorization"))

async def _admin_dep(request: Request):
    if _get_current_admin is None:
        raise HTTPException(status_code=503, detail="Admin auth not attached")
    return await _get_current_admin(request.headers.get("authorization"))


@user_router.get("")
async def list_notifications(
    limit: int = Query(50, le=200),
    skip: int = 0,
    category: Optional[str] = None,
    unread_only: bool = False,
    q: Optional[str] = None,
    user: Dict[str, Any] = Depends(_user_dep),
):
    filt: Dict[str, Any] = {"user_id": user["user_id"]}
    if category and category != "all":
        filt["category"] = category
    if unread_only:
        filt["read"] = False
    if q:
        filt["$or"] = [
            {"title": {"$regex": re.escape(q), "$options": "i"}},
            {"body": {"$regex": re.escape(q), "$options": "i"}},
        ]
    rows = await _db.notifications.find(filt, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await _db.notifications.count_documents(filt)
    unread = await _db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    # per-category counts
    pipeline = [
        {"$match": {"user_id": user["user_id"]}},
        {"$group": {"_id": {"category": "$category", "read": "$read"}, "count": {"$sum": 1}}},
    ]
    grouped = await _db.notifications.aggregate(pipeline).to_list(200)
    per_category: Dict[str, Dict[str, int]] = {c: {"total": 0, "unread": 0} for c in CATEGORIES}
    for g in grouped:
        c = (g["_id"] or {}).get("category", "system")
        if c not in per_category:
            per_category[c] = {"total": 0, "unread": 0}
        per_category[c]["total"] += int(g["count"])
        if not (g["_id"] or {}).get("read", True):
            per_category[c]["unread"] += int(g["count"])
    return {"items": rows, "total": total, "unread": unread, "per_category": per_category, "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()]}


@user_router.get("/unread-count")
async def unread_count(user: Dict[str, Any] = Depends(_user_dep)):
    return {"unread": await _db.notifications.count_documents({"user_id": user["user_id"], "read": False})}


@user_router.post("/{nid}/read")
async def mark_one_read(nid: str, user: Dict[str, Any] = Depends(_user_dep)):
    r = await _db.notifications.update_one(
        {"notif_id": nid, "user_id": user["user_id"]},
        {"$set": {"read": True, "opened_at": _now()}}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    # bump campaign opened counter if applicable
    doc = await _db.notifications.find_one({"notif_id": nid}, {"_id": 0, "campaign_id": 1})
    if doc and doc.get("campaign_id"):
        await _db.notification_campaigns.update_one({"campaign_id": doc["campaign_id"]}, {"$inc": {"opened": 1}})
    return {"ok": True}


@user_router.post("/mark-read")
async def mark_batch(body: MarkReadBatch, user: Dict[str, Any] = Depends(_user_dep)):
    filt: Dict[str, Any] = {"user_id": user["user_id"], "read": False}
    if body.ids:
        filt["notif_id"] = {"$in": body.ids}
    r = await _db.notifications.update_many(filt, {"$set": {"read": True, "opened_at": _now()}})
    return {"ok": True, "modified": r.modified_count}


@user_router.delete("/{nid}")
async def delete_notif(nid: str, user: Dict[str, Any] = Depends(_user_dep)):
    r = await _db.notifications.delete_one({"notif_id": nid, "user_id": user["user_id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@user_router.delete("")
async def clear_all(user: Dict[str, Any] = Depends(_user_dep)):
    r = await _db.notifications.delete_many({"user_id": user["user_id"]})
    return {"ok": True, "deleted": r.deleted_count}


@user_router.get("/preferences")
async def get_prefs(user: Dict[str, Any] = Depends(_user_dep)):
    return {"preferences": await get_user_prefs(user["user_id"]), "categories": CATEGORY_LABELS}


@user_router.put("/preferences")
async def put_prefs(body: PrefsPatch, user: Dict[str, Any] = Depends(_user_dep)):
    patch = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await _db.notification_prefs.update_one(
        {"user_id": user["user_id"]},
        {"$set": {**patch, "updated_at": _now(), "user_id": user["user_id"]}},
        upsert=True,
    )
    return {"ok": True, "preferences": await get_user_prefs(user["user_id"])}


# ================= Admin routes =================
async def _resolve_target(req: ComposeReq) -> List[str]:
    """Return list of user_ids to notify based on the compose target."""
    if req.target_type == "user":
        if not req.target_user_id:
            raise HTTPException(status_code=400, detail="target_user_id required")
        u = await _db.users.find_one({"user_id": req.target_user_id}, {"_id": 0, "user_id": 1})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        return [req.target_user_id]

    if req.target_type == "segment":
        seg = req.target_segment
        if seg == "kyc_pending":
            ids = await _db.users.distinct("user_id", {"kyc_status": {"$ne": "approved"}})
            kyc_pending = await _db.kyc_profiles.distinct("user_id", {"status": {"$ne": "approved"}})
            return list(set(ids + kyc_pending))
        if seg == "kyc_approved":
            u = await _db.users.distinct("user_id", {"kyc_status": "approved"})
            k = await _db.kyc_profiles.distinct("user_id", {"status": "approved"})
            return list(set(u + k))
        if seg == "wallet_users":
            return await _db.wallets.distinct("user_id", {"balance": {"$gt": 0}})
        if seg == "premium_users":
            return await _db.users.distinct("user_id", {"tier": {"$in": ["premium", "gold", "platinum"]}})
        raise HTTPException(status_code=400, detail=f"Unknown segment '{seg}'")

    # all
    return await _db.users.distinct("user_id")


async def _dispatch_campaign(campaign_id: str) -> Dict[str, Any]:
    """Fan-out to all target user_ids honoring preferences, updates campaign counters."""
    camp = await _db.notification_campaigns.find_one({"campaign_id": campaign_id})
    if not camp:
        return {"error": "campaign missing"}
    ids: List[str] = camp.get("target_user_ids") or []
    sent = 0
    skipped = 0
    for uid in ids:
        nid = await emit(
            uid,
            category=camp["category"],
            title=camp["title"],
            body=camp["body"],
            deeplink=camp.get("deeplink") or "/",
            image=camp.get("image"),
            action_label=camp.get("action_label"),
            priority=camp.get("priority") or "normal",
            send_push=bool(camp.get("send_push", True)),
        )
        if nid:
            # tag with campaign_id
            await _db.notifications.update_one(
                {"notif_id": nid},
                {"$set": {"campaign_id": campaign_id, "source": "campaign", "expires_at": camp.get("expires_at")}}
            )
            sent += 1
        else:
            skipped += 1
    await _db.notification_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "sent", "sent_at": _now(), "sent_count": sent, "skipped_count": skipped, "total_targets": len(ids)}}
    )
    return {"ok": True, "sent": sent, "skipped": skipped, "total": len(ids)}


@admin_router.post("/compose")
async def admin_compose(body: ComposeReq, admin: Dict[str, Any] = Depends(_admin_dep)):
    if body.target_type not in TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Choose from {CATEGORIES}")
    target_ids = await _resolve_target(body)
    campaign_id = f"cmp_{secrets.token_hex(6)}"
    sched = _as_naive(body.schedule_at)
    exp = _as_naive(body.expires_at)
    scheduled = sched is not None and sched > _now()
    doc = {
        "campaign_id": campaign_id, "title": body.title, "body": body.body,
        "category": body.category, "priority": body.priority,
        "deeplink": body.deeplink, "image": body.image, "action_label": body.action_label,
        "target_type": body.target_type, "target_segment": body.target_segment,
        "target_user_id": body.target_user_id, "target_user_ids": target_ids,
        "schedule_at": sched, "expires_at": exp, "send_push": body.send_push,
        "status": "scheduled" if scheduled else "sending",
        "created_at": _now(),
        "created_by": (admin or {}).get("admin_id") or (admin or {}).get("user_id") or "admin",
        "total_targets": len(target_ids), "sent_count": 0, "skipped_count": 0, "opened": 0,
    }
    await _db.notification_campaigns.insert_one(doc)
    if _log_action:
        try:
            await _log_action(doc["created_by"], "notif_campaign_create",
                              None, {"campaign_id": campaign_id, "target_type": body.target_type, "count": len(target_ids)})
        except Exception:
            pass

    if not scheduled:
        # fire and forget
        asyncio.create_task(_dispatch_campaign(campaign_id))

    doc.pop("_id", None)
    return {"ok": True, "campaign": doc}


@admin_router.get("/campaigns")
async def list_campaigns(q: Optional[str] = None, status: Optional[str] = None,
                         limit: int = 100, admin: Dict[str, Any] = Depends(_admin_dep)):
    filt: Dict[str, Any] = {}
    if q:
        filt["$or"] = [
            {"campaign_id": {"$regex": re.escape(q), "$options": "i"}},
            {"title": {"$regex": re.escape(q), "$options": "i"}},
        ]
    if status:
        filt["status"] = status
    items = await _db.notification_campaigns.find(filt, {"_id": 0, "target_user_ids": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    total = await _db.notification_campaigns.count_documents(filt)
    return {"items": items, "total": total}


@admin_router.get("/campaigns/{cid}")
async def campaign_detail(cid: str, admin: Dict[str, Any] = Depends(_admin_dep)):
    c = await _db.notification_campaigns.find_one({"campaign_id": cid}, {"_id": 0, "target_user_ids": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    # Delivery info
    delivered = await _db.notifications.count_documents({"campaign_id": cid, "delivered": True})
    opened = await _db.notifications.count_documents({"campaign_id": cid, "opened_at": {"$ne": None}})
    c["delivered"] = delivered
    c["opened"] = opened
    c["ctr_pct"] = round((opened / delivered * 100) if delivered > 0 else 0.0, 2)
    return {"campaign": c}


@admin_router.post("/campaigns/{cid}/resend")
async def resend_campaign(cid: str, admin: Dict[str, Any] = Depends(_admin_dep)):
    c = await _db.notification_campaigns.find_one({"campaign_id": cid})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    r = await _dispatch_campaign(cid)
    if _log_action:
        try:
            await _log_action((admin or {}).get("admin_id") or "admin",
                              "notif_campaign_resend", None, {"campaign_id": cid, **r})
        except Exception: pass
    return {"ok": True, **r}


@admin_router.post("/campaigns/{cid}/cancel")
async def cancel_scheduled(cid: str, admin: Dict[str, Any] = Depends(_admin_dep)):
    r = await _db.notification_campaigns.update_one(
        {"campaign_id": cid, "status": "scheduled"},
        {"$set": {"status": "cancelled", "cancelled_at": _now()}}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found or already dispatched")
    return {"ok": True}


@admin_router.get("/analytics")
async def analytics(days: int = 7, admin: Dict[str, Any] = Depends(_admin_dep)):
    now = _now()
    since = now - timedelta(days=days)
    total_sent = await _db.notifications.count_documents({"created_at": {"$gte": since}})
    delivered = await _db.notifications.count_documents({"delivered": True, "created_at": {"$gte": since}})
    opened = await _db.notifications.count_documents({"opened_at": {"$ne": None}, "created_at": {"$gte": since}})
    failed = await _db.notifications.count_documents({"delivered": False, "created_at": {"$gte": since}})
    ctr = round((opened / delivered * 100) if delivered > 0 else 0.0, 2)

    # per-day series
    chart = []
    for i in range(days):
        d0 = (now - timedelta(days=days - 1 - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        d1 = d0 + timedelta(days=1)
        c_sent = await _db.notifications.count_documents({"created_at": {"$gte": d0, "$lt": d1}})
        c_opened = await _db.notifications.count_documents({"opened_at": {"$gte": d0, "$lt": d1}})
        chart.append({"date": d0.strftime("%Y-%m-%d"), "sent": c_sent, "opened": c_opened})

    # per-category totals
    per_cat_agg = await _db.notifications.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "opened": {"$sum": {"$cond": [{"$ifNull": ["$opened_at", False]}, 1, 0]}}}}
    ]).to_list(50)
    per_category = [{"category": (x["_id"] or "system"), "label": CATEGORY_LABELS.get(x["_id"] or "system", "System"), "sent": x["count"], "opened": x["opened"], "ctr_pct": round((x["opened"] / x["count"] * 100) if x["count"] else 0, 2)} for x in per_cat_agg]
    per_category.sort(key=lambda x: -x["sent"])

    return {
        "range_days": days,
        "totals": {
            "sent": total_sent, "delivered": delivered, "opened": opened, "failed": failed,
            "ctr_pct": ctr, "campaigns": await _db.notification_campaigns.count_documents({"created_at": {"$gte": since}}),
        },
        "chart": chart, "per_category": per_category,
    }


@admin_router.get("/audit")
async def audit_logs(limit: int = 50, admin: Dict[str, Any] = Depends(_admin_dep)):
    items = await _db.admin_audit.find(
        {"action": {"$regex": "^notif_"}}, {"_id": 0}
    ).sort("at", -1).limit(limit).to_list(limit)
    return {"items": items}


# ================= Scheduler =================
_scheduler_task = None

async def _scheduler_loop():
    while True:
        try:
            now = _now()
            due = await _db.notification_campaigns.find(
                {"status": "scheduled", "schedule_at": {"$lte": now}}, {"campaign_id": 1, "_id": 0}
            ).to_list(50)
            for c in due:
                await _db.notification_campaigns.update_one({"campaign_id": c["campaign_id"]}, {"$set": {"status": "sending"}})
                await _dispatch_campaign(c["campaign_id"])
        except Exception as e:  # pragma: no cover
            if _logger: _logger.warning(f"notif scheduler tick err: {e}")
        await asyncio.sleep(30)


def attach(api: APIRouter, *, db, get_current_user: Callable, get_current_admin: Callable,
           send_push: Optional[Callable] = None, log_action: Optional[Callable] = None, logger=None):
    global _db, _get_current_user, _get_current_admin, _send_push, _log_action, _logger, _scheduler_task
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin
    _send_push = send_push
    _log_action = log_action
    _logger = logger
    api.include_router(user_router)
    api.include_router(admin_router)
    if _scheduler_task is None:
        try:
            loop = asyncio.get_event_loop()
            _scheduler_task = loop.create_task(_scheduler_loop())
        except RuntimeError:
            pass  # loop not running yet; will be started on demand
