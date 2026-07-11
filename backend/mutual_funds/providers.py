"""Mutual-fund NAV / catalog provider abstraction.

We deliberately keep the interface small — every provider only needs to
expose `list_funds()` and `nav(scheme_code)`. The engine handles all
downstream business logic (orders, SIPs, portfolio) so switching providers
is trivial.

Auto-fallback chain: chosen → amfi → mock.
"""
from __future__ import annotations
import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("mutual_funds.providers")


class MFProviderBase:
    name = "base"
    real = False

    def __init__(self, db):
        self.db = db

    def is_configured(self) -> bool:
        return True

    async def list_funds(self) -> List[Dict[str, Any]]:
        return []

    async def nav(self, scheme_code: str) -> Optional[float]:
        return None


class MockMFProvider(MFProviderBase):
    """Simulated feed — used by the seed. Returns latest NAV from DB."""
    name = "mock"
    real = False

    async def list_funds(self) -> List[Dict[str, Any]]:
        cur = self.db.mf_funds.find({}, {"_id": 0}).limit(200)
        return [d async for d in cur]

    async def nav(self, scheme_code: str) -> Optional[float]:
        f = await self.db.mf_funds.find_one({"scheme_code": scheme_code},
                                            {"_id": 0, "current_nav": 1})
        return float(f.get("current_nav")) if f and f.get("current_nav") else None


class AMFIProvider(MFProviderBase):
    """AMFI daily NAV feed (free & public). https://www.amfiindia.com/nav-history-download

    Only used when explicitly enabled; otherwise mock is used to keep tests hermetic.
    """
    name = "amfi"
    real = True
    URL = "https://www.amfiindia.com/spages/NAVAll.txt"

    def is_configured(self) -> bool:
        return os.getenv("AMFI_ENABLED", "").lower() in ("1", "true", "yes")

    async def fetch(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(self.URL)
                r.raise_for_status()
                for line in r.text.splitlines():
                    parts = line.split(";")
                    # code;isin1;isin2;scheme_name;nav;date
                    if len(parts) < 6:
                        continue
                    code, _, _, _, nav, _ = parts[:6]
                    if not code.strip().isdigit():
                        continue
                    try:
                        out[code.strip()] = float(nav)
                    except ValueError:
                        pass
        except Exception as e:
            logger.warning("AMFI fetch failed: %s", e)
        return out

    async def nav(self, scheme_code: str) -> Optional[float]:
        m = await self.fetch()
        return m.get(scheme_code)


class CAMSProvider(MFProviderBase):
    name = "cams"
    real = True
    def is_configured(self) -> bool: return bool(os.getenv("CAMS_API_KEY"))


class KFintechProvider(MFProviderBase):
    name = "kfintech"
    real = True
    def is_configured(self) -> bool: return bool(os.getenv("KFINTECH_API_KEY"))


class MFCentralProvider(MFProviderBase):
    name = "mf_central"
    real = True
    def is_configured(self) -> bool: return bool(os.getenv("MF_CENTRAL_API_KEY"))


PROVIDER_REGISTRY = ["mock", "amfi", "cams", "kfintech", "mf_central"]


def get_provider(db, name: str) -> MFProviderBase:
    n = (name or "mock").lower()
    if n == "amfi": return AMFIProvider(db)
    if n == "cams": return CAMSProvider(db)
    if n == "kfintech": return KFintechProvider(db)
    if n == "mf_central": return MFCentralProvider(db)
    return MockMFProvider(db)
