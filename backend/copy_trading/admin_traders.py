"""Copy Trading — Admin trader management (Sprint 7B.3)

Provides:
  * Overlay system for the 28 seeded/system traders — admin edits are stored
    in `copy_trader_overlays` and merged at read time. Seeded traders remain
    deterministic when NOT edited.
  * Fully-persisted custom traders — created by admin, stored in
    `copy_custom_traders`. They participate in the same simulator and
    leaderboard as system traders.
  * Categories (system / verified / custom / disabled) + Approval Levels
    (verified / professional / elite / master).

Every read is async because overlays live in mongo. The public `traders.py`
module still ships the deterministic seeded personas untouched — this module
sits above it and produces the final "admin-visible" trader payload.
"""
from __future__ import annotations
import base64
import hashlib
import math
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import traders as tmod

# --- Constants ---
APPROVAL_LEVELS = ("verified", "professional", "elite", "master")
RISK_TIERS = ("Conservative", "Moderate", "Aggressive")
TRADING_STYLES = list({p["style"] for p in tmod._PERSONAS})
CATEGORIES = ("system", "verified", "custom", "disabled")

_OVERLAYS_COLL = "copy_trader_overlays"
_CUSTOM_COLL = "copy_custom_traders"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Overlay reads
# ---------------------------------------------------------------------------
async def _load_overlays(db) -> Dict[str, Dict[str, Any]]:
    cur = db[_OVERLAYS_COLL].find({}, {"_id": 0})
    out: Dict[str, Dict[str, Any]] = {}
    async for d in cur:
        out[d["trader_id"]] = d
    return out


def apply_overlay(trader: Dict[str, Any], overlay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge overlay onto a seeded trader dict (from traders.get_trader).

    Overlay may set: avatar_url, bio, verified, risk_tier (Conservative|
    Moderate|Aggressive), style, country_code, country_name, visible,
    disabled, approval_level.
    """
    if not overlay:
        # Ensure all admin-facing fields exist
        trader = dict(trader)
        trader.setdefault("visible", True)
        trader.setdefault("disabled", False)
        trader.setdefault("approval_level", "verified" if trader.get("verified") else None)
        trader.setdefault("kind", "system")
        return trader
    t = dict(trader)
    for k in ("avatar_url", "bio", "country_code", "country_name"):
        if overlay.get(k) is not None:
            t[k] = overlay[k]
    if overlay.get("style"):
        t["style"] = overlay["style"]
    if overlay.get("verified") is not None:
        t["verified"] = bool(overlay["verified"])
    if overlay.get("approval_level") in APPROVAL_LEVELS:
        t["approval_level"] = overlay["approval_level"]
    else:
        t.setdefault("approval_level", "verified" if t.get("verified") else None)
    if overlay.get("risk_tier") in RISK_TIERS and "risk" in t:
        t["risk"] = {**t["risk"], "risk_tier": overlay["risk_tier"]}
    t["visible"] = bool(overlay.get("visible", True))
    t["disabled"] = bool(overlay.get("disabled", False))
    t["kind"] = "system"
    t["_edited"] = True
    return t


# ---------------------------------------------------------------------------
# Custom trader synthesis
# ---------------------------------------------------------------------------
def _synth_seed(name: str) -> int:
    return int(hashlib.sha256(name.encode()).hexdigest(), 16) % (2 ** 31)


def _synth_stats(persona: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Reuse traders.py generators but with a custom persona dict."""
    monthly = tmod._generate_monthly_returns(persona, months=12)
    curve = tmod._generate_equity_curve(persona, months=12)
    stats = tmod._stats_from_truth(persona, curve, monthly)
    risk = tmod._risk_score(persona, stats)
    step = max(1, len(curve) // 120)
    light_curve = curve[::step]
    return {
        "stats": stats, "risk": risk,
        "monthly_returns_pct": [round(r * 100, 2) for r in monthly],
        "equity_curve": light_curve,
    }


DEFAULT_CUSTOM_TRUTH = {
    "win_rate": 0.55,
    "payoff_ratio": 1.6,
    "trades_per_month": 30,
    "avg_holding_hours": 8,
    "annual_vol_pct": 0.18,
    "annual_target_roi_pct": 0.5,
    "drawdown_cap_pct": 0.14,
    "avg_lot": 0.8,
}


async def create_custom_trader(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    style = payload.get("style") or "Day Trading"
    if style not in tmod._SYMBOLS_BY_STYLE:
        raise ValueError(f"invalid style; choose from {sorted(tmod._SYMBOLS_BY_STYLE.keys())}")
    country_code = (payload.get("country_code") or "US").upper()
    country_name = payload.get("country_name") or country_code
    bio = payload.get("bio") or ""
    experience_years = int(payload.get("experience_years", 3))
    verified = bool(payload.get("verified", False))
    approval_level = payload.get("approval_level") if payload.get("approval_level") in APPROVAL_LEVELS else ("verified" if verified else "verified")
    truth = {**DEFAULT_CUSTOM_TRUTH, **(payload.get("truth") or {})}
    # Slot the truth values sanely
    truth["win_rate"] = max(0.2, min(0.9, float(truth["win_rate"])))
    truth["payoff_ratio"] = max(0.5, min(4.0, float(truth["payoff_ratio"])))
    truth["annual_target_roi_pct"] = max(-0.5, min(1.5, float(truth["annual_target_roi_pct"])))
    truth["drawdown_cap_pct"] = max(0.03, min(0.4, float(truth["drawdown_cap_pct"])))

    tid = payload.get("id") or f"custom_{uuid.uuid4().hex[:10]}"
    seed = _synth_seed(tid)
    avatar_url = payload.get("avatar_url") or f"https://api.dicebear.com/7.x/avataaars/svg?seed={seed}"

    persona = {
        "id": tid, "name": name, "country_code": country_code, "country_name": country_name,
        "style": style, "experience_years": experience_years, "bio": bio,
        "seed": seed, "verified": verified, "truth": truth,
    }
    doc = {
        "trader_id": tid, "persona": persona,
        "avatar_url": avatar_url,
        "approval_level": approval_level,
        "visible": True, "disabled": False,
        "kind": "custom",
        "created_at": _now(), "updated_at": _now(),
    }
    await db[_CUSTOM_COLL].insert_one(doc)
    return await get_custom_trader(db, tid, include_curve=False)  # type: ignore[return-value]


async def update_custom_trader(db, trader_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    doc = await db[_CUSTOM_COLL].find_one({"trader_id": trader_id})
    if not doc:
        return None
    p = doc["persona"]
    changed_truth = False
    if patch.get("name"):
        p["name"] = patch["name"]
    if patch.get("bio") is not None:
        p["bio"] = patch["bio"]
    if patch.get("country_code"):
        p["country_code"] = patch["country_code"].upper()
    if patch.get("country_name"):
        p["country_name"] = patch["country_name"]
    if patch.get("style") and patch["style"] in tmod._SYMBOLS_BY_STYLE:
        p["style"] = patch["style"]
    if patch.get("experience_years") is not None:
        p["experience_years"] = int(patch["experience_years"])
    if patch.get("verified") is not None:
        p["verified"] = bool(patch["verified"])
    if isinstance(patch.get("truth"), dict):
        p["truth"] = {**p["truth"], **patch["truth"]}
        changed_truth = True
    set_ops: Dict[str, Any] = {"persona": p, "updated_at": _now()}
    if patch.get("avatar_url"):
        set_ops["avatar_url"] = patch["avatar_url"]
    if patch.get("approval_level") in APPROVAL_LEVELS:
        set_ops["approval_level"] = patch["approval_level"]
    if patch.get("visible") is not None:
        set_ops["visible"] = bool(patch["visible"])
    if patch.get("disabled") is not None:
        set_ops["disabled"] = bool(patch["disabled"])
    if changed_truth:
        # Force recompute on next read
        set_ops["_stats_dirty"] = True
    await db[_CUSTOM_COLL].update_one({"trader_id": trader_id}, {"$set": set_ops})
    return await get_custom_trader(db, trader_id, include_curve=False)


async def delete_custom_trader(db, trader_id: str) -> bool:
    res = await db[_CUSTOM_COLL].delete_one({"trader_id": trader_id})
    # Also delete relationships & stats
    await db.copy_relationships.delete_many({"trader_id": trader_id})
    return res.deleted_count > 0


async def get_custom_trader(db, trader_id: str, include_curve: bool = False) -> Optional[Dict[str, Any]]:
    doc = await db[_CUSTOM_COLL].find_one({"trader_id": trader_id}, {"_id": 0})
    if not doc:
        return None
    persona = doc["persona"]
    calc = _synth_stats(persona, persona["seed"])
    created_at = doc.get("created_at") or _now()
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    joined = int((_now() - created_at).total_seconds() / 86400)
    out = {
        "id": persona["id"], "name": persona["name"],
        "country_code": persona["country_code"], "country_name": persona["country_name"],
        "style": persona["style"], "experience_years": persona["experience_years"],
        "bio": persona["bio"], "verified": persona["verified"],
        "avatar_url": doc.get("avatar_url"),
        "joined_days_ago": max(1, joined),
        "stats": calc["stats"], "risk": calc["risk"],
        "monthly_returns_pct": calc["monthly_returns_pct"],
        "approval_level": doc.get("approval_level", "verified"),
        "visible": doc.get("visible", True),
        "disabled": doc.get("disabled", False),
        "kind": "custom",
    }
    if include_curve:
        out["equity_curve"] = calc["equity_curve"]
    return out


async def list_custom_traders(db, include_hidden: bool = False,
                              include_disabled: bool = False) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if not include_hidden:
        q["visible"] = {"$ne": False}
    if not include_disabled:
        q["disabled"] = {"$ne": True}
    cur = db[_CUSTOM_COLL].find(q, {"_id": 0})
    out: List[Dict[str, Any]] = []
    async for doc in cur:
        t = await get_custom_trader(db, doc["trader_id"])
        if t:
            out.append(t)
    return out


async def list_custom_trader_ids(db) -> List[str]:
    cur = db[_CUSTOM_COLL].find({}, {"_id": 0, "trader_id": 1})
    return [d["trader_id"] async for d in cur]


# ---------------------------------------------------------------------------
# Overlay writes
# ---------------------------------------------------------------------------
async def upsert_overlay(db, trader_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Insert/update overlay for a SYSTEM trader (validates it exists in _PERSONAS)."""
    if not tmod._persona_by_id(trader_id):
        raise ValueError(f"unknown system trader {trader_id}")
    clean = {"trader_id": trader_id, "updated_at": _now()}
    for k in ("avatar_url", "bio", "country_code", "country_name"):
        if patch.get(k) is not None:
            clean[k] = str(patch[k])
    if patch.get("style") in tmod._SYMBOLS_BY_STYLE:
        clean["style"] = patch["style"]
    if patch.get("verified") is not None:
        clean["verified"] = bool(patch["verified"])
    if patch.get("risk_tier") in RISK_TIERS:
        clean["risk_tier"] = patch["risk_tier"]
    if patch.get("approval_level") in APPROVAL_LEVELS:
        clean["approval_level"] = patch["approval_level"]
    if patch.get("visible") is not None:
        clean["visible"] = bool(patch["visible"])
    if patch.get("disabled") is not None:
        clean["disabled"] = bool(patch["disabled"])
    await db[_OVERLAYS_COLL].update_one(
        {"trader_id": trader_id}, {"$set": clean}, upsert=True,
    )
    return clean


async def reset_overlay(db, trader_id: str) -> bool:
    res = await db[_OVERLAYS_COLL].delete_one({"trader_id": trader_id})
    return res.deleted_count > 0


# ---------------------------------------------------------------------------
# Combined enumeration (used by admin + public leaderboard)
# ---------------------------------------------------------------------------
async def all_traders(db, include_disabled: bool = False,
                      include_hidden: bool = False) -> List[Dict[str, Any]]:
    overlays = await _load_overlays(db)
    seeded = [apply_overlay(tmod.get_trader(pid), overlays.get(pid)) for pid in tmod.list_trader_ids()]
    if not include_disabled:
        seeded = [t for t in seeded if not t.get("disabled")]
    if not include_hidden:
        seeded = [t for t in seeded if t.get("visible", True)]
    custom = await list_custom_traders(db, include_hidden=include_hidden,
                                       include_disabled=include_disabled)
    return seeded + custom


async def get_trader(db, trader_id: str, include_curve: bool = False,
                     include_hidden: bool = True,
                     include_disabled: bool = True) -> Optional[Dict[str, Any]]:
    """Unified lookup — seeded (with overlay) OR custom."""
    if tmod._persona_by_id(trader_id):
        base = tmod.get_trader(trader_id, include_curve=include_curve)
        overlays = await _load_overlays(db)
        return apply_overlay(base, overlays.get(trader_id)) if base else None
    return await get_custom_trader(db, trader_id, include_curve=include_curve)


async def all_trader_ids(db) -> List[str]:
    """IDs of every trader (seeded + custom, incl. hidden/disabled). Used by simulator."""
    ids = list(tmod.list_trader_ids())
    ids += await list_custom_trader_ids(db)
    return ids


async def is_trader_active_for_sim(db, trader_id: str) -> bool:
    """Returns True if the simulator should trade on this trader (not disabled)."""
    if tmod._persona_by_id(trader_id):
        overlays = await _load_overlays(db)
        ov = overlays.get(trader_id) or {}
        return not bool(ov.get("disabled"))
    doc = await db[_CUSTOM_COLL].find_one({"trader_id": trader_id}, {"_id": 0, "disabled": 1})
    return bool(doc and not doc.get("disabled"))


def truth_of(persona_or_custom: Dict[str, Any]) -> Dict[str, Any]:
    """Get the `truth` dict for either a seeded persona or a custom trader doc."""
    if "truth" in persona_or_custom:
        return persona_or_custom["truth"]
    p = persona_or_custom.get("persona") or {}
    return p.get("truth") or DEFAULT_CUSTOM_TRUTH
