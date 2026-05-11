import structlog

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import verify_api_key
from app.auth.session import lookup_session
from app.core.database import get_db
from app.models.drone import Drone
from app.models.user import User

log = structlog.get_logger()


# Name of the HttpOnly cookie carrying the dashboard session token.
SESSION_COOKIE_NAME = "specter_session"


async def get_current_drone(
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        session: AsyncSession = Depends(get_db),
    ) -> Drone:
    """
      FastAPI dependency: authenticate a request via the X-API-Key header.

      Returns the Drone on success.
      Raises 401 Unauthorized on any failure (missing, malformed, unknown, revoked).

      The drone_id and org_id for downstream handlers come from the returned
      Drone instance — never trust those fields from the request body.
      """
    if x_api_key is None:
        log.warning("missing_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    drone = await verify_api_key(x_api_key, session)
    if drone is None:
        # verify_api_key has already logged the specific reason
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    log.debug("api_key_authenticated", drone_id=drone.id)
    return drone


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    cookie_token: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(None),
) -> User:
    """FastAPI dependency: authenticate a human user via session cookie OR bearer token.

    Cookie (dashboard) takes priority — if both are present, cookie wins.
    Bearer is for the desktop GCS, where cookies are awkward.

    Returns the User on success. Raises 401 on:
      - No credential present
      - Token doesn't match an active session
      - Session revoked / hard-expired / idle-timed-out
      - User account is inactive

    The org_id for downstream authorization comes from the returned User
    or the resource being acted on — never from the request body.
    """
    raw_token: str | None = cookie_token

    if raw_token is None and authorization is not None:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_token = parts[1].strip() or None

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sess = await lookup_session(db, raw_token)
    if sess is None:
        # lookup_session returns None for any failure mode. We don't
        # distinguish in the response — same 401 for "bad token" and
        # "expired" — to avoid leaking session state to attackers.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, sess.user_id)
    if user is None or not user.is_active:
        log.warning(
            "session_for_inactive_or_missing_user",
            user_id=str(sess.user_id),
            session_id=str(sess.id),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
