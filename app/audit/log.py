"""Audit log writer.

Append-only writes to the audit_log table. Every authentication and
authorization decision is logged here — defense audits, SOC2, and
incident response all depend on completeness.

Design
------
Writes are NOT batched. Every authz decision writes one row synchronously
within the request transaction. This keeps audit entries consistent with
the action they describe (if the request fails, the audit row rolls back —
which is correct: "we never authorized that").

For deny decisions (where the request is about to fail with 403), the
caller commits explicitly so the deny audit persists even though the
request transaction will unwind. See `app.auth.rbac.require_permission`.

Scaling beyond v1: if audit volume becomes a problem, consider:
- Async queue (Kafka/Redis) for non-critical events
- Monthly partitioning of audit_log
- A read replica for compliance / reporting queries
"""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


_VALID_DECISIONS = frozenset({"allow", "deny"})


async def write(
    db: AsyncSession,
    *,
    action: str,
    decision: str,
    user_id: UUID | None = None,
    request_id: UUID | None = None,
    permission: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    target_org_id: UUID | None = None,
    matched_role_id: int | None = None,
    matched_org_id: UUID | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit log row to the session. Caller controls commit timing.

    For request-scoped audit (typical authz checks), call this from within
    the request transaction. For deny decisions, the caller should commit
    before raising, so the audit survives the request unwind.

    Returns the AuditLog model so callers can inspect the assigned id if
    they need to (after flush).
    """
    if decision not in _VALID_DECISIONS:
        raise ValueError(
            f"invalid decision {decision!r}; must be one of {_VALID_DECISIONS}"
        )

    entry = AuditLog(
        user_id=user_id,
        request_id=request_id,
        action=action,
        permission=permission,
        resource_type=resource_type,
        resource_id=resource_id,
        target_org_id=target_org_id,
        matched_role_id=matched_role_id,
        matched_org_id=matched_org_id,
        decision=decision,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        extra=extra,
    )
    db.add(entry)
    return entry
