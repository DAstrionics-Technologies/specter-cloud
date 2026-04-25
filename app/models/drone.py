from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Uuid, DateTime, func, text, ForeignKey, UniqueConstraint

from app.models.base import Base



class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(60))
    org_id: Mapped[UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_drone_org_slug"),)