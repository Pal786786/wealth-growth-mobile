"""Sprint 12.2 — Withdrawal payout provider abstraction.

Provides pluggable payout providers (currently Cashfree + Demo). Used by
withdrawal_module.py after admin/auto approval to actually push money to
the user's verified bank account.
"""
from .providers import (
    resolve_payout_provider,
    get_payout_provider,
    PayoutProviderBase,
    DemoPayoutProvider,
    CashfreePayoutProvider,
    REGISTRY,
)

__all__ = [
    "resolve_payout_provider",
    "get_payout_provider",
    "PayoutProviderBase",
    "DemoPayoutProvider",
    "CashfreePayoutProvider",
    "REGISTRY",
]
