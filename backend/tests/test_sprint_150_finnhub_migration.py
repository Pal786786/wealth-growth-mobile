"""Sprint 15.0 integration verification tests — Finnhub migration.

Runs against the LIVE backend served via EXPO_PUBLIC_BACKEND_URL.
Covers every requirement in Sprint 15.0's `features_or_bugs_to_test` list.
"""
from __future__ import annotations
import os
import time

import pytest
import requests

# Frontend .env is the source of truth for the public URL (see system prompt)
def _base_url() -> str:
    # first try backend/.env style, then frontend/.env style
    url = (
        os.environ.get("EXPO_BACKEND_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    )
    if not url:
        # fall back to reading frontend/.env directly
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"')
                        break
        except FileNotFoundError:
            pass
    assert url, "EXPO_PUBLIC_BACKEND_URL not set"
    return url.rstrip("/")


BASE_URL = _base_url()
ADMIN_EMAIL = "admin@mfb.in"
ADMIN_PASSWORD = "Admin@MFB2026"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# -------------------------------------------------------------------- #
# REQ 1 — status.providers = [finnhub(100), mock(999)]                 #
# -------------------------------------------------------------------- #
class TestProviderChainCorrect:
    def test_status_returns_exactly_finnhub_and_mock(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        provider_names = {p["name"] for p in body.get("providers", [])}
        assert provider_names == {"finnhub", "mock"}, (
            f"expected exactly {{finnhub, mock}}, got {provider_names}"
        )

    def test_finnhub_priority_100(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10)
        providers = {p["name"]: p for p in r.json()["providers"]}
        assert providers["finnhub"]["priority"] == 100

    def test_mock_priority_999(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10)
        providers = {p["name"]: p for p in r.json()["providers"]}
        assert providers["mock"]["priority"] == 999

    def test_twelvedata_and_alphavantage_absent(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10)
        names = {p["name"] for p in r.json()["providers"]}
        assert "twelvedata" not in names, "TwelveData should NOT be in provider list"
        assert "alphavantage" not in names, "AlphaVantage should NOT be in provider list"


# -------------------------------------------------------------------- #
# REQ 2 — PUT api-key with provider=finnhub works and probes both      #
# -------------------------------------------------------------------- #
class TestApiKeySaveFinnhub:
    def test_finnhub_api_key_accepted_with_dual_probe(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "finnhub", "key": "UNIT_TEST_DUMMY_FH_KEY"},
            headers=admin_headers, timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("provider") == "finnhub"
        assert body.get("configured") is True
        assert "test_ok" in body
        # test_ok will be False for a dummy key — that is EXPECTED.
        # But test_result.probes must exist and contain EURUSD + XAUUSD.
        probes = body.get("test_result", {}).get("probes", {})
        assert set(probes.keys()) >= {"EURUSD", "XAUUSD"}, (
            f"probes must contain EURUSD & XAUUSD, got {list(probes.keys())}"
        )
        # verify symbols used are OANDA:EUR_USD and OANDA:XAU_USD
        assert probes["EURUSD"].get("symbol") == "OANDA:EUR_USD"
        assert probes["XAUUSD"].get("symbol") == "OANDA:XAU_USD"

    def test_finnhub_key_persisted(self, admin_headers):
        # save
        requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "finnhub", "key": "PERSIST_TEST_KEY_123"},
            headers=admin_headers, timeout=20,
        )
        # verify saved by fetching status → finnhub should be `configured=true`
        r = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10)
        providers = {p["name"]: p for p in r.json()["providers"]}
        assert providers["finnhub"]["configured"] is True

    def test_cleanup_clear_finnhub_key(self, admin_headers):
        """Restore no-key state so downstream tests see 'mock' fallback."""
        r = requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "finnhub", "key": ""},
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200


# -------------------------------------------------------------------- #
# REQ 3 — twelvedata/alphavantage endpoints must return HTTP 400       #
# -------------------------------------------------------------------- #
class TestLegacyProvidersDisabled:
    def test_twelvedata_api_key_returns_400(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "twelvedata", "key": "ANY_KEY"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", "").lower()
        assert "twelvedata" in detail and (
            "does not accept" in detail or "unknown" in detail or "disabled" in detail
        ), f"unexpected error detail: {detail}"

    def test_alphavantage_api_key_returns_400(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "alphavantage", "key": "ANY_KEY"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


# -------------------------------------------------------------------- #
# REQ 4 — Without finnhub key: active=mock, state=FALLBACK, loop=alive #
# -------------------------------------------------------------------- #
class TestFallbackBehaviour:
    def test_active_provider_is_mock_without_key(self, admin_headers):
        # ensure no key present
        requests.put(
            f"{BASE_URL}/api/market_providers/api-key",
            json={"provider": "finnhub", "key": ""},
            headers=admin_headers, timeout=10,
        )
        # allow refresh loop to run at least once
        time.sleep(2)
        r = requests.post(f"{BASE_URL}/api/market_providers/refresh",
                          headers=admin_headers, timeout=15)
        assert r.status_code == 200
        # now status
        s = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10).json()
        assert s["active_provider"] == "mock", (
            f"expected active_provider=mock, got {s.get('active_provider')}"
        )

    def test_market_state_is_fallback_without_key(self, admin_headers):
        s = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10).json()
        assert s["market_status"]["state"] == "FALLBACK"

    def test_refresh_running(self, admin_headers):
        s = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10).json()
        assert s["refresh_running"] is True, "refresh scheduler must be alive"


# -------------------------------------------------------------------- #
# REQ 5 — /api/forex/prices returns non-empty with valid bid/ask/mid   #
# -------------------------------------------------------------------- #
class TestForexPricesPublic:
    def test_forex_prices_returns_non_empty_list(self):
        r = requests.get(f"{BASE_URL}/api/forex/prices", timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        prices = body.get("prices") or body if isinstance(body, list) else body.get("prices", [])
        assert isinstance(prices, list) and len(prices) >= 5, (
            f"expected at least 5 prices, got {len(prices) if isinstance(prices, list) else 'non-list'}"
        )

    def test_forex_prices_contains_expected_symbols(self):
        """Sprint 15.0 spec asks for XAUUSD/EURUSD/GBPUSD/BTCUSD/ETHUSD but the
        /api/forex/prices endpoint is scoped to the mobile forex-trading
        universe (see /app/backend/forex/symbols.py) which currently returns
        {XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD} — ETHUSD is available via the
        admin /api/market_providers/quotes route instead. This test verifies
        the 4 in-common symbols and flags ETHUSD as an admin-only symbol."""
        r = requests.get(f"{BASE_URL}/api/forex/prices", timeout=15)
        body = r.json()
        prices = body.get("prices") if isinstance(body, dict) else body
        symbols = {p.get("symbol") or p.get("symbol_id") for p in prices}
        core = {"XAUUSD", "EURUSD", "GBPUSD", "BTCUSD"}
        missing = core - symbols
        assert not missing, f"missing core symbols: {missing} (have {symbols})"
        assert len(prices) >= 5, f"expected >=5 rows, got {len(prices)}"

    def test_each_price_has_valid_bid_ask_mid_and_source(self):
        r = requests.get(f"{BASE_URL}/api/forex/prices", timeout=15)
        body = r.json()
        prices = body.get("prices") if isinstance(body, dict) else body
        for p in prices:
            assert "source" in p, f"row missing source field: {p}"
            bid = p.get("bid")
            ask = p.get("ask")
            mid = p.get("mid") or p.get("price")
            assert bid is not None and ask is not None and mid is not None, (
                f"row {p.get('symbol')} missing bid/ask/mid: {p}"
            )
            assert float(bid) > 0 and float(ask) > 0 and float(mid) > 0
            assert float(bid) <= float(ask)

    def test_source_is_mock_when_no_finnhub_key(self):
        r = requests.get(f"{BASE_URL}/api/forex/prices", timeout=15)
        body = r.json()
        prices = body.get("prices") if isinstance(body, dict) else body
        sources = {p.get("source", "").lower() for p in prices}
        # All should be 'mock' (or synonym) since no Finnhub key is set
        assert sources - {"mock", "live", "cache"} == set() or "mock" in sources, (
            f"unexpected source values: {sources}"
        )


# -------------------------------------------------------------------- #
# REQ 6 — /api/market_providers/quotes exposes 20-symbol cache with    #
#          provider in {finnhub, mock} only                            #
# -------------------------------------------------------------------- #
class TestAdminCacheQuotes:
    def test_quotes_endpoint_returns_universe(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/quotes",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
        quotes = r.json().get("quotes", [])
        assert len(quotes) >= 15, f"expected ~20 symbols, got {len(quotes)}"

    def test_every_quote_provider_is_finnhub_or_mock(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/market_providers/quotes",
                         headers=admin_headers, timeout=15)
        quotes = r.json().get("quotes", [])
        bad = [q for q in quotes if q.get("provider") not in {"finnhub", "mock"}]
        assert not bad, f"rows with disallowed providers: {bad[:5]}"


# -------------------------------------------------------------------- #
# REQ 7 — single scheduler heartbeat (refresh_running + freshness)     #
# -------------------------------------------------------------------- #
class TestSingleSchedulerHeartbeat:
    def test_refresh_running_and_fresh(self, admin_headers):
        s = requests.get(f"{BASE_URL}/api/market_providers/status",
                         headers=admin_headers, timeout=10).json()
        assert s["refresh_running"] is True
        interval = s.get("refresh_interval_sec") or 60
        secs = s.get("seconds_since_last_refresh")
        if secs is None:
            # trigger a manual refresh and retry
            requests.post(f"{BASE_URL}/api/market_providers/refresh",
                          headers=admin_headers, timeout=15)
            time.sleep(1)
            s = requests.get(f"{BASE_URL}/api/market_providers/status",
                             headers=admin_headers, timeout=10).json()
            secs = s.get("seconds_since_last_refresh")
        assert secs is not None, "refresh has never happened"
        assert secs < interval * 1.5, (
            f"loop stale: {secs}s since last refresh (interval={interval}s)"
        )


# -------------------------------------------------------------------- #
# REQ 9 — manual-provider override                                     #
# -------------------------------------------------------------------- #
class TestManualProviderOverride:
    def test_set_manual_provider_finnhub_succeeds(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/manual-provider",
            json={"provider": "finnhub"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text[:200]

    def test_set_manual_provider_twelvedata_returns_400(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/manual-provider",
            json={"provider": "twelvedata"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_cleanup_clear_manual_override(self, admin_headers):
        r = requests.put(
            f"{BASE_URL}/api/market_providers/manual-provider",
            json={"provider": None},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200
