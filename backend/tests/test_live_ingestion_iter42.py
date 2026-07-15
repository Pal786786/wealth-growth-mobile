"""Sprint 14.1.2 — LIVE ingestion pipeline unit test.

Proves the FULL happy path:

    TwelveData HTTP response → parser → Quote → ProviderManager
    → QuoteCache.put_many() → market_price_cache document (provider=twelvedata)

Uses an in-memory Mongo stub + a monkey-patched httpx.AsyncClient so we don't
touch the network. If this test passes, the ingestion drop investigated by
Sprint 14.1.2 is fixed at the code level. Any drop the operator sees in prod
after this passes must be an environment / key / rate-limit issue, which the
new `GET /api/market/debug/xauusd` endpoint will surface directly.

Sprint 15.0 update
------------------
TwelveData is DISABLED at the ``ProviderManager`` level. Its code is retained
on disk (so historic keys still deserialise) but it is no longer instantiated
in the provider chain. These tests therefore no longer apply to the live
pipeline — they've been superseded by ``test_finnhub_provider_iter44.py``.
The whole module is skipped rather than deleted, so the audit trail is
preserved.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Sprint 15.0: TwelveData provider disabled — superseded by test_finnhub_provider_iter44.py"
)

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

from market_providers.manager import ProviderManager
from market_providers.twelvedata import TwelveDataProvider


# ---------------- in-memory Mongo stub ----------------
class _Coll:
    def __init__(self):
        self.docs = []
    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None
    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        if upsert:
            new_doc = dict(q); new_doc.update(upd.get("$set", {}))
            self.docs.append(new_doc)
        return SimpleNamespace(matched_count=0)
    async def delete_many(self, q):
        before = len(self.docs)
        self.docs = [d for d in self.docs
                      if not all(d.get(k) == v for k, v in q.items())]
        return SimpleNamespace(deleted_count=before - len(self.docs))
    async def estimated_document_count(self):
        return len(self.docs)
    async def count_documents(self, q):
        return len(self.docs)
    async def insert_one(self, d):
        self.docs.append(d)
    def find(self, q=None, proj=None):
        return _Cursor(list(self.docs))
    async def create_index(self, *a, **k): pass


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    def skip(self, n): self._docs = self._docs[n:]; return self
    def __aiter__(self): self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration
    async def to_list(self, n):
        return self._docs[:n]


class _DB:
    def __init__(self):
        self._colls = {}
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _Coll()
        return self._colls[name]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------- canned TwelveData response ----------------
_XAU_BATCH_OK = {
    "XAU/USD": {
        "symbol": "XAU/USD", "name": "Gold Spot",
        "exchange": "OTC", "currency": "USD",
        "datetime": "2026-07-14 12:00:00", "timestamp": 1752494400,
        "open": "2340.15", "high": "2352.60", "low": "2338.20",
        "close": "2349.75", "previous_close": "2341.10",
        "change": "8.65", "percent_change": "0.37", "is_market_open": True,
    },
    "EUR/USD": {
        "symbol": "EUR/USD", "close": "1.0842", "percent_change": "0.12",
        "datetime": "2026-07-14 12:00:00",
    },
}


def _make_http_response(status_code: int, body: dict, headers: dict = None):
    """Build a mock httpx.Response-like object."""
    text = json.dumps(body)
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode()
    resp.headers = headers or {"api-credits-left": "50", "api-daily-credits-left": "700"}
    resp.json = MagicMock(return_value=body)
    resp.elapsed = MagicMock(); resp.elapsed.total_seconds = MagicMock(return_value=0.05)
    return resp


class _MockAsyncClient:
    """Drop-in replacement for httpx.AsyncClient returning a canned batch."""
    def __init__(self, *a, **k):
        self.get = AsyncMock(
            return_value=_make_http_response(200, _XAU_BATCH_OK)
        )
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


# ============================================================================
#  The critical ingestion happy-path test
# ============================================================================
class TestLiveIngestionFullPipeline:

    def test_twelvedata_quote_reaches_market_price_cache(self):
        """End-to-end: refresh_once → cache document with provider=twelvedata.
        This is the exact flow that Sprint 14.1.2 flagged as broken.
        """
        db = _DB()
        # Small universe to keep the mock focused
        pm = ProviderManager(db, universe=["XAUUSD", "EURUSD"],
                              refresh_interval_sec=60)
        # Inject a working key into the TwelveData provider so is_configured() → True
        td: TwelveDataProvider = pm._by_name["twelvedata"]  # type: ignore
        td._api_key = "TEST_KEY_ABC123"

        # Ensure the manager picks TwelveData (highest priority) and not mock
        with patch("market_providers.twelvedata.httpx.AsyncClient", _MockAsyncClient):
            result = _run(pm.refresh_once())

        # 1. Provider used = twelvedata
        assert result["provider"] == "twelvedata", result
        # 2. Two quotes parsed, both accepted into cache
        assert result["count"] == 2, result
        assert result["accepted"] == 2, result
        assert result["rejected"] == 0, result

        # 3. Mongo document for XAUUSD is LIVE from TwelveData
        doc = _run(pm.cache.get("XAUUSD"))
        assert doc is not None, "market_price_cache missing XAUUSD"
        assert abs(doc["price"] - 2349.75) < 1e-6
        assert doc["provider"] == "twelvedata"
        assert doc["source"] == "LIVE"
        # last_write_reason surfaces which provider wrote
        assert "twelvedata" in doc["last_write_reason"]

    def test_ingestion_rejects_mock_after_live_write(self):
        """After a live TwelveData write, the mock refresh must NOT
        overwrite the fresh row (guard from Sprint 14.1).
        """
        db = _DB()
        pm = ProviderManager(db, universe=["XAUUSD"], refresh_interval_sec=60)
        td: TwelveDataProvider = pm._by_name["twelvedata"]  # type: ignore
        td._api_key = "TEST_KEY_ABC123"

        with patch("market_providers.twelvedata.httpx.AsyncClient", _MockAsyncClient):
            _run(pm.refresh_once())

        # Now force mock and refresh again
        _run(pm.set_manual_provider("mock"))
        result = _run(pm.refresh_once())
        assert result["provider"] == "mock"
        # Guard rejects the mock write
        assert result["rejected"] >= 1, result

        # XAUUSD is still the twelvedata row
        doc = _run(pm.cache.get("XAUUSD"))
        assert doc["provider"] == "twelvedata"
        assert doc["source"] in ("LIVE", "STALE")   # depends on read-time age

    def test_ingestion_survives_partial_batch_errors(self):
        """If TwelveData returns an error for one symbol and a valid quote
        for another, the valid one MUST still reach the cache.
        """
        db = _DB()
        pm = ProviderManager(db, universe=["XAUUSD", "NIFTY_BAD"],
                              refresh_interval_sec=60)
        td: TwelveDataProvider = pm._by_name["twelvedata"]  # type: ignore
        td._api_key = "TEST_KEY_ABC123"

        mixed_response = {
            "XAU/USD": _XAU_BATCH_OK["XAU/USD"],
            "NIFTY_BAD": {"code": 400, "status": "error",
                           "message": "**symbol** NIFTY_BAD not found"},
        }

        class _MixedClient(_MockAsyncClient):
            def __init__(self, *a, **k):
                self.get = AsyncMock(
                    return_value=_make_http_response(200, mixed_response)
                )

        with patch("market_providers.twelvedata.httpx.AsyncClient", _MixedClient):
            result = _run(pm.refresh_once())

        assert result["provider"] == "twelvedata"
        assert result["count"] == 1        # only XAUUSD parsed
        assert result["accepted"] == 1
        doc = _run(pm.cache.get("XAUUSD"))
        assert doc is not None
        assert doc["provider"] == "twelvedata"
