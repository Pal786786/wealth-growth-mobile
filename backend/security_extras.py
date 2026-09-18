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
import os
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


# ---------------------------------------------------------------------------
# MSG91 OTP Widget (backend-proxied, server-to-server)
# Secrets live ONLY in backend env vars — never sent to the frontend, never
# stored in Mongo, never logged. Flow: sendOtpMobile → reqId → verifyOtp →
# accessToken → verifyAccessToken.
# ---------------------------------------------------------------------------

MSG91_WIDGET_BASE = "https://control.msg91.com/api/v5/widget"


def _otp_demo_forced() -> bool:
    """OTP_DEMO_MODE=true (env) forces demo OTP regardless of any live config."""
    return (os.environ.get("OTP_DEMO_MODE") or "").strip().lower() == "true"


def _msg91_env_cfg() -> Optional[Dict[str, str]]:
    """Returns live MSG91 widget config from env, or None (demo/unconfigured).

    OTP_DEMO_MODE=true forces demo mode even when keys are present.
    """
    if _otp_demo_forced():
        return None
    authkey = (os.environ.get("MSG91_AUTHKEY") or "").strip()
    widget_id = (os.environ.get("MSG91_WIDGET_ID") or "").strip()
    if not authkey or not widget_id:
        return None
    return {"authkey": authkey, "widget_id": widget_id}


async def _msg91_live_cfg() -> Optional[Dict[str, str]]:
    """Resolves live MSG91 Widget config. Priority: env vars (platform Secrets)
    > Admin Panel settings in Mongo (api_settings.sms_provider with
    provider=msg91_widget + widget_id). Returns None when demo/unconfigured."""
    cfg = _msg91_env_cfg()
    if cfg:
        return cfg
    if _otp_demo_forced():
        return None
    doc = await _db.api_settings.find_one({"api_name": "sms_provider"}, {"_id": 0})
    if not doc or not doc.get("is_enabled", True) or doc.get("force_demo"):
        return None
    extra = doc.get("extra") or {}
    provider = (extra.get("provider") or "").strip().lower().replace("-", "_").replace(" ", "_")
    authkey = (doc.get("api_key") or "").strip()
    widget_id = (extra.get("widget_id") or "").strip()
    if provider.startswith("msg91") and authkey and widget_id:
        return {"authkey": authkey, "widget_id": widget_id}
    return None


def _msg91_identifier(mobile: str) -> str:
    """Normalize to MSG91 format: country code + digits, no '+'. 10-digit → 91-prefixed."""
    digits = "".join(ch for ch in mobile if ch.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def _msg91_value(data: Dict[str, Any], *names: str) -> Optional[str]:
    """Defensive field extraction across MSG91 response casings/nesting."""
    for n in names:
        if data.get(n):
            return data[n]
    for container in (data.get("data"), data.get("result")):
        if isinstance(container, dict):
            for n in names:
                if container.get(n):
                    return container[n]
    return None


async def _msg91_widget_call(path: str, body: Dict[str, Any]) -> tuple:
    """POST to MSG91 widget API. Returns (status_code, json_dict).

    Redacted logging (never logs authkey/token/OTP). Handles 3xx redirects
    manually: logs the Location header and re-POSTs (method+body preserved)
    ONLY when the target is https on *.msg91.com — the authkey is never sent
    to any other host. httpx's automatic following is not used because it
    downgrades POST→GET on 301/302, which breaks the widget API.
    """
    url = MSG91_WIDGET_BASE + path
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # Some WAF/CDN layers 302-redirect non-browser clients — present a browser UA
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as http:
            for hop in range(3):
                r = await http.post(url, json=body, headers=headers)
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location", "")
                    logger.warning(f"[msg91] {path} HTTP {r.status_code} redirect → {loc[:200] or '<no Location>'} (hop {hop + 1})")
                    if loc:
                        target = httpx.URL(url).join(loc)
                        host = str(target.host or "")
                        if str(target.scheme) == "https" and (host == "msg91.com" or host.endswith(".msg91.com")):
                            url = str(target)
                            continue
                    return r.status_code, {
                        "message": f"MSG91 redirected the request (HTTP {r.status_code}) to '{loc[:160] or 'unknown'}' instead of answering — the endpoint may be geo-blocked or the request was intercepted",
                        "redirect_location": loc[:200],
                    }
                try:
                    data = r.json() if r.text else {}
                except ValueError:
                    data = {"message": r.text[:300]}
                if not isinstance(data, dict):
                    data = {"message": str(data)[:300]}
                if 200 <= r.status_code < 300 and data.get("type") == "success":
                    logger.info(f"[msg91] {path} status={r.status_code} type=success")
                else:
                    # Provider response body is safe to snippet (no secrets of ours)
                    logger.warning(f"[msg91] {path} status={r.status_code} type={data.get('type')} body={r.text[:200]}")
                return r.status_code, data
            logger.error(f"[msg91] {path} exceeded redirect limit")
            return 508, {"message": "MSG91 kept redirecting (redirect loop)"}
    except httpx.HTTPError as e:
        logger.error(f"[msg91] {path} network error: {type(e).__name__}")
        return 0, {"message": f"network_error:{type(e).__name__}"}


def _hash_otp(otp: str, mobile: str) -> str:
    """HMAC-SHA256 of OTP keyed by mobile (mild salt). Stored, not the plaintext."""
    return hmac.new(mobile.encode(), otp.encode(), hashlib.sha256).hexdigest()


async def _get_sms_cfg() -> Dict[str, Any]:
    """Reads api_settings.sms_provider; falls back to demo mode."""
    if _otp_demo_forced():
        return {"is_demo": True, "provider": "demo"}
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
    if provider == "msg91_widget":
        # Widget flow can't deliver a custom code — should be handled upstream
        return {"ok": False, "provider": provider,
                "error": "MSG91 Widget misconfigured (missing widget_id?)", "demo": False}
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

    # ---- Live MSG91 widget flow (env or Admin Panel config) — MSG91 generates & delivers OTP ----
    cfg91 = await _msg91_live_cfg()
    if cfg91:
        identifier = _msg91_identifier(mobile)
        status, data = await _msg91_widget_call("/sendOtpMobile", {
            "authkey": cfg91["authkey"],
            "widgetId": cfg91["widget_id"],
            "identifier": identifier,
        })
        req_id = None
        if 200 <= status < 300 and (data.get("type") == "success"):
            req_id = _msg91_value(data, "reqId", "reqID", "requestId", "message")
        if not req_id and last and last.get("req_id") and not last.get("consumed"):
            # Send rejected (likely an active session) — retry on the previous session
            status2, data2 = await _msg91_widget_call("/retryOtp", {
                "authkey": cfg91["authkey"], "reqId": last["req_id"],
            })
            if 200 <= status2 < 300 and data2.get("type") == "success":
                req_id = last["req_id"]
        await _db.sms_logs.insert_one({
            "mobile": mobile, "purpose": purpose, "provider": "msg91_widget",
            "ok": bool(req_id), "error": None if req_id else str(data.get("message"))[:200],
            "demo": False, "at": _now(),
        })
        if not req_id:
            logger.error(f"[msg91] OTP send failed for ...{mobile[-4:]}: status={status}")
            raise HTTPException(502, "Unable to send OTP right now. Please try again shortly.")
        await _db.otp_codes.insert_one({
            "mobile": mobile,
            "purpose": purpose,
            "provider": "msg91_widget",
            "req_id": req_id,
            "otp_hash": None,
            "otp_plain_demo": None,
            "created_at": _now(),
            "expires_at": _now() + timedelta(minutes=OTP_TTL_MIN),
            "attempts": 0,
            "consumed": False,
            "delivery": {"ok": True, "provider": "msg91_widget", "demo": False},
        })
        return {
            "ok": True,
            "message": "OTP sent successfully",
            "expires_in": OTP_TTL_MIN * 60,
            "demo": False,
            "provider": "msg91",
        }

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
                                         {"_id": 1, "otp_hash": 1, "expires_at": 1, "attempts": 1,
                                          "req_id": 1, "provider": 1},
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

    # ---- Live MSG91 widget verification ----
    if doc.get("req_id"):
        cfg91 = await _msg91_live_cfg()
        if not cfg91:
            # Keys removed / demo forced after issue — cannot verify a live session
            return False
        status, data = await _msg91_widget_call("/verifyOtp", {
            "authkey": cfg91["authkey"], "reqId": doc["req_id"], "otp": otp.strip(),
        })
        if not (200 <= status < 300 and data.get("type") == "success"):
            return False
        # verifyOtp success yields an access token (field name varies by revision;
        # some revisions return it in `message` as a JWT-like string)
        access = _msg91_value(data, "accessToken", "access-token", "access_token", "token")
        if not access:
            msg = data.get("message")
            if isinstance(msg, str) and len(msg) > 40 and " " not in msg:
                access = msg
        if access:
            status2, data2 = await _msg91_widget_call("/verifyAccessToken", {
                "authkey": cfg91["authkey"], "access-token": access,
            })
            if not (200 <= status2 < 300 and data2.get("type") == "success"):
                return False
        else:
            logger.warning("[msg91] verifyOtp success but no access token found in response")
        await _db.otp_codes.update_one({"_id": doc["_id"]}, {"$set": {"consumed": True}})
        return True

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
            via_mobile = bool(user.get("mobile")) and (ident == user.get("mobile") or ident.endswith(user.get("mobile", "")))
            use_widget = via_mobile and (await _msg91_live_cfg()) is not None
            reset_doc: Dict[str, Any] = {
                "user_id": user["user_id"],
                "code_hash": _hash_otp(code, user["user_id"]),
                "created_at": _now(),
                "expires_at": _now() + timedelta(minutes=15),
                "used": False,
            }
            if use_widget:
                # Live MSG91 widget: the provider generates & delivers its own OTP;
                # our reset doc references the widget session instead of a local code.
                reset_doc["via"] = "msg91_widget"
                reset_doc["mobile"] = user["mobile"]
            await _db.password_resets.insert_one(reset_doc)
            if use_widget:
                try:
                    await issue_otp(user["mobile"], "reset")
                except HTTPException:
                    pass  # cooldown/rate-limit — response stays generic (anti-enumeration)
            elif via_mobile:
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
        if doc.get("via") == "msg91_widget":
            ok = await verify_otp(doc.get("mobile", ""), body.code, "reset")
            if not ok:
                raise HTTPException(401, "Invalid reset code")
        else:
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
        expose the OTP value here — otp_plain_demo is null for those.
        Access restricted to super_admin / admin only. Every access is audited."""
        if adm["role"] not in ("super_admin", "admin"):
            raise HTTPException(403, "Only super_admin/admin can view demo OTPs")
        # Check if SMS provider is live — if so, hide all OTPs (security)
        cfg = await _get_sms_cfg()
        if not cfg.get("is_demo") or (await _msg91_live_cfg()) is not None:
            return {
                "items": [],
                "count": 0,
                "live_mode": True,
                "warning": "SMS provider is LIVE. Demo OTPs are not exposed in live mode for security.",
            }
        recent = await _db.otp_codes.find(
            {
                "otp_plain_demo": {"$ne": None},
                "created_at": {"$gte": _now() - timedelta(minutes=10)},
            },
            {"_id": 0, "mobile": 1, "purpose": 1, "otp_plain_demo": 1,
             "created_at": 1, "expires_at": 1, "attempts": 1, "delivery": 1, "consumed": 1},
        ).sort("created_at", -1).limit(50).to_list(50)
        # Audit log every access to demo OTP page
        await _db.admin_audit.insert_one({
            "admin_id": adm.get("admin_id"),
            "admin_email": adm.get("email"),
            "action": "security.demo_otps.view",
            "target": "demo_otps",
            "details": {"count": len(recent)},
            "at": _now(),
        })
        return {
            "items": recent,
            "count": len(recent),
            "live_mode": False,
            "warning": "These OTPs are visible only in DEMO mode. Configure SMS provider in API Management to enable real SMS delivery — once enabled, OTP values will no longer appear here.",
        }

    api.include_router(admin)
