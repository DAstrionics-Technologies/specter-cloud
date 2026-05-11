from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Uuid, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import INET

from app.models.base import Base


class Session(Base):
    """Server-side session record. The opaque token issued to the client never
    appears in this table — only its SHA-256 hash. Same security model as
    drone API keys (DroneApiKey.hashed_key): a DB leak doesn't yield usable
    tokens.

    `transport` distinguishes how the session was issued:
      - 'cookie': HttpOnly Secure cookie, dashboard browser sessions.
      - 'bearer': Authorization: Bearer header, desktop GCS sessions.
    Lets us revoke en-masse by transport (e.g., revoke all bearer tokens for
    a user after a desktop loss) without affecting the other channel.

    `revoked_at` + `revoked_reason` for soft-delete and audit. Never DELETE.
    """

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    transport: Mapped[str] = mapped_column(String(16))

    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
