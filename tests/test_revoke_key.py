import pytest

from app.auth.api_key import verify_api_key
from scripts.revoke_key import revoke_by_drone, revoke_by_prefix


def _extract_prefix(raw_key: str) -> str:
    # Format: sk_drone_<8-hex-prefix>_<secret>
    return raw_key[len("sk_drone_"):].split("_", 1)[0]


# --- revoke_by_prefix path ---


async def test_revoke_by_prefix_success(db_session, authed_drone):
    _drone, raw_key = authed_drone
    prefix = _extract_prefix(raw_key)

    rows = await revoke_by_prefix(db_session, prefix)
    assert rows == 1

    result = await verify_api_key(raw_key, db_session)
    assert result is None


async def test_revoke_by_prefix_returns_zero_when_no_match(db_session):
    rows = await revoke_by_prefix(db_session, "deadbeef")
    assert rows == 0


async def test_revoke_by_prefix_returns_zero_when_already_revoked(db_session, authed_drone):
    _drone, raw_key = authed_drone
    prefix = _extract_prefix(raw_key)

    first = await revoke_by_prefix(db_session, prefix)
    assert first == 1

    second = await revoke_by_prefix(db_session, prefix)
    assert second == 0


# --- revoke_by_drone path ---


async def test_revoke_by_drone_success(db_session, authed_drone):
    _drone, raw_key = authed_drone

    rows = await revoke_by_drone(db_session, "test-org", "test-drone")
    assert rows == 1

    result = await verify_api_key(raw_key, db_session)
    assert result is None


async def test_revoke_by_drone_raises_when_org_missing(db_session, authed_drone):
    with pytest.raises(ValueError, match="No org 'nope'"):
        await revoke_by_drone(db_session, "nope", "test-drone")


async def test_revoke_by_drone_raises_when_drone_missing(db_session, authed_drone):
    with pytest.raises(ValueError, match="No drone 'nope'"):
        await revoke_by_drone(db_session, "test-org", "nope")


async def test_revoke_by_drone_returns_zero_when_no_active_keys(db_session, unkeyed_drone):
    rows = await revoke_by_drone(db_session, "test-org", "test-drone")
    assert rows == 0
