import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drone import Drone
from app.models.drone_api_key import DroneApiKey


KEY_TAG = "sk_drone_"
PREFIX_BYTES = 4
SECRET_BYTES = 24
LAST_USED_DEBOUNCE_SECONDS = 60


def hash_key(raw: str) -> str:
    """SHA-256 hex digest of the raw key. Deterministic, 64 chars."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new drone API key.

    Returns (raw_key, prefix, hashed_key):
    - raw_key: plaintext `sk_drone_<prefix>_<secret>`. Show to operator ONCE, never store.
    - prefix: 8 hex chars. Stored for O(1) lookup.
    - hashed_key: SHA-256 hex (64 chars). Stored for verification.
    """
    prefix = secrets.token_hex(PREFIX_BYTES)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    raw = f"{KEY_TAG}{prefix}_{secret}"
    hashed_key = hash_key(raw)
    
    return raw, prefix, hashed_key


def parse_key(raw: str) -> tuple[str, str] | None:
    """
    Validate the on-the-wire format and split into (prefix, secret).

    Returns None if the key is malformed (wrong type, wrong tag,
    wrong shape, non-hex prefix, empty secret). Callers treat None as "reject".
    """
    if not isinstance(raw, str) or not raw.startswith(KEY_TAG):
        return None

    parts = raw[len(KEY_TAG):].split("_", 1)
    
    if len(parts) != 2:
        return None
    
    prefix, secret = parts
    
    if len(prefix) != PREFIX_BYTES * 2 or not secret:
        return None

    try:
        int(prefix, 16)
    except ValueError:
        return None

    return prefix, secret


async def verify_api_key(raw: str, session: AsyncSession) -> Drone | None:
    """
    Full verification. Returns the authenticated Drone, or None on failure.
    None means: bad format, no matching row, revoked key, hash mismatch,
    or deactivated drone. The caller (FastAPI dep) translates None → 401.
    """
    parsed_key = parse_key(raw)
    if parsed_key is None:
        return None
    
    prefix, _secret = parsed_key
    stmt = (
        select(DroneApiKey, Drone)
        .join(Drone, Drone.id == DroneApiKey.drone_id)
        .where(
            DroneApiKey.prefix == prefix,
            DroneApiKey.revoked_at.is_(None),
            Drone.is_active.is_(True),
        )
    )

    result = await session.execute(stmt)
    rows = result.all()

    hashed_key = hash_key(raw)
    matched_api_key = None
    matched_drone = None
    for api_key_row, drone in rows:
        if hmac.compare_digest(hashed_key, api_key_row.hashed_key):
            matched_api_key = api_key_row
            matched_drone = drone
            break

    if matched_api_key is None:
        return None

    update_stmt = (
        update(DroneApiKey)
        .where(
            DroneApiKey.id == matched_api_key.id,
            (DroneApiKey.last_used_at.is_(None))
            | (DroneApiKey.last_used_at < func.now() - timedelta(seconds=LAST_USED_DEBOUNCE_SECONDS)),
        )
        .values(last_used_at=func.now())
    )

    await session.execute(update_stmt)
    await session.commit()
    return matched_drone