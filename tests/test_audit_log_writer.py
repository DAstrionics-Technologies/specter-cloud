"""Tests for app.audit.log.write — the audit log writer."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.audit import log as audit_log
from app.auth.password import hash_password
from app.models import AuditLog, Org, User


@pytest.fixture
async def org(db_session):
    o = Org(name="TestCo", slug="testco-audit")
    db_session.add(o)
    await db_session.flush()
    return o


@pytest.fixture
async def user(db_session, org):
    u = User(
        email="audit-user@example.com",
        password_hash=hash_password("hunter2"),
        name="Audit User",
        org_id=org.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def test_write_basic_authz_decision(db_session, user, org):
    entry = await audit_log.write(
        db_session,
        action="authz.granted",
        decision="allow",
        user_id=user.id,
        permission="drone:read",
        target_org_id=org.id,
        reason="granted_via_operator",
    )
    await db_session.flush()
    assert entry.id is not None
    assert entry.created_at is not None  # server_default applied


async def test_write_with_request_id_and_resource(db_session, user, org):
    request_id = uuid4()
    entry = await audit_log.write(
        db_session,
        action="authz.denied",
        decision="deny",
        user_id=user.id,
        request_id=request_id,
        permission="drone:command",
        resource_type="drone",
        resource_id="abc-123",
        target_org_id=org.id,
        reason="no_matching_role_grant",
        ip_address="10.0.0.5",
        user_agent="Specter-Dashboard/1.0",
    )
    await db_session.flush()

    fetched = await db_session.get(AuditLog, entry.id)
    assert fetched.request_id == request_id
    assert fetched.resource_type == "drone"
    assert fetched.resource_id == "abc-123"
    assert str(fetched.ip_address) == "10.0.0.5"
    assert fetched.user_agent == "Specter-Dashboard/1.0"


async def test_write_anonymous_event(db_session):
    """Some events have no user attached — login.failed for an unknown email,
    for instance. Writer must accept user_id=None."""
    entry = await audit_log.write(
        db_session,
        action="login.failed",
        decision="deny",
        user_id=None,
        reason="unknown_user",
        ip_address="203.0.113.7",
        extra={"attempted_email": "ghost@nowhere.example"},
    )
    await db_session.flush()
    assert entry.id is not None
    assert entry.user_id is None


async def test_write_jsonb_extra_roundtrip(db_session, user):
    entry = await audit_log.write(
        db_session,
        action="login.failed",
        decision="deny",
        user_id=user.id,
        extra={"attempt": 3, "from_country": "GB", "nested": {"keys": [1, 2]}},
    )
    await db_session.flush()
    await db_session.refresh(entry)
    assert entry.extra == {
        "attempt": 3,
        "from_country": "GB",
        "nested": {"keys": [1, 2]},
    }


async def test_write_rejects_invalid_decision(db_session):
    """Decision must be 'allow' or 'deny' — typos are bugs that would
    silently produce un-queryable audit data."""
    with pytest.raises(ValueError, match="invalid decision"):
        await audit_log.write(
            db_session,
            action="login.success",
            decision="yes",  # invalid
        )


async def test_write_does_not_commit(db_session, user):
    """Writer adds the row to the session; caller controls commit timing.

    This is important: for authz.granted on a route that subsequently fails,
    the audit row should roll back with the request. For authz.denied, the
    caller commits explicitly before raising — that's the require_permission
    contract. The writer itself stays simple.
    """
    entry = await audit_log.write(
        db_session,
        action="authz.granted",
        decision="allow",
        user_id=user.id,
    )
    # No flush yet — nothing is in the DB. The id only assigns on flush.
    assert entry.id is None


async def test_write_then_query(db_session, user):
    """Smoke test: write a row, query it back."""
    await audit_log.write(
        db_session,
        action="login.success",
        decision="allow",
        user_id=user.id,
    )
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "login.success"
