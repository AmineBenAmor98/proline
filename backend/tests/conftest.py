import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "local")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """A client per test, with the connection pool disposed afterwards.

    pytest-asyncio gives each test its own event loop; asyncpg connections are
    bound to the loop that opened them, so a pool that survives the test raises
    'Event loop is closed' in the next one.
    """
    from app.db.session import engine
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/admin/login",
        json={"username": os.environ["ADMIN_USERNAME"], "password": os.environ["ADMIN_PASSWORD"]},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}
