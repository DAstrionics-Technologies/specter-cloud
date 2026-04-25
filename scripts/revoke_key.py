"""
revoke_key.py — mark a drone API key revoked. Takes effect immediately.

Usage:
    python scripts/revoke_key.py --prefix <8-hex-prefix>
    python scripts/revoke_key.py --org-slug <slug> --drone-slug <slug>

--prefix revokes a single key. --drone-slug revokes every active key on
that drone (the break-glass option when you don't know which prefix).
"""
import argparse
import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import Drone, DroneApiKey, Org


async def revoke_by_prefix(session: AsyncSession, prefix: str) -> int:
    stmt = (
        update(DroneApiKey)
        .where(
            DroneApiKey.prefix == prefix,
            DroneApiKey.revoked_at.is_(None),
        ).values(revoked_at=func.now())
    )

    result = await session.execute(stmt)
    await session.commit()

    rows_affected: int = result.rowcount

    return rows_affected


async def revoke_by_drone(session: AsyncSession, org_slug: str, drone_slug: str) -> int:
    orgs = await session.execute(select(Org).where(Org.slug==org_slug))
    org: Org | None = orgs.scalar_one_or_none()
            
    if org is None:
        raise ValueError(f"No org '{org_slug}' found!")

    drones = await session.execute(select(Drone).where(Drone.slug==drone_slug, Drone.org_id==org.id))
    drone: Drone | None = drones.scalar_one_or_none()

    if drone is None:
        raise ValueError(f"No drone '{drone_slug}' found in org '{org_slug}'!")

    stmt = (
        update(DroneApiKey)
        .where(
            DroneApiKey.drone_id == drone.id,
            DroneApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    result = await session.execute(stmt)
    await session.commit()
    rows_affected: int = result.rowcount 

    return rows_affected


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prefix", help="Revoke a single key by its 8-hex prefix")
    group.add_argument(
        "--drone-slug",
        help="Revoke ALL active keys on this drone (requires --org-slug)",
    )
    parser.add_argument("--org-slug", help="Required with --drone-slug")
    args = parser.parse_args()

    if  args.drone_slug and not args.org_slug:
        parser.error("--org-slug is required when --drone-slug is provided")

    async def _run() -> int:
        async with SessionLocal() as session:
            if args.prefix:
                return await revoke_by_prefix(session, args.prefix)
            return await revoke_by_drone(session, args.org_slug, args.drone_slug)
            
    count = asyncio.run(_run())
    print(f"Revoked {count} key(s).")


if __name__ == "__main__":
    main()
