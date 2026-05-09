from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, SmallInteger, Boolean, Text, DateTime, func, text

from app.models.base import Base


class Role(Base):
    """Roles seeded by migration. The id is small and stable; never auto-assigned.

    Stable IDs let migrations and seeds reference roles without name lookups
    and stay consistent across all environments.

    Cloud v1 commercial uses ids 1, 2, 6 (viewer/operator/admin).
    Ids 3-5 (planner, technician, developer) are seeded for forward
    compatibility with the GCS rollout and the military fork; their permission
    bundles in `app/auth/permissions.py` are empty (planner, technician) or
    Specter-only (developer) until those products ship.

    `is_platform_role = True` marks roles that may only be granted at the
    Specter root org (currently: developer). UI/API grant flows enforce this
    in addition to the application-level PLATFORM_ONLY_ROLES check.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(Text)
    is_platform_role: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
