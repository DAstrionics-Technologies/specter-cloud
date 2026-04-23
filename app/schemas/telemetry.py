from pydantic import BaseModel, Field
from typing import Literal


FLIGHT_MODE = Literal["STABILIZE", "ALT_HOLD", "LOITER", "AUTO", "RTL", "LAND", "GUIDED", "POSHOLD", "BRAKE",]


class TelemetryPayload(BaseModel):
    """
    Telemetry payload schema.
    """
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float = Field(..., ge=0, le=10000)
    speed: float = Field(..., ge=0, le=200)
    heading: int = Field(..., ge=0, lt=360)
    battery: float = Field(..., ge=0, le=100)
    voltage: float = Field(..., ge=0, le=60)
    armed: bool
    flight_mode: FLIGHT_MODE
    gps_fix_type: int = Field(..., ge=0, le=8)
    satellites: int = Field(..., ge=0, le=64)
