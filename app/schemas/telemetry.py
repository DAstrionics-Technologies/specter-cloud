from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    """
    Telemetry payload schema.
    """
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    # MAVLink relative_alt is signed (above-home displacement). Negatives are
    # legitimate: rooftop takeoff with ground descent, valley/mine surveys,
    # GPS noise around home. Lower bound is a sanity ceiling, not a physics one.
    alt: float = Field(..., ge=-1000, le=10000)
    speed: float = Field(..., ge=0, le=200)
    heading: int = Field(..., ge=0, lt=360)
    battery: float = Field(..., ge=0, le=100)
    voltage: float = Field(..., ge=0, le=60)
    armed: bool
    # Pattern-validated rather than enum-closed. Decouples cloud schema
    # from firmware mode catalogs (ArduCopter/Plane/Rover all differ);
    # accepts UNKNOWN during the boot window before first HEARTBEAT.
    flight_mode: str = Field(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    gps_fix_type: int = Field(..., ge=0, le=8)
    satellites: int = Field(..., ge=0, le=64)
