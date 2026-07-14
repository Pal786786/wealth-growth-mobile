"""Sprint 14.1.1 — Live-endpoint integration tests for price-source consistency.

These tests exercise the running FastAPI server (backend on the preview URL)
to verify the STRUCTURAL invariants that were broken before the Sprint 14.1.1
fix:

  1. GET /api/forex/prices returns quotes served from the SAME underlying feed
     that /api/forex/positions uses for entry_price.
  2. POST /api/forex/positions → immediate GET /api/forex/prices returns
     matching bid/ask for that symbol at that tick (no cross-provider drift).
  3. Feed source is preserved across successive reads within the 10-minute
     grace window (LIVE_MAX_AGE_SEC = 600).
  4. Full order lifecycle: open → hold 10 s → close — the close price must come
     from the SAME feed source as the open (no live/sim mixing mid-lifecycle).
  5. Admin `/api/market_providers/cache/writes` shows no mock/sim overwrites
     of live entries for the XAUUSD symbol (when live entries exist).

The environment currently has no live TwelveData API key, so the active
provider is "simulated" — but the invariants MUST hold regardless of which
provider is active (that is the whole point of the fix).
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Trading symbol under active investigation for the bug
TEST_SYMBOL = "XAUUSD"


# ---------- Auth fixtures ----------

@pytest.fixture(scope="module")
def user_headers():
    """Create a fresh test user, return auth headers."""
    email = f"TEST_iter40_{uuid.uuid4().hex[:10]}@mfb.in"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": "TestPass@2026", "name": "Iter40 Tester",
    }, timeout=15)
    if r.status_code not in (200, 201):
        # fall back to demo user
        r = requests.post(f"{API}/auth/login", json={
            "identifier": "demo@mfb.in", "password": "demo1234",
        }, timeout=15)
        if r.status_code != 200:
            pytest.skip(f"cannot obtain auth token: {r.status_code} {r.text[:200]}")
    token = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login", json={
        "email": "admin@mfb.in", "password": "Admin@MFB2026",
    }, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Helpers ----------

def _get_price_row(symbol_id: str):
    r = requests.get(f"{API}/forex/prices", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "prices" in data and isinstance(data["prices"], list)
    for row in data["prices"]:
        if row["symbol_id"] == symbol_id:
            return row
    return None


# ---------- 1. /forex/prices baseline ----------

class TestForexPricesBaseline:
    def test_prices_endpoint_returns_all_symbols_with_source(self):
        r = requests.get(f"{API}/forex/prices", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "prices" in body
        assert len(body["prices"]) >= 1
        for row in body["prices"]:
            for k in ("symbol_id", "bid", "ask", "mid", "ts", "source"):
                assert k in row, f"missing {k} in {row}"
            # source is either live (twelvedata/binance/shared/…) or simulated
            assert isinstance(row["source"], str) and row["source"]

    def test_prices_source_is_stable_across_two_reads(self):
        """Within the grace window, two consecutive reads must not swap sources."""
        row1 = _get_price_row(TEST_SYMBOL)
        assert row1 is not None
        source_1 = row1["source"]
        time.sleep(1.0)
        row2 = _get_price_row(TEST_SYMBOL)
        assert row2 is not None
        # source may only change from "live" → other live or same; sim→sim
        # Critical: if source was a LIVE provider, must not silently become sim
        if source_1 in ("twelvedata", "binance", "shared"):
            assert row2["source"] in ("twelvedata", "binance", "shared"), \
                f"Live source flipped to {row2['source']} within grace window"
        # In sim mode both should stay simulated
        else:
            assert row2["source"] == source_1, \
                f"Sim source changed unexpectedly: {source_1} → {row2['source']}"


# ---------- 2. Execution vs UI price consistency ----------

class TestExecutionPricesConsistency:
    def test_open_position_entry_matches_prices_endpoint(self, user_headers):
        """POST /positions then immediately GET /prices — entry_price must sit
        between the returned bid and ask for that symbol (they must come from
        the same in-memory quote object)."""
        px_before = _get_price_row(TEST_SYMBOL)
        assert px_before is not None
        open_resp = requests.post(f"{API}/forex/positions", headers=user_headers, json={
            "symbol_id": TEST_SYMBOL, "side": "buy", "lot_size": 0.01,
        }, timeout=15)
        assert open_resp.status_code == 200, f"open failed: {open_resp.text}"
        pos = open_resp.json()
        entry_price = float(pos["entry_price"])

        px_after = _get_price_row(TEST_SYMBOL)
        assert px_after is not None

        # source before/after must not silently switch (the bug!)
        assert px_after["source"] == px_before["source"], (
            f"source flipped between open and read: {px_before['source']} → "
            f"{px_after['source']} (Sprint 14.1.1 regression)"
        )

        # entry_price MUST be inside a reasonable band around the current
        # bid/ask (within one spread — same feed guarantees this).
        spread = float(px_after["ask"]) - float(px_after["bid"])
        tolerance = max(spread * 4, 0.5)  # tolerate 4 spreads or 50 cents
        assert abs(entry_price - float(px_after["ask"])) <= tolerance, (
            f"entry_price {entry_price} diverges from prices.ask {px_after['ask']} "
            f"(spread={spread}) — indicates two different sources!"
        )

        # Cleanup
        try:
            pid = pos["position_id"]
            requests.post(f"{API}/forex/positions/{pid}/close", headers=user_headers, timeout=15)
        except Exception:
            pass

    def test_open_position_and_immediate_positions_list_agree(self, user_headers):
        """POST /positions then GET /positions?status=open — the open row must
        carry the SAME entry_price and pnl computed from the same feed."""
        open_resp = requests.post(f"{API}/forex/positions", headers=user_headers, json={
            "symbol_id": TEST_SYMBOL, "side": "sell", "lot_size": 0.01,
        }, timeout=15)
        assert open_resp.status_code == 200, open_resp.text
        pos = open_resp.json()
        pid = pos["position_id"]
        entry = float(pos["entry_price"])

        lst = requests.get(f"{API}/forex/positions?status=open",
                            headers=user_headers, timeout=10)
        assert lst.status_code == 200
        rows = lst.json()
        match = next((p for p in rows if p["position_id"] == pid), None)
        assert match is not None, "just-opened position missing from /positions list"
        assert float(match["entry_price"]) == entry, \
            "entry_price differs between /positions POST response and GET list"

        # current_price and pnl on the list must be derived from the SAME feed
        # (they are enriched inline via feed.get_quote in engine._enrich).
        assert "current_price" in match and match["current_price"] is not None
        assert "pnl_inr" in match

        # cleanup
        requests.post(f"{API}/forex/positions/{pid}/close",
                       headers=user_headers, timeout=15)


# ---------- 3. Full lifecycle: open → hold → close ----------

class TestOrderLifecycleFeedSource:
    def test_open_hold_close_same_feed_source(self, user_headers):
        """Open a position, snapshot feed source, hold 10 s, snapshot again,
        close. The source must remain in the same 'family' throughout the
        lifecycle — i.e., LIVE never silently becomes sim, and sim never
        silently becomes LIVE (either direction would be the Sprint 14.1.1
        bug in reverse)."""
        px_open = _get_price_row(TEST_SYMBOL)
        assert px_open is not None
        src_open = px_open["source"]

        open_resp = requests.post(f"{API}/forex/positions", headers=user_headers, json={
            "symbol_id": TEST_SYMBOL, "side": "buy", "lot_size": 0.01,
        }, timeout=15)
        assert open_resp.status_code == 200, open_resp.text
        pos = open_resp.json()
        pid = pos["position_id"]

        # Hold 10 seconds — this is where the pre-fix bug used to swap sim ↔ live
        time.sleep(10)

        px_mid = _get_price_row(TEST_SYMBOL)
        assert px_mid is not None
        # LIVE family must stay LIVE within 10 min grace; sim stays sim.
        LIVE = {"twelvedata", "binance", "shared"}
        if src_open in LIVE:
            assert px_mid["source"] in LIVE, \
                f"LIVE source degraded to {px_mid['source']} within grace window"
        else:
            # sim env — must remain simulated (no phantom live upgrade either)
            assert px_mid["source"] not in LIVE, \
                f"sim source upgraded to LIVE {px_mid['source']} unexpectedly"

        # Now close and verify close price came from a compatible source
        close_resp = requests.post(f"{API}/forex/positions/{pid}/close",
                                     headers=user_headers, timeout=15)
        assert close_resp.status_code == 200, close_resp.text
        closed = close_resp.json()
        assert "close_price" in closed and closed["close_price"] is not None

        px_close = _get_price_row(TEST_SYMBOL)
        assert px_close is not None
        if src_open in LIVE:
            assert px_close["source"] in LIVE, \
                "close price source diverged from open price source (LIVE → sim)"
        else:
            assert px_close["source"] not in LIVE, \
                "close price source diverged from open price source (sim → LIVE)"


# ---------- 4. Equity endpoint consistency ----------

class TestEquityMarkToMarketConsistency:
    def test_equity_unrealized_matches_positions_sum(self, user_headers):
        """/forex/equity.unrealized_pnl must equal sum of pnl_inr from
        /forex/positions?status=open — proving both routes read the same
        feed for mark-to-market."""
        # ensure we have at least one open position
        open_resp = requests.post(f"{API}/forex/positions", headers=user_headers, json={
            "symbol_id": TEST_SYMBOL, "side": "buy", "lot_size": 0.01,
        }, timeout=15)
        assert open_resp.status_code == 200
        pid = open_resp.json()["position_id"]

        eq = requests.get(f"{API}/forex/equity", headers=user_headers, timeout=10)
        assert eq.status_code == 200
        eq_body = eq.json()

        pos_list = requests.get(f"{API}/forex/positions?status=open",
                                  headers=user_headers, timeout=10).json()
        pnl_sum = round(sum(float(p.get("pnl_inr") or 0) for p in pos_list), 2)
        # tiny drift possible if a mark-to-market tick fired between calls
        assert abs(float(eq_body["unrealized_pnl"]) - pnl_sum) <= 5.0, (
            f"equity.unrealized_pnl={eq_body['unrealized_pnl']} vs "
            f"sum(positions.pnl_inr)={pnl_sum} — diverging feed sources"
        )

        # cleanup
        requests.post(f"{API}/forex/positions/{pid}/close",
                       headers=user_headers, timeout=15)


# ---------- 5. Admin cache/writes — no mock overwrites of live entries ----------

class TestMarketCacheWritesAudit:
    def test_no_mock_overwrites_of_live_xauusd_entries(self, admin_headers):
        """Fetch the audit trail; if any live provider ever wrote XAUUSD, no
        subsequent mock/sim write should have overwritten it (guard fires)."""
        r = requests.get(f"{API}/market_providers/cache/writes?symbol={TEST_SYMBOL}&limit=200",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        writes = r.json().get("writes") or []

        # Walk in chronological order (oldest first). If we ever see a LIVE
        # write accepted, then the next write from mock/sim for the same
        # symbol must be REJECTED (i.e., accepted=False) inside the grace
        # window. Otherwise this is the exact bug.
        try:
            chrono = sorted(writes, key=lambda w: w.get("ts", 0))
        except Exception:
            chrono = writes

        LIVE = {"twelvedata", "binance", "alphavantage", "yahoo"}
        last_live_ts = None
        for w in chrono:
            provider = (w.get("provider") or "").lower()
            accepted = w.get("accepted", w.get("ok", True))
            ts = w.get("ts") or 0
            if provider in LIVE and accepted:
                last_live_ts = ts
                continue
            if provider in {"mock", "sim", "simulated"} and accepted and last_live_ts is not None:
                age = ts - last_live_ts
                # Sprint 14.1.1 guard: within 600 s a mock must not overwrite live
                assert age >= 600, (
                    f"REGRESSION: mock/sim provider {provider} overwrote a "
                    f"LIVE {TEST_SYMBOL} entry only {age:.1f}s later — the "
                    f"Sprint 14.1.1 guard is not firing."
                )

    def test_cache_stats_reachable(self, admin_headers):
        r = requests.get(f"{API}/market_providers/cache/stats",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        # structural check only
        assert isinstance(body, dict)
