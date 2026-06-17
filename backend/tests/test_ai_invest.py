"""Tests for the AI Investment Suggestions feature (Claude Sonnet 4.6 via Emergent LLM key).

Endpoint under test: GET /api/invest/ai-suggestions
"""
import time
import pytest
import requests


# ---------------- AI suggestions feature ----------------
class TestAiSuggestions:
    def test_requires_auth(self, api_base):
        r = requests.get(f"{api_base}/invest/ai-suggestions")
        assert r.status_code == 401, f"expected 401 got {r.status_code} body={r.text[:200]}"

    def test_first_call_returns_full_payload_live(self, api_base, demo_headers):
        # Force-bypass cache for the first run so we always hit the LLM path
        r = requests.get(
            f"{api_base}/invest/ai-suggestions?refresh=true",
            headers=demo_headers,
            timeout=60,
        )
        assert r.status_code == 200, f"got {r.status_code} body={r.text[:300]}"
        body = r.json()
        # Schema checks
        for k in ("overall_summary", "risk_score", "risk_label", "recommendations",
                  "next_steps", "disclaimer", "mode", "generated_at"):
            assert k in body, f"missing key {k}"
        assert "suggested_sip" in body  # may be null
        assert body["cached"] is False
        assert isinstance(body["risk_score"], int)
        assert 1 <= body["risk_score"] <= 5
        assert body["risk_label"] in {"Conservative", "Moderate", "Balanced", "Growth", "Aggressive"}
        assert isinstance(body["recommendations"], list)
        assert isinstance(body["next_steps"], list)
        assert body["mode"] in {"live", "demo"}
        # With EMERGENT_LLM_KEY configured we expect live mode
        assert body["mode"] == "live", f"expected 'live' mode but got '{body['mode']}'"

    def test_second_call_returns_cached_fast(self, api_base, demo_headers):
        # First call to ensure cache is warm (no refresh)
        requests.get(f"{api_base}/invest/ai-suggestions", headers=demo_headers, timeout=60)
        t0 = time.time()
        r = requests.get(f"{api_base}/invest/ai-suggestions", headers=demo_headers, timeout=10)
        elapsed_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        body = r.json()
        assert body["cached"] is True, f"expected cached=True body keys={list(body)[:8]}"
        assert elapsed_ms < 1500, f"cached response too slow: {elapsed_ms:.0f}ms"

    def test_refresh_true_bypasses_cache(self, api_base, demo_headers):
        # Get current generated_at
        r1 = requests.get(f"{api_base}/invest/ai-suggestions", headers=demo_headers, timeout=60)
        assert r1.status_code == 200
        first_gen = r1.json().get("generated_at")
        # Wait briefly so timestamps differ
        time.sleep(1.1)
        r2 = requests.get(
            f"{api_base}/invest/ai-suggestions?refresh=true",
            headers=demo_headers,
            timeout=60,
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["cached"] is False
        assert body["generated_at"] != first_gen, "generated_at must be fresh on refresh"


# ---------------- Regression: existing endpoints still work ----------------
class TestExistingEndpointsRegression:
    def test_login(self, api_base):
        r = requests.post(
            f"{api_base}/auth/login",
            json={"identifier": "demo@mfb.in", "password": "demo1234"},
            timeout=15,
        )
        assert r.status_code == 200
        assert "token" in r.json()

    def test_dashboard_summary(self, api_base, demo_headers):
        r = requests.get(f"{api_base}/dashboard/summary", headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]

    def test_invest_stocks(self, api_base):
        r = requests.get(f"{api_base}/invest/stocks", timeout=20)
        assert r.status_code == 200
        body = r.json()
        # response may be a list directly or object with key — accept either
        if isinstance(body, dict):
            assert "stocks" in body or "data" in body or "items" in body, list(body.keys())
        else:
            assert isinstance(body, list)

    def test_invest_portfolio(self, api_base, demo_headers):
        r = requests.get(f"{api_base}/invest/portfolio", headers=demo_headers, timeout=15)
        assert r.status_code == 200

    def test_wallet(self, api_base, demo_headers):
        r = requests.get(f"{api_base}/wallet", headers=demo_headers, timeout=15)
        assert r.status_code == 200

    def test_api_status_public(self, api_base):
        r = requests.get(f"{api_base}/app/api-status", timeout=15)
        assert r.status_code == 200
        body = r.json()
        # Should not leak api_key fields
        for itm in body.get("integrations", body.get("items", [])) or []:
            assert "api_key" not in itm
            assert "api_key_masked" not in itm
