"""Bank Account Verification — Sprint 12.1

Adds Cashfree Penny Drop bank verification without touching the existing
`withdrawal_module.py` bank-accounts CRUD. This module ONLY provides:

  * Provider abstraction (Demo + Cashfree)
  * User endpoint: verify a bank account via penny-drop
  * User endpoint: set / list / remove primary bank account
  * Admin endpoints: read/write Cashfree config + connection test + verification history

Business rule reminder: bank verification is only required at withdrawal time.
Signup, deposit, trading, gold, MF do NOT need a verified bank account.
"""
from __future__ import annotations
import logging
from .engine import BankVerificationEngine
from .routes import attach as _attach

logger = logging.getLogger("bank_verification")


def attach(app, db, get_current_user, get_current_admin):
    engine = BankVerificationEngine(db)
    _attach(app, db, get_current_user, get_current_admin, engine)

    async def _startup():
        try:
            await engine.init_config()
            await engine.ensure_indexes()
            logger.info("bank_verification attached (Sprint 12.1) provider=%s",
                        engine.config.get("provider"))
        except Exception as e:
            logger.exception("bank_verification startup failed: %s", e)

    app.add_event_handler("startup", _startup)
    return None


__all__ = ["attach"]
