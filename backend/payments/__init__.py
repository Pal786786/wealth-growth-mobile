"""Payments — Sprint 8 (Production Payments Phase 1)

Razorpay production integration with:
  * Orders API (via razorpay Python SDK)
  * HMAC webhook signature verification + replay protection
  * Idempotency-Key HTTP header support
  * Full + Partial Refund APIs
  * Reconciliation (auto-heal missed webhooks)
  * Structured JSON logging (secrets never logged)
  * Admin dashboard: orders, transactions, refunds, reconciliation, audit log
  * Demo mode fallback (admin toggle) that simulates Razorpay locally

Wallet is NEVER credited until webhook signature verification passes.
"""
from __future__ import annotations
import logging

from .engine import PaymentsEngine
from .reconciliation import ReconciliationJob
from .routes import attach as _attach_routes
from .logging_setup import configure_payments_logging

logger = logging.getLogger("payments")


def attach(app, db, get_current_user, get_current_admin):
    configure_payments_logging()
    engine = PaymentsEngine(db)
    recon = ReconciliationJob(db, engine)
    router = _attach_routes(app, db, get_current_user, get_current_admin,
                            engine=engine, recon=recon)

    async def _startup():
        try:
            await engine.init_config()
            await recon.start()
            logger.info("payments subsystem attached (Sprint 8) mode=%s demo=%s",
                        engine.mode, engine.demo_mode)
        except Exception as e:
            logger.exception("payments startup failed: %s", e)

    async def _shutdown():
        try:
            await recon.stop()
        except Exception:
            pass

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)
    # Sprint 12.2.1 — expose the engine so downstream modules (wallet_qr) can reuse
    # the same order-creation + webhook-credit pipeline.
    return {"router": router, "engine": engine, "recon": recon}


__all__ = ["attach"]
