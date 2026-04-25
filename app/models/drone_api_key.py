from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Uuid, DateTime, func, ForeignKey

from app.models.base import Base


class DroneApiKey(Base):
    __tablename__ = "drone_api_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    drone_id: Mapped[UUID] = mapped_column(
        ForeignKey("drones.id", ondelete="CASCADE"),  
        index=True
    )
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    hashed_key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(80))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))