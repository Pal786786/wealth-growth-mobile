"""Provider abstraction for bank penny-drop verification.

Two implementations:
  * `DemoProvider` — deterministic mock used for tests + when Cashfree keys
    are missing. Passes for IFSC prefix != `FAIL` and account_number != 000...
  * `CashfreeProvider` — real Cashfree Bank Verification API. Config comes
    from the admin panel and is stored in `bank_verification_config`.

Auto-switch: if the configured provider fails to initialise (bad creds,
network error) we fall back to DemoProvider automatically so the app
remains usable in dev.
"""
from __future__ import annotations
import logging
import os
import random
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("bank_verification.providers")


class BVProviderBase:
    name = "base"
    real = False

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg or {}

    def is_configured(self) -> bool:
        return True

    async def verify(self, *, account_number: str, ifsc: str, holder_name: str) -> Dict[str, Any]:
        raise NotImplementedError


class DemoProvider(BVProviderBase):
    name = "demo"
    real = False

    async def verify(self, *, account_number: str, ifsc: str, holder_name: str) -> Dict[str, Any]:
        # Deterministic behaviour for tests
        acct = (account_number or "").strip()
        if acct.startswith("000") or ifsc.upper().startswith("FAIL"):
            return {
                "ok": False,
                "status": "failed",
                "reason": "Account inactive or does not exist (demo)",
                "matched_name": None,
                "name_match_score": 0,
                "reference_id": "demo_" + acct[-6:],
                "provider": self.name,
                "raw": {"provider": self.name, "demo": True},
            }
        # Simulate a slight name-match variance
        rnd = random.Random(hash(acct) & 0xFFFFFFFF)
        matched = (holder_name or "").strip().upper()
        score = 100 if matched else 90
        # Occasionally lower score
        if rnd.random() < 0.1: score = 85
        return {
            "ok": True,
            "status": "verified",
            "reason": None,
            "matched_name": matched,
            "name_match_score": score,
            "reference_id": "demo_" + acct[-6:] + "_" + ifsc[-4:],
            "provider": self.name,
            "raw": {"provider": self.name, "demo": True, "amount": 1.0},
        }


class CashfreeProvider(BVProviderBase):
    """Cashfree Payments — Bank Account Verification (Penny Drop).

    Uses the /verification/bank-account/async endpoint. Requires client_id +
    client_secret from the Cashfree dashboard. See
    https://docs.cashfree.com/docs/bank-account-verification for API details.
    """
    name = "cashfree"
    real = True
    BASE_URL_PROD = "https://api.cashfree.com"
    BASE_URL_SANDBOX = "https://sandbox.cashfree.com"

    def is_configured(self) -> bool:
        return bool(self.cfg.get("client_id") and self.cfg.get("client_secret"))

    def _base(self) -> str:
        env = (self.cfg.get("env") or "sandbox").lower()
        return self.BASE_URL_PROD if env == "production" else self.BASE_URL_SANDBOX

    async def verify(self, *, account_number: str, ifsc: str, holder_name: str) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Cashfree not configured — client_id / client_secret missing")
        url = f"{self._base()}/verification/bank-account/sync"
        headers = {
            "x-client-id": self.cfg["client_id"],
            "x-client-secret": self.cfg["client_secret"],
            "x-api-version": "2023-08-01",
            "Content-Type": "application/json",
        }
        payload = {
            "bank_account": account_number,
            "ifsc": ifsc.upper(),
            "name": holder_name,
            "phone": self.cfg.get("dummy_phone", "9999999999"),
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                r = await c.post(url, json=payload, headers=headers)
                data = r.json()
        except Exception as e:
            logger.warning("cashfree api failed: %s", e)
            return {
                "ok": False, "status": "error", "reason": f"provider error: {e}",
                "provider": self.name, "raw": {"exception": str(e)},
                "matched_name": None, "name_match_score": 0, "reference_id": None,
            }
        # Cashfree returns account_status: VALID / INVALID / RECEIVED (pending)
        account_status = (data.get("account_status") or "").upper()
        name_at_bank = data.get("name_at_bank") or data.get("beneficiary_name")
        ok = account_status == "VALID"
        name_match_score = 100 if (name_at_bank and holder_name and
                                     name_at_bank.strip().upper() ==
                                     holder_name.strip().upper()) else 80 if name_at_bank else 0
        return {
            "ok": ok,
            "status": "verified" if ok else (account_status.lower() or "failed"),
            "reason": data.get("account_status_code") or data.get("message"),
            "matched_name": name_at_bank,
            "name_match_score": name_match_score,
            "reference_id": str(data.get("reference_id") or ""),
            "provider": self.name,
            "raw": data,
        }


REGISTRY = ["demo", "cashfree"]


def get_provider(name: str, cfg: Dict[str, Any]) -> BVProviderBase:
    if (name or "demo").lower() == "cashfree": return CashfreeProvider(cfg)
    return DemoProvider(cfg)


def resolve_provider(cfg: Dict[str, Any]) -> BVProviderBase:
    """Return the configured provider, falling back to demo if not configured."""
    chosen = get_provider(cfg.get("provider") or "demo", cfg)
    if chosen.is_configured():
        return chosen
    if chosen.name != "demo":
        logger.warning("provider %s not configured, falling back to demo", chosen.name)
    return DemoProvider(cfg)
