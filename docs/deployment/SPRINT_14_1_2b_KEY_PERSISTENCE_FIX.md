# Sprint 14.1.2b — Fragmented Key Persistence Fix

**Status:** Root cause of "TwelveData key disappears" identified and fixed at every layer. `PUT /api/market_providers/api-key` was never the issue — the bug was that FOUR different admin UI pages wrote to FOUR different Mongo collections and only one was read by `ProviderManager`.

## Root cause matrix

| Admin UI page          | Endpoint                              | Collection.field                                          | ProviderManager reads? |
|------------------------|---------------------------------------|-----------------------------------------------------------|------------------------|
| **AdminLiveMarket**    | `PUT /api/market_providers/api-key`   | `market_provider_config._id="active".twelvedata_api_key`  | ✅ **CANONICAL**       |
| AdminMarketSettings    | `PUT /api/admin/market/settings`      | `market_settings._id="default".api_keys.twelve_data`      | ❌                     |
| AdminMarketData        | `PUT /api/admin/market_data/settings` | `market_data_settings._id="default".api_keys.twelvedata`  | ❌                     |
| AdminForexSettings     | `PUT /api/admin/forex/settings`       | `forex_settings._id="active".twelve_data_api_key`         | ❌                     |

## The fix (three layers)

### 1. Canonical key-store (`market_providers/key_store.py`)
- `canonical_write(db, provider, key)` — always writes to `market_provider_config`.
- `canonical_read(db, provider)` — reads canonical first, falls back through the legacy chain.
- `migrate_legacy_keys(db)` — one-shot idempotent migration; runs at `ProviderManager.start()`.

### 2. Startup migration
`ProviderManager._load_config()` now calls `migrate_legacy_keys(db)` BEFORE reading the config. Any legacy-saved key gets back-filled into `market_provider_config` on the FIRST boot after this deploy. Subsequent boots are no-ops (idempotent).

### 3. Live propagation from legacy endpoints
All three legacy PUT endpoints now, in addition to writing to their native collection:
- `canonical_write()` shadow-writes into `market_provider_config`.
- `market_providers.propagate_api_key()` pushes the new key into the running `ProviderManager` — no restart needed.

## Contract (before → after)

| Operator action                                                          | Before                              | After |
|--------------------------------------------------------------------------|-------------------------------------|-------|
| Save key via AdminLiveMarket                                             | Works                               | Works |
| Save key via AdminMarketSettings / AdminMarketData / AdminForexSettings  | Key silently ignored by manager     | Works, live within 1 refresh tick |
| Restart backend with a legacy-only key                                   | Key vanishes from manager           | Auto-migrated to canonical, loaded |
| Multiple pages set different values                                       | Undefined precedence                | Last write to canonical wins |

## Verified end-to-end in this session
- CASE A `PUT /admin/market_data/settings` → canonical match ✅, live manager fp updated ✅
- CASE B `PUT /admin/forex/settings` → canonical match ✅, live manager fp updated ✅
- CASE C `PUT /admin/market/settings` → canonical match ✅, live manager fp updated ✅
- Seeded legacy-only key → restart → canonical populated by migration → manager loads key ✅ (log: `market_providers.startup: loaded twelvedata api_key`).

## Tests (25 new, 0 regressions)
- `tests/test_key_store_persistence_iter42.py` — 14 unit tests (canonical/legacy/migration/idempotency).
- Debug endpoint contract tests updated to accept new verdicts (`INVALID_API_KEY`, `PROVIDER_5XX`).
- All 189+ market + forex tests pass locally.
