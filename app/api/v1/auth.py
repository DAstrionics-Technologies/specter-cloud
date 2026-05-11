"""Login / logout / current-user routes for human session auth.

Cookie-based for the dashboard browser. Bearer-token issuance lands when
the desktop GCS needs it — the session model already supports both
transports.
"""
from datetime import timedelta
from uuid import UUID

import structlog
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log as audit_log
from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.auth.login import LoginInvalid, LoginLocked, LoginSuccess, attempt_login
from app.auth.session import SESSION_TTL_DAYS, _hash_token, revoke_session
from app.core.config import settings
from app.core.database import get_db
from app.models.session import Session
from app.models.user import User


log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ============================================================
# Schemas
# ============================================================


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserView(BaseModel):
    id: UUID
    email: str
    name: str
    org_id: UUID

    @classmethod
    def from_model(cls, user: User) -> "UserView":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            org_id=user.org_id,
        )


class LoginResponse(BaseModel):
    user: UserView


# ============================================================
# Routes
# ============================================================


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Validate credentials and create a cookie-bound session.

    - 200 on success — sets the `specter_session` HttpOnly cookie and
      returns the user info.
    - 401 on bad credentials — generic detail to avoid email enumeration.
    - 423 when the account is temporarily locked.
    """
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None

    result = await attempt_login(
        db,
        email=payload.email,
        password=payload.password,
        transport="cookie",
        user_agent=user_agent,
        ip_address=ip,
    )

    if isinstance(result, LoginInvalid):
        await audit_log.write(
            db,
            action="login.failed",
            decision="deny",
            reason="invalid_credentials",
            ip_address=ip,
            user_agent=user_agent,
            extra={"attempted_email": payload.email.strip().lower()},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if isinstance(result, LoginLocked):
        await audit_log.write(
            db,
            action="login.locked",
            decision="deny",
            reason="account_locked",
            ip_address=ip,
            user_agent=user_agent,
            extra={
                "attempted_email": payload.email.strip().lower(),
                "locked_until": result.until.isoformat(),
            },
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed attempts",
        )

    # LoginSuccess
    assert isinstance(result, LoginSuccess)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.raw_token,
        max_age=int(timedelta(days=SESSION_TTL_DAYS).total_seconds()),
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )

    await audit_log.write(
        db,
        action="login.success",
        decision="allow",
        user_id=result.user.id,
        ip_address=ip,
        user_agent=user_agent,
    )
    await db.commit()

    log.info("login_success", user_id=str(result.user.id))
    return LoginResponse(user=UserView.from_model(result.user))


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),
    cookie_token: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current session and clear the browser cookie.

    Looks up the session by the token's hash (we don't store the raw
    token anywhere). If the lookup fails we still clear the client cookie
    and respond 200 — the client's local state should match.
    """
    if cookie_token:
        token_hash = _hash_token(cookie_token)
        sess = await db.scalar(
            select(Session).where(Session.token_hash == token_hash)
        )
        if sess is not None:
            await revoke_session(db, sess.id, reason="logout")

    response.delete_cookie(SESSION_COOKIE_NAME, path="/")

    await audit_log.write(
        db,
        action="logout",
        decision="allow",
        user_id=user.id,
    )
    await db.commit()

    return {"detail": "logged out"}


@router.get("/me", response_model=UserView)
async def me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile. The dashboard hits this on
    every page load to confirm the session is still valid."""
    return UserView.from_model(user)
