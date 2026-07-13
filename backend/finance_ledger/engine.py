"""Sprint 12.3 · Phase A — Journal engine (double-entry, immutable).

Design invariants:
  1. Every posting is BALANCED: sum(debits) == sum(credits) (assertion).
  2. Every posting is IMMUTABLE: the collection has NO update path.
  3. Reversals produce a NEW entry with negated legs, linked back via
     `reverses_journal_id`. The original is marked `is_reversed=True`
     (the only allowed metadata mutation — a single-shot flag).
  4. Idempotency: a caller may pass `dedupe_key` — repeats are no-ops.

The engine is deliberately DB-only (no HTTP). Callers are:
    * `finance_ledger/routes.py`  — HTTP surface
    * `finance_ledger/hooks.py`   — monkey-patched hooks into wallet/withdrawal/etc
    * `finance_ledger/backfill.py` — one-time migration
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("finance_ledger")

JOURNAL_COLL = "finance_journal"
BALANCE_COLL = "finance_ledger_balances"
AUDIT_COLL   = "finance_audit_trail"
MIGRATION_COLL = "finance_migrations"


# ---------------------------------------------------------------- constants
TXN_TYPES = {
    "wallet_credit",      # generic wallet credit (e.g. promo, admin credit)
    "wallet_debit",       # generic wallet debit
    "razorpay_deposit",   # user wallet ← Razorpay captured
    "cashfree_withdrawal", # user wallet → Cashfree payout
    "gold_buy",
    "gold_sell",
    "mutual_fund_buy",
    "mutual_fund_redeem",
    "forex_pnl",
    "referral_bonus",
    "cashback",
    "admin_adjustment",
    "reversal",
    "fee",
    "tax",
    "provider_charge",
}

COA_NODE_ROOTS = {
    "assets", "liab", "rev", "exp", "eq", "susp",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str = "jrn") -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


# ---------------------------------------------------------------- models
class JournalLeg(dict):
    """{account: str, amount: float, side: 'DR'|'CR'}"""

    @classmethod
    def make(cls, account: str, amount: float, side: str) -> "JournalLeg":
        if side not in ("DR", "CR"):
            raise ValueError(f"bad side: {side!r}")
        if amount is None or float(amount) <= 0:
            raise ValueError(f"leg amount must be > 0: {amount!r}")
        root = account.split(":", 1)[0]
        if root not in COA_NODE_ROOTS:
            raise ValueError(f"account {account!r} does not start with a valid CoA root")
        return cls(account=account, amount=round(float(amount), 4), side=side)


class JournalEntry(dict):
    """A balanced multi-leg journal entry."""

    @classmethod
    def make(
        cls, *,
        journal_id: Optional[str] = None,
        txn_type: str,
        legs: List[JournalLeg],
        amount: float,
        currency: str = "INR",
        reference_id: Optional[str] = None,
        reference_type: Optional[str] = None,
        user_id: Optional[str] = None,
        narration: str = "",
        posted_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        entry_date: Optional[datetime] = None,
        dedupe_key: Optional[str] = None,
        reverses_journal_id: Optional[str] = None,
    ) -> "JournalEntry":
        if txn_type not in TXN_TYPES:
            raise ValueError(f"unknown txn_type: {txn_type!r}")
        if not legs or len(legs) < 2:
            raise ValueError("journal needs ≥ 2 legs")
        dr = sum(l["amount"] for l in legs if l["side"] == "DR")
        cr = sum(l["amount"] for l in legs if l["side"] == "CR")
        if abs(dr - cr) > 0.005:
            raise ValueError(f"unbalanced journal: DR={dr} CR={cr}")
        return cls(
            journal_id=journal_id or _gen_id(),
            txn_type=txn_type,
            legs=legs,
            amount=round(float(amount or dr), 4),
            currency=currency.upper(),
            reference_id=reference_id,
            reference_type=reference_type,
            user_id=user_id,
            narration=narration or "",
            posted_by=posted_by,
            metadata=metadata or {},
            entry_date=entry_date or _now(),
            dedupe_key=dedupe_key,
            reverses_journal_id=reverses_journal_id,
            is_reversed=False,
            created_at=_now(),
        )


# ---------------------------------------------------------------- Journal API
class Journal:
    """Async wrapper around the finance_journal collection.

    Not a singleton; the module-level `post_journal(...)` uses the default
    instance bound at attach-time. Instantiate directly for tests / backfill.
    """
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        j = self.db[JOURNAL_COLL]
        # Unique dedupe_key when present (sparse so nulls don't collide)
        try:
            await j.create_index(
                [("dedupe_key", 1)], unique=True, sparse=True,
                name="fj_dedupe_key",
            )
        except Exception as e:
            logger.debug("dedupe index exists / %s", e)
        for spec, name in [
            ([("entry_date", -1)], "fj_entry_date"),
            ([("user_id", 1), ("entry_date", -1)], "fj_user_date"),
            ([("txn_type", 1), ("entry_date", -1)], "fj_type_date"),
            ([("reference_id", 1)], "fj_reference_id"),
            ([("reference_type", 1), ("reference_id", 1)], "fj_reftype_ref"),
            ([("is_reversed", 1)], "fj_is_reversed"),
        ]:
            try:
                await j.create_index(spec, name=name)
            except Exception:
                pass
        # Balances index
        try:
            await self.db[BALANCE_COLL].create_index([("account", 1)], unique=True, name="fb_account")
        except Exception:
            pass

    async def post(self, entry: JournalEntry) -> Dict[str, Any]:
        """Insert a balanced immutable entry, idempotent via `dedupe_key`.

        Returns the stored entry (or the existing one if deduped)."""
        dk = entry.get("dedupe_key")
        if dk:
            existing = await self.db[JOURNAL_COLL].find_one({"dedupe_key": dk}, {"_id": 0})
            if existing:
                logger.debug("journal dedupe hit: %s", dk)
                return existing
        try:
            await self.db[JOURNAL_COLL].insert_one(dict(entry))
        except Exception as e:
            # Handle unique-key race
            if "duplicate key" in str(e).lower() and dk:
                existing = await self.db[JOURNAL_COLL].find_one({"dedupe_key": dk}, {"_id": 0})
                if existing:
                    return existing
            raise
        await self._update_balances(entry["legs"])
        return dict(entry)

    async def reverse(self, journal_id: str, posted_by: str = "system",
                      narration: str = "") -> Dict[str, Any]:
        original = await self.db[JOURNAL_COLL].find_one({"journal_id": journal_id})
        if not original:
            raise ValueError("journal not found")
        if original.get("is_reversed"):
            raise ValueError("journal already reversed")
        flipped_legs = [
            JournalLeg.make(l["account"], l["amount"],
                             "CR" if l["side"] == "DR" else "DR")
            for l in original["legs"]
        ]
        rev = JournalEntry.make(
            txn_type="reversal",
            legs=flipped_legs,
            amount=original["amount"],
            currency=original.get("currency", "INR"),
            reference_id=original.get("reference_id"),
            reference_type=original.get("reference_type"),
            user_id=original.get("user_id"),
            narration=narration or f"Reversal of {journal_id}",
            posted_by=posted_by,
            metadata={"reverses_meta": original.get("metadata")},
            reverses_journal_id=journal_id,
            dedupe_key=f"reverse:{journal_id}",
        )
        stored = await self.post(rev)
        await self.db[JOURNAL_COLL].update_one(
            {"journal_id": journal_id, "is_reversed": {"$ne": True}},
            {"$set": {"is_reversed": True, "reversed_at": _now(),
                       "reversed_by": posted_by, "reversal_id": stored["journal_id"]}},
        )
        return stored

    async def _update_balances(self, legs: List[Dict[str, Any]]) -> None:
        """Denormalized running balance per account for fast reads.

        Convention: DR increases assets & expenses / decreases liab & revenue.
        We store the *signed* balance (positive for the account's natural
        side — assets/expenses positive on DR, liab/revenue/eq positive on CR).
        """
        for l in legs:
            acct = l["account"]
            amt = float(l["amount"])
            root = acct.split(":", 1)[0]
            sign = 0
            if l["side"] == "DR":
                sign = +1 if root in ("assets", "exp") else -1
            else:  # CR
                sign = +1 if root in ("liab", "rev", "eq", "susp") else -1
            await self.db[BALANCE_COLL].update_one(
                {"account": acct},
                {"$inc": {"balance": sign * amt},
                 "$set": {"updated_at": _now()},
                 "$setOnInsert": {"created_at": _now(),
                                    "coa_root": root}},
                upsert=True,
            )

    async def balance(self, account: str) -> float:
        doc = await self.db[BALANCE_COLL].find_one({"account": account}, {"_id": 0, "balance": 1})
        return float((doc or {}).get("balance") or 0.0)

    async def user_passbook(
        self, user_id: str, *, limit: int = 50, skip: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Passbook rows w/ running balance, opening / closing / totals."""
        wallet_acct = f"assets:user_wallet:{user_id}"

        q: Dict[str, Any] = {"legs.account": wallet_acct}
        if date_from or date_to:
            q["entry_date"] = {}
            if date_from:
                q["entry_date"]["$gte"] = date_from
            if date_to:
                q["entry_date"]["$lte"] = date_to
        cursor = self.db[JOURNAL_COLL].find(q, {"_id": 0}).sort("entry_date", 1)
        all_rows = await cursor.to_list(10_000)

        # Compute opening balance (sum of leg signs BEFORE first row of the window)
        opening = 0.0
        if date_from:
            pre_q = {"legs.account": wallet_acct, "entry_date": {"$lt": date_from}}
            pre_cur = self.db[JOURNAL_COLL].find(pre_q, {"_id": 0, "legs": 1})
            async for r in pre_cur:
                for l in r["legs"]:
                    if l["account"] == wallet_acct:
                        # assets increase on DR (user gains balance from provider's perspective)
                        # Actually: user_wallet is an ASSET on our books but a LIABILITY conceptually
                        # (money owed to user). For passbook UX we treat CR to user_wallet as a
                        # credit-to-user (top-up), DR as a debit-from-user (withdrawal/spend).
                        opening += l["amount"] if l["side"] == "CR" else -l["amount"]
        # (When no date_from is supplied we don't paginate the opening; the running balance is
        # calculated forward from the first entry.)

        rows: List[Dict[str, Any]] = []
        running = opening
        total_credit = 0.0
        total_debit = 0.0
        for r in all_rows:
            for l in r["legs"]:
                if l["account"] != wallet_acct:
                    continue
                is_credit = l["side"] == "CR"
                delta = l["amount"] if is_credit else -l["amount"]
                pre = running
                running = round(running + delta, 4)
                total_credit += l["amount"] if is_credit else 0.0
                total_debit  += l["amount"] if not is_credit else 0.0
                rows.append({
                    "journal_id": r["journal_id"],
                    "entry_date": r["entry_date"],
                    "txn_type": r["txn_type"],
                    "reference_id": r.get("reference_id"),
                    "reference_type": r.get("reference_type"),
                    "narration": r.get("narration"),
                    "utr": (r.get("metadata") or {}).get("utr"),
                    "status": (r.get("metadata") or {}).get("status") or "success",
                    "opening_balance": round(pre, 2),
                    "credit": round(l["amount"] if is_credit else 0.0, 2),
                    "debit":  round(l["amount"] if not is_credit else 0.0, 2),
                    "closing_balance": round(running, 2),
                    "is_reversed": bool(r.get("is_reversed")),
                })
        # Sort DESC for UI + paginate
        rows.sort(key=lambda x: x["entry_date"], reverse=True)
        paginated = rows[skip:skip + limit]
        return {
            "opening_balance": round(opening, 2),
            "closing_balance": round(running, 2),
            "total_credit": round(total_credit, 2),
            "total_debit": round(total_debit, 2),
            "total_rows": len(rows),
            "rows": paginated,
        }


# ---------------------------------------------------------------- module-level
_JOURNAL: Optional[Journal] = None


def set_default_journal(j: Journal) -> None:
    global _JOURNAL
    _JOURNAL = j


def get_default_journal() -> Optional[Journal]:
    return _JOURNAL


async def post_journal(**kwargs) -> Optional[Dict[str, Any]]:
    """Convenience module-level poster. Safe no-op if engine not attached.

    Kwargs match `JournalEntry.make()`. Callers must supply pre-built legs.
    """
    if _JOURNAL is None:
        logger.debug("post_journal called before attach; ignoring")
        return None
    try:
        entry = JournalEntry.make(**kwargs)
        return await _JOURNAL.post(entry)
    except Exception as e:
        logger.warning("post_journal failed (%s): %s", kwargs.get("txn_type"), e)
        return None


async def reverse_journal(journal_id: str, *, posted_by: str = "system",
                          narration: str = "") -> Optional[Dict[str, Any]]:
    if _JOURNAL is None:
        return None
    try:
        return await _JOURNAL.reverse(journal_id, posted_by=posted_by, narration=narration)
    except Exception as e:
        logger.warning("reverse_journal failed: %s", e)
        return None


async def account_balance(account: str) -> float:
    if _JOURNAL is None:
        return 0.0
    return await _JOURNAL.balance(account)


async def passbook(user_id: str, **kwargs) -> Dict[str, Any]:
    if _JOURNAL is None:
        return {"opening_balance": 0, "closing_balance": 0,
                "total_credit": 0, "total_debit": 0, "total_rows": 0, "rows": []}
    return await _JOURNAL.user_passbook(user_id, **kwargs)


# ---------------------------------------------------------------- CoA helpers
def coa_user_wallet(user_id: str) -> str: return f"assets:user_wallet:{user_id}"
def coa_provider(provider: str) -> str:   return f"assets:provider:{provider.lower()}"
def coa_bank_cash() -> str:                return "assets:cash:bank"
def coa_platform_liability() -> str:      return "liab:users_wallets"
def coa_revenue_fees() -> str:            return "rev:fees"
def coa_revenue_forex() -> str:           return "rev:forex"
def coa_revenue_gold() -> str:            return "rev:gold_spread"
def coa_revenue_mf() -> str:              return "rev:mf_commission"
def coa_expense_referral() -> str:        return "exp:referral"
def coa_expense_provider_charges() -> str: return "exp:provider_charges"
def coa_equity_adjustment() -> str:        return "eq:adjustments"
def coa_suspense_mismatch() -> str:        return "susp:mismatch"
def coa_tax_gst() -> str:                  return "liab:tax:gst"
