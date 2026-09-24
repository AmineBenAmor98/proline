"""The connection string a managed host hands us is not the one asyncpg opens.

These are the literal shapes the providers emit, kept as strings rather than
built from parts, because the point of the test is that a real DigitalOcean
binding survives contact with `create_async_engine` -- and the failure this
guards is a TypeError on the first visitor's request, long after the health
check went green.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, normalise_database_url

DO_DIRECT = (
    "postgresql://doadmin:secret@db-postgresql-tor1-1-do-user-1.k.db"
    ".ondigitalocean.com:25060/defaultdb?sslmode=require"
)
DO_POOLED = (
    "postgresql://doadmin:secret@db-postgresql-tor1-1-do-user-1.k.db"
    ".ondigitalocean.com:25061/proline-pool?sslmode=require"
)
SUPABASE = "postgres://postgres:secret@db.abcdefgh.supabase.co:5432/postgres"
LOCAL = "postgresql+asyncpg://proline:proline@localhost:5432/proline"


@pytest.mark.parametrize("url", [DO_DIRECT, DO_POOLED, SUPABASE])
def test_provider_urls_become_asyncpg(url: str) -> None:
    fixed = normalise_database_url(url)
    assert fixed.startswith("postgresql+asyncpg://")
    assert "sslmode=" not in fixed


@pytest.mark.parametrize("url", [DO_DIRECT, DO_POOLED, SUPABASE, LOCAL])
def test_engine_opens_and_asyncpg_gets_only_arguments_it_takes(url: str) -> None:
    """`create_connect_args` is where a stray `sslmode` would survive to become
    a TypeError inside asyncpg.connect(). Asserting on the keyword names is the
    whole test: the engine is never connected."""
    engine = create_async_engine(normalise_database_url(url))
    assert engine.dialect.driver == "asyncpg"
    _, params = engine.dialect.create_connect_args(engine.url)
    assert "sslmode" not in params


def test_sslmode_maps_to_the_asyncpg_spelling() -> None:
    assert "ssl=require" in normalise_database_url(DO_DIRECT)
    # verify-ca has no asyncpg equivalent; verify-full is the nearest that does
    # not silently weaken what was asked for.
    assert "ssl=verify-full" in normalise_database_url(
        "postgresql://u:p@h:5432/d?sslmode=verify-ca"
    )


def test_an_explicit_ssl_argument_wins() -> None:
    """Someone who wrote `ssl=` meant it; sslmode does not overwrite it."""
    fixed = normalise_database_url("postgresql://u:p@h:5432/d?ssl=disable&sslmode=require")
    assert "ssl=disable" in fixed
    assert "sslmode" not in fixed


def test_other_query_parameters_survive() -> None:
    """A transaction-mode pooler needs statement_cache_size=0; losing it here
    would turn prepared statements into intermittent errors under load."""
    fixed = normalise_database_url(f"{DO_POOLED}&statement_cache_size=0")
    assert "statement_cache_size=0" in fixed


def test_a_url_that_is_already_right_is_left_alone() -> None:
    assert normalise_database_url(LOCAL) == LOCAL


def test_settings_normalise_on_load() -> None:
    """Alembic and the app both read this setting, so the fix has to live on the
    field rather than at either call site."""
    assert Settings(database_url=DO_DIRECT).database_url.startswith(
        "postgresql+asyncpg://"
    )
