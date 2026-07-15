"""Sprint 15.0 — Finnhub provider unit tests + architecture guards."""
from __future__ import annotations
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from market_providers.finnhub import FinnhubProvider, SYMBOL_MAP
from market_providers.manager import ProviderManager


# --- in-memory Mongo stub (same pattern as iter42) ---
class _Coll:
    def __init__(self): self.docs = []
    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None
    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {})); return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        if upsert:
            new = dict(q); new.update(upd.get("$set", {})); self.docs.append(new)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=new.get("_id"))
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)
    async def insert_one(self, d): self.docs.append(d)
    async def delete_many(self, q):
        n = len(self.docs); self.docs = [d for d in self.docs if not all(d.get(k)==v for k,v in q.items())]
        return SimpleNamespace(deleted_count=n - len(self.docs))
    async def estimated_document_count(self): return len(self.docs)
    async def count_documents(self, q): return len(self.docs)
    async def create_index(self, *a, **k): pass
    def find(self, q=None, proj=None): return _Cursor(list(self.docs))
class _Cursor:
    def __init__(self, docs): self._d = docs
    def sort(self,*a,**k): return self
    def limit(self,n): self._d=self._d[:n]; return self
    def skip(self,n): self._d=self._d[n:]; return self
    async def to_list(self,n): return self._d[:n]
    def __aiter__(self): self._i = iter(self._d); return self
    async def __anext__(self):
        try: return next(self._i)
        except StopIteration: raise StopAsyncIteration
class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n):
        if n not in self._c: self._c[n] = _Coll()
        return self._c[n]

def _run(coro): return asyncio.new_event_loop().run_until_complete(coro)


def _mkresp(status, body):
    import json as _j
    r = MagicMock(); r.status_code = status
    text = _j.dumps(body); r.text = text
    r.headers = {"content-type":"application/json"}
    r.json = MagicMock(return_value=body)
    return r


class _MockHttp:
    """Returns canned Finnhub /quote responses for each symbol."""
    def __init__(self, sym_prices):
        self._prices = sym_prices
        async def _get(url, params=None):
            sym = (params or {}).get("symbol")
            px = self._prices.get(sym, 0)
            return _mkresp(200, {"c": px, "h": px, "l": px, "o": px, "pc": px, "t": 0})
        self.get = _get
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


class TestFinnhubBasics:
    def test_symbol_map_covers_all_required(self):
        required = {"EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
                    "XAUUSD","XAGUSD","BTCUSD","ETHUSD",
                    "US30","NAS100","SPX500","GER40","UK100","IND50",
                    "USOIL","UKOIL","NATGAS"}
        missing = required - set(SYMBOL_MAP.keys())
        assert not missing, f"missing symbol map entries: {missing}"

    def test_forex_symbols_use_oanda(self):
        for s in ("EURUSD","GBPUSD","USDJPY","XAUUSD"):
            assert SYMBOL_MAP[s].startswith("OANDA:"), f"{s} should be OANDA:"

    def test_crypto_symbols_use_binance(self):
        assert SYMBOL_MAP["BTCUSD"] == "BINANCE:BTCUSDT"
        assert SYMBOL_MAP["ETHUSD"] == "BINANCE:ETHUSDT"

    def test_priority_is_100(self):
        p = FinnhubProvider()
        assert p.priority == 100

    def test_not_configured_without_key(self):
        p = FinnhubProvider(api_key="")
        assert _run(p.is_configured()) is False

    def test_configured_with_key(self):
        p = FinnhubProvider(api_key="abc")
        assert _run(p.is_configured()) is True


class TestFinnhubFetch:
    def test_fetch_returns_quote_for_valid_symbols(self):
        p = FinnhubProvider(api_key="TEST")
        with patch("market_providers.finnhub.httpx.AsyncClient",
                   lambda *a, **k: _MockHttp({"OANDA:EUR_USD": 1.0842,
                                                 "OANDA:XAU_USD": 2349.75,
                                                 "BINANCE:BTCUSDT": 92501.4})):
            quotes = _run(p._fetch_quotes(["EURUSD", "XAUUSD", "BTCUSD"]))
        assert set(quotes.keys()) == {"EURUSD", "XAUUSD", "BTCUSD"}
        assert quotes["EURUSD"].provider == "finnhub"
        assert abs(quotes["EURUSD"].price - 1.0842) < 1e-6
        assert quotes["EURUSD"].bid < quotes["EURUSD"].ask

    def test_zero_price_symbol_is_dropped(self):
        p = FinnhubProvider(api_key="TEST")
        with patch("market_providers.finnhub.httpx.AsyncClient",
                   lambda *a, **k: _MockHttp({"OANDA:EUR_USD": 1.08,
                                                 "OANDA:XAU_USD": 0})):
            quotes = _run(p._fetch_quotes(["EURUSD", "XAUUSD"]))
        assert "EURUSD" in quotes
        assert "XAUUSD" not in quotes


class TestManagerPriorityChain:
    def test_finnhub_is_first_in_chain(self):
        db = _DB()
        mgr = ProviderManager(db, universe=["EURUSD"], refresh_interval_sec=60)
        names = [p.name for p in mgr.providers]
        assert names[0] == "finnhub"
        assert names == sorted(names, key=lambda n: mgr._by_name[n].priority)

    def test_manager_picks_finnhub_when_configured(self):
        db = _DB()
        mgr = ProviderManager(db, universe=["EURUSD"], refresh_interval_sec=60)
        fh = mgr._by_name["finnhub"]; fh._api_key = "TEST_KEY_1234"
        with patch("market_providers.finnhub.httpx.AsyncClient",
                   lambda *a, **k: _MockHttp({"OANDA:EUR_USD": 1.0842})):
            result = _run(mgr.refresh_once())
        assert result["provider"] == "finnhub", result
        assert result["accepted"] >= 1

    def test_manager_writes_finnhub_to_cache(self):
        db = _DB()
        mgr = ProviderManager(db, universe=["EURUSD"], refresh_interval_sec=60)
        mgr._by_name["finnhub"]._api_key = "TEST"
        with patch("market_providers.finnhub.httpx.AsyncClient",
                   lambda *a, **k: _MockHttp({"OANDA:EUR_USD": 1.0842})):
            _run(mgr.refresh_once())
        doc = _run(mgr.cache.get("EURUSD"))
        assert doc["provider"] == "finnhub"
        assert doc["source"] == "LIVE"
        assert abs(doc["price"] - 1.0842) < 1e-6

    def test_manager_falls_back_to_mock_when_finnhub_unconfigured(self):
        db = _DB()
        mgr = ProviderManager(db, universe=["EURUSD"], refresh_interval_sec=60)
        # no keys anywhere → only mock is configured
        result = _run(mgr.refresh_once())
        assert result["provider"] == "mock"


class TestStatusExposesFinnhub:
    def test_http_status_contains_finnhub(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001")
        r = requests.post(f"{base}/api/admin/login", json={"email":"admin@mfb.in","password":"Admin@MFB2026"}, timeout=8)
        if r.status_code != 200: pytest.skip("admin login unavailable")
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        s = requests.get(f"{base}/api/market_providers/status", headers=h, timeout=8).json()
        names = [p["name"] for p in s["providers"]]
        assert "finnhub" in names
        fh = next(p for p in s["providers"] if p["name"]=="finnhub")
        assert fh["priority"] == 100

    def test_api_key_save_route_accepts_finnhub(self):
        import os, requests
        base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001")
        r = requests.post(f"{base}/api/admin/login", json={"email":"admin@mfb.in","password":"Admin@MFB2026"}, timeout=8)
        if r.status_code != 200: pytest.skip("admin login unavailable")
        h = {"Authorization": f"Bearer {r.json()['token']}", "Content-Type":"application/json"}
        # save a dummy key → immediately clear
        r = requests.put(f"{base}/api/market_providers/api-key",
                          json={"provider":"finnhub","key":"UNIT_TEST_DUMMY_FH_KEY"}, headers=h, timeout=15)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("provider") == "finnhub"
        assert body.get("configured") is True
        # cleanup
        requests.put(f"{base}/api/market_providers/api-key",
                     json={"provider":"finnhub","key":""}, headers=h, timeout=8)
