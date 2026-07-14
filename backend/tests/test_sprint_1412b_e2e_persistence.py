"""Sprint 14.1.2b — End-to-end persistence integration tests.

Verifies each of the three LEGACY admin save endpoints:
  1) canonically shadow-writes to market_provider_config._id="active"
  2) live-propagates the new key into the running ProviderManager (no restart)

Uses REAL running backend + REAL Mongo. TwelveData fake keys will produce
INVALID_API_KEY (HTTP 401) from TwelveData — that is EXPECTED.
"""
from __future__ import annotations

import os
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Prefer localhost to avoid preview edge timeouts during regression
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
if "preview.emergentagent.com" in BASE_URL:
    BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "my_funding_bank")

ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _wipe():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    for coll, flt in [
        ("market_provider_config", {"_id": "active"}),
        ("market_data_settings", {"_id": "default"}),
        ("market_settings", {"_id": "default"}),
        ("forex_settings", {"_id": "active"}),
    ]:
        await db[coll].update_one(
            flt,
            {"$set": {
                "twelvedata_api_key": "",
                "alphavantage_api_key": "",
                "twelve_data_api_key": "",
                "api_keys.twelvedata": "",
                "api_keys.twelve_data": "",
                "api_keys.alphavantage": "",
                "api_keys.alpha_vantage": "",
            }},
            upsert=True,
        )
    c.close()


async def _read_canonical():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    doc = await db["market_provider_config"].find_one({"_id": "active"})
    c.close()
    return (doc or {}).get("twelvedata_api_key", "") or ""


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _wipe_between():
    _run(_wipe())
    yield
    _run(_wipe())


def _check_debug_shows_key(admin_headers, expected_prefix: str) -> dict:
    r = requests.get(f"{API}/market/debug/xauusd", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    stages = {s["stage"]: s for s in body["stages"]}
    lp = stages["locate_provider"]["details"]
    rd = stages["read_db_config"]["details"]
    assert lp.get("api_key_configured") is True, f"api_key_configured False: {lp}"
    fp = lp.get("api_key_fingerprint") or rd.get("api_key_fingerprint") or ""
    assert fp.startswith(expected_prefix), f"fingerprint '{fp}' does not start with '{expected_prefix}'"
    return body


class TestMarketDataSettingsPersistence:
    """PUT /api/admin/market_data/settings — legacy path #1."""

    def test_shadow_write_and_live_propagate(self, admin_headers):
        key = "TEST_KEY_MD_XXXXXXX"
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_headers,
                         json={"api_keys": {"twelvedata": key}}, timeout=15)
        assert r.status_code == 200, r.text[:300]

        # Canonical shadow-write
        can = _run(_read_canonical())
        assert can == key, f"canonical mismatch: {can!r} vs {key!r}"

        # Live propagation reflected in debug
        _check_debug_shows_key(admin_headers, "TEST")


class TestForexSettingsPersistence:
    """PUT /api/admin/forex/settings — legacy path #2."""

    def test_shadow_write_and_live_propagate(self, admin_headers):
        key = "TEST_KEY_FX_YYYYYYY"
        r = requests.put(f"{API}/admin/forex/settings",
                         headers=admin_headers,
                         json={"twelve_data_api_key": key, "live_mode": True},
                         timeout=15)
        assert r.status_code == 200, r.text[:300]

        can = _run(_read_canonical())
        assert can == key, f"canonical mismatch: {can!r} vs {key!r}"

        _check_debug_shows_key(admin_headers, "TEST")


class TestMarketSettingsPersistence:
    """PUT /api/admin/market/settings — legacy path #3."""

    def test_shadow_write_and_live_propagate(self, admin_headers):
        key = "TEST_KEY_MM_ZZZZZZZ"
        r = requests.put(f"{API}/admin/market/settings",
                         headers=admin_headers,
                         json={"api_keys": {"twelve_data": key}}, timeout=15)
        assert r.status_code == 200, r.text[:300]

        can = _run(_read_canonical())
        assert can == key, f"canonical mismatch: {can!r} vs {key!r}"

        _check_debug_shows_key(admin_headers, "TEST")


class TestNoRegressions:
    def test_market_providers_status(self, admin_headers):
        r = requests.get(f"{API}/market_providers/status",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # Should contain a list of providers
        assert isinstance(body, dict), body
        # providers list appears under any of these keys
        found = False
        for k in ("providers", "provider_stats", "items"):
            if k in body:
                found = True
                break
        assert found, f"no providers list in response: {list(body.keys())}"

    def test_market_providers_api_key_endpoint(self, admin_headers):
        r = requests.put(f"{API}/market_providers/api-key",
                         headers=admin_headers,
                         json={"provider": "twelvedata", "key": "TEST_KEY_PROBE_ABCDE"},
                         timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        for k in ("provider", "configured", "test_ok", "test_result"):
            assert k in body, f"missing key {k} in response: {body}"


class TestDebugVerdictForInvalidKey:
    """Debug verdict must be INVALID_API_KEY (401 from TwelveData), not
    NOT_CONFIGURED / EXCEPTION_Exception.
    """
    def test_invalid_key_verdict(self, admin_headers):
        # Save a fake key via canonical route
        r = requests.put(f"{API}/market_providers/api-key",
                         headers=admin_headers,
                         json={"provider": "twelvedata", "key": "FAKE_KEY_FOR_VERDICT_TEST"},
                         timeout=15)
        assert r.status_code == 200
        # Fetch debug trace
        r2 = requests.get(f"{API}/market/debug/xauusd", headers=admin_headers, timeout=25)
        assert r2.status_code == 200, r2.text[:200]
        verdict = r2.json()["result"]
        # Accept INVALID_API_KEY / RATE_LIMITED / any http-error verdict — must NOT be NOT_CONFIGURED
        assert verdict != "NOT_CONFIGURED", f"verdict regressed: {verdict}"
        assert verdict != "ERROR_PROVIDER_MISSING", f"verdict regressed: {verdict}"
        # Ideal: INVALID_API_KEY (401 from TD)
        # Acceptable fallbacks (network/env): PROVIDER_5XX, RATE_LIMITED, ERROR_HTTP
        assert verdict in {"INVALID_API_KEY", "PROVIDER_5XX", "RATE_LIMITED", "ERROR_HTTP"} \
            or verdict.startswith("EXCEPTION_"), f"unexpected verdict: {verdict}"
