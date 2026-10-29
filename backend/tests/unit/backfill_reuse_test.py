"""A backfill reuses a region's results from one date to the next only when what they're worked out from
hasn't changed: its odds when its teams, games and win chances match, its scenarios, team paths and
insights when its games match (and, with five or fewer left, the win chances too)."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.prefect import region_scenarios_pipeline as pipeline
from backend.prefect.region_scenarios_pipeline import Reuse

TEAMS = ["A", "B", "C", "D"]
COMPLETED = [CompletedGame("A", "B", 1, 7, 14, 21), CompletedGame("C", "D", -1, -3, 17, 14)]


def _remaining(n: int) -> list[RemainingGame]:
    """The region's games left: the first *n* of A-C, A-D, B-C, B-D."""
    return [RemainingGame(a, b, "neutral") for a, b in (("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"))[:n]]


def test_reuse_returns_a_result_only_for_the_same_inputs():
    """The region's last result comes back for the same key, and nothing for another key or region."""
    reuse = Reuse()
    reuse.put("odds", 1, 5, ("k",), "result")
    assert reuse.get("odds", 1, 5, ("k",)) == "result"
    assert reuse.get("odds", 1, 5, ("other",)) is None
    assert reuse.get("odds", 1, 6, ("k",)) is None
    assert reuse.get("scenarios", 1, 5, ("k",)) is None
    assert reuse.reused == {"odds": 1, "scenarios": 0}
    assert reuse.worked_out == {"odds": 1, "scenarios": 0}


def test_reuse_keeps_only_each_regions_last_result():
    """A new result replaces the region's last one, so an earlier key no longer matches."""
    reuse = Reuse()
    reuse.put("odds", 1, 5, ("first",), 1)
    reuse.put("odds", 1, 5, ("second",), 2)
    assert reuse.get("odds", 1, 5, ("first",)) is None
    assert reuse.get("odds", 1, 5, ("second",)) == 2


@pytest.fixture
def seeding_env(monkeypatch):
    """get_region_seeding_odds with its database reads stubbed and determine_scenarios counted."""
    games = SimpleNamespace(remaining=_remaining(2))
    monkeypatch.setattr(pipeline, "fetch_region_teams", SimpleNamespace(fn=lambda c, r, s: TEAMS))
    monkeypatch.setattr(pipeline, "fetch_completed_pairs", SimpleNamespace(fn=lambda t, s, cutoff_date: COMPLETED))
    monkeypatch.setattr(
        pipeline, "fetch_remaining_pairs", SimpleNamespace(fn=lambda t, s, cutoff_date: list(games.remaining))
    )
    counted = MagicMock(side_effect=pipeline.determine_scenarios)
    monkeypatch.setattr(pipeline, "determine_scenarios", counted)
    return SimpleNamespace(games=games, calls=counted)


def _odds(reuse, ratings):
    """Phase 1 for region 1-5A with *ratings*."""
    return pipeline.get_region_seeding_odds.fn(5, 1, 2025, elo_ratings=ratings, elo_snapshots=[], reuse=reuse)


RATINGS = {"A": 1600.0, "B": 1500.0, "C": 1450.0, "D": 1400.0}


def test_odds_are_reused_when_teams_games_and_win_chances_match(seeding_env):
    """The same games and ratings: the odds are worked out once and the same result returned."""
    reuse = Reuse()
    first = _odds(reuse, RATINGS)
    assert _odds(reuse, dict(RATINGS)) is first
    assert seeding_env.calls.call_count == 1


def test_odds_are_worked_out_again_when_a_win_chance_changes(seeding_env):
    """A team in a game left has a new rating: its win chance changes, so the odds are worked out again."""
    reuse = Reuse()
    first = _odds(reuse, RATINGS)
    second = _odds(reuse, {**RATINGS, "C": 1500.0})
    assert seeding_env.calls.call_count == 2
    assert second.remaining_win_probs != first.remaining_win_probs


def test_odds_are_worked_out_again_when_a_rating_outside_the_games_left_changes(seeding_env):
    """Only the win chances of the games left count: a rating change for a team with none left reuses."""
    seeding_env.games.remaining = _remaining(1)  # A-C only
    reuse = Reuse()
    first = _odds(reuse, RATINGS)
    assert _odds(reuse, {**RATINGS, "D": 1300.0}) is first
    assert seeding_env.calls.call_count == 1


def test_odds_are_worked_out_again_when_the_games_change(seeding_env):
    """A game played since: the games left differ, so the odds are worked out again."""
    reuse = Reuse()
    _odds(reuse, RATINGS)
    seeding_env.games.remaining = _remaining(1)
    _odds(reuse, RATINGS)
    assert seeding_env.calls.call_count == 2


def test_the_daily_update_never_reuses(seeding_env):
    """Without a Reuse (the daily update), every call works the odds out."""
    _odds(None, RATINGS)
    _odds(None, RATINGS)
    assert seeding_env.calls.call_count == 2


@pytest.fixture
def finish_env(monkeypatch):
    """get_region_finish_scenarios with its reads and writes stubbed and the scenario work counted."""
    written: list = []
    stubs = {
        "get_run_logger": lambda: logging.getLogger("test"),
        "fetch_num_rounds": SimpleNamespace(fn=lambda c, s: 4),
        "fetch_first_round_home_seeds": SimpleNamespace(fn=lambda c, r, s: [1, 2]),
        "fetch_all_format_slots": SimpleNamespace(fn=lambda c, s: []),
        "fetch_region_standings": SimpleNamespace(fn=lambda c, r, s, cutoff_date=None: []),
        "write_region_standings": SimpleNamespace(fn=MagicMock()),
        "write_region_seed_pairs": SimpleNamespace(fn=MagicMock()),
        "write_region_scenarios": SimpleNamespace(fn=lambda *a, **k: written.append(k)),
    }
    for name, value in stubs.items():
        monkeypatch.setattr(pipeline, name, value)
    counted = MagicMock(side_effect=pipeline.enumerate_division_scenarios)
    monkeypatch.setattr(pipeline, "enumerate_division_scenarios", counted)
    return SimpleNamespace(calls=counted, written=written)


def _seeding(remaining, win_probs):
    """Phase 1's result for a region with *remaining* games left at *win_probs*, worked out for real."""
    r = pipeline.determine_scenarios(TEAMS, COMPLETED, remaining, ignore_margins=len(remaining) > 5)
    odds, odds_weighted = pipeline.odds_from_results(TEAMS, r)
    return pipeline.RegionSeedingData(
        odds=odds,
        odds_weighted=odds_weighted,
        coinflip_teams=r.coinflip_teams,
        teams=TEAMS,
        completed=COMPLETED,
        remaining=remaining,
        remaining_win_probs=win_probs,
    )


def _finish(reuse, seeding, day):
    """Phase 2 for region 1-5A on October *day*."""
    from datetime import date

    pipeline.get_region_finish_scenarios.fn(5, 1, 2025, seeding, None, as_of_date=date(2025, 10, day), reuse=reuse)


def test_scenarios_carry_over_while_only_ratings_change_with_six_or_more_left(finish_env):
    """Win/loss scenarios don't depend on the win chances: new ratings reuse them, each date still written."""
    remaining = _remaining(4) + [RemainingGame("A", "B", "neutral"), RemainingGame("C", "D", "neutral")]
    reuse = Reuse()
    _finish(reuse, _seeding(remaining, [0.6] * 6), 3)
    _finish(reuse, _seeding(remaining, [0.7] * 6), 10)
    assert finish_env.calls.call_count == 1
    assert [w["as_of_date"].day for w in finish_env.written] == [3, 10]
    assert finish_env.written[0]["complete_scenarios"] is finish_env.written[1]["complete_scenarios"]


def test_scenarios_are_worked_out_again_when_win_chances_change_with_five_or_fewer_left(finish_env):
    """With five or fewer left each scenario carries its Projected chance, so new win chances mean new work."""
    remaining = _remaining(2)
    reuse = Reuse()
    _finish(reuse, _seeding(remaining, [0.6, 0.6]), 3)
    _finish(reuse, _seeding(remaining, [0.6, 0.6]), 4)
    _finish(reuse, _seeding(remaining, [0.7, 0.6]), 10)
    assert finish_env.calls.call_count == 2
    assert [w["as_of_date"].day for w in finish_env.written] == [3, 4, 10]
