"""Tests for scripts.bootstrap_specter_org.bootstrap().

Exercises the idempotent bootstrap flow that creates the Specter root org
and the first admin user. Uses the savepoint-rolled session — production
SessionLocal is never touched.
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.password import hash_password, verify_password
from app.models import Org, Role, User, UserRole
from scripts.bootstrap_specter_org import bootstrap


async def test_bootstrap_creates_org_user_and_grants(db_session):
    org_id = uuid4()
    performed = await bootstrap(
        db_session,
        org_id=org_id,
        email="admin@specter.example",
        password="hunter2-strong-pass",
        name="Initial Admin",
    )
    assert performed is True

    org = await db_session.get(Org, org_id)
    assert org is not None
    assert org.slug == "specter"
    assert org.name == "Specter"
    assert org.parent_org_id is None  # root

    user = await db_session.scalar(
        select(User).where(User.email == "admin@specter.example")
    )
    assert user is not None
    assert user.name == "Initial Admin"
    assert user.org_id == org_id
    assert verify_password("hunter2-strong-pass", user.password_hash) is True


async def test_bootstrap_grants_admin_and_developer_at_specter_org(db_session):
    org_id = uuid4()
    await bootstrap(
        db_session,
        org_id=org_id,
        email="admin2@specter.example",
        password="another-strong-password",
        name="Admin Two",
    )

    user = await db_session.scalar(
        select(User).where(User.email == "admin2@specter.example")
    )
    grant_rows = (
        await db_session.execute(
            select(UserRole, Role)
            .join(Role, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, UserRole.org_id == org_id)
        )
    ).all()

    role_names = {r.name for _, r in grant_rows}
    assert role_names == {"admin", "developer"}

    # All grants are active and system-attributed
    for grant, _ in grant_rows:
        assert grant.revoked_at is None
        assert grant.granted_by is None  # system bootstrap


async def test_bootstrap_email_normalized_lowercase(db_session):
    """Mixed-case email at input → stored lowercase. Prevents duplicate
    accounts from case variants of the same address."""
    org_id = uuid4()
    await bootstrap(
        db_session,
        org_id=org_id,
        email="MixedCase@Specter.example",
        password="strong-pass-123",
    )

    user = await db_session.scalar(
        select(User).where(User.email == "mixedcase@specter.example")
    )
    assert user is not None


async def test_bootstrap_idempotent_when_already_done(db_session):
    """Re-running bootstrap when an active admin grant exists is a safe no-op."""
    org_id = uuid4()

    first = await bootstrap(
        db_session,
        org_id=org_id,
        email="admin3@specter.example",
        password="strong-pass-123",
    )
    assert first is True

    second = await bootstrap(
        db_session,
        org_id=org_id,
        email="admin3@specter.example",
        password="strong-pass-123",
    )
    assert second is False


async def test_bootstrap_rejects_duplicate_email(db_session):
    """If the email chosen for the first admin is already in use by an
    existing user (e.g., a customer signed up with the same address before
    the operator ran bootstrap), bootstrap must fail loudly with a clear
    ValueError, not a silent collision or DB-level integrity error.
    """
    # Pre-create a non-Specter org with a user that holds the email.
    # Using a non-Specter org so the slug-uniqueness constraint on the
    # later bootstrap call doesn't fire first.
    other_org = Org(name="OtherCo", slug="otherco")
    db_session.add(other_org)
    await db_session.flush()

    db_session.add(
        User(
            email="dup@specter.example",
            password_hash=hash_password("their-password"),
            name="Existing Customer",
            org_id=other_org.id,
        )
    )
    await db_session.flush()

    specter_org_id = uuid4()
    with pytest.raises(ValueError, match="already exists"):
        await bootstrap(
            db_session,
            org_id=specter_org_id,
            email="dup@specter.example",
            password="strong-pass-123",
        )


async def test_bootstrap_default_name_when_omitted(db_session):
    """If name is omitted, defaults to 'Specter Admin'."""
    org_id = uuid4()
    await bootstrap(
        db_session,
        org_id=org_id,
        email="defname@specter.example",
        password="strong-pass-123",
    )

    user = await db_session.scalar(
        select(User).where(User.email == "defname@specter.example")
    )
    assert user.name == "Specter Admin"


async def test_bootstrap_password_is_hashed_not_stored_plain(db_session):
    """Sanity check that password ends up in argon2 form, not plaintext."""
    org_id = uuid4()
    plaintext = "very-strong-pass-456"
    await bootstrap(
        db_session,
        org_id=org_id,
        email="hashcheck@specter.example",
        password=plaintext,
    )

    user = await db_session.scalar(
        select(User).where(User.email == "hashcheck@specter.example")
    )
    # Stored value is not the plaintext, and is in argon2id format
    assert user.password_hash != plaintext
    assert user.password_hash.startswith("$argon2id$")


async def test_bootstrap_user_is_active(db_session):
    """First admin must be active immediately — cannot be locked out at birth."""
    org_id = uuid4()
    await bootstrap(
        db_session,
        org_id=org_id,
        email="active@specter.example",
        password="strong-pass-123",
    )

    user = await db_session.scalar(
        select(User).where(User.email == "active@specter.example")
    )
    assert user.is_active is True
    assert user.locked_until is None
    assert user.failed_login_count == 0
