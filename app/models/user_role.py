from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    SmallInteger,
    Uuid,
    DateTime,
    ForeignKey,
    Text,
    PrimaryKeyConstraint,
    func,
)

from app.models.base import Base


class UserRole(Base):
    """Grant of a role to a user, scoped to an org.

    A grant at org X is effective at X and all descendants of X (the
    permission check walks up the org tree from the target resource).

    Soft-delete only: never DELETE rows. Set `revoked_at` and `revoked_by`
    to retire a grant. Audit ("who had access on date Y") needs the history.

    `granted_by` and `revoked_by` are FK to users; both nullable because:
      - `granted_by` is NULL for system-bootstrapped grants (the first admin
        granted by the bootstrap script, before any user existed to attribute).
      - `revoked_by` is NULL while the grant is active.
      - Either becomes NULL via SET NULL if the actor user is later deleted.
        Audit trail is preserved via the audit_log table; user_roles fields
        are convenience.
    """

    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    org_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("orgs.id", ondelete="CASCADE")
    )
    role_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT")
    )

    granted_by: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    revoked_by: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "org_id", "role_id"),
    )
