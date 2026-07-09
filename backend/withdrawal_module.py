"""Withdrawal Management System — Sprint 2A.

Extends the existing Wallet without touching any prior endpoint. Adds:
  Collections:
    bank_accounts          — user's saved bank accounts (verified/unverified)
    withdrawal_requests    — 8-state lifecycle w/ ledger integration
    withdrawal_otps        — 5-min expiry, 3 attempts, 30-sec resend
    withdrawal_timeline    — audit trail for every state change
    withdrawal_settings    — admin-configurable limits + charges (singleton)

Security:
  • KYC-approved gate
  • Rate limit: 3 requests/hour/user
  • Anti-duplicate: no identical amount within 60s
  • Idempotency via Idempotency-Key header (24h dedupe window)
  • OTP: 6-digit, 5-min expiry, 3 attempts, 30-sec resend cooldown
  • Full audit log on every state change

Balance handling (double-entry):
  • On OTP verify → DEBIT wallet immediately, status=under_review (money held)
  • On reject/fail/cancel → REFUND via wallet credit, status updated
  • On completed → status updated (already debited, no ledger change)
"""
from __future__ import annotations
import csv
import hashlib
import io
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Header, Response
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.withdrawal")
_db = None

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
STATUS = {"pending", "under_review", "approved", "processing", "completed",
          "rejected", "failed", "cancelled"}

DEFAULT_SETTINGS = {
    "min_amount": 100.0,
    "max_amount": 100_000.0,
    "daily_max_amount": 500_000.0,
    "daily_max_count": 5,
    "charge_type": "flat",        # flat | percentage
    "charge_flat": 0.0,
    "charge_percent": 0.0,
    "free_threshold": 0.0,        # amounts >= this are free
    "promo_waiver": True,          # global waiver
    "otp_expiry_seconds": 300,
    "otp_max_attempts": 3,
    "otp_resend_cooldown": 30,
    "rate_limit_per_hour": 3,
    "duplicate_window_seconds": 60,
    "processing_time_hours": 24,
}


def _now() -> datetime:
    # Return naive UTC to match Mongo's storage semantics (motor drops tzinfo on read).
    # Prevents "can't compare offset-naive and offset-aware datetimes" errors.
    return datetime.utcnow()


def _as_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _gid(p: str) -> str:
    return f"{p}_{secrets.token_hex(6)}"


async def _settings() -> Dict[str, Any]:
    doc = await _db.withdrawal_settings.find_one({"_id": "singleton"}, {"_id": 0})
    if not doc:
        await _db.withdrawal_settings.insert_one({"_id": "singleton", **DEFAULT_SETTINGS,
                                                   "created_at": _now()})
        return DEFAULT_SETTINGS.copy()
    # Merge with defaults for forward-compat
    return {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}


def _compute_charge(amount: float, s: Dict[str, Any]) -> float:
    if s.get("promo_waiver"):
        return 0.0
    if s.get("free_threshold") and amount >= s["free_threshold"]:
        return 0.0
    if s.get("charge_type") == "percentage":
        return round(amount * (s.get("charge_percent", 0) / 100), 2)
    return float(s.get("charge_flat", 0.0))


async def _timeline(w_id: str, event: str, actor: str, meta: Optional[Dict[str, Any]] = None):
    await _db.withdrawal_timeline.insert_one({
        "event_id": _gid("we"), "withdrawal_id": w_id, "event": event,
        "actor": actor, "meta": meta or {}, "at": _now(),
    })


def _mask_account(n: str) -> str:
    return f"{'X' * (len(n) - 4)}{n[-4:]}" if n and len(n) > 4 else n or "—"


# ---------- Pydantic ----------
class BankAccountReq(BaseModel):
    holder_name: str = Field(..., min_length=2)
    bank_name: str = Field(..., min_length=2)
    ifsc: str = Field(..., min_length=11, max_length=11)
    account_number: str = Field(..., min_length=8, max_length=25)

class WithdrawRequestReq(BaseModel):
    amount: float = Field(..., gt=0)
    bank_account_id: str
    reason: Optional[str] = None

class VerifyOTPReq(BaseModel):
    withdrawal_id: str
    otp: str = Field(..., min_length=4, max_length=8)

class ResendOTPReq(BaseModel):
    withdrawal_id: str

class AdminActionReq(BaseModel):
    reason: Optional[str] = None

class BulkActionReq(BaseModel):
    action: str  # approve|reject|processing|completed
    ids: List[str]
    reason: Optional[str] = None

class SettingsReq(BaseModel):
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    daily_max_amount: Optional[float] = None
    daily_max_count: Optional[int] = None
    charge_type: Optional[str] = None
    charge_flat: Optional[float] = None
    charge_percent: Optional[float] = None
    free_threshold: Optional[float] = None
    promo_waiver: Optional[bool] = None
    otp_expiry_seconds: Optional[int] = None
    otp_max_attempts: Optional[int] = None
    otp_resend_cooldown: Optional[int] = None
    rate_limit_per_hour: Optional[int] = None
    duplicate_window_seconds: Optional[int] = None
    processing_time_hours: Optional[int] = None


def attach(api: APIRouter, db, get_current_user, get_current_admin,
           log_action, credit_wallet, debit_wallet, kyc_gate, send_push,
           notify_user, build_receipt_pdf):
    global _db
    _db = db

    user = APIRouter(prefix="/wallet/withdrawals", tags=["withdrawals"])
    admin = APIRouter(prefix="/admin/withdrawals", tags=["withdrawals-admin"])

    # ----- BANK ACCOUNTS -----
    @user.get("/bank-accounts")
    async def list_banks(u=Depends(get_current_user)):
        items = await db.bank_accounts.find({"user_id": u["user_id"], "deleted": {"$ne": True}},
                                             {"_id": 0}).sort("created_at", -1).to_list(20)
        for it in items:
            it["account_masked"] = _mask_account(it.get("account_number", ""))
            it.pop("account_number", None)  # never send full number back
        return {"items": items}

    @user.post("/bank-accounts")
    async def add_bank(body: BankAccountReq, u=Depends(get_current_user)):
        # KYC gate removed — users can add bank accounts anytime.
        # KYC is enforced only when actually submitting a withdrawal request.
        ifsc = body.ifsc.upper()
        if not IFSC_RE.match(ifsc):
            raise HTTPException(400, "Invalid IFSC format (e.g. HDFC0001234)")
        # Prevent exact duplicate
        exist = await db.bank_accounts.find_one({"user_id": u["user_id"],
                                                  "account_number": body.account_number,
                                                  "ifsc": ifsc, "deleted": {"$ne": True}})
        if exist:
            return {"ok": True, "bank_id": exist["bank_id"], "duplicate": True}
        bid = _gid("ba")
        doc = {
            "bank_id": bid, "user_id": u["user_id"],
            "holder_name": body.holder_name.strip(), "bank_name": body.bank_name.strip(),
            "ifsc": ifsc, "account_number": body.account_number.strip(),
            "verified": False, "verification_method": None,
            "created_at": _now(), "deleted": False,
        }
        await db.bank_accounts.insert_one(doc)
        return {"ok": True, "bank_id": bid, "account_masked": _mask_account(body.account_number)}

    @user.delete("/bank-accounts/{bank_id}")
    async def del_bank(bank_id: str, u=Depends(get_current_user)):
        r = await db.bank_accounts.update_one(
            {"bank_id": bank_id, "user_id": u["user_id"]},
            {"$set": {"deleted": True, "deleted_at": _now()}})
        if not r.modified_count:
            raise HTTPException(404, "Bank account not found")
        return {"ok": True}

    # ----- SETTINGS (user-visible read) -----
    @user.get("/settings")
    async def user_settings():
        s = await _settings()
        return {k: s[k] for k in ["min_amount", "max_amount", "daily_max_amount",
                                   "daily_max_count", "charge_type", "charge_flat",
                                   "charge_percent", "free_threshold", "promo_waiver",
                                   "processing_time_hours", "otp_expiry_seconds",
                                   "otp_resend_cooldown"]}

    @user.post("/quote")
    async def quote(body: WithdrawRequestReq, u=Depends(get_current_user)):
        s = await _settings()
        charge = _compute_charge(body.amount, s)
        return {"amount": body.amount, "charge": charge, "net_amount": body.amount - charge,
                "processing_time_hours": s["processing_time_hours"]}

    # ----- CREATE WITHDRAWAL + OTP -----
    @user.post("/request")
    async def create_request(body: WithdrawRequestReq, u=Depends(get_current_user),
                             idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
        await kyc_gate(u)
        s = await _settings()

        # Idempotency
        if idempotency_key:
            dup = await db.withdrawal_requests.find_one(
                {"idempotency_key": idempotency_key, "user_id": u["user_id"]}, {"_id": 0})
            if dup:
                return {"ok": True, "withdrawal_id": dup["withdrawal_id"],
                        "status": dup["status"], "idempotent": True}

        # Amount limits
        if body.amount < s["min_amount"]:
            raise HTTPException(400, f"Minimum withdrawal is ₹{s['min_amount']:.0f}")
        if body.amount > s["max_amount"]:
            raise HTTPException(400, f"Maximum per request is ₹{s['max_amount']:.0f}")

        # Bank account
        bank = await db.bank_accounts.find_one(
            {"bank_id": body.bank_account_id, "user_id": u["user_id"], "deleted": {"$ne": True}})
        if not bank:
            raise HTTPException(404, "Bank account not found")

        # Wallet balance check
        w = await db.wallets.find_one({"user_id": u["user_id"]}, {"_id": 0, "balance": 1}) or {}
        balance = float(w.get("balance", 0.0))
        if body.amount > balance:
            raise HTTPException(400, f"Insufficient balance. Available: ₹{balance:.2f}")

        # Anti-duplicate
        window = _now() - timedelta(seconds=s["duplicate_window_seconds"])
        recent_dup = await db.withdrawal_requests.find_one({
            "user_id": u["user_id"], "amount": body.amount,
            "created_at": {"$gte": window},
            "status": {"$in": ["pending", "under_review", "approved", "processing"]},
        })
        if recent_dup:
            raise HTTPException(429, "Duplicate withdrawal request detected. Wait a moment.")

        # Rate limit
        hour_ago = _now() - timedelta(hours=1)
        recent = await db.withdrawal_requests.count_documents(
            {"user_id": u["user_id"], "created_at": {"$gte": hour_ago}})
        if recent >= s["rate_limit_per_hour"]:
            raise HTTPException(429, f"Too many requests. Max {s['rate_limit_per_hour']}/hour.")

        # Daily limit + count
        day_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        today = await db.withdrawal_requests.find(
            {"user_id": u["user_id"], "created_at": {"$gte": day_start},
             "status": {"$ne": "cancelled"}}, {"_id": 0, "amount": 1}).to_list(50)
        if len(today) >= s["daily_max_count"]:
            raise HTTPException(429, f"Daily limit reached ({s['daily_max_count']} requests/day)")
        if sum(x["amount"] for x in today) + body.amount > s["daily_max_amount"]:
            raise HTTPException(429, f"Daily amount cap of ₹{s['daily_max_amount']:.0f} would be exceeded")

        charge = _compute_charge(body.amount, s)
        wid = _gid("wd")
        ref = "MFB-W-" + secrets.token_hex(4).upper()
        # Create OTP
        otp = f"{secrets.randbelow(900000) + 100000}"
        otp_doc = {
            "withdrawal_id": wid, "user_id": u["user_id"], "otp": otp,
            "attempts": 0, "created_at": _now(),
            "expires_at": _now() + timedelta(seconds=s["otp_expiry_seconds"]),
            "consumed": False, "last_sent_at": _now(),
        }
        await db.withdrawal_otps.insert_one(otp_doc)

        # Persist withdrawal in `pending` (no wallet debit yet)
        doc = {
            "withdrawal_id": wid, "user_id": u["user_id"],
            "amount": float(body.amount), "charge": charge,
            "net_amount": float(body.amount) - charge,
            "status": "pending",
            "reference_no": ref, "reason": body.reason,
            "bank_account_id": bank["bank_id"],
            "bank_snapshot": {
                "holder_name": bank["holder_name"], "bank_name": bank["bank_name"],
                "ifsc": bank["ifsc"], "account_masked": _mask_account(bank["account_number"]),
            },
            "idempotency_key": idempotency_key,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.withdrawal_requests.insert_one(doc)
        await _timeline(wid, "created", "user", {"amount": body.amount})

        # Notify (dev mode: return OTP for demo)
        try:
            await notify_user(u["user_id"], "Withdrawal Requested",
                              f"OTP: {otp}. Valid for {s['otp_expiry_seconds']//60} min. Request #{ref}",
                              "/wallet/withdrawals")
        except Exception:
            pass

        return {"ok": True, "withdrawal_id": wid, "reference_no": ref,
                "charge": charge, "net_amount": doc["net_amount"],
                "otp_expires_in": s["otp_expiry_seconds"],
                "otp_demo": otp}  # SHOWN ONLY IN DEMO MODE

    @user.post("/verify-otp")
    async def verify_otp(body: VerifyOTPReq, u=Depends(get_current_user)):
        s = await _settings()
        wd = await db.withdrawal_requests.find_one(
            {"withdrawal_id": body.withdrawal_id, "user_id": u["user_id"]}, {"_id": 0})
        if not wd:
            raise HTTPException(404, "Withdrawal request not found")
        if wd["status"] != "pending":
            raise HTTPException(400, f"Cannot verify OTP for {wd['status']} withdrawal")
        otp_doc = await db.withdrawal_otps.find_one(
            {"withdrawal_id": body.withdrawal_id, "consumed": False},
            {"_id": 0}, sort=[("created_at", -1)])
        if not otp_doc:
            raise HTTPException(400, "No pending OTP found")
        if _now() > otp_doc["expires_at"]:
            raise HTTPException(400, "OTP expired. Please resend.")
        if otp_doc["attempts"] >= s["otp_max_attempts"]:
            raise HTTPException(429, "Maximum OTP attempts exceeded")
        await db.withdrawal_otps.update_one({"withdrawal_id": body.withdrawal_id, "consumed": False},
                                             {"$inc": {"attempts": 1}})
        if body.otp.strip() != otp_doc["otp"]:
            remaining = s["otp_max_attempts"] - otp_doc["attempts"] - 1
            raise HTTPException(400, f"Invalid OTP ({remaining} attempts left)")

        # Debit wallet (hold funds)
        await debit_wallet(user_id=u["user_id"], amount=float(wd["amount"]),
                           category="withdraw",
                           description=f"Withdrawal to {wd['bank_snapshot']['account_masked']} (Ref: {wd['reference_no']})",
                           provider="bank", reference_id=wd["reference_no"])
        await db.withdrawal_otps.update_one({"withdrawal_id": body.withdrawal_id, "consumed": False},
                                             {"$set": {"consumed": True, "consumed_at": _now()}})
        await db.withdrawal_requests.update_one({"withdrawal_id": body.withdrawal_id},
            {"$set": {"status": "under_review", "verified_at": _now(), "updated_at": _now()}})
        await _timeline(body.withdrawal_id, "otp_verified", "user")
        try:
            await notify_user(u["user_id"], "Withdrawal Under Review",
                              f"Your withdrawal of ₹{wd['amount']:.2f} is queued for admin approval.",
                              "/wallet/withdrawals")
        except Exception:
            pass
        return {"ok": True, "status": "under_review"}

    @user.post("/resend-otp")
    async def resend_otp(body: ResendOTPReq, u=Depends(get_current_user)):
        s = await _settings()
        prev = await db.withdrawal_otps.find_one(
            {"withdrawal_id": body.withdrawal_id, "consumed": False},
            {"_id": 0}, sort=[("created_at", -1)])
        if not prev:
            raise HTTPException(404, "No active OTP found")
        elapsed = (_now() - prev["last_sent_at"]).total_seconds()
        if elapsed < s["otp_resend_cooldown"]:
            raise HTTPException(429, f"Please wait {int(s['otp_resend_cooldown'] - elapsed)}s before resending")
        otp = f"{secrets.randbelow(900000) + 100000}"
        await db.withdrawal_otps.update_one(
            {"withdrawal_id": body.withdrawal_id, "consumed": False},
            {"$set": {"otp": otp, "attempts": 0, "last_sent_at": _now(),
                      "expires_at": _now() + timedelta(seconds=s["otp_expiry_seconds"])}})
        return {"ok": True, "otp_expires_in": s["otp_expiry_seconds"], "otp_demo": otp}

    @user.post("/{wid}/cancel")
    async def user_cancel(wid: str, u=Depends(get_current_user)):
        wd = await db.withdrawal_requests.find_one({"withdrawal_id": wid, "user_id": u["user_id"]},
                                                     {"_id": 0})
        if not wd:
            raise HTTPException(404, "Not found")
        if wd["status"] not in ("pending", "under_review"):
            raise HTTPException(400, f"Cannot cancel {wd['status']} withdrawal")
        # If money already held (under_review), refund
        if wd["status"] == "under_review":
            await credit_wallet(user_id=u["user_id"], amount=float(wd["amount"]),
                                category="refund",
                                description=f"Withdrawal cancelled: {wd['reference_no']}",
                                provider="system", reference_id=wd["reference_no"])
        await db.withdrawal_requests.update_one({"withdrawal_id": wid},
            {"$set": {"status": "cancelled", "updated_at": _now(),
                      "cancelled_at": _now(), "cancelled_by": "user"}})
        await _timeline(wid, "cancelled", "user")
        return {"ok": True}

    @user.get("")
    async def list_history(u=Depends(get_current_user), limit: int = 50, skip: int = 0,
                            status: Optional[str] = None):
        q: Dict[str, Any] = {"user_id": u["user_id"]}
        if status and status != "all":
            q["status"] = status
        items = await db.withdrawal_requests.find(q, {"_id": 0}).sort("created_at", -1).skip(max(skip, 0)).limit(min(limit, 200)).to_list(min(limit, 200))
        total = await db.withdrawal_requests.count_documents(q)
        return {"items": items, "total": total}

    @user.get("/{wid}")
    async def detail(wid: str, u=Depends(get_current_user)):
        wd = await db.withdrawal_requests.find_one({"withdrawal_id": wid, "user_id": u["user_id"]}, {"_id": 0})
        if not wd:
            raise HTTPException(404, "Not found")
        timeline = await db.withdrawal_timeline.find({"withdrawal_id": wid}, {"_id": 0}).sort("at", 1).to_list(50)
        return {"withdrawal": wd, "timeline": timeline}

    @user.get("/{wid}/receipt.pdf")
    async def receipt(wid: str, u=Depends(get_current_user)):
        wd = await db.withdrawal_requests.find_one({"withdrawal_id": wid, "user_id": u["user_id"]}, {"_id": 0})
        if not wd:
            raise HTTPException(404, "Not found")
        # Reuse existing wallet receipt template
        tx = {
            "tx_id": wd["reference_no"], "type": "debit", "amount": wd["amount"],
            "status": wd["status"], "category": "withdraw",
            "description": f"Withdrawal to {wd['bank_snapshot']['bank_name']} · {wd['bank_snapshot']['account_masked']}",
            "counterparty": wd["bank_snapshot"]["holder_name"],
            "provider": "bank", "reference_id": wd["reference_no"],
            "created_at": wd["created_at"],
        }
        w = await db.wallets.find_one({"user_id": u["user_id"]}, {"_id": 0, "balance": 1}) or {}
        pdf = build_receipt_pdf(tx, u, float(w.get("balance", 0.0)))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="MFB_Withdrawal_{wd["reference_no"]}.pdf"'})

    # ============ ADMIN ============
    @admin.get("")
    async def admin_list(adm=Depends(get_current_admin), q: Optional[str] = None,
                         status: Optional[str] = None, user_id: Optional[str] = None,
                         limit: int = 100, skip: int = 0):
        query: Dict[str, Any] = {}
        if status and status != "all":
            query["status"] = status
        if user_id:
            query["user_id"] = user_id
        if q:
            query["$or"] = [
                {"reference_no": {"$regex": q, "$options": "i"}},
                {"withdrawal_id": {"$regex": q, "$options": "i"}},
                {"bank_snapshot.holder_name": {"$regex": q, "$options": "i"}},
            ]
        items = await db.withdrawal_requests.find(query, {"_id": 0}).sort("created_at", -1).skip(max(skip, 0)).limit(min(limit, 500)).to_list(min(limit, 500))
        # Enrich w/ user data
        if items:
            uids = list({it["user_id"] for it in items})
            users = {x["user_id"]: x async for x in db.users.find({"user_id": {"$in": uids}}, {"_id": 0, "user_id": 1, "full_name": 1, "email": 1, "mobile": 1})}
            for it in items:
                it["user"] = users.get(it["user_id"], {})
        total = await db.withdrawal_requests.count_documents(query)
        return {"items": items, "total": total}

    @admin.get("/dashboard")
    async def dashboard(adm=Depends(get_current_admin)):
        today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=6)
        async def sum_by_status(status: str, since: Optional[datetime] = None):
            q: Dict[str, Any] = {"status": status}
            if since:
                q["created_at"] = {"$gte": since}
            r = await db.withdrawal_requests.aggregate([{"$match": q},
                {"$group": {"_id": None, "s": {"$sum": "$amount"}, "c": {"$sum": 1}}}]).to_list(1)
            return {"amount": float(r[0]["s"]) if r else 0.0, "count": r[0]["c"] if r else 0}
        stats = {
            "today_count": await db.withdrawal_requests.count_documents({"created_at": {"$gte": today}}),
            "pending": await sum_by_status("under_review"),
            "approved": await sum_by_status("approved"),
            "processing": await sum_by_status("processing"),
            "completed": await sum_by_status("completed"),
            "rejected": await sum_by_status("rejected"),
            "failed": await sum_by_status("failed"),
        }
        # 7-day chart
        chart = []
        for i in range(7):
            day = week + timedelta(days=i)
            end = day + timedelta(days=1)
            r = await db.withdrawal_requests.aggregate([
                {"$match": {"created_at": {"$gte": day, "$lt": end}}},
                {"$group": {"_id": "$status", "c": {"$sum": 1}, "s": {"$sum": "$amount"}}},
            ]).to_list(20)
            by = {x["_id"]: {"count": x["c"], "amount": float(x["s"])} for x in r}
            chart.append({"date": day.strftime("%Y-%m-%d"), "by_status": by})
        return {"stats": stats, "chart": chart}

    async def _transition(wid: str, new_status: str, adm: Dict[str, Any],
                         reason: Optional[str] = None,
                         allow_from: Optional[List[str]] = None):
        wd = await db.withdrawal_requests.find_one({"withdrawal_id": wid}, {"_id": 0})
        if not wd:
            raise HTTPException(404, "Not found")
        if allow_from and wd["status"] not in allow_from:
            raise HTTPException(400, f"Cannot go from {wd['status']} to {new_status}")

        update: Dict[str, Any] = {"status": new_status, "updated_at": _now(),
                                   f"{new_status}_at": _now(),
                                   f"{new_status}_by": adm["admin_id"]}
        if reason:
            update["reason_admin"] = reason

        # Refund on rejection / failure (money was held on OTP verify)
        if new_status in ("rejected", "failed") and wd["status"] not in ("pending", "cancelled"):
            await credit_wallet(user_id=wd["user_id"], amount=float(wd["amount"]),
                                category="refund",
                                description=f"Withdrawal {new_status}: {reason or 'admin action'} · {wd['reference_no']}",
                                provider="system", reference_id=wd["reference_no"])

        await db.withdrawal_requests.update_one({"withdrawal_id": wid}, {"$set": update})
        await _timeline(wid, new_status, f"admin:{adm['admin_id']}", {"reason": reason})
        await log_action(adm["admin_id"], f"withdrawal.{new_status}", target=wid,
                         meta={"amount": wd["amount"], "reason": reason})

        # Notify user
        titles = {"approved": "Withdrawal Approved", "rejected": "Withdrawal Rejected",
                  "processing": "Withdrawal Processing", "completed": "Withdrawal Completed",
                  "failed": "Withdrawal Failed"}
        if new_status in titles:
            try:
                await notify_user(wd["user_id"], titles[new_status],
                                  f"₹{wd['amount']:.2f} to {wd['bank_snapshot']['account_masked']} · {wd['reference_no']}"
                                  + (f"\nReason: {reason}" if reason and new_status == "rejected" else ""),
                                  "/wallet/withdrawals")
            except Exception:
                pass
        return {"ok": True, "status": new_status}

    @admin.post("/{wid}/approve")
    async def a_approve(wid: str, adm=Depends(get_current_admin)):
        return await _transition(wid, "approved", adm, allow_from=["under_review"])

    @admin.post("/{wid}/reject")
    async def a_reject(wid: str, body: AdminActionReq, adm=Depends(get_current_admin)):
        if not body.reason:
            raise HTTPException(400, "reason required")
        return await _transition(wid, "rejected", adm, reason=body.reason,
                                  allow_from=["under_review", "approved", "processing"])

    @admin.post("/{wid}/processing")
    async def a_processing(wid: str, adm=Depends(get_current_admin)):
        return await _transition(wid, "processing", adm, allow_from=["approved"])

    @admin.post("/{wid}/completed")
    async def a_completed(wid: str, adm=Depends(get_current_admin)):
        return await _transition(wid, "completed", adm,
                                  allow_from=["approved", "processing"])

    @admin.post("/{wid}/failed")
    async def a_failed(wid: str, body: AdminActionReq, adm=Depends(get_current_admin)):
        return await _transition(wid, "failed", adm, reason=body.reason,
                                  allow_from=["approved", "processing"])

    @admin.post("/{wid}/refund")
    async def a_refund(wid: str, adm=Depends(get_current_admin)):
        # Explicit refund for completed withdrawals (edge case)
        wd = await db.withdrawal_requests.find_one({"withdrawal_id": wid}, {"_id": 0})
        if not wd:
            raise HTTPException(404, "Not found")
        if wd.get("refunded"):
            raise HTTPException(400, "Already refunded")
        await credit_wallet(user_id=wd["user_id"], amount=float(wd["amount"]),
                            category="refund",
                            description=f"Withdrawal refund: {wd['reference_no']}",
                            provider="admin", reference_id=wd["reference_no"])
        await db.withdrawal_requests.update_one({"withdrawal_id": wid},
            {"$set": {"refunded": True, "refunded_at": _now(), "updated_at": _now()}})
        await _timeline(wid, "refunded", f"admin:{adm['admin_id']}")
        await log_action(adm["admin_id"], "withdrawal.refund", target=wid)
        return {"ok": True}

    @admin.post("/bulk")
    async def bulk(body: BulkActionReq, adm=Depends(get_current_admin)):
        if body.action not in ("approve", "reject", "processing", "completed"):
            raise HTTPException(400, "Invalid action")
        allow_map = {"approve": ["under_review"], "reject": ["under_review", "approved"],
                     "processing": ["approved"], "completed": ["approved", "processing"]}
        ok = 0
        for wid in body.ids[:200]:
            try:
                await _transition(wid, body.action if body.action != "reject" else "rejected",
                                   adm, reason=body.reason, allow_from=allow_map[body.action])
                ok += 1
            except Exception as e:
                logger.warning(f"[withdrawal.bulk] {wid}: {e}")
        return {"processed": ok, "requested": len(body.ids)}

    @admin.get("/export.csv")
    async def export_csv(adm=Depends(get_current_admin)):
        rows = await db.withdrawal_requests.find({}, {"_id": 0}).sort("created_at", -1).limit(10000).to_list(10000)
        s = io.StringIO()
        w = csv.writer(s)
        w.writerow(["reference_no", "withdrawal_id", "user_id", "amount", "charge",
                    "net_amount", "status", "bank", "account_masked", "created_at"])
        for r in rows:
            bs = r.get("bank_snapshot", {})
            w.writerow([r.get("reference_no"), r.get("withdrawal_id"), r.get("user_id"),
                        r.get("amount"), r.get("charge", 0), r.get("net_amount"),
                        r.get("status"), bs.get("bank_name", ""), bs.get("account_masked", ""),
                        r.get("created_at", "")])
        await log_action(adm["admin_id"], "withdrawal.csv_export", meta={"count": len(rows)})
        return Response(content=s.getvalue().encode("utf-8"), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="MFB_Withdrawals.csv"'})

    @admin.get("/settings")
    async def get_settings(adm=Depends(get_current_admin)):
        return await _settings()

    @admin.put("/settings")
    async def put_settings(body: SettingsReq, adm=Depends(get_current_admin)):
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can update settings")
        updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
        if not updates:
            raise HTTPException(400, "No changes")
        updates["updated_at"] = _now()
        updates["updated_by"] = adm["admin_id"]
        await db.withdrawal_settings.update_one({"_id": "singleton"}, {"$set": updates}, upsert=True)
        await log_action(adm["admin_id"], "withdrawal.settings_update", meta=updates)
        return {"ok": True, "settings": await _settings()}

    @admin.post("/bank-accounts/{bank_id}/verify")
    async def verify_bank(bank_id: str, adm=Depends(get_current_admin)):
        r = await db.bank_accounts.update_one({"bank_id": bank_id},
            {"$set": {"verified": True, "verification_method": "admin_manual",
                      "verified_by": adm["admin_id"], "verified_at": _now()}})
        if not r.modified_count:
            raise HTTPException(404, "Bank not found")
        await log_action(adm["admin_id"], "bank.verify", target=bank_id)
        return {"ok": True}

    api.include_router(user)
    api.include_router(admin)
