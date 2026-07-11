"""KYC v2 — Sprint 9 (Real KYC Platform)

Extends the existing `kyc_module.py` with a pluggable Provider abstraction so
real APIs (NSDL PAN, DigiLocker Aadhaar, Karza, Signzy …) can be swapped in
without touching business logic.

Collections (new, additive):
  * kyc_verifications   — per-check results (PAN, Aadhaar, DigiLocker, Face)
  * kyc_gating_events   — audit trail for gate decisions
"""
from __future__ import annotations
import logging

from .routes import attach as _attach_routes
from .gating import require_kyc_for, is_kyc_gated_action

logger = logging.getLogger("kyc_v2")


def attach(app, db, get_current_user, get_current_admin):
    _attach_routes(app, db, get_current_user, get_current_admin)
    logger.info("kyc_v2 subsystem attached (Sprint 9)")


__all__ = ["attach", "require_kyc_for", "is_kyc_gated_action"]
