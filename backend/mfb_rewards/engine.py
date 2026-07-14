"""MFB Rewards — Reward Engine (single entry point).

Exposes::

    await engine.award(user_id, source, reference_id, *, amount=None,
                       amount_inr=None, meta=None)
    await engine.notify_event(event_type, user_id, ...)   # thin wrapper for hooks
    await engine.record_daily_login(user_id)
    await engine.check_achievements(user_id)

All functions are idempotent by (source, reference_id, user_id).
The module refuses to double-award or over-spend.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from . import wallet as W
from . import achievements


@dataclass
class Context:
    db: Any = None
    logger: Any = None
    subscribers: List[Callable[[Dict[str, Any]], Awaitable[None]]] = field(default_factory=list)


_CTX: Optional[Context] = None


def set_context(ctx: Context) -> None:
    global _CTX
    _CTX = ctx


def get_context() -> Context:
    if _CTX is None:
        raise RuntimeError("mfb_rewards.engine.Context not initialised (call attach() first)")
    return _CTX


# ---------------------------- Helpers -----------------------------------
def _compute_amount(rate: Dict[str, Any], amount_inr: Optional[float]) -> int:
    unit = rate.get("unit", "flat")
    if unit == "flat":
        return int(rate.get("amount", 0))
    if unit == "per_100":
        if not amount_inr or amount_inr <= 0:
            return 0
        per = float(rate.get("amount", 0))
        return max(0, int((float(amount_inr) / 100.0) * per))
    if unit == "vector":
        return 0   # streak curve consumed elsewhere
    return int(rate.get("amount", 0))


async def _flag_enabled(db, key: str = "flag.enabled") -> bool:
    doc = await W.get_setting(db, key)
    if not doc:
        return True
    return bool(doc.get("value", {}).get("value", True))


# ---------------------------- Core: award -------------------------------
async def award(user_id: str, source: str, reference_id: Optional[str] = None,
                *, amount: Optional[int] = None, amount_inr: Optional[float] = None,
                reason: Optional[str] = None, meta: Optional[Dict[str, Any]] = None,
                allow_reward_zero: bool = False) -> Dict[str, Any]:
    """Idempotently award MFB tokens.

    - `amount`      : explicit MFB to grant (bypasses rate lookup)
    - `amount_inr`  : underlying INR event value (for per-₹100 rules)
    - `reference_id`: makes the award idempotent per (source, reference_id, user_id)
    Returns the created transaction dict, or {"skipped": True, ...} if duplicate.
    """
    ctx = get_context()
    db = ctx.db
    if not user_id:
        return {"skipped": True, "reason": "no_user_id"}

    if not await _flag_enabled(db):
        return {"skipped": True, "reason": "engine_disabled"}

    # Idempotency
    if reference_id:
        if await W.already_awarded(db, user_id, source, reference_id):
            return {"skipped": True, "reason": "duplicate", "source": source,
                    "reference_id": reference_id}

    # Resolve amount from settings if not given
    if amount is None:
        rate = await W.get_rate(db, f"rate.{source}")
        if not rate and source.startswith("achievement."):
            rate = await W.get_rate(db, source)
        amount = _compute_amount(rate or {}, amount_inr)

    amount = int(amount or 0)
    if amount <= 0 and not allow_reward_zero:
        return {"skipped": True, "reason": "zero_amount", "source": source}

    await W.ensure_wallet(db, user_id)
    updated = await W.apply_delta(db, user_id, delta=amount, xp_delta=amount if amount > 0 else 0)
    tx = await W.record_tx(
        db,
        user_id=user_id,
        amount=amount,
        source=source,
        reference_id=reference_id,
        reason=reason or f"Reward for {source}",
        tx_type="credit",
        balance_after=updated.get("balance", 0),
        meta=meta,
    )

    # Fire subscribers (achievements etc.)
    for sub in ctx.subscribers:
        try:
            await sub({"user_id": user_id, "source": source, "amount": amount, "tx": tx})
        except Exception as e:                    # pragma: no cover
            if ctx.logger:
                ctx.logger.warning("reward subscriber failed: %s", e)

    # Auto-run achievements evaluator (best-effort, non-blocking)
    try:
        await achievements.evaluate(db, user_id)
    except Exception as e:                        # pragma: no cover
        if ctx.logger:
            ctx.logger.warning("achievement eval failed for %s: %s", user_id, e)

    return tx


async def debit(user_id: str, amount: int, *, source: str = "spend",
                reference_id: Optional[str] = None, reason: str = "Spend",
                meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Spend MFB tokens (never touches XP). Raises ValueError on insufficient balance."""
    ctx = get_context()
    db = ctx.db
    w = await W.ensure_wallet(db, user_id)
    if w.get("balance", 0) < amount:
        raise ValueError("insufficient_mfb_balance")
    updated = await W.apply_delta(db, user_id, delta=-amount, xp_delta=0)
    tx = await W.record_tx(db, user_id=user_id, amount=-int(amount), source=source,
                             reference_id=reference_id, reason=reason,
                             tx_type="debit", balance_after=updated.get("balance", 0), meta=meta)
    return tx


async def reverse(user_id: str, tx_id: str, reason: str = "admin_reversal") -> Dict[str, Any]:
    """Admin-only: reverse a previous credit (creates a compensating debit)."""
    ctx = get_context()
    tx = await ctx.db[W.COLL_TX].find_one({"tx_id": tx_id, "user_id": user_id}, {"_id": 0})
    if not tx:
        raise ValueError("tx_not_found")
    if tx.get("status") == "reversed":
        return {"skipped": True, "reason": "already_reversed"}
    amt = int(tx.get("amount", 0))
    if amt <= 0:
        raise ValueError("only_credits_can_be_reversed")
    updated = await W.apply_delta(ctx.db, user_id, delta=-amt, xp_delta=0)
    rev = await W.record_tx(ctx.db, user_id=user_id, amount=-amt, source="reversal",
                              reference_id=tx_id, reason=reason, tx_type="reversal",
                              balance_after=updated.get("balance", 0),
                              meta={"original_tx": tx_id})
    await ctx.db[W.COLL_TX].update_one({"tx_id": tx_id}, {"$set": {"status": "reversed"}})
    return rev


# ---------------------------- Daily login streak -------------------------
async def record_daily_login(user_id: str) -> Dict[str, Any]:
    """Grant daily-login reward. Returns dict with streak/day/amount.

    Missed day resets the streak. Rewards are per-calendar-day (UTC).
    Idempotent within a single UTC day.
    """
    ctx = get_context()
    db = ctx.db
    if not user_id:
        return {"skipped": True, "reason": "no_user"}

    if not await _flag_enabled(db) or not await _flag_enabled(db, "flag.streak_enabled"):
        return {"skipped": True, "reason": "streak_disabled"}

    w = await W.ensure_wallet(db, user_id)
    today = datetime.now(timezone.utc).date()
    last = w.get("streak_last_date")
    last_date = None
    if isinstance(last, datetime):
        last_date = last.date()
    elif isinstance(last, str):
        try:
            last_date = date.fromisoformat(last[:10])
        except Exception:
            last_date = None

    if last_date == today:
        return {"skipped": True, "reason": "already_awarded_today",
                "streak": w.get("streak_current", 0)}

    # Compute new streak
    if last_date == today - timedelta(days=1):
        streak = int(w.get("streak_current", 0)) + 1
    else:
        streak = 1

    # Cap at 7 for reward curve, but streak counter can climb
    curve = (await W.get_rate(db, "streak.curve")).get("amount", [20, 30, 40, 70, 110, 170, 250])
    day_idx = min(streak, len(curve)) - 1
    day_idx = max(0, day_idx)
    reward = int(curve[day_idx])

    # Update wallet snapshot
    await db[W.COLL_WALLETS].update_one(
        {"user_id": user_id},
        {"$set": {
            "streak_current":    streak,
            "streak_best":       max(streak, int(w.get("streak_best", 0))),
            "streak_last_date": datetime.now(timezone.utc),
            "updated_at":        datetime.now(timezone.utc),
        }},
    )

    # Record daily reward entry (idempotent per (user, date))
    date_key = today.isoformat()
    try:
        await db[W.COLL_DAILY_REWARDS].insert_one({
            "user_id": user_id,
            "date":    date_key,
            "day_in_streak": streak,
            "amount":  reward,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        if "E11000" in str(e):
            return {"skipped": True, "reason": "already_awarded_today", "streak": streak}
        raise

    tx = await award(user_id, "daily_login", f"daily:{date_key}",
                     amount=reward, reason=f"Daily login streak day {streak}",
                     meta={"streak": streak, "date": date_key})
    return {"ok": True, "streak": streak, "day": streak, "amount": reward, "tx": tx}


# ---------------------------- Event hook wrapper -------------------------
EVENT_MAP = {
    "signup":              ("signup",             False),
    "kyc_approved":        ("kyc_complete",       False),
    "wallet_topup":        ("wallet_topup",       True),
    "gold_buy":            ("gold_buy",           True),
    "mf_invest":            ("mf_invest",          True),
    "sip_success":          ("sip_success",        False),
    "forex_trade":          ("forex_trade",        True),
    "referral_install":     ("referral_install",   False),
    "referral_kyc":         ("referral_kyc",       False),
    "referral_deposit":     ("referral_deposit",   False),
    "trading_milestone":    ("trading_milestone",  False),
}


async def notify_event(event_type: str, user_id: str, *,
                       reference_id: Optional[str] = None,
                       amount_inr: Optional[float] = None,
                       meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Guarded, one-line-usable hook for existing modules.

    Existing business logic can call this without knowing anything about the
    rewards internals. Errors are swallowed (returns {'error': ...}).
    """
    if _CTX is None:
        return {"skipped": True, "reason": "engine_not_ready"}
    src_conf = EVENT_MAP.get(event_type)
    if not src_conf:
        return {"skipped": True, "reason": f"unknown_event:{event_type}"}
    source, wants_inr = src_conf
    try:
        return await award(user_id, source, reference_id,
                           amount_inr=amount_inr if wants_inr else None,
                           meta=meta)
    except Exception as e:                        # pragma: no cover
        return {"error": str(e)[:200]}


# ---------------------------- Query helpers ------------------------------
async def list_transactions(db, user_id: str, *, limit: int = 50, skip: int = 0,
                            source: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"user_id": user_id}
    if source:
        q["source"] = source
    cur = db[W.COLL_TX].find(q, {"_id": 0}).sort("created_at", -1).skip(int(skip)).limit(int(limit))
    return [d async for d in cur]
