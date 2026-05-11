from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    String,
    Text,
    BigInteger,
    SmallInteger,
    Uuid,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB

from app.models.base import Base


class AuditLog(Base):
    """Append-only audit log. Application code never UPDATEs or DELETEs.

    Every authorization decision (allow + deny) writes a row here, plus
    authentication events (login success/failure, logout), session
    lifecycle (issued, revoked), and privileged actions (role grants,
    revocations, password changes).

    For commercial v1 we run unpartitioned. When the table grows past
    ~100M rows (low priority for v1), partition by month. Cold archival
    after 90 days is the v1 retention plan; defense fork extends to 7y.

    User and org references are SET NULL on parent delete to preserve
    history. The textual `action`, `permission`, `resource_*` fields
    keep the audit row meaningful even if related rows vanish later.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    action: Mapped[str] = mapped_column(String(60))
    permission: Mapped[str | None] = mapped_column(String(60), nullable=True)

    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_org_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )

    matched_role_id: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    matched_org_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )

    decision: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    extra: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
