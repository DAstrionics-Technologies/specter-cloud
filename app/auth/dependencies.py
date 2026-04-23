from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import verify_api_key
from app.core.database import get_db
from app.models.drone import Drone


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    drone = await verify_api_key(x_api_key, session)
    if drone is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return drone
