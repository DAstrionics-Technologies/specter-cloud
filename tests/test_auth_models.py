"""Integration tests for the auth models against a real Postgres.

Exercises constraints, defaults, and the seed data the migration installs.
Uses the savepoint-rolled `db_session` fixture from conftest.py.
"""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.password import hash_password
from app.models import AuditLog, Org, Role, Session, User, UserRole


@pytest.fixture
async def org(db_session):
    o = Org(name="TestCo", slug="testco")
    db_session.add(o)
    await db_session.flush()
    return o


@pytest.fixture
async def user(db_session, org):
    u = User(
        email="alice@example.com",
        password_hash=hash_password("hunter2"),
        name="Alice",
        org_id=org.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ============================================================
# User
# ============================================================


async def test_user_email_unique(db_session, org, user):
    duplicate = User(
        email="alice@example.com",
        password_hash=hash_password("other"),
        name="Alice 2",
        org_id=org.id,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_server_defaults(db_session, user):
    """is_active defaults to true, failed_login_count to 0, lockout/login fields null."""
    await db_session.refresh(user)
    assert user.is_active is True
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.last_login_at is None
    assert user.email_verified_at is None


async def test_user_requires_org_id(db_session):
    """org_id is NOT NULL — every user belongs to exactly one org."""
    orphan = User(
        email="orphan@example.com",
        password_hash=hash_password("x"),
        name="Orphan",
        # org_id omitted
    )
    db_session.add(orphan)
    with pytest.raises(IntegrityError):
        await db_session.flush()


# ============================================================
# Role (seeded data)
# ============================================================


async def test_seeded_roles_present_with_correct_ids_and_names(db_session):
    """Migration seeds 6 roles with stable IDs. This test guards against
    drift between the migration seed and the Permission catalog assumptions."""
    result = await db_session.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()
    rows = [(r.id, r.name) for r in roles]
    assert rows == [
        (1, "viewer"),
        (2, "operator"),
        (3, "planner"),
        (4, "technician"),
        (5, "developer"),
        (6, "admin"),
    ]


async def test_developer_role_is_platform_role(db_session):
    role = await db_session.scalar(select(Role).where(Role.name == "developer"))
    assert role.is_platform_role is True


async def test_non_developer_roles_are_not_platform_roles(db_session):
    """Only `developer` is platform-locked. Other roles are grantable at any org."""
    for name in ("viewer", "operator", "planner", "technician", "admin"):
        role = await db_session.scalar(select(Role).where(Role.name == name))
        assert role.is_platform_role is False, (
            f"unexpected platform-role flag on {name!r}"
        )


# ============================================================
# UserRole
# ============================================================


async def test_grant_user_role(db_session, org, user):
    operator_role = await db_session.scalar(
        select(Role).where(Role.name == "operator")
    )
    grant = UserRole(
        user_id=user.id,
        org_id=org.id,
        role_id=operator_role.id,
    )
    db_session.add(grant)
    await db_session.flush()

    fetched = await db_session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.org_id == org.id,
            UserRole.role_id == operator_role.id,
        )
    )
    assert fetched is not None
    assert fetched.revoked_at is None
    assert fetched.granted_at is not None


async def test_user_role_composite_pk_prevents_duplicate(db_session, org, user):
    """Same (user, org, role) cannot be granted twice. To re-grant after
    revocation, the existing row's revoked_at must be cleared, not a new row."""
    operator_role = await db_session.scalar(
        select(Role).where(Role.name == "operator")
    )
    db_session.add(UserRole(user_id=user.id, org_id=org.id, role_id=operator_role.id))
    await db_session.flush()

    db_session.add(UserRole(user_id=user.id, org_id=org.id, role_id=operator_role.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_revoke_user_role_soft_deletes(db_session, org, user):
    """Revoking sets revoked_at + revoked_reason; row is preserved for audit."""
    admin_role = await db_session.scalar(select(Role).where(Role.name == "admin"))
    grant = UserRole(user_id=user.id, org_id=org.id, role_id=admin_role.id)
    db_session.add(grant)
    await db_session.flush()

    grant.revoked_at = datetime.now(timezone.utc)
    grant.revoked_reason = "promoted out of role"
    await db_session.flush()

    fetched = await db_session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == admin_role.id,
        )
    )
    assert fetched is not None  # row preserved
    assert fetched.revoked_at is not None
    assert fetched.revoked_reason == "promoted out of role"


async def test_user_role_user_can_grant_multiple_roles_at_same_org(db_session, org, user):
    """Same user can have multiple distinct roles at the same org."""
    operator_role = await db_session.scalar(
        select(Role).where(Role.name == "operator")
    )
    admin_role = await db_session.scalar(select(Role).where(Role.name == "admin"))

    db_session.add(UserRole(user_id=user.id, org_id=org.id, role_id=operator_role.id))
    db_session.add(UserRole(user_id=user.id, org_id=org.id, role_id=admin_role.id))
    await db_session.flush()

    grants = (
        await db_session.execute(
            select(UserRole).where(UserRole.user_id == user.id)
        )
    ).scalars().all()
    assert {g.role_id for g in grants} == {operator_role.id, admin_role.id}


# ============================================================
# Session
# ============================================================


async def test_session_token_hash_unique(db_session, user):
    """Two sessions cannot share a token_hash — would mean token collision."""
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    s1 = Session(
        user_id=user.id,
        token_hash="a" * 64,
        transport="cookie",
        expires_at=expires,
    )
    db_session.add(s1)
    await db_session.flush()

    s2 = Session(
        user_id=user.id,
        token_hash="a" * 64,
        transport="bearer",
        expires_at=expires,
    )
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_session_transport_distinguishes_channels(db_session, user):
    """Same user can have a cookie session AND a bearer session simultaneously."""
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    db_session.add(
        Session(
            user_id=user.id,
            token_hash="c" * 64,
            transport="cookie",
            expires_at=expires,
        )
    )
    db_session.add(
        Session(
            user_id=user.id,
            token_hash="b" * 64,
            transport="bearer",
            expires_at=expires,
        )
    )
    await db_session.flush()

    sessions = (
        await db_session.execute(
            select(Session).where(Session.user_id == user.id)
        )
    ).scalars().all()
    assert len(sessions) == 2
    assert {s.transport for s in sessions} == {"cookie", "bearer"}


async def test_session_revoked_fields_default_null(db_session, user):
    """Active sessions have null revoked_at + revoked_reason."""
    sess = Session(
        user_id=user.id,
        token_hash="d" * 64,
        transport="cookie",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sess)
    await db_session.flush()
    await db_session.refresh(sess)
    assert sess.revoked_at is None
    assert sess.revoked_reason is None
    assert sess.created_at is not None
    assert sess.last_seen_at is not None


# ============================================================
# AuditLog
# ============================================================


async def test_audit_log_basic_insert(db_session, user, org):
    audit = AuditLog(
        user_id=user.id,
        action="authz.granted",
        permission="drone:read",
        resource_type="drone",
        resource_id="some-uuid",
        target_org_id=org.id,
        decision="allow",
        reason="granted_via_operator",
    )
    db_session.add(audit)
    await db_session.flush()
    assert audit.id is not None  # bigserial assigned
    assert audit.created_at is not None  # server_default applied


async def test_audit_log_metadata_jsonb_roundtrip(db_session, user):
    """The Python attribute is `extra`; the SQL column is `metadata`.
    Verify a JSONB roundtrip works."""
    audit = AuditLog(
        user_id=user.id,
        action="login.failed",
        decision="deny",
        extra={"attempt": 3, "ip": "1.2.3.4", "nested": {"a": [1, 2]}},
    )
    db_session.add(audit)
    await db_session.flush()
    await db_session.refresh(audit)
    assert audit.extra == {"attempt": 3, "ip": "1.2.3.4", "nested": {"a": [1, 2]}}


async def test_audit_log_anonymous_event_allowed(db_session):
    """Some events have no associated user (e.g., login.failed for unknown email).
    user_id is nullable — these still get logged."""
    audit = AuditLog(
        user_id=None,
        action="login.failed",
        decision="deny",
        reason="unknown_user",
    )
    db_session.add(audit)
    await db_session.flush()
    assert audit.id is not None
    assert audit.user_id is None
