"""Sprint 12.2.1 — Wallet QR Top-up routes.

Endpoints:
  Public (user-authenticated):
    GET  /api/wallet/qr/config                — public config (allowed VPAs, merchant name)
    POST /api/wallet/qr/parse                 — parse & validate a scanned UPI URI
    POST /api/wallet/qr/initiate              — parse + validate + create order + return UPI intent
    GET  /api/wallet/qr/status/{order_id}     — poll payment status (proxy to payments engine)

  Admin:
    GET  /api/admin/wallet/qr/config          — read allowed VPAs / merchant name
    PUT  /api/admin/wallet/qr/config          — update allowed VPAs / merchant name

Only MFB-owned VPAs (configured in `wallet_qr_config` singleton) are permitted.
Third-party QRs are rejected with a friendly `not_supported` reason.
"""
from __future__ import annotations
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Body, Header
from pydantic import BaseModel, Field

logger = logging.getLogger("wallet_qr")


# ------------------------------------------------------------ constants ----
DEFAULT_CONFIG: Dict[str, Any] = {
    "_id": "singleton",
    "merchant_name": "My Funding Bank",
    "merchant_code": "5411",           # generic merchant category code
    "allowed_vpas": [
        # Populated by admin. Kept empty by default so QR flow is opt-in.
    ],
    "allowed_vpa_domains": [],          # e.g. ["mfb.razorpay", "myfundingbank"]
    "min_amount": 1.0,                  # in rupees
    "max_amount": 200_000.0,            # in rupees
    "note_template": "MFB Wallet Top-up · {order_id}",
    "enabled": True,
}

# UPI VPA syntax: local@handle, both alnum + . _ - allowed.
_VPA_RE = re.compile(r"^[a-zA-Z0-9._\-]{2,64}@[a-zA-Z0-9.\-]{2,64}$")
_UPI_SCHEMES = {"upi", "gpay", "phonepe", "paytmmp", "bhim"}


# ------------------------------------------------------------ models -------
class ParseQRIn(BaseModel):
    upi_uri: str = Field(..., min_length=6, max_length=2000)


class InitiateQRIn(BaseModel):
    upi_uri: str = Field(..., min_length=6, max_length=2000)
    amount: float = Field(..., gt=0)   # rupees. If QR has an amount, must match.


class ConfigPatch(BaseModel):
    merchant_name: Optional[str] = None
    merchant_code: Optional[str] = None
    allowed_vpas: Optional[List[str]] = None
    allowed_vpa_domains: Optional[List[str]] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    note_template: Optional[str] = None
    enabled: Optional[bool] = None


# ------------------------------------------------------------ helpers ------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_upi_uri(uri: str) -> Dict[str, Any]:
    """Robust UPI URI parser. Returns dict with keys:
       pa (payee vpa), pn (payee name), am (amount str or ""),
       cu (currency), tn (transaction note), tr (ref id), mc (merchant code),
       url_scheme (upi/gpay/etc), raw_params.
    """
    if not isinstance(uri, str):
        raise ValueError("URI must be a string")
    stripped = uri.strip()
    # Some scanners return `"upi://pay?..."`; some return without scheme.
    if "://" not in stripped:
        raise ValueError("Not a UPI URI (missing scheme)")
    parsed = urlparse(stripped)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _UPI_SCHEMES:
        raise ValueError(f"Unsupported URI scheme: {scheme}")
    if parsed.netloc.lower() != "pay":
        # Some UPI URIs use `upi://pay` — reject others (e.g., `upi://transfer`)
        raise ValueError(f"Unsupported UPI action: {parsed.netloc}")
    q = parse_qs(parsed.query, keep_blank_values=True)

    def _first(k: str) -> str:
        v = q.get(k) or []
        return v[0] if v else ""

    return {
        "pa": _first("pa").strip(),
        "pn": _first("pn").strip(),
        "am": _first("am").strip(),
        "cu": (_first("cu") or "INR").upper(),
        "tn": _first("tn").strip(),
        "tr": _first("tr").strip(),
        "mc": _first("mc").strip(),
        "url_scheme": scheme,
        "raw_params": {k: v[0] if v else "" for k, v in q.items()},
    }


def _validate_vpa(vpa: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Returns {'ok': bool, 'reason': str|None, 'match_type': 'vpa'|'domain'|None}."""
    if not vpa or not _VPA_RE.match(vpa):
        return {"ok": False, "reason": "invalid_vpa_format", "match_type": None}
    allowed = {v.lower().strip() for v in (cfg.get("allowed_vpas") or []) if isinstance(v, str)}
    if vpa.lower() in allowed:
        return {"ok": True, "reason": None, "match_type": "vpa"}
    # Domain-level match (useful for dynamic sub-VPAs like `order123@merchant`)
    _, _, handle = vpa.partition("@")
    handle = handle.lower()
    domains = {d.lower().strip() for d in (cfg.get("allowed_vpa_domains") or []) if isinstance(d, str)}
    if handle in domains:
        return {"ok": True, "reason": None, "match_type": "domain"}
    return {"ok": False, "reason": "not_mfb_vpa", "match_type": None}


def build_upi_intent(
    *, payee_vpa: str, payee_name: str, amount_rupees: float,
    order_receipt: str, currency: str = "INR",
    merchant_code: Optional[str] = None, note: Optional[str] = None,
) -> str:
    """Assemble a canonical `upi://pay?...` intent URI.

    NB: we intentionally build server-side to prevent client tampering.
    """
    parts = [
        ("pa", payee_vpa),
        ("pn", payee_name or "My Funding Bank"),
        ("am", f"{float(amount_rupees):.2f}"),
        ("cu", currency),
        ("tr", order_receipt),
        ("tn", (note or f"MFB Top-up {order_receipt}")[:80]),
    ]
    if merchant_code:
        parts.append(("mc", merchant_code))
    return "upi://pay?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in parts if v)


# ------------------------------------------------------------ attach --------
def attach(app, db, get_current_user, get_current_admin, payments_engine, log_action=None):
    """Wire the wallet-QR routes onto the FastAPI app.

    `payments_engine` is the existing Razorpay engine (from payments/engine.py).
    We call `engine.create_order(...)` to reuse the exact same order-creation +
    idempotency + webhook credit path as the standard top-up.
    """

    async def _cfg() -> Dict[str, Any]:
        doc = await db.wallet_qr_config.find_one({"_id": "singleton"})
        if not doc:
            await db.wallet_qr_config.insert_one({**DEFAULT_CONFIG, "created_at": _now()})
            return dict(DEFAULT_CONFIG)
        merged = {**DEFAULT_CONFIG, **doc}
        merged.pop("_id", None)
        return merged

    async def _log(actor_id: str, action: str, target: Optional[str] = None,
                    meta: Optional[Dict[str, Any]] = None):
        if log_action is None:
            return
        try:
            await log_action(actor_id, action, target=target, meta=meta or {})
        except Exception as e:
            logger.debug("audit log failed: %s", e)

    api = APIRouter()

    # =========================== USER ROUTES ==============================
    @api.get("/wallet/qr/config")
    async def user_get_config(user=Depends(get_current_user)):
        c = await _cfg()
        # Only expose what the client needs — never expose provider keys / secrets
        return {
            "enabled": c.get("enabled", True),
            "merchant_name": c.get("merchant_name"),
            "allowed_vpas": c.get("allowed_vpas") or [],
            "allowed_vpa_domains": c.get("allowed_vpa_domains") or [],
            "min_amount": float(c.get("min_amount", 1.0)),
            "max_amount": float(c.get("max_amount", 200_000.0)),
        }

    @api.post("/wallet/qr/parse")
    async def user_parse(body: ParseQRIn, user=Depends(get_current_user)):
        """Parse-only. Does NOT create a Razorpay order — useful for the
        confirmation screen where the user has just scanned but hasn't
        confirmed yet."""
        cfg = await _cfg()
        if not cfg.get("enabled", True):
            raise HTTPException(423, "QR top-up is temporarily disabled")
        try:
            parsed = parse_upi_uri(body.upi_uri)
        except ValueError as e:
            raise HTTPException(400, f"Invalid QR: {e}")

        vpa_check = _validate_vpa(parsed["pa"], cfg)
        is_mfb = bool(vpa_check["ok"])

        amt_raw = parsed.get("am") or ""
        parsed_amount: Optional[float] = None
        if amt_raw:
            try:
                parsed_amount = round(float(amt_raw), 2)
                if parsed_amount <= 0:
                    parsed_amount = None
            except ValueError:
                parsed_amount = None

        return {
            "is_mfb": is_mfb,
            "reason": vpa_check.get("reason"),
            "match_type": vpa_check.get("match_type"),
            "payee_vpa": parsed["pa"],
            "payee_name": parsed["pn"] or cfg.get("merchant_name"),
            "amount": parsed_amount,   # None if QR has no amount (static)
            "currency": parsed["cu"] or "INR",
            "note": parsed["tn"] or "",
            "merchant_code": parsed["mc"] or "",
            "supported_message": None if is_mfb else "This QR is not supported for Wallet Top-up.",
        }

    @api.post("/wallet/qr/initiate")
    async def user_initiate(
        body: InitiateQRIn,
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        user=Depends(get_current_user),
    ):
        cfg = await _cfg()
        if not cfg.get("enabled", True):
            raise HTTPException(423, "QR top-up is temporarily disabled")
        try:
            parsed = parse_upi_uri(body.upi_uri)
        except ValueError as e:
            raise HTTPException(400, f"Invalid QR: {e}")

        vpa_check = _validate_vpa(parsed["pa"], cfg)
        if not vpa_check["ok"]:
            raise HTTPException(422, "This QR is not supported for Wallet Top-up.")

        # Amount validation
        amt = round(float(body.amount), 2)
        min_amt = float(cfg.get("min_amount", 1.0))
        max_amt = float(cfg.get("max_amount", 200_000.0))
        if amt < min_amt:
            raise HTTPException(400, f"Minimum top-up is ₹{min_amt:.0f}")
        if amt > max_amt:
            raise HTTPException(400, f"Maximum top-up is ₹{max_amt:.0f}")

        # If the QR carries its own amount, enforce it matches (guard against tampering)
        qr_am = parsed.get("am") or ""
        if qr_am:
            try:
                qr_amount = round(float(qr_am), 2)
                if abs(qr_amount - amt) > 0.005:
                    raise HTTPException(400, f"Amount does not match the QR (₹{qr_amount:.2f})")
            except ValueError:
                pass  # ignore malformed amount → user-entered amount wins

        # Reuse the existing Razorpay engine to create the order (idempotency + audit)
        try:
            order, created_new = await payments_engine.create_order(
                user_id=user["user_id"],
                amount_paise=int(round(amt * 100)),
                currency="INR",
                idempotency_key=idempotency_key or f"qr_{secrets.token_hex(8)}",
                method_hint="upi",
                notes={
                    "source": "wallet_qr",
                    "qr_payee_vpa": parsed["pa"],
                    "qr_scheme": parsed["url_scheme"],
                    "qr_match_type": vpa_check.get("match_type"),
                },
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # payments provider error
            logger.warning("qr_initiate: order create failed: %s", e)
            raise HTTPException(502, f"Payment provider error: {e}")

        # Build the UPI intent URI (server-crafted for security)
        order_receipt = order.get("receipt") or order.get("provider_order_id") or order["order_id"]
        note = (cfg.get("note_template") or "MFB Wallet Top-up · {order_id}").format(
            order_id=order_receipt
        )
        intent_uri = build_upi_intent(
            payee_vpa=parsed["pa"],
            payee_name=cfg.get("merchant_name") or parsed["pn"] or "My Funding Bank",
            amount_rupees=amt,
            order_receipt=order_receipt,
            currency="INR",
            merchant_code=cfg.get("merchant_code"),
            note=note,
        )

        # Log
        await _log(user["user_id"], "wallet.qr.initiate",
                    target=order["order_id"],
                    meta={"amount": amt, "payee_vpa": parsed["pa"],
                          "match_type": vpa_check.get("match_type"),
                          "created_new": created_new})

        # Persist a "scan" trace so admin can audit QR usage
        await db.wallet_qr_scans.insert_one({
            "scan_id": f"qr_{secrets.token_hex(6)}",
            "user_id": user["user_id"],
            "order_id": order["order_id"],
            "payee_vpa": parsed["pa"],
            "payee_name": parsed["pn"] or cfg.get("merchant_name"),
            "amount": amt,
            "match_type": vpa_check.get("match_type"),
            "created_at": _now(),
        })

        pub_cfg = await payments_engine.public_config()
        return {
            "ok": True,
            "order": order,
            "intent_uri": intent_uri,
            "checkout": {
                "key_id": pub_cfg["key_id_public"],
                "provider_order_id": order["provider_order_id"],
                "amount_paise": order["amount_paise"],
                "currency": order["currency"],
                "receipt": order["receipt"],
                "demo": order.get("is_demo", False),
                "mode": pub_cfg["mode"],
            },
            "merchant": {
                "name": cfg.get("merchant_name"),
                "vpa": parsed["pa"],
            },
            "reason": None,
        }

    @api.get("/wallet/qr/status/{order_id}")
    async def user_status(order_id: str, user=Depends(get_current_user)):
        order = await payments_engine.get_order(order_id, user_id=user["user_id"])
        if not order:
            raise HTTPException(404, "Order not found")
        return {
            "order_id": order["order_id"],
            "status": order.get("status"),
            "amount_paise": order.get("amount_paise"),
            "captured_at": order.get("captured_at"),
            "provider_order_id": order.get("provider_order_id"),
            "receipt": order.get("receipt"),
            "wallet_credited": order.get("wallet_credited", False),
        }

    # =========================== ADMIN ROUTES ============================
    @api.get("/admin/wallet/qr/config")
    async def admin_get_config(adm=Depends(get_current_admin)):
        return await _cfg()

    @api.put("/admin/wallet/qr/config")
    async def admin_put_config(patch: ConfigPatch, adm=Depends(get_current_admin)):
        if adm.get("role") not in ("super_admin", "admin"):
            raise HTTPException(403, "Insufficient permissions")
        updates = {k: v for k, v in patch.dict(exclude_unset=True).items() if v is not None}
        if "allowed_vpas" in updates:
            bad = [v for v in updates["allowed_vpas"] if not _VPA_RE.match(v)]
            if bad:
                raise HTTPException(400, f"Invalid VPA format: {bad}")
            updates["allowed_vpas"] = list(dict.fromkeys([v.strip() for v in updates["allowed_vpas"]]))
        if not updates:
            raise HTTPException(400, "No changes")
        updates["updated_at"] = _now()
        updates["updated_by"] = adm["admin_id"]
        await db.wallet_qr_config.update_one(
            {"_id": "singleton"}, {"$set": updates}, upsert=True
        )
        await _log(adm["admin_id"], "wallet.qr.config_update", meta=updates)
        return {"ok": True, "config": await _cfg()}

    @api.get("/admin/wallet/qr/scans")
    async def admin_list_scans(limit: int = 50, skip: int = 0,
                                adm=Depends(get_current_admin)):
        cur = db.wallet_qr_scans.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        rows = await cur.to_list(limit)
        total = await db.wallet_qr_scans.count_documents({})
        return {"items": rows, "total": total}

    # =========================== attach ==================================
    app.include_router(api, prefix="/api", tags=["wallet-qr"])
    logger.info("wallet_qr attached")
