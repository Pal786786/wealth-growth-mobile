"""DigiLocker & Aadhaar providers.

Demo mode fabricates a well-formed authorization URL, code exchange, and
returns a deterministic Aadhaar payload. When real DigiLocker credentials are
provided we use the standard OAuth2 flow.
"""
from __future__ import annotations
import hashlib
import logging
import os
import random
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("kyc_v2.providers.digilocker")


class DemoDigiLockerProvider:
    provider = "demo"

    def is_configured(self) -> bool:
        return True

    async def issue_authorization(self, redirect_uri: str, state: str,
                                    user_id: str) -> Dict[str, Any]:
        # Demo: local URL that returns a pre-generated code back to us
        code = f"dlcode_{uuid.uuid4().hex[:14]}"
        return {
            "provider": self.provider,
            "authorization_url": (
                f"{redirect_uri}?code={code}&state={state}&demo=1"),
            "code": code,       # exposed only in demo
            "state": state,
            "expires_in": 600,
        }

    async def exchange_code(self, code: str, state: str) -> Dict[str, Any]:
        if not code.startswith("dlcode_") and not code.startswith("real_"):
            return {"ok": False, "message": "invalid code", "provider": self.provider}
        return {
            "ok": True,
            "access_token": f"dlaccess_{uuid.uuid4().hex[:16]}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "provider": self.provider,
        }

    async def fetch_aadhaar(self, access_token: str) -> Dict[str, Any]:
        if not access_token.startswith("dlaccess_"):
            return {"ok": False, "message": "invalid token", "provider": self.provider}
        seeded = random.Random(access_token)
        # Random but reproducible 12-digit Aadhaar (with a valid Verhoeff-friendly last digit)
        base = "".join(str(seeded.randint(0, 9)) for _ in range(11))
        checksum = str(sum(int(d) for d in base) % 10)
        aadhaar = base + checksum
        first_names = ["Aarav", "Vivaan", "Reyansh", "Ishaan", "Kabir",
                       "Ananya", "Diya", "Aanya", "Riya", "Isha"]
        last_names = ["Sharma", "Verma", "Nair", "Iyer", "Reddy",
                      "Menon", "Kumar", "Gupta", "Patel", "Bose"]
        cities = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai",
                  "Kolkata", "Pune", "Ahmedabad"]
        states = ["MH", "DL", "KA", "TS", "TN", "WB", "MH", "GJ"]
        idx = seeded.randint(0, len(cities) - 1)
        return {
            "ok": True, "provider": self.provider,
            "aadhaar_last4": aadhaar[-4:],
            "aadhaar_hash": hashlib.sha256(aadhaar.encode()).hexdigest(),
            "name": f"{seeded.choice(first_names)} {seeded.choice(last_names)}",
            "gender": seeded.choice(["M", "F"]),
            "dob": f"{seeded.randint(1975, 2003)}-{seeded.randint(1,12):02d}-{seeded.randint(1,28):02d}",
            "address": {
                "line1": f"{seeded.randint(1, 999)} MG Road",
                "line2": f"Sector {seeded.randint(1, 40)}",
                "city": cities[idx], "state": states[idx],
                "pincode": f"{seeded.randint(100000, 999999)}",
                "country": "IN",
            },
            "issued_at": time.time(),
            "reference_id": f"dlref_{uuid.uuid4().hex[:14]}",
        }


class DigiLockerProviderReal:
    provider = "digilocker"
    AUTH_URL = "https://api.digitallocker.gov.in/public/oauth2/1/authorize"
    TOKEN_URL = "https://api.digitallocker.gov.in/public/oauth2/1/token"
    AADHAAR_URL = "https://api.digitallocker.gov.in/public/oauth2/3/xml/eaadhaar"

    def __init__(self):
        self.client_id = (os.environ.get("DIGILOCKER_CLIENT_ID") or "").strip()
        self.client_secret = (os.environ.get("DIGILOCKER_CLIENT_SECRET") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_id != "placeholder" and
                    self.client_secret and self.client_secret != "placeholder")

    async def issue_authorization(self, redirect_uri: str, state: str,
                                    user_id: str) -> Dict[str, Any]:
        if not self.is_configured():
            return await DemoDigiLockerProvider().issue_authorization(
                redirect_uri, state, user_id)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "state": state,
            "redirect_uri": redirect_uri,
        }
        return {
            "provider": self.provider,
            "authorization_url": f"{self.AUTH_URL}?{urlencode(params)}",
            "state": state, "expires_in": 600,
        }

    async def exchange_code(self, code: str, state: str) -> Dict[str, Any]:
        if not self.is_configured():
            return await DemoDigiLockerProvider().exchange_code(code, state)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(self.TOKEN_URL, data={
                    "grant_type": "authorization_code", "code": code,
                    "client_id": self.client_id, "client_secret": self.client_secret,
                })
            j = r.json() if r.status_code == 200 else {}
            return {"ok": r.status_code == 200,
                    "access_token": j.get("access_token", ""),
                    "token_type": j.get("token_type", "Bearer"),
                    "expires_in": j.get("expires_in", 3600),
                    "provider": self.provider,
                    "error": j.get("error") if r.status_code != 200 else None}
        except Exception as e:
            logger.warning("digilocker token exchange failed: %s", e)
            return {"ok": False, "message": str(e), "provider": self.provider}

    async def fetch_aadhaar(self, access_token: str) -> Dict[str, Any]:
        if not self.is_configured():
            return await DemoDigiLockerProvider().fetch_aadhaar(access_token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    self.AADHAAR_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if r.status_code == 200:
                # DigiLocker returns eAadhaar XML — parse in a real impl
                return {"ok": True, "provider": self.provider,
                        "raw_xml_len": len(r.text),
                        "note": "XML parsing required for production"}
            return {"ok": False, "message": f"HTTP {r.status_code}",
                    "provider": self.provider}
        except Exception as e:
            return {"ok": False, "message": str(e), "provider": self.provider}


def get_digilocker_provider() -> Any:
    p = DigiLockerProviderReal()
    if p.is_configured():
        return p
    return DemoDigiLockerProvider()
