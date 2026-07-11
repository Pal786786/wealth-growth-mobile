"""Sprint 11 — Mutual Funds supplemental coverage (all AI kinds, all chart windows,
all filter combinations, portfolio 4-view allocations, admin provider switch,
KYC gate on redemption).
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CHART_WINDOWS = ["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"]
AI_KINDS = ["analyze_portfolio", "suggest_funds", "sip_increase",
            "tax_saving", "risk_analysis", "diversification"]


# ---------------- fixtures ---------------- #
@pytest.fixture(scope="module")
def demo_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": "demo@mfb.in", "password": "demo1234"}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def any_fund(demo_headers):
    r = requests.get(f"{API}/mf/funds", headers=demo_headers, params={"limit": 40}, timeout=15)
    return r.json()["items"]


# ------------- Fund listing filters/search ------------- #
def test_funds_seeded_40(any_fund):
    assert len(any_fund) == 40, f"expected 40 seeded funds, got {len(any_fund)}"


def test_filter_by_risk(demo_headers):
    for risk in ("low", "moderate", "high"):
        r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                         params={"risk": risk, "limit": 40}, timeout=15)
        assert r.status_code == 200
        for f in r.json()["items"]:
            assert f["risk"] == risk


def test_filter_by_min_rating(demo_headers):
    r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                     params={"min_rating": 4, "limit": 40}, timeout=15)
    assert r.status_code == 200
    for f in r.json()["items"]:
        assert f["star_rating"] >= 4


def test_filter_by_amc(demo_headers, any_fund):
    amc = any_fund[0]["amc"]
    r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                     params={"amc": amc, "limit": 40}, timeout=15)
    assert r.status_code == 200
    for f in r.json()["items"]:
        assert f["amc"] == amc


def test_search_query(demo_headers, any_fund):
    # search first word from a fund name
    name_token = any_fund[0]["name"].split()[0]
    r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                     params={"q": name_token, "limit": 40}, timeout=15)
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    hits = [f["name"].lower() for f in r.json()["items"]]
    assert any(name_token.lower() in n for n in hits)


def test_sort_options(demo_headers):
    for s in ("aum_desc", "returns_1y_desc", "rating_desc"):
        r = requests.get(f"{API}/mf/funds", headers=demo_headers,
                         params={"sort": s, "limit": 5}, timeout=15)
        assert r.status_code == 200, f"sort {s} failed"


# ------------- Fund detail integrity ------------- #
def test_fund_detail_has_holdings_sectors_docs(demo_headers, any_fund):
    r = requests.get(f"{API}/mf/funds/{any_fund[0]['fund_id']}", headers=demo_headers, timeout=10)
    j = r.json()
    assert isinstance(j.get("holdings"), list) and len(j["holdings"]) > 0
    assert isinstance(j.get("sector_allocation"), (list, dict))
    assert "documents" in j


# ------------- Chart windows ------------- #
def test_all_chart_windows(demo_headers, any_fund):
    fid = any_fund[0]["fund_id"]
    for w in CHART_WINDOWS:
        r = requests.get(f"{API}/mf/funds/{fid}/chart", headers=demo_headers,
                         params={"window": w}, timeout=10)
        assert r.status_code == 200, f"chart window {w} failed: {r.text[:200]}"
        pts = r.json().get("points", [])
        assert len(pts) >= 2, f"window {w} returned <2 points"


# ------------- Portfolio 4-view allocations ------------- #
def test_portfolio_four_allocation_views(demo_headers, any_fund):
    # Ensure at least one holding
    requests.post(f"{API}/mf/invest",
                  json={"fund_id": any_fund[0]["fund_id"], "amount": 500},
                  headers=demo_headers, timeout=15)
    r = requests.get(f"{API}/mf/portfolio", headers=demo_headers, timeout=15)
    assert r.status_code == 200
    p = r.json()
    allocs = p["allocations"]
    assert set(allocs.keys()) == {"asset", "amc", "category", "risk"}
    for view, buckets in allocs.items():
        assert isinstance(buckets, list), f"{view} not list"
        if buckets:
            total = sum(float(b.get("value") or b.get("amount") or 0) for b in buckets)
            assert total > 0, f"{view} allocation has zero total"


# ------------- AI advisor: all 6 kinds ------------- #
@pytest.mark.parametrize("kind", AI_KINDS)
def test_ai_all_kinds(demo_headers, kind):
    r = requests.post(f"{API}/mf/ai", json={"kind": kind},
                      headers=demo_headers, timeout=90)
    assert r.status_code == 200, f"kind {kind} status {r.status_code}: {r.text[:200]}"
    ans = r.json().get("answer", "")
    assert isinstance(ans, str) and len(ans) > 20, f"kind {kind} produced empty answer"


# ------------- KYC gate on redemption ------------- #
def test_redeem_kyc_gate_when_required(demo_headers, admin_headers, any_fund):
    """Enable redemption_kyc_required, temporarily set demo user KYC to 'pending',
    attempt redeem — must fail with KYC error. Restore both afterwards."""
    from pymongo import MongoClient
    import os as _os
    mongo_url = _os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    _db_name = _os.environ.get("DB_NAME", "my_funding_bank")
    mc = MongoClient(mongo_url); mdb = mc[_db_name]

    orig_cfg = requests.get(f"{API}/admin/mf/config", headers=admin_headers, timeout=10).json()
    # resolve demo user_id
    who = requests.get(f"{API}/auth/me", headers=demo_headers, timeout=10).json()
    uid = who.get("user_id") or who.get("id")
    orig_kyc = mdb.kyc_profiles.find_one({"user_id": uid}) or {}
    try:
        requests.put(f"{API}/admin/mf/config",
                     json={"redemption_kyc_required": True},
                     headers=admin_headers, timeout=10)
        # Invest first so user has units (invest is KYC-open per business rules)
        inv = requests.post(f"{API}/mf/invest",
                            json={"fund_id": any_fund[0]["fund_id"], "amount": 500},
                            headers=demo_headers, timeout=15)
        assert inv.status_code == 200
        units = float(inv.json().get("units", 0))
        # Now flip user's KYC to pending
        mdb.kyc_profiles.update_one({"user_id": uid},
                                     {"$set": {"user_id": uid, "status": "pending"}},
                                     upsert=True)
        r = requests.post(f"{API}/mf/redeem",
                          json={"fund_id": any_fund[0]["fund_id"], "units": min(units, 0.1)},
                          headers=demo_headers, timeout=10)
        assert r.status_code in (400, 402, 403, 409), f"expected KYC block, got {r.status_code}"
        body_txt = r.text.lower()
        assert "kyc" in body_txt or "verify" in body_txt or "approv" in body_txt, r.text
    finally:
        # Restore config + user KYC
        requests.put(f"{API}/admin/mf/config",
                     json={"redemption_kyc_required": orig_cfg.get("redemption_kyc_required", False)},
                     headers=admin_headers, timeout=10)
        mdb.kyc_profiles.update_one({"user_id": uid},
                                     {"$set": {"status": orig_kyc.get("status", "approved")}},
                                     upsert=True)
        mc.close()


# ------------- Admin dashboard KPIs ------------- #
def test_admin_dashboard_expanded_kpis(admin_headers):
    r = requests.get(f"{API}/admin/mf/dashboard", headers=admin_headers, timeout=15)
    j = r.json()
    for k in ("aum", "active_investors", "active_sips", "sip_success_rate",
              "avg_sip_amount"):
        assert k in j["totals"], f"missing kpi {k}"
    assert isinstance(j["by_amc"], list)
    assert isinstance(j["by_category"], list)
    assert isinstance(j["top_funds"], list)


def test_admin_execute_due_dry_run_summary(admin_headers):
    r = requests.post(f"{API}/admin/mf/sips/execute-due",
                      headers=admin_headers, params={"dry_run": "true"}, timeout=15)
    j = r.json()
    assert "considered" in j
    # dry_run must not actually execute
    assert j.get("dry_run", True) in (True, "true", 1)


def test_admin_provider_switch(admin_headers):
    orig = requests.get(f"{API}/admin/mf/config", headers=admin_headers, timeout=10).json()
    try:
        r = requests.put(f"{API}/admin/mf/config",
                        json={"provider": "mock"}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("provider") == "mock"
    finally:
        requests.put(f"{API}/admin/mf/config",
                     json={"provider": orig.get("provider", "mock")},
                     headers=admin_headers, timeout=10)
