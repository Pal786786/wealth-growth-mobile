"""Sprint 17 — Real MT5 Trading Account Module (Phase 1: account opening only).

Scope
-----
  * User applies for ONE real MT5 account (email only — KYC deferred).
  * Provisioning goes through an isolated MT5AccountService; the rest of the
    app never talks to the MT5 Manager API directly.
  * NO fake MT5 accounts: if the Manager API is not configured the
    application is stored and marked FAILED with error_code MT5_UNAVAILABLE.
  * Fully separated from demo trading (own collections, no demo engine use).

Collections
-----------
  real_trading_accounts   — one doc per (user_id, account_type)
  real_account_audit      — append-only provisioning/event log
  real_account_config     — admin-editable defaults (doc _id="defaults")

States: NOT_CREATED (no doc) → PENDING → ACTIVE | FAILED → (retry → PENDING)
        ACTIVE ↔ SUSPENDED (admin)
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

logger = logging.getLogger("real_accounts")

ACCOUNTS_COLL = "real_trading_accounts"
AUDIT_COLL = "real_account_audit"
CONFIG_COLL = "real_account_config"

# Centralised provisioning defaults — admin-editable via the config endpoint,
# stored in real_account_config. NEVER hardcode these elsewhere.
REAL_ACCOUNT_DEFAULTS: Dict[str, Any] = {
    "mt5_server": os.environ.get("MT5_SERVER", "Broker-MT5-Live"),
    "account_type": "standard",
    "currency": "USD",
    "leverage": 100,
    "group": "real\\standard",
    "trade_mode": "netting",
    "initial_balance": 0,
}

VALID_STATUSES = {"PENDING", "ACTIVE", "FAILED", "SUSPENDED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================== MT5 service
class MT5AccountService:
    """Single integration point for the MT5 Manager API.

    Reads credentials from the environment:
        MT5_MANAGER_API_URL   — base URL of the broker's Manager/Web API
        MT5_MANAGER_LOGIN     — manager login
        MT5_MANAGER_PASSWORD  — manager password  (never leaves the backend)
        MT5_SERVER            — trade server name shown to users

    No credentials configured → every call returns a structured failure with
    error_code MT5_UNAVAILABLE. Fake account numbers are NEVER generated.
    """

    def __init__(self) -> None:
        self.api_url = (os.environ.get("MT5_MANAGER_API_URL") or "").rstrip("/")
        self.login = os.environ.get("MT5_MANAGER_LOGIN") or ""
        self.password = os.environ.get("MT5_MANAGER_PASSWORD") or ""

    @property
    def available(self) -> bool:
        return bool(self.api_url and self.login and self.password)

    def _unavailable(self) -> Dict[str, Any]:
        logger.error(
            "MT5 provisioning unavailable — set MT5_MANAGER_API_URL, "
            "MT5_MANAGER_LOGIN and MT5_MANAGER_PASSWORD in backend/.env "
            "(broker Manager/Web API credentials required)."
        )
        return {
            "success": False,
            "error_code": "MT5_UNAVAILABLE",
            "message": "MT5 provisioning unavailable — broker Manager API is not configured.",
        }

    async def _call(self, method: str, path: str,
                    payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generic Manager API call with structured error mapping."""
        if not self.available:
            return self._unavailable()
        try:
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.request(
                    method, f"{self.api_url}{path}", json=payload,
                    auth=(self.login, self.password),
                )
            if r.status_code in (401, 403):
                return {"success": False, "error_code": "MT5_AUTH_FAILED",
                        "message": f"Manager API authentication failed (HTTP {r.status_code})."}
            if r.status_code >= 400:
                return {"success": False, "error_code": f"MT5_HTTP_{r.status_code}",
                        "message": r.text[:200]}
            return {"success": True, "data": r.json()}
        except httpx.TimeoutException:
            return {"success": False, "error_code": "MT5_TIMEOUT",
                    "message": "MT5 Manager API request timed out."}
        except httpx.HTTPError as e:
            return {"success": False, "error_code": "MT5_NETWORK_ERROR",
                    "message": str(e)[:200]}
        except Exception as e:  # pragma: no cover
            return {"success": False, "error_code": "MT5_UNKNOWN_ERROR",
                    "message": f"{type(e).__name__}: {str(e)[:160]}"}

    async def create_real_account(self, *, email: str, name: str,
                                  cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Create a live MT5 account. Returns
        {success, mt5_account_number?, error_code?, message?}."""
        res = await self._call("POST", "/api/users/create", {
            "email": email, "name": name,
            "group": cfg["group"], "leverage": cfg["leverage"],
            "currency": cfg["currency"], "trade_mode": cfg["trade_mode"],
        })
        if not res["success"]:
            return res
        login_id = (res.get("data") or {}).get("login")
        if not login_id:
            return {"success": False, "error_code": "MT5_CREATE_REJECTED",
                    "message": "Manager API did not return an account login."}
        return {"success": True, "mt5_account_number": str(login_id)}

    async def get_account(self, mt5_account_number: str) -> Dict[str, Any]:
        return await self._call("GET", f"/api/users/{mt5_account_number}")

    async def disable_account(self, mt5_account_number: str) -> Dict[str, Any]:
        return await self._call("POST", f"/api/users/{mt5_account_number}/disable")

    async def reset_password(self, mt5_account_number: str) -> Dict[str, Any]:
        return await self._call("POST", f"/api/users/{mt5_account_number}/reset-password")

    async def sync_account(self, mt5_account_number: str) -> Dict[str, Any]:
        return await self.get_account(mt5_account_number)


mt5_service = MT5AccountService()


# ============================================================== helpers
class ApplyReq(BaseModel):
    email: EmailStr


_db = None  # set by attach()


async def _get_config() -> Dict[str, Any]:
    doc = await _db[CONFIG_COLL].find_one({"_id": "defaults"}) or {}
    cfg = {**REAL_ACCOUNT_DEFAULTS, **{k: v for k, v in doc.items() if k != "_id"}}
    return cfg


async def _audit(user_id: str, application_id: str, action: str, status: str,
                 error_code: Optional[str] = None,
                 error_message: Optional[str] = None,
                 actor: str = "user") -> None:
    await _db[AUDIT_COLL].insert_one({
        "audit_id": f"raud_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "application_id": application_id,
        "action": action,
        "status": status,
        "actor": actor,
        "error_code": error_code,
        "error_message": error_message,
        "at": _now(),
    })


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Response shape — NEVER includes secrets/internal fields."""
    return {
        "application_id": doc.get("application_id"),
        "email": doc.get("email"),
        "mt5_account_number": doc.get("mt5_account_number"),
        "mt5_server": doc.get("mt5_server"),
        "account_type": doc.get("account_type"),
        "currency": doc.get("currency"),
        "leverage": doc.get("leverage"),
        "group": doc.get("group"),
        "status": doc.get("status"),
        "kyc_status": doc.get("kyc_status", "NOT_REQUIRED"),
        "error_code": doc.get("error_code"),
        "error_message": doc.get("error_message"),
        "created_at": doc.get("created_at"),
        "provisioned_at": doc.get("provisioned_at"),
    }


async def _provision(doc: Dict[str, Any], actor: str = "user") -> Dict[str, Any]:
    """Run MT5 provisioning for a PENDING account doc; returns updated doc."""
    user_id, app_id = doc["user_id"], doc["application_id"]
    cfg = await _get_config()
    await _audit(user_id, app_id, "REAL_ACCOUNT_PROVISIONING_STARTED", "PENDING", actor=actor)
    res = await mt5_service.create_real_account(
        email=doc["email"], name=doc.get("full_name") or doc["email"], cfg=cfg)
    now = _now()
    if res.get("success"):
        upd = {
            "status": "ACTIVE",
            "mt5_account_number": res["mt5_account_number"],
            "provisioned_at": now, "updated_at": now, "last_sync_at": now,
            "error_code": None, "error_message": None,
        }
        await _db[ACCOUNTS_COLL].update_one(
            {"application_id": app_id}, {"$set": upd})
        await _audit(user_id, app_id, "REAL_ACCOUNT_CREATED", "ACTIVE", actor=actor)
    else:
        upd = {
            "status": "FAILED", "updated_at": now,
            "error_code": res.get("error_code", "MT5_UNKNOWN_ERROR"),
            "error_message": res.get("message", "Unknown provisioning error"),
        }
        await _db[ACCOUNTS_COLL].update_one(
            {"application_id": app_id}, {"$set": upd})
        await _audit(user_id, app_id, "REAL_ACCOUNT_PROVISIONING_FAILED", "FAILED",
                     error_code=upd["error_code"], error_message=upd["error_message"],
                     actor=actor)
    return await _db[ACCOUNTS_COLL].find_one({"application_id": app_id})


# ============================================================== attach
def attach(api, db, get_current_user, get_current_admin) -> None:
    global _db
    _db = db

    # ---------------------------------------------------------- user routes
    @api.post("/real-account/apply")
    async def apply_real_account(req: ApplyReq, user=Depends(get_current_user)):
        email = req.email.strip().lower()
        user_id = user["user_id"]
        existing = await db[ACCOUNTS_COLL].find_one(
            {"user_id": user_id, "account_type": (await _get_config())["account_type"]})
        if existing and existing["status"] in ("PENDING", "ACTIVE", "SUSPENDED"):
            return {"success": False, "status": existing["status"],
                    "error_code": "DUPLICATE_ACCOUNT",
                    "message": "A real trading account already exists for this user.",
                    "account": _public(existing)}
        if existing and existing["status"] == "FAILED":
            # A failed application exists — treat apply as a retry.
            await db[ACCOUNTS_COLL].update_one(
                {"application_id": existing["application_id"]},
                {"$set": {"status": "PENDING", "email": email, "updated_at": _now()}})
            await _audit(user_id, existing["application_id"],
                         "REAL_ACCOUNT_PROVISIONING_RETRIED", "PENDING")
            fresh = await db[ACCOUNTS_COLL].find_one(
                {"application_id": existing["application_id"]})
            doc = await _provision(fresh)
            ok = doc["status"] == "ACTIVE"
            return {"success": ok, "status": doc["status"],
                    "error_code": doc.get("error_code"),
                    "message": doc.get("error_message") if not ok else "Real trading account created.",
                    "account": _public(doc)}

        cfg = await _get_config()
        app_id = f"rapp_{uuid.uuid4().hex[:12]}"
        now = _now()
        doc = {
            "application_id": app_id,
            "user_id": user_id,
            "email": email,
            "full_name": user.get("full_name"),
            "mt5_account_number": None,
            "mt5_server": cfg["mt5_server"],
            "account_type": cfg["account_type"],
            "currency": cfg["currency"],
            "leverage": cfg["leverage"],
            "group": cfg["group"],
            "trade_mode": cfg["trade_mode"],
            "status": "PENDING",
            "kyc_status": "NOT_REQUIRED",   # future KYC sprint
            "created_at": now, "updated_at": now,
            "provisioned_at": None, "last_sync_at": None,
            "error_code": None, "error_message": None,
        }
        try:
            await db[ACCOUNTS_COLL].insert_one(doc)
        except Exception:
            # unique (user_id, account_type) race → return the existing one
            existing = await db[ACCOUNTS_COLL].find_one(
                {"user_id": user_id, "account_type": cfg["account_type"]})
            return {"success": False, "status": existing["status"],
                    "error_code": "DUPLICATE_ACCOUNT",
                    "message": "A real trading account already exists for this user.",
                    "account": _public(existing)}
        await _audit(user_id, app_id, "REAL_ACCOUNT_APPLICATION_CREATED", "PENDING")
        doc = await _provision(doc)
        ok = doc["status"] == "ACTIVE"
        return {"success": ok, "status": doc["status"],
                "error_code": doc.get("error_code"),
                "message": "Real trading account created." if ok else doc.get("error_message"),
                "account": _public(doc)}

    @api.get("/real-account")
    async def get_real_account(user=Depends(get_current_user)):
        doc = await db[ACCOUNTS_COLL].find_one({"user_id": user["user_id"]})
        if not doc:
            return {"status": "NOT_CREATED", "account": None}
        return {"status": doc["status"], "account": _public(doc)}

    @api.get("/real-account/status")
    async def get_real_account_status(user=Depends(get_current_user)):
        doc = await db[ACCOUNTS_COLL].find_one({"user_id": user["user_id"]})
        return {"status": doc["status"] if doc else "NOT_CREATED"}

    @api.post("/real-account/retry")
    async def retry_real_account(user=Depends(get_current_user)):
        doc = await db[ACCOUNTS_COLL].find_one({"user_id": user["user_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="No real account application found")
        if doc["status"] != "FAILED":
            return {"success": False, "status": doc["status"],
                    "error_code": "INVALID_STATE",
                    "message": f"Retry only allowed from FAILED (current: {doc['status']})."}
        await db[ACCOUNTS_COLL].update_one(
            {"application_id": doc["application_id"]},
            {"$set": {"status": "PENDING", "updated_at": _now()}})
        await _audit(user["user_id"], doc["application_id"],
                     "REAL_ACCOUNT_PROVISIONING_RETRIED", "PENDING")
        fresh = await db[ACCOUNTS_COLL].find_one({"application_id": doc["application_id"]})
        out = await _provision(fresh)
        ok = out["status"] == "ACTIVE"
        return {"success": ok, "status": out["status"],
                "error_code": out.get("error_code"),
                "message": "Real trading account created." if ok else out.get("error_message"),
                "account": _public(out)}

    # ---------------------------------------------------------- admin routes
    @api.get("/admin/real-accounts")
    async def admin_list(status: Optional[str] = Query(None),
                         admin=Depends(get_current_admin)):
        q: Dict[str, Any] = {}
        if status and status.upper() != "ALL":
            if status.upper() not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status filter")
            q["status"] = status.upper()
        cur = db[ACCOUNTS_COLL].find(q, {"_id": 0}).sort("created_at", -1).limit(500)
        items = [d async for d in cur]
        counts: Dict[str, int] = {}
        async for d in db[ACCOUNTS_COLL].aggregate(
                [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
            counts[d["_id"]] = d["n"]
        return {"accounts": [_public(d) | {"user_id": d["user_id"]} for d in items],
                "counts": counts}

    @api.get("/admin/real-accounts/{application_id}")
    async def admin_detail(application_id: str,
                           admin=Depends(get_current_admin)):
        doc = await db[ACCOUNTS_COLL].find_one({"application_id": application_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        hist = [h async for h in db[AUDIT_COLL]
                .find({"application_id": application_id}, {"_id": 0})
                .sort("at", 1)]
        return {"account": _public(doc) | {"user_id": doc["user_id"]},
                "history": hist}

    @api.post("/admin/real-accounts/{application_id}/retry")
    async def admin_retry(application_id: str,
                          admin=Depends(get_current_admin)):
        doc = await db[ACCOUNTS_COLL].find_one({"application_id": application_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc["status"] != "FAILED":
            raise HTTPException(status_code=400, detail=f"Retry only from FAILED (current: {doc['status']})")
        await db[ACCOUNTS_COLL].update_one(
            {"application_id": application_id},
            {"$set": {"status": "PENDING", "updated_at": _now()}})
        await _audit(doc["user_id"], application_id,
                     "REAL_ACCOUNT_PROVISIONING_RETRIED", "PENDING", actor="admin")
        fresh = await db[ACCOUNTS_COLL].find_one({"application_id": application_id})
        out = await _provision(fresh, actor="admin")
        return {"success": out["status"] == "ACTIVE", "status": out["status"],
                "account": _public(out)}

    @api.post("/admin/real-accounts/{application_id}/suspend")
    async def admin_suspend(application_id: str,
                            admin=Depends(get_current_admin)):
        doc = await db[ACCOUNTS_COLL].find_one({"application_id": application_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc["status"] != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"Only ACTIVE accounts can be suspended (current: {doc['status']})")
        await db[ACCOUNTS_COLL].update_one(
            {"application_id": application_id},
            {"$set": {"status": "SUSPENDED", "updated_at": _now()}})
        await _audit(doc["user_id"], application_id, "REAL_ACCOUNT_SUSPENDED",
                     "SUSPENDED", actor="admin")
        if doc.get("mt5_account_number"):
            await mt5_service.disable_account(doc["mt5_account_number"])
        return {"success": True, "status": "SUSPENDED"}

    @api.post("/admin/real-accounts/{application_id}/activate")
    async def admin_activate(application_id: str,
                             admin=Depends(get_current_admin)):
        doc = await db[ACCOUNTS_COLL].find_one({"application_id": application_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc["status"] != "SUSPENDED":
            raise HTTPException(status_code=400, detail=f"Only SUSPENDED accounts can be reactivated (current: {doc['status']})")
        await db[ACCOUNTS_COLL].update_one(
            {"application_id": application_id},
            {"$set": {"status": "ACTIVE", "updated_at": _now()}})
        await _audit(doc["user_id"], application_id, "REAL_ACCOUNT_REACTIVATED",
                     "ACTIVE", actor="admin")
        return {"success": True, "status": "ACTIVE"}

    @api.get("/admin/real-accounts-config")
    async def admin_get_config(admin=Depends(get_current_admin)):
        cfg = await _get_config()
        return {"config": cfg, "mt5_provisioning_available": mt5_service.available}

    @api.put("/admin/real-accounts-config")
    async def admin_set_config(body: Dict[str, Any],
                               admin=Depends(get_current_admin)):
        allowed = set(REAL_ACCOUNT_DEFAULTS)
        upd = {k: v for k, v in (body or {}).items() if k in allowed}
        if not upd:
            raise HTTPException(status_code=400, detail="No valid config keys")
        await db[CONFIG_COLL].update_one({"_id": "defaults"}, {"$set": upd}, upsert=True)
        return {"success": True, "config": await _get_config()}

    logger.info("real_accounts attached (Sprint 17 Phase 1) — mt5_available=%s",
                mt5_service.available)


async def ensure_indexes(db) -> None:
    try:
        await db[ACCOUNTS_COLL].create_index(
            [("user_id", 1), ("account_type", 1)], unique=True, name="user_acct_type")
        await db[ACCOUNTS_COLL].create_index("application_id", unique=True)
        await db[AUDIT_COLL].create_index([("application_id", 1), ("at", 1)])
    except Exception as e:  # pragma: no cover
        logger.warning("real_accounts index init failed: %s", e)
