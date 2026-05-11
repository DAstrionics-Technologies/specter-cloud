"""Bootstrap the Specter root org and the first admin user.

Idempotent: refuses to do anything destructive if the Specter org already
has at least one active admin grant. Safe to run on every deploy.

Usage
-----
Set environment variables, then run as a module from the project root:

    SPECTER_ORG_ID=<uuid>                          (required, fixed across envs)
    SPECTER_BOOTSTRAP_EMAIL=admin@specter.example  (required)
    SPECTER_BOOTSTRAP_PASSWORD=<password>          (required)
    SPECTER_BOOTSTRAP_NAME="Specter Admin"         (optional, default "Specter Admin")

    python -m scripts.bootstrap_specter_org

What it does
------------
  1. Verifies the Specter org row exists with the configured fixed UUID;
     creates it if absent (parent_org_id = NULL, slug = "specter").
  2. Creates the initial admin user (email-normalized to lowercase).
  3. Grants `admin` and `developer` roles at the Specter org.
  4. Idempotency check: if Specter org already has an active admin grant,
     returns False (the CLI then prints a no-op message).

After bootstrap
---------------
Every customer org should be created with parent_org_id = SPECTER_ORG_ID.
The Specter staff member who ran bootstrap can log in via the standard
auth flow and manage the platform from there.
"""
import asyncio
import os
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.core.database import SessionLocal
from app.models.org import Org
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: {name} environment variable is required")
    return value


async def bootstrap(
    session: AsyncSession,
    org_id: UUID,
    email: str,
    password: str,
    name: str = "Specter Admin",
) -> bool:
    """Idempotent bootstrap. Creates Specter root org (if absent), initial
    admin user, and grants admin + developer roles at the Specter org.

    Returns:
        True if bootstrap performed work.
        False if it was a no-op (Specter org already has at least one
        active admin grant).

    Raises:
        ValueError: if 'admin' or 'developer' role missing (migrations
            not run), or if the chosen email already belongs to another user.
    """
    email = email.strip().lower()
    name = name.strip()

    admin_role = await session.scalar(
        select(Role).where(Role.name == "admin")
    )
    if admin_role is None:
        raise ValueError(
            "'admin' role not found in roles table. Run alembic migrations first."
        )

    existing_grant = await session.scalar(
        select(UserRole).where(
            UserRole.org_id == org_id,
            UserRole.role_id == admin_role.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if existing_grant is not None:
        return False

    org = await session.get(Org, org_id)
    if org is None:
        org = Org(
            id=org_id,
            name="Specter",
            slug="specter",
            parent_org_id=None,
        )
        session.add(org)
        await session.flush()

    existing_user = await session.scalar(
        select(User).where(User.email == email)
    )
    if existing_user is not None:
        raise ValueError(
            f"user with email {email!r} already exists. "
            f"Cannot proceed — manual intervention required."
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        org_id=org_id,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    developer_role = await session.scalar(
        select(Role).where(Role.name == "developer")
    )
    if developer_role is None:
        raise ValueError(
            "'developer' role not found. Migrations may be incomplete."
        )

    for role in (admin_role, developer_role):
        session.add(
            UserRole(
                user_id=user.id,
                org_id=org_id,
                role_id=role.id,
                granted_by=None,
            )
        )

    await session.commit()
    return True


async def _main() -> None:
    org_id = UUID(_required_env("SPECTER_ORG_ID"))
    email = _required_env("SPECTER_BOOTSTRAP_EMAIL")
    password = _required_env("SPECTER_BOOTSTRAP_PASSWORD")
    name = os.environ.get("SPECTER_BOOTSTRAP_NAME", "Specter Admin")

    async with SessionLocal() as session:
        try:
            performed = await bootstrap(session, org_id, email, password, name)
        except ValueError as e:
            sys.exit(f"error: {e}")

    if performed:
        print(
            f"bootstrap complete: Specter org={org_id} admin={email.strip().lower()}"
        )
    else:
        print(
            "Specter org already has at least one active admin grant. No-op."
        )


if __name__ == "__main__":
    asyncio.run(_main())
