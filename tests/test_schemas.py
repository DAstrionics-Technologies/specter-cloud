from app.schemas.telemetry import TelemetryPayload
from pydantic import ValidationError
import pytest


async def test_valid_payload():
    data = {
        "drone_id": "drone-1",
        "lat": 28.6139,
        "lon": 77.2090,
        "alt": 42.0,
        "speed": 12.5,
        "heading": 356,
        "battery": 88.0,
        "voltage": 16.2,
        "armed": True,
        "flight_mode": "STABILIZE",
        "gps_fix_type": 3,
        "satellites": 14,
    }
    payload = TelemetryPayload(**data)
    assert payload.drone_id == "drone-1"
    assert payload.lat == 28.6139
    assert payload.lon == 77.2090
    assert payload.alt == 42.0
    assert payload.speed == 12.5
    assert payload.heading == 356
    assert payload.battery == 88.0
    assert payload.voltage == 16.2
    assert payload.armed is True
    assert payload.flight_mode == "STABILIZE"
    assert payload.gps_fix_type == 3
    assert payload.satellites == 14


async def test_missing_field_rejected():
    data = {
        "drone_id": "drone-1",
        "lat": 28.6139,
    }
    with pytest.raises(ValidationError):
        TelemetryPayload(**data)


async def test_wrong_type_rejected():
    data = {
        "drone_id": "drone-1",
        "lat": "Not a number",
        "lon": 77,
        "alt": 42,
        "speed": 12.5,
        "heading": 356,
        "battery": 88.0,
        "voltage": 16.2,
        "armed": 1,
        "flight_mode": "STABILIZE",
        "gps_fix_type": 3,
        "satellites": 14,
    }

    with pytest.raises(ValidationError):
        TelemetryPayload(**data)
