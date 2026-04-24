"""
mint_key.py — issue a new drone API key.

Usage:
    python scripts/mint_key.py --org-slug <slug> --drone-slug <slug> --label <str>

Output: raw API key on stdout. Copy it once — it is never recoverable.
"""
import argparse
import asyncio
import sys

from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import generate_api_key
from app.core.database import SessionLocal
from app.models import Drone, DroneApiKey, Org


async def mint(session: AsyncSession, org_slug: str, drone_slug: str, label: str) -> str:
    orgs = await session.execute(select(Org).where(Org.slug == org_slug))
    org: Org | None = orgs.scalar_one_or_none()
    if org is None:
        raise ValueError(f"Organization '{org_slug}' not found")

    drones = await session.execute(select(Drone).where(Drone.org_id == org.id, Drone.slug == drone_slug))
    drone: Drone | None = drones.scalar_one_or_none()
    if drone is None:
        raise ValueError(f"Drone '{drone_slug}' not found in organization '{org_slug}'")

    result = await session.execute(
        select(DroneApiKey).where(
            DroneApiKey.drone_id == drone.id,
            DroneApiKey.revoked_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"active api key for the Drone '{drone_slug}' available, revoke it first")

    raw_key, prefix, hashed_key = generate_api_key()

    stmt = insert(DroneApiKey).values(drone_id=drone.id, prefix=prefix, hashed_key=hashed_key, label=label)

    await session.execute(stmt)
    await session.commit()

    return raw_key


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--org-slug", required=True)
    parser.add_argument("--drone-slug", required=True)
    parser.add_argument(
        "--label",
        required=True,
        help="Free-form label, e.g. 'initial provisioning' or 'rotation 2026-04-24'",
    )
    args = parser.parse_args()

    async def _run() -> str:
        async with SessionLocal() as session:

            return await mint(session, args.org_slug, args.drone_slug, args.label)

    raw_key = asyncio.run(_run())
    print(raw_key)
    print("Copy this key now. It is never recoverable.", file=sys.stderr)


if __name__ == "__main__":
    main()
