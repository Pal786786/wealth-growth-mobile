"""Admin API endpoints for My Funding Bank super-app.
Role-based access on top of the existing JWT system.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, Field

# Imported from server module at startup (set in attach())
_db = None
_logger = None


# ---------- Models ----------
class AdminLoginReq(BaseModel):
    email: EmailStr
    password: str


class AdminUserOut(BaseModel):
    admin_id: str
    name: str
    email: str
    role: str
    created_at: datetime


class AdminTokenOut(BaseModel):
    token: str
    admin: AdminUserOut


class UserActionReq(BaseModel):
    action: str  # "suspend" | "activate"


class WalletAdjustReq(BaseModel):
    user_id: str
    amount: float
    type: str  # "credit" | "debit"
    note: Optional[str] = "Adjustment by admin"


class KycActionReq(BaseModel):
    user_id: str
    action: str  # "approve" | "reject"
    note: Optional[str] = None


class NotifReq(BaseModel):
    title: str
    body: str
    target: str = "all"  # "all" | "user_id"
    user_id: Optional[str] = None


# ---------- Helpers ----------
ROLES = {"super_admin", "admin", "finance_manager", "support_manager", "investment_manager"}
ROLE_LABEL = {
    "super_admin": "Super Admin",
    "admin": "Admin",
    "finance_manager": "Finance Manager",
    "support_manager": "Support Manager",
    "investment_manager": "Investment Manager",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def _create_admin_token(admin_id: str, role: str) -> str:
    secret = os.environ["JWT_SECRET"]
    algo = os.environ.get("JWT_ALGORITHM", "HS256")
    payload = {"sub": admin_id, "role": role, "kind": "admin", "iat": _now(), "exp": _now() + timedelta(hours=12)}
    return jwt.encode(payload, secret, algorithm=algo)


async def get_current_admin(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    if payload.get("kind") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin token")
    admin = await _db.admins.find_one({"admin_id": payload["sub"]}, {"_id": 0, "password": 0})
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin


def require_role(*roles: str):
    async def dep(admin: Dict[str, Any] = Depends(get_current_admin)) -> Dict[str, Any]:
        if admin["role"] not in roles and admin["role"] != "super_admin":
            raise HTTPException(status_code=403, detail=f"Requires role: {roles}")
        return admin
    return dep


def _admin_public(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "admin_id": a["admin_id"],
        "name": a["name"],
        "email": a["email"],
        "role": a["role"],
        "created_at": a["created_at"],
    }


async def _log_action(admin_id: str, action: str, target: Optional[str] = None, meta: Optional[Dict[str, Any]] = None):
    # Defensive coercion — some legacy callers pass a dict as `target`; keep audit
    # rows homogeneous (str|None) so the admin UI never explodes rendering them.
    _target: Optional[str]
    if target is None or isinstance(target, str):
        _target = target
    else:
        try:
            import json as _json
            _target = _json.dumps(target, default=str)
        except Exception:
            _target = str(target)
    await _db.admin_audit.insert_one({
        "id": uuid.uuid4().hex[:16],
        "admin_id": admin_id,
        "action": action,
        "target": _target,
        "meta": meta or {},
        "at": _now(),
    })


# ---------- Router ----------
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post("/login", response_model=AdminTokenOut)
async def admin_login(req: AdminLoginReq):
    a = await _db.admins.find_one({"email": req.email})
    if not a or not _verify(req.password, a.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await _log_action(a["admin_id"], "admin.login")
    return {"token": _create_admin_token(a["admin_id"], a["role"]), "admin": _admin_public(a)}


@admin_router.get("/me", response_model=AdminUserOut)
async def admin_me(admin: Dict[str, Any] = Depends(get_current_admin)):
    return _admin_public(admin)


# Dashboard stats
@admin_router.get("/dashboard/stats")
async def dashboard_stats(admin: Dict[str, Any] = Depends(get_current_admin)):
    now = _now()
    start_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start_30d = now - timedelta(days=30)

    total_users = await _db.users.count_documents({})
    active_users = await _db.users.count_documents({"suspended": {"$ne": True}})
    new_today = await _db.users.count_documents({"created_at": {"$gte": start_today}})

    # Wallet totals
    wallet_agg = await _db.wallets.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$balance"}}}
    ]).to_list(1)
    total_wallet_balance = wallet_agg[0]["total"] if wallet_agg else 0.0

    async def tx_sum(category: str, ttype: Optional[str] = None) -> float:
        q: Dict[str, Any] = {"category": category}
        if ttype:
            q["type"] = ttype
        rows = await _db.transactions.aggregate([
            {"$match": q},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]).to_list(1)
        return rows[0]["total"] if rows else 0.0

    total_deposits = await tx_sum("topup", "credit")
    total_withdrawals = await tx_sum("send", "debit")
    cashback = await tx_sum("cashback")

    # Investments
    inv_by_type = await _db.holdings.aggregate([
        {"$group": {"_id": "$asset_type", "total": {"$sum": "$amount"}}}
    ]).to_list(20)
    inv_map = {r["_id"]: r["total"] for r in inv_by_type}

    total_bookings = await _db.bookings.count_documents({})
    booking_revenue = 0.0
    rev_rows = await _db.bookings.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    if rev_rows:
        booking_revenue = rev_rows[0]["total"]

    # User growth (last 30 days)
    growth = await _db.users.aggregate([
        {"$match": {"created_at": {"$gte": start_30d}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(60)
    user_growth = [{"date": r["_id"], "count": r["count"]} for r in growth]

    # Transactions per day
    tx_daily = await _db.transactions.aggregate([
        {"$match": {"created_at": {"$gte": start_30d}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "credits": {"$sum": {"$cond": [{"$eq": ["$type", "credit"]}, "$amount", 0]}},
            "debits": {"$sum": {"$cond": [{"$eq": ["$type", "debit"]}, "$amount", 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(60)
    tx_chart = [{"date": r["_id"], "credits": r["credits"], "debits": r["debits"]} for r in tx_daily]

    pending_kyc = await _db.users.count_documents({"kyc_status": "pending"})

    return {
        "users": {
            "total": total_users, "active": active_users, "new_today": new_today,
            "pending_kyc": pending_kyc,
        },
        "wallet": {
            "total_balance": round(total_wallet_balance, 2),
            "total_deposits": round(total_deposits, 2),
            "total_withdrawals": round(total_withdrawals, 2),
            "cashback_paid": round(cashback, 2),
        },
        "investments": {
            "mutual_fund": round(inv_map.get("mutual_fund", 0), 2),
            "stock": round(inv_map.get("stock", 0), 2),
            "gold": round(inv_map.get("gold", 0), 2),
            "fd": round(inv_map.get("fd", 0), 2),
            "govt": round(inv_map.get("govt", 0), 2),
        },
        "bookings": {"total": total_bookings, "revenue": round(booking_revenue, 2)},
        "charts": {
            "user_growth": user_growth,
            "tx_daily": tx_chart,
        },
    }


# User management
@admin_router.get("/users")
async def list_users(
    q: Optional[str] = None,
    suspended: Optional[bool] = None,
    kyc: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    query: Dict[str, Any] = {}
    if suspended is not None:
        query["suspended"] = suspended
    if kyc:
        query["kyc_status"] = kyc
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"mobile": {"$regex": q}},
            {"full_name": {"$regex": q, "$options": "i"}},
            {"user_id": q},
        ]
    rows = await _db.users.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    # Batch-fetch wallet balances in a single query (avoids N+1)
    if rows:
        user_ids = [r["user_id"] for r in rows]
        wallets = await _db.wallets.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1, "balance": 1},
        ).to_list(len(user_ids))
        wallet_map = {w["user_id"]: w.get("balance", 0.0) for w in wallets}
        for r in rows:
            r["wallet_balance"] = wallet_map.get(r["user_id"], 0.0)
    total = await _db.users.count_documents(query)
    return {"items": rows, "total": total}


@admin_router.get("/users/{user_id}")
async def user_detail(user_id: str, admin: Dict[str, Any] = Depends(get_current_admin)):
    u = await _db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    w = await _db.wallets.find_one({"user_id": user_id}, {"_id": 0})
    txs = await _db.transactions.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    holdings = await _db.holdings.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    bookings = await _db.bookings.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"user": u, "wallet": w, "transactions": txs, "holdings": holdings, "bookings": bookings}


@admin_router.post("/users/{user_id}/action")
async def user_action(user_id: str, req: UserActionReq, admin: Dict[str, Any] = Depends(get_current_admin)):
    if req.action not in ("suspend", "activate"):
        raise HTTPException(status_code=400, detail="Invalid action")
    suspended = req.action == "suspend"
    res = await _db.users.update_one({"user_id": user_id}, {"$set": {"suspended": suspended}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await _log_action(admin["admin_id"], f"user.{req.action}", target=user_id)
    return {"success": True, "suspended": suspended}


# KYC
@admin_router.get("/kyc/pending")
async def kyc_pending(admin: Dict[str, Any] = Depends(get_current_admin)):
    rows = await _db.users.find({"kyc_status": "pending"}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(200)
    return rows


@admin_router.post("/kyc/action")
async def kyc_action(req: KycActionReq, admin: Dict[str, Any] = Depends(get_current_admin)):
    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    new_status = "verified" if req.action == "approve" else "rejected"
    res = await _db.users.update_one(
        {"user_id": req.user_id},
        {"$set": {"kyc_status": new_status, "kyc_note": req.note, "kyc_reviewed_at": _now(), "kyc_reviewed_by": admin["admin_id"]}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await _log_action(admin["admin_id"], f"kyc.{req.action}", target=req.user_id, meta={"note": req.note})
    return {"success": True, "kyc_status": new_status}


# Wallet adjust
@admin_router.post("/wallet/adjust")
async def wallet_adjust(req: WalletAdjustReq, admin: Dict[str, Any] = Depends(get_current_admin)):
    if req.type not in ("credit", "debit") or req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid params")
    w = await _db.wallets.find_one({"user_id": req.user_id}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if req.type == "debit" and w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    delta = req.amount if req.type == "credit" else -req.amount
    await _db.wallets.update_one({"user_id": req.user_id}, {"$inc": {"balance": delta}})
    tx = {
        "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
        "user_id": req.user_id,
        "type": req.type,
        "category": "admin_adjust",
        "amount": req.amount,
        "description": f"Admin: {req.note}",
        "status": "success",
        "counterparty": admin["name"],
        "created_at": _now(),
    }
    await _db.transactions.insert_one(tx)
    await _log_action(admin["admin_id"], f"wallet.{req.type}", target=req.user_id, meta={"amount": req.amount})

    # Sprint 12.3 · Phase A — Emit journal entry for the adjustment
    try:
        from finance_ledger.engine import (
            JournalLeg, post_journal,
            coa_user_wallet, coa_equity_adjustment,
        )
        user_acct = coa_user_wallet(req.user_id)
        adj_acct = coa_equity_adjustment()
        amt = float(req.amount)
        if req.type == "credit":
            legs = [JournalLeg.make(adj_acct, amt, "DR"),
                    JournalLeg.make(user_acct, amt, "CR")]
        else:
            legs = [JournalLeg.make(user_acct, amt, "DR"),
                    JournalLeg.make(adj_acct, amt, "CR")]
        await post_journal(
            txn_type="admin_adjustment", legs=legs, amount=amt, currency="INR",
            reference_id=tx["tx_id"], reference_type="admin_adjust",
            user_id=req.user_id, narration=f"Admin: {req.note}",
            posted_by=f"admin:{admin['admin_id']}",
            metadata={"admin_id": admin["admin_id"], "reason": req.note,
                       "adjust_type": req.type},
            dedupe_key=f"admin_adjust:{tx['tx_id']}",
        )
    except Exception as _e:
        pass  # journal is best-effort; existing behaviour preserved

    return {"success": True, "new_balance": w["balance"] + delta}


# Transactions
@admin_router.get("/transactions")
async def list_transactions(
    user_id: Optional[str] = None,
    category: Optional[str] = None,
    ttype: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    q: Dict[str, Any] = {}
    if user_id:
        q["user_id"] = user_id
    if category:
        q["category"] = category
    if ttype:
        q["type"] = ttype
    rows = await _db.transactions.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await _db.transactions.count_documents(q)
    return {"items": rows, "total": total}


# Audit log
@admin_router.get("/audit")
async def audit(
    limit: int = 200,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    target: Optional[str] = None,
    since_days: Optional[int] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Returns recent admin audit log entries with optional filters."""
    q: Dict[str, Any] = {}
    if action:
        q["action"] = {"$regex": action, "$options": "i"}
    if actor:
        q["admin_id"] = actor
    if target:
        q["target"] = {"$regex": target, "$options": "i"}
    if since_days and since_days > 0:
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        q["at"] = {"$gte": _dt.now(_tz.utc) - _td(days=since_days)}
    rows = await _db.admin_audit.find(q, {"_id": 0}).sort("at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
    # Join admin names
    admin_ids = list({r.get("admin_id") for r in rows if r.get("admin_id")})
    admins_map: Dict[str, str] = {}
    if admin_ids:
        async for a in _db.admins.find({"admin_id": {"$in": admin_ids}}, {"_id": 0, "admin_id": 1, "email": 1, "full_name": 1}):
            admins_map[a["admin_id"]] = a.get("full_name") or a.get("email") or a["admin_id"]
    for r in rows:
        r["actor_name"] = admins_map.get(r.get("admin_id", ""), r.get("admin_id", "system"))
    return {"items": rows, "total": len(rows)}


def attach(parent_router: APIRouter, db, logger):
    """Wire the admin router and seed the default super admin."""
    global _db, _logger
    _db = db
    _logger = logger
    parent_router.include_router(admin_router)


async def seed_admin(db, logger):
    """Seed the default super-admin if no admin exists."""
    count = await db.admins.count_documents({})
    if count > 0:
        return
    admin = {
        "admin_id": f"adm_{uuid.uuid4().hex[:12]}",
        "name": "Super Admin",
        "email": "admin@mfb.in",
        "password": _hash("Admin@MFB2026"),
        "role": "super_admin",
        "created_at": _now(),
    }
    await db.admins.insert_one(admin)
    logger.info("Seeded default super admin: admin@mfb.in / Admin@MFB2026")
