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
from . import key_store  # noqa: F401  — re-exported for legacy shadow writers

logger = logging.getLogger("market_providers")

_manager: Optional[ProviderManager] = None


def get_manager() -> Optional[ProviderManager]:
    """Return the singleton manager (available after attach()). Consumers use this."""
    return _manager


async def propagate_api_key(provider: str, key: str) -> bool:
    """Push a newly-saved API key into the LIVE ProviderManager instance.

    Called by legacy admin save-paths (market_data, market_module, forex)
    AFTER they shadow-write to the canonical Mongo collection, so the
    running manager picks up the key immediately without a restart.

    Returns True on success. Safe to call before manager has started.
    """
    if _manager is None:
        return False
    try:
        prov = _manager._by_name.get(provider)          # type: ignore[attr-defined]
        if not prov or not hasattr(prov, "set_api_key"):
            return False
        prov.set_api_key(key)                            # type: ignore[attr-defined]
        # Reset circuit-breaker for this provider so the next tick uses the new key
        br = _manager._breakers.get(provider)            # type: ignore[attr-defined]
        if br is not None:
            br.opened_at = None
            br.consecutive_failures = 0
        logger.info("propagate_api_key: pushed new %s key into live manager (len=%d)",
                    provider, len(key or ""))
        return True
    except Exception as _e:      # pragma: no cover
        logger.warning("propagate_api_key failed: %s", _e)
        return False


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
