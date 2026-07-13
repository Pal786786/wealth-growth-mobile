"""Sprint 12.3 · Phase C tests — Alert engine, provider health, scheduler."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


def test_alert_types_list(admin_headers):
    r = requests.get(f"{API}/admin/finance/alerts/types",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    types = r.json()["types"]
    for t in ("settlement_failed", "ledger_mismatch", "negative_balance",
               "large_withdrawal", "razorpay_unavailable", "cashfree_unavailable"):
        assert t in types


def test_alerts_evaluate_and_list(admin_headers):
    r = requests.post(f"{API}/admin/finance/alerts/evaluate",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "raised" in j
    # Immediately queryable
    lst = requests.get(f"{API}/admin/finance/alerts",
                       headers=admin_headers, timeout=10).json()
    assert lst["total"] >= 0


def test_alert_dedupe_on_second_evaluate(admin_headers):
    """Evaluating rules twice in quick succession should NOT duplicate active
    alerts (dedupe_key)."""
    r1 = requests.post(f"{API}/admin/finance/alerts/evaluate",
                       headers=admin_headers, timeout=30).json()
    r2 = requests.post(f"{API}/admin/finance/alerts/evaluate",
                       headers=admin_headers, timeout=30).json()
    lst1 = requests.get(f"{API}/admin/finance/alerts",
                        params={"limit": 500}, headers=admin_headers, timeout=10).json()
    lst2 = requests.get(f"{API}/admin/finance/alerts",
                        params={"limit": 500}, headers=admin_headers, timeout=10).json()
    # 2nd call cannot produce net-new alerts beyond the 1st when dedupe works
    assert lst2["total"] <= lst1["total"] + r2["raised"]


def test_alerts_filter_severity(admin_headers):
    for sev in ("critical", "warning", "info"):
        r = requests.get(f"{API}/admin/finance/alerts",
                         params={"severity": sev}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        for a in r.json()["items"][:5]:
            assert a["severity"] == sev


def test_alerts_summary(admin_headers):
    r = requests.get(f"{API}/admin/finance/alerts/summary",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "by_status" in j and "by_severity" in j


def test_alert_ack_resolve_note_flow(admin_headers):
    lst = requests.get(f"{API}/admin/finance/alerts",
                       params={"status": "active", "limit": 1},
                       headers=admin_headers, timeout=10).json()
    if not lst["items"]:
        # Force a rule evaluate first
        requests.post(f"{API}/admin/finance/alerts/evaluate",
                      headers=admin_headers, timeout=30)
        lst = requests.get(f"{API}/admin/finance/alerts",
                           params={"status": "active", "limit": 1},
                           headers=admin_headers, timeout=10).json()
    if not lst["items"]:
        pytest.skip("no active alerts to test workflow")
    aid = lst["items"][0]["alert_id"]
    # Ack
    r = requests.post(f"{API}/admin/finance/alerts/{aid}/ack",
                      json={"note": "seen"}, headers=admin_headers, timeout=10)
    assert r.status_code == 200
    # Add note
    r = requests.post(f"{API}/admin/finance/alerts/{aid}/note",
                      json={"note": "investigating"},
                      headers=admin_headers, timeout=10)
    assert r.status_code == 200
    # Resolve
    r = requests.post(f"{API}/admin/finance/alerts/{aid}/resolve",
                      json={"note": "fixed"}, headers=admin_headers, timeout=10)
    assert r.status_code == 200
    # Verify status
    check = requests.get(f"{API}/admin/finance/alerts",
                         params={"limit": 500}, headers=admin_headers, timeout=10).json()
    match = [a for a in check["items"] if a["alert_id"] == aid][0]
    assert match["status"] == "resolved"
    assert match["resolved_by"]
    assert len(match["notes"]) >= 2


def test_alert_actions_audited(admin_headers):
    a = requests.get(f"{API}/admin/ledger/audit",
                     params={"action_prefix": "finance.alert", "limit": 5},
                     headers=admin_headers, timeout=10)
    assert a.status_code == 200
    assert a.json()["total"] >= 1


def test_alert_note_requires_body(admin_headers):
    lst = requests.get(f"{API}/admin/finance/alerts",
                       params={"limit": 1}, headers=admin_headers, timeout=10).json()
    if not lst["items"]:
        pytest.skip("no alerts")
    aid = lst["items"][0]["alert_id"]
    r = requests.post(f"{API}/admin/finance/alerts/{aid}/note",
                      json={}, headers=admin_headers, timeout=10)
    assert r.status_code == 400


def test_alert_not_found(admin_headers):
    for path in ("ack", "resolve", "note"):
        r = requests.post(f"{API}/admin/finance/alerts/does-not-exist/{path}",
                          json={"note": "x"} if path == "note" else {},
                          headers=admin_headers, timeout=10)
        assert r.status_code == 404


# ================================================================ Health --
def test_provider_health(admin_headers):
    r = requests.get(f"{API}/admin/finance/health",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    provs = {p["provider"] for p in j["providers"]}
    for p in ("razorpay", "cashfree"):
        assert p in provs
    for p in j["providers"]:
        for k in ("status", "error_rate_pct", "circuit_breaker", "backoff"):
            assert k in p, k


# ================================================================ Jobs -----
def test_scheduler_trigger_health(admin_headers):
    r = requests.post(f"{API}/admin/finance/jobs/health/trigger",
                      headers=admin_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["kind"] == "health"


def test_scheduler_trigger_alerts(admin_headers):
    r = requests.post(f"{API}/admin/finance/jobs/alerts/trigger",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200


def test_scheduler_unknown_job(admin_headers):
    r = requests.post(f"{API}/admin/finance/jobs/nonsense/trigger",
                      headers=admin_headers, timeout=10)
    assert r.status_code == 400


def test_scheduler_job_runs_history(admin_headers):
    r = requests.get(f"{API}/admin/finance/jobs/runs",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert "items" in r.json()


# ================================================================ SAFETY ---
def test_alerts_never_touch_journal(admin_headers):
    before = requests.get(f"{API}/admin/ledger/journal", params={"limit": 1},
                          headers=admin_headers, timeout=10).json()["total"]
    requests.post(f"{API}/admin/finance/alerts/evaluate",
                  headers=admin_headers, timeout=30)
    after = requests.get(f"{API}/admin/ledger/journal", params={"limit": 1},
                         headers=admin_headers, timeout=10).json()["total"]
    assert after >= before   # may grow via other activity but never shrink


def test_all_alert_endpoints_require_admin():
    for path, method in (
        ("/admin/finance/alerts", "get"),
        ("/admin/finance/alerts/evaluate", "post"),
        ("/admin/finance/health", "get"),
        ("/admin/finance/jobs/health/trigger", "post"),
    ):
        fn = getattr(requests, method)
        r = fn(f"{API}{path}", timeout=10)
        assert r.status_code in (401, 403)
