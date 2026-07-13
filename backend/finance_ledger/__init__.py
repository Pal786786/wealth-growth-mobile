"""Sprint 12.3 · Phase A — Finance Ledger (double-entry, immutable journal).

Layers a **proper Chart-of-Accounts double-entry journal** on top of the
existing per-module ledgers (wallet_ledger, payments_orders, withdrawal_requests,
gold_transactions, mf_orders, forex_positions). Nothing pre-existing is
removed — the journal is a super-set aggregating all finance events.

Key exports:
    post_journal(...)      — write one balanced journal entry (immutable)
    reverse_journal(...)   — write a reverse entry (does NOT delete the original)
    account_balance(coa)   — computed balance for a Chart-of-Accounts leaf
    passbook(user_id, ...) — projected user passbook w/ running balance

Chart of Accounts (CoA):
    Assets:
        assets:user_wallet:<user_id>            — user's on-platform wallet holding
        assets:provider:razorpay                — cash held with Razorpay
        assets:provider:cashfree                — cash held with Cashfree (payouts)
        assets:provider:gold                    — custodian gold reserves
        assets:provider:mutual_funds            — cash pending AMC/RTA settlement
        assets:cash:bank                        — MFB bank account (settled cash)
    Liabilities:
        liab:users_wallets                      — aggregate liability to all users
        liab:tax:gst                            — GST payable
    Revenue:
        rev:fees                                — transaction fees
        rev:forex                               — realised forex PnL (net gains)
        rev:gold_spread                         — gold bid-ask
        rev:mf_commission                       — mutual fund trail commission
        rev:referral                            — referral bonus given (contra)
    Expenses:
        exp:provider_charges                    — payment gateway fees
        exp:promo_waivers                       — waivers granted
    Equity / Suspense:
        eq:adjustments                          — admin manual adjustments
        susp:mismatch                           — reconciliation suspense
"""
from .engine import (
    Journal,
    post_journal, reverse_journal,
    account_balance, passbook,
    JournalEntry, JournalLeg,
    TXN_TYPES, COA_NODE_ROOTS,
    JOURNAL_COLL, BALANCE_COLL, AUDIT_COLL,
)
from .routes import attach

__all__ = [
    "Journal", "post_journal", "reverse_journal",
    "account_balance", "passbook",
    "JournalEntry", "JournalLeg", "TXN_TYPES", "COA_NODE_ROOTS",
    "JOURNAL_COLL", "BALANCE_COLL", "AUDIT_COLL",
    "attach",
]
