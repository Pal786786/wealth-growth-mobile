"""
MFB Rewards & Ecosystem — Internal Token Platform
===================================================
Sprint 14 self-contained module. Provides an internal (non-blockchain)
reward asset called "MFB Token" with a fully featured gamification stack:

    • Reward wallet (balance, lifetime XP, level, tier, streak)
    • Reward engine (idempotent award() + admin-configurable rules)
    • Referral system with QR codes
    • Daily login streak
    • Achievements & badges
    • Campaign engine (admin CRUD)
    • Leaderboards (weekly/monthly/all-time × 4 categories)
    • Analytics + APScheduler-driven refresh
    • Migration-ready schema (internal_token_id / future_blockchain_id / migration_status)

Usage from server.py::

    import mfb_rewards
    mfb_rewards.attach(api, app, db=db,
                       get_current_user=get_current_user,
                       get_current_admin=admin_module.get_current_admin,
                       logger=logger)
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

from . import wallet, engine, referrals, campaigns, achievements, analytics, scheduler, routes  # noqa: F401

__all__ = ["attach", "engine", "wallet", "referrals", "campaigns", "achievements", "analytics"]


def attach(api: APIRouter, app: FastAPI, *, db, get_current_user, get_current_admin, logger=None) -> None:
    """Wire the MFB Rewards module into an existing FastAPI application."""
    ctx = engine.Context(db=db, logger=logger)
    engine.set_context(ctx)

    routes.attach(api, db=db, get_current_user=get_current_user,
                  get_current_admin=get_current_admin, logger=logger)

    # Kick off background tasks after startup
    @app.on_event("startup")
    async def _mfb_rewards_startup():   # noqa: D401
        await wallet.seed_default_settings(db)
        await scheduler.start(db, logger=logger)
        if logger:
            logger.info("mfb_rewards attached (v1.0)")

    @app.on_event("shutdown")
    async def _mfb_rewards_shutdown():
        await scheduler.stop(logger=logger)
