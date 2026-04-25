import pytest

from app.auth.api_key import verify_api_key
from scripts.mint_key import mint


async def test_mint_succeeds_with_valid_org_and_drone(db_session, unkeyed_drone):
    raw_key = await mint(db_session, "test-org", "test-drone", "smoke")

    assert raw_key.startswith("sk_drone_")

    authed = await verify_api_key(raw_key, db_session)
    assert authed is not None
    assert authed.id == unkeyed_drone.id


async def test_mint_raises_when_org_missing(db_session, unkeyed_drone):
    with pytest.raises(ValueError, match="Organization 'nope' not found"):
        await mint(db_session, "nope", "test-drone", "smoke")


async def test_mint_raises_when_drone_missing(db_session, unkeyed_drone):
    with pytest.raises(ValueError, match="Drone 'nope' not found"):
        await mint(db_session, "test-org", "nope", "smoke")


async def test_mint_raises_when_active_key_exists(db_session, authed_drone):
    with pytest.raises(ValueError, match="active api key"):
        await mint(db_session, "test-org", "test-drone", "rotation")
