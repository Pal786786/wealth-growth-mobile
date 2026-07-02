"""Sprint 4 — AI Wealth Advisor test suite.

Covers all user endpoints (/api/ai/*) and admin endpoints (/api/admin/ai/*).
Uses live Claude Sonnet 4.5 via EMERGENT_LLM_KEY.
"""
import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wealth-growth-mobile.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ------------ session fixtures ------------
@pytest.fixture(scope="session")
def user_token():
    r = requests.post(f"{API}/auth/login", json={"identifier": "demo@mfb.in", "password": "demo1234"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def uh(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"email": "admin@mfb.in", "password": "Admin@MFB2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def ah(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session", autouse=True)
def _reset_settings_after(ah):
    """Reset settings to safe defaults after tests."""
    yield
    try:
        requests.put(
            f"{API}/admin/ai/settings",
            headers=ah,
            json={
                "features": {"chat": True, "portfolio_analysis": True, "goals": True, "investment_suggestions": True},
                "rate_limit_per_hour": 40,
            },
            timeout=15,
        )
    except Exception:
        pass


# ---------- Auth guard ----------
class TestAuth:
    def test_ai_suggestions_public(self):
        # suggestions is defined without auth dep — verify still 200
        r = requests.get(f"{API}/ai/suggestions", timeout=15)
        assert r.status_code == 200
        assert len(r.json().get("items", [])) >= 4

    def test_ai_profile_requires_auth(self):
        r = requests.get(f"{API}/ai/profile", timeout=15)
        assert r.status_code in (401, 403)

    def test_ai_conversations_requires_auth(self):
        r = requests.get(f"{API}/ai/conversations", timeout=15)
        assert r.status_code in (401, 403)

    def test_ai_chat_stream_requires_auth(self):
        r = requests.post(f"{API}/ai/chat/stream", json={"message": "hi"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_dashboard_requires_admin(self):
        r = requests.get(f"{API}/admin/ai/dashboard", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Profile & suggestions ----------
class TestProfile:
    def test_suggestions_min_4(self):
        r = requests.get(f"{API}/ai/suggestions", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert isinstance(items, list) and len(items) >= 4

    def test_profile_shape(self, uh):
        r = requests.get(f"{API}/ai/profile", headers=uh, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()["profile"]
        for key in ["user", "wallet", "portfolio", "sips", "gold", "forex", "activity_30d", "goals", "analytics"]:
            assert key in p, f"missing top-level key {key}"
        a = p["analytics"]
        for key in ["health_score", "risk_bucket", "confidence_pct"]:
            assert key in a
        assert isinstance(a["health_score"], (int, float))
        assert a["risk_bucket"] in ("Low", "Medium", "High")


# ---------- Conversations CRUD ----------
class TestConversations:
    def test_create_and_list(self, uh):
        r = requests.post(f"{API}/ai/conversations", headers=uh, json={"title": "TEST_conv"}, timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["conversation"]["conversation_id"]
        assert cid.startswith("conv_")

        # List
        r2 = requests.get(f"{API}/ai/conversations", headers=uh, timeout=15)
        assert r2.status_code == 200
        ids = [c["conversation_id"] for c in r2.json()["items"]]
        assert cid in ids

        # Get detail
        r3 = requests.get(f"{API}/ai/conversations/{cid}", headers=uh, timeout=15)
        assert r3.status_code == 200
        body = r3.json()
        assert body["conversation"]["conversation_id"] == cid
        assert body["messages"] == []

        # Delete
        r4 = requests.delete(f"{API}/ai/conversations/{cid}", headers=uh, timeout=15)
        assert r4.status_code == 200
        r5 = requests.get(f"{API}/ai/conversations/{cid}", headers=uh, timeout=15)
        assert r5.status_code == 404


# ---------- SSE Streaming Chat ----------
def _parse_sse(chunk_iter):
    """Yield (event, data_dict) tuples from a stream."""
    buf = b""
    for chunk in chunk_iter:
        if not chunk:
            continue
        buf += chunk
        while b"\n\n" in buf:
            frame, buf = buf.split(b"\n\n", 1)
            event = None
            data = None
            for line in frame.decode("utf-8", errors="replace").split("\n"):
                if line.startswith("event: "):
                    event = line[len("event: "):].strip()
                elif line.startswith("data: "):
                    data = line[len("data: "):].strip()
            if event:
                try:
                    d = json.loads(data) if data else {}
                except Exception:
                    d = {"_raw": data}
                yield event, d


class TestChatStream:
    def test_chat_stream_creates_conv_and_streams(self, uh):
        r = requests.post(
            f"{API}/ai/chat/stream",
            headers=uh,
            json={"message": "In one short paragraph, what is my portfolio health score and one tip?"},
            stream=True,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        events = list(_parse_sse(r.iter_content(chunk_size=None)))
        r.close()
        by_evt = {e[0]: [x for x in events if x[0] == e[0]] for e in events}
        assert "hello" in by_evt, f"no hello event: {[e[0] for e in events]}"
        assert "start" in by_evt
        assert "done" in by_evt
        assert len(by_evt.get("delta", [])) > 0, "expected at least one delta"
        # hello has conversation_id
        cid = by_evt["hello"][0][1].get("conversation_id")
        assert cid and cid.startswith("conv_")
        # start has user/ass ids and profile_snapshot
        start_data = by_evt["start"][0][1]
        assert start_data.get("user_message_id", "").startswith("msg_")
        assert start_data.get("assistant_message_id", "").startswith("msg_")
        assert "profile_snapshot" in start_data
        # assemble text
        full_text = "".join(d.get("text", "") for e, d in events if e == "delta")
        assert len(full_text) > 40
        # loose investment-related keyword check
        assert any(
            k.lower() in full_text.lower()
            for k in ["portfolio", "invest", "sip", "risk", "return", "score", "₹", "inr", "advice", "fund"]
        ), f"reply not investment-related: {full_text[:200]}"

        # Save cid for chained checks
        pytest.chat_cid_1 = cid  # type: ignore
        pytest.chat_ass_id_1 = start_data["assistant_message_id"]  # type: ignore

    def test_multi_turn_context(self, uh):
        cid = getattr(pytest, "chat_cid_1", None)
        assert cid, "test_chat_stream_creates_conv_and_streams must run first"
        # Turn 2 — reference "earlier" answer implicitly
        r = requests.post(
            f"{API}/ai/chat/stream",
            headers=uh,
            json={"conversation_id": cid, "message": "Given what you just said, name ONE asset class to add next."},
            stream=True,
            timeout=120,
        )
        assert r.status_code == 200
        events = list(_parse_sse(r.iter_content(chunk_size=None)))
        r.close()
        text = "".join(d.get("text", "") for e, d in events if e == "delta")
        assert len(text) > 20
        # Should NOT ask "what earlier message" — should reference context
        # (soft check — LLM output can vary; ensure it produced a coherent recommendation)
        assert any(kw in text.lower() for kw in ["fund", "gold", "sip", "equity", "debt", "bond", "index", "mutual", "fd"])

        # Verify messages persisted
        det = requests.get(f"{API}/ai/conversations/{cid}", headers=uh, timeout=15).json()
        # 2 turns × (user + assistant) = 4 messages
        assert len(det["messages"]) >= 4

    def test_feedback_on_assistant_message(self, uh):
        aid = getattr(pytest, "chat_ass_id_1", None)
        assert aid
        r = requests.post(
            f"{API}/ai/feedback",
            headers=uh,
            json={"message_id": aid, "rating": 1, "note": "TEST_ helpful"},
            timeout=15,
        )
        assert r.status_code == 200
        # bad message id → 404
        r2 = requests.post(
            f"{API}/ai/feedback", headers=uh, json={"message_id": "msg_nonexistent", "rating": -1}, timeout=15
        )
        assert r2.status_code == 404


# ---------- Portfolio analyze (with cache verify) ----------
class TestPortfolioAnalyze:
    def test_analyze_and_cache(self, uh):
        t0 = time.time()
        r1 = requests.get(f"{API}/ai/portfolio/analyze", headers=uh, timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert "profile" in d1 and "insights" in d1
        ins = d1["insights"]
        for k in ["headline", "highlights", "recommendations", "risks", "disclaimer"]:
            assert k in ins, f"missing insights.{k}"
        assert d1.get("generated_at") and d1.get("expires_at")
        dt1 = time.time() - t0

        # Second call should be cached (<1s)
        t1 = time.time()
        r2 = requests.get(f"{API}/ai/portfolio/analyze", headers=uh, timeout=30)
        dt2 = time.time() - t1
        assert r2.status_code == 200
        assert dt2 < 2.0 or dt2 < dt1 / 2, f"cache miss? first={dt1:.2f}s second={dt2:.2f}s"


# ---------- Goals CRUD (all 6 types) ----------
class TestGoals:
    GOAL_TYPES = [
        ("house", "TEST_ Buy a 2BHK", 5000000, 7),
        ("car", "TEST_ Family car", 1200000, 3),
        ("retirement", "TEST_ Retire at 60", 20000000, 25),
        ("education", "TEST_ Kid's college", 3000000, 12),
        ("emergency", "TEST_ Emergency fund", 300000, 1),
        ("custom", "TEST_ Vacation", 500000, 2),
    ]

    def test_create_all_types(self, uh):
        created = []
        for gt, title, tgt, hz in self.GOAL_TYPES:
            r = requests.post(
                f"{API}/ai/goals",
                headers=uh,
                json={
                    "goal_type": gt,
                    "title": title,
                    "target_amount": tgt,
                    "horizon_years": hz,
                    "current_savings": 10000,
                    "risk_appetite": "moderate",
                },
                timeout=120,
            )
            assert r.status_code == 200, f"{gt}: {r.text}"
            g = r.json()["goal"]
            assert g["goal_id"].startswith("goal_")
            assert g["recommended_monthly_sip"] > 0, f"{gt} SIP was 0"
            assert g["expected_return_pct"] > 0
            assert 0 <= g["probability_pct"] <= 100
            # ai_notes may be None only if LLM failed - warn but don't fail suite
            if g.get("ai_notes"):
                n = g["ai_notes"]
                # loose check on ai_notes shape
                assert isinstance(n, dict)
            created.append(g["goal_id"])
        pytest.goal_ids = created  # type: ignore
        assert len(created) == 6

    def test_list_and_get(self, uh):
        r = requests.get(f"{API}/ai/goals", headers=uh, timeout=15)
        assert r.status_code == 200
        ids = [g["goal_id"] for g in r.json()["items"]]
        for gid in getattr(pytest, "goal_ids", []):
            assert gid in ids
        # get one
        one = getattr(pytest, "goal_ids", [None])[0]
        r2 = requests.get(f"{API}/ai/goals/{one}", headers=uh, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["goal"]["goal_id"] == one

    def test_delete_cleanup(self, uh):
        for gid in getattr(pytest, "goal_ids", []):
            r = requests.delete(f"{API}/ai/goals/{gid}", headers=uh, timeout=15)
            assert r.status_code == 200
        # verify deleted
        r2 = requests.get(f"{API}/ai/goals/{getattr(pytest, 'goal_ids', ['x'])[0]}", headers=uh, timeout=15)
        assert r2.status_code == 404


# ---------- Feature toggle & rate limit ----------
class TestFeatureAndRate:
    def test_feature_toggle_chat(self, uh, ah):
        # disable chat
        r = requests.put(
            f"{API}/admin/ai/settings",
            headers=ah,
            json={"features": {"chat": False, "portfolio_analysis": True, "goals": True, "investment_suggestions": True}},
            timeout=15,
        )
        assert r.status_code == 200
        # sleep past settings cache (30s TTL) — but PUT calls force refresh serverside; still user endpoint uses cached _get_settings.
        # Force a bit: cache TTL is 30s. Wait 32s.
        time.sleep(32)
        rc = requests.post(f"{API}/ai/chat/stream", headers=uh, json={"message": "TEST_hi"}, timeout=15)
        assert rc.status_code == 403, f"expected 403 after disabling chat, got {rc.status_code}: {rc.text[:200]}"

        # re-enable
        requests.put(
            f"{API}/admin/ai/settings",
            headers=ah,
            json={"features": {"chat": True, "portfolio_analysis": True, "goals": True, "investment_suggestions": True}},
            timeout=15,
        )
        time.sleep(32)
        rc2 = requests.post(
            f"{API}/ai/chat/stream",
            headers=uh,
            json={"message": "TEST_hi again"},
            stream=True,
            timeout=60,
        )
        assert rc2.status_code == 200
        # drain
        for _ in rc2.iter_content(chunk_size=1024):
            break
        rc2.close()

    def test_rate_limit(self, uh, ah):
        # Set limit to 2
        requests.put(f"{API}/admin/ai/settings", headers=ah, json={"rate_limit_per_hour": 2}, timeout=15)
        time.sleep(32)  # bust settings cache

        results = []
        for i in range(3):
            r = requests.post(
                f"{API}/ai/chat/stream",
                headers=uh,
                json={"message": f"TEST_rl {i} — say one word"},
                stream=True,
                timeout=60,
            )
            results.append(r.status_code)
            # drain
            if r.status_code == 200:
                for _ in r.iter_content(chunk_size=1024):
                    pass
            r.close()

        # Restore
        requests.put(f"{API}/admin/ai/settings", headers=ah, json={"rate_limit_per_hour": 40}, timeout=15)

        # Expect at least one 429 among the 3 attempts
        assert 429 in results, f"expected a 429 in rate-limit run, got {results}"


# ---------- Admin endpoints ----------
class TestAdmin:
    def test_dashboard(self, ah):
        r = requests.get(f"{API}/admin/ai/dashboard", headers=ah, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "stats" in d and "chart" in d and "top_users" in d
        s = d["stats"]
        for k in ["total_conversations", "messages_24h", "tokens_7d", "est_cost_usd_7d", "feedback", "active_users_7d"]:
            assert k in s, f"missing stat {k}"
        assert "up" in s["feedback"] and "down" in s["feedback"]
        assert isinstance(d["chart"], list) and len(d["chart"]) == 7
        for row in d["chart"]:
            assert "date" in row and "messages" in row and "tokens" in row

    def test_list_conversations(self, ah):
        r = requests.get(f"{API}/admin/ai/conversations", headers=ah, timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()
        # with search
        r2 = requests.get(f"{API}/admin/ai/conversations", headers=ah, params={"q": "TEST_conv"}, timeout=15)
        assert r2.status_code == 200

    def test_get_conversation_detail(self, uh, ah):
        # create a conv + message
        cv = requests.post(f"{API}/ai/conversations", headers=uh, json={"title": "TEST_admin_view"}, timeout=15).json()
        cid = cv["conversation"]["conversation_id"]
        # send message
        r = requests.post(
            f"{API}/ai/chat/stream",
            headers=uh,
            json={"conversation_id": cid, "message": "TEST_ ping — one line reply."},
            stream=True,
            timeout=60,
        )
        for _ in r.iter_content(chunk_size=1024):
            pass
        r.close()

        # admin view
        r2 = requests.get(f"{API}/admin/ai/conversations/{cid}", headers=ah, timeout=15)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["conversation"]["conversation_id"] == cid
        assert "user" in body and "messages" in body
        assert len(body["messages"]) >= 2

    def test_feedback_list(self, ah):
        r = requests.get(f"{API}/admin/ai/feedback", headers=ah, timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_settings_get_and_patch_propagation(self, ah):
        r = requests.get(f"{API}/admin/ai/settings", headers=ah, timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()["settings"]
        for k in ["system_prompt", "model", "features", "temperature", "suggested_questions"]:
            assert k in s

        # PATCH suggested_questions
        new_q = ["TEST_q1", "TEST_q2", "TEST_q3", "TEST_q4"]
        r2 = requests.put(f"{API}/admin/ai/settings", headers=ah, json={"suggested_questions": new_q}, timeout=15)
        assert r2.status_code == 200
        # bust cache
        time.sleep(32)
        r3 = requests.get(f"{API}/ai/suggestions", timeout=15)
        assert r3.status_code == 200
        assert r3.json()["items"] == new_q

        # restore
        requests.put(
            f"{API}/admin/ai/settings",
            headers=ah,
            json={"suggested_questions": [
                "Analyze my portfolio",
                "Where should I invest today?",
                "Best SIP for ₹5000/month",
                "Gold or Mutual Funds?",
                "How can I reduce risk?",
                "Build me a retirement plan",
            ]},
            timeout=15,
        )

    def test_settings_patch_temperature_and_model(self, ah):
        r = requests.put(
            f"{API}/admin/ai/settings",
            headers=ah,
            json={"temperature": 0.6, "model": "claude-sonnet-4-5-20250929"},
            timeout=15,
        )
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["temperature"] == 0.6
        assert s["model"] == "claude-sonnet-4-5-20250929"
