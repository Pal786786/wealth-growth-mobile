"""Extended admin endpoints — notifications, investment manager, content, reports, settings."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from admin import get_current_admin, _log_action, _hash, ROLES, ROLE_LABEL  # type: ignore

_db = None


# ---------- Models ----------
class NotificationReq(BaseModel):
    title: str
    body: str
    target: str = "all"   # "all" | "user" | "segment"
    user_id: Optional[str] = None
    segment: Optional[str] = None  # "kyc_pending" | "active" | "investors"


class FundReq(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    nav: float
    returns_1y: float
    risk: str


class FDReq(BaseModel):
    id: Optional[str] = None
    name: str
    tenure_months: int
    interest_rate: float


class GovtReq(BaseModel):
    id: Optional[str] = None
    name: str
    rate: float
    tenure: str


class GoldRateReq(BaseModel):
    price_per_gram: float


class BannerReq(BaseModel):
    id: Optional[str] = None
    title: str
    subtitle: Optional[str] = ""
    image_url: Optional[str] = ""
    cta_label: Optional[str] = "Explore"
    cta_route: Optional[str] = "/"
    active: bool = True
    order: int = 0


class OfferReq(BaseModel):
    id: Optional[str] = None
    title: str
    description: str
    code: Optional[str] = None
    discount_pct: Optional[float] = None
    expires_at: Optional[str] = None
    active: bool = True


class SettingsReq(BaseModel):
    referral_bonus: Optional[float] = None
    cashback_pct: Optional[float] = None
    sip_min_amount: Optional[float] = None
    otp_enabled: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    welcome_bonus: Optional[float] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


router = APIRouter(prefix="/admin", tags=["admin-extra"])


# ---------- Notifications ----------
@router.post("/notifications/send")
async def send_notification(req: NotificationReq, admin=Depends(get_current_admin)):
    user_ids: List[str] = []
    if req.target == "all":
        users = await _db.users.find({}, {"_id": 0, "user_id": 1}).to_list(10000)
        user_ids = [u["user_id"] for u in users]
    elif req.target == "user" and req.user_id:
        user_ids = [req.user_id]
    elif req.target == "segment":
        q: Dict[str, Any] = {}
        if req.segment == "kyc_pending":
            q["kyc_status"] = "pending"
        elif req.segment == "active":
            q["suspended"] = {"$ne": True}
        elif req.segment == "investors":
            inv = await _db.holdings.distinct("user_id")
            q["user_id"] = {"$in": inv}
        users = await _db.users.find(q, {"_id": 0, "user_id": 1}).to_list(10000)
        user_ids = [u["user_id"] for u in users]

    if not user_ids:
        raise HTTPException(status_code=400, detail="No recipients matched")

    batch_id = _id("notif")
    docs = [{
        "notif_id": _id("nf"),
        "batch_id": batch_id,
        "user_id": uid,
        "title": req.title,
        "body": req.body,
        "read": False,
        "created_at": _now(),
    } for uid in user_ids]
    await _db.notifications.insert_many(docs)

    await _db.notification_batches.insert_one({
        "batch_id": batch_id,
        "title": req.title,
        "body": req.body,
        "target": req.target,
        "segment": req.segment,
        "recipients": len(user_ids),
        "sent_by": admin["admin_id"],
        "sent_at": _now(),
    })
    await _log_action(admin["admin_id"], "notification.send", target=batch_id, meta={"recipients": len(user_ids)})
    return {"success": True, "batch_id": batch_id, "recipients": len(user_ids)}


@router.get("/notifications/history")
async def notif_history(admin=Depends(get_current_admin)):
    return await _db.notification_batches.find({}, {"_id": 0}).sort("sent_at", -1).limit(50).to_list(50)


# ---------- Investment Manager ----------
async def _get_or_seed(coll: str, defaults: list):
    if await _db[coll].count_documents({}) == 0 and defaults:
        await _db[coll].insert_many([{**d} for d in defaults])
    return await _db[coll].find({}, {"_id": 0}).to_list(200)


@router.get("/invest/funds")
async def get_funds(admin=Depends(get_current_admin)):
    return await _db.mfb_funds.find({}, {"_id": 0}).to_list(200)


@router.post("/invest/funds")
async def upsert_fund(req: FundReq, admin=Depends(get_current_admin)):
    fid = req.id or _id("mf")
    doc = req.dict(); doc["id"] = fid
    await _db.mfb_funds.update_one({"id": fid}, {"$set": doc}, upsert=True)
    await _log_action(admin["admin_id"], "invest.fund.upsert", target=fid)
    return doc


@router.delete("/invest/funds/{fid}")
async def del_fund(fid: str, admin=Depends(get_current_admin)):
    await _db.mfb_funds.delete_one({"id": fid})
    await _log_action(admin["admin_id"], "invest.fund.delete", target=fid)
    return {"success": True}


@router.get("/invest/fds")
async def get_fds(admin=Depends(get_current_admin)):
    return await _db.mfb_fds.find({}, {"_id": 0}).to_list(200)


@router.post("/invest/fds")
async def upsert_fd(req: FDReq, admin=Depends(get_current_admin)):
    fid = req.id or _id("fd")
    doc = req.dict(); doc["id"] = fid
    await _db.mfb_fds.update_one({"id": fid}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/invest/fds/{fid}")
async def del_fd(fid: str, admin=Depends(get_current_admin)):
    await _db.mfb_fds.delete_one({"id": fid})
    return {"success": True}


@router.get("/invest/govt")
async def get_govt(admin=Depends(get_current_admin)):
    return await _db.mfb_govt.find({}, {"_id": 0}).to_list(200)


@router.post("/invest/govt")
async def upsert_govt(req: GovtReq, admin=Depends(get_current_admin)):
    gid = req.id or _id("gv")
    doc = req.dict(); doc["id"] = gid
    await _db.mfb_govt.update_one({"id": gid}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/invest/govt/{gid}")
async def del_govt(gid: str, admin=Depends(get_current_admin)):
    await _db.mfb_govt.delete_one({"id": gid})
    return {"success": True}


@router.post("/invest/gold-rate")
async def set_gold_rate(req: GoldRateReq, admin=Depends(get_current_admin)):
    await _db.app_settings.update_one(
        {"_key": "gold_rate"},
        {"$set": {"_key": "gold_rate", "price_per_gram": req.price_per_gram, "updated_at": _now()}},
        upsert=True,
    )
    await _log_action(admin["admin_id"], "invest.gold.rate", meta={"price": req.price_per_gram})
    return {"success": True, "price_per_gram": req.price_per_gram}


# ---------- Content Manager ----------
@router.get("/content/banners")
async def list_banners(admin=Depends(get_current_admin)):
    return await _db.banners.find({}, {"_id": 0}).sort("order", 1).to_list(50)


@router.post("/content/banners")
async def upsert_banner(req: BannerReq, admin=Depends(get_current_admin)):
    bid = req.id or _id("bnr")
    doc = req.dict(); doc["id"] = bid
    doc["updated_at"] = _now()
    await _db.banners.update_one({"id": bid}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/content/banners/{bid}")
async def del_banner(bid: str, admin=Depends(get_current_admin)):
    await _db.banners.delete_one({"id": bid})
    return {"success": True}


@router.get("/content/offers")
async def list_offers(admin=Depends(get_current_admin)):
    return await _db.offers.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/content/offers")
async def upsert_offer(req: OfferReq, admin=Depends(get_current_admin)):
    oid = req.id or _id("ofr")
    doc = req.dict(); doc["id"] = oid
    doc["created_at"] = _now()
    await _db.offers.update_one({"id": oid}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/content/offers/{oid}")
async def del_offer(oid: str, admin=Depends(get_current_admin)):
    await _db.offers.delete_one({"id": oid})
    return {"success": True}


# ---------- Reports ----------
@router.get("/reports/{kind}")
async def report(kind: str, start: Optional[str] = None, end: Optional[str] = None, admin=Depends(get_current_admin)):
    coll_map = {
        "users": ("users", ["user_id", "full_name", "email", "mobile", "kyc_status", "suspended", "created_at"]),
        "transactions": ("transactions", ["tx_id", "user_id", "type", "category", "amount", "description", "status", "created_at"]),
        "investments": ("holdings", ["holding_id", "user_id", "asset_type", "asset_name", "amount", "sip", "created_at"]),
        "bookings": ("bookings", ["booking_id", "user_id", "booking_type", "title", "amount", "status", "created_at"]),
    }
    if kind not in coll_map:
        raise HTTPException(status_code=404, detail="Unknown report")
    coll, fields = coll_map[kind]
    q: Dict[str, Any] = {}
    if start or end:
        date_q: Dict[str, Any] = {}
        if start: date_q["$gte"] = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        if end: date_q["$lte"] = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        q["created_at"] = date_q
    rows = await _db[coll].find(q, {"_id": 0}).sort("created_at", -1).to_list(50000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(fields)
    for r in rows:
        w.writerow([r.get(f, "") for f in fields])
    await _log_action(admin["admin_id"], f"report.{kind}", meta={"rows": len(rows)})
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="mfb_{kind}_{_now().date()}.csv"'},
    )


# ---------- Settings ----------
@router.get("/settings")
async def get_settings(admin=Depends(get_current_admin)):
    s = await _db.app_settings.find_one({"_key": "global"}, {"_id": 0}) or {}
    s.pop("_key", None)
    return {
        "referral_bonus": s.get("referral_bonus", 50),
        "cashback_pct": s.get("cashback_pct", 2.0),
        "sip_min_amount": s.get("sip_min_amount", 500),
        "otp_enabled": s.get("otp_enabled", True),
        "maintenance_mode": s.get("maintenance_mode", False),
        "welcome_bonus": s.get("welcome_bonus", 5000),
    }


@router.put("/settings")
async def update_settings(req: SettingsReq, admin=Depends(get_current_admin)):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        await _db.app_settings.update_one({"_key": "global"}, {"$set": {"_key": "global", **updates}}, upsert=True)
    await _log_action(admin["admin_id"], "settings.update", meta=updates)
    return await get_settings(admin)


# Public endpoints used by the mobile app (no auth needed for banners/offers display)
public_router = APIRouter(prefix="/app", tags=["public-content"])


@public_router.get("/banners")
async def public_banners():
    return await _db.banners.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(20)


@public_router.get("/offers")
async def public_offers():
    return await _db.offers.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(20)


@public_router.get("/settings")
async def public_settings():
    s = await _db.app_settings.find_one({"_key": "global"}, {"_id": 0}) or {}
    s.pop("_key", None)
    return {
        "referral_bonus": s.get("referral_bonus", 50),
        "cashback_pct": s.get("cashback_pct", 2.0),
        "sip_min_amount": s.get("sip_min_amount", 500),
        "otp_enabled": s.get("otp_enabled", True),
        "maintenance_mode": s.get("maintenance_mode", False),
    }


def attach(parent_router: APIRouter, db):
    global _db
    _db = db
    parent_router.include_router(router)
    parent_router.include_router(public_router)


# ---------- Admin user management (super_admin only) ----------
class NewAdminReq(BaseModel):
    name: str
    email: str
    password: str
    role: str  # one of ROLES


def _require_super(admin):
    if admin["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can manage admins")


@router.get("/admins")
async def list_admins(admin=Depends(get_current_admin)):
    _require_super(admin)
    rows = await _db.admins.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(200)
    return {"items": rows, "roles": [{"id": r, "label": ROLE_LABEL[r]} for r in ROLES]}


@router.post("/admins")
async def create_admin(req: NewAdminReq, admin=Depends(get_current_admin)):
    _require_super(admin)
    if req.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from {sorted(ROLES)}")
    if await _db.admins.find_one({"email": req.email}):
        raise HTTPException(status_code=400, detail="Admin with this email exists")
    doc = {
        "admin_id": _id("adm"),
        "name": req.name,
        "email": req.email,
        "password": _hash(req.password),
        "role": req.role,
        "created_at": _now(),
        "created_by": admin["admin_id"],
    }
    await _db.admins.insert_one(doc)
    await _log_action(admin["admin_id"], "admin.create", target=doc["admin_id"], meta={"role": req.role})
    doc.pop("password", None); doc.pop("_id", None)
    return doc


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: str, admin=Depends(get_current_admin)):
    _require_super(admin)
    if admin_id == admin["admin_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await _db.admins.find_one({"admin_id": admin_id}, {"_id": 0, "role": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")
    if target.get("role") == "super_admin":
        # don't allow deleting the last super_admin
        cnt = await _db.admins.count_documents({"role": "super_admin"})
        if cnt <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last super_admin")
    await _db.admins.delete_one({"admin_id": admin_id})
    await _log_action(admin["admin_id"], "admin.delete", target=admin_id)
    return {"success": True}
