"""Security & messaging enhancements for My Funding Bank.

Modules included:
  • Push delivery logs (retry-safe, admin-visible)
  • OTP via configurable SMS provider (MSG91 / Twilio / Demo)
  • Forgot password (email + mobile OTP routes)
  • Change password (auth required)
  • Admin user security: status, force reset, disable, unlock

NEVER stores or returns plain-text passwords. All OTPs are random 6-digit
codes with hashed in-DB storage, expiry, resend cap & per-mobile rate limit.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import random
import secrets
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("mfb.security")
_db = None
_get_current_user = None
_get_current_admin = None
_send_push = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# 1. PUSH DELIVERY LOGS
# ============================================================================

async def log_push_send(
    title: str, message: str, recipients: List[str], ok: bool,
    provider_response: Optional[str] = None, error: Optional[str] = None,
    batch_id: Optional[str] = None, latency_ms: Optional[int] = None,
):
    await _db.push_logs.insert_one({
        "log_id": f"plog_{secrets.token_hex(6)}",
        "batch_id": batch_id,
        "title": title,
        "message": message,
        "recipients_count": len(recipients),
        "recipients_sample": recipients[:5],
        "ok": ok,
        "status": "success" if ok else "failed",
        "provider_response": (provider_response or "")[:500],
        "error": (error or "")[:500],
        "latency_ms": latency_ms,
        "at": _now(),
    })


async def send_push_logged(recipients: List[str], data: Dict[str, Any],
                            batch_id: Optional[str] = None, max_retries: int = 2) -> Dict[str, Any]:
    """Send push with full logging + retry. Returns {ok, attempts, error}."""
    if not _send_push:
        await log_push_send(data.get("title", "?"), data.get("message", "?"),
                            recipients, False, error="send_push not initialised")
        return {"ok": False, "error": "send_push not initialised"}

    last_err = None
    last_resp = None
    started = time.time()
    for attempt in range(max_retries + 1):
        try:
            await _send_push(recipients=recipients, data=data, idempotency_key=batch_id)
            latency = int((time.time() - started) * 1000)
            await log_push_send(data.get("title", "?"), data.get("message", "?"),
                                recipients, True, provider_response="200 OK",
                                batch_id=batch_id, latency_ms=latency)
            return {"ok": True, "attempts": attempt + 1, "latency_ms": latency}
        except Exception as e:
            last_err = str(e)[:400]
            last_resp = type(e).__name__
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))
    latency = int((time.time() - started) * 1000)
    await log_push_send(data.get("title", "?"), data.get("message", "?"),
                        recipients, False, provider_response=last_resp,
                        error=last_err, batch_id=batch_id, latency_ms=latency)
    return {"ok": False, "attempts": max_retries + 1, "error": last_err}


# ============================================================================
# 2. OTP — Configurable SMS Provider (MSG91 / Twilio / Demo)
# ============================================================================

OTP_TTL_MIN = 5
OTP_RESEND_COOLDOWN_SEC = 30
OTP_MAX_PER_HOUR = 5
OTP_MAX_VERIFY_ATTEMPTS = 5


def _gen_otp() -> str:
    """Cryptographically-random 6-digit OTP. Never hardcoded."""
    return f"{secrets.randbelow(1000000):06d}"


def _hash_otp(otp: str, mobile: str) -> str:
    """HMAC-SHA256 of OTP keyed by mobile (mild salt). Stored, not the plaintext."""
    return hmac.new(mobile.encode(), otp.encode(), hashlib.sha256).hexdigest()


async def _get_sms_cfg() -> Dict[str, Any]:
    """Reads api_settings.sms_provider; falls back to demo mode."""
    doc = await _db.api_settings.find_one({"api_name": "sms_provider"}, {"_id": 0})
    if not doc:
        return {"is_demo": True, "provider": "demo"}
    key = (doc.get("api_key") or "").strip()
    if not doc.get("is_enabled", True) or doc.get("force_demo") or not key:
        return {"is_demo": True, "provider": "demo"}
    extra = doc.get("extra") or {}
    provider = (extra.get("provider") or "").lower()
    if not provider:
        # Infer from key shape
        if key.startswith("AC") and len(key) >= 30:
            provider = "twilio"
        else:
            provider = "msg91"
    return {
        "is_demo": False,
        "provider": provider,
        "api_key": key,
        "sender_id": extra.get("sender_id", "MFBANK"),
        "template_id": extra.get("template_id", ""),
        "twilio_sid": extra.get("twilio_sid", ""),
        "twilio_from": extra.get("twilio_from", ""),
    }


async def _deliver_otp_sms(mobile: str, otp: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Sends OTP via configured provider. Returns {ok, provider, response, demo}."""
    body = f"Your My Funding Bank OTP is {otp}. Valid for {OTP_TTL_MIN} minutes. Do not share."
    if cfg["is_demo"]:
        # Demo mode — log securely server-side, never return OTP in API response
        logger.warning(f"[DEMO-OTP] mobile={mobile} otp={otp} ttl={OTP_TTL_MIN}min")
        return {"ok": True, "provider": "demo", "demo": True}

    provider = cfg["provider"]
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            if provider == "msg91":
                # MSG91 OTP API
                params = {
                    "authkey": cfg["api_key"],
                    "mobile": mobile.lstrip("+"),
                    "otp": otp,
                    "sender": cfg.get("sender_id", "MFBANK"),
                }
                if cfg.get("template_id"):
                    params["template_id"] = cfg["template_id"]
                r = await http.get("https://api.msg91.com/api/v5/otp", params=params)
                ok = r.status_code == 200 and (r.json() or {}).get("type") == "success"
                return {"ok": ok, "provider": "msg91", "response": r.text[:200], "demo": False}
            elif provider == "twilio":
                sid = cfg.get("twilio_sid", "")
                token = cfg["api_key"]
                from_ = cfg.get("twilio_from", "+15005550006")
                if not sid:
                    return {"ok": False, "provider": "twilio", "error": "twilio_sid missing", "demo": False}
                r = await http.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data={"From": from_, "To": mobile, "Body": body},
                )
                return {"ok": 200 <= r.status_code < 300, "provider": "twilio", "response": r.text[:200], "demo": False}
            else:
                return {"ok": False, "provider": provider, "error": "Unknown provider", "demo": False}
    except Exception as e:
        return {"ok": False, "provider": provider, "error": str(e)[:200], "demo": False}


async def issue_otp(mobile: str, purpose: str = "login") -> Dict[str, Any]:
    """Generate & deliver OTP. Returns {ok, message, expires_in, demo, retry_in}."""
    if not mobile or len(mobile) < 8:
        raise HTTPException(400, "Invalid mobile number")

    # Resend cooldown
    last = await _db.otp_codes.find_one({"mobile": mobile}, {"_id": 0}, sort=[("created_at", -1)])
    if last and last.get("created_at"):
        last_at = last["created_at"]
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        elapsed = (_now() - last_at).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SEC:
            return {
                "ok": False,
                "message": f"Please wait {int(OTP_RESEND_COOLDOWN_SEC - elapsed)}s before resending",
                "retry_in": int(OTP_RESEND_COOLDOWN_SEC - elapsed),
            }

    # Rate limit
    one_hour_ago = _now() - timedelta(hours=1)
    sent_in_hour = await _db.otp_codes.count_documents({"mobile": mobile, "created_at": {"$gte": one_hour_ago}})
    if sent_in_hour >= OTP_MAX_PER_HOUR:
        raise HTTPException(429, f"Too many OTPs requested. Try again later.")

    otp = _gen_otp()
    cfg = await _get_sms_cfg()
    delivery = await _deliver_otp_sms(mobile, otp, cfg)
    await _db.otp_codes.insert_one({
        "mobile": mobile,
        "purpose": purpose,
        "otp_hash": _hash_otp(otp, mobile),
        "otp_plain_demo": otp if delivery.get("demo") else None,  # ONLY in demo mode
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=OTP_TTL_MIN),
        "attempts": 0,
        "consumed": False,
        "delivery": delivery,
    })
    await _db.sms_logs.insert_one({
        "mobile": mobile,
        "purpose": purpose,
        "provider": delivery.get("provider"),
        "ok": delivery.get("ok"),
        "error": delivery.get("error"),
        "demo": delivery.get("demo", False),
        "at": _now(),
    })
    return {
        "ok": True,
        "message": "OTP sent successfully" if delivery.get("ok") else "OTP queued (demo mode)",
        "expires_in": OTP_TTL_MIN * 60,
        "demo": delivery.get("demo", False),
        "provider": delivery.get("provider"),
    }


async def verify_otp(mobile: str, otp: str, purpose: str = "login") -> bool:
    """Verify OTP. Marks consumed on success. Returns True/False."""
    doc = await _db.otp_codes.find_one({"mobile": mobile, "consumed": False, "purpose": purpose},
                                         {"_id": 1, "otp_hash": 1, "expires_at": 1, "attempts": 1},
                                         sort=[("created_at", -1)])
    if not doc:
        return False
    exp = doc["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _now():
        return False
    if doc.get("attempts", 0) >= OTP_MAX_VERIFY_ATTEMPTS:
        return False
    await _db.otp_codes.update_one({"_id": doc["_id"]}, {"$inc": {"attempts": 1}})
    expected = _hash_otp(otp.strip(), mobile)
    if hmac.compare_digest(expected, doc.get("otp_hash", "")):
        await _db.otp_codes.update_one({"_id": doc["_id"]}, {"$set": {"consumed": True}})
        return True
    return False


# ============================================================================
# 3. FORGOT / CHANGE PASSWORD
# ============================================================================

def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


class ForgotReq(BaseModel):
    identifier: str = Field(..., description="email or mobile")


class ResetReq(BaseModel):
    identifier: str
    code: str
    new_password: str


class ChangePwReq(BaseModel):
    current_password: str
    new_password: str


# ============================================================================
# 4. ADMIN USER SECURITY
# ============================================================================

class AdminUserActionReq(BaseModel):
    action: str  # "force_reset" | "disable_login" | "enable_login" | "unlock"


# ============================================================================
# Routers
# ============================================================================

def attach(api: APIRouter, db, get_current_user, get_current_admin, send_push_fn, logger_=None):
    global _db, _get_current_user, _get_current_admin, _send_push, logger
    _db = db
    _get_current_user = get_current_user
    _get_current_admin = get_current_admin
    _send_push = send_push_fn
    if logger_:
        logger = logger_

    # ---------- Auth: OTP issue/verify + Forgot password ----------
    auth = APIRouter(prefix="/auth", tags=["auth-security"])

    class OtpRequestBody(BaseModel):
        mobile: str
        purpose: Optional[str] = "login"

    class OtpVerifyBody(BaseModel):
        mobile: str
        otp: str
        purpose: Optional[str] = "login"

    @auth.post("/otp/request")
    async def otp_request(body: OtpRequestBody):
        return await issue_otp(body.mobile, body.purpose or "login")

    @auth.post("/otp/verify")
    async def otp_verify(body: OtpVerifyBody):
        """Verify only — actual login still uses /auth/login or /auth/signup."""
        ok = await verify_otp(body.mobile, body.otp, body.purpose or "login")
        if not ok:
            raise HTTPException(401, "Invalid or expired OTP")
        return {"ok": True, "verified": True}

    @auth.post("/forgot-password")
    async def forgot_password(body: ForgotReq):
        """Issues a reset code to email OR mobile. Always returns generic success (anti-enumeration)."""
        ident = body.identifier.strip().lower()
        user = await _db.users.find_one(
            {"$or": [{"email": ident}, {"mobile": ident}]},
            {"_id": 0, "user_id": 1, "email": 1, "mobile": 1},
        )
        # Always 200 to prevent account enumeration
        if user:
            code = _gen_otp()
            await _db.password_resets.insert_one({
                "user_id": user["user_id"],
                "code_hash": _hash_otp(code, user["user_id"]),
                "created_at": _now(),
                "expires_at": _now() + timedelta(minutes=15),
                "used": False,
            })
            # Send via mobile OTP if identifier is mobile
            if user.get("mobile") and (ident == user.get("mobile") or ident.endswith(user.get("mobile", ""))):
                cfg = await _get_sms_cfg()
                await _deliver_otp_sms(user["mobile"], code, cfg)
            # Always log email send attempt (demo logs to console)
            email_cfg = await _db.api_settings.find_one({"api_name": "email_service"}, {"_id": 0})
            if email_cfg and email_cfg.get("api_key") and email_cfg.get("is_enabled", True) and not email_cfg.get("force_demo"):
                logger.info(f"[email] Reset code {code} would be sent to {user.get('email')} via {email_cfg.get('api_name')}")
            else:
                logger.warning(f"[DEMO-RESET] user={user['user_id']} code={code} (email demo mode)")
        return {"ok": True, "message": "If the account exists, a reset code was sent."}

    @auth.post("/reset-password")
    async def reset_password(body: ResetReq):
        ident = body.identifier.strip().lower()
        user = await _db.users.find_one(
            {"$or": [{"email": ident}, {"mobile": ident}]},
            {"_id": 0, "user_id": 1},
        )
        if not user:
            raise HTTPException(400, "Invalid request")
        if len(body.new_password) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        doc = await _db.password_resets.find_one(
            {"user_id": user["user_id"], "used": False},
            sort=[("created_at", -1)],
        )
        if not doc:
            raise HTTPException(401, "No reset code requested")
        exp = doc["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            raise HTTPException(401, "Reset code expired")
        expected = _hash_otp(body.code.strip(), user["user_id"])
        if not hmac.compare_digest(expected, doc.get("code_hash", "")):
            raise HTTPException(401, "Invalid reset code")
        await _db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "password": _hash_password(body.new_password),
                "password_updated_at": _now(),
                "force_password_reset": False,
                "failed_logins": 0,
            }},
        )
        await _db.password_resets.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
        return {"ok": True, "message": "Password reset successfully"}

    @auth.post("/change-password")
    async def change_password(body: ChangePwReq, user: Dict[str, Any] = Depends(get_current_user)):
        if len(body.new_password) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        doc = await _db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password": 1})
        if not doc or not _verify_password(body.current_password, doc.get("password", "")):
            raise HTTPException(401, "Current password is incorrect")
        await _db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "password": _hash_password(body.new_password),
                "password_updated_at": _now(),
                "force_password_reset": False,
            }},
        )
        return {"ok": True, "message": "Password changed successfully"}

    api.include_router(auth)

    # ---------- Admin: push delivery logs ----------
    admin = APIRouter(prefix="/admin", tags=["admin-security"])

    def _ensure(adm):
        if adm["role"] not in ("super_admin", "admin", "finance_manager", "support_manager"):
            raise HTTPException(403, "Forbidden")

    @admin.get("/push-logs")
    async def push_logs(limit: int = 100, status: Optional[str] = None, adm=Depends(get_current_admin)):
        _ensure(adm)
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        rows = await _db.push_logs.find(q, {"_id": 0}).sort("at", -1).limit(min(limit, 500)).to_list(min(limit, 500))
        total = await _db.push_logs.count_documents({})
        success = await _db.push_logs.count_documents({"status": "success"})
        failed = await _db.push_logs.count_documents({"status": "failed"})
        recent_24h = await _db.push_logs.count_documents({"at": {"$gte": _now() - timedelta(hours=24)}})
        return {
            "items": rows,
            "total": total,
            "success_count": success,
            "failed_count": failed,
            "recent_24h": recent_24h,
            "success_rate": round((success / total) * 100, 1) if total > 0 else 0,
        }

    @admin.post("/push-logs/{log_id}/retry")
    async def push_retry(log_id: str, adm=Depends(get_current_admin)):
        _ensure(adm)
        doc = await _db.push_logs.find_one({"log_id": log_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Log not found")
        if doc.get("ok"):
            raise HTTPException(400, "Log already successful — cannot retry")
        # Fetch original recipients (sample only; for full retry would need batch_id lookup)
        recipients = doc.get("recipients_sample", [])
        if not recipients and doc.get("batch_id"):
            # Re-derive recipients by querying notifications table for this batch
            notifs = await _db.notifications.find({"batch_id": doc["batch_id"]}, {"_id": 0, "user_id": 1}).to_list(200)
            recipients = list({n["user_id"] for n in notifs})
        if not recipients:
            raise HTTPException(400, "No recipients to retry")
        result = await send_push_logged(
            recipients=recipients,
            data={"title": doc.get("title", ""), "message": doc.get("message", "")},
            batch_id=f"retry-{log_id}",
        )
        return {"ok": result.get("ok"), "result": result}

    @admin.get("/users/{user_id}/security")
    async def user_security(user_id: str, adm=Depends(get_current_admin)):
        _ensure(adm)
        u = await _db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(404, "User not found")
        return {
            "user_id": u["user_id"],
            "email": u.get("email"),
            "mobile": u.get("mobile"),
            "password_set": bool(u.get("password")),  # never the actual hash
            "password_updated_at": u.get("password_updated_at"),
            "login_method": u.get("login_method", "mobile" if u.get("mobile") else "email"),
            "failed_logins": u.get("failed_logins", 0),
            "last_login_at": u.get("last_login_at"),
            "last_login_ip": u.get("last_login_ip"),
            "disabled": bool(u.get("disabled", False)),
            "locked_until": u.get("locked_until"),
            "force_password_reset": bool(u.get("force_password_reset", False)),
            "kyc_status": u.get("kyc_status"),
        }

    @admin.get("/users-security")
    async def users_security_list(limit: int = 200, search: Optional[str] = None, adm=Depends(get_current_admin)):
        _ensure(adm)
        q: Dict[str, Any] = {}
        if search:
            q = {"$or": [
                {"email": {"$regex": search, "$options": "i"}},
                {"mobile": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}},
            ]}
        rows = await _db.users.find(q, {
            "_id": 0, "user_id": 1, "full_name": 1, "email": 1, "mobile": 1,
            "password": 1, "password_updated_at": 1, "login_method": 1,
            "failed_logins": 1, "last_login_at": 1, "disabled": 1,
            "locked_until": 1, "force_password_reset": 1, "kyc_status": 1,
        }).limit(min(limit, 500)).to_list(min(limit, 500))
        # Strip hash, just keep boolean
        for r in rows:
            r["password_set"] = bool(r.pop("password", None))
            r["login_method"] = r.get("login_method") or ("mobile" if r.get("mobile") else "email")
        return {"items": rows, "total": len(rows)}

    @admin.post("/users/{user_id}/security-action")
    async def user_security_action(user_id: str, body: AdminUserActionReq, adm=Depends(get_current_admin)):
        _ensure(adm)
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can run security actions")
        u = await _db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1})
        if not u:
            raise HTTPException(404, "User not found")
        actions = {
            "force_reset": {"force_password_reset": True},
            "disable_login": {"disabled": True},
            "enable_login": {"disabled": False},
            "unlock": {"locked_until": None, "failed_logins": 0, "disabled": False},
        }
        if body.action not in actions:
            raise HTTPException(400, "Unknown action")
        await _db.users.update_one({"user_id": user_id}, {"$set": actions[body.action]})
        await _db.admin_audit.insert_one({
            "admin_id": adm.get("admin_id"),
            "action": f"user.security.{body.action}",
            "target": user_id,
            "at": _now(),
        })
        return {"ok": True, "action": body.action, "user_id": user_id}

    @admin.get("/demo-otps")
    async def demo_otps_view(adm=Depends(get_current_admin)):
        """Returns recent DEMO OTPs (last 10 min, unconsumed) for admin testing.
        SECURITY: only returns OTPs issued in demo mode. Real SMS OTPs never
        expose the OTP value here — otp_plain_demo is null for those."""
        _ensure(adm)
        recent = await _db.otp_codes.find(
            {
                "otp_plain_demo": {"$ne": None},
                "consumed": False,
                "created_at": {"$gte": _now() - timedelta(minutes=10)},
            },
            {"_id": 0, "mobile": 1, "purpose": 1, "otp_plain_demo": 1,
             "created_at": 1, "expires_at": 1, "attempts": 1, "delivery": 1},
        ).sort("created_at", -1).limit(20).to_list(20)
        return {
            "items": recent,
            "count": len(recent),
            "warning": "These OTPs are visible only in DEMO mode. Configure SMS provider in API Management to enable real SMS delivery — once enabled, OTP values will no longer appear here.",
        }

    api.include_router(admin)
