"""Unit tests for backend.helpers.run_lock: one heavy update at a time, subflows included."""

from unittest.mock import MagicMock

import pytest

from backend.helpers import run_lock


def _conn(free: bool = True) -> MagicMock:
    """A connection whose try-lock answers *free*."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (free,)
    return conn


def _sql(conn: MagicMock) -> list[str]:
    """The statements run on *conn*, in order."""
    return [c.args[0] for c in conn.cursor.return_value.__enter__.return_value.execute.call_args_list]


def test_waits_for_the_lock_then_releases_it_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn()
    monkeypatch.setattr(run_lock, "_lock_connection", lambda: conn)
    with run_lock.exclusive_run() as held:
        assert held
    assert _sql(conn) == ["SELECT pg_advisory_lock(%s)", "SELECT pg_advisory_unlock(%s)"]
    assert conn.autocommit is True
    conn.close.assert_called_once()


def test_without_waiting_a_busy_lock_is_reported_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn(free=False)
    monkeypatch.setattr(run_lock, "_lock_connection", lambda: conn)
    with run_lock.exclusive_run(wait=False) as held:
        assert not held
    assert _sql(conn) == ["SELECT pg_try_advisory_lock(%s)"]
    conn.close.assert_called_once()


def test_a_subflow_of_the_holder_goes_straight_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily update holds the lock and runs the region update, which takes it again."""
    conns = [_conn()]
    monkeypatch.setattr(run_lock, "_lock_connection", lambda: conns[-1])
    with run_lock.exclusive_run() as outer:
        with run_lock.exclusive_run(wait=False) as inner:
            assert outer and inner
    assert len(_sql(conns[0])) == 2  # one lock, one unlock: the inner one used no connection
    with run_lock.exclusive_run():  # and it's free again afterwards
        pass


def test_the_lock_is_released_when_the_flow_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn()
    monkeypatch.setattr(run_lock, "_lock_connection", lambda: conn)

    @run_lock.holds_update_lock
    def flow_body(season: int) -> None:
        """A flow that fails partway."""
        raise RuntimeError(season)

    with pytest.raises(RuntimeError):
        flow_body(2026)
    assert _sql(conn)[-1] == "SELECT pg_advisory_unlock(%s)"
    conn.close.assert_called_once()
