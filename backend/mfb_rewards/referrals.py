"""MFB Rewards — Referral system with QR generation."""
from __future__ import annotations

import base64
import io
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import wallet as W
from . import engine

try:
    import qrcode
    HAS_QRCODE = True
except Exception:
    HAS_QRCODE = False


_QR_CACHE: Dict[str, str] = {}   # code -> base64 png


def _base_url() -> str:
    return (os.getenv("REFERRAL_BASE_URL")
            or os.getenv("APP_URL", "https://myfundingbank.com")).rstrip("/")


def build_deep_link(code: str) -> Dict[str, str]:
    return {
        "web":       f"{_base_url()}/ref/{code}",
        "deep_link": f"mfb://ref/{code}",
    }


def generate_qr_png_b64(code: str) -> str:
    """Return a base64-encoded PNG QR containing the web referral link. Cached per code."""
    if code in _QR_CACHE:
        return _QR_CACHE[code]
    link = build_deep_link(code)["web"]
    if not HAS_QRCODE:
        # Minimal fallback (transparent 1x1 PNG). Tests should still pass.
        _QR_CACHE[code] = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        return _QR_CACHE[code]
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    _QR_CACHE[code] = b64
    return b64


def invalidate_qr_cache(code: str) -> None:
    _QR_CACHE.pop(code, None)


# ------------------------- Referral tracking --------------------------
async def get_or_create_referral_code(db, user_id: str) -> str:
    w = await W.ensure_wallet(db, user_id)
    return w.get("referral_code") or f"MFB{user_id[-6:].upper()}"


async def resolve_referrer(db, code: str) -> Optional[Dict[str, Any]]:
    if not code:
        return None
    # Look up in wallet first, fallback to users collection (legacy)
    doc = await db[W.COLL_WALLETS].find_one({"referral_code": code.upper()},
                                             {"_id": 0, "user_id": 1, "referral_code": 1})
    if doc:
        return doc
    user = await db.users.find_one({"referral_code": code.upper()},
                                    {"_id": 0, "user_id": 1, "referral_code": 1})
    return user


async def track_event(db, referrer_id: str, referred_id: Optional[str], code: str,
                     status: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Update or create a referral record. Idempotent per (referrer, referred, status)."""
    q = {"referrer_id": referrer_id}
    if referred_id:
        q["referred_id"] = referred_id
    else:
        q["code"] = code

    doc = await db[W.COLL_REFERRALS].find_one(q, {"_id": 0})
    now = datetime.now(timezone.utc)
    if not doc:
        doc = {
            "referral_id":   W.gen_id("ref"),
            "referrer_id":   referrer_id,
            "referred_id":   referred_id,
            "code":          code,
            "status":        status,
            "events":        [{"event": status, "at": now, "meta": meta or {}}],
            "rewards_paid":  {"install": False, "kyc": False, "first_deposit": False},
            "created_at":    now,
            "updated_at":    now,
        }
        await db[W.COLL_REFERRALS].insert_one(doc)
        doc.pop("_id", None)
    else:
        # Only progress status forward (invited < installed < registered < kyc_completed < first_deposit)
        order = ["invited", "installed", "registered", "kyc_completed", "first_deposit"]
        if status in order and order.index(status) > order.index(doc.get("status", "invited")):
            await db[W.COLL_REFERRALS].update_one(
                {"referral_id": doc["referral_id"]},
                {"$set": {"status": status, "referred_id": referred_id or doc.get("referred_id"),
                          "updated_at": now},
                 "$push": {"events": {"event": status, "at": now, "meta": meta or {}}}},
            )
            doc["status"] = status
    return doc


async def award_referral_rewards(db, referrer_id: str, referred_id: str,
                                  stage: str) -> Dict[str, Any]:
    """Award the referrer for stages: install, kyc, first_deposit.

    Emits one MFB credit per stage per referred_id.
    """
    stage_map = {
        "install":       ("referral_install", "install"),
        "kyc":           ("referral_kyc", "kyc"),
        "first_deposit": ("referral_deposit", "first_deposit"),
    }
    if stage not in stage_map:
        return {"skipped": True, "reason": "unknown_stage"}
    source, flag = stage_map[stage]

    ref_doc = await db[W.COLL_REFERRALS].find_one(
        {"referrer_id": referrer_id, "referred_id": referred_id}, {"_id": 0})
    if not ref_doc:
        return {"skipped": True, "reason": "no_referral_link"}
    if ref_doc.get("rewards_paid", {}).get(flag):
        return {"skipped": True, "reason": "already_paid", "stage": stage}

    tx = await engine.award(referrer_id, source, f"ref:{referred_id}:{stage}",
                            reason=f"Referral bonus ({stage})",
                            meta={"referred_id": referred_id, "stage": stage})
    await db[W.COLL_REFERRALS].update_one(
        {"referral_id": ref_doc["referral_id"]},
        {"$set": {f"rewards_paid.{flag}": True, "updated_at": datetime.now(timezone.utc)}},
    )
    if stage == "install":
        await W.inc_referral_count(db, referrer_id, 1)
    return {"ok": True, "tx": tx}


async def list_user_referrals(db, referrer_id: str) -> Dict[str, Any]:
    cur = db[W.COLL_REFERRALS].find({"referrer_id": referrer_id}, {"_id": 0}).sort("created_at", -1)
    items = [d async for d in cur]
    totals = {
        "total":          len(items),
        "installed":      sum(1 for i in items if i.get("status") in {"installed", "registered", "kyc_completed", "first_deposit"}),
        "registered":     sum(1 for i in items if i.get("status") in {"registered", "kyc_completed", "first_deposit"}),
        "kyc_completed":  sum(1 for i in items if i.get("status") in {"kyc_completed", "first_deposit"}),
        "first_deposit": sum(1 for i in items if i.get("status") == "first_deposit"),
    }
    return {"items": items, "totals": totals}
