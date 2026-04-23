import pytest
from pydantic import ValidationError

from app.schemas.telemetry import TelemetryPayload


def _valid_data() -> dict:
    return {
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


async def test_valid_payload():
    payload = TelemetryPayload(**_valid_data())
    assert payload.lat == 28.6139
    assert payload.lon == 77.2090
    assert payload.flight_mode == "STABILIZE"
    assert payload.armed is True


async def test_missing_field_rejected():
    with pytest.raises(ValidationError):
        TelemetryPayload(**{"lat": 28.6139})


async def test_wrong_type_rejected():
    data = _valid_data()
    data["lat"] = "Not a number"
    with pytest.raises(ValidationError):
        TelemetryPayload(**data)


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("lat", 91.0),
        ("lat", -91.0),
        ("lon", 181.0),
        ("lon", -181.0),
        ("alt", -1.0),
        ("alt", 10_001.0),
        ("speed", -1.0),
        ("speed", 201.0),
        ("heading", -1),
        ("heading", 360),
        ("battery", -1.0),
        ("battery", 101.0),
        ("voltage", -1.0),
        ("voltage", 61.0),
        ("gps_fix_type", -1),
        ("gps_fix_type", 9),
        ("satellites", -1),
        ("satellites", 65),
        ("flight_mode", "MANUAL"),
        ("flight_mode", ""),
    ],
)
async def test_out_of_range_rejected(field, bad_value):
    data = _valid_data()
    data[field] = bad_value
    with pytest.raises(ValidationError):
        TelemetryPayload(**data)
