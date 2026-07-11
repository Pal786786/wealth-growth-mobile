"""PAN verification providers.

Default: DemoPanProvider (deterministic OK unless the PAN starts with "BAD").
NSDLPanProvider: stub calling `/pan/verify` — admin plugs API key later.
"""
from __future__ import annotations
import logging
import os
import random
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("kyc_v2.providers.pan")


def pan_checksum_valid(pan: str) -> bool:
    """Sanity check: PAN pattern is 5 letters + 4 digits + 1 letter (AAAAA9999A)."""
    import re
    return bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", (pan or "").upper()))


class DemoPanProvider:
    provider = "demo"

    def is_configured(self) -> bool:
        return True

    async def verify(self, pan: str, name: Optional[str] = None,
                      dob: Optional[str] = None) -> Dict[str, Any]:
        pan = (pan or "").upper().strip()
        if not pan_checksum_valid(pan):
            return {"ok": False, "status": "invalid_format",
                    "message": "PAN format is AAAAA9999A",
                    "provider": self.provider}
        # Test bad PANs to allow negative-flow testing
        if pan.startswith("BAD"):
            return {"ok": False, "status": "not_found",
                    "message": "PAN not found in demo directory",
                    "provider": self.provider}
        # Deterministic "official" name derived from PAN so repeat verifications match
        seeded = random.Random(pan)
        first_names = ["Aarav", "Vivaan", "Aditya", "Reyansh", "Krishna",
                       "Ishaan", "Rohan", "Arjun", "Karan", "Kabir"]
        last_names = ["Sharma", "Verma", "Iyer", "Nair", "Gupta",
                      "Patel", "Reddy", "Menon", "Kumar", "Singh"]
        official = f"{seeded.choice(first_names)} {seeded.choice(last_names)}"
        name_ok = True
        if name:
            name_norm = name.strip().upper().replace(".", "").replace("  ", " ")
            off_norm = official.upper().replace(".", "")
            # Allow partial match — either first name matches or the full
            # normalised strings overlap by >= 60% of characters
            name_ok = (name_norm.split()[0] == off_norm.split()[0] or
                       (len(set(name_norm) & set(off_norm)) / max(1, len(set(off_norm)))) >= 0.6)
        return {
            "ok": True, "status": "valid", "provider": self.provider,
            "pan": pan, "official_name": official,
            "name_match": bool(name_ok),
            "category": "individual",
            "reference_id": f"demo_pan_ref_{int(time.time())}",
        }


class NSDLPanProvider:
    """Real NSDL PAN check — stubbed HTTP call. In production wire the actual
    endpoint here. Falls back to Demo behaviour if not configured."""
    provider = "nsdl"
    BASE = "https://api.nsdl.co.in/kyc-services"

    def __init__(self, api_key: Optional[str] = None):
        self._key = (api_key or os.environ.get("NSDL_PAN_API_KEY") or "").strip()

    def is_configured(self) -> bool:
        return bool(self._key and self._key != "placeholder")

    async def verify(self, pan: str, name: Optional[str] = None,
                      dob: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_configured():
            # Delegate to demo when we haven't been given credentials yet
            return await DemoPanProvider().verify(pan, name, dob)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(
                    f"{self.BASE}/pan/verify",
                    headers={"Authorization": f"Bearer {self._key}",
                             "Content-Type": "application/json"},
                    json={"pan": pan, "name": name, "dob": dob},
                )
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 200 and j.get("status") in ("valid", "active"):
                return {"ok": True, "status": "valid", "provider": self.provider,
                        "pan": pan, "official_name": j.get("name"),
                        "name_match": bool(j.get("name_match", True)),
                        "category": j.get("pan_type", "individual"),
                        "reference_id": j.get("reference_id", "")}
            return {"ok": False, "status": j.get("status", "unknown"),
                    "message": j.get("message", f"HTTP {r.status_code}"),
                    "provider": self.provider}
        except Exception as e:
            logger.warning("NSDL call failed: %s", e)
            return {"ok": False, "status": "provider_error",
                    "message": str(e), "provider": self.provider}


def get_pan_provider() -> Any:
    provider = NSDLPanProvider()
    if provider.is_configured():
        return provider
    return DemoPanProvider()
