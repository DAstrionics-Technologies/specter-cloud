"""Login flow + account lockout state machine.

Wraps password verification, failed-attempt tracking, lockout decisions,
and session creation into one cohesive call. Lives separately from
session.py so the session module stays a pure session-record concern.

Lockout policy (commercial v1):
  - 5 failed attempts in a row → 15-minute lock
  - On lock, failed_login_count is reset to 0 (it'll count again after
    the lock expires)
  - Successful login clears both fields

This is intentionally simple. If a customer needs progressive lockout
(15min → 1h → 24h), add a `lockout_count` column and revisit. For v1
the flat 15-min policy is enough to defang automated brute force without
making operators wait too long when they fat-finger their password.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, needs_rehash, verify_password
from app.auth.session import SessionTransport, create_session
from app.models.session import Session
from app.models.user import User


# Lockout policy
LOCKOUT_THRESHOLD = 5            # Failed attempts before account locks
LOCKOUT_DURATION_MINUTES = 15    # How long the lock lasts


@dataclass
class LoginSuccess:
    user: User
    raw_token: str
    session: Session


@dataclass
class LoginInvalid:
    """Bad credentials. Intentionally generic — no detail about which
    field was wrong, to mitigate email enumeration."""


@dataclass
class LoginLocked:
    until: datetime


LoginResult = LoginSuccess | LoginInvalid | LoginLocked


async def attempt_login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    transport: SessionTransport,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> LoginResult:
    """Attempt a login. One of three outcomes:
      - LoginSuccess: credentials valid, session created
      - LoginInvalid: bad email or password (response indistinguishable
        between the two cases on purpose)
      - LoginLocked: account currently locked due to repeated failures

    Caller is responsible for the audit log row that explains *why*. This
    function commits its own DB changes (failed-count increments, lockout
    timestamps, last_login_at, session insert) so they persist regardless
    of what happens later in the request.
    """
    email = email.strip().lower()

    user = await db.scalar(select(User).where(User.email == email))

    if user is None:
        # Burn similar CPU as a successful verify to mitigate timing
        # attacks that probe whether an email exists. Hash output is discarded.
        hash_password("placeholder-to-burn-cpu")
        return LoginInvalid()

    if not user.is_active:
        return LoginInvalid()

    now = datetime.now(timezone.utc)

    if user.locked_until is not None and user.locked_until > now:
        return LoginLocked(until=user.locked_until)

    if not verify_password(password, user.password_hash):
        # Increment failed count, possibly trigger lockout
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            user.failed_login_count = 0  # restart counting after the lock expires
        await db.commit()
        return LoginInvalid()

    # --- Success path ---
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    # Re-hash if argon2 cost params have moved upward in a release
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    raw_token, sess = await create_session(
        db,
        user_id=user.id,
        transport=transport,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await db.commit()

    return LoginSuccess(user=user, raw_token=raw_token, session=sess)
