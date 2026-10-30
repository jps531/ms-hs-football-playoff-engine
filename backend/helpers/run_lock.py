"""One heavy update at a time: the flows that write games or the computed snapshots share a lock.

The daily update, the backfill, the region and playoff updates, the schedule pull and the
recompute after corrections each hold it while they run, so none of them reads half of another's
writes or writes over it. It's a Postgres session advisory lock, held on a connection of its own
for the length of the run.

A flow that runs another as a subflow (the daily update runs the schedule pull and the region
update) already holds the lock, so taking it again in the same process just goes through.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

from backend.helpers.database_helpers import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, get_conn

# Any fixed number; Postgres advisory locks are keyed by integers.
LOCK_KEY = 2026_10_30


def _lock_connection():
    """A new connection for the lock's session."""
    return get_conn(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)


P = ParamSpec("P")
R = TypeVar("R")

_depth = 0
_depth_guard = threading.Lock()


@contextmanager
def exclusive_run(wait: bool = True) -> Iterator[bool]:
    """Hold the update lock for the block; yields whether it's held.

    With ``wait`` (the default) it waits for whichever update is running to finish. Without it,
    it yields False at once when another update holds the lock, and the caller skips its work.
    """
    global _depth
    with _depth_guard:
        if _depth:
            _depth += 1
            nested = True
        else:
            nested = False
    if nested:
        try:
            yield True
        finally:
            with _depth_guard:
                _depth -= 1
        return

    # A connection of its own, even inside a shared transaction (database_helpers), closed
    # explicitly: psycopg2's ``with conn`` only ends a transaction, and the lock lasts as long
    # as the connection's session does.
    conn = _lock_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if wait:
                cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
                held = True
            else:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
                held = bool(cur.fetchone()[0])
        if not held:
            yield False
            return
        with _depth_guard:
            _depth = 1
        try:
            yield True
        finally:
            with _depth_guard:
                _depth = 0
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    finally:
        conn.close()


def holds_update_lock(fn: Callable[P, R]) -> Callable[P, R]:
    """Run *fn* (a flow's function, decorated under ``@flow``) holding the update lock, waiting for it."""

    @functools.wraps(fn)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        """Take the lock, then run the flow."""
        with exclusive_run():
            return fn(*args, **kwargs)

    return run
