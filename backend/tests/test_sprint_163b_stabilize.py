"""Sprint 16.3b — Candle pipeline stabilization.

  1. _store_bars writes in bounded batches (<=400 ops) and reports
     {stored, last_ok_t, complete} so meta can resume after partial failure
     (prevents Atlas NetworkTimeout losing the whole sync).
  2. get_candles guarantees unique ascending timestamps (finnhub preferred
     over live duplicates).

Run: cd /app/backend && python -m pytest tests/test_sprint_163b_stabilize.py -v
"""
import asyncio
import sys
import time

import pytest
import requests

sys.path.insert(0, "/app/backend")

API = "http://localhost:8001/api"
SYMBOLS = ["BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD"]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------- #
# 1. Chunked _store_bars
# --------------------------------------------------------------------- #
class TestChunkedStore:
    def _bars(self, n, t0=1784000040):
        return [{"t": t0 + i * 60, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 0.0}
                for i in range(n)]

    def test_batches_are_bounded(self):
        """1000 bars must be written in ceil(1000/400)=3 bulk calls."""
        import market_candles as mc
        calls = []

        class FakeRes:
            upserted_count, modified_count = 400, 0

        class FakeColl:
            async def bulk_write(self, ops, ordered=False):
                calls.append(len(ops))
                r = FakeRes(); r.upserted_count = len(ops)
                return r

        class FakeDB(dict):
            def __getitem__(self, k): return FakeColl()

        old = mc._db; mc._db = FakeDB()
        try:
            st = _run(mc._store_bars("TESTSYM", "1m", self._bars(1000)))
        finally:
            mc._db = old
        assert calls == [400, 400, 200]
        assert st["stored"] == 1000 and st["complete"] is True
        assert st["last_ok_t"] == 1784000040 + 999 * 60

    def test_partial_failure_resumable(self):
        """If batch 2 dies (NetworkTimeout-style), last_ok_t must point at the
        end of batch 1 so meta lets the next sync RESUME, not refetch."""
        import market_candles as mc
        n_calls = {"i": 0}

        class FakeColl:
            async def bulk_write(self, ops, ordered=False):
                n_calls["i"] += 1
                if n_calls["i"] == 2:
                    raise RuntimeError("simulated NetworkTimeout")
                class R: upserted_count, modified_count = len(ops), 0
                return R()

        class FakeDB(dict):
            def __getitem__(self, k): return FakeColl()

        old = mc._db; mc._db = FakeDB()
        try:
            st = _run(mc._store_bars("TESTSYM", "1m", self._bars(1000)))
        finally:
            mc._db = old
        assert st["complete"] is False
        assert st["stored"] == 400
        assert st["last_ok_t"] == 1784000040 + 399 * 60  # end of batch 1

    def test_total_failure_reports_none(self):
        import market_candles as mc

        class FakeColl:
            async def bulk_write(self, ops, ordered=False):
                raise RuntimeError("down")

        class FakeDB(dict):
            def __getitem__(self, k): return FakeColl()

        old = mc._db; mc._db = FakeDB()
        try:
            st = _run(mc._store_bars("TESTSYM", "1m", self._bars(10)))
        finally:
            mc._db = old
        assert st == {"stored": 0, "last_ok_t": None, "complete": False}


# --------------------------------------------------------------------- #
# 2. Unique ascending timestamps on read
# --------------------------------------------------------------------- #
class TestReadDedupe:
    def test_duplicate_rows_deduped_finnhub_preferred(self):
        """Two DB rows at the same t (live + finnhub) → one candle, finnhub wins."""
        import market_candles as mc
        from motor.motor_asyncio import AsyncIOMotorClient

        async def scenario():
            db = AsyncIOMotorClient("mongodb://localhost:27017").sprint163b_test
            coll = db[mc.HIST_COLL]
            await coll.drop()
            t0 = int(time.time() // 60) * 60 - 600
            await coll.insert_many([
                {"symbol": "TESTSYM", "tf": "1m", "t": t0, "o": 1, "h": 1, "l": 1, "c": 1.0, "v": 1, "source": "live"},
                {"symbol": "TESTSYM", "tf": "1m", "t": t0, "o": 2, "h": 2, "l": 2, "c": 2.0, "v": 5, "source": "finnhub"},
                {"symbol": "TESTSYM", "tf": "1m", "t": t0 + 60, "o": 3, "h": 3, "l": 3, "c": 3.0, "v": 1, "source": "live"},
                {"symbol": "TESTSYM", "tf": "1m", "t": t0 + 60, "o": 3, "h": 3, "l": 3, "c": 3.0, "v": 1, "source": "live"},
            ])
            old = mc._db; mc._db = db
            try:
                out = await mc.get_candles("TESTSYM", "1m", limit=100)
            finally:
                mc._db = old
                await coll.drop()
            return out, t0

        out, t0 = _run(scenario())
        ts = [c["t"] for c in out]
        assert len(ts) == len(set(ts)) == 2, f"expected 2 unique candles, got {ts}"
        assert ts == sorted(ts)
        first = [c for c in out if c["t"] == t0][0]
        assert first["source"] == "finnhub" and first["c"] == 2.0


# --------------------------------------------------------------------- #
# 3. E2E: all six symbols — 200, unique asc timestamps, API shape intact
# --------------------------------------------------------------------- #
class TestEndpoints:
    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_symbol(self, sym):
        t0 = time.time()
        r = requests.get(f"{API}/market/candles/{sym}?tf=1m&limit=300", timeout=40)
        dt = time.time() - t0
        assert r.status_code == 200, f"{sym}: {r.status_code}"
        j = r.json()
        assert set(j.keys()) >= {"symbol", "tf", "candles", "volume_available", "quote", "sync"}
        ts = [c["t"] for c in j["candles"]]
        assert len(ts) == len(set(ts)), f"{sym}: duplicate timestamps"
        assert ts == sorted(ts), f"{sym}: not ascending"
        assert dt < 5, f"{sym}: too slow locally ({dt:.1f}s)"
