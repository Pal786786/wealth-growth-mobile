"""Sprint 11 — Mutual Funds & SIP Platform backend tests."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------------- fixtures ---------------- #
@pytest.fixture(scope="module")
def demo_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": "demo@mfb.in", "password": "demo1234"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_funds(demo_headers):
    r = requests.get(f"{API}/mf/funds", headers=demo_headers, params={"limit": 5}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---------------- tests ---------------- #
def test_user_config(demo_headers):
    r = requests.get(f"{API}/mf/config", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "min_lumpsum_inr" in j and "min_sip_inr" in j


def test_list_funds_and_filters(demo_headers):
    r = requests.get(f"{API}/mf/funds", headers=demo_headers, params={"limit": 5}, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["total"] >= 20
    assert len(j["items"]) == 5
    # By category
    r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                      params={"category": "large_cap", "limit": 20}, timeout=15)
    assert r.status_code == 200
    assert all(x["category"] == "large_cap" for x in r.json()["items"])
    # Sort by rating
    r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                      params={"sort": "rating_desc", "limit": 3}, timeout=15)
    ratings = [x["star_rating"] for x in r.json()["items"]]
    assert ratings == sorted(ratings, reverse=True)


def test_amcs(demo_headers):
    r = requests.get(f"{API}/mf/amcs", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 5


def test_fund_detail_and_chart(demo_headers, sample_funds):
    f = sample_funds[0]
    r = requests.get(f"{API}/mf/funds/{f['fund_id']}", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j["fund_id"] == f["fund_id"] and "holdings" in j
    # Chart
    r = requests.get(f"{API}/mf/funds/{f['fund_id']}/chart", headers=demo_headers,
                      params={"window": "1M"}, timeout=10)
    assert r.status_code == 200
    assert len(r.json()["points"]) >= 10


def test_compare(demo_headers, sample_funds):
    r = requests.post(f"{API}/mf/compare", headers=demo_headers,
                       json={"fund_ids": [sample_funds[0]["fund_id"], sample_funds[1]["fund_id"]]},
                       timeout=10)
    assert r.status_code == 200
    assert len(r.json()["funds"]) == 2


def test_watchlist_add_list_delete(demo_headers, sample_funds):
    fid = sample_funds[2]["fund_id"]
    r = requests.post(f"{API}/mf/watchlist", json={"fund_id": fid}, headers=demo_headers, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/mf/watchlist", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    assert any(x["fund_id"] == fid for x in r.json()["items"])
    r = requests.delete(f"{API}/mf/watchlist/{fid}", headers=demo_headers, timeout=10)
    assert r.status_code == 200


def test_lumpsum_order_lifecycle(demo_headers, sample_funds):
    fid = sample_funds[0]["fund_id"]
    r = requests.post(f"{API}/mf/invest",
                       json={"fund_id": fid, "amount": 500},
                       headers=demo_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "completed"
    assert j["kind"] == "lumpsum"
    assert j["units"] > 0
    # Status history should include lifecycle steps
    steps = [s["status"] for s in (j.get("status_history") or [])]
    for req in ("created", "pending_payment", "processing", "allocated", "completed"):
        assert req in steps, f"missing {req} in {steps}"


def test_lumpsum_idempotency(demo_headers, sample_funds):
    fid = sample_funds[0]["fund_id"]
    key = f"idem-{uuid.uuid4().hex[:8]}"
    r1 = requests.post(f"{API}/mf/invest",
                        json={"fund_id": fid, "amount": 500},
                        headers={**demo_headers, "Idempotency-Key": key}, timeout=15)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/mf/invest",
                        json={"fund_id": fid, "amount": 500},
                        headers={**demo_headers, "Idempotency-Key": key}, timeout=15)
    assert r2.status_code == 200
    assert r1.json()["order_id"] == r2.json()["order_id"]


def test_sip_create_pause_resume_cancel(demo_headers, sample_funds):
    fid = sample_funds[1]["fund_id"]
    r = requests.post(f"{API}/mf/sips",
                       json={"fund_id": fid, "amount": 500, "day_of_month": 5, "frequency": "monthly"},
                       headers=demo_headers, timeout=10)
    assert r.status_code == 200, r.text
    sip_id = r.json()["sip_id"]
    for status in ("paused", "active", "cancelled"):
        r = requests.post(f"{API}/mf/sips/{sip_id}/status", json={"status": status},
                           headers=demo_headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == status


def test_sip_modify(demo_headers, sample_funds):
    fid = sample_funds[1]["fund_id"]
    r = requests.post(f"{API}/mf/sips",
                       json={"fund_id": fid, "amount": 500}, headers=demo_headers, timeout=10)
    sip_id = r.json()["sip_id"]
    r = requests.patch(f"{API}/mf/sips/{sip_id}", json={"amount": 750, "day_of_month": 10},
                        headers=demo_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["amount"] == 750
    assert r.json()["day_of_month"] == 10


def test_sip_validation(demo_headers, sample_funds):
    fid = sample_funds[0]["fund_id"]
    r = requests.post(f"{API}/mf/sips", json={"fund_id": fid, "amount": 10},
                       headers=demo_headers, timeout=10)
    assert r.status_code == 400
    r = requests.post(f"{API}/mf/sips",
                       json={"fund_id": fid, "amount": 500, "day_of_month": 40},
                       headers=demo_headers, timeout=10)
    assert r.status_code in (400, 422)


def test_portfolio_analytics(demo_headers):
    r = requests.get(f"{API}/mf/portfolio", headers=demo_headers, timeout=15)
    assert r.status_code == 200
    p = r.json()
    for k in ("total_invested", "current_value", "unrealized_pnl", "absolute_return_pct",
                "daily_pl", "weekly_pl", "monthly_pl", "allocations", "count_funds",
                "top_performer", "worst_performer"):
        assert k in p, f"missing {k}"
    assert set(p["allocations"].keys()) == {"asset", "amc", "category", "risk"}


def test_goal_create_progress_delete(demo_headers, sample_funds):
    fid = sample_funds[0]["fund_id"]
    r = requests.post(f"{API}/mf/goals",
                       json={"name": "Test House", "kind": "house", "target_amount": 5000000,
                              "target_date": "2035-01-01T00:00:00Z",
                              "linked_funds": [fid]},
                       headers=demo_headers, timeout=10)
    assert r.status_code == 200, r.text
    gid = r.json()["goal_id"]
    r = requests.get(f"{API}/mf/goals", headers=demo_headers, timeout=10)
    goals = r.json()["items"]
    goal = next(g for g in goals if g["goal_id"] == gid)
    for k in ("current_amount", "remaining_amount", "progress_pct",
                "required_monthly_sip", "months_left"):
        assert k in goal
    assert goal["required_monthly_sip"] > 0
    # Delete
    r = requests.delete(f"{API}/mf/goals/{gid}", headers=demo_headers, timeout=10)
    assert r.status_code == 200


def test_ai_advisor(demo_headers):
    r = requests.post(f"{API}/mf/ai", json={"kind": "analyze_portfolio"},
                       headers=demo_headers, timeout=45)
    assert r.status_code == 200
    assert len(r.json().get("answer", "")) > 20


def test_orders_list(demo_headers):
    r = requests.get(f"{API}/mf/orders", headers=demo_headers, timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_redeem_insufficient_units(demo_headers, sample_funds):
    r = requests.post(f"{API}/mf/redeem",
                       json={"fund_id": sample_funds[3]["fund_id"], "units": 1000},
                       headers=demo_headers, timeout=10)
    assert r.status_code in (400, 500)  # insufficient / kyc


# ---------- ADMIN ----------
def test_admin_dashboard(admin_headers):
    r = requests.get(f"{API}/admin/mf/dashboard", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    for k in ("totals", "by_amc", "by_category", "top_funds", "provider_status"):
        assert k in j
    for kpi in ("aum", "active_investors", "total_funds", "active_sips",
                  "sip_success_rate", "sip_failure_rate", "avg_sip_amount",
                  "avg_investment_size", "avg_holding_days"):
        assert kpi in j["totals"]


def test_admin_config_update(admin_headers):
    r = requests.get(f"{API}/admin/mf/config", headers=admin_headers, timeout=10)
    original = r.json()
    r = requests.put(f"{API}/admin/mf/config", json={"min_sip_inr": 250},
                       headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["min_sip_inr"] == 250
    # restore
    requests.put(f"{API}/admin/mf/config",
                  json={"min_sip_inr": original["min_sip_inr"]},
                  headers=admin_headers, timeout=10)


def test_admin_orders_sips_investors_funds(admin_headers):
    for path in ("orders", "sips", "investors", "funds", "providers"):
        r = requests.get(f"{API}/admin/mf/{path}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"{path} failed: {r.text}"


def test_admin_execute_due(admin_headers):
    r = requests.post(f"{API}/admin/mf/sips/execute-due", headers=admin_headers,
                       params={"dry_run": "true"}, timeout=15)
    assert r.status_code == 200
    assert "considered" in r.json()


def test_no_kyc_needed_for_sip_and_lumpsum(demo_headers, sample_funds):
    """Verify business rule: NO KYC required for browse/SIP/lumpsum."""
    fid = sample_funds[2]["fund_id"]
    r = requests.post(f"{API}/mf/invest", json={"fund_id": fid, "amount": 500},
                       headers=demo_headers, timeout=15)
    assert r.status_code == 200
    r = requests.post(f"{API}/mf/sips", json={"fund_id": fid, "amount": 500},
                       headers=demo_headers, timeout=10)
    assert r.status_code == 200
