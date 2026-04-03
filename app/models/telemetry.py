from sqlalchemy import String, Float, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.models.base import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        primary_key=True,
    )
    drone_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt: Mapped[float] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    heading: Mapped[int] = mapped_column(Integer)
    battery: Mapped[float] = mapped_column(Float)
    voltage: Mapped[float] = mapped_column(Float)
    armed: Mapped[bool] = mapped_column(Boolean)
    flight_mode: Mapped[str] = mapped_column(String(32))
    gps_fix_type: Mapped[int] = mapped_column(Integer)
    satellites: Mapped[int] = mapped_column(Integer)
