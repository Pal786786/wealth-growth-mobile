"""My Funding Bank backend API tests"""
import time
import uuid
import requests
import pytest

from conftest import API


# ---------- Health ----------
def test_root_health(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Auth ----------
class TestAuth:
    def test_signup_new_user_returns_token_and_wallet_seeded(self, session):
        uniq = uuid.uuid4().hex[:8]
        email = f"TEST_{uniq}@mfb.in"
        mobile = f"7{uniq[:9]}"[:10].ljust(10, "0")
        payload = {
            "full_name": "TEST User",
            "email": email,
            "mobile": mobile,
            "password": "test1234",
        }
        r = session.post(f"{API}/auth/signup", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and len(data["token"]) > 20
        u = data["user"]
        assert u["email"] == email
        assert u["mobile"] == mobile
        assert u["kyc_status"] == "pending"
        assert u["referral_code"].startswith("MFB")
        assert "_id" not in u

        token = data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Wallet should be seeded with 5000
        rw = session.get(f"{API}/wallet", headers=headers)
        assert rw.status_code == 200
        assert rw.json()["balance"] == 5000.0
        assert rw.json()["currency"] == "INR"

        # Rewards should include 100 points
        rr = session.get(f"{API}/rewards", headers=headers)
        assert rr.status_code == 200
        assert rr.json()["reward_points"] >= 100

        # Stash for other tests
        pytest.new_user = {"email": email, "mobile": mobile, "token": token, "headers": headers, "user_id": u["user_id"]}

    def test_signup_duplicate_rejected(self, session):
        # Should rely on the previous test's email
        nu = getattr(pytest, "new_user", None)
        if not nu:
            pytest.skip("Previous signup test missing")
        r = session.post(f"{API}/auth/signup", json={
            "full_name": "Dup", "email": nu["email"], "mobile": nu["mobile"], "password": "x"
        })
        assert r.status_code == 400

    def test_login_with_email(self, session):
        r = session.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"})
        assert r.status_code == 200, r.text
        assert "token" in r.json()

    def test_login_with_mobile(self, session):
        r = session.post(f"{API}/auth/login", json={"identifier": "9999999999", "password": "demo1234"})
        assert r.status_code == 200, r.text
        assert "token" in r.json()

    def test_login_invalid_password(self, session):
        r = session.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "wrong"})
        assert r.status_code == 401

    def test_otp_request_returns_demo_otp(self, session):
        mobile = "8" + str(int(time.time()))[-9:]
        r = session.post(f"{API}/auth/otp/request", json={"mobile": mobile})
        assert r.status_code == 200
        body = r.json()
        assert body["sent"] is True
        assert body["demo_otp"] == "123456"
        pytest.otp_mobile = mobile

    def test_otp_verify_creates_new_user(self, session):
        mobile = getattr(pytest, "otp_mobile", None)
        assert mobile, "OTP request must have run"
        r = session.post(f"{API}/auth/otp/verify", json={"mobile": mobile, "otp": "123456", "full_name": "OTP TEST"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data
        assert data["user"]["mobile"] == mobile

    def test_otp_verify_wrong_code_fails(self, session):
        mobile = "8" + str(int(time.time()))[-9:] + "1"
        mobile = mobile[:10]
        session.post(f"{API}/auth/otp/request", json={"mobile": mobile})
        r = session.post(f"{API}/auth/otp/verify", json={"mobile": mobile, "otp": "000000", "full_name": "X"})
        assert r.status_code == 401

    def test_me_requires_token(self, session):
        r = session.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, session, demo_headers):
        r = session.get(f"{API}/auth/me", headers=demo_headers)
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == "demo@mfb.in"
        assert "_id" not in u
        assert "password" not in u


# ---------- Auth protection ----------
class TestAuthProtection:
    @pytest.mark.parametrize("path,method,payload", [
        ("/wallet", "GET", None),
        ("/wallet/transactions", "GET", None),
        ("/wallet/send", "POST", {"recipient": "x", "amount": 1}),
        ("/wallet/recharge", "POST", {"operator": "Jio", "mobile": "1", "amount": 1}),
        ("/wallet/billpay", "POST", {"biller_type": "electricity", "biller_name": "x", "consumer_number": "1", "amount": 1}),
        ("/invest/buy", "POST", {"asset_id": "x", "asset_type": "stock", "asset_name": "x", "amount": 1}),
        ("/invest/portfolio", "GET", None),
        ("/travel/book", "POST", {"booking_type": "flight", "travel_date": "2026-01-01", "amount": 1, "title": "t"}),
        ("/insurance/policies", "GET", None),
        ("/rewards", "GET", None),
        ("/profile/kyc", "POST", {"pan": "x", "aadhaar": "x"}),
        ("/dashboard/summary", "GET", None),
    ])
    def test_unauth_returns_401(self, session, path, method, payload):
        if method == "GET":
            r = session.get(f"{API}{path}")
        else:
            r = session.post(f"{API}{path}", json=payload)
        assert r.status_code == 401, f"{path} returned {r.status_code}"


# ---------- Wallet ----------
class TestWallet:
    def test_get_wallet(self, session, demo_headers):
        r = session.get(f"{API}/wallet", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert "balance" in d and isinstance(d["balance"], (int, float))
        assert d["currency"] == "INR"

    def test_send_money_debits_wallet_and_creates_tx(self, session, demo_headers):
        before = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        amount = 50.0
        r = session.post(f"{API}/wallet/send", headers=demo_headers,
                         json={"recipient": "9876543210", "amount": amount, "note": "TEST send"})
        if r.status_code == 400:
            pytest.skip("Insufficient balance")
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True
        tx = r.json()["tx"]
        assert tx["type"] == "debit" and tx["category"] == "send"
        after = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        assert abs(after - (before - amount)) < 0.01

        # verify tx persisted
        tlist = session.get(f"{API}/wallet/transactions", headers=demo_headers).json()
        assert any(t["tx_id"] == tx["tx_id"] for t in tlist)

    def test_send_money_insufficient_balance(self, session, demo_headers):
        r = session.post(f"{API}/wallet/send", headers=demo_headers,
                         json={"recipient": "x", "amount": 99999999})
        assert r.status_code == 400

    def test_send_money_invalid_amount(self, session, demo_headers):
        r = session.post(f"{API}/wallet/send", headers=demo_headers,
                         json={"recipient": "x", "amount": -5})
        assert r.status_code == 400

    def test_recharge_creates_debit_and_cashback(self, session, demo_headers):
        before = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        amount = 200.0
        r = session.post(f"{API}/wallet/recharge", headers=demo_headers,
                         json={"operator": "Jio", "mobile": "9999999999", "amount": amount, "plan_name": "TEST"})
        if r.status_code == 400:
            pytest.skip("Insufficient balance")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        expected_cashback = round(amount * 0.02, 2)
        assert body["cashback"] == expected_cashback
        after = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        # debit -200, credit +4 cashback => net -196
        assert abs(after - (before - amount + expected_cashback)) < 0.01

    def test_billpay(self, session, demo_headers):
        before = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        r = session.post(f"{API}/wallet/billpay", headers=demo_headers, json={
            "biller_type": "electricity", "biller_name": "BSES", "consumer_number": "12345", "amount": 75.0
        })
        if r.status_code == 400:
            pytest.skip("Insufficient balance")
        assert r.status_code == 200
        after = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        assert abs(after - (before - 75.0)) < 0.01


# ---------- Stripe ----------
class TestStripeTopup:
    def test_create_session_returns_checkout_url(self, session, demo_headers):
        r = session.post(f"{API}/wallet/topup/create-session", headers=demo_headers,
                         json={"amount": 100.0, "platform": "web"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "checkout_url" in data and data["checkout_url"].startswith("https://")
        assert "session_id" in data and data["session_id"].startswith("cs_")

    def test_invalid_amount_rejected(self, session, demo_headers):
        r = session.post(f"{API}/wallet/topup/create-session", headers=demo_headers,
                         json={"amount": 5})
        assert r.status_code == 400


# ---------- Invest ----------
class TestInvest:
    def test_mutual_funds(self, session):
        r = session.get(f"{API}/invest/mutual-funds")
        assert r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0
        assert "nav" in r.json()[0]

    def test_stocks(self, session):
        r = session.get(f"{API}/invest/stocks")
        assert r.status_code == 200 and len(r.json()) > 0
        assert "symbol" in r.json()[0]

    def test_gold_price(self, session):
        r = session.get(f"{API}/invest/gold-price")
        assert r.status_code == 200
        assert r.json()["price_per_gram"] > 0

    def test_fds(self, session):
        r = session.get(f"{API}/invest/fixed-deposits")
        assert r.status_code == 200 and len(r.json()) > 0

    def test_govt_schemes(self, session):
        r = session.get(f"{API}/invest/govt-schemes")
        assert r.status_code == 200 and len(r.json()) > 0

    def test_buy_and_portfolio(self, session, demo_headers):
        before = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        r = session.post(f"{API}/invest/buy", headers=demo_headers, json={
            "asset_id": "mf_axis_bluechip", "asset_type": "mutual_fund",
            "asset_name": "Axis Bluechip Fund", "amount": 500.0, "sip": False,
        })
        if r.status_code == 400:
            pytest.skip("Insufficient balance")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["holding"]["asset_id"] == "mf_axis_bluechip"
        after = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        assert abs(after - (before - 500.0)) < 0.01

        # Portfolio reflects the holding
        rp = session.get(f"{API}/invest/portfolio", headers=demo_headers)
        assert rp.status_code == 200
        pf = rp.json()
        assert pf["total_invested"] >= 500.0
        assert pf["total_current"] >= pf["total_invested"]  # mock multipliers >1
        assert "returns_pct" in pf and "by_type" in pf
        assert any(h["asset_id"] == "mf_axis_bluechip" for h in pf["holdings"])


# ---------- Travel ----------
class TestTravel:
    def test_flights_no_auth(self, session):
        r = session.get(f"{API}/travel/flights")
        assert r.status_code == 200 and len(r.json()) > 0
        assert "airline" in r.json()[0]

    def test_hotels_no_auth(self, session):
        r = session.get(f"{API}/travel/hotels")
        assert r.status_code == 200 and len(r.json()) > 0
        assert "name" in r.json()[0]

    def test_flights_filter(self, session):
        r = session.get(f"{API}/travel/flights", params={"from_loc": "DEL", "to_loc": "BLR"})
        assert r.status_code == 200 and all(f["from"] == "DEL" and f["to"] == "BLR" for f in r.json())

    def test_book(self, session, demo_headers):
        before = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        if before < 100:
            pytest.skip("Wallet too low")
        r = session.post(f"{API}/travel/book", headers=demo_headers, json={
            "booking_type": "flight", "from_loc": "DEL", "to_loc": "BLR",
            "travel_date": "2026-02-15", "passengers": 1, "amount": 50.0,
            "title": "TEST IndiGo 6E-203 DEL->BLR"
        })
        assert r.status_code == 200, r.text
        booking = r.json()["booking"]
        assert booking["status"] == "confirmed"
        assert "_id" not in booking


# ---------- Insurance ----------
class TestInsurance:
    def test_list_plans(self, session):
        r = session.get(f"{API}/insurance/plans")
        assert r.status_code == 200 and len(r.json()) > 0

    def test_buy_and_list_policies(self, session, demo_headers):
        # Use cheapest plan (travel 2500); ensure balance
        balance = session.get(f"{API}/wallet", headers=demo_headers).json()["balance"]
        if balance < 2500:
            pytest.skip("Wallet too low for insurance")
        r = session.post(f"{API}/insurance/buy", headers=demo_headers, params={"plan_id": "ins_travel"})
        assert r.status_code == 200, r.text
        policy = r.json()["policy"]
        assert policy["plan_id"] == "ins_travel"
        assert policy["status"] == "active"

        rp = session.get(f"{API}/insurance/policies", headers=demo_headers)
        assert rp.status_code == 200
        assert any(p["policy_id"] == policy["policy_id"] for p in rp.json())

    def test_buy_unknown_plan(self, session, demo_headers):
        r = session.post(f"{API}/insurance/buy", headers=demo_headers, params={"plan_id": "ins_unknown_xxxx"})
        assert r.status_code == 404


# ---------- Rewards & Referral ----------
class TestRewards:
    def test_rewards(self, session, demo_headers):
        r = session.get(f"{API}/rewards", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("reward_points", "cashback_earned", "referral_code", "referrals_count", "badges"):
            assert k in d
        assert isinstance(d["badges"], list)

    def test_leaderboard(self, session):
        r = session.get(f"{API}/referral/leaderboard")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Profile / KYC ----------
class TestProfile:
    def test_submit_kyc(self, session, demo_headers):
        r = session.post(f"{API}/profile/kyc", headers=demo_headers,
                         json={"pan": "ABCDE1234F", "aadhaar": "123412341234"})
        assert r.status_code == 200
        assert r.json()["kyc_status"] == "verified"

        r2 = session.get(f"{API}/auth/me", headers=demo_headers)
        assert r2.json()["kyc_status"] == "verified"


# ---------- Dashboard ----------
class TestDashboard:
    def test_dashboard_summary(self, session, demo_headers):
        r = session.get(f"{API}/dashboard/summary", headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ("wallet_balance", "portfolio_value", "portfolio_invested",
                  "gold_value", "recent_transactions", "trending_stocks", "trending_funds"):
            assert k in d
        assert isinstance(d["recent_transactions"], list)
        # No mongodb _id leaks
        for tx in d["recent_transactions"]:
            assert "_id" not in tx
