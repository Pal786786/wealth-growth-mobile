"""AI Intelligence subsystem — Sprint 7C.1

Independent modules per architecture:
  Signal Engine → TA Engine → AI Engine → Alerts (Notifications) → Frontend
"""
from __future__ import annotations
import logging

from .alerts_engine import AlertsEngine
from .routes import attach as _attach_routes

logger = logging.getLogger("ai_intelligence")


def attach(app, db, get_current_user, get_current_admin=None):
    alerts = AlertsEngine(db, interval_sec=30)
    router = _attach_routes(app, db, get_current_user, alerts, get_current_admin)

    async def _startup():
        try:
            cfg = await db.ai_config.find_one({"_id": "active"})
            if cfg and cfg.get("alerts_eval_interval_sec"):
                alerts.set_interval(int(cfg["alerts_eval_interval_sec"]))
            await alerts.start()
        except Exception as e:
            logger.exception("ai_intelligence startup failed: %s", e)

    async def _shutdown():
        try:
            await alerts.stop()
        except Exception:
            pass

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)
    return router


__all__ = ["attach"]
