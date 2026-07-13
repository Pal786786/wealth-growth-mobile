"""Sprint 12.3 · Phase C — Finance Alert Engine + Provider Health.

Read-only monitor that evaluates rules over journal + reconciliation + provider
data, produces alerts, and integrates with the existing notification system.

Alerts NEVER modify balances or the journal. Purely observational.
"""
from __future__ import annotations
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("finance_ledger.alerts")

ALERTS_COLL = "finance_alerts"
HEALTH_COLL = "finance_provider_health"
JOBS_COLL   = "finance_scheduler_jobs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


ALERT_TYPES = {
    "settlement_failed":          {"sev": "critical", "label": "Settlement failed"},
    "provider_offline":            {"sev": "critical", "label": "Provider offline"},
    "high_payment_failure_rate":   {"sev": "warning",  "label": "High payment failure rate"},
    "ledger_mismatch":              {"sev": "critical", "label": "Ledger mismatch"},
    "negative_balance":             {"sev": "critical", "label": "Negative account balance"},
    "large_withdrawal":             {"sev": "warning",  "label": "Large withdrawal"},
    "large_refund":                  {"sev": "warning",  "label": "Large refund"},
    "large_wallet_adjustment":      {"sev": "warning",  "label": "Large wallet adjustment"},
    "high_mismatch_rate":            {"sev": "warning",  "label": "High reconciliation mismatch rate"},
    "low_provider_balance":         {"sev": "warning",  "label": "Low provider balance"},
    "cashfree_unavailable":          {"sev": "critical", "label": "Cashfree unavailable"},
    "razorpay_unavailable":          {"sev": "critical", "label": "Razorpay unavailable"},
    "pending_settlement_exceeded":  {"sev": "warning",  "label": "Pending settlement exceeded"},
}

DEFAULT_THRESHOLDS = {
    "large_withdrawal_amount": 100_000.0,
    "large_refund_amount": 25_000.0,
    "large_wallet_adjustment_amount": 50_000.0,
    "payment_failure_rate_pct": 20.0,      # % failed in last 24h
    "mismatch_rate_pct": 5.0,               # % of recon rows
    "low_provider_balance_amount": 0.0,     # negative provider balance
    "pending_settlement_hours": 48,
    "provider_offline_hours": 24,
}


class AlertEngine:
    def __init__(self, db, notifier: Optional[Callable] = None):
        self.db = db
        self.notifier = notifier  # async fn(user_id, title, body, deep_link)

    async def ensure_indexes(self) -> None:
        try:
            await self.db[ALERTS_COLL].create_index(
                [("dedupe_key", 1)], unique=True, sparse=True, name="fa_dedupe")
        except Exception:
            pass
        for spec, name in [
            ([("status", 1), ("created_at", -1)], "fa_status_created"),
            ([("severity", 1)], "fa_sev"),
            ([("type", 1), ("created_at", -1)], "fa_type_created"),
        ]:
            try:
                await self.db[ALERTS_COLL].create_index(spec, name=name)
            except Exception:
                pass
        try:
            await self.db[HEALTH_COLL].create_index(
                [("provider", 1)], unique=True, name="fh_provider")
        except Exception:
            pass

    async def raise_alert(self, *, alert_type: str, entity_id: Optional[str] = None,
                            message: str = "", context: Optional[Dict[str, Any]] = None,
                            dedupe_window_minutes: int = 60) -> Optional[Dict[str, Any]]:
        """Insert an alert (dedupe within window). Fires notification."""
        meta = ALERT_TYPES.get(alert_type)
        if meta is None:
            logger.warning("unknown alert_type: %s", alert_type)
            return None
        dedupe_key = f"{alert_type}:{entity_id or 'global'}:{int(_now().timestamp() // (dedupe_window_minutes * 60))}"
        existing = await self.db[ALERTS_COLL].find_one({"dedupe_key": dedupe_key}, {"_id": 0})
        if existing:
            return existing
        alert = {
            "alert_id": f"al_{secrets.token_hex(8)}",
            "type": alert_type, "label": meta["label"], "severity": meta["sev"],
            "status": "active",
            "entity_id": entity_id, "message": message,
            "context": context or {},
            "created_at": _now(), "acknowledged_at": None, "resolved_at": None,
            "acknowledged_by": None, "resolved_by": None,
            "notes": [], "dedupe_key": dedupe_key,
        }
        try:
            await self.db[ALERTS_COLL].insert_one(alert)
        except Exception as e:
            if "duplicate key" not in str(e).lower():
                raise
            return existing
        # Fire in-app notification (best-effort)
        if self.notifier:
            try:
                await self.notifier(
                    None, f"[{meta['sev'].upper()}] {meta['label']}",
                    message[:180] or meta["label"],
                    f"/finance?alert={alert['alert_id']}",
                )
            except Exception as e:
                logger.debug("alert notification failed: %s", e)
        return alert

    # ------------------------------------------------------- Rule engine ---
    async def run_all_rules(self, thresholds: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        raised = []
        try: raised += await self._rule_settlement_failed(th)
        except Exception as e: logger.warning("rule settlement_failed: %s", e)
        try: raised += await self._rule_high_payment_failure(th)
        except Exception as e: logger.warning("rule high_payment_failure: %s", e)
        try: raised += await self._rule_ledger_mismatch(th)
        except Exception as e: logger.warning("rule ledger_mismatch: %s", e)
        try: raised += await self._rule_negative_balance(th)
        except Exception as e: logger.warning("rule negative_balance: %s", e)
        try: raised += await self._rule_large_events(th)
        except Exception as e: logger.warning("rule large_events: %s", e)
        try: raised += await self._rule_provider_health(th)
        except Exception as e: logger.warning("rule provider_health: %s", e)
        try: raised += await self._rule_pending_settlement(th)
        except Exception as e: logger.warning("rule pending_settlement: %s", e)
        return {"raised": len(raised), "alerts": raised, "ran_at": _now()}

    async def _rule_settlement_failed(self, th) -> List[Dict[str, Any]]:
        out = []
        # Any withdrawal in status=failed produced in last 24h → alert
        cutoff = _now() - timedelta(hours=24)
        cur = self.db.withdrawal_requests.find(
            {"status": "failed", "updated_at": {"$gte": cutoff}}, {"_id": 0},
        )
        async for w in cur:
            a = await self.raise_alert(
                alert_type="settlement_failed",
                entity_id=w.get("withdrawal_id"),
                message=f"Withdrawal {w.get('reference_no')} failed: {w.get('reason_admin') or w.get('provider_reason') or 'unknown'}",
                context={"amount": w.get("amount"), "user_id": w.get("user_id")},
            )
            if a: out.append(a)
        return out

    async def _rule_high_payment_failure(self, th) -> List[Dict[str, Any]]:
        cutoff = _now() - timedelta(hours=24)
        total = await self.db.payments_orders.count_documents({"created_at": {"$gte": cutoff}})
        if total < 10:
            return []
        failed = await self.db.payments_orders.count_documents(
            {"status": "failed", "created_at": {"$gte": cutoff}})
        rate = 100.0 * failed / total
        if rate >= th["payment_failure_rate_pct"]:
            a = await self.raise_alert(
                alert_type="high_payment_failure_rate",
                message=f"{rate:.1f}% payments failed in last 24h ({failed}/{total})",
                context={"rate_pct": rate, "failed": failed, "total": total},
                dedupe_window_minutes=60 * 6,
            )
            return [a] if a else []
        return []

    async def _rule_ledger_mismatch(self, th) -> List[Dict[str, Any]]:
        total = await self.db.finance_reconciliation.count_documents({})
        if total == 0:
            return []
        mm = await self.db.finance_reconciliation.count_documents(
            {"status": {"$in": ["mismatch", "manual_review"]}})
        rate = 100.0 * mm / total
        out = []
        if rate >= th["mismatch_rate_pct"]:
            a = await self.raise_alert(
                alert_type="high_mismatch_rate",
                message=f"{rate:.1f}% of recon rows are unmatched ({mm}/{total})",
                context={"rate_pct": rate, "mismatch": mm, "total": total},
                dedupe_window_minutes=60 * 6,
            )
            if a: out.append(a)
        # Individual critical mismatches (missing_payment) — high severity
        cur = self.db.finance_reconciliation.find(
            {"status": "mismatch", "reason": "missing_payment"}, {"_id": 0}
        ).limit(50)
        async for m in cur:
            a = await self.raise_alert(
                alert_type="ledger_mismatch", entity_id=m.get("pair_key"),
                message=f"{m.get('module')} row {m.get('reference_id')} has no journal entry",
                context={"pair_key": m.get("pair_key"),
                          "delta": m.get("delta"), "module": m.get("module")},
            )
            if a: out.append(a)
        return out

    async def _rule_negative_balance(self, th) -> List[Dict[str, Any]]:
        out = []
        cur = self.db.finance_ledger_balances.find(
            {"balance": {"$lt": -0.01}}, {"_id": 0}
        )
        async for b in cur:
            a = await self.raise_alert(
                alert_type="negative_balance", entity_id=b["account"],
                message=f"Negative balance on {b['account']}: {b['balance']}",
                context={"account": b["account"], "balance": b["balance"]},
            )
            if a: out.append(a)
        return out

    async def _rule_large_events(self, th) -> List[Dict[str, Any]]:
        out = []
        cutoff = _now() - timedelta(hours=24)
        # Large withdrawals
        async for w in self.db.withdrawal_requests.find({
                "amount": {"$gte": th["large_withdrawal_amount"]},
                "created_at": {"$gte": cutoff}}, {"_id": 0}):
            a = await self.raise_alert(
                alert_type="large_withdrawal", entity_id=w.get("withdrawal_id"),
                message=f"Large withdrawal ₹{w.get('amount'):.0f} by {w.get('user_id')}",
                context={"amount": w.get("amount"), "user_id": w.get("user_id"),
                          "status": w.get("status")},
                dedupe_window_minutes=60 * 24,
            )
            if a: out.append(a)
        # Large wallet adjustments
        async for j in self.db.finance_journal.find({
                "txn_type": "admin_adjustment",
                "amount": {"$gte": th["large_wallet_adjustment_amount"]},
                "entry_date": {"$gte": cutoff},
                "is_reversed": {"$ne": True}}, {"_id": 0}):
            a = await self.raise_alert(
                alert_type="large_wallet_adjustment", entity_id=j.get("journal_id"),
                message=f"Large admin adjustment ₹{j.get('amount'):.0f} on user {j.get('user_id')}",
                context={"amount": j.get("amount"), "user_id": j.get("user_id"),
                          "narration": j.get("narration")},
                dedupe_window_minutes=60 * 24,
            )
            if a: out.append(a)
        return out

    async def _rule_provider_health(self, th) -> List[Dict[str, Any]]:
        """Check provider health snapshot age; raise if stale."""
        out = []
        stale_cutoff = _now() - timedelta(hours=th["provider_offline_hours"])
        async for h in self.db[HEALTH_COLL].find({}, {"_id": 0}):
            prov = h["provider"]
            ls = h.get("last_success_at")
            if ls and ls.tzinfo is None:
                ls = ls.replace(tzinfo=timezone.utc)
            if not ls or ls < stale_cutoff:
                atype = "razorpay_unavailable" if prov == "razorpay" else \
                        "cashfree_unavailable" if prov == "cashfree" else \
                        "provider_offline"
                a = await self.raise_alert(
                    alert_type=atype, entity_id=prov,
                    message=f"{prov} appears offline (last success: {ls or 'never'})",
                    context={"provider": prov, "last_success_at": str(ls)},
                    dedupe_window_minutes=60 * 6,
                )
                if a: out.append(a)
        # Low provider balance
        async for b in self.db.finance_ledger_balances.find(
            {"account": {"$regex": "^assets:provider:"},
              "balance": {"$lt": th["low_provider_balance_amount"]}}, {"_id": 0}
        ):
            a = await self.raise_alert(
                alert_type="low_provider_balance",
                entity_id=b["account"].split(":")[-1],
                message=f"Provider {b['account']} balance is {b['balance']:.2f}",
                context={"account": b["account"], "balance": b["balance"]},
                dedupe_window_minutes=60 * 6,
            )
            if a: out.append(a)
        return out

    async def _rule_pending_settlement(self, th) -> List[Dict[str, Any]]:
        out = []
        cutoff = _now() - timedelta(hours=th["pending_settlement_hours"])
        async for w in self.db.withdrawal_requests.find({
                "status": {"$in": ["approved", "processing"]},
                "created_at": {"$lte": cutoff}}, {"_id": 0}):
            a = await self.raise_alert(
                alert_type="pending_settlement_exceeded",
                entity_id=w.get("withdrawal_id"),
                message=f"Withdrawal {w.get('reference_no')} pending > {th['pending_settlement_hours']}h",
                context={"amount": w.get("amount"),
                          "since": str(w.get("created_at"))},
                dedupe_window_minutes=60 * 24,
            )
            if a: out.append(a)
        return out


# ================================================================ Health --
class ProviderHealth:
    """Read-only provider health probe. Uses recent transaction success/failure
    counts to derive online/offline status. NO network probes."""
    def __init__(self, db):
        self.db = db

    async def snapshot(self, provider: str) -> Dict[str, Any]:
        p = provider.lower()
        h = await self.db[HEALTH_COLL].find_one({"provider": p}, {"_id": 0})
        # Compute fresh metrics
        cutoff_24 = _now() - timedelta(hours=24)
        metrics = {"provider": p, "last_computed": _now()}
        if p == "razorpay":
            total = await self.db.payments_orders.count_documents(
                {"created_at": {"$gte": cutoff_24}})
            failed = await self.db.payments_orders.count_documents(
                {"status": "failed", "created_at": {"$gte": cutoff_24}})
            last_success = await self.db.payments_orders.find_one(
                {"status": "captured"}, {"_id": 0, "captured_at": 1},
                sort=[("captured_at", -1)])
            last_failure = await self.db.payments_orders.find_one(
                {"status": "failed"}, {"_id": 0, "updated_at": 1},
                sort=[("updated_at", -1)])
            metrics.update({
                "requests_24h": total, "failed_24h": failed,
                "error_rate_pct": round(100 * failed / total, 2) if total else 0,
                "last_success_at": last_success.get("captured_at") if last_success else None,
                "last_failure_at": last_failure.get("updated_at") if last_failure else None,
            })
        elif p == "cashfree":
            if "withdrawal_settlements" in await self.db.list_collection_names():
                total = await self.db.withdrawal_settlements.count_documents(
                    {"created_at": {"$gte": cutoff_24}})
                failed = await self.db.withdrawal_settlements.count_documents(
                    {"status": "failed", "created_at": {"$gte": cutoff_24}})
                last_success = await self.db.withdrawal_settlements.find_one(
                    {"status": "success"}, {"_id": 0, "created_at": 1},
                    sort=[("created_at", -1)])
                last_failure = await self.db.withdrawal_settlements.find_one(
                    {"status": "failed"}, {"_id": 0, "created_at": 1},
                    sort=[("created_at", -1)])
                metrics.update({
                    "requests_24h": total, "failed_24h": failed,
                    "error_rate_pct": round(100 * failed / total, 2) if total else 0,
                    "last_success_at": last_success.get("created_at") if last_success else None,
                    "last_failure_at": last_failure.get("created_at") if last_failure else None,
                })
            else:
                metrics.update({"requests_24h": 0, "failed_24h": 0,
                                "error_rate_pct": 0, "last_success_at": None,
                                "last_failure_at": None})
        else:
            # Generic provider — infer nothing from DB
            metrics.update({"requests_24h": 0, "failed_24h": 0,
                             "error_rate_pct": 0, "last_success_at": None,
                             "last_failure_at": None})
        # Derive online status
        err = metrics["error_rate_pct"]
        ls = metrics["last_success_at"]
        if ls and ls.tzinfo is None:
            ls = ls.replace(tzinfo=timezone.utc)
        hours_since_success = ((_now() - ls).total_seconds() / 3600) if ls else 999
        status = "online" if hours_since_success < 24 and err < 50 else \
                 "degraded" if hours_since_success < 168 else "offline"
        metrics["status"] = status
        metrics["hours_since_success"] = round(hours_since_success, 2) if ls else None
        metrics["response_time_ms"] = (h or {}).get("response_time_ms")
        metrics["circuit_breaker"] = "open" if status == "offline" else "closed"
        metrics["backoff"] = "active" if status == "offline" else "none"
        # Persist snapshot
        await self.db[HEALTH_COLL].update_one(
            {"provider": p},
            {"$set": metrics, "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )
        return metrics

    async def all_snapshots(self, providers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        provs = providers or ["razorpay", "cashfree", "live_market",
                                "mutual_funds", "gold"]
        return [await self.snapshot(p) for p in provs]


# ================================================================ Scheduler
class Scheduler:
    """In-process cooperative scheduler. Runs periodic jobs (recon,
    finance summaries, alerts) using asyncio background tasks."""
    def __init__(self, db, alert_engine: AlertEngine, health: ProviderHealth,
                 reconciler, kpi_module):
        self.db = db
        self.alert_engine = alert_engine
        self.health = health
        self.reconciler = reconciler
        self.kpi = kpi_module
        self._task: Optional[asyncio.Task] = None
        self._stop = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        logger.info("finance scheduler started")

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try: await self._task
            except Exception: pass

    async def _loop(self) -> None:
        # Immediately snapshot health so alerts have data
        try: await self.health.all_snapshots()
        except Exception: pass
        # Then loop: reconcile every hour, run alerts, health every 15 min
        counter = 0
        while not self._stop:
            try:
                await self.health.all_snapshots()
                if counter % 4 == 0:   # every hour
                    await self.reconciler.run(triggered_by="scheduler")
                await self.alert_engine.run_all_rules()
                await self._log_run("periodic", "ok")
            except Exception as e:
                logger.warning("scheduler tick failed: %s", e)
                await self._log_run("periodic", f"failed: {e}")
            counter += 1
            try:
                await asyncio.sleep(900)   # 15 min
            except asyncio.CancelledError:
                break

    async def _log_run(self, kind: str, status: str) -> None:
        await self.db[JOBS_COLL].insert_one(
            {"kind": kind, "status": status, "at": _now()}
        )

    async def trigger_now(self, kind: str) -> Dict[str, Any]:
        """Manually run a specific job. Returns run summary."""
        if kind == "health":
            snaps = await self.health.all_snapshots()
            return {"kind": "health", "snapshots": len(snaps)}
        if kind == "alerts":
            r = await self.alert_engine.run_all_rules()
            return {"kind": "alerts", "raised": r["raised"]}
        if kind == "reconcile":
            r = await self.reconciler.run(triggered_by="scheduler_manual")
            return {"kind": "reconcile", "totals": r["totals"]}
        raise ValueError(f"unknown job kind: {kind}")
