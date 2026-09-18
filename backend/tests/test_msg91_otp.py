"""MSG91 OTP Widget integration tests (provider mocked — no real SMS).

Covers:
  • Env gating: demo when keys absent / OTP_DEMO_MODE=true, live when keys present
  • Identifier normalization (10-digit → 91-prefixed)
  • Live send stores reqId, never a plaintext OTP
  • Wrong OTP rejected, correct OTP verified via verifyOtp + verifyAccessToken
  • Replay (consumed session) blocked
  • Send failure falls back to retryOtp on previous session, else 502
"""
import asyncio
import os

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import security_extras as se  # noqa: E402

MOBILE = "7000000001"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def live_env(monkeypatch):
    monkeypatch.setenv("MSG91_AUTHKEY", "test_authkey")
    monkeypatch.setenv("MSG91_WIDGET_ID", "test_widget")
    monkeypatch.delenv("OTP_DEMO_MODE", raising=False)
    se._db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    _run(se._db.otp_codes.delete_many({"mobile": MOBILE}))
    yield
    _run(se._db.otp_codes.delete_many({"mobile": MOBILE}))


def _fake_provider(monkeypatch, calls, send_ok=True, retry_ok=True):
    async def fake_call(path, body):
        calls.append((path, {k: v for k, v in body.items() if k != "authkey"}))
        if path == "/sendOtpMobile":
            if send_ok:
                return 200, {"type": "success", "message": "req_test_1"}
            return 400, {"type": "error", "message": "request already exists"}
        if path == "/retryOtp":
            if retry_ok:
                return 200, {"type": "success", "message": "OTP resent"}
            return 400, {"type": "error", "message": "retry failed"}
        if path == "/verifyOtp":
            if body["otp"] == "123456":
                return 200, {"type": "success",
                             "message": "eyJhbGciOiJIUzI1NiJ9.payload.signature_long_token_x"}
            return 400, {"type": "error", "message": "OTP not match"}
        if path == "/verifyAccessToken":
            return 200, {"type": "success", "message": "ok"}
        return 404, {}
    monkeypatch.setattr(se, "_msg91_widget_call", fake_call)


# ---------------------------------------------------------------------------
# Env gating
# ---------------------------------------------------------------------------

def test_env_cfg_absent(monkeypatch):
    monkeypatch.delenv("MSG91_AUTHKEY", raising=False)
    monkeypatch.delenv("MSG91_WIDGET_ID", raising=False)
    assert se._msg91_env_cfg() is None


def test_env_cfg_demo_mode_forces_none(monkeypatch):
    monkeypatch.setenv("MSG91_AUTHKEY", "x")
    monkeypatch.setenv("MSG91_WIDGET_ID", "y")
    monkeypatch.setenv("OTP_DEMO_MODE", "true")
    assert se._msg91_env_cfg() is None


def test_env_cfg_live(monkeypatch):
    monkeypatch.setenv("MSG91_AUTHKEY", "x")
    monkeypatch.setenv("MSG91_WIDGET_ID", "y")
    monkeypatch.setenv("OTP_DEMO_MODE", "false")
    cfg = se._msg91_env_cfg()
    assert cfg == {"authkey": "x", "widget_id": "y"}


def test_identifier_normalization():
    assert se._msg91_identifier("8556939970") == "918556939970"
    assert se._msg91_identifier("+91 8556939970") == "918556939970"
    assert se._msg91_identifier("918556939970") == "918556939970"


# ---------------------------------------------------------------------------
# Live flow (mocked provider)
# ---------------------------------------------------------------------------

def test_live_send_verify_replay(live_env, monkeypatch):
    calls = []
    _fake_provider(monkeypatch, calls)

    r = _run(se.issue_otp(MOBILE, "login"))
    assert r["ok"] and r["provider"] == "msg91" and r["demo"] is False

    doc = _run(se._db.otp_codes.find_one({"mobile": MOBILE}, sort=[("created_at", -1)]))
    assert doc["provider"] == "msg91_widget"
    assert doc["req_id"] == "req_test_1"
    assert doc["otp_plain_demo"] is None and doc["otp_hash"] is None

    assert _run(se.verify_otp(MOBILE, "999999", "login")) is False
    assert _run(se.verify_otp(MOBILE, "123456", "login")) is True
    # Replay must fail — session consumed
    assert _run(se.verify_otp(MOBILE, "123456", "login")) is False

    paths = [c[0] for c in calls]
    assert paths == ["/sendOtpMobile", "/verifyOtp", "/verifyOtp", "/verifyAccessToken"]
    assert calls[0][1]["identifier"] == "917000000001"


def test_live_send_failure_raises_503(live_env, monkeypatch):
    calls = []
    _fake_provider(monkeypatch, calls, send_ok=False, retry_ok=False)
    with pytest.raises(HTTPException) as e:
        _run(se.issue_otp(MOBILE, "login"))
    assert e.value.status_code == 503


def test_live_send_falls_back_to_retry(live_env, monkeypatch):
    calls = []
    # Seed a previous live session so retry path is available
    _fake_provider(monkeypatch, calls)
    _run(se.issue_otp(MOBILE, "login"))
    calls.clear()
    _fake_provider(monkeypatch, calls, send_ok=False, retry_ok=True)

    async def _no_cooldown():
        await se._db.otp_codes.update_many(
            {"mobile": MOBILE},
            {"$set": {"created_at": se._now() - se.timedelta(seconds=60)}})
    _run(_no_cooldown())

    r = _run(se.issue_otp(MOBILE, "login"))
    assert r["ok"] is True
    assert [c[0] for c in calls] == ["/sendOtpMobile", "/retryOtp"]
    doc = _run(se._db.otp_codes.find_one({"mobile": MOBILE}, sort=[("created_at", -1)]))
    assert doc["req_id"] == "req_test_1"  # reused previous session


def test_live_cfg_from_admin_db(monkeypatch):
    """No env keys — Admin Panel Mongo config (provider=msg91_widget) activates live mode."""
    monkeypatch.delenv("MSG91_AUTHKEY", raising=False)
    monkeypatch.delenv("MSG91_WIDGET_ID", raising=False)
    monkeypatch.delenv("OTP_DEMO_MODE", raising=False)
    se._db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async def scenario():
        original = await se._db.api_settings.find_one({"api_name": "sms_provider"})
        try:
            await se._db.api_settings.update_one(
                {"api_name": "sms_provider"},
                {"$set": {"api_key": "db_authkey_123", "is_enabled": True, "force_demo": False,
                          "extra": {"provider": "msg91_widget", "widget_id": "db_widget_1",
                                    "server_token": "db_token"}}},
                upsert=True)
            cfg = await se._msg91_live_cfg()
            assert cfg == {"authkey": "db_authkey_123", "widget_id": "db_widget_1"}
            # force_demo in admin panel disables live mode
            await se._db.api_settings.update_one({"api_name": "sms_provider"}, {"$set": {"force_demo": True}})
            assert await se._msg91_live_cfg() is None
            # missing widget_id → no widget mode
            await se._db.api_settings.update_one(
                {"api_name": "sms_provider"},
                {"$set": {"force_demo": False, "extra.widget_id": ""}})
            assert await se._msg91_live_cfg() is None
        finally:
            if original is not None:
                original.pop("_id", None)
                await se._db.api_settings.replace_one({"api_name": "sms_provider"}, original)
            else:
                await se._db.api_settings.delete_one({"api_name": "sms_provider"})
    _run(scenario())


def test_env_overrides_db(monkeypatch):
    """Platform Secrets (env) take priority over Admin Panel config."""
    monkeypatch.setenv("MSG91_AUTHKEY", "env_ak")
    monkeypatch.setenv("MSG91_WIDGET_ID", "env_wid")
    monkeypatch.delenv("OTP_DEMO_MODE", raising=False)
    se._db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    cfg = _run(se._msg91_live_cfg())
    assert cfg == {"authkey": "env_ak", "widget_id": "env_wid"}


# ---------------------------------------------------------------------------
# Redirect handling in _msg91_widget_call (httpx transport mocked)
# ---------------------------------------------------------------------------

def _set_transport(monkeypatch, handler):
    import httpx
    orig = httpx.AsyncClient

    def factory(**kw):
        return orig(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(se.httpx, "AsyncClient", factory)


def test_redirect_to_msg91_host_is_followed_with_post(monkeypatch):
    import httpx
    hits = []

    def handler(req):
        hits.append((req.method, str(req.url.host)))
        if req.url.host == "control.msg91.com":
            return httpx.Response(302, headers={"location": "https://api.msg91.com/api/v5/widget/sendOtpMobile"})
        return httpx.Response(200, json={"type": "success", "message": "req_after_redirect"})
    _set_transport(monkeypatch, handler)
    s, d = _run(se._msg91_widget_call("/sendOtpMobile", {"authkey": "x"}))
    assert s == 200 and d["message"] == "req_after_redirect"
    assert [m for m, _ in hits] == ["POST", "POST"]  # method preserved across redirect


def test_redirect_to_foreign_host_not_followed(monkeypatch):
    import httpx

    def handler(req):
        assert req.url.host.endswith("msg91.com"), "authkey leaked to foreign host!"
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})
    _set_transport(monkeypatch, handler)
    s, d = _run(se._msg91_widget_call("/sendOtpMobile", {"authkey": "x"}))
    assert s == 302
    assert d["redirect_location"] == "https://evil.example.com/steal"
    assert "redirected" in d["message"]


def test_redirect_loop_capped(monkeypatch):
    import httpx

    def handler(req):
        return httpx.Response(302, headers={"location": "https://control.msg91.com/api/v5/widget/sendOtpMobile"})
    _set_transport(monkeypatch, handler)
    s, d = _run(se._msg91_widget_call("/sendOtpMobile", {"authkey": "x"}))
    assert s == 508


def test_redirect_without_location(monkeypatch):
    import httpx

    def handler(req):
        return httpx.Response(302)
    _set_transport(monkeypatch, handler)
    s, d = _run(se._msg91_widget_call("/sendOtpMobile", {"authkey": "x"}))
    assert s == 302 and "unknown" in d["message"]


def test_max_verify_attempts(live_env, monkeypatch):
    calls = []
    _fake_provider(monkeypatch, calls)
    _run(se.issue_otp(MOBILE, "login"))
    for _ in range(se.OTP_MAX_VERIFY_ATTEMPTS):
        assert _run(se.verify_otp(MOBILE, "000000", "login")) is False
    # Attempts exhausted — even the correct OTP is now rejected locally
    assert _run(se.verify_otp(MOBILE, "123456", "login")) is False
