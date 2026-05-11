"""Tests for app.auth.session — token gen, lookup, revoke, expiry handling."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.auth.password import hash_password
from app.auth.session import (
    IDLE_TIMEOUT_DAYS,
    LAST_SEEN_DEBOUNCE_MINUTES,
    SESSION_TTL_DAYS,
    _hash_token,
    create_session,
    generate_token,
    lookup_session,
    revoke_all_user_sessions,
    revoke_session,
)
from app.models import Org, User


@pytest.fixture
async def org(db_session):
    o = Org(name="TestCo", slug="testco-session")
    db_session.add(o)
    await db_session.flush()
    return o


@pytest.fixture
async def user(db_session, org):
    u = User(
        email="session-user@example.com",
        password_hash=hash_password("hunter2"),
        name="Session User",
        org_id=org.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ============================================================
# Token generation
# ============================================================


def test_generate_token_returns_raw_and_hash():
    raw, hashed = generate_token()
    assert raw
    assert hashed
    assert len(hashed) == 64  # SHA-256 hex


def test_generate_token_each_call_unique():
    tokens = {generate_token()[0] for _ in range(50)}
    assert len(tokens) == 50  # No collisions across 50 calls


def test_hash_token_is_deterministic():
    raw = "fixed-input"
    assert _hash_token(raw) == _hash_token(raw)


def test_hash_token_different_for_different_input():
    assert _hash_token("a") != _hash_token("b")


# ============================================================
# create_session
# ============================================================


async def test_create_session_persists_hash_not_raw(db_session, user):
    raw_token, sess = await create_session(
        db_session,
        user_id=user.id,
        transport="cookie",
    )

    assert sess.user_id == user.id
    assert sess.transport == "cookie"
    assert sess.token_hash == _hash_token(raw_token)
    # Raw token must NOT appear anywhere in the persisted record
    assert sess.token_hash != raw_token


async def test_create_session_sets_expires_at(db_session, user):
    before = datetime.now(timezone.utc)
    _, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    after = datetime.now(timezone.utc)

    expected_min = before + timedelta(days=SESSION_TTL_DAYS) - timedelta(seconds=2)
    expected_max = after + timedelta(days=SESSION_TTL_DAYS) + timedelta(seconds=2)
    assert expected_min <= sess.expires_at <= expected_max


async def test_create_session_records_user_agent_and_ip(db_session, user):
    _, sess = await create_session(
        db_session,
        user_id=user.id,
        transport="bearer",
        user_agent="Specter-GCS/1.0",
        ip_address="10.0.0.5",
    )
    assert sess.user_agent == "Specter-GCS/1.0"
    # ip_address comes back as the str form of Postgres INET
    assert str(sess.ip_address) == "10.0.0.5"


# ============================================================
# lookup_session
# ============================================================


async def test_lookup_session_success(db_session, user):
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    found = await lookup_session(db_session, raw)
    assert found is not None
    assert found.id == sess.id


async def test_lookup_session_returns_none_for_bad_token(db_session, user):
    await create_session(db_session, user_id=user.id, transport="cookie")
    found = await lookup_session(db_session, "not-the-real-token")
    assert found is None


async def test_lookup_session_returns_none_for_empty_token(db_session):
    assert await lookup_session(db_session, "") is None


async def test_lookup_session_returns_none_when_revoked(db_session, user):
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    sess.revoked_at = datetime.now(timezone.utc)
    sess.revoked_reason = "logout"
    await db_session.flush()

    assert await lookup_session(db_session, raw) is None


async def test_lookup_session_returns_none_when_hard_expired(db_session, user):
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    assert await lookup_session(db_session, raw) is None


async def test_lookup_session_returns_none_when_idle_timeout(db_session, user):
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    # Push last_seen_at past the idle window
    sess.last_seen_at = datetime.now(timezone.utc) - timedelta(
        days=IDLE_TIMEOUT_DAYS + 1
    )
    await db_session.flush()

    assert await lookup_session(db_session, raw) is None


async def test_lookup_session_updates_last_seen_when_stale(db_session, user):
    """When last_seen_at is older than the debounce window, it should be
    updated to 'now' on lookup."""
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    # Push last_seen_at past the debounce window but still inside idle window
    sess.last_seen_at = datetime.now(timezone.utc) - timedelta(
        minutes=LAST_SEEN_DEBOUNCE_MINUTES + 1
    )
    await db_session.flush()

    before = datetime.now(timezone.utc)
    found = await lookup_session(db_session, raw)
    after = datetime.now(timezone.utc)

    assert found is not None
    # Tolerate 1s clock skew on either side
    assert before - timedelta(seconds=1) <= found.last_seen_at <= after + timedelta(seconds=1)


async def test_lookup_session_does_not_update_last_seen_when_fresh(db_session, user):
    """Within the debounce window, last_seen_at should not be touched."""
    raw, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    original = sess.last_seen_at

    # Sleep is unnecessary — last_seen_at was just set by create_session and
    # is well within the 5-minute window. Lookup should leave it alone.
    found = await lookup_session(db_session, raw)
    assert found is not None
    assert found.last_seen_at == original


# ============================================================
# revoke_session
# ============================================================


async def test_revoke_session_marks_revoked_at_and_reason(db_session, user):
    _, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    revoked = await revoke_session(db_session, sess.id, reason="logout")
    assert revoked is True

    await db_session.refresh(sess)
    assert sess.revoked_at is not None
    assert sess.revoked_reason == "logout"


async def test_revoke_session_returns_false_if_already_revoked(db_session, user):
    _, sess = await create_session(db_session, user_id=user.id, transport="cookie")
    await revoke_session(db_session, sess.id, reason="logout")

    second = await revoke_session(db_session, sess.id, reason="logout")
    assert second is False


async def test_revoke_session_returns_false_for_unknown_id(db_session):
    assert await revoke_session(db_session, uuid4(), reason="logout") is False


# ============================================================
# revoke_all_user_sessions
# ============================================================


async def test_revoke_all_user_sessions_counts(db_session, user):
    """All active sessions should be revoked; revoked or other-user sessions untouched."""
    await create_session(db_session, user_id=user.id, transport="cookie")
    await create_session(db_session, user_id=user.id, transport="bearer")
    _, already = await create_session(db_session, user_id=user.id, transport="cookie")
    already.revoked_at = datetime.now(timezone.utc)
    already.revoked_reason = "earlier"
    await db_session.flush()

    count = await revoke_all_user_sessions(db_session, user.id, reason="admin_action")
    assert count == 2  # The previously-revoked one is not re-counted


async def test_revoke_all_user_sessions_transport_filter(db_session, user):
    """Filtering by transport revokes only that subset."""
    _, cookie_s = await create_session(db_session, user_id=user.id, transport="cookie")
    _, bearer_s = await create_session(db_session, user_id=user.id, transport="bearer")

    count = await revoke_all_user_sessions(
        db_session, user.id, reason="lost_device", transport="bearer"
    )
    assert count == 1

    await db_session.refresh(bearer_s)
    await db_session.refresh(cookie_s)
    assert bearer_s.revoked_at is not None
    assert cookie_s.revoked_at is None  # untouched


async def test_revoke_all_user_sessions_returns_zero_when_no_active(db_session, user):
    count = await revoke_all_user_sessions(db_session, user.id, reason="logout")
    assert count == 0
