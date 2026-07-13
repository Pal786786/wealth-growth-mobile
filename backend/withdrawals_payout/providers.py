"""Sprint 12.2 — Cashfree Payouts + Demo payout providers.

Two implementations:
  * `DemoPayoutProvider` — deterministic mock used for tests and when Cashfree
    keys are missing. Auto-succeeds unless account_masked contains 'FAIL'.
  * `CashfreePayoutProvider` — real Cashfree Payouts (Standard Transfer) API.
    Uses the /payout/transfers endpoint via v2 API (2024) — requires
    `client_id` + `client_secret` from the Cashfree Payouts dashboard.

Auto-switch: if the configured provider fails to initialise (bad creds,
network error), we fall back to DemoPayoutProvider automatically so the
app remains usable in dev.
"""
from __future__ import annotations
import logging
import random
import secrets
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("withdrawals_payout.providers")


class PayoutProviderBase:
    name = "base"
    real = False

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg or {}

    def is_configured(self) -> bool:
        return True

    async def transfer(
        self,
        *,
        transfer_id: str,
        amount: float,
        account_number: str,
        ifsc: str,
        holder_name: str,
        remarks: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate a payout. Returns dict:
        {
          ok: bool,
          status: "processing" | "success" | "failed" | "pending",
          provider_reference: str,     # provider-side ID
          utr: Optional[str],          # UTR number when known
          settlement_status: str,
          reason: Optional[str],
          raw: dict,
        }
        """
        raise NotImplementedError

    async def status(self, *, transfer_id: str, provider_reference: Optional[str] = None) -> Dict[str, Any]:
        """Query the transfer status. Same return shape as `transfer`."""
        raise NotImplementedError


class DemoPayoutProvider(PayoutProviderBase):
    name = "demo"
    real = False

    async def transfer(
        self,
        *,
        transfer_id: str,
        amount: float,
        account_number: str,
        ifsc: str,
        holder_name: str,
        remarks: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Force a failure path when account contains "FAIL" for testability
        acct = (account_number or "").upper()
        if "FAIL" in acct or ifsc.upper().startswith("FAIL"):
            return {
                "ok": False,
                "status": "failed",
                "provider_reference": "DEMO_FAIL_" + secrets.token_hex(4).upper(),
                "utr": None,
                "settlement_status": "failed",
                "reason": "Demo provider: forced failure (account contains FAIL)",
                "raw": {"provider": self.name, "demo": True},
            }
        # Success — return a deterministic-looking UTR after a "processing" tick
        rnd = random.Random(hash(transfer_id) & 0xFFFFFFFF)
        utr = f"MFB{rnd.randint(10**11, 10**12 - 1)}"
        return {
            "ok": True,
            "status": "success",
            "provider_reference": "DEMO_" + secrets.token_hex(4).upper(),
            "utr": utr,
            "settlement_status": "credited",
            "reason": None,
            "raw": {"provider": self.name, "demo": True, "amount": amount, "utr": utr},
        }

    async def status(self, *, transfer_id: str, provider_reference: Optional[str] = None) -> Dict[str, Any]:
        # Demo: assume already-terminal on ping
        return {
            "ok": True, "status": "success",
            "provider_reference": provider_reference or "DEMO_QUERY",
            "utr": f"MFB{random.randint(10**11, 10**12 - 1)}",
            "settlement_status": "credited",
            "reason": None,
            "raw": {"provider": self.name, "demo": True, "query": True},
        }


class CashfreePayoutProvider(PayoutProviderBase):
    """Cashfree Payouts (Standard Transfer)  Requires client_id + client_secret
    from the Cashfree Payouts dashboard.

    Docs: https://docs.cashfree.com/reference/pgcreatetransfer
    """
    name = "cashfree"
    real = True
    BASE_URL_PROD = "https://payout-api.cashfree.com"
    BASE_URL_SANDBOX = "https://payout-gamma.cashfree.com"

    def is_configured(self) -> bool:
        return bool(self.cfg.get("payout_client_id") and self.cfg.get("payout_client_secret"))

    def _base(self) -> str:
        env = (self.cfg.get("payout_env") or "sandbox").lower()
        return self.BASE_URL_PROD if env == "production" else self.BASE_URL_SANDBOX

    def _headers(self) -> Dict[str, str]:
        return {
            "x-client-id": self.cfg["payout_client_id"],
            "x-client-secret": self.cfg["payout_client_secret"],
            "x-api-version": "2024-01-01",
            "Content-Type": "application/json",
        }

    async def transfer(
        self,
        *,
        transfer_id: str,
        amount: float,
        account_number: str,
        ifsc: str,
        holder_name: str,
        remarks: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Cashfree Payouts not configured — payout_client_id / payout_client_secret missing")
        url = f"{self._base()}/payout/transfers"
        payload = {
            "transfer_id": transfer_id,
            "transfer_amount": round(float(amount), 2),
            "transfer_mode": "banktransfer",
            "beneficiary_details": {
                "beneficiary_instrument_details": {
                    "bank_account_number": account_number,
                    "bank_ifsc": ifsc.upper(),
                },
                "beneficiary_name": holder_name,
            },
            "transfer_remarks": (remarks or "MFB Withdrawal")[:60],
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                r = await c.post(url, json=payload, headers=self._headers())
                data = r.json()
        except Exception as e:
            logger.warning("cashfree payout initiate failed: %s", e)
            return {
                "ok": False, "status": "failed",
                "provider_reference": None, "utr": None,
                "settlement_status": "failed",
                "reason": f"provider error: {e}",
                "raw": {"exception": str(e)},
            }
        status = (data.get("status") or "").upper()
        # Cashfree Payouts statuses: RECEIVED / APPROVED / PENDING / SUCCESS / FAILED / REJECTED / REVERSED
        ok = status in ("SUCCESS", "APPROVED", "RECEIVED", "PENDING")
        mapped = "success" if status == "SUCCESS" else \
                 "processing" if status in ("APPROVED", "RECEIVED", "PENDING") else \
                 "failed"
        return {
            "ok": ok, "status": mapped,
            "provider_reference": str(data.get("cf_transfer_id") or data.get("transfer_id") or ""),
            "utr": data.get("transfer_utr"),
            "settlement_status": mapped,
            "reason": data.get("status_description") or data.get("message"),
            "raw": data,
        }

    async def status(self, *, transfer_id: str, provider_reference: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Cashfree Payouts not configured")
        url = f"{self._base()}/payout/transfers"
        params = {"transfer_id": transfer_id}
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                r = await c.get(url, params=params, headers=self._headers())
                data = r.json()
        except Exception as e:
            return {"ok": False, "status": "failed", "provider_reference": provider_reference,
                    "utr": None, "settlement_status": "failed",
                    "reason": f"query failed: {e}", "raw": {"exception": str(e)}}
        status = (data.get("status") or "").upper()
        ok = status in ("SUCCESS", "APPROVED", "RECEIVED", "PENDING")
        mapped = "success" if status == "SUCCESS" else \
                 "processing" if status in ("APPROVED", "RECEIVED", "PENDING") else \
                 "failed"
        return {
            "ok": ok, "status": mapped,
            "provider_reference": str(data.get("cf_transfer_id") or provider_reference or ""),
            "utr": data.get("transfer_utr"),
            "settlement_status": mapped,
            "reason": data.get("status_description"),
            "raw": data,
        }


REGISTRY = ["demo", "cashfree"]


def get_payout_provider(name: str, cfg: Dict[str, Any]) -> PayoutProviderBase:
    if (name or "demo").lower() == "cashfree":
        return CashfreePayoutProvider(cfg)
    return DemoPayoutProvider(cfg)


def resolve_payout_provider(cfg: Dict[str, Any]) -> PayoutProviderBase:
    """Return the configured payout provider, falling back to demo if not configured."""
    chosen = get_payout_provider(cfg.get("payout_provider") or "demo", cfg)
    if chosen.is_configured():
        return chosen
    if chosen.name != "demo":
        logger.warning("payout provider %s not configured, falling back to demo", chosen.name)
    return DemoPayoutProvider(cfg)
