"""AI Market News & Analytics — Sprint 7C.2

Modules:
  * news_engine.py    — AI-generated market news (Claude Sonnet 4.5)
  * calendar_engine.py — Economic calendar with impact filters + countdown
  * summary_engine.py — Daily/weekly/intraday market summaries (AI)
  * analytics_engine.py — Signal analytics (win rate, TP hit rate, ROI)
  * routes.py — All API endpoints (public + admin console)

All AI features degrade to a deterministic fallback so backend tests never
depend on network / API keys. Notifications are dispatched via the same
Mongo collection as other notifications so nothing regresses.
"""
from __future__ import annotations
import logging

from .analytics_engine import AnalyticsEngine
from .calendar_engine import CalendarSeeder
from .news_engine import NewsBroadcaster
from .routes import attach as _attach_routes

logger = logging.getLogger("ai_news")


def attach(app, db, get_current_user, get_current_admin):
    analytics = AnalyticsEngine(db, interval_sec=300)
    broadcaster = NewsBroadcaster(db, interval_sec=120)
    seeder = CalendarSeeder(db)

    router = _attach_routes(app, db, get_current_user, get_current_admin,
                            analytics=analytics, broadcaster=broadcaster)

    async def _startup():
        try:
            await seeder.ensure_seeded()
            await analytics.start()
            await broadcaster.start()
            logger.info("ai_news subsystem attached (Sprint 7C.2)")
        except Exception as e:
            logger.exception("ai_news startup failed: %s", e)

    async def _shutdown():
        try:
            await analytics.stop()
            await broadcaster.stop()
        except Exception:
            pass

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)
    return router


__all__ = ["attach"]
