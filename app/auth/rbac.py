"""Permission checks via recursive CTE walk of the org hierarchy.

This module is the heart of the RBAC system. Every authorized route uses
`require_permission(...)` as a FastAPI dependency. The check answers:

    "Does this user have a role granting this permission, at this org or
     any ancestor of this org?"

The walk is a single SQL query (Postgres recursive CTE). Walks stop at
MAX_HIERARCHY_DEPTH to defend against accidental org cycles. Real customer
trees rarely exceed 3-4 levels; the cap is cheap insurance.

Design rules:
  - DON'T trust client-supplied org_ids. Always resolve the target org
    from the resource being acted on (drone, mission, user). The
    `org_resolver` callable handles this — see resolve_drone_org for the
    pattern.
  - DON'T cache permission decisions. A role revocation must take effect
    immediately. The CTE is fast (~1-3 ms with the partial indexes from
    the migration); the cache miss is acceptable.
  - DO audit every decision (allow + deny). Audit rows for deny are
    committed before the 403 raises so they persist past the request
    transaction unwind.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log as audit_log
from app.auth.dependencies import get_current_user
from app.auth.permissions import Permission, roles_with_permission
from app.core.database import get_db
from app.models.user import User


# Defense against accidentally introducing an org cycle. The CTE will
# stop at depth=10 and the auth check fails closed (no match -> deny).
MAX_HIERARCHY_DEPTH = 10


@dataclass
class PermissionCheckResult:
    """Outcome of an authorization check, including provenance for audit logging."""

    allowed: bool
    matched_role_id: int | None
    matched_org_id: UUID | None
    matched_role_name: str | None
    reason: str


# Type alias: an org resolver extracts the target org from the request.
# Typically by reading a path/body param and looking up the resource.
OrgResolver = Callable[[Request, AsyncSession], Awaitable[UUID]]


async def check_permission(
    user: User,
    permission: Permission,
    target_org_id: UUID,
    db: AsyncSession,
) -> PermissionCheckResult:
    """Walk the org hierarchy upward from `target_org_id`. Find the closest
    ancestor at which the user has an active role grant whose bundle
    includes `permission`. Return that match, or a deny result.

    The closest match (smallest depth) wins. If the user has both `viewer`
    at corps and `operator` at battalion, a battalion-scoped check returns
    operator-via-battalion, not viewer-via-corps. The audit log captures
    which level matched.
    """
    eligible_roles = roles_with_permission(permission)
    if not eligible_roles:
        return PermissionCheckResult(
            allowed=False,
            matched_role_id=None,
            matched_org_id=None,
            matched_role_name=None,
            reason="permission_not_in_any_role",
        )

    query = text(
        """
        WITH RECURSIVE org_chain AS (
            SELECT id, parent_org_id, 0 AS depth
            FROM orgs
            WHERE id = :target_org_id
            UNION ALL
            SELECT o.id, o.parent_org_id, c.depth + 1
            FROM orgs o
            JOIN org_chain c ON o.id = c.parent_org_id
            WHERE c.depth < :max_depth
        )
        SELECT ur.role_id, ur.org_id, r.name
        FROM user_roles ur
        JOIN org_chain c ON ur.org_id = c.id
        JOIN roles r ON ur.role_id = r.id
        WHERE ur.user_id = :user_id
          AND ur.revoked_at IS NULL
          AND r.name = ANY(:eligible_roles)
        ORDER BY c.depth ASC
        LIMIT 1
        """
    )

    row = (
        await db.execute(
            query,
            {
                "target_org_id": target_org_id,
                "user_id": user.id,
                "eligible_roles": eligible_roles,
                "max_depth": MAX_HIERARCHY_DEPTH,
            },
        )
    ).first()

    if row is None:
        return PermissionCheckResult(
            allowed=False,
            matched_role_id=None,
            matched_org_id=None,
            matched_role_name=None,
            reason="no_matching_role_grant",
        )

    return PermissionCheckResult(
        allowed=True,
        matched_role_id=row.role_id,
        matched_org_id=row.org_id,
        matched_role_name=row.name,
        reason=f"granted_via_{row.name}",
    )


def require_permission(
    permission: Permission,
    org_resolver: OrgResolver | None = None,
):
    """FastAPI dependency factory.

    Usage:
        @router.post("/drones/{drone_id}/command")
        async def send_command(
            drone_id: UUID,
            user: User = Depends(require_permission(
                Permission.DRONE_COMMAND, resolve_drone_org
            )),
        ): ...

    `org_resolver` extracts the target org from the request, typically by
    looking up the resource (drone, mission, user) and reading its org_id.
    Don't trust client-supplied org_ids — always resolve from the resource.

    If `org_resolver` is None, the user's home org is used. Suitable for
    routes that operate against the user's own org (e.g., GET /me).
    """

    async def checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if org_resolver is not None:
            target_org_id = await org_resolver(request, db)
        else:
            target_org_id = user.org_id

        result = await check_permission(user, permission, target_org_id, db)

        request_id = _extract_request_id(request)

        await audit_log.write(
            db,
            action="authz.granted" if result.allowed else "authz.denied",
            decision="allow" if result.allowed else "deny",
            user_id=user.id,
            request_id=request_id,
            permission=permission.value,
            target_org_id=target_org_id,
            matched_role_id=result.matched_role_id,
            matched_org_id=result.matched_org_id,
            reason=result.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        if not result.allowed:
            # Commit so the deny audit row persists past the 403's transaction
            # unwind. At this point in the request lifecycle nothing else has
            # been modified, so this commit only persists the audit row.
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def _extract_request_id(request: Request) -> UUID | None:
    """Pull the X-Request-ID off request.state if RequestIDMiddleware set it.
    Returns None if absent or malformed — audit row just gets a NULL there.
    """
    raw = getattr(request.state, "request_id", None)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None
