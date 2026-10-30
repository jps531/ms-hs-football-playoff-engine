"""Unit tests for backend.prefect.recompute_pipeline: approved corrections worked in once they stop coming."""

import logging
from contextlib import contextmanager
from datetime import date, datetime

import pytest

import backend.prefect.recompute_pipeline as recompute

APPROVED = datetime(2026, 10, 30, 11, 28)


@pytest.fixture(autouse=True)
def _quiet_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flow logs through Prefect's run logger, which needs a live run; a plain logger will do."""
    monkeypatch.setattr(recompute, "get_run_logger", lambda: logging.getLogger("test"))


def _run(monkeypatch, waiting, *, lock_free=True, completes=True, unchanged=True):
    """Run the flow's body with its database reads and the flows it runs replaced; return (result, calls)."""
    calls = []

    @contextmanager
    def lock(wait=True):
        calls.append(("lock", wait))
        yield lock_free

    monkeypatch.setattr(recompute, "ready_requests", lambda: waiting)
    monkeypatch.setattr(recompute, "exclusive_run", lock)
    monkeypatch.setattr(
        recompute,
        "backfill_historical_snapshots",
        lambda season, from_date, superseded_after: (
            calls.append(("backfill", season, from_date, superseded_after)) or completes
        ),
    )
    monkeypatch.setattr(recompute, "region_scenarios_data_flow", lambda season: calls.append(("today", season)))
    monkeypatch.setattr(recompute, "finish_request", lambda season, at: calls.append(("finish", season)) or unchanged)
    return recompute.recompute_after_corrections.fn(), calls


def test_nothing_waiting_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls = _run(monkeypatch, [])
    assert result == [] and calls == []


def test_the_current_season_is_recomputed_from_its_date_then_today(monkeypatch: pytest.MonkeyPatch) -> None:
    this_year = date.today().year
    result, calls = _run(monkeypatch, [(this_year, date(this_year, 10, 9), APPROVED)])
    assert calls == [
        ("lock", False),
        ("backfill", this_year, date(this_year, 10, 9), APPROVED),
        ("today", this_year),
        ("finish", this_year),
    ]
    assert result == [f"{this_year}: recomputed from {this_year}-10-09"]


def test_a_past_season_needs_no_today(monkeypatch: pytest.MonkeyPatch) -> None:
    _, calls = _run(monkeypatch, [(2025, date(2025, 10, 30), APPROVED)])
    assert ("today", 2025) not in calls and ("finish", 2025) in calls


def test_a_busy_lock_skips_this_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls = _run(monkeypatch, [(2025, date(2025, 10, 30), APPROVED)], lock_free=False)
    assert result == ["skipped: another update is running"]
    assert calls == [("lock", False)]


def test_a_newer_correction_mid_run_leaves_the_request_to_start_over(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls = _run(monkeypatch, [(2025, date(2025, 10, 30), APPROVED)], completes=False)
    assert result == ["2025: stopped for a newer correction; starts over once they stop"]
    assert not any(c[0] in ("today", "finish") for c in calls)


def test_a_correction_after_the_last_date_keeps_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = _run(monkeypatch, [(2025, date(2025, 10, 30), APPROVED)], unchanged=False)
    assert result == ["2025: recomputed from 2025-10-30; a newer correction runs next"]


def test_only_requests_quiet_for_a_while_are_ready() -> None:
    assert "requested_at <= NOW() - %s" in recompute._READY_SQL
    assert recompute.QUIET.total_seconds() == 600
    assert "AND requested_at = %s" in recompute._DONE_SQL  # a newer approval keeps the row
