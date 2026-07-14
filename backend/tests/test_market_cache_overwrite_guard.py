"""Sprint 14.1 — Cache overwrite guard regression suite.

Proves that:
  * Mock CANNOT overwrite a fresh TwelveData live quote.
  * An older-timestamp write is rejected.
  * A LIVE row aging past FRESH_MAX_SEC is exposed as STALE on read.
  * Every write is audit-logged with old/new price + provider + reason.
  * put_many returns {accepted, rejected} counts.
  * ensure_indexes() is idempotent.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from market_providers.cache import (
    QuoteCache, FRESH_MAX_SEC, STALE_MAX_SEC, _COLL, _AUDIT_COLL,
)
from market_providers.base import Quote


# ---------------- in-memory fake Mongo ----------------
class _Coll:
    def __init__(self):
        self.docs = []
        self._indexes = []
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
        n = 0
        for d in self.docs:
            hit = True
            for k, v in q.items():
                if isinstance(v, dict) and "$gte" in v:
                    val = d.get(k)
                    if not val or val < v["$gte"]:
                        hit = False; break
                elif d.get(k) != v:
                    hit = False; break
            if hit:
                n += 1
        return n
    async def insert_one(self, d):
        self.docs.append(d)
    def find(self, q=None, proj=None):
        return _Cursor([d for d in self.docs
                         if not q or all(d.get(k) == v for k, v in q.items())])
    async def create_index(self, *a, **k): self._indexes.append((a, k))


class _Cursor:
    def __init__(self, docs): self._docs = list(docs); self._sort = None; self._limit = None
    def sort(self, key, direction=None):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    def __aiter__(self): self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _DB:
    def __init__(self):
        self._colls = {}
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _Coll()
        return self._colls[name]


def _now(): return datetime.now(timezone.utc)


@pytest.fixture
def cache():
    return QuoteCache(_DB(), ttl_seconds=60)


def _q(price, provider="twelvedata", ts=None, bid=None, ask=None):
    ts = ts or _now()
    return Quote(symbol="XAUUSD", price=float(price),
                  bid=bid or price - 0.05, ask=ask or price + 0.05,
                  change_pct=0.0, provider=provider, ts=ts)


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro) if False \
            else asyncio.new_event_loop().run_until_complete(coro)


# ============================================================================
#  Priority guard
# ============================================================================
def test_mock_cannot_overwrite_fresh_twelvedata(cache):
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    # Immediately try mock → must reject
    res = _run(cache.put_many({"XAUUSD": _q(2000.00, "mock")}))
    assert res == {"accepted": 0, "rejected": 1}
    doc = _run(cache.get("XAUUSD"))
    assert doc["price"] == 3450.00
    assert doc["provider"] == "twelvedata"
    assert doc["source"] == "LIVE"


def test_mock_can_overwrite_expired_twelvedata(cache):
    # Write an OLD twelvedata row (past STALE_MAX_SEC)
    old_ts = _now() - timedelta(seconds=STALE_MAX_SEC + 60)
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata", ts=old_ts)}))
    # Manually age it in the DB
    for d in cache.db[_COLL].docs:
        d["updated_at"] = old_ts
        d["provider_ts"] = old_ts
    res = _run(cache.put_many({"XAUUSD": _q(3400.00, "mock")}))
    assert res == {"accepted": 1, "rejected": 0}
    doc = _run(cache.get("XAUUSD"))
    assert doc["provider"] == "mock"
    assert doc["source"] == "MOCK"


def test_higher_priority_provider_overwrites_lower(cache):
    # AlphaVantage (200) writes first
    _run(cache.put_many({"XAUUSD": _q(3450.00, "alphavantage")}))
    # TwelveData (100) arrives → must overwrite
    res = _run(cache.put_many({"XAUUSD": _q(3451.00, "twelvedata")}))
    assert res["accepted"] == 1
    doc = _run(cache.get("XAUUSD"))
    assert doc["provider"] == "twelvedata"


def test_same_provider_updates_freely(cache):
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    _run(cache.put_many({"XAUUSD": _q(3452.50, "twelvedata")}))
    doc = _run(cache.get("XAUUSD"))
    assert doc["price"] == 3452.50


# ============================================================================
#  Timestamp guard
# ============================================================================
def test_older_timestamp_write_is_rejected(cache):
    now = _now()
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata", ts=now)}))
    # Same provider, older timestamp (10s ago) → rejected
    res = _run(cache.put_many({"XAUUSD": _q(3400.00, "twelvedata", ts=now - timedelta(seconds=10))}))
    assert res == {"accepted": 0, "rejected": 1}


def test_newer_timestamp_write_accepted(cache):
    now = _now()
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata", ts=now - timedelta(seconds=10))}))
    res = _run(cache.put_many({"XAUUSD": _q(3452.00, "twelvedata", ts=now)}))
    assert res["accepted"] == 1


# ============================================================================
#  Source label re-derivation on read
# ============================================================================
def test_fresh_live_quote_labelled_live(cache):
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    doc = _run(cache.get("XAUUSD"))
    assert doc["source"] == "LIVE"
    assert doc["age_sec"] < FRESH_MAX_SEC


def test_aged_live_quote_read_as_stale(cache):
    # Insert then age it past FRESH_MAX_SEC
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    old = _now() - timedelta(seconds=FRESH_MAX_SEC + 30)
    for d in cache.db[_COLL].docs:
        d["updated_at"] = old
    doc = _run(cache.get("XAUUSD"))
    assert doc["source"] == "STALE"


def test_very_old_live_quote_read_as_cache(cache):
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    old = _now() - timedelta(seconds=STALE_MAX_SEC + 300)
    for d in cache.db[_COLL].docs:
        d["updated_at"] = old
    doc = _run(cache.get("XAUUSD"))
    assert doc["source"] == "CACHE"


def test_mock_row_labelled_mock(cache):
    _run(cache.put_many({"XAUUSD": _q(3400.00, "mock")}))
    doc = _run(cache.get("XAUUSD"))
    assert doc["source"] == "MOCK"


# ============================================================================
#  Audit logging
# ============================================================================
def test_every_write_produces_audit_row(cache):
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    _run(cache.put_many({"XAUUSD": _q(2000.00, "mock")}))          # rejected
    _run(cache.put_many({"XAUUSD": _q(3452.00, "twelvedata")}))    # accepted
    audit = cache.db[_AUDIT_COLL].docs
    assert len(audit) == 3
    # Check reject entry
    rej = [a for a in audit if not a["accepted"]]
    assert len(rej) == 1
    assert rej[0]["symbol"] == "XAUUSD"
    assert "REJECTED" in rej[0]["reason"]
    assert rej[0]["provider"] == "mock"
    assert rej[0]["old_price"] == 3450.00
    assert rej[0]["new_price"] == 2000.00


def test_recent_writes_trace_ordered_by_time(cache):
    _run(cache.put_many({"EURUSD": _q(1.09, "twelvedata")}))
    _run(cache.put_many({"XAUUSD": _q(3450.0, "twelvedata")}))
    _run(cache.put_many({"XAUUSD": _q(2000.0, "mock")}))       # reject
    trace = _run(cache.recent_writes(symbol="XAUUSD", limit=10))
    assert len(trace) == 2
    assert trace[0]["provider"] == "mock"                       # newest first
    assert trace[0]["accepted"] is False
    assert trace[1]["provider"] == "twelvedata"
    assert trace[1]["accepted"] is True


def test_stats_reports_write_counts(cache):
    _run(cache.put_many({"EURUSD": _q(1.09, "twelvedata"), "GBPUSD": _q(1.25, "twelvedata")}))
    _run(cache.put_many({"EURUSD": _q(1.05, "mock")}))          # reject
    s = _run(cache.stats())
    assert s["writes_accepted_process"] == 2
    assert s["writes_rejected_process"] == 1
    assert s["writes_by_provider_process"] == {"twelvedata": 2}


# ============================================================================
#  Invalidate by source
# ============================================================================
def test_invalidate_by_source_removes_only_that_provider(cache):
    _run(cache.put_many({"EURUSD": _q(1.09, "twelvedata")}))
    _run(cache.put_many({"BTCUSD": _q(60000, "binance")}))
    _run(cache.put_many({"XAGUSD": _q(30, "mock")}))
    deleted = _run(cache.invalidate_by_source("twelvedata"))
    assert deleted == 1
    remaining = {d["symbol"] for d in cache.db[_COLL].docs}
    assert "EURUSD" not in remaining
    assert "BTCUSD" in remaining
    assert "XAGUSD" in remaining


# ============================================================================
#  put_many returns accepted/rejected counts
# ============================================================================
def test_put_many_returns_counts(cache):
    _run(cache.put_many({"EURUSD": _q(1.09, "twelvedata")}))
    res = _run(cache.put_many({
        "EURUSD": _q(1.05, "mock"),      # rejected
        "GBPUSD": _q(1.25, "mock"),      # accepted (no prior)
        "XAUUSD": _q(3450, "twelvedata"),# accepted
    }))
    assert res == {"accepted": 2, "rejected": 1}


# ============================================================================
#  ensure_indexes idempotent
# ============================================================================
def test_ensure_indexes_idempotent(cache):
    _run(cache.ensure_indexes())
    _run(cache.ensure_indexes())
    idx = cache.db[_COLL]._indexes
    assert len(idx) >= 2


# ============================================================================
#  Real-world overwrite scenario (Sprint 14.1 root-cause reproduction)
# ============================================================================
def test_scenario_manual_live_then_mock_scheduler_no_longer_wins(cache):
    """Reproduces the exact bug from the ticket:
    1. Live XAU/USD manual fetch writes 3450.00 (twelvedata)
    2. A few seconds later the background scheduler falls back to Mock
       (because free-tier throttled TwelveData) and TRIES to overwrite
       with 2000.00. Previously this succeeded and users saw the wrong price.
    3. With the guard the mock write is rejected and the trace records the reason.
    """
    # Step 1 — live TwelveData write
    _run(cache.put_many({"XAUUSD": _q(3450.00, "twelvedata")}))
    # Step 2 — background scheduler tick using mock
    _run(cache.put_many({"XAUUSD": _q(2000.00, "mock")}))
    # Step 3 — read what the app now shows
    price = _run(cache.get_price("XAUUSD"))
    assert price == 3450.00
    # Step 4 — the trace endpoint proves the overwrite was attempted & blocked
    trace = _run(cache.recent_writes(symbol="XAUUSD"))
    reasons = [t["reason"] for t in trace]
    assert any("REJECTED" in r and "mock" in r for r in reasons)
    assert any("ACCEPTED" in r and "twelvedata" in r for r in reasons)
