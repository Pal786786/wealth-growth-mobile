"""Sprint 16.3 — Forex/Gold historical candle 500 fix.

Covers the three defects fixed in market_candles.py:
  1. ensure_history TypeError: naive last_sync_at (Mongo) vs tz-aware _now_dt()
     → previously HTTP 500 on EVERY request once a meta doc existed.
  2. _store_bars: duplicate timestamps in one Finnhub batch / BulkWriteError
     → previously an unhandled exception; now de-duplicated + salvaged.
  3. Route isolation: a sync exception must never 500 the read path.

Run: cd /app/backend && python -m pytest tests/test_sprint_163_candle_fix.py -v
"""
import asyncio
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

API = "http://localhost:8001/api"
DB = MongoClient("mongodb://localhost:27017").my_funding_bank

SYMBOLS = ["BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD"]


# --------------------------------------------------------------------- #
# 1. The proven production crash: naive last_sync_at in market_history_meta
# --------------------------------------------------------------------- #
class TestNaiveDatetimeMeta:
    def test_naive_meta_no_longer_500s(self):
        """Insert a meta doc exactly as _update_meta writes it (Mongo returns
        it NAIVE). Before the fix this made the endpoint 500 in one call."""
        mid = "XAUUSD:1m"
        backup = DB.market_history_meta.find_one({"_id": mid})
        now = int(time.time())
        DB.market_history_meta.replace_one({"_id": mid}, {
            "_id": mid,
            "oldest_t": now - 2 * 86400,
            "newest_t": now - 7200,
            "last_sync_at": datetime.now(timezone.utc) - timedelta(hours=2),
        }, upsert=True)
        try:
            r = requests.get(f"{API}/market/candles/XAUUSD?tf=1m&limit=50", timeout=30)
            assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:100]}"
            j = r.json()
            assert "candles" in j and "sync" in j
            assert not str(j["sync"].get("reason", "")).startswith("sync_error:TypeError")
        finally:
            if backup is None:
                DB.market_history_meta.delete_one({"_id": mid})
            else:
                DB.market_history_meta.replace_one({"_id": mid}, backup, upsert=True)

    def test_throttle_branch_works_with_fresh_naive_meta(self):
        """A FRESH naive last_sync_at must hit the throttle branch (reason
        'throttled' or 'up_to_date'), proving the subtraction now works."""
        mid = "XAUUSD:1m"
        backup = DB.market_history_meta.find_one({"_id": mid})
        now = int(time.time())
        DB.market_history_meta.replace_one({"_id": mid}, {
            "_id": mid,
            "oldest_t": now - 2 * 86400,
            "newest_t": now - 7200,
            "last_sync_at": datetime.now(timezone.utc),   # just synced
        }, upsert=True)
        try:
            r = requests.get(f"{API}/market/candles/XAUUSD?tf=1m&limit=50", timeout=30)
            assert r.status_code == 200
            assert r.json()["sync"]["reason"] in ("throttled", "up_to_date")
        finally:
            if backup is None:
                DB.market_history_meta.delete_one({"_id": mid})
            else:
                DB.market_history_meta.replace_one({"_id": mid}, backup, upsert=True)


# --------------------------------------------------------------------- #
# 2. _store_bars: dedupe + BulkWriteError salvage
# --------------------------------------------------------------------- #
class TestStoreBars:
    def _run(self, coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_duplicate_timestamps_deduped(self):
        """Two bars with the same t must produce ONE stored doc (no E11000,
        no duplicate candles) even under a unique (symbol, tf, t) index."""
        import sys
        sys.path.insert(0, "/app/backend")
        import market_candles as mc
        from motor.motor_asyncio import AsyncIOMotorClient

        async def scenario():
            db = AsyncIOMotorClient("mongodb://localhost:27017").sprint163_test
            coll = db[mc.HIST_COLL]
            await coll.drop()
            await coll.create_index([("symbol", 1), ("tf", 1), ("t", 1)],
                                    unique=True, name="sym_tf_t")
            old_db = mc._db
            mc._db = db
            try:
                t0 = 1784000000 - (1784000000 % 60)
                bars = [
                    {"t": t0, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 1.0},
                    {"t": t0, "o": 1.1, "h": 2.1, "l": 0.6, "c": 1.6, "v": 2.0},  # dup t
                    {"t": t0 + 60, "o": 1.6, "h": 2.2, "l": 1.0, "c": 2.0, "v": 3.0},
                ]
                stored = await mc._store_bars("TESTSYM", "1m", bars)
                n = await coll.count_documents({"symbol": "TESTSYM"})
                doc = await coll.find_one({"symbol": "TESTSYM", "t": t0})
                return stored, n, doc
            finally:
                mc._db = old_db
                await coll.drop()

        stored, n, doc = self._run(scenario())
        assert n == 2, f"expected 2 unique docs, found {n}"
        assert doc["c"] == 1.6, "last duplicate must win"
        assert stored == 2

    def test_bulkwriteerror_salvaged_not_raised(self):
        """A BulkWriteError from the driver must be logged + salvaged, never
        propagated (this is what 500'd production)."""
        import sys
        sys.path.insert(0, "/app/backend")
        import market_candles as mc
        from pymongo.errors import BulkWriteError

        class FakeColl:
            async def bulk_write(self, ops, ordered=False):
                raise BulkWriteError({
                    "nUpserted": 5, "nModified": 2,
                    "writeErrors": [{"errmsg": "E11000 duplicate key error (simulated)"}],
                })

        class FakeDB(dict):
            def __getitem__(self, k):
                return FakeColl()

        old_db = mc._db
        mc._db = FakeDB()
        try:
            bars = [{"t": 1784000000 + i * 60, "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}
                    for i in range(10)]
            stored = self._run(mc._store_bars("TESTSYM", "1m", bars))
            assert stored == 7, "must return salvaged nUpserted+nModified"
        finally:
            mc._db = old_db


# --------------------------------------------------------------------- #
# 3. All six mandatory symbols: HTTP 200, candles, cache, no regression
# --------------------------------------------------------------------- #
class TestMandatorySymbols:
    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_symbol_200_with_candles(self, sym):
        r = requests.get(f"{API}/market/candles/{sym}?tf=1m&limit=300", timeout=40)
        assert r.status_code == 200, f"{sym}: {r.status_code} {r.text[:80]}"
        j = r.json()
        assert j["symbol"] == sym
        assert isinstance(j["candles"], list) and len(j["candles"]) > 0
        c0 = j["candles"][0]
        for k in ("t", "o", "h", "l", "c", "v"):
            assert k in c0
        # never a raw exception in sync result
        assert isinstance(j["sync"], dict)

    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_no_duplicate_timestamps_in_response(self, sym):
        r = requests.get(f"{API}/market/candles/{sym}?tf=1m&limit=300", timeout=40)
        ts = [c["t"] for c in r.json()["candles"]]
        assert len(ts) == len(set(ts)), f"{sym}: duplicate candle timestamps"
        assert ts == sorted(ts), f"{sym}: candles not ascending"

    def test_cache_populated(self):
        """market_price_history must hold 1m rows for every mandatory symbol."""
        for sym in SYMBOLS:
            n = DB.market_price_history.count_documents({"symbol": sym, "tf": "1m"})
            assert n > 0, f"{sym}: no cached 1m candles"

    def test_btc_behaviour_unchanged(self):
        r = requests.get(f"{API}/market/candles/BTCUSD?tf=1m&limit=300", timeout=40)
        assert r.status_code == 200
        j = r.json()
        assert len(j["candles"]) > 0
        assert j["volume_available"] in (True, False)

    def test_higher_timeframes_aggregate(self):
        for tf in ("5m", "1h", "1d"):
            r = requests.get(f"{API}/market/candles/XAUUSD?tf={tf}&limit=100", timeout=40)
            assert r.status_code == 200, f"tf={tf}: {r.status_code}"
            assert len(r.json()["candles"]) > 0
