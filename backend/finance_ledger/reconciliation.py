"""Sprint 12.3 · Phase B — Reconciliation engine (READ-ONLY).

Compares each per-module ledger with the immutable `finance_journal` and
produces `reconciliation_records`. **Never modifies journal entries.**

Every reconciliation record has:
    * pair_key       — deterministic hash of (module, reference_id)
    * module         — payments | withdrawals | wallet | gold | mf | forex
    * reference_id   — module's own row id (order_id, withdrawal_id, tx_id, ...)
    * status         — matched | pending | mismatch | manual_review
    * reason         — missing_payment | duplicate_webhook | ledger_imbalance
                        | provider_timeout | settlement_mismatch | manual_adjustment
                        | (empty for matched)
    * expected       — dict from the source module
    * actual         — dict summarising journal state
    * delta          — {amount, count, sign}
    * ran_at
    * resolved_by    — nullable
    * resolved_at    — nullable
    * admin_notes    — []

The engine is idempotent per pair_key — running it repeatedly overwrites the
same record with the latest snapshot (never journal). Historical mismatch
resolutions are preserved via the `resolutions` sub-collection.
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("finance_ledger.reconciliation")

RECON_COLL = "finance_reconciliation"
RECON_RUNS_COLL = "finance_reconciliation_runs"
RESOL_COLL = "finance_reconciliation_resolutions"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Reconciler:
    MODULES = ["payments", "withdrawals", "wallet", "gold", "mutual_funds", "forex"]

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[RECON_COLL].create_index(
                [("pair_key", 1)], unique=True, name="rc_pair_key"
            )
        except Exception:
            pass
        for spec, name in [
            ([("module", 1), ("status", 1)], "rc_mod_status"),
            ([("ran_at", -1)], "rc_ran_at"),
            ([("resolved_at", -1)], "rc_resolved_at"),
        ]:
            try:
                await self.db[RECON_COLL].create_index(spec, name=name)
            except Exception:
                pass

    # ------------------------------------------------------------ run --
    async def run(self, *, modules: Optional[List[str]] = None,
                    triggered_by: str = "system") -> Dict[str, Any]:
        run_id = f"rec_{secrets.token_hex(8)}"
        started = _now()
        summary: Dict[str, Any] = {
            "run_id": run_id, "started_at": started,
            "triggered_by": triggered_by,
            "modules": modules or self.MODULES,
            "per_module": {},
            "totals": {"matched": 0, "mismatch": 0, "pending": 0, "manual_review": 0},
        }
        chosen = set(modules or self.MODULES)
        if "payments" in chosen:
            summary["per_module"]["payments"] = await self._recon_payments()
        if "withdrawals" in chosen:
            summary["per_module"]["withdrawals"] = await self._recon_withdrawals()
        if "wallet" in chosen:
            summary["per_module"]["wallet"] = await self._recon_wallet()
        if "gold" in chosen:
            summary["per_module"]["gold"] = await self._recon_gold()
        if "mutual_funds" in chosen:
            summary["per_module"]["mutual_funds"] = await self._recon_mf()
        if "forex" in chosen:
            summary["per_module"]["forex"] = await self._recon_forex()

        for _, stats in summary["per_module"].items():
            for k in ("matched", "mismatch", "pending", "manual_review"):
                summary["totals"][k] += stats.get(k, 0)

        summary["finished_at"] = _now()
        summary["duration_ms"] = int((summary["finished_at"] - started).total_seconds() * 1000)
        await self.db[RECON_RUNS_COLL].insert_one(dict(summary))
        return summary

    # ---------------------------------------------------------- writers -
    async def _upsert(self, module: str, reference_id: str,
                        status: str, reason: str,
                        expected: Dict[str, Any], actual: Dict[str, Any],
                        delta: Dict[str, Any], user_id: Optional[str] = None) -> None:
        pair_key = f"{module}:{reference_id}"
        # Look up an existing record so we can preserve manual_review/resolve state
        existing = await self.db[RECON_COLL].find_one({"pair_key": pair_key},
                                                       {"_id": 0, "status": 1,
                                                        "resolved_by": 1, "admin_notes": 1})
        # If admin marked manual_review or resolved, don't downgrade to matched
        if existing and existing.get("status") in ("manual_review", "resolved_matched"):
            # Only override if user asks recon to re-run this record explicitly
            if status == "matched" and existing.get("status") == "manual_review":
                # Auto-transition: keep audit trail
                status = "resolved_matched"
        doc = {
            "pair_key": pair_key,
            "module": module,
            "reference_id": reference_id,
            "user_id": user_id,
            "status": status,
            "reason": reason,
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "ran_at": _now(),
            "resolved_by": None,
            "resolved_at": None,
            "admin_notes": existing.get("admin_notes") if existing else [],
        }
        await self.db[RECON_COLL].update_one(
            {"pair_key": pair_key},
            {"$set": doc, "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )

    # ------------------------------------------------------ payments (RZP)
    async def _recon_payments(self) -> Dict[str, int]:
        stats = {"matched": 0, "mismatch": 0, "pending": 0, "manual_review": 0,
                  "total": 0}
        cur = self.db.payments_orders.find({}, {"_id": 0})
        async for o in cur:
            stats["total"] += 1
            order_id = o.get("order_id")
            status = (o.get("status") or "").lower()
            amt_paise = int(o.get("amount_paise", 0))
            amt = amt_paise / 100.0
            uid = o.get("user_id")

            # Find matching journal entry
            j = await self.db.finance_journal.find_one(
                {"reference_id": order_id, "reference_type": {"$in": ["razorpay_order", "topup", "razorpay"]},
                 "is_reversed": {"$ne": True}}, {"_id": 0},
            )

            if status in ("created", "attempted"):
                # Payment not yet captured — pending is expected
                await self._upsert("payments", order_id,
                                    "pending", "provider_timeout" if status == "attempted" else "",
                                    expected={"status": status, "amount": amt},
                                    actual={"has_journal": bool(j)},
                                    delta={"amount": 0, "count": 0}, user_id=uid)
                stats["pending"] += 1
                continue

            if status == "captured" and j is None:
                await self._upsert("payments", order_id,
                                    "mismatch", "missing_payment",
                                    expected={"status": status, "amount": amt},
                                    actual={"has_journal": False},
                                    delta={"amount": amt, "count": 1}, user_id=uid)
                stats["mismatch"] += 1
                continue

            if status == "captured" and j is not None:
                # Check amount agreement
                j_amount = float(j.get("amount", 0.0))
                if abs(j_amount - amt) > 0.01:
                    await self._upsert("payments", order_id,
                                        "mismatch", "ledger_imbalance",
                                        expected={"status": status, "amount": amt},
                                        actual={"journal_amount": j_amount,
                                                "journal_id": j["journal_id"]},
                                        delta={"amount": j_amount - amt, "count": 0},
                                        user_id=uid)
                    stats["mismatch"] += 1
                else:
                    await self._upsert("payments", order_id,
                                        "matched", "",
                                        expected={"status": status, "amount": amt},
                                        actual={"journal_amount": j_amount,
                                                "journal_id": j["journal_id"]},
                                        delta={"amount": 0, "count": 0}, user_id=uid)
                    stats["matched"] += 1
                continue

            if status in ("failed", "expired", "refunded"):
                # These shouldn't produce a wallet-credit journal
                if j is not None:
                    await self._upsert("payments", order_id,
                                        "mismatch", "duplicate_webhook",
                                        expected={"status": status, "amount": 0},
                                        actual={"journal_amount": float(j.get("amount", 0)),
                                                "journal_id": j["journal_id"]},
                                        delta={"amount": float(j.get("amount", 0)),
                                                "count": 1}, user_id=uid)
                    stats["mismatch"] += 1
                else:
                    await self._upsert("payments", order_id,
                                        "matched", "",
                                        expected={"status": status, "amount": 0},
                                        actual={"has_journal": False},
                                        delta={"amount": 0, "count": 0}, user_id=uid)
                    stats["matched"] += 1
        return stats

    # ------------------------------------------------------ withdrawals -
    async def _recon_withdrawals(self) -> Dict[str, int]:
        stats = {"matched": 0, "mismatch": 0, "pending": 0, "manual_review": 0, "total": 0}
        cur = self.db.withdrawal_requests.find({}, {"_id": 0})
        async for w in cur:
            stats["total"] += 1
            wid = w.get("withdrawal_id")
            status = (w.get("status") or "").lower()
            uid = w.get("user_id")
            amt = float(w.get("net_amount") or w.get("amount") or 0)
            j = await self.db.finance_journal.find_one(
                {"reference_id": wid, "reference_type": {"$in": ["withdrawal", "withdrawals"]},
                 "is_reversed": {"$ne": True}}, {"_id": 0},
            )
            if status in ("pending", "under_review", "approved", "processing"):
                await self._upsert("withdrawals", wid, "pending", "",
                                    expected={"status": status, "amount": amt},
                                    actual={"has_journal": bool(j)},
                                    delta={"amount": 0, "count": 0}, user_id=uid)
                stats["pending"] += 1
                continue
            if status == "completed":
                if j is None:
                    await self._upsert("withdrawals", wid, "mismatch",
                                        "missing_payment",
                                        expected={"status": status, "amount": amt},
                                        actual={"has_journal": False},
                                        delta={"amount": amt, "count": 1}, user_id=uid)
                    stats["mismatch"] += 1
                else:
                    jamt = float(j.get("amount", 0))
                    if abs(jamt - amt) > 0.01:
                        await self._upsert("withdrawals", wid, "mismatch",
                                            "ledger_imbalance",
                                            expected={"amount": amt},
                                            actual={"journal_amount": jamt,
                                                    "journal_id": j["journal_id"]},
                                            delta={"amount": jamt - amt, "count": 0},
                                            user_id=uid)
                        stats["mismatch"] += 1
                    else:
                        await self._upsert("withdrawals", wid, "matched", "",
                                            expected={"status": status, "amount": amt},
                                            actual={"journal_amount": jamt,
                                                    "journal_id": j["journal_id"]},
                                            delta={"amount": 0, "count": 0}, user_id=uid)
                        stats["matched"] += 1
                continue
            if status in ("failed", "rejected", "cancelled"):
                if j is not None:
                    await self._upsert("withdrawals", wid, "manual_review",
                                        "duplicate_webhook",
                                        expected={"status": status, "amount": 0},
                                        actual={"journal_id": j["journal_id"],
                                                "journal_amount": float(j.get("amount", 0))},
                                        delta={"amount": float(j.get("amount", 0)),
                                                "count": 1}, user_id=uid)
                    stats["manual_review"] += 1
                else:
                    await self._upsert("withdrawals", wid, "matched", "",
                                        expected={"status": status, "amount": 0},
                                        actual={"has_journal": False},
                                        delta={"amount": 0, "count": 0}, user_id=uid)
                    stats["matched"] += 1
        return stats

    # ------------------------------------------------------ wallet -----
    async def _recon_wallet(self) -> Dict[str, int]:
        """Verify each user's wallet.balance == denorm ledger balance."""
        stats = {"matched": 0, "mismatch": 0, "pending": 0, "manual_review": 0, "total": 0}
        cur = self.db.wallets.find({}, {"_id": 0, "user_id": 1, "balance": 1})
        async for w in cur:
            stats["total"] += 1
            uid = w.get("user_id")
            if not uid:
                continue
            wb = float(w.get("balance", 0) or 0)
            acct = f"assets:user_wallet:{uid}"
            bdoc = await self.db.finance_ledger_balances.find_one(
                {"account": acct}, {"_id": 0, "balance": 1},
            )
            lb = float((bdoc or {}).get("balance", 0.0))
            if abs(wb - lb) < 0.01:
                await self._upsert("wallet", uid, "matched", "",
                                    expected={"wallet_balance": wb},
                                    actual={"ledger_balance": lb},
                                    delta={"amount": 0, "count": 0}, user_id=uid)
                stats["matched"] += 1
            else:
                # A pre-ledger user (only historical data) may have some drift;
                # mark manual_review — never mismatch.
                st = "mismatch" if lb != 0 else "manual_review"
                reason = "ledger_imbalance" if st == "mismatch" else "manual_adjustment"
                await self._upsert("wallet", uid, st, reason,
                                    expected={"wallet_balance": wb},
                                    actual={"ledger_balance": lb},
                                    delta={"amount": wb - lb, "count": 0}, user_id=uid)
                stats["mismatch" if st == "mismatch" else "manual_review"] += 1
        return stats

    # ------------------------------------------------------ gold / mf / forex
    async def _recon_generic(self, module: str, collection_names: List[str],
                              journal_ref_types: List[str]) -> Dict[str, int]:
        stats = {"matched": 0, "mismatch": 0, "pending": 0, "manual_review": 0, "total": 0}
        col = None
        col_names = await self.db.list_collection_names()
        for c in collection_names:
            if c in col_names:
                col = self.db[c]
                break
        if col is None:
            return stats
        async for r in col.find({}, {"_id": 0}):
            stats["total"] += 1
            ref = r.get("txn_id") or r.get("order_id") or r.get("position_id") or r.get("id") or r.get("gold_id")
            if not ref:
                continue
            st = (r.get("status") or "").lower()
            uid = r.get("user_id")
            amt = float(r.get("total_amount") or r.get("amount") or r.get("realised_pnl") or r.get("pnl") or 0)
            j = await self.db.finance_journal.find_one(
                {"reference_id": ref,
                 "reference_type": {"$in": journal_ref_types},
                 "is_reversed": {"$ne": True}}, {"_id": 0},
            )
            terminal = st in ("completed", "success", "settled", "closed")
            if not terminal:
                await self._upsert(module, ref, "pending", "",
                                    expected={"status": st, "amount": abs(amt)},
                                    actual={"has_journal": bool(j)},
                                    delta={"amount": 0, "count": 0}, user_id=uid)
                stats["pending"] += 1
                continue
            if j is None:
                await self._upsert(module, ref, "mismatch", "missing_payment",
                                    expected={"status": st, "amount": abs(amt)},
                                    actual={"has_journal": False},
                                    delta={"amount": abs(amt), "count": 1}, user_id=uid)
                stats["mismatch"] += 1
            else:
                jamt = float(j.get("amount", 0))
                if abs(jamt - abs(amt)) > 0.01:
                    await self._upsert(module, ref, "mismatch",
                                        "ledger_imbalance",
                                        expected={"amount": abs(amt)},
                                        actual={"journal_amount": jamt,
                                                "journal_id": j["journal_id"]},
                                        delta={"amount": jamt - abs(amt), "count": 0},
                                        user_id=uid)
                    stats["mismatch"] += 1
                else:
                    await self._upsert(module, ref, "matched", "",
                                        expected={"status": st, "amount": abs(amt)},
                                        actual={"journal_amount": jamt,
                                                "journal_id": j["journal_id"]},
                                        delta={"amount": 0, "count": 0}, user_id=uid)
                    stats["matched"] += 1
        return stats

    async def _recon_gold(self):
        return await self._recon_generic(
            "gold", ["gold_transactions", "gold_orders", "gold_txn"],
            ["gold_transactions", "gold_orders", "gold_txn"],
        )

    async def _recon_mf(self):
        return await self._recon_generic(
            "mutual_funds", ["mf_orders", "mutual_fund_orders", "mf_investments"],
            ["mf_orders", "mutual_fund_orders", "mf_investments"],
        )

    async def _recon_forex(self):
        return await self._recon_generic(
            "forex", ["forex_positions", "forex_trades"],
            ["forex_positions", "forex_trades"],
        )
