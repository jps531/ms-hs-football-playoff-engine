"""Database connection helpers.

Provides a psycopg2 connection factory used by scripts and pipelines.
Connection parameters are read from environment variables with sensible
Docker-compose defaults.
"""

import os
import threading
from contextlib import contextmanager

import psycopg2

# --- DATABASE CONFIG ---
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "mshsfootball")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")


def get_conn(db_host: str, db_port: int, db_name: str, db_user: str, db_password: str):
    """Open and return a psycopg2 connection to the specified PostgreSQL database.

    Args:
        db_host: Hostname or IP of the PostgreSQL server.
        db_port: Port number the server is listening on.
        db_name: Name of the database to connect to.
        db_user: Database user name.
        db_password: Database user password.

    Returns:
        An open psycopg2 connection object.
    """
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )


def get_database_connection():
    """Open a psycopg2 connection using environment-variable configuration.

    Reads ``POSTGRES_HOST``, ``POSTGRES_PORT``, ``POSTGRES_DB``,
    ``POSTGRES_USER``, and ``POSTGRES_PASSWORD`` from the environment,
    falling back to Docker-compose defaults.

    Inside ``shared_transaction``, it's that transaction's connection instead.

    Returns:
        An open psycopg2 connection object.
    """
    if _shared is not None:  # inside shared_transaction: everyone shares its connection
        return _SharedConnection(_shared)
    conn = get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    return conn


# The connection a shared transaction runs on (see shared_transaction), or None.
_shared = None
_shared_guard = threading.Lock()


class _SharedConnection:
    """The shared transaction's connection as one task sees it: everything passes through, except
    that it never commits, closes, or ends the transaction on leaving ``with conn:``. The
    transaction ends once, when ``shared_transaction`` does."""

    def __init__(self, conn):
        """Wrap the transaction's real connection."""
        self._conn = conn

    def __getattr__(self, name):
        """Everything else (cursors, mostly) passes through to the real connection."""
        return getattr(self._conn, name)

    def commit(self) -> None:
        """Committing is the shared transaction's job, at the end."""

    def close(self) -> None:
        """The shared transaction closes the connection when it ends."""

    def rollback(self) -> None:
        """Rolling back would undo every earlier step's work too, and carrying on would then commit
        part of the update; fail instead, which rolls the whole transaction back."""
        raise RuntimeError("A step tried to roll back inside a shared transaction")

    def __enter__(self):
        """``with conn:`` inside the transaction: nothing to start."""
        return self

    def __exit__(self, *exc) -> bool:
        """Leaving ``with conn:`` neither commits nor rolls back; an error still propagates."""
        return False


@contextmanager
def shared_transaction():
    """Run the block's database work as one transaction: all of it is committed at the end, or,
    if the block fails, none of it.

    Inside it, ``get_database_connection`` hands every caller (every task, on any thread) the
    same connection, so each step sees the earlier steps' writes while nothing is visible to
    anyone else until the commit.
    """
    global _shared
    conn = get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    with _shared_guard:
        if _shared is not None:
            conn.close()
            raise RuntimeError("A shared transaction is already open in this process")
        _shared = conn
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        with _shared_guard:
            _shared = None
        conn.close()
