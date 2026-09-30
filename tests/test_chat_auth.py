"""Chat access control (Q54): single-use codes, session cookie, expiry, revocation, quota."""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.chat_auth import AuthStore, normalise_code
from backend.chat_pricing import Usage, cost_usd
from backend.main import create_app

SECRET = "test-admin-secret"
ADMIN = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture
def auth(tmp_path):
    return AuthStore(tmp_path / "auth.sqlite", SECRET)


@pytest.fixture
def client(tmp_path, auth):
    # The app's lifespan (artefact loading) isn't needed for these routes, so no `with`.
    # https: the session cookie is Secure.
    # A placeholder model client: these tests never reach the model
    app = create_app(tmp_path, chat_auth=auth, chat_client=object())
    return TestClient(app, base_url="https://testserver")


def later(hours: float = 2) -> str:
    return (datetime.now().astimezone() + timedelta(hours=hours)).isoformat()


def new_codes(client, n=1, **kw) -> list[str]:
    body = {"count": n, "expires_at": later(), **kw}
    r = client.post("/api/admin/codes", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["codes"]


def test_code_format_and_normalisation(auth):
    codes = auth.create_codes(20, int(time.time()) + 60)
    assert len(set(codes)) == 20
    for c in codes:
        assert len(c) == 9 and c[4] == "-"
        assert not set(c.replace("-", "")) & set("01ILO")
    assert normalise_code(" k7qm-4rxp ") == "K7QM4RXP"


def test_codes_are_not_stored_in_plain_text(auth, tmp_path):
    (code,) = auth.create_codes(1, int(time.time()) + 60)
    raw = (tmp_path / "auth.sqlite").read_bytes()
    assert normalise_code(code).encode() not in raw and code.encode() not in raw


def test_redeem_once_then_session_cookie(client):
    (code,) = new_codes(client)
    assert client.get("/api/chat/status").json() == {
        "available": True, "authenticated": False, "expires_at": None,
        "budget_usd": None, "spent_usd": None,
    }  # fmt: skip

    r = client.post("/api/chat/session", json={"code": code.lower().replace("-", " ")})
    assert r.status_code == 200
    assert r.json()["authenticated"]
    assert (r.json()["budget_usd"], r.json()["spent_usd"]) == (0.30, 0)  # default budget
    set_cookie = r.headers["set-cookie"].lower()
    for attr in ("httponly", "secure", "samesite=strict", "path=/api"):
        assert attr in set_cookie
    assert client.get("/api/chat/status").json()["authenticated"]

    # Single use: the same code fails in another browser
    other = TestClient(client.app, base_url="https://testserver")
    assert other.post("/api/chat/session", json={"code": code}).status_code == 401


def test_invalid_codes_never_block(client):
    # No attempt limit (Q54): shared IPs (carrier-grade NAT, venue Wi-Fi) must not lock people out
    for _ in range(20):
        assert client.post("/api/chat/session", json={"code": "AAAA-AAAA"}).status_code == 401
    (code,) = new_codes(client)
    assert client.post("/api/chat/session", json={"code": code}).status_code == 200


def test_expired_code_rejected(client, auth):
    (code,) = auth.create_codes(1, int(time.time()) - 1)
    assert client.post("/api/chat/session", json={"code": code}).status_code == 401
    r = client.post("/api/admin/codes", json={"count": 1, "expires_at": later(-1)}, headers=ADMIN)
    assert r.status_code == 422


def test_session_expires_with_its_code(client, auth):
    (code,) = auth.create_codes(1, int(time.time()) + 1)
    assert client.post("/api/chat/session", json={"code": code}).status_code == 200
    time.sleep(1.1)
    assert not client.get("/api/chat/status").json()["authenticated"]


def test_budget_and_usage(client, auth):
    (code,) = new_codes(client, budget_usd=0.01)
    client.post("/api/chat/session", json={"code": code})
    sid = client.get("/api/admin/sessions", headers=ADMIN).json()[0]["id"]
    assert auth.start_question(sid)
    # Haiku 4.5: 2000 × $1 + 4000 × $1.25 + 10000 × $0.10 + 500 × $5 per MTok = $0.0105
    usage = Usage(input_tokens=2000, output_tokens=500, cache_read_tokens=10_000,
                  cache_write_5m_tokens=4000)  # fmt: skip
    assert auth.record_usage(sid, "claude-haiku-4-5", usage) == pytest.approx(0.0105)
    assert not auth.start_question(sid)  # budget spent: no more questions
    s = client.get("/api/admin/sessions", headers=ADMIN).json()[0]
    assert (s["questions"], s["input_tokens"], s["output_tokens"]) == (1, 2000, 500)
    assert (s["cache_read_tokens"], s["cache_write_tokens"]) == (10_000, 4000)
    assert s["spent_usd"] == pytest.approx(0.0105) and s["budget_usd"] == 0.01
    assert "token_hash" not in s
    status = client.get("/api/chat/status").json()
    assert (status["budget_usd"], status["spent_usd"]) == (0.01, 0.0105)
    assert client.get("/api/admin/status", headers=ADMIN).json()["spent_usd"] == 0.0105


def test_budget_limits(client):
    for bad in (0, -1, 5.01):
        body = {"count": 1, "expires_at": later(), "budget_usd": bad}
        assert client.post("/api/admin/codes", json=body, headers=ADMIN).status_code == 422


def test_pricing():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000,
              cache_write_5m_tokens=1_000_000, cache_write_1h_tokens=1_000_000)  # fmt: skip
    assert cost_usd("claude-haiku-4-5", u) == pytest.approx(1 + 5 + 0.10 + 1.25 + 2)
    assert cost_usd("claude-sonnet-5-5", u) == pytest.approx(2 + 10 + 0.20 + 2.50 + 4)
    with pytest.raises(ValueError):
        cost_usd("unknown-model", u)


def test_usage_from_api():
    split = SimpleNamespace(ephemeral_5m_input_tokens=30, ephemeral_1h_input_tokens=70)
    api = SimpleNamespace(input_tokens=10, output_tokens=20, cache_read_input_tokens=40,
                          cache_creation_input_tokens=100, cache_creation=split)  # fmt: skip
    assert Usage.from_api(api) == Usage(10, 20, 40, 30, 70)
    # Without the per-duration split, writes count at the 5-minute rate
    api.cache_creation = None
    assert Usage.from_api(api) == Usage(10, 20, 40, 100, 0)


def test_revoke_one_and_all(client):
    a, b, unused = new_codes(client, 3, label="giuria")
    other = TestClient(client.app, base_url="https://testserver")
    client.post("/api/chat/session", json={"code": a})
    other.post("/api/chat/session", json={"code": b})
    sessions = client.get("/api/admin/sessions", headers=ADMIN).json()
    assert [s["label"] for s in sessions] == ["giuria", "giuria"]

    r = client.post(f"/api/admin/sessions/{sessions[0]['id']}/revoke", headers=ADMIN)
    assert r.status_code == 200
    assert not client.get("/api/chat/status").json()["authenticated"]
    assert other.get("/api/chat/status").json()["authenticated"]

    assert client.post("/api/admin/revoke-all", headers=ADMIN).json() == {"sessions": 1, "codes": 1}
    assert not other.get("/api/chat/status").json()["authenticated"]
    assert client.post("/api/chat/session", json={"code": unused}).status_code == 401
    status = client.get("/api/admin/status", headers=ADMIN).json()
    assert status["codes"] == {"total": 3, "used": 2, "unused": 0, "dead": 1}
    assert status["sessions_active"] == 0


def test_switch_off(client):
    (code,) = new_codes(client, 1)
    client.post("/api/chat/session", json={"code": code})
    assert client.put("/api/admin/chat", json={"enabled": False}, headers=ADMIN).json() == {
        "enabled": False
    }
    assert client.get("/api/chat/status").json()["available"] is False
    (code2,) = new_codes(client, 1)
    assert client.post("/api/chat/session", json={"code": code2}).status_code == 503
    client.put("/api/admin/chat", json={"enabled": True}, headers=ADMIN)
    assert client.get("/api/chat/status").json()["authenticated"]  # the session survived


def test_logout(client):
    (code,) = new_codes(client)
    client.post("/api/chat/session", json={"code": code})
    client.delete("/api/chat/session")
    assert not client.get("/api/chat/status").json()["authenticated"]


def test_admin_requires_secret(client):
    assert client.get("/api/admin/status").status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    one, too_many = {"count": 1, "expires_at": later()}, {"count": 51, "expires_at": later()}
    assert client.post("/api/admin/codes", json=one, headers=bad).status_code == 401
    assert client.post("/api/admin/codes", json=too_many, headers=ADMIN).status_code == 422


def test_not_configured_means_no_chat(tmp_path, auth):
    url = "https://testserver"
    c = TestClient(create_app(tmp_path, chat_auth=None, chat_client=object()), base_url=url)
    assert c.get("/api/chat/status").json()["available"] is False
    assert c.post("/api/chat/session", json={"code": "AAAA-AAAA"}).status_code == 503
    assert c.get("/api/admin/status", headers=ADMIN).status_code == 404
    # Access configured but no model (no ANTHROPIC_API_KEY): unavailable, admin API still there
    c = TestClient(create_app(tmp_path, chat_auth=auth, chat_client=None), base_url=url)
    assert c.get("/api/chat/status").json()["available"] is False
    assert c.get("/api/admin/status", headers=ADMIN).status_code == 200
