"""Sprint 12.3 · Phase A — Wire wallet_module → finance_journal.

Monkey-patches `wallet_module._post_ledger` so that every credit/debit
also produces a proper double-entry journal entry. Non-destructive: the
original wallet_ledger writes still happen.

Mapping (category → txn_type + counterparty CoA):
    topup / razorpay / deposit  → razorpay_deposit
    withdraw / bank             → cashfree_withdrawal
    gold_buy                    → gold_buy       (mapped from category='gold_buy')
    gold_sell                   → gold_sell
    mf_buy                      → mutual_fund_buy
    mf_redeem                   → mutual_fund_redeem
    forex_pnl / forex_close     → forex_pnl
    referral                    → referral_bonus
    cashback                    → cashback
    fee                         → fee
    tax                         → tax
    refund                      → wallet_credit (reversal-flavoured)
    admin_adjust                → admin_adjustment
    otherwise                   → wallet_credit | wallet_debit (fallback)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from .engine import (
    JournalLeg, post_journal,
    coa_user_wallet, coa_provider, coa_revenue_fees, coa_revenue_forex,
    coa_revenue_gold, coa_revenue_mf, coa_expense_referral,
    coa_equity_adjustment, coa_tax_gst, coa_platform_liability,
)

logger = logging.getLogger("finance_ledger.hooks")


# Maps low-level `_post_ledger` categories to Journal txn_types
_CATEGORY_TO_TXN: Dict[str, str] = {
    "topup": "razorpay_deposit",
    "deposit": "razorpay_deposit",
    "razorpay": "razorpay_deposit",
    "withdraw": "cashfree_withdrawal",
    "withdrawal": "cashfree_withdrawal",
    "bank": "cashfree_withdrawal",
    "gold_buy": "gold_buy",
    "gold_sell": "gold_sell",
    "mf_buy": "mutual_fund_buy",
    "mf_redeem": "mutual_fund_redeem",
    "forex_pnl": "forex_pnl",
    "forex_close": "forex_pnl",
    "referral": "referral_bonus",
    "referral_bonus": "referral_bonus",
    "cashback": "cashback",
    "fee": "fee",
    "tax": "tax",
    "refund": "wallet_credit",
    "admin_adjust": "admin_adjustment",
    "admin_adjustment": "admin_adjustment",
}


def _pick_txn_type(category: str, side_hint: str) -> str:
    if category in _CATEGORY_TO_TXN:
        return _CATEGORY_TO_TXN[category]
    return "wallet_credit" if side_hint == "credit" else "wallet_debit"


def _pick_counterparty(txn_type: str, provider: Optional[str]) -> str:
    """Return the CoA account that pairs with the user_wallet leg."""
    if txn_type == "razorpay_deposit":
        return coa_provider(provider or "razorpay")
    if txn_type == "cashfree_withdrawal":
        return coa_provider(provider or "cashfree")
    if txn_type == "gold_buy":
        return coa_provider("gold")
    if txn_type == "gold_sell":
        return coa_provider("gold")
    if txn_type == "mutual_fund_buy":
        return coa_provider("mutual_funds")
    if txn_type == "mutual_fund_redeem":
        return coa_provider("mutual_funds")
    if txn_type == "forex_pnl":
        return coa_revenue_forex()
    if txn_type == "referral_bonus":
        return coa_expense_referral()
    if txn_type == "cashback":
        return coa_expense_referral()
    if txn_type == "fee":
        return coa_revenue_fees()
    if txn_type == "tax":
        return coa_tax_gst()
    if txn_type == "admin_adjustment":
        return coa_equity_adjustment()
    return coa_platform_liability()


async def _emit_wallet_journal(
    *, side: str, user_id: str, amount: float, category: str,
    description: str, provider: Optional[str], reference_id: Optional[str],
    tx_id: str,
) -> None:
    """Produce a two-leg journal for a wallet movement.

    side = 'credit'  → CR user_wallet, DR counterparty
    side = 'debit'   → DR user_wallet, CR counterparty
    """
    txn_type = _pick_txn_type(category, side)
    counter = _pick_counterparty(txn_type, provider)
    user_acc = coa_user_wallet(user_id)
    if side == "credit":
        legs = [
            JournalLeg.make(counter,  amount, "DR"),
            JournalLeg.make(user_acc, amount, "CR"),
        ]
    else:
        legs = [
            JournalLeg.make(user_acc, amount, "DR"),
            JournalLeg.make(counter,  amount, "CR"),
        ]
    await post_journal(
        txn_type=txn_type, legs=legs, amount=amount,
        currency="INR", reference_id=reference_id, reference_type=category,
        user_id=user_id, narration=description,
        posted_by=f"module:wallet",
        metadata={"provider": provider, "tx_id": tx_id, "category": category,
                   "wallet_side": side},
        dedupe_key=f"wallet:{side}:{tx_id}",
    )


def install_wallet_hooks(wallet_module) -> bool:
    """Wrap wallet_module._post_ledger so every write ALSO posts a journal."""
    if not hasattr(wallet_module, "_post_ledger"):
        logger.warning("wallet_module has no _post_ledger — skipping hook")
        return False
    if getattr(wallet_module._post_ledger, "_fl_hooked", False):
        return True  # already hooked
    original = wallet_module._post_ledger

    async def wrapped(tx_id, user_id, amount, category,
                      debit_account, credit_account,
                      description, provider=None, reference_id=None):
        # Always run original first (keeps existing wallet_ledger flow)
        result = await original(tx_id, user_id, amount, category,
                                 debit_account, credit_account,
                                 description, provider, reference_id)
        # Determine side: if `credit_account` is the user wallet, it was a credit
        try:
            if credit_account.startswith("user:wallet:") and credit_account.endswith(user_id):
                side = "credit"
            elif debit_account.startswith("user:wallet:") and debit_account.endswith(user_id):
                side = "debit"
            else:
                # Not a wallet movement — skip journal
                return result
            await _emit_wallet_journal(
                side=side, user_id=user_id, amount=float(amount),
                category=category, description=description or "",
                provider=provider, reference_id=reference_id, tx_id=tx_id,
            )
        except Exception as e:
            logger.warning("wallet journal hook failed for tx=%s: %s", tx_id, e)
        return result

    wrapped._fl_hooked = True    # type: ignore[attr-defined]
    wallet_module._post_ledger = wrapped
    return True
