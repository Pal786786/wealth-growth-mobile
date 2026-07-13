"""Sprint 12.3 · Phase A — One-time idempotent ledger backfill.

Scans every historical finance-touching collection and produces journal
entries for events that don't already have one (checked via `dedupe_key`
uniqueness constraint on `finance_journal`).

Supports `dry_run=True` — reports what would be migrated without writing.

Sources scanned:
    * wallet_ledger              → wallet credits / debits
    * transactions                → top-level transaction rows (fallback for anything not in wallet_ledger)
    * payments_orders             → Razorpay captures
    * withdrawal_requests         → Cashfree payouts (completed only)
    * gold_transactions           → gold buy/sell (module: gold)
    * mf_orders                    → mutual fund buy/redeem
    * forex_positions             → forex close P&L
    * users referral_bonuses / users cashback events  (if collection exists)

Every entry is deduped by `dedupe_key = "backfill:<source>:<row_id>"`.
"""
from __future__ import annotations
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request

from .engine import (
    Journal, JournalLeg, JournalEntry, set_default_journal, get_default_journal,
    coa_user_wallet, coa_provider, coa_revenue_fees, coa_revenue_forex,
    coa_platform_liability, coa_equity_adjustment, coa_expense_referral,
    MIGRATION_COLL,
)

logger = logging.getLogger("finance_ledger.backfill")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rid() -> str:
    return f"mig_{secrets.token_hex(8)}"


class Backfiller:
    MODULES = ["wallet_ledger", "payments", "withdrawals",
                "gold", "mutual_funds", "forex", "referrals"]

    def __init__(self, db, journal: Optional[Journal] = None):
        self.db = db
        self.journal = journal or get_default_journal() or Journal(db)

    async def run(self, *, dry_run: bool = True, modules: Optional[List[str]] = None,
                    triggered_by: str = "system", request: Optional[Request] = None) -> Dict[str, Any]:
        run_id = _rid()
        started = time.time()
        run_doc: Dict[str, Any] = {
            "run_id": run_id,
            "dry_run": dry_run,
            "triggered_by": triggered_by,
            "modules": modules or self.MODULES,
            "status": "running",
            "started_at": _now(),
            "created_at": _now(),
            "processed": 0, "migrated": 0, "skipped": 0, "failed": 0,
            "per_module": {},
            "errors_sample": [],
        }
        await self.db[MIGRATION_COLL].insert_one(dict(run_doc))

        chosen = set(modules or self.MODULES)
        try:
            if "wallet_ledger" in chosen: await self._do_wallet(run_doc, dry_run)
            if "payments" in chosen:      await self._do_payments(run_doc, dry_run)
            if "withdrawals" in chosen:    await self._do_withdrawals(run_doc, dry_run)
            if "gold" in chosen:           await self._do_gold(run_doc, dry_run)
            if "mutual_funds" in chosen:    await self._do_mf(run_doc, dry_run)
            if "forex" in chosen:          await self._do_forex(run_doc, dry_run)
            if "referrals" in chosen:      await self._do_referrals(run_doc, dry_run)
            run_doc["status"] = "completed"
        except Exception as e:
            run_doc["status"] = "failed"
            run_doc["errors_sample"].append({"where": "top-level", "error": str(e)})
            logger.exception("backfill failed")

        run_doc["finished_at"] = _now()
        run_doc["duration_ms"] = int((time.time() - started) * 1000)
        await self.db[MIGRATION_COLL].update_one({"run_id": run_id},
                                                    {"$set": {k: v for k, v in run_doc.items()
                                                              if k not in ("run_id", "created_at")}})
        return run_doc

    # ------------------------------------------------------------ writers -
    async def _emit(self, run_doc: Dict[str, Any], dry_run: bool,
                     module: str, entry_kwargs: Dict[str, Any]) -> None:
        run_doc["processed"] += 1
        mod_stats = run_doc["per_module"].setdefault(module, {
            "processed": 0, "migrated": 0, "skipped": 0, "failed": 0,
        })
        mod_stats["processed"] += 1
        if dry_run:
            mod_stats["migrated"] += 1  # would-be-migrated
            run_doc["migrated"] += 1
            return
        try:
            entry = JournalEntry.make(**entry_kwargs)
            # Skip if dedupe key already has an entry
            existing = None
            dk = entry.get("dedupe_key")
            if dk:
                existing = await self.db.finance_journal.find_one({"dedupe_key": dk}, {"_id": 0})
            if existing:
                mod_stats["skipped"] += 1
                run_doc["skipped"] += 1
                return
            await self.journal.post(entry)
            mod_stats["migrated"] += 1
            run_doc["migrated"] += 1
        except Exception as e:
            mod_stats["failed"] += 1
            run_doc["failed"] += 1
            if len(run_doc["errors_sample"]) < 20:
                run_doc["errors_sample"].append({"module": module, "error": str(e),
                                                    "row_id": entry_kwargs.get("reference_id")})

    # ------------------------------------------------------------ wallet ----
    async def _do_wallet(self, run_doc, dry_run):
        """Aggregate paired wallet_ledger rows (debit+credit for the same tx_id)
        into single journal entries. This is the master source — we prefer
        pairs from wallet_ledger over per-module sources because it's the
        cleanest existing double-entry."""
        # Fetch tx_ids grouped
        pipeline = [{"$group": {"_id": "$tx_id",
                                 "user_id": {"$first": "$user_id"},
                                 "amount": {"$first": "$amount"},
                                 "category": {"$first": "$category"},
                                 "description": {"$first": "$description"},
                                 "provider": {"$first": "$provider"},
                                 "reference_id": {"$first": "$reference_id"},
                                 "created_at": {"$first": "$created_at"},
                                 "accounts": {"$push": "$account"},
                                 "sides": {"$push": "$side"}}}]
        async for grp in self.db.wallet_ledger.aggregate(pipeline, allowDiskUse=True):
            tx_id = grp["_id"]
            if not tx_id or len(grp["sides"]) < 2:
                continue
            # Determine credit vs debit based on which side is user:wallet
            uid = grp["user_id"]
            user_acct = f"user:wallet:{uid}"
            try:
                cr_idx = grp["accounts"].index(user_acct) if user_acct in grp["accounts"] else -1
                dr_idx = grp["accounts"].index(user_acct) if user_acct in grp["accounts"] else -1
            except ValueError:
                cr_idx = dr_idx = -1
            side = "credit"
            for a, s in zip(grp["accounts"], grp["sides"]):
                if a == user_acct:
                    side = "credit" if s == "CR" else "debit"
                    break
            # Map to Journal category
            from .hooks import _pick_txn_type, _pick_counterparty
            txn_type = _pick_txn_type(grp.get("category") or "", side)
            counter = _pick_counterparty(txn_type, grp.get("provider"))
            amount = float(grp["amount"])
            user_leg = coa_user_wallet(uid)
            if side == "credit":
                legs = [JournalLeg.make(counter, amount, "DR"),
                        JournalLeg.make(user_leg, amount, "CR")]
            else:
                legs = [JournalLeg.make(user_leg, amount, "DR"),
                        JournalLeg.make(counter, amount, "CR")]
            await self._emit(run_doc, dry_run, "wallet_ledger", dict(
                txn_type=txn_type, legs=legs, amount=amount,
                reference_id=grp.get("reference_id") or tx_id,
                reference_type=grp.get("category") or "wallet",
                user_id=uid,
                narration=grp.get("description") or "",
                posted_by="backfill",
                entry_date=grp.get("created_at") or _now(),
                metadata={"tx_id": tx_id, "provider": grp.get("provider"),
                          "backfilled": True, "source": "wallet_ledger"},
                dedupe_key=f"backfill:wallet_ledger:{tx_id}",
            ))

    # ------------------------------------------------------------ payments --
    async def _do_payments(self, run_doc, dry_run):
        """Any captured Razorpay orders whose wallet-side wasn't traced already."""
        cur = self.db.payments_orders.find(
            {"status": "captured", "wallet_credited": True}, {"_id": 0}
        )
        async for o in cur:
            uid = o.get("user_id")
            if not uid:
                continue
            amt = float(o.get("amount_paise", 0)) / 100.0
            if amt <= 0:
                continue
            legs = [
                JournalLeg.make(coa_provider("razorpay"), amt, "DR"),
                JournalLeg.make(coa_user_wallet(uid), amt, "CR"),
            ]
            await self._emit(run_doc, dry_run, "payments", dict(
                txn_type="razorpay_deposit", legs=legs, amount=amt,
                reference_id=o.get("order_id"), reference_type="razorpay_order",
                user_id=uid,
                narration=f"Wallet top-up · {o.get('receipt') or o.get('order_id')}",
                posted_by="backfill",
                entry_date=o.get("captured_at") or o.get("created_at") or _now(),
                metadata={"provider_order_id": o.get("provider_order_id"),
                           "provider_payment_id": o.get("provider_payment_id"),
                           "backfilled": True, "source": "payments_orders"},
                dedupe_key=f"backfill:payments:{o.get('order_id')}",
            ))

    # ------------------------------------------------------------ withdrawals
    async def _do_withdrawals(self, run_doc, dry_run):
        """Completed withdrawals — user wallet was already debited via
        `debit_wallet` (captured under wallet_ledger)."""
        cur = self.db.withdrawal_requests.find({"status": "completed"}, {"_id": 0})
        async for w in cur:
            uid = w.get("user_id")
            amt = float(w.get("net_amount") or w.get("amount") or 0)
            if not uid or amt <= 0:
                continue
            legs = [
                JournalLeg.make(coa_user_wallet(uid), amt, "DR"),
                JournalLeg.make(coa_provider(w.get("provider") or "cashfree"), amt, "CR"),
            ]
            await self._emit(run_doc, dry_run, "withdrawals", dict(
                txn_type="cashfree_withdrawal", legs=legs, amount=amt,
                reference_id=w.get("withdrawal_id"), reference_type="withdrawal",
                user_id=uid,
                narration=f"Withdrawal · {w.get('reference_no') or w.get('withdrawal_id')}",
                posted_by="backfill",
                entry_date=w.get("completed_at") or w.get("updated_at") or _now(),
                metadata={"utr": w.get("utr"), "provider_reference": w.get("provider_reference"),
                           "backfilled": True, "source": "withdrawal_requests",
                           "status": w.get("status")},
                dedupe_key=f"backfill:withdrawal:{w.get('withdrawal_id')}",
            ))

    # ------------------------------------------------------------ gold ------
    async def _do_gold(self, run_doc, dry_run):
        # Try common gold-txn collections; skip silently if not present
        for cname in ("gold_transactions", "gold_orders", "gold_txn"):
            if cname not in await self.db.list_collection_names():
                continue
            cur = self.db[cname].find({"status": {"$in": ["completed", "success"]}}, {"_id": 0})
            async for g in cur:
                uid = g.get("user_id")
                amt = float(g.get("total_amount") or g.get("amount") or 0)
                side = (g.get("side") or g.get("type") or "").lower()
                if not uid or amt <= 0 or side not in ("buy", "sell"):
                    continue
                if side == "buy":
                    legs = [JournalLeg.make(coa_user_wallet(uid), amt, "DR"),
                            JournalLeg.make(coa_provider("gold"), amt, "CR")]
                    txn = "gold_buy"
                else:
                    legs = [JournalLeg.make(coa_provider("gold"), amt, "DR"),
                            JournalLeg.make(coa_user_wallet(uid), amt, "CR")]
                    txn = "gold_sell"
                await self._emit(run_doc, dry_run, "gold", dict(
                    txn_type=txn, legs=legs, amount=amt,
                    reference_id=g.get("txn_id") or g.get("order_id") or g.get("gold_id"),
                    reference_type=cname, user_id=uid,
                    narration=f"Gold {side} · {g.get('grams') or ''}g",
                    posted_by="backfill",
                    entry_date=g.get("created_at") or _now(),
                    metadata={"grams": g.get("grams"), "backfilled": True, "source": cname},
                    dedupe_key=f"backfill:gold:{g.get('txn_id') or g.get('order_id')}",
                ))
            break

    # ------------------------------------------------------------ MF -------
    async def _do_mf(self, run_doc, dry_run):
        for cname in ("mf_orders", "mutual_fund_orders", "mf_investments"):
            if cname not in await self.db.list_collection_names():
                continue
            cur = self.db[cname].find({"status": {"$in": ["completed", "success", "settled"]}}, {"_id": 0})
            async for m in cur:
                uid = m.get("user_id")
                amt = float(m.get("amount") or 0)
                side = (m.get("type") or m.get("side") or "").lower()
                if not uid or amt <= 0:
                    continue
                if side in ("buy", "lumpsum", "sip"):
                    legs = [JournalLeg.make(coa_user_wallet(uid), amt, "DR"),
                            JournalLeg.make(coa_provider("mutual_funds"), amt, "CR")]
                    txn = "mutual_fund_buy"
                elif side in ("redeem", "sell"):
                    legs = [JournalLeg.make(coa_provider("mutual_funds"), amt, "DR"),
                            JournalLeg.make(coa_user_wallet(uid), amt, "CR")]
                    txn = "mutual_fund_redeem"
                else:
                    continue
                await self._emit(run_doc, dry_run, "mutual_funds", dict(
                    txn_type=txn, legs=legs, amount=amt,
                    reference_id=m.get("order_id") or m.get("id"),
                    reference_type=cname, user_id=uid,
                    narration=f"MF {side} · {m.get('scheme_name') or m.get('fund_id') or ''}",
                    posted_by="backfill",
                    entry_date=m.get("created_at") or _now(),
                    metadata={"scheme": m.get("scheme_name") or m.get("fund_id"),
                               "backfilled": True, "source": cname},
                    dedupe_key=f"backfill:mf:{m.get('order_id') or m.get('id')}",
                ))
            break

    # ------------------------------------------------------------ forex ----
    async def _do_forex(self, run_doc, dry_run):
        for cname in ("forex_positions", "forex_trades"):
            if cname not in await self.db.list_collection_names():
                continue
            cur = self.db[cname].find({"status": "closed"}, {"_id": 0})
            async for p in cur:
                uid = p.get("user_id")
                pnl = float(p.get("realised_pnl") or p.get("pnl") or 0)
                if not uid or abs(pnl) < 0.01:
                    continue
                if pnl > 0:
                    legs = [JournalLeg.make(coa_revenue_forex(), pnl, "DR"),
                            JournalLeg.make(coa_user_wallet(uid), pnl, "CR")]
                else:
                    legs = [JournalLeg.make(coa_user_wallet(uid), abs(pnl), "DR"),
                            JournalLeg.make(coa_revenue_forex(), abs(pnl), "CR")]
                await self._emit(run_doc, dry_run, "forex", dict(
                    txn_type="forex_pnl", legs=legs, amount=abs(pnl),
                    reference_id=p.get("position_id") or p.get("id"),
                    reference_type=cname, user_id=uid,
                    narration=f"Forex realised P&L · {p.get('symbol') or ''} · ₹{pnl:+.2f}",
                    posted_by="backfill",
                    entry_date=p.get("closed_at") or p.get("updated_at") or _now(),
                    metadata={"symbol": p.get("symbol"), "pnl": pnl,
                               "backfilled": True, "source": cname},
                    dedupe_key=f"backfill:forex:{p.get('position_id') or p.get('id')}",
                ))
            break

    async def _do_referrals(self, run_doc, dry_run):
        for cname in ("referral_bonuses", "referrals", "cashback_events"):
            if cname not in await self.db.list_collection_names():
                continue
            cur = self.db[cname].find({"status": {"$in": ["credited", "success"]}}, {"_id": 0})
            async for r in cur:
                uid = r.get("user_id")
                amt = float(r.get("amount") or 0)
                if not uid or amt <= 0:
                    continue
                is_cashback = "cashback" in cname
                legs = [JournalLeg.make(coa_expense_referral(), amt, "DR"),
                        JournalLeg.make(coa_user_wallet(uid), amt, "CR")]
                await self._emit(run_doc, dry_run, "referrals", dict(
                    txn_type="cashback" if is_cashback else "referral_bonus",
                    legs=legs, amount=amt,
                    reference_id=r.get("id") or r.get("_id"),
                    reference_type=cname, user_id=uid,
                    narration=r.get("description") or ("Cashback" if is_cashback else "Referral bonus"),
                    posted_by="backfill",
                    entry_date=r.get("created_at") or _now(),
                    metadata={"backfilled": True, "source": cname},
                    dedupe_key=f"backfill:{cname}:{r.get('id') or str(r.get('_id'))}",
                ))
