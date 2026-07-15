"""Centralized API Settings module — manages all third-party integration keys & demo mode.

Provides:
- Registry of supported integrations (catalog)
- `api_settings` MongoDB collection (one doc per api_name)
- `get_config(api_name)` helper used by integrations to check mode/key
- Admin CRUD endpoints under /api/admin/api-settings
- Public status endpoint /api/app/api-status (for mobile demo banner)
- Test-connection helpers that never raise hard errors
"""
from __future__ import annotations

import os
import uuid
import httpx
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin import get_current_admin, _log_action  # type: ignore

_db = None

# ---------- Registry of supported integrations ----------
# Defines the "catalog" of APIs the admin can configure. Adding a new entry
# here automatically exposes it in the admin UI with no code changes elsewhere.
API_CATALOG: List[Dict[str, Any]] = [
    {
        "api_name": "payment_gateway_stripe",
        "display_name": "Stripe (Payments)",
        "category": "payments",
        "description": "Card payments / wallet top-up via Stripe Checkout.",
        "fields": ["api_key"],
        "test_kind": "stripe",
    },
    {
        "api_name": "payment_gateway_razorpay",
        "display_name": "Razorpay (Payments + Recharge)",
        "category": "payments",
        "description": "UPI / cards / mobile recharge via Razorpay.",
        "fields": ["api_key", "key_secret"],
        "test_kind": "razorpay",
    },
    {
        "api_name": "sms_provider",
        "display_name": "SMS Provider / OTP",
        "category": "messaging",
        "description": "Send real OTP/SMS via MSG91, Twilio, or use Firebase Phone Auth (ID-token verification on backend).",
        "fields": ["api_key", "provider", "sender_id", "template_id", "twilio_sid", "twilio_from", "firebase_project_id"],
        "test_kind": "sms_provider",
    },
    {
        "api_name": "email_service",
        "display_name": "Email Service",
        "category": "messaging",
        "description": "Transactional email (SendGrid / Resend).",
        "fields": ["api_key", "from_email"],
        "test_kind": "noop",
    },
    {
        "api_name": "stock_market",
        "display_name": "Stock Market Data (Alpha Vantage)",
        "category": "investments",
        "description": "Live equity prices for the Invest screen.",
        "fields": ["api_key"],
        "test_kind": "alpha_vantage",
    },
    {
        "api_name": "twelvedata",
        "display_name": "TwelveData (Live Forex + Metals)",
        "category": "investments",
        "description": "Real-time XAU/USD, EUR/USD and other FX / metals quotes.",
        "fields": ["api_key"],
        "test_kind": "twelvedata",
    },
    {
        # Sprint 15.0 — Finnhub is the new primary live provider.
        "api_name": "finnhub",
        "display_name": "Finnhub (PRIMARY — Live Market)",
        "category": "investments",
        "description": "Real-time FX/metals/crypto/indices via OANDA + Binance feeds (paid Q-plan).",
        "fields": ["api_key"],
        "test_kind": "finnhub",
    },
    {
        "api_name": "mutual_fund",
        "display_name": "Mutual Fund Data API",
        "category": "investments",
        "description": "Live NAV & scheme catalog (MFAPI / AMFI).",
        "fields": ["api_key"],
        "test_kind": "noop",
    },
    {
        "api_name": "gold_price",
        "display_name": "Gold Price API",
        "category": "investments",
        "description": "Live gold price per gram (Metals API / GoldAPI).",
        "fields": ["api_key"],
        "test_kind": "noop",
    },
    {
        "api_name": "flight_booking",
        "display_name": "Flight Booking API",
        "category": "travel",
        "description": "Flight search & bookings (Amadeus / Tripjack).",
        "fields": ["api_key", "client_secret"],
        "test_kind": "noop",
    },
    {
        "api_name": "hotel_booking",
        "display_name": "Hotel Booking API",
        "category": "travel",
        "description": "Hotel inventory & bookings (Booking.com / Agoda).",
        "fields": ["api_key", "client_secret"],
        "test_kind": "noop",
    },
    {
        "api_name": "push_notifications",
        "display_name": "Push Notifications (FCM)",
        "category": "messaging",
        "description": "Firebase Cloud Messaging push tokens.",
        "fields": ["server_key"],
        "test_kind": "noop",
    },
    {
        "api_name": "kyc_verification",
        "display_name": "KYC Verification API",
        "category": "compliance",
        "description": "PAN/Aadhaar verification (Karza/IDfy/Surepass).",
        "fields": ["api_key"],
        "test_kind": "noop",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_live(doc: Optional[Dict[str, Any]]) -> bool:
    """A config is LIVE if enabled, has api_key set, and is not explicitly in demo."""
    if not doc:
        return False
    if not doc.get("is_enabled", True):
        return False
    if doc.get("force_demo", False):
        return False
    key = (doc.get("api_key") or "").strip()
    return len(key) > 8 and not key.lower().startswith("demo")


def _status_of(doc: Optional[Dict[str, Any]]) -> str:
    """Returns 'live' | 'demo' | 'disabled'."""
    if doc and doc.get("is_enabled") is False:
        return "disabled"
    return "live" if _is_live(doc) else "demo"


async def seed_catalog():
    """Insert any missing catalog entries with demo defaults. Never overwrites api_key/extra/flags.
    DOES sync display_name/description/fields/category from catalog so UI stays consistent."""
    existing = await _db.api_settings.find({}, {"_id": 0}).to_list(200)
    existing_by_name = {r["api_name"]: r for r in existing}
    docs = []
    # Pre-seed Stripe & Alpha Vantage from env so they don't appear empty on first run
    env_seed = {
        "payment_gateway_stripe": os.environ.get("STRIPE_API_KEY", ""),
        "stock_market": os.environ.get("ALPHA_VANTAGE_KEY", ""),
    }
    for entry in API_CATALOG:
        if entry["api_name"] in existing_by_name:
            # Sync metadata fields from catalog (display_name/description/fields/category/test_kind)
            await _db.api_settings.update_one(
                {"api_name": entry["api_name"]},
                {"$set": {
                    "display_name": entry["display_name"],
                    "category": entry["category"],
                    "description": entry["description"],
                    "fields": entry["fields"],
                    "test_kind": entry["test_kind"],
                }},
            )
            continue
        env_key = env_seed.get(entry["api_name"], "")
        # Treat placeholder demo keys as empty
        if env_key.lower() in ("sk_test_emergent", "demo", "placeholder"):
            env_key = ""
        docs.append({
            "api_name": entry["api_name"],
            "display_name": entry["display_name"],
            "category": entry["category"],
            "description": entry["description"],
            "fields": entry["fields"],
            "test_kind": entry["test_kind"],
            "api_key": env_key,
            "extra": {},
            "is_enabled": True,
            "force_demo": False,
            "created_at": _now(),
            "updated_at": _now(),
        })
    if docs:
        await _db.api_settings.insert_many(docs)


async def get_config(api_name: str) -> Dict[str, Any]:
    """Returns config used by integrations to decide live vs demo.

    Always returns a dict with: {api_key, extra, is_enabled, is_demo, mode}.
    Falls back to a safe demo config if entry is missing.
    """
    doc = await _db.api_settings.find_one({"api_name": api_name}, {"_id": 0}) if _db is not None else None
    is_live = _is_live(doc)
    return {
        "api_key": (doc or {}).get("api_key", "") if is_live else "",
        "extra": (doc or {}).get("extra", {}),
        "is_enabled": (doc or {}).get("is_enabled", True),
        "is_demo": not is_live,
        "mode": _status_of(doc),
    }


# ---------- Admin endpoints ----------
class ApiUpsertReq(BaseModel):
    api_key: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    force_demo: Optional[bool] = None


router = APIRouter(prefix="/admin/api-settings", tags=["admin-api-settings"])


def _public_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Mask the api_key (don't expose full secret). Show last 4 chars."""
    key = (doc.get("api_key") or "")
    masked = (key[:4] + "•" * max(0, len(key) - 8) + key[-4:]) if len(key) >= 8 else ("•" * len(key) if key else "")
    return {
        "api_name": doc["api_name"],
        "display_name": doc.get("display_name", doc["api_name"]),
        "category": doc.get("category", "other"),
        "description": doc.get("description", ""),
        "fields": doc.get("fields", ["api_key"]),
        "test_kind": doc.get("test_kind", "noop"),
        "has_key": bool(key),
        "api_key_masked": masked,
        "extra": doc.get("extra", {}) or {},
        "is_enabled": doc.get("is_enabled", True),
        "force_demo": doc.get("force_demo", False),
        "status": _status_of(doc),
        "updated_at": doc.get("updated_at"),
    }


def _require_super_or_admin(admin: Dict[str, Any]):
    if admin["role"] not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only super_admin or admin can manage API keys")


@router.get("")
async def list_apis(admin=Depends(get_current_admin)):
    rows = await _db.api_settings.find({}, {"_id": 0}).to_list(200)
    by_name = {r["api_name"]: r for r in rows}
    out = []
    # Preserve catalog order; include any DB-only rows after
    for entry in API_CATALOG:
        doc = by_name.get(entry["api_name"])
        if doc:
            out.append(_public_doc(doc))
        else:
            # Catalog entry exists but DB row missing — surface as demo
            out.append(_public_doc({**entry, "api_key": "", "is_enabled": True, "force_demo": False}))
    catalog_names = {e["api_name"] for e in API_CATALOG}
    for doc in rows:
        if doc["api_name"] not in catalog_names:
            out.append(_public_doc(doc))
    demo_count = sum(1 for d in out if d["status"] == "demo")
    return {
        "items": out,
        "total": len(out),
        "demo_count": demo_count,
        "live_count": sum(1 for d in out if d["status"] == "live"),
        "disabled_count": sum(1 for d in out if d["status"] == "disabled"),
    }


@router.put("/{api_name}")
async def update_api(api_name: str, req: ApiUpsertReq, admin=Depends(get_current_admin)):
    _require_super_or_admin(admin)
    catalog_entry = next((e for e in API_CATALOG if e["api_name"] == api_name), None)
    existing = await _db.api_settings.find_one({"api_name": api_name}, {"_id": 0})
    if not catalog_entry and not existing:
        raise HTTPException(status_code=404, detail="Unknown api_name")
    base = existing or {
        "api_name": api_name,
        "display_name": (catalog_entry or {}).get("display_name", api_name),
        "category": (catalog_entry or {}).get("category", "other"),
        "description": (catalog_entry or {}).get("description", ""),
        "fields": (catalog_entry or {}).get("fields", ["api_key"]),
        "test_kind": (catalog_entry or {}).get("test_kind", "noop"),
        "api_key": "",
        "extra": {},
        "is_enabled": True,
        "force_demo": False,
        "created_at": _now(),
    }
    if req.api_key is not None:
        base["api_key"] = req.api_key.strip()
    if req.extra is not None:
        base["extra"] = req.extra
    if req.is_enabled is not None:
        base["is_enabled"] = req.is_enabled
    if req.force_demo is not None:
        base["force_demo"] = req.force_demo
    base["updated_at"] = _now()
    await _db.api_settings.update_one({"api_name": api_name}, {"$set": base}, upsert=True)
    # Sprint 14.1.2c — When saving a market-provider key on the API
    # Management page, propagate it to the canonical `market_provider_config`
    # collection AND push it into the LIVE ProviderManager immediately.
    # Otherwise the key would be persisted here but the running manager
    # (which reads from market_provider_config) would never see it.
    _provider_for_apiname = {
        "twelvedata":   "twelvedata",
        "finnhub":      "finnhub",
        "stock_market": "alphavantage",
        "alphavantage": "alphavantage",
    }
    _prov = _provider_for_apiname.get(api_name)
    if _prov and base.get("api_key"):
        try:
            from market_providers import key_store as _ks, propagate_api_key as _prop
            await _ks.canonical_write(_db, _prov, base["api_key"])
            await _prop(_prov, base["api_key"])
        except Exception:
            pass
    await _log_action(admin["admin_id"], "api_settings.update", target=api_name, meta={
        "is_enabled": base.get("is_enabled"),
        "force_demo": base.get("force_demo"),
        "has_key": bool(base.get("api_key")),
    })
    fresh = await _db.api_settings.find_one({"api_name": api_name}, {"_id": 0})
    return _public_doc(fresh)


@router.post("/{api_name}/test")
async def test_connection(api_name: str, admin=Depends(get_current_admin)):
    """Test a connection. ALWAYS returns 200 with {ok: bool, mode, message}.
    Never raises so the admin UI never breaks."""
    _require_super_or_admin(admin)
    doc = await _db.api_settings.find_one({"api_name": api_name}, {"_id": 0})
    if not doc:
        return {"ok": False, "mode": "demo", "message": "Not configured — running in demo mode."}
    if not doc.get("is_enabled", True):
        return {"ok": False, "mode": "disabled", "message": "API is disabled."}
    if doc.get("force_demo"):
        return {"ok": False, "mode": "demo", "message": "Force-demo is ON — live calls suppressed."}
    key = (doc.get("api_key") or "").strip()
    if not key:
        return {"ok": False, "mode": "demo", "message": "No API key set — demo mode active."}

    kind = doc.get("test_kind", "noop")
    try:
        if kind == "finnhub":
            async with httpx.AsyncClient(timeout=8) as http:
                r = await http.get("https://finnhub.io/api/v1/quote",
                                   params={"symbol": "OANDA:EUR_USD", "token": key})
                data = r.json() or {}
            if isinstance(data, dict) and float(data.get("c") or 0) > 0:
                return {"ok": True, "mode": "live",
                        "message": f"Finnhub OK. EUR/USD current={data['c']}"}
            return {"ok": False, "mode": "demo",
                    "message": f"Finnhub rejected key or symbol: HTTP {r.status_code} {str(data)[:120]}"}
        if kind == "twelvedata":
            async with httpx.AsyncClient(timeout=8) as http:
                r = await http.get("https://api.twelvedata.com/quote",
                                   params={"symbol": "EUR/USD", "apikey": key})
                data = r.json() or {}
            if isinstance(data, dict) and data.get("close"):
                return {"ok": True, "mode": "live",
                        "message": f"TwelveData authenticated. EUR/USD close={data.get('close')}"}
            if isinstance(data, dict) and data.get("status") == "error":
                msg = data.get("message", "")
                if "credit" in msg.lower() or "limit" in msg.lower():
                    return {"ok": False, "mode": "demo",
                            "message": f"TwelveData rate limited: {msg[:120]}"}
                return {"ok": False, "mode": "demo",
                        "message": f"TwelveData rejected key: {msg[:120]}"}
            return {"ok": False, "mode": "demo",
                    "message": "TwelveData returned no quote — check key."}
        if kind == "alpha_vantage":
            async with httpx.AsyncClient(timeout=8) as http:
                r = await http.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": key},
                )
                data = r.json() or {}
            if data.get("Global Quote", {}).get("05. price"):
                return {"ok": True, "mode": "live", "message": "Alpha Vantage responded with live data."}
            if data.get("Note") or data.get("Information"):
                return {"ok": False, "mode": "demo", "message": f"Rate-limited: {data.get('Note') or data.get('Information')}"}
            return {"ok": False, "mode": "demo", "message": "No quote returned — check key."}
        if kind == "stripe":
            if not key.startswith(("sk_test_", "sk_live_")):
                return {"ok": False, "mode": "demo", "message": "Stripe key must start with sk_test_ or sk_live_."}
            try:
                import stripe as _stripe
                _stripe.api_key = key
                _stripe.Balance.retrieve()
                return {"ok": True, "mode": "live", "message": "Stripe key authenticated."}
            except Exception as e:
                return {"ok": False, "mode": "demo", "message": f"Stripe rejected key: {e}"}
        if kind == "razorpay":
            secret = (doc.get("extra") or {}).get("key_secret", "")
            if not secret:
                return {"ok": False, "mode": "demo", "message": "Razorpay needs both Key ID and Key Secret."}
            try:
                async with httpx.AsyncClient(timeout=8, auth=(key, secret)) as http:
                    r = await http.get("https://api.razorpay.com/v1/payments?count=1")
                if r.status_code == 200:
                    return {"ok": True, "mode": "live", "message": "Razorpay authenticated."}
                return {"ok": False, "mode": "demo", "message": f"Razorpay error {r.status_code}"}
            except Exception as e:
                return {"ok": False, "mode": "demo", "message": f"Razorpay test failed: {e}"}
        if kind == "sms_provider":
            extra = doc.get("extra", {}) or {}
            provider = (extra.get("provider") or "").lower().strip()
            if not provider:
                # Auto-infer
                if key.startswith("AC") and len(key) >= 30:
                    provider = "twilio"
                else:
                    provider = "msg91"
            try:
                # Firebase Phone Auth — no balance check needed, validate by
                # fetching Google's public certs endpoint + project_id presence
                if provider == "firebase":
                    project_id = (extra.get("firebase_project_id") or "").strip()
                    if not project_id:
                        return {"ok": False, "mode": "demo",
                                "message": "Firebase needs 'firebase_project_id' (from google-services.json → project_info.project_id)."}
                    async with httpx.AsyncClient(timeout=8) as http:
                        r = await http.get("https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com")
                        if r.status_code == 200 and r.json():
                            return {"ok": True, "mode": "live",
                                    "message": f"Firebase Phone Auth ready. Project: {project_id}. Backend will verify ID tokens posted from mobile."}
                        return {"ok": False, "mode": "demo",
                                "message": "Could not reach Google's public-cert endpoint. Backend won't be able to verify Firebase ID tokens."}

                async with httpx.AsyncClient(timeout=8) as http:
                    if provider == "msg91":
                        # MSG91 balance endpoint validates the key (no SMS sent)
                        r = await http.get(
                            "https://api.msg91.com/api/balance.php",
                            params={"authkey": key, "type": "4"},
                        )
                        if r.status_code == 200 and r.text and not r.text.strip().lower().startswith("invalid"):
                            return {"ok": True, "mode": "live", "message": f"MSG91 authenticated. Balance check OK (balance: {r.text.strip()})."}
                        return {"ok": False, "mode": "demo", "message": f"MSG91 rejected key: {r.text[:120]}"}
                    elif provider == "twilio":
                        sid = extra.get("twilio_sid", "")
                        if not sid:
                            return {"ok": False, "mode": "demo", "message": "Twilio needs both Account SID and Auth Token."}
                        r = await http.get(
                            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                            auth=(sid, key),
                        )
                        if r.status_code == 200:
                            return {"ok": True, "mode": "live", "message": "Twilio account authenticated."}
                        return {"ok": False, "mode": "demo", "message": f"Twilio rejected (status {r.status_code})"}
                    else:
                        return {"ok": False, "mode": "demo", "message": f"Unknown SMS provider: {provider}"}
            except Exception as e:
                return {"ok": False, "mode": "demo", "message": f"SMS provider test failed: {e}"}
        # noop / unknown: optimistic
        return {"ok": True, "mode": "live", "message": "Key saved. Live calls will be attempted on next request."}
    except Exception as e:
        return {"ok": False, "mode": "demo", "message": f"Test failed safely: {e}"}


# ---------- Public status endpoint (no auth) ----------
public_router = APIRouter(prefix="/app", tags=["public-api-status"])


@public_router.get("/api-status")
async def public_api_status():
    """Returns demo/live status of all integrations for the mobile UI banner.
    Never exposes the actual key."""
    rows = await _db.api_settings.find({}, {"_id": 0}).to_list(200)
    by_name = {r["api_name"]: r for r in rows}
    items = []
    for entry in API_CATALOG:
        doc = by_name.get(entry["api_name"])
        items.append({
            "api_name": entry["api_name"],
            "display_name": entry["display_name"],
            "category": entry["category"],
            "status": _status_of(doc),
        })
    demo = [i for i in items if i["status"] == "demo"]
    return {
        "any_demo": len(demo) > 0,
        "demo_count": len(demo),
        "live_count": sum(1 for i in items if i["status"] == "live"),
        "items": items,
    }


def attach(parent_router: APIRouter, db):
    global _db
    _db = db
    parent_router.include_router(router)
    parent_router.include_router(public_router)
