from sqlalchemy import select
from app.models.telemetry import TelemetryRecord


ingest_api_route = "/api/v1/ingest/telemetry"


async def test_ingest_returns_200(db_client):
    payload = {
        "drone_id": "test-drone-persistence",
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
    response = await db_client.post(ingest_api_route, json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ingest_invalid_payload_returns_422(db_client):
    payload = {
        "drone_id": "test-drone-persistence",
        "lat": "Not a number",
        "lon": 77.2090,
        "alt": 42.0,
        "speed": 12.5,
        "heading": 356,
        "battery": 88.0,
        "voltage": 16.2,
        "armed": True,
        "flight_mode": "STABILIZE",
        "gps_fix_type": 3,
        # "satellites": 14,
    }
    response = await db_client.post(ingest_api_route, json=payload)
    assert response.status_code == 422


async def test_ingest_persistence_to_db(db_client, db_session):
    payload = {
        "drone_id": "test-drone-persistence",
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

    response = await db_client.post(ingest_api_route, json=payload)
    assert response.status_code == 200

    result = await db_session.execute(
        select(TelemetryRecord).where(TelemetryRecord.drone_id == "test-drone-persistence")
    )
    record = result.scalar_one()
    assert record.drone_id == payload["drone_id"]
    assert record.alt == payload["alt"]
