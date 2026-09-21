"""Every test starts from the same known world.

The suite used to run against whatever database `DATABASE_URL` pointed at, and
took for granted that someone had seeded a rate card into it. That made failures
lie: a test would go red because an earlier run had published a card with
different numbers, not because anything was broken.

So the suite owns its database. `DATABASE_URL` still says which server, but the
tests run in a `<name>_test` database beside it, created here, migrated here, and
emptied and reseeded before every single test. Nothing a test does survives into
the next one, and running `pytest` twice gives the same answer as running it once.

It needs a real Postgres -- the migrations use jsonb and array types that SQLite
has no answer for -- which is the same Postgres the app is developed against.
"""

import os
import subprocess

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from psycopg import sql

os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "local")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_URL = "postgresql+asyncpg://proline:proline@localhost:5432/proline"


def _test_database_url() -> str:
    """The developer's database name with `_test` on the end.

    Pointing the suite at the development database itself would be a footgun with
    a loaded chamber: the fixtures below truncate every table.
    """
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    base, _, name = url.rpartition("/")
    name = name.split("?")[0]
    return f"{base}/{name}_test" if not name.endswith("_test") else url


TEST_URL = _test_database_url()
# Set before anything imports app.core.config, which caches the settings object.
os.environ["DATABASE_URL"] = TEST_URL

# psycopg speaks plain libpq; the app speaks asyncpg through SQLAlchemy.
SYNC_URL = TEST_URL.replace("postgresql+asyncpg://", "postgresql://")
ADMIN_URL, _, TEST_DB = SYNC_URL.rpartition("/")


def _create_database() -> None:
    with psycopg.connect(f"{ADMIN_URL}/postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))


def _migrate() -> None:
    """Rebuild from nothing, so the schema under test is the one the migrations
    produce -- not the one `Base.metadata.create_all` would have produced, which
    is how a broken migration reaches production green."""
    with psycopg.connect(SYNC_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    done = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, cwd=BACKEND_DIR,
        env=dict(os.environ, DATABASE_URL=TEST_URL),
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.fixture(scope="session", autouse=True)
def database() -> str:
    try:
        _create_database()
    except psycopg.OperationalError as error:  # pragma: no cover - environment
        pytest.exit(
            f"the test suite needs Postgres at {ADMIN_URL}: {error}\n"
            "Start it, or point DATABASE_URL at a server you can reach.",
            returncode=1,
        )
    _migrate()
    return TEST_URL


# Every table, children first, so a truncate cascade is not needed.
TABLES = ("quote_photos", "quotes", "quote_requests", "properties", "leads", "rate_cards")


@pytest.fixture(autouse=True)
def clean_database(database: str):
    """Empty and reseed before each test.

    Before, not after: a failing test leaves its rows behind for inspection, and
    the next test still starts clean.
    """
    import json
    from datetime import date

    from scripts.seed_rate_card import GRID, VERSION

    with psycopg.connect(SYNC_URL, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        conn.execute(
            """INSERT INTO rate_cards (id, version, effective_from, is_active,
                                       hourly_rate_cents, minimum_visit_cents,
                                       travel_cents, grid, residential_online_pricing)
               VALUES (gen_random_uuid(), %s, %s, true, 4500, 12000, 1500, %s, true)""",
            (VERSION, date.today(), json.dumps(GRID)),
        )
    yield


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
