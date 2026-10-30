"""Shared pytest fixtures/config for backend.tests.

Sets defaults for env vars that backend.api.auth reads at import time, so
the test suite doesn't require real Auth0/session credentials to run.
setdefault() means real exported values (e.g. in CI) still win.
"""

import os

import pytest

os.environ.setdefault("AUTH0_DOMAIN", "test.auth0.local")
os.environ.setdefault("AUTH0_AUDIENCE", "test-audience")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-not-for-production")


@pytest.fixture(autouse=True)
def _update_lock_without_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """The heavy flows take the update lock (backend.helpers.run_lock) on a database connection of
    their own; in tests it's always free and needs no database. run_lock_test replaces this."""
    from unittest.mock import MagicMock

    from backend.helpers import run_lock

    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    monkeypatch.setattr(run_lock, "get_database_connection", lambda: conn)
