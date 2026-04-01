from pydantic import BaseModel


class TelemetryPayload(BaseModel):
    drone_id: str
    lat: float
    lon: float
    alt: float
    speed: float
    battery: float
