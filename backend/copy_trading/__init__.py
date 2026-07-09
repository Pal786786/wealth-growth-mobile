"""Copy Trading module — Sprint 7B.2

Bootstrap wiring:
  1. Load CopyConfig
  2. Build EventBus + PaperBroker + CopyEngine + MasterSimulator
  3. Register HTTP routes
  4. Start simulator on FastAPI startup
"""
from __future__ import annotations
import logging
from typing import Any

from .config import CopyConfig
from .events import EventBus
from .broker import build_broker
from .engine import CopyEngine
from .simulator import MasterSimulator
from .routes import attach as _attach_routes

logger = logging.getLogger("copy_trading")


def attach(app, db, get_current_user, get_current_admin=None) -> Any:
    """Wire subsystem into the FastAPI app. Returns the router."""
    config = CopyConfig(db)
    bus = EventBus()
    broker = build_broker("paper", db=db)
    engine = CopyEngine(db=db, bus=bus, broker=broker, config=config)
    simulator = MasterSimulator(db=db, bus=bus, config=config)

    router = _attach_routes(app, db, get_current_user, engine, simulator, get_current_admin)

    # Kick off the simulator on FastAPI startup so demo trades begin flowing
    async def _startup():
        try:
            await config.load(force=True)
            await simulator.start()
            logger.info("copy_trading: simulator started")
        except Exception as e:
            logger.exception("copy_trading startup failed: %s", e)

    async def _shutdown():
        try:
            await simulator.stop()
        except Exception:
            pass

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)

    return router


__all__ = ["attach"]
