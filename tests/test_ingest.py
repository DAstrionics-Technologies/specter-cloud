ingest_api_route = "/api/v1/ingest/telemetry"


def _valid_payload() -> dict:
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


async def test_ingest_returns_200(db_client, authed_drone):
    _drone, raw_key = authed_drone
    response = await db_client.post(
        ingest_api_route,
        json=_valid_payload(),
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ingest_invalid_payload_returns_422(db_client, authed_drone):
    _drone, raw_key = authed_drone
    payload = _valid_payload()
    payload["lat"] = "Not a number"
    del payload["satellites"]

    response = await db_client.post(
        ingest_api_route,
        json=payload,
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_ingest_missing_api_key_returns_401(db_client):
    response = await db_client.post(ingest_api_route, json=_valid_payload())
    assert response.status_code == 401


async def test_ingest_invalid_api_key_returns_401(db_client):
    response = await db_client.post(
        ingest_api_route,
        json=_valid_payload(),
        headers={"X-API-Key": "sk_drone_deadbeef_notarealsecret"},
    )
    assert response.status_code == 401
