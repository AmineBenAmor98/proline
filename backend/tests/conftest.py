import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_TOKEN", "test-token")
os.environ.setdefault("ENVIRONMENT", "local")


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
