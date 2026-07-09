"""Sprint 7 Slice 1 - Iter22 P1 retest.

Focus: PUT /api/admin/market_data/settings now accepts JSON body
(after moving AdminSettings to module scope + `Body(...)` marker).
"""
import os
import requests
import pytest

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://wealth-growth-mobile.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_hdrs():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


class TestAdminPutRetest:
    def test_put_interval_seconds_two(self, admin_hdrs):
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_hdrs,
                         json={"interval_seconds": 2}, timeout=10)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert body["settings"]["interval_seconds"] == 2

    def test_put_switch_provider_twelvedata_with_fake_key(self, admin_hdrs):
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_hdrs,
                         json={"provider": "twelvedata",
                               "api_keys": {"twelvedata": "FAKE_KEY"}},
                         timeout=10)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        s = r.json()["settings"]
        assert s["provider"] == "twelvedata"
        assert s["api_keys"]["twelvedata"] == "FAKE_KEY"

    def test_quote_with_fake_twelvedata_key_must_not_500(self):
        r = requests.get(f"{API}/market_data/quote/XAUUSD", timeout=15)
        assert r.status_code in (200, 404, 503), (
            f"quote returned {r.status_code} (must not 500): {r.text}"
        )

    def test_put_reset_to_mock(self, admin_hdrs):
        r = requests.put(f"{API}/admin/market_data/settings",
                         headers=admin_hdrs,
                         json={"provider": "mock",
                               "transport": "polling",
                               "interval_seconds": 3,
                               "api_keys": {"twelvedata": ""}},
                         timeout=10)
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["provider"] == "mock"
        assert s["transport"] == "polling"
        assert s["interval_seconds"] == 3

    def test_final_status_restored(self, admin_hdrs):
        r = requests.get(f"{API}/admin/market_data/status",
                         headers=admin_hdrs, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["catalog_size"] == 96
        assert d["provider_health"]["ok"] is True
        assert d["settings"]["provider"] == "mock"
        assert d["settings"]["interval_seconds"] == 3
        # Quote back to mock source
        rq = requests.get(f"{API}/market_data/quote/XAUUSD", timeout=10)
        assert rq.status_code == 200
        assert rq.json()["source"] == "mock"
