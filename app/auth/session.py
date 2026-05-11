"""Server-side session management for human users.

Tokens are random 32-byte URL-safe strings. We persist only their SHA-256
hashes in `sessions.token_hash`, the same security model used by drone
API keys (`DroneApiKey.hashed_key`). A DB leak doesn't yield usable tokens.

Two transports share one table, distinguished by `sessions.transport`:
  - 'cookie' — HttpOnly Secure cookie, dashboard browser sessions
  - 'bearer' — Authorization header, desktop GCS sessions

Sessions have two timeouts:
  - SESSION_TTL_DAYS: hard expiry (default 30)
  - IDLE_TIMEOUT_DAYS: sliding idle (default 7, on `last_seen_at`)
The hard cap means a token can't live forever even if used continuously;
the idle cap means a forgotten session expires reasonably quickly.

Last-seen updates are debounced — only persisted when the session is
>5 minutes stale. This keeps high-frequency requests from hammering
the row.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


SessionTransport = Literal["cookie", "bearer"]

TOKEN_BYTES = 32                # 256-bit opaque token
SESSION_TTL_DAYS = 30           # Hard expiry
IDLE_TIMEOUT_DAYS = 7           # Sliding idle window
LAST_SEEN_DEBOUNCE_MINUTES = 5  # Only update last_seen_at if this stale


def generate_token() -> tuple[str, str]:
    """Generate (raw_token, token_hash). Show raw_token to the client once,
    persist the hash. Hash is SHA-256 hex (64 chars), deterministic per token.
    """
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, _hash_token(raw)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    transport: SessionTransport,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, Session]:
    """Create a fresh session for `user_id` with the given transport.

    Returns (raw_token, session_record). The raw token is the only place
    the unhashed value ever appears in the system; persist nothing of it
    beyond what's returned to the client.
    """
    raw_token, token_hash = generate_token()
    now = datetime.now(timezone.utc)

    sess = Session(
        user_id=user_id,
        token_hash=token_hash,
        transport=transport,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(sess)
    await db.flush()

    return raw_token, sess


async def lookup_session(db: AsyncSession, raw_token: str) -> Session | None:
    """Return the active Session for a raw token, or None if invalid.

    None means: bad token, no matching hash, revoked, hard-expired, or
    idle-timed-out. The caller (FastAPI dep) translates None to 401.

    Side effect: updates `last_seen_at` if the session is more than
    LAST_SEEN_DEBOUNCE_MINUTES stale, and commits the change. Same pattern
    as `verify_api_key` updating `last_used_at` on the drone API key.
    """
    if not raw_token:
        return None

    token_hash = _hash_token(raw_token)
    sess = await db.scalar(select(Session).where(Session.token_hash == token_hash))
    if sess is None:
        return None

    if sess.revoked_at is not None:
        return None

    now = datetime.now(timezone.utc)
    if now > sess.expires_at:
        return None

    idle_cutoff = now - timedelta(days=IDLE_TIMEOUT_DAYS)
    if sess.last_seen_at < idle_cutoff:
        return None

    if (now - sess.last_seen_at) > timedelta(minutes=LAST_SEEN_DEBOUNCE_MINUTES):
        sess.last_seen_at = now
        await db.commit()

    return sess


async def revoke_session(
    db: AsyncSession,
    session_id: UUID,
    reason: str,
) -> bool:
    """Revoke a session by id. Returns True if it transitioned from active
    to revoked, False if it was already revoked or absent.

    Commits so the revocation persists immediately — same pattern as
    `lookup_session` updating `last_seen_at`. A logout that returns 200
    must mean the session is actually invalidated.
    """
    sess = await db.get(Session, session_id)
    if sess is None or sess.revoked_at is not None:
        return False

    sess.revoked_at = datetime.now(timezone.utc)
    sess.revoked_reason = reason
    await db.commit()
    return True


async def revoke_all_user_sessions(
    db: AsyncSession,
    user_id: UUID,
    reason: str,
    transport: SessionTransport | None = None,
) -> int:
    """Revoke all active sessions for a user. Optionally limit to one transport
    (e.g., revoke all bearer tokens after a desktop loss without affecting the
    user's browser cookie).

    Commits so the revocations persist immediately. Returns the count.
    """
    query = select(Session).where(
        Session.user_id == user_id,
        Session.revoked_at.is_(None),
    )
    if transport is not None:
        query = query.where(Session.transport == transport)

    sessions = (await db.execute(query)).scalars().all()
    if not sessions:
        return 0

    now = datetime.now(timezone.utc)
    for sess in sessions:
        sess.revoked_at = now
        sess.revoked_reason = reason
    await db.commit()
    return len(sessions)
