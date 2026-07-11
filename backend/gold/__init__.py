"""Gold Investment Platform — Sprint 10

Production module with provider abstraction (Mock + Augmont/MMTC-PAMP/SafeGold stubs).
Uses the existing Live Market cache when available and falls back to Mock.
"""
from __future__ import annotations
import logging

from .engine import GoldEngine
from .routes import attach as _attach_routes

logger = logging.getLogger("gold")


def attach(app, db, get_current_user, get_current_admin):
    engine = GoldEngine(db)
    _attach_routes(app, db, get_current_user, get_current_admin, engine)

    async def _startup():
        try:
            await engine.init_config()
            logger.info("gold subsystem attached (Sprint 10) provider=%s spread_bps=%s",
                        engine.config.get("provider"), engine.config.get("spread_bps"))
        except Exception as e:
            logger.exception("gold startup failed: %s", e)

    app.add_event_handler("startup", _startup)
    return None


__all__ = ["attach"]
