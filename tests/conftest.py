import os

os.environ["DATABASE_URL"] = "postgresql://specter:specter@localhost:5432/specter"
os.environ["REDIS_URL"] = "redis://localhost:6379"

import pytest
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app


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
            session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
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
