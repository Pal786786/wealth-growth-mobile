"""Sprint 14.1.2b — Canonical TwelveData / AlphaVantage key store.

The bug this module fixes:
==========================
The codebase has FOUR different admin UI pages that let super-admins save
a TwelveData key, and each writes to a DIFFERENT Mongo collection:

    Admin UI page          → endpoint                          → collection.field
    ─────────────────────────────────────────────────────────────────────────────
    AdminLiveMarket        → PUT /market_providers/api-key     → market_provider_config._id="active".twelvedata_api_key   (canonical — read by ProviderManager)
    AdminMarketSettings    → PUT /admin/market/settings        → market_settings._id="default".api_keys.twelve_data
    AdminMarketData        → PUT /admin/market_data/settings   → market_data_settings._id="default".api_keys.twelvedata
    AdminForexSettings     → PUT /admin/forex/settings         → forex_settings._id="active".twelve_data_api_key

Only the first location is read by the running `ProviderManager`. If a
super-admin saves the key on any of the other three pages the key lands in
Mongo but the manager NEVER sees it — the debug endpoint then correctly
reports `NOT_CONFIGURED`.

This module provides:

    1. `canonical_write(db, provider, key)`
       — writes the key to the canonical `market_provider_config` collection.
       Every legacy save-path now shadow-writes here.

    2. `canonical_read(db)`
       — returns whichever key IS set, checking the canonical collection
       first and falling back to each legacy location in priority order.
       Used by ProviderManager._load_config on startup, so even PRE-EXISTING
       keys saved on the wrong page get picked up on first boot.

    3. `migrate_legacy_keys(db)`
       — one-shot idempotent migration: reads every legacy collection and
       back-fills the canonical location if it is currently empty. Also
       run at ProviderManager.start().

The invariant is now:
  * A key saved from ANY of the four admin pages ends up in the canonical
    collection.
  * ProviderManager reads from the canonical collection first, and if that
    is empty, walks the legacy fallback chain (self-healing).
  * A backend restart never "loses" a key that was ever saved.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("market.providers.key_store")

CANONICAL_COLL = "market_provider_config"
CANONICAL_ID   = "active"

# ordered fallback chain: (collection, filter, path_to_key)
# path_to_key is dot-notated so we can descend into nested dicts.
LEGACY_LOCATIONS: Dict[str, Tuple[str, Dict[str, Any], str]] = {
    "twelvedata": [
        ("market_settings",       {"_id": "default"},         "api_keys.twelve_data"),
        ("market_data_settings",  {"_id": "default"},         "api_keys.twelvedata"),
        ("forex_settings",        {"_id": "active"},          "twelve_data_api_key"),
        ("api_settings",          {"api_name": "twelvedata"}, "api_key"),
        ("api_settings",          {"api_name": "market_data_twelvedata"}, "api_key"),
    ],
    "alphavantage": [
        ("market_settings",       {"_id": "default"},           "api_keys.alpha_vantage"),
        ("market_data_settings",  {"_id": "default"},           "api_keys.alphavantage"),
        ("api_settings",          {"api_name": "stock_market"}, "api_key"),
        ("api_settings",          {"api_name": "alphavantage"}, "api_key"),
    ],
    "finnhub": [
        ("api_settings",          {"api_name": "finnhub"}, "api_key"),
    ],
}


# --------------------------------------------------------------------------- #
def _get_nested(d: Optional[Dict[str, Any]], path: str) -> Optional[str]:
    if not d:
        return None
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, str):
        v = cur.strip()
        return v or None
    return None


# --------------------------------------------------------------------------- #
async def canonical_write(db, provider: str, key: str) -> None:
    """Persist `key` to the canonical `market_provider_config` document.
    Idempotent. `key=""` clears the field (upsert-safe)."""
    field = f"{provider}_api_key"
    val = (key or "").strip()
    await db[CANONICAL_COLL].update_one(
        {"_id": CANONICAL_ID}, {"$set": {field: val}}, upsert=True,
    )
    logger.info("key_store.canonical_write provider=%s len=%d", provider, len(val))


# --------------------------------------------------------------------------- #
async def canonical_read(db, provider: str) -> Optional[str]:
    """Return the key for `provider`, checking canonical first then walking
    the legacy fallback chain. Returns None if no key found anywhere.
    """
    doc = await db[CANONICAL_COLL].find_one({"_id": CANONICAL_ID})
    field = f"{provider}_api_key"
    can_val = (doc or {}).get(field)
    if isinstance(can_val, str) and can_val.strip():
        return can_val.strip()

    for coll, flt, path in LEGACY_LOCATIONS.get(provider, []):
        try:
            ldoc = await db[coll].find_one(flt)
        except Exception as _e:  # pragma: no cover
            logger.warning("key_store: read %s failed: %s", coll, _e)
            continue
        v = _get_nested(ldoc, path)
        if v:
            logger.info("key_store: found %s key in LEGACY %s.%s — will migrate", provider, coll, path)
            return v
    return None


# --------------------------------------------------------------------------- #
async def migrate_legacy_keys(db) -> Dict[str, Dict[str, Any]]:
    """One-shot idempotent migration. For every provider, if the canonical
    location is empty and a legacy location has a key, copy it into the
    canonical collection.

    Returns a summary dict for logging / audit purposes.
    """
    summary: Dict[str, Dict[str, Any]] = {}
    for provider in LEGACY_LOCATIONS.keys():
        entry: Dict[str, Any] = {"canonical_before": None, "migrated_from": None}
        doc = await db[CANONICAL_COLL].find_one({"_id": CANONICAL_ID})
        field = f"{provider}_api_key"
        can_val = (doc or {}).get(field, "")
        entry["canonical_before"] = bool(can_val and can_val.strip())

        if entry["canonical_before"]:
            summary[provider] = entry
            continue        # canonical already set — skip

        for coll, flt, path in LEGACY_LOCATIONS[provider]:
            try:
                ldoc = await db[coll].find_one(flt)
            except Exception:
                continue
            v = _get_nested(ldoc, path)
            if v:
                await canonical_write(db, provider, v)
                entry["migrated_from"] = f"{coll}.{path}"
                entry["migrated_len"]  = len(v)
                logger.info("key_store.migrate: %s ← %s.%s (len=%d)",
                            provider, coll, path, len(v))
                break
        summary[provider] = entry
    return summary
