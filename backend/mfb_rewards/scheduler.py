"""MFB Rewards — Background scheduler (APScheduler).

Jobs:
    * campaign auto-close (every 5 min)
    * leaderboard rebuild (every 15 min for weekly/monthly, hourly for all-time)
    * daily analytics snapshot (once per day)
"""
from __future__ import annotations

from typing import Any, Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    HAS_APS = True
except Exception:
    HAS_APS = False

from . import wallet as W
from . import campaigns as _campaigns
from . import analytics as _analytics


_SCHED: Optional[Any] = None


async def start(db, *, logger=None) -> None:
    await W.ensure_indexes(db)
    global _SCHED
    if _SCHED is not None:
        return
    if not HAS_APS:
        if logger:
            logger.warning("apscheduler unavailable — mfb_rewards scheduler disabled")
        return
    sched = AsyncIOScheduler(timezone="UTC")

    async def _close_expired():
        try:
            await _campaigns.auto_close_expired(db)
        except Exception as e:                      # pragma: no cover
            if logger:
                logger.warning("mfb_rewards: auto_close_expired failed: %s", e)

    async def _rebuild_short():
        try:
            for period in ("weekly", "monthly"):
                for cat in _analytics.CATEGORIES:
                    await _analytics.rebuild_leaderboard(db, period, cat)
        except Exception as e:                      # pragma: no cover
            if logger:
                logger.warning("mfb_rewards: rebuild leaderboards failed: %s", e)

    async def _rebuild_all():
        try:
            await _analytics.rebuild_all(db)
        except Exception as e:                      # pragma: no cover
            if logger:
                logger.warning("mfb_rewards: rebuild_all failed: %s", e)

    sched.add_job(_close_expired, "interval", minutes=5, id="mfb_close_expired", replace_existing=True)
    sched.add_job(_rebuild_short, "interval", minutes=15, id="mfb_lb_short", replace_existing=True)
    sched.add_job(_rebuild_all,   "interval", hours=1,   id="mfb_lb_full",  replace_existing=True)

    sched.start()
    _SCHED = sched
    if logger:
        logger.info("mfb_rewards scheduler started (3 jobs)")


async def stop(*, logger=None) -> None:
    global _SCHED
    if _SCHED is None:
        return
    try:
        _SCHED.shutdown(wait=False)
    except Exception:                              # pragma: no cover
        pass
    _SCHED = None
    if logger:
        logger.info("mfb_rewards scheduler stopped")
