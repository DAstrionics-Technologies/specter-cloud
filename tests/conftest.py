import os

os.environ["DATABASE_URL"] = "postgresql://specter:specter@localhost:5432/specter"
os.environ["REDIS_URL"] = "redis://localhost:6379"

import pytest
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from app.auth.api_key import generate_api_key
from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app
from app.models import Drone, DroneApiKey, Org


# --- Test engine: NullPool means no connection reuse across event loops ---
test_engine = create_async_engine(
    os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1),
    poolclass=NullPool,
)


# --- Fake Redis ---
class FakeRedis:
    """Stand-in for redis.asyncio client. Stores nothing, publishes nothing."""

    async def set(self, *args, **kwargs):
        return True

    async def get(self, *args, **kwargs):
        return None

    async def publish(self, *args, **kwargs):
        return 0

    async def close(self):
        pass


# --- Override lifespan so tests don't connect to real Redis ---
@asynccontextmanager
async def test_lifespan(app):
    yield


app.router.lifespan_context = test_lifespan


# --- Fixtures ---


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session():
    async with test_engine.connect() as conn:
        async with test_engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            yield session
            await trans.rollback()
            await session.close()


@pytest.fixture
async def db_client(db_session):
    fake_redis = FakeRedis()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: fake_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def authed_drone(db_session):
    # Seeds Org + Drone + DroneApiKey and returns (drone, raw_key).
    # verify_api_key commits during auth; the outer fixture's savepoint
    # rollback still cleans up because join_transaction_mode="create_savepoint".
    org = Org(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.flush()

    drone = Drone(name="Test Drone", slug="test-drone", org_id=org.id)
    db_session.add(drone)
    await db_session.flush()

    raw_key, prefix, hashed_key = generate_api_key()
    api_key = DroneApiKey(
        drone_id=drone.id, prefix=prefix, hashed_key=hashed_key, label="test"
    )
    db_session.add(api_key)
    await db_session.flush()

    return drone, raw_key
