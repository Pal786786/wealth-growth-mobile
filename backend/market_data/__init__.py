"""Market Data subsystem — Sprint 7 Slice 1

Public surface:
  from market_data import attach
  attach(app, db, get_current_user, get_current_admin)

Provides:
  - Scalable instrument catalog (200+ symbols across 8 categories today,
    extensible to thousands with no schema change).
  - Provider abstraction: Mock + TwelveData (skeleton), pluggable for
    AlphaVantage / Finnhub / Polygon / Kite Connect / Upstox later.
  - Transport abstraction: PollingTransport (default) + WebSocketTransport
    (falls back to polling until provider WS is wired).
  - Favorites + Recently Viewed (persisted per user).
  - Public WebSocket endpoint /api/market_data/ws/stream for live streaming
    that hides the transport choice from the frontend.
  - Admin endpoints under /api/admin/market_data/* for provider + transport
    configuration.

Does NOT touch the existing Forex trading engine (backend/forex/*) — those
routes and behaviours remain untouched.
"""
from .routes import attach

__all__ = ["attach"]
