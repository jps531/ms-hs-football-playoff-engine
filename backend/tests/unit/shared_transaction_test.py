"""Unit tests for database_helpers.shared_transaction: every step on one connection, committed once."""

import threading
from unittest.mock import MagicMock

import pytest

from backend.helpers import database_helpers as db


@pytest.fixture
def real_conn(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The connection shared_transaction opens (and, outside it, any other)."""
    conn = MagicMock()
    monkeypatch.setattr(db, "get_conn", lambda *a: conn)
    return conn


def test_every_step_on_any_thread_shares_one_connection_committed_once(real_conn: MagicMock) -> None:
    seen = []
    with db.shared_transaction():
        with db.get_database_connection() as conn:
            conn.cursor().execute("INSERT 1")
            conn.commit()  # a step's own commit waits for the end
            conn.close()
        worker = threading.Thread(target=lambda: seen.append(db.get_database_connection()))
        worker.start()
        worker.join()
        real_conn.commit.assert_not_called()
    assert seen[0]._conn is real_conn  # a task's thread gets the same connection
    real_conn.cursor.return_value.execute.assert_called_once_with("INSERT 1")
    real_conn.commit.assert_called_once()
    real_conn.rollback.assert_not_called()
    real_conn.close.assert_called_once()


def test_a_failure_rolls_everything_back(real_conn: MagicMock) -> None:
    with pytest.raises(RuntimeError), db.shared_transaction():
        db.get_database_connection().cursor().execute("INSERT 1")
        raise RuntimeError("a later step failed")
    real_conn.commit.assert_not_called()
    real_conn.rollback.assert_called_once()
    real_conn.close.assert_called_once()


def test_a_step_cannot_roll_back_part_of_the_update(real_conn: MagicMock) -> None:
    """Rolling back would undo the earlier steps and let the rest commit: it fails the run instead."""
    with pytest.raises(RuntimeError, match="roll back"), db.shared_transaction():
        db.get_database_connection().rollback()
    real_conn.commit.assert_not_called()
    real_conn.rollback.assert_called_once()  # the whole transaction's, on the way out


def test_outside_a_shared_transaction_connections_are_separate(real_conn: MagicMock) -> None:
    assert db.get_database_connection() is real_conn
    with db.shared_transaction():
        pass
    assert db.get_database_connection() is real_conn


def test_one_shared_transaction_at_a_time(real_conn: MagicMock) -> None:
    with db.shared_transaction(), pytest.raises(RuntimeError, match="already open"), db.shared_transaction():
        pass
