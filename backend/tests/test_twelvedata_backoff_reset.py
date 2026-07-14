"""Bug-fix regression — TwelveData provider api-key rotation & backoff reset.

Covers the four scenarios called out in the bug ticket:
    * invalid → valid key
    * valid → invalid key
    * backoff reset after key change
    * cache invalidation after provider update

All tests are self-contained: they use HTTPX mocking via `monkeypatch` on
`httpx.AsyncClient.get` so no real HTTP is issued.
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import httpx

from market_providers.twelvedata import TwelveDataProvider, BASE_URL
from market_providers.alphavantage import AlphaVantageProvider
from market_providers.base import ProviderStats
from market_providers.cache import QuoteCache, _COLL as CACHE_COLL


# -------------------- httpx AsyncClient mock ---------------------------
class _MockResp:
    def __init__(self, status_code: int, json_body=None, text: str = "", headers=None):
        self.status_code = status_code
        self._json       = json_body if json_body is not None else {}
        self.text        = text or (str(json_body) if json_body is not None else "")
        self.headers     = headers or {}
        self.elapsed     = timedelta(milliseconds=50)

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _MockClient:
    def __init__(self, responder):
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, **kwargs):
        return self._responder(url, params or {})


def _patch_httpx(monkeypatch, responder):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _MockClient(responder))


# -------------------- Fixtures ------------------------------------------
@pytest.fixture
def fresh_twelvedata():
    p = TwelveDataProvider(api_key="OLD_KEY")
    # Simulate accumulated failure state from prior 429s
    p._backoff_step = 3
    p._backoff_until = datetime.now(timezone.utc) + timedelta(seconds=600)
    p._total_429_events = 12
    p._last_429_at = datetime.now(timezone.utc)
    p.stats.total_requests = 25
    p.stats.failed_requests = 12
    p.stats.successful_requests = 13
    p.stats.last_error = "You have run out of API credits for the current minute."
    p.stats.last_error_at = datetime.now(timezone.utc)
    p._credits_left_daily = 0
    p._credits_left_minute = 0
    return p


# ============================================================================
# 1) `set_api_key()` clears ALL backoff + stats state (unit test)
# ============================================================================
def test_set_api_key_clears_backoff_and_stats(fresh_twelvedata):
    p = fresh_twelvedata
    # Precondition: provider is in bad state
    assert p.is_backed_off()
    assert p._backoff_step == 3
    assert p.stats.failed_requests == 12
    assert p.stats.last_error is not None
    assert p._credits_left_minute == 0

    p.set_api_key("NEW_VALID_KEY")

    # Backoff cleared
    assert not p.is_backed_off()
    assert p._backoff_step == 0
    assert p._backoff_until is None

    # Stats zeroed
    assert p.stats.failed_requests == 0
    assert p.stats.successful_requests == 0
    assert p.stats.total_requests == 0
    assert p.stats.last_error is None
    assert p.stats.last_error_at is None

    # Credit trackers cleared (so UI doesn't show "0 credits left" from old key)
    assert p._credits_left_daily is None
    assert p._credits_left_minute is None

    # Historical total_429_events is intentionally NOT reset (audit)
    assert p._total_429_events == 12


def test_set_api_key_empty_string_still_clears_state(fresh_twelvedata):
    p = fresh_twelvedata
    p.set_api_key("")
    assert p._api_key == ""
    assert p._backoff_step == 0
    assert p.stats.failed_requests == 0
    assert p.stats.last_error is None


def test_set_api_key_strips_whitespace():
    p = TwelveDataProvider(api_key="")
    p.set_api_key("  ABC123  ")
    assert p._api_key == "ABC123"


# ============================================================================
# 2) test_connection() invalid → valid key
# ============================================================================
def test_test_connection_invalid_key_surfaces_exact_error(monkeypatch):
    import asyncio
    async def _inner():
        p = TwelveDataProvider(api_key="BAD_KEY")

        exact_msg = ("**apikey** parameter is incorrect or not specified. "
                      "Get your key at https://twelvedata.com/pricing.")
        def _resp(url, params):
            assert params["apikey"] == "BAD_KEY"
            return _MockResp(401, {"code": 401, "message": exact_msg, "status": "error"},
                              text=f'{{"code":401,"message":"{exact_msg}","status":"error"}}')
        _patch_httpx(monkeypatch, _resp)

        result = await p.test_connection()
        assert result["ok"] is False
        assert result["status_code"] == 401
        assert result["error"] == exact_msg              # ← EXACT provider text, not generic
        assert "BAD_KEY" not in result["response"]        # ← API key redacted from body
        assert "<REDACTED>" not in exact_msg              # message text itself doesn't contain key
        assert p.stats.last_error == exact_msg[:200]      # stats.last_error updated
        assert p.stats.failed_requests == 1
        assert p.stats.successful_requests == 0


    asyncio.run(_inner())

def test_test_connection_valid_key_marks_healthy(monkeypatch):
    import asyncio
    async def _inner():
        p = TwelveDataProvider(api_key="BAD_KEY")
        p._backoff_step = 2
        p._backoff_until = datetime.now(timezone.utc) + timedelta(seconds=120)

        p.set_api_key("GOOD_KEY")   # rotates state

        def _resp(url, params):
            assert params["apikey"] == "GOOD_KEY"
            return _MockResp(200, {"symbol": "EUR/USD", "close": "1.09123",
                                     "percent_change": "0.12"})
        _patch_httpx(monkeypatch, _resp)

        result = await p.test_connection()
        assert result["ok"] is True
        assert result["status_code"] == 200
        assert result["error"] is None
        # Rolling stats reflect healthy
        assert p.stats.successful_requests == 1
        assert p.stats.failed_requests == 0
        assert p.stats.last_error is None
        # Backoff cleared
        assert p.is_backed_off() is False


    asyncio.run(_inner())

# ============================================================================
# 3) Invalid → Valid key transition scenario
# ============================================================================
def test_invalid_to_valid_key_transition(monkeypatch):
    import asyncio
    async def _inner():
        p = TwelveDataProvider(api_key="INVALID")
        # Simulate that repeated failures have piled up rolling stats
        p.stats.failed_requests = 8
        p.stats.last_error = "invalid apikey"
        p._backoff_step = 4
        p._backoff_until = datetime.now(timezone.utc) + timedelta(seconds=240)

        # 1. Admin rotates to new key
        p.set_api_key("NEW_VALID")
        assert p.stats.failed_requests == 0
        assert p.stats.last_error is None
        assert not p.is_backed_off()

        # 2. Probe returns OK
        def _resp(url, params):
            return _MockResp(200, {"symbol": "EUR/USD", "close": "1.10"})
        _patch_httpx(monkeypatch, _resp)
        result = await p.test_connection()
        assert result["ok"] is True
        assert p.stats.successful_requests == 1
        assert p.stats.failed_requests == 0


    asyncio.run(_inner())

# ============================================================================
# 4) Valid → Invalid key transition scenario
# ============================================================================
def test_valid_to_invalid_key_surfaces_exact_error(monkeypatch):
    import asyncio
    async def _inner():
        p = TwelveDataProvider(api_key="GOOD")
        p.stats.successful_requests = 10

        # Now admin sets a bad key
        p.set_api_key("BAD")
        assert p.stats.successful_requests == 0    # stats reset even though prior was healthy

        err_msg = "You did not specify a valid api key."
        def _resp(url, params):
            return _MockResp(401, {"code": 401, "message": err_msg, "status": "error"},
                              text=f'{{"code":401,"message":"{err_msg}"}}')
        _patch_httpx(monkeypatch, _resp)

        result = await p.test_connection()
        assert result["ok"] is False
        assert result["error"] == err_msg
        assert p.stats.last_error == err_msg[:200]
        assert p.stats.failed_requests == 1


    asyncio.run(_inner())

# ============================================================================
# 5) 429 triggers backoff; key change resets it
# ============================================================================
def test_429_triggers_backoff_then_key_change_resets(monkeypatch):
    import asyncio
    async def _inner():
        p = TwelveDataProvider(api_key="K1")

        def _resp429(url, params):
            return _MockResp(429, {"code": 429, "message": "You have run out of credits.",
                                     "status": "error"})
        _patch_httpx(monkeypatch, _resp429)

        r1 = await p.test_connection()
        assert r1["ok"] is False
        assert p.is_backed_off() is True
        assert p._backoff_step >= 1

        # New key immediately resets backoff
        p.set_api_key("K2")
        assert p.is_backed_off() is False
        assert p._backoff_step == 0
        assert p.stats.rate_limited_requests == 0


    asyncio.run(_inner())

# ============================================================================
# 6) API key redaction — never leak into logs or response body
# ============================================================================
def test_api_key_never_appears_in_response_payload(monkeypatch):
    import asyncio
    async def _inner():
        secret = "SECRET_KEY_12345"
        p = TwelveDataProvider(api_key=secret)

        def _resp(url, params):
            # Simulate the API echoing the apikey back (some errors do)
            body_text = f'{{"code":401,"message":"invalid apikey={secret}"}}'
            return _MockResp(401, {"code": 401, "message": f"invalid apikey={secret}"},
                              text=body_text)
        _patch_httpx(monkeypatch, _resp)

        result = await p.test_connection()
        assert secret not in result["response"]
        # error message string comes from provider JSON so it may still contain the key.
        # The requirement is that the response BODY preview is redacted; that's what we log.
        assert "<REDACTED>" in result["response"]


    asyncio.run(_inner())

# ============================================================================
# 7) Cache invalidation by source (post-key-change hygiene)
# ============================================================================
def test_cache_invalidate_by_source_removes_stale_provider_prices():
    import asyncio
    async def _inner():
        # Use an in-memory fake db
        class _Coll:
            def __init__(self): self.docs = []
            async def delete_many(self, q):
                before = len(self.docs)
                self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
                return SimpleNamespace(deleted_count=before - len(self.docs))
            async def insert_one(self, d): self.docs.append(d)
        class _DB:
            def __init__(self): self._c = _Coll()
            def __getitem__(self, name): return self._c

        db = _DB()
        cache = QuoteCache(db, ttl_seconds=60)

        await db[CACHE_COLL].insert_one({"symbol": "EURUSD", "source": "twelvedata", "price": 1.1})
        await db[CACHE_COLL].insert_one({"symbol": "XAUUSD", "source": "twelvedata", "price": 3450.0})
        await db[CACHE_COLL].insert_one({"symbol": "BTCUSD", "source": "mock", "price": 65000.0})
        assert len(db[CACHE_COLL].docs) == 3

        deleted = await cache.invalidate_by_source("twelvedata")
        assert deleted == 2
        assert len(db[CACHE_COLL].docs) == 1
        assert db[CACHE_COLL].docs[0]["source"] == "mock"

        # No-op for unknown source
        deleted = await cache.invalidate_by_source("nonexistent")
        assert deleted == 0


    asyncio.run(_inner())

# ============================================================================
# 8) Alpha Vantage set_api_key resets stats too
# ============================================================================
def test_alpha_vantage_set_api_key_resets_stats():
    p = AlphaVantageProvider(api_key="OLD")
    p.stats.failed_requests = 5
    p.stats.last_error = "quota exceeded"

    p.set_api_key("NEW")
    assert p._api_key == "NEW"
    assert p.stats.failed_requests == 0
    assert p.stats.last_error is None


def test_alpha_vantage_test_connection_success(monkeypatch):
    import asyncio
    async def _inner():
        p = AlphaVantageProvider(api_key="GOOD")
        def _resp(url, params):
            return _MockResp(200, {"Realtime Currency Exchange Rate": {"5. Exchange Rate": "1.09"}})
        _patch_httpx(monkeypatch, _resp)
        r = await p.test_connection()
        assert r["ok"] is True


    asyncio.run(_inner())

def test_alpha_vantage_test_connection_quota_error(monkeypatch):
    import asyncio
    async def _inner():
        p = AlphaVantageProvider(api_key="THROTTLED")
        def _resp(url, params):
            msg = "We have detected your API key and our standard API rate limit is 25 requests per day."
            return _MockResp(200, {"Information": msg})
        _patch_httpx(monkeypatch, _resp)
        r = await p.test_connection()
        assert r["ok"] is False
        assert "25 requests per day" in r["error"]


    asyncio.run(_inner())

# ============================================================================
# 9) ProviderStats.reset() unit
# ============================================================================
def test_provider_stats_reset_zeros_counters_but_keeps_shape():
    s = ProviderStats(name="twelvedata", daily_credits_limit=800)
    s.record_failure("429", is_rate_limit=True)
    s.record_failure("401")
    s.record_success(latency_ms=25.0)
    assert s.failed_requests == 2
    assert s.total_requests == 3
    assert s.last_error == "401"

    s.reset()
    assert s.failed_requests == 0
    assert s.successful_requests == 0
    assert s.rate_limited_requests == 0
    assert s.total_requests == 0
    assert s.last_error is None
    assert s.last_error_at is None
    assert s.avg_response_ms == 0.0
    # Static config preserved
    assert s.name == "twelvedata"
    assert s.daily_credits_limit == 800
