"""Mutual Funds Platform — Sprint 11.

Production module with:
  * Provider abstraction (Mock + AMFI + CAMS/KFintech/MF Central stubs)
  * Order lifecycle (created → pending_payment → processing → allocated → completed → failed → redeemed)
  * SIP state machine (active / paused / cancelled / failed / completed) with retry policy
  * Portfolio analytics (XIRR, CAGR, Daily/Weekly/Monthly P/L, allocations)
  * Goal planning (SIP required, completion ETA, progress, AI recs)
  * Fund comparison & watchlist
  * AI Advisor integration (Claude Sonnet 4.5)
  * Notification fan-out
Reuses: Wallet, Notifications, KYC v2, AI Advisor, Live Market cache, Admin analytics framework.
"""
from __future__ import annotations
import logging
from .engine import MutualFundEngine
from .routes import attach as _attach_routes

logger = logging.getLogger("mutual_funds")


def attach(app, db, get_current_user, get_current_admin):
    engine = MutualFundEngine(db)
    _attach_routes(app, db, get_current_user, get_current_admin, engine)

    async def _startup():
        try:
            await engine.init_config()
            await engine.seed_if_needed()
            logger.info("mutual_funds attached (Sprint 11) provider=%s funds=%d",
                        engine.config.get("provider"), await engine.count_funds())
        except Exception as e:
            logger.exception("mutual_funds startup failed: %s", e)

    app.add_event_handler("startup", _startup)
    return None


__all__ = ["attach"]
