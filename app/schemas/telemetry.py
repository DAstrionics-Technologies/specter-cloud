from pydantic import BaseModel


class TelemetryPayload(BaseModel):
    drone_id: str
    lat: float
    lon: float
    alt: float
    speed: float
    heading: int
    battery: float
    voltage: float
    armed: bool
    flight_mode: str
    gps_fix_type: int
    satellites: int
