"""While the daily update holds the season's game rows (one transaction), an API write gives up
after a few seconds and is told to try again, rather than hanging or failing with a 500."""

import asyncio
import json

from psycopg.errors import LockNotAvailable

from backend.api import db
from backend.api.main import UPDATE_RUNNING, _update_running


def test_api_connections_stop_waiting_for_row_locks() -> None:
    assert f"lock_timeout={db.LOCK_TIMEOUT_MS}" in db._conninfo
    assert db.LOCK_TIMEOUT_MS == 5000


def test_a_lock_timeout_is_a_503_saying_to_try_again() -> None:
    response = asyncio.run(_update_running(None, LockNotAvailable()))
    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": UPDATE_RUNNING}
    assert response.headers["retry-after"] == "300"
