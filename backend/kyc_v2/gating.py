"""KYC gating helpers.

Defines the small set of actions that REQUIRE KYC. Everything else
(deposit, forex trade, copy trade, AI, gold, SIP, mutual funds) works
without KYC per Sprint 9 product decision.

Actions that require KYC:
  * withdrawal
  * become_signal_provider
  * become_copy_trader
  * exceeded_compliance_limits (aggregate check)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger("kyc_v2.gating")

GATED_ACTIONS = {
    "withdrawal": {
        "label": "Withdrawal",
        "reason": "RBI / SEBI KYC norms require verified identity for cash-out.",
    },
    "become_signal_provider": {
        "label": "Signal Provider Onboarding",
        "reason": "SEBI investment-adviser rules require KYC for anyone "
                  "publishing trade signals.",
    },
    "become_copy_trader": {
        "label": "Master Copy Trader",
        "reason": "Copy-trade leaders must complete KYC before earning fees.",
    },
    "compliance_limits": {
        "label": "High-value threshold",
        "reason": "You have crossed a compliance threshold. Complete KYC to "
                  "continue transacting above the limit.",
    },
}

# Aggregate compliance thresholds — hitting either triggers a KYC gate
COMPLIANCE_LIMITS = {
    "cumulative_deposit_paise": 5_00_000_00,  # ₹5 lakh lifetime cumulative deposits
    "single_transaction_paise": 1_00_000_00,  # ₹1 lakh single transaction
}


def is_kyc_gated_action(action: str) -> bool:
    return action in GATED_ACTIONS


async def kyc_status(db, user_id: str) -> str:
    """Return the current KYC status for the user. Reads legacy `users.kyc_status`
    if kyc_profiles doesn't have an entry yet."""
    prof = await db.kyc_profiles.find_one({"user_id": user_id}, {"status": 1, "_id": 0})
    if prof and prof.get("status"):
        return prof["status"]
    u = await db.users.find_one({"user_id": user_id}, {"kyc_status": 1, "_id": 0})
    return (u or {}).get("kyc_status") or "not_started"


async def evaluate_gate(db, user_id: str, action: str,
                        extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a structured gate result without raising."""
    if not is_kyc_gated_action(action):
        return {"required": False, "reason": None, "status": "not_gated",
                "action": action}
    st = await kyc_status(db, user_id)
    if st == "approved":
        return {"required": False, "reason": None, "status": st,
                "action": action}
    meta = GATED_ACTIONS[action]
    result = {
        "required": True,
        "reason": meta["reason"],
        "action": action, "action_label": meta["label"],
        "kyc_status": st,
        "unblock_hint": "Complete KYC in the app (Profile → KYC) to unlock this action.",
    }
    # Audit trail
    try:
        await db.kyc_gating_events.insert_one({
            "user_id": user_id, "action": action,
            "required": True, "status": st,
            "extra": extra or {}, "at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
    return result


async def require_kyc_for(db, user_id: str, action: str,
                           extra: Optional[Dict[str, Any]] = None):
    """Raise HTTPException 403 with structured detail if KYC is required."""
    result = await evaluate_gate(db, user_id, action, extra)
    if result.get("required"):
        raise HTTPException(403, detail={"kyc_required": True, **result})
    return result


async def compliance_report(db, user_id: str) -> Dict[str, Any]:
    """Aggregate transaction totals used for KYC-limit checks."""
    # 30-day + lifetime cumulative deposits from payments_transactions
    now = datetime.now(timezone.utc)
    since_30 = now - timedelta(days=30)
    pipeline_life = [
        {"$match": {"user_id": user_id, "status": {"$in": ["captured", "partially_refunded", "refunded"]}}},
        {"$group": {"_id": None, "sum": {"$sum": "$amount_paise"}, "count": {"$sum": 1}}}
    ]
    pipeline_30 = [
        {"$match": {"user_id": user_id, "status": {"$in": ["captured", "partially_refunded", "refunded"]},
                     "captured_at": {"$gte": since_30}}},
        {"$group": {"_id": None, "sum": {"$sum": "$amount_paise"}, "count": {"$sum": 1}}}
    ]
    life = await db.payments_transactions.aggregate(pipeline_life).to_list(1)
    d30 = await db.payments_transactions.aggregate(pipeline_30).to_list(1)
    max_single_pipeline = [
        {"$match": {"user_id": user_id, "status": {"$in": ["captured"]}}},
        {"$group": {"_id": None, "max": {"$max": "$amount_paise"}}}
    ]
    max_single = await db.payments_transactions.aggregate(max_single_pipeline).to_list(1)
    cum_life = (life[0]["sum"] if life else 0) or 0
    cum_30 = (d30[0]["sum"] if d30 else 0) or 0
    max_tx = (max_single[0]["max"] if max_single else 0) or 0
    over_cum = cum_life >= COMPLIANCE_LIMITS["cumulative_deposit_paise"]
    over_single = max_tx >= COMPLIANCE_LIMITS["single_transaction_paise"]
    return {
        "cumulative_deposit_paise": int(cum_life),
        "cumulative_deposit_30d_paise": int(cum_30),
        "largest_single_transaction_paise": int(max_tx),
        "cumulative_deposit_limit_paise": COMPLIANCE_LIMITS["cumulative_deposit_paise"],
        "single_transaction_limit_paise": COMPLIANCE_LIMITS["single_transaction_paise"],
        "over_cumulative_limit": over_cum,
        "over_single_txn_limit": over_single,
        "kyc_required_by_compliance": bool(over_cum or over_single),
    }
