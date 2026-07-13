"""Sprint 12.3 · Phase B tests — Reconciliation, Dashboard, Settlements, Reports."""
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


# ============================================================ RECONCILIATION
def test_reconcile_run(admin_headers):
    r = requests.post(f"{API}/admin/finance/reconcile",
                      json={}, headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "run_id" in j
    assert "totals" in j
    assert set(j["totals"].keys()) >= {"matched", "mismatch", "pending", "manual_review"}
    assert isinstance(j["per_module"], dict)


def test_reconcile_only_specific_module(admin_headers):
    r = requests.post(f"{API}/admin/finance/reconcile",
                      json={"modules": ["payments"]},
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert list(j["per_module"].keys()) == ["payments"]


def test_reconcile_creates_records_readonly(admin_headers):
    """Reconciliation must never modify a journal entry.  Snapshot the journal
    count before/after — invariant: no deletes, no updates to journal."""
    before = requests.get(f"{API}/admin/ledger/journal", params={"limit": 1},
                          headers=admin_headers, timeout=10).json()["total"]
    requests.post(f"{API}/admin/finance/reconcile", json={},
                  headers=admin_headers, timeout=60)
    after = requests.get(f"{API}/admin/ledger/journal", params={"limit": 1},
                         headers=admin_headers, timeout=10).json()["total"]
    # Journal may only grow (new events during the window), never shrink
    assert after >= before


def test_mismatches_query(admin_headers):
    r = requests.get(f"{API}/admin/finance/mismatches",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "items" in j and "total" in j
    for it in j["items"][:5]:
        assert it["status"] in ("mismatch", "manual_review", "pending", "matched",
                                 "resolved_matched", "ignored")


def test_mismatch_resolve_and_ignore_workflow(admin_headers):
    # Pick a mismatch (any)
    r = requests.get(f"{API}/admin/finance/mismatches",
                     params={"status": "mismatch", "limit": 1},
                     headers=admin_headers, timeout=10).json()
    if not r["items"]:
        pytest.skip("no mismatches in DB")
    pk = r["items"][0]["pair_key"]
    # Resolve
    from urllib.parse import quote
    pk_q = quote(pk, safe="")
    rr = requests.post(f"{API}/admin/finance/mismatches/{pk_q}/resolve",
                       json={"note": "test resolved"}, headers=admin_headers, timeout=10)
    assert rr.status_code == 200, rr.text
    assert rr.json()["recon"]["status"] == "resolved_matched"
    assert rr.json()["recon"]["resolved_by"]
    # Append a note
    rn = requests.post(f"{API}/admin/finance/mismatches/{pk_q}/note",
                       json={"note": "follow-up"}, headers=admin_headers, timeout=10)
    assert rn.status_code == 200
    # Audit trail must record resolve + note
    a = requests.get(f"{API}/admin/ledger/audit",
                     params={"action_prefix": "finance.mismatch"},
                     headers=admin_headers, timeout=10).json()
    assert a["total"] >= 2


def test_mismatch_retry_reruns_recon(admin_headers):
    r = requests.get(f"{API}/admin/finance/mismatches",
                     params={"limit": 1}, headers=admin_headers, timeout=10).json()
    if not r["items"]:
        pytest.skip("empty mismatch queue")
    from urllib.parse import quote
    pk = quote(r["items"][0]["pair_key"], safe="")
    rr = requests.post(f"{API}/admin/finance/mismatches/{pk}/retry",
                       headers=admin_headers, timeout=30)
    assert rr.status_code == 200, rr.text
    assert "run" in rr.json() and "recon" in rr.json()


def test_recon_runs_history(admin_headers):
    r = requests.get(f"{API}/admin/finance/reconciliation/runs",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


# ============================================================ DASHBOARD
def test_dashboard_default_range(admin_headers):
    r = requests.get(f"{API}/admin/finance/dashboard",
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("kpis", "breakdown", "providers", "charts", "range"):
        assert k in j
    for k in ("total_deposits", "total_withdrawals", "wallet_balance",
               "platform_liability", "provider_balance", "fees", "gst",
               "failed_payments", "pending_withdrawals", "pending_settlements",
               "net_revenue"):
        assert k in j["kpis"], f"missing kpi: {k}"


def test_dashboard_all_range_keys(admin_headers):
    for rk in ("today", "week", "month", "quarter", "year"):
        r = requests.get(f"{API}/admin/finance/dashboard",
                         params={"range": rk}, headers=admin_headers, timeout=15)
        assert r.status_code == 200, (rk, r.text)


def test_dashboard_charts_series(admin_headers):
    r = requests.get(f"{API}/admin/finance/dashboard?range=month",
                     headers=admin_headers, timeout=15).json()
    ch = r["charts"]["deposits_vs_withdrawals"]
    for k in ("deposits", "withdrawals"):
        assert isinstance(ch[k], list)


# ============================================================ SETTLEMENTS
def test_settlements_razorpay(admin_headers):
    r = requests.get(f"{API}/admin/finance/settlements/razorpay",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "razorpay"
    for row in j["items"][:3]:
        for f in ("settlement_id", "amount", "date", "status", "utr"):
            assert f in row


def test_settlements_cashfree(admin_headers):
    r = requests.get(f"{API}/admin/finance/settlements/cashfree",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200


def test_settlements_unknown_provider_400(admin_headers):
    r = requests.get(f"{API}/admin/finance/settlements/unknown",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 400


# ============================================================ REPORTS
def test_report_types_list(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 200
    j = r.json()
    for t in ("daily", "weekly", "monthly", "quarterly", "yearly",
               "deposit", "withdrawal", "gold", "mf", "forex", "fees", "tax"):
        assert t in j["types"], t
    assert set(j["formats"]) == {"pdf", "xlsx", "csv"}


def test_report_pdf_export(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/monthly.pdf",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers.get("content-disposition", "").startswith("attachment;")
    # PDF magic byte
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


def test_report_xlsx_export(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/monthly.xlsx",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    # XLSX is a zip file
    assert r.content[:2] == b"PK"


def test_report_csv_export(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/deposit.csv",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "EXECUTIVE SUMMARY" in r.text
    assert "ENTRIES" in r.text


def test_report_bad_type_400(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/nonsense.pdf",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 400


def test_report_bad_format_400(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/monthly.docx",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 400


def test_report_with_filters(admin_headers):
    r = requests.get(f"{API}/admin/finance/reports/withdrawal.csv",
                     params={"date_from": "2020-01-01",
                             "date_to": "2030-12-31"},
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("x-report-rows") is not None


def test_report_export_audited(admin_headers):
    requests.get(f"{API}/admin/finance/reports/daily.pdf",
                 headers=admin_headers, timeout=30)
    a = requests.get(f"{API}/admin/ledger/audit",
                     params={"action_prefix": "finance.report.export"},
                     headers=admin_headers, timeout=10).json()
    assert a["total"] >= 1


# ============================================================ AUTH GUARDS
def test_all_phase_b_endpoints_require_admin():
    for path in ("/admin/finance/reconcile", "/admin/finance/dashboard",
                 "/admin/finance/mismatches", "/admin/finance/settlements/razorpay",
                 "/admin/finance/reports/monthly.pdf", "/admin/finance/reports"):
        if "reports/monthly.pdf" in path or "reports\"" in path:
            r = requests.get(f"{API}{path}", timeout=10)
        elif "reconcile" in path:
            r = requests.post(f"{API}{path}", timeout=10)
        else:
            r = requests.get(f"{API}{path}", timeout=10)
        assert r.status_code in (401, 403), (path, r.status_code)


# ============================================================ SAFETY
def test_reconciliation_never_updates_journal_amount(admin_headers):
    """Trigger recon and confirm the aggregate journal total is unchanged."""
    before = requests.get(f"{API}/admin/ledger/journal",
                          params={"limit": 500, "include_reversed": True},
                          headers=admin_headers, timeout=15).json()
    before_amt = sum(float(e["amount"]) for e in before["items"])
    before_count = before["total"]
    requests.post(f"{API}/admin/finance/reconcile", json={},
                  headers=admin_headers, timeout=60)
    after = requests.get(f"{API}/admin/ledger/journal",
                         params={"limit": 500, "include_reversed": True},
                         headers=admin_headers, timeout=15).json()
    after_amt = sum(float(e["amount"]) for e in after["items"])
    # Journal is immutable → any existing entry's amount must not change.
    # (New entries may appear if any wallet activity happened concurrently — allow.)
    assert after["total"] >= before_count
    if after["total"] == before_count:
        assert abs(after_amt - before_amt) < 0.01
