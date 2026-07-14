"""Live Market Providers subsystem — Sprint 7.5

Bootstrap wiring. Import `manager` from this package elsewhere to read cached
prices. Consumers must never call providers directly.
"""
from __future__ import annotations
import logging
from typing import Optional

from .manager import ProviderManager
from .routes import attach as _attach_routes
from .debug_routes import attach as _attach_debug_routes

logger = logging.getLogger("market_providers")

_manager: Optional[ProviderManager] = None


def get_manager() -> Optional[ProviderManager]:
    """Return the singleton manager (available after attach()). Consumers use this."""
    return _manager


def attach(app, db, get_current_admin, log_action=None):
    global _manager
    _manager = ProviderManager(db)
    router = _attach_routes(app, _manager, get_current_admin)
    _attach_debug_routes(app, _manager, get_current_admin, log_action=log_action)

    async def _startup():
        try:
            await _manager.start()
        except Exception as e:
            logger.exception("market_providers startup failed: %s", e)

    async def _shutdown():
        try:
            await _manager.stop()
        except Exception:
            pass

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)
    return router


__all__ = ["attach", "get_manager"]
