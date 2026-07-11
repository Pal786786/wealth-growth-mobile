"""Reconciliation job — heals missed webhooks.

Runs:
  * On demand via admin endpoint
  * Every 30 minutes as a background task (auto-scan orders in `created`/`attempted`)

Approach: for each recent order still in a pending state, ask Razorpay for the
current status. If we find a captured payment we haven't recorded yet, pipe it
through `engine.capture_payment()` so wallet gets credited.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .models import OrderStatus
from .providers.razorpay import RazorpayError

logger = logging.getLogger("payments.reconciliation")

RECON_COLL = "payments_reconciliation_runs"


def _now():
    return datetime.now(timezone.utc)


class ReconciliationJob:
    def __init__(self, db, engine, interval_sec: int = 1800):
        self.db = db
        self.engine = engine
        self.interval_sec = int(interval_sec)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("reconciliation job started (interval=%ds)", self.interval_sec)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        # Warm-up so we don't pound Razorpay right after boot
        await asyncio.sleep(30)
        while not self._stop.is_set():
            try:
                await self.run_once(triggered_by="scheduled")
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("reconciliation loop error: %s", e)
            await asyncio.sleep(self.interval_sec)

    async def run_once(self, triggered_by: str = "admin",
                        window_hours: int = 24) -> Dict[str, Any]:
        run_id = f"rec_{_now().timestamp():.0f}"
        start = _now()
        cutoff = start - timedelta(hours=int(window_hours))
        stats = {
            "run_id": run_id, "started_at": start,
            "triggered_by": triggered_by,
            "window_hours": window_hours,
            "scanned": 0, "healed": 0, "failed": 0, "expired": 0,
            "errors": [],
        }

        # Only reconcile against a real Razorpay account
        provider = self.engine._provider()
        if not provider.configured or getattr(provider, "key_id", "").startswith("rzp_test_demo_stub"):
            stats["skipped"] = "demo_mode_or_unconfigured"
            stats["finished_at"] = _now()
            stats["duration_ms"] = 0
            await self.db[RECON_COLL].insert_one(dict(stats))
            stats["started_at"] = start.isoformat()
            stats["finished_at"] = stats["finished_at"].isoformat()
            return stats

        # Scan pending orders
        cursor = self.db["payments_orders"].find({
            "status": {"$in": [OrderStatus.CREATED.value, OrderStatus.ATTEMPTED.value]},
            "created_at": {"$gte": cutoff},
        }, {"_id": 0})
        async for order in cursor:
            stats["scanned"] += 1
            try:
                # 1. Fetch the associated payments from Razorpay
                payments = provider.fetch_order_payments(order["provider_order_id"])
                healed_any = False
                for p in payments:
                    if p.get("status") == "captured":
                        try:
                            await self.engine.capture_payment(
                                provider_payment_id=p["id"],
                                provider_order_id=order["provider_order_id"],
                                amount_paise=int(p.get("amount") or order["amount_paise"]),
                                method=p.get("method", "other"),
                                raw_payment=p,
                            )
                            healed_any = True
                            stats["healed"] += 1
                        except Exception as e:
                            stats["failed"] += 1
                            stats["errors"].append({"order_id": order["order_id"],
                                                    "error": str(e)[:200]})
                    elif p.get("status") == "failed":
                        await self.engine.fail_payment(
                            provider_payment_id=p["id"],
                            provider_order_id=order["provider_order_id"],
                            reason=p.get("error_description", "failed"),
                            raw=p,
                        )
                if not healed_any:
                    # Expire orders older than 30 min still pending
                    created = order.get("created_at")
                    if isinstance(created, str):
                        try:
                            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except Exception:
                            created = None
                    if created and created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if created and (_now() - created) > timedelta(minutes=30):
                        await self.engine._mark_status(
                            order["order_id"], OrderStatus.EXPIRED.value,
                            extra={"expired_at": _now()})
                        stats["expired"] += 1
            except RazorpayError as e:
                stats["failed"] += 1
                stats["errors"].append({"order_id": order["order_id"], "error": str(e)[:200]})
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append({"order_id": order["order_id"], "error": str(e)[:200]})

        stats["finished_at"] = _now()
        stats["duration_ms"] = int((stats["finished_at"] - start).total_seconds() * 1000)
        await self.db[RECON_COLL].insert_one(dict(stats))
        # ISO-format for the return payload
        stats["started_at"] = start.isoformat()
        stats["finished_at"] = stats["finished_at"].isoformat()
        logger.info("reconciliation done", extra=stats)
        return stats

    async def latest_run(self) -> Optional[Dict[str, Any]]:
        d = await self.db[RECON_COLL].find_one({}, {"_id": 0},
                                                 sort=[("started_at", -1)])
        if not d:
            return None
        for k in ("started_at", "finished_at"):
            v = d.get(k)
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d

    async def recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        cur = self.db[RECON_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(int(limit))
        rows = [d async for d in cur]
        for d in rows:
            for k in ("started_at", "finished_at"):
                v = d.get(k)
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
        return rows
