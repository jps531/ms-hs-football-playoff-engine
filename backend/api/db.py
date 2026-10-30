"""Async database connection pool for the playoff engine API.

Uses psycopg v3 AsyncConnectionPool.  The pool is opened once on application
startup (via the FastAPI lifespan) and closed on shutdown.  Routers acquire
connections via the ``get_conn`` dependency.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

_DB_HOST = os.getenv("POSTGRES_HOST", "db")
_DB_PORT = os.getenv("POSTGRES_PORT", "5432")
_DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
_DB_USER = os.getenv("POSTGRES_USER", "postgres")
_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# A write that waits more than this for a row lock gives up (the daily update holds the season's
# game rows for its whole run, in one transaction); main.py answers it with a 503.
LOCK_TIMEOUT_MS = 5000

# make_conninfo quotes each value, so a password with a space or quote still works.
_conninfo = make_conninfo(
    host=_DB_HOST,
    port=_DB_PORT,
    dbname=_DB_NAME,
    user=_DB_USER,
    password=_DB_PASSWORD,
    options=f"-c lock_timeout={LOCK_TIMEOUT_MS}",
)

pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    """Open the async connection pool.  Called once at application startup."""
    global pool
    pool = AsyncConnectionPool(conninfo=_conninfo, min_size=2, max_size=10, open=False)
    await pool.open()


async def close_pool() -> None:
    """Close the async connection pool.  Called once at application shutdown."""
    if pool is not None:
        await pool.close()


@asynccontextmanager
async def get_conn() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """Yield an async psycopg connection from the pool.

    Usage in a route::

        async with get_conn() as conn:
            await conn.execute(...)
    """
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    async with pool.connection() as conn:
        yield conn
