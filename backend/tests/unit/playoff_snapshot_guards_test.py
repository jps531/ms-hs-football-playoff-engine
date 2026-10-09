"""Regular-season flows must leave classes in the playoffs to the playoff bracket update.

``region_standings`` overwrites on (school, season, as_of_date), and the
newest row is what readers see. The daily flow and the historical backfill
compute every snapshot as if no playoff game had been played, so once a
class's playoffs start they would either overwrite the playoff-aware rows on
playoff dates (backfill) or write a newer row that shadows them (a daily or
late manual run). These tests run the flows' bodies with every database and
engine call mocked, recording which regions get written for which dates and
when the playoff update runs.
"""

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.prefect import region_scenarios_pipeline as pipeline
from backend.prefect.region_scenarios_pipeline import classes_in_playoffs

ALL_REGIONS = [(c, r) for c in range(1, 8) for r in (range(1, 9) if c <= 4 else range(1, 5))]


class TestClassesInPlayoffs:
    """The pure cutoff rule."""

    def test_class_is_in_playoffs_from_its_first_playoff_game_on(self):
        """A class counts from the date of its first completed playoff game, inclusive."""
        starts = {3: date(2025, 11, 7)}
        assert classes_in_playoffs(starts, date(2025, 11, 6)) == set()
        assert classes_in_playoffs(starts, date(2025, 11, 7)) == {3}
        assert classes_in_playoffs(starts, date(2026, 6, 24)) == {3}

    def test_offset_playoff_schedules_are_per_class(self):
        """1A-4A start a week before 5A-7A, so a date can catch one group and not the other."""
        starts = {c: date(2025, 11, 7) for c in (1, 2, 3, 4)} | {c: date(2025, 11, 14) for c in (5, 6, 7)}
        assert classes_in_playoffs(starts, date(2025, 11, 10)) == {1, 2, 3, 4}

    def test_no_playoff_games_means_no_classes(self):
        """Before any playoff game is final, every class is still regular season."""
        assert classes_in_playoffs({}, date(2025, 10, 31)) == set()


class _FakeDate(date):
    """``date`` with a pinned ``today()`` so the flow's run date is deterministic."""

    pinned = date(2025, 11, 10)

    @classmethod
    def today(cls):
        """Return the pinned run date."""
        return cls.pinned


@pytest.fixture
def flow_env(monkeypatch):
    """Mock every DB/engine call the two flows make, recording region writes and playoff updates."""
    events: list[tuple] = []

    def finish(c, r, season, seeding, matchup_fn, as_of_date=None):
        events.append(("write", c, r, as_of_date))

    elo_snapshots = [(date(2025, 10, 31), {}), (date(2025, 11, 7), {}), (date(2025, 11, 14), {})]
    stubs = {
        "get_run_logger": lambda: logging.getLogger("test"),
        "fetch_all_season_games": MagicMock(return_value=[]),
        "fetch_all_season_schools": MagicMock(return_value=[]),
        "fetch_prior_season_elo": MagicMock(return_value={}),
        "compute_elo_ratings": MagicMock(return_value=({}, {}, elo_snapshots)),
        "compute_rpi": MagicMock(return_value={}),
        "write_team_ratings": MagicMock(),
        "write_elo_game_date_snapshots": MagicMock(return_value=0),
        "initial_elo_ratings": MagicMock(return_value={}),
        "write_pregame_probabilities": MagicMock(return_value=0),
        "get_region_seeding_odds": MagicMock(return_value=SimpleNamespace(odds_weighted={})),
        "make_matchup_prob_fn": MagicMock(return_value=None),
        "get_region_finish_scenarios": finish,
        "run_playoff_bracket_update": lambda season: events.append(("playoff_update", season)),
        "date": _FakeDate,
    }
    for name, value in stubs.items():
        monkeypatch.setattr(pipeline, name, value)

    def set_playoff_starts(starts):
        monkeypatch.setattr(pipeline, "fetch_playoff_start_dates", MagicMock(return_value=starts))

    set_playoff_starts({})
    return SimpleNamespace(events=events, set_playoff_starts=set_playoff_starts)


def _written(events):
    """(class, region, as_of_date) for every region_standings write, in order."""
    return [e[1:] for e in events if e[0] == "write"]


class TestDailyFlow:
    """region_scenarios_data_flow."""

    def test_regular_season_writes_every_region_and_skips_the_playoff_update(self, flow_env):
        """With no playoff games final, all 44 regions are computed and nothing is handed off."""
        pipeline.region_scenarios_data_flow.fn(season=2025)
        assert sorted((c, r) for c, r, _ in _written(flow_env.events)) == ALL_REGIONS
        assert ("playoff_update", 2025) not in flow_env.events

    def test_classes_in_the_playoffs_are_left_to_the_playoff_update(self, flow_env):
        """1A-4A in the playoffs: only 5A-7A are written, then the playoff update runs last."""
        flow_env.set_playoff_starts({c: date(2025, 11, 7) for c in (1, 2, 3, 4)})
        pipeline.region_scenarios_data_flow.fn(season=2025)
        assert {c for c, _, _ in _written(flow_env.events)} == {5, 6, 7}
        assert flow_env.events[-1] == ("playoff_update", 2025)

    def test_a_late_run_for_a_finished_season_writes_no_regular_season_rows(self, flow_env):
        """The June 24 case: every class's playoffs are over, so nothing stale is written."""
        _FakeDate.pinned = date(2026, 6, 24)
        try:
            flow_env.set_playoff_starts({c: date(2025, 11, 7) for c in range(1, 8)})
            pipeline.region_scenarios_data_flow.fn(season=2025)
        finally:
            _FakeDate.pinned = date(2025, 11, 10)
        assert _written(flow_env.events) == []
        assert flow_env.events == [("playoff_update", 2025)]

    def test_single_region_run_for_a_class_in_the_playoffs_is_handed_off(self, flow_env):
        """A one-region manual run respects the same rule."""
        flow_env.set_playoff_starts({3: date(2025, 11, 7)})
        pipeline.region_scenarios_data_flow.fn(season=2025, clazz=3, region=6)
        assert _written(flow_env.events) == []
        assert flow_env.events == [("playoff_update", 2025)]


class TestBackfill:
    """backfill_historical_snapshots."""

    def test_playoff_dates_are_left_to_the_playoff_update_which_runs_last(self, flow_env):
        """Each class is backfilled only before its first playoff game; the playoff update runs after every write."""
        flow_env.set_playoff_starts(
            {c: date(2025, 11, 7) for c in (1, 2, 3, 4)} | {c: date(2025, 11, 14) for c in (5, 6, 7)}
        )
        pipeline.backfill_historical_snapshots.fn(season=2025)

        written = _written(flow_env.events)
        by_date: dict[date, set[int]] = {}
        for c, _, d in written:
            by_date.setdefault(d, set()).add(c)
        assert by_date == {
            date(2025, 10, 31): {1, 2, 3, 4, 5, 6, 7},  # regular season for everyone
            date(2025, 11, 7): {5, 6, 7},  # 1A-4A playoffs began
            # Nov 14: every class is in the playoffs, so nothing is written
        }
        assert flow_env.events[-1] == ("playoff_update", 2025)

    def test_season_without_playoff_games_backfills_every_date_and_skips_the_update(self, flow_env):
        """No playoff games final yet: the backfill behaves as before."""
        pipeline.backfill_historical_snapshots.fn(season=2025)
        dates = {d for _, _, d in _written(flow_env.events)}
        assert dates == {date(2025, 10, 31), date(2025, 11, 7), date(2025, 11, 14)}
        assert ("playoff_update", 2025) not in flow_env.events
