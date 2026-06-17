"""Super-App backend tests — Travel (Bus/Train + Cancel), Insurance (Calculator + Compare),
Rewards (Tier + Redeem + Cashback), Admin super endpoints, plus regression.
"""
import os
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def demo_token(s):
    r = s.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
    if r.status_code != 200:
        pytest.skip(f"Demo login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "Admin@MFB2026"})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_user_id(s, demo_headers):
    r = s.get(f"{API}/auth/me", headers=demo_headers)
    if r.status_code != 200:
        # Some implementations use /users/me
        r = s.get(f"{API}/users/me", headers=demo_headers)
    if r.status_code == 200:
        d = r.json()
        return d.get("user_id") or d.get("id") or d.get("user", {}).get("user_id")
    return None


def _topup_demo(s, headers, amount: float):
    """Demo top-up flow: create session, then poll status to complete."""
    r = s.post(f"{API}/wallet/topup/create-session", headers=headers, json={"amount": amount, "platform": "native"})
    assert r.status_code == 200, f"topup create-session failed: {r.text}"
    sid = r.json()["session_id"]
    r2 = s.get(f"{API}/wallet/topup/status/{sid}", headers=headers)
    assert r2.status_code == 200, f"topup status failed: {r2.text}"
    return r2.json()


# ============================================================
# TRAVEL — Bus / Train listing & filtering
# ============================================================
class TestTravelListings:
    def test_buses_list(self, s):
        r = s.get(f"{API}/travel/buses")
        assert r.status_code == 200
        buses = r.json()
        assert isinstance(buses, list)
        assert len(buses) >= 5
        b = buses[0]
        for k in ("operator", "from", "to", "depart", "arrive", "price", "seats_left", "rating"):
            assert k in b, f"missing key {k} in bus row"

    def test_trains_list(self, s):
        r = s.get(f"{API}/travel/trains")
        assert r.status_code == 200
        trains = r.json()
        assert isinstance(trains, list)
        assert len(trains) >= 5
        t = trains[0]
        for k in ("number", "name", "classes", "prices"):
            assert k in t, f"missing key {k} in train row"
        assert isinstance(t["prices"], dict) and len(t["prices"]) > 0

    def test_buses_filter_bengaluru(self, s):
        r = s.get(f"{API}/travel/buses", params={"from_loc": "Bengaluru"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        assert all(b["from"].lower() == "bengaluru" for b in rows)


# ============================================================
# TRAVEL — Booking + Cancellation
# ============================================================
class TestTravelBookCancel:
    @pytest.fixture(scope="class")
    def fresh_booking(self, s, demo_headers):
        # Top up enough wallet
        _topup_demo(s, demo_headers, 5000)
        # Pick a bus
        buses = s.get(f"{API}/travel/buses").json()
        bus = buses[0]
        travel_date = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
        payload = {
            "booking_type": "bus",
            "from_loc": bus["from"],
            "to_loc": bus["to"],
            "travel_date": travel_date,
            "passengers": 1,
            "amount": float(bus["price"]),
            "title": f"{bus['operator']} {bus['from']}->{bus['to']}",
            "meta": {"bus_id": bus["id"]},
        }
        r = s.post(f"{API}/travel/book", headers=demo_headers, json=payload)
        assert r.status_code == 200, f"booking failed: {r.text}"
        data = r.json()
        assert data.get("success") is True
        assert "booking" in data and "booking_id" in data["booking"]
        assert "cashback" in data
        cb = data["cashback"]
        assert cb.get("points_added", 0) > 0, f"cashback points missing: {cb}"
        assert cb.get("cashback_amount", 0) > 0, f"cashback amount missing: {cb}"
        return data["booking"]

    def test_book_returns_cashback(self, fresh_booking):
        assert fresh_booking["status"] == "confirmed"
        assert fresh_booking["amount"] > 0

    def test_cancel_booking_credits_refund(self, s, demo_headers, fresh_booking):
        # Travel date is 10 days away → expect 90% refund
        bid = fresh_booking["booking_id"]
        # Get wallet pre-cancel
        w_before = s.get(f"{API}/wallet", headers=demo_headers).json()
        bal_before = w_before["balance"]
        r = s.post(f"{API}/travel/cancel/{bid}", headers=demo_headers, json={"reason": "test"})
        assert r.status_code == 200, f"cancel failed: {r.text}"
        d = r.json()
        assert d["status"] == "cancelled"
        assert d["refund_pct"] == 90, f"expected 90%, got {d['refund_pct']}"
        expected_refund = round(fresh_booking["amount"] * 0.9, 2)
        assert abs(d["refund_amount"] - expected_refund) < 0.5
        # Wallet bumped
        w_after = s.get(f"{API}/wallet", headers=demo_headers).json()
        assert w_after["balance"] >= bal_before + expected_refund - 0.5
        # Refund transaction exists
        txs = s.get(f"{API}/wallet/transactions", headers=demo_headers).json()
        assert any(t.get("category") == "refund" and abs(t.get("amount", 0) - expected_refund) < 0.5 for t in txs), \
            "refund transaction not found"

    def test_cancel_already_cancelled_returns_400(self, s, demo_headers, fresh_booking):
        bid = fresh_booking["booking_id"]
        r = s.post(f"{API}/travel/cancel/{bid}", headers=demo_headers, json={"reason": "again"})
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_cancel_nonexistent_returns_404(self, s, demo_headers):
        r = s.post(f"{API}/travel/cancel/bkg_doesnotexist123", headers=demo_headers, json={"reason": "x"})
        assert r.status_code == 404


# ============================================================
# INSURANCE — Premium Calculator + Compare
# ============================================================
class TestInsuranceCalc:
    def test_quote_health(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "health", "age": 35, "cover": 500000})
        assert r.status_code == 200
        d = r.json()
        for k in ("estimated_premium", "gst", "total_annual_premium", "monthly_emi", "breakdown", "disclaimer", "mode"):
            assert k in d, f"missing key {k}"
        assert d["mode"] == "demo"
        assert d["total_annual_premium"] > 0
        assert d["monthly_emi"] > 0
        assert isinstance(d["breakdown"], list)

    def test_quote_life(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "life", "age": 40, "cover": 10000000})
        assert r.status_code == 200
        assert r.json()["total_annual_premium"] > 0

    def test_quote_motor(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "motor", "cover": 600000, "vehicle_age": 3})
        assert r.status_code == 200
        assert r.json()["total_annual_premium"] > 0

    def test_quote_travel(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "travel", "trip_days": 14, "age": 35})
        assert r.status_code == 200
        assert r.json()["total_annual_premium"] > 0

    def test_quote_invalid_plan(self, s):
        r = s.post(f"{API}/insurance/quote", json={"plan_type": "garbage", "cover": 100000})
        assert r.status_code == 400

    def test_compare_health(self, s):
        # ids from INSURANCE_PLANS seed
        r = s.get(f"{API}/insurance/compare", params={"plan_type": "health", "ids": "ins_health_basic,ins_health_plus"})
        assert r.status_code in (200, 404), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 200:
            d = r.json()
            assert "plans" in d and len(d["plans"]) >= 2
            assert "matrix_keys" in d
        else:
            # Verify shape of 404
            assert "detail" in r.json()

    def test_insurance_buy_returns_cashback(self, s, demo_headers):
        _topup_demo(s, demo_headers, 10000)
        r = s.post(f"{API}/insurance/buy", headers=demo_headers, params={"plan_id": "ins_travel"})
        assert r.status_code == 200, f"insurance buy failed: {r.text}"
        d = r.json()
        assert d.get("success") is True
        assert "policy" in d and d["policy"]["status"] == "active"
        assert "cashback" in d
        assert d["cashback"].get("points_added", 0) > 0


# ============================================================
# REWARDS — Tier + Redeem
# ============================================================
class TestRewards:
    def test_get_tier(self, s, demo_headers):
        r = s.get(f"{API}/rewards/tier", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert "current" in d
        cur = d["current"]
        for k in ("id", "name", "min", "rate", "color"):
            assert k in cur
        assert "current_points" in d
        assert 0 <= d["progress_pct"] <= 100

    def test_redeem_invalid_amount(self, s, demo_headers):
        # 50 is below 100
        r = s.post(f"{API}/rewards/redeem", headers=demo_headers, params={"amount": 50})
        assert r.status_code == 400

    def test_redeem_non_multiple(self, s, demo_headers):
        r = s.post(f"{API}/rewards/redeem", headers=demo_headers, params={"amount": 150})
        assert r.status_code == 400

    def test_redeem_success_or_insufficient(self, s, demo_headers):
        tier = s.get(f"{API}/rewards/tier", headers=demo_headers).json()
        pts = tier["current_points"]
        if pts >= 100:
            r = s.post(f"{API}/rewards/redeem", headers=demo_headers, params={"amount": 100})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["success"] is True
            assert d["cash_credited"] == 10
            # Verify transaction
            txs = s.get(f"{API}/wallet/transactions", headers=demo_headers).json()
            assert any(t.get("category") == "redeem" for t in txs), "redeem tx not found"
        else:
            r = s.post(f"{API}/rewards/redeem", headers=demo_headers, params={"amount": 100})
            assert r.status_code == 400


# ============================================================
# ADMIN — super-app endpoints
# ============================================================
class TestAdminSuper:
    def test_all_bookings(self, s, admin_headers):
        r = s.get(f"{API}/admin/super/bookings", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_all_policies(self, s, admin_headers):
        r = s.get(f"{API}/admin/super/policies", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_rewards_summary(self, s, admin_headers):
        r = s.get(f"{API}/admin/super/rewards-summary", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_points_in_circulation", "total_cashback_paid", "cashback_count", "top_referrers", "tiers"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["tiers"], list) and len(d["tiers"]) >= 5

    def test_grant_bonus(self, s, admin_headers, demo_user_id, demo_headers):
        if not demo_user_id:
            pytest.skip("Could not resolve demo user_id")
        # Snapshot before
        tier_before = s.get(f"{API}/rewards/tier", headers=demo_headers).json()
        w_before = s.get(f"{API}/wallet", headers=demo_headers).json()
        r = s.post(f"{API}/admin/super/grant-bonus", headers=admin_headers,
                   json={"user_id": demo_user_id, "points": 50, "cashback": 10})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("success") is True
        tier_after = s.get(f"{API}/rewards/tier", headers=demo_headers).json()
        w_after = s.get(f"{API}/wallet", headers=demo_headers).json()
        assert tier_after["current_points"] >= tier_before["current_points"] + 50
        assert w_after["balance"] >= w_before["balance"] + 10 - 0.5


# ============================================================
# REGRESSION — Existing endpoints still work
# ============================================================
class TestRegression:
    def test_auth_login(self, s):
        r = s.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_wallet(self, s, demo_headers):
        r = s.get(f"{API}/wallet", headers=demo_headers)
        assert r.status_code == 200
        assert "balance" in r.json()

    def test_ai_suggestions(self, s, demo_headers):
        r = s.get(f"{API}/invest/ai-suggestions", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert "recommendations" in d
        assert d.get("mode") in ("live", "demo")

    def test_app_api_status(self, s):
        r = s.get(f"{API}/app/api-status")
        assert r.status_code == 200

    def test_admin_api_settings(self, s, admin_headers):
        r = s.get(f"{API}/admin/api-settings", headers=admin_headers)
        assert r.status_code == 200

    def test_travel_flights(self, s):
        r = s.get(f"{API}/travel/flights")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_travel_hotels(self, s):
        r = s.get(f"{API}/travel/hotels")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_insurance_plans(self, s):
        r = s.get(f"{API}/insurance/plans")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_insurance_policies(self, s, demo_headers):
        r = s.get(f"{API}/insurance/policies", headers=demo_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_rewards(self, s, demo_headers):
        r = s.get(f"{API}/rewards", headers=demo_headers)
        assert r.status_code == 200
