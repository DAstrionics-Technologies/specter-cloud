"""Integration tests for /api/v1/auth/{login,logout,me}.

Uses the existing db_client fixture (FakeRedis + savepoint-rolled session).
"""
import pytest

from app.auth.password import hash_password
from app.models import Org, User


@pytest.fixture
async def org(db_session):
    o = Org(name="TestCo", slug="testco-routes")
    db_session.add(o)
    await db_session.flush()
    return o


@pytest.fixture
async def user(db_session, org):
    u = User(
        email="alice@example.com",
        password_hash=hash_password("hunter2-strong-pass"),
        name="Alice",
        org_id=org.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ============================================================
# /login
# ============================================================


async def test_login_success_sets_cookie_and_returns_user(db_client, user):
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "hunter2-strong-pass"},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["name"] == "Alice"
    assert body["user"]["id"] == str(user.id)

    # Cookie set
    set_cookie = resp.headers.get("set-cookie", "")
    assert "specter_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie


async def test_login_with_wrong_password_returns_401(db_client, user):
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers or "specter_session" not in resp.headers.get("set-cookie", "")


async def test_login_with_unknown_email_returns_401(db_client):
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_login_email_normalized_lowercase(db_client, user):
    """Mixed-case email at login should match the lowercased stored email."""
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "Alice@Example.com", "password": "hunter2-strong-pass"},
    )
    assert resp.status_code == 200


async def test_login_inactive_user_returns_401(db_client, db_session, user):
    user.is_active = False
    await db_session.commit()

    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "hunter2-strong-pass"},
    )
    assert resp.status_code == 401


async def test_login_lockout_after_threshold_attempts(db_client, user):
    """Five failed attempts → 423 Locked on the 6th."""
    for _ in range(5):
        resp = await db_client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    # 6th attempt — should be locked even with correct password
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "hunter2-strong-pass"},
    )
    assert resp.status_code == 423


async def test_login_validation_rejects_empty_password(db_client):
    resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.com", "password": ""},
    )
    assert resp.status_code == 422  # pydantic validation


# ============================================================
# /me
# ============================================================


async def test_me_unauthenticated_returns_401(db_client):
    resp = await db_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_valid_session_returns_user(db_client, user):
    """Round-trip: login → get cookie → call /me → see ourselves."""
    login_resp = await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "hunter2-strong-pass"},
    )
    assert login_resp.status_code == 200
    # httpx auto-stores the Set-Cookie for subsequent requests on the same client

    me_resp = await db_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "alice@example.com"


async def test_me_with_bogus_cookie_returns_401(db_client):
    resp = await db_client.get(
        "/api/v1/auth/me",
        cookies={"specter_session": "not-a-real-token"},
    )
    assert resp.status_code == 401


# ============================================================
# /logout
# ============================================================


async def test_logout_revokes_session_and_clears_cookie(db_client, user):
    await db_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "hunter2-strong-pass"},
    )

    logout_resp = await db_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    # Set-Cookie with empty value or Max-Age=0
    set_cookie = logout_resp.headers.get("set-cookie", "")
    assert "specter_session" in set_cookie

    # Subsequent /me should fail because the session is revoked
    me_resp = await db_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401


async def test_logout_unauthenticated_returns_401(db_client):
    resp = await db_client.post("/api/v1/auth/logout")
    assert resp.status_code == 401


# ============================================================
# Bearer token (Authorization header) — Phase 1B-A doesn't issue these from
# /login, but /me should accept them for tests that simulate the GCS path.
# ============================================================


async def test_me_accepts_bearer_token(db_client, db_session, user):
    """Sessions can also be authenticated via Authorization: Bearer header.
    Even though our login endpoint only issues cookies in v1, the dependency
    should accept bearer tokens for the desktop GCS use case."""
    from app.auth.session import create_session
    raw_token, _ = await create_session(
        db_session, user_id=user.id, transport="bearer"
    )

    resp = await db_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"
