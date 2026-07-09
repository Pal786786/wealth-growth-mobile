"""Copy Trading — Runtime configuration (Sprint 7B.2)

All Copy Engine defaults live in the mongo `copy_config` collection under
_id="active". Admin (Phase 3) can edit these without a redeploy. Public users
can read a subset via /meta and override per-copy via settings.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

_COLLECTION = "copy_config"
_KEY = "active"

# --- Follower defaults (per-copy settings) ---
DEFAULT_SETTINGS: Dict[str, Any] = {
    "mode": "multiplier",                     # 'fixed_lot' | 'multiplier' | 'equity_percent'
    "multiplier": 1.0,                        # 0.1 – 5.0
    "fixed_lot": 0.10,
    "equity_percent": 2.0,                    # % of follower equity per source lot
    # Risk protection
    "max_daily_loss_pct": 10.0,
    "max_drawdown_pct": 20.0,
    "max_open_trades": 10,
    "equity_protection_pct": 30.0,            # halt copy if equity dips below (100-pct)% of start
    "auto_close_on_equity_protection": True,
    "auto_pause_on_daily_loss": True,
    "resume_mode": "manual",                  # manual | auto
    # Trade size caps
    "max_lot_size": 5.00,
    "min_lot_size": 0.01,
    "slippage_pips": 5,
    # Behaviour flags
    "auto_copy_new_trades": True,
    "copy_existing_open_trades": False,
}
VALID_MODES = {"fixed_lot", "multiplier", "equity_percent"}
STATUSES = {"active", "paused", "stopped", "halted"}

# --- Global (admin-controlled) simulation defaults ---
DEFAULT_SIM_STATE: Dict[str, Any] = {
    "enabled": True,                          # master switch — set false to stop demo mode
    "speed": "normal",                        # slow | normal | fast
    # Base intervals in seconds per style (before speed multiplier)
    "style_intervals": {
        "Scalping":         [30, 90],
        "Day Trading":      [120, 360],
        "Swing":            [600, 1800],
        "Position":         [1800, 4200],
        "Trend Following":  [900, 2400],
        "Mean Reversion":   [300, 900],
        "News Trader":      [900, 1800],
        "Breakout":         [420, 1200],
        "Grid":             [60, 180],
        "Arbitrage":        [90, 240],
    },
    # Trade hold durations (seconds) — compressed vs style avg_holding_hours
    "style_hold": {
        "Scalping":         [30, 120],
        "Day Trading":      [180, 480],
        "Swing":            [900, 2400],
        "Position":         [2700, 6000],
        "Trend Following":  [1200, 3600],
        "Mean Reversion":   [300, 900],
        "News Trader":      [180, 900],
        "Breakout":         [600, 1800],
        "Grid":             [120, 300],
        "Arbitrage":        [90, 240],
    },
}

SPEED_MULTIPLIERS = {"slow": 2.0, "normal": 1.0, "fast": 0.3}


def _sanitize_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for k, v in patch.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if k == "mode":
            if v in VALID_MODES:
                clean[k] = v
        elif k == "resume_mode":
            if v in ("manual", "auto"):
                clean[k] = v
        elif isinstance(v, bool):
            clean[k] = v
        elif isinstance(v, (int, float)):
            if k in ("max_open_trades",):
                clean[k] = int(v)
            else:
                clean[k] = float(v)
    return clean


class CopyConfig:
    """Singleton wrapper backed by mongo. Cached in-process after first load."""

    def __init__(self, db):
        self.db = db
        self._cache: Optional[Dict[str, Any]] = None

    async def load(self, force: bool = False) -> Dict[str, Any]:
        if self._cache is not None and not force:
            return self._cache
        doc = await self.db[_COLLECTION].find_one({"_id": _KEY})
        if not doc:
            doc = {"_id": _KEY, "settings": DEFAULT_SETTINGS, "sim": DEFAULT_SIM_STATE}
            await self.db[_COLLECTION].insert_one(doc)
        # Merge with defaults so newly added keys always exist
        merged_settings = {**DEFAULT_SETTINGS, **(doc.get("settings") or {})}
        merged_sim = {**DEFAULT_SIM_STATE, **(doc.get("sim") or {})}
        self._cache = {"settings": merged_settings, "sim": merged_sim}
        return self._cache

    async def defaults(self) -> Dict[str, Any]:
        cfg = await self.load()
        return dict(cfg["settings"])

    async def sim_state(self) -> Dict[str, Any]:
        cfg = await self.load()
        return dict(cfg["sim"])

    async def update_defaults(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        clean = _sanitize_settings(patch)
        if not clean:
            return await self.defaults()
        current = await self.defaults()
        merged = {**current, **clean}
        await self.db[_COLLECTION].update_one(
            {"_id": _KEY}, {"$set": {"settings": merged}}, upsert=True
        )
        self._cache = None
        return merged

    async def update_sim(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = await self.sim_state()
        merged = {**current}
        if "enabled" in patch and isinstance(patch["enabled"], bool):
            merged["enabled"] = patch["enabled"]
        if "speed" in patch and patch["speed"] in SPEED_MULTIPLIERS:
            merged["speed"] = patch["speed"]
        await self.db[_COLLECTION].update_one(
            {"_id": _KEY}, {"$set": {"sim": merged}}, upsert=True
        )
        self._cache = None
        return merged
