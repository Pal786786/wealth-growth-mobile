"""Sprint 14.1.2b — Canonical key-store persistence tests.

Verifies the fragmented-collection persistence bug is fully fixed:

  BEFORE: A key saved from AdminMarketSettings / AdminMarketData /
          AdminForexSettings landed in one of three legacy Mongo collections
          that ProviderManager never reads. Manager kept using Mock, and the
          debug endpoint correctly reported `NOT_CONFIGURED`.

  AFTER:  Every save-path shadow-writes to the canonical
          `market_provider_config._id="active"` collection AND propagates
          to the live ProviderManager instance immediately. Plus, on
          restart, `_load_config` auto-migrates any legacy keys that
          somehow slipped through.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from market_providers import key_store


class _Coll:
    def __init__(self): self.docs = {}
    async def find_one(self, q):
        key = tuple(sorted(q.items()))
        return self.docs.get(key)
    async def update_one(self, q, upd, upsert=False):
        key = tuple(sorted(q.items()))
        cur = self.docs.get(key)
        if cur is None:
            if not upsert:
                return SimpleNamespace(matched_count=0)
            cur = dict(q)
            self.docs[key] = cur
        _set = upd.get("$set", {})
        for k, v in _set.items():
            if "." in k:
                head, *rest = k.split(".")
                d = cur.setdefault(head, {})
                for p in rest[:-1]:
                    d = d.setdefault(p, {})
                d[rest[-1]] = v
            else:
                cur[k] = v
        return SimpleNamespace(matched_count=1)


class _DB:
    def __init__(self):
        self._c = {}
    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = _Coll()
        return self._c[name]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestCanonicalReadWrite:
    def test_canonical_write_and_read(self):
        db = _DB()
        _run(key_store.canonical_write(db, "twelvedata", "KEY_ABC"))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "KEY_ABC"

    def test_canonical_write_strips_whitespace(self):
        db = _DB()
        _run(key_store.canonical_write(db, "twelvedata", "  KEY_TRIM  "))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "KEY_TRIM"

    def test_canonical_write_empty_clears(self):
        db = _DB()
        _run(key_store.canonical_write(db, "twelvedata", "SOMETHING"))
        _run(key_store.canonical_write(db, "twelvedata", ""))
        assert _run(key_store.canonical_read(db, "twelvedata")) is None


class TestLegacyFallback:
    def test_reads_from_market_settings_when_canonical_empty(self):
        db = _DB()
        _run(db["market_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"twelve_data": "LEGACY_MS"}}},
            upsert=True))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "LEGACY_MS"

    def test_reads_from_market_data_settings_when_canonical_empty(self):
        db = _DB()
        _run(db["market_data_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"twelvedata": "LEGACY_MD"}}},
            upsert=True))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "LEGACY_MD"

    def test_reads_from_forex_settings_when_canonical_empty(self):
        db = _DB()
        _run(db["forex_settings"].update_one(
            {"_id": "active"},
            {"$set": {"twelve_data_api_key": "LEGACY_FX"}}, upsert=True))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "LEGACY_FX"

    def test_canonical_wins_over_legacy(self):
        db = _DB()
        _run(key_store.canonical_write(db, "twelvedata", "CANONICAL"))
        _run(db["forex_settings"].update_one(
            {"_id": "active"},
            {"$set": {"twelve_data_api_key": "LEGACY_LOSER"}}, upsert=True))
        assert _run(key_store.canonical_read(db, "twelvedata")) == "CANONICAL"


class TestMigrateLegacyKeys:
    def test_migrates_when_canonical_empty(self):
        db = _DB()
        _run(db["market_data_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"twelvedata": "M_FROM_LEGACY"}}},
            upsert=True))
        summary = _run(key_store.migrate_legacy_keys(db))
        assert summary["twelvedata"]["migrated_from"] == "market_data_settings.api_keys.twelvedata"
        assert summary["twelvedata"]["migrated_len"] == len("M_FROM_LEGACY")
        # Canonical now has it
        assert _run(key_store.canonical_read(db, "twelvedata")) == "M_FROM_LEGACY"

    def test_skips_when_canonical_already_set(self):
        db = _DB()
        _run(key_store.canonical_write(db, "twelvedata", "ALREADY_HERE"))
        _run(db["forex_settings"].update_one(
            {"_id": "active"},
            {"$set": {"twelve_data_api_key": "SHOULD_NOT_MIGRATE"}}, upsert=True))
        summary = _run(key_store.migrate_legacy_keys(db))
        assert summary["twelvedata"]["migrated_from"] is None
        assert _run(key_store.canonical_read(db, "twelvedata")) == "ALREADY_HERE"

    def test_migrate_alphavantage_too(self):
        db = _DB()
        _run(db["market_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"alpha_vantage": "AV_LEGACY"}}}, upsert=True))
        summary = _run(key_store.migrate_legacy_keys(db))
        assert summary["alphavantage"]["migrated_from"] == "market_settings.api_keys.alpha_vantage"

    def test_migration_is_idempotent(self):
        db = _DB()
        _run(db["market_data_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"twelvedata": "IDEMPOTENT"}}}, upsert=True))
        _run(key_store.migrate_legacy_keys(db))
        _run(key_store.migrate_legacy_keys(db))     # second run — no-op
        assert _run(key_store.canonical_read(db, "twelvedata")) == "IDEMPOTENT"

    def test_ignores_whitespace_only_legacy_values(self):
        db = _DB()
        _run(db["market_data_settings"].update_one(
            {"_id": "default"},
            {"$set": {"api_keys": {"twelvedata": "   "}}}, upsert=True))
        summary = _run(key_store.migrate_legacy_keys(db))
        assert summary["twelvedata"]["migrated_from"] is None
        assert _run(key_store.canonical_read(db, "twelvedata")) is None


class TestNoBlockingBugs:
    def test_missing_provider_key_returns_none(self):
        db = _DB()
        assert _run(key_store.canonical_read(db, "twelvedata")) is None

    def test_unknown_provider_migration_is_safe(self):
        db = _DB()
        summary = _run(key_store.migrate_legacy_keys(db))
        # Sprint 15.0: finnhub is now a known provider alongside twelvedata / alphavantage
        assert set(summary.keys()) == {"twelvedata", "alphavantage", "finnhub"}
        assert all(v["migrated_from"] is None for v in summary.values())
