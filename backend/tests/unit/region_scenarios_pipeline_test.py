"""Unit tests for backend/prefect/region_scenarios_pipeline.py's pure helpers.

Only ``compute_pregame_prob_rows`` is tested here — it's pure Python (no DB,
no Prefect task wrapper), extracted specifically so this leakage-avoidance
logic can be verified without mocking a database connection.
"""

from datetime import date

import pytest

from backend.helpers.data_classes import Game, GameStatus
from backend.helpers.win_probability import EloConfig, compute_pregame_win_prob
from backend.prefect.region_scenarios_pipeline import compute_pregame_prob_rows

_CFG = EloConfig()


def _game(
    school: str,
    opponent: str,
    game_date: date,
    location: str = "home",
    final: bool = True,
    result: str | None = "W",
    pf: int | None = 21,
    pa: int | None = 14,
) -> Game:
    """Build a minimal final (or in-progress) ``Game`` for a given school/opponent/date."""
    return Game(
        school=school,
        date=game_date,
        season=2025,
        location_id=None,
        points_for=pf,
        points_against=pa,
        round=None,
        kickoff_time=None,
        opponent=opponent,
        result=result,
        game_status=GameStatus.FINAL if final else None,
        source=None,
        location=location,
        region_game=True,
        final=final,
        overtime=0,
    )


class TestComputePregameProbRows:
    """compute_pregame_prob_rows: which games get pregame_prob rows, and from what rating."""

    def test_first_game_of_season_uses_initial_ratings(self):
        """A team's first game (no prior snapshot exists) uses initial_ratings."""
        d1 = date(2025, 8, 22)
        games = [_game("Alpha", "Beta", d1, location="home")]
        initial = {"Alpha": 1200.0, "Beta": 1000.0}
        rows = compute_pregame_prob_rows(games, elo_snapshots=[], initial_ratings=initial, elo_cfg=_CFG)

        expected = compute_pregame_win_prob(1200.0, 1000.0, "home", _CFG)
        by_school = {school: prob for school, _date, prob in rows}
        assert by_school["Alpha"] == pytest.approx(expected)
        assert by_school["Beta"] == pytest.approx(1.0 - expected)

    def test_second_game_uses_prior_snapshot_not_own_date(self):
        """A game's pregame_prob must use the snapshot strictly BEFORE its own date.

        elo_snapshots contains a snapshot dated the same as the second game
        (post that game's own result) and an earlier one from the team's
        first game. Using the same-date snapshot would leak the second
        game's own outcome into its own pregame probability — this is
        exactly the bug the strictly-before lookup avoids.
        """
        d1, d2 = date(2025, 8, 22), date(2025, 8, 29)
        games = [_game("Alpha", "Gamma", d2, location="away")]
        initial = {"Alpha": 1000.0, "Gamma": 1000.0}
        elo_snapshots = [
            (d1, {"Alpha": 1150.0, "Gamma": 1000.0}, {"Alpha": 1, "Gamma": 0}),  # after Alpha's 1st game
            (d2, {"Alpha": 1300.0, "Gamma": 850.0}, {"Alpha": 2, "Gamma": 1}),  # after THIS game — must not be used
        ]
        rows = compute_pregame_prob_rows(games, elo_snapshots, initial_ratings=initial, elo_cfg=_CFG)

        # Correct: uses d1's snapshot (Alpha=1150.0) — not d2's (Alpha=1300.0, which
        # already reflects this very game's result).
        expected = compute_pregame_win_prob(1150.0, 1000.0, "away", _CFG)
        by_school = {school: prob for school, _date, prob in rows}
        assert by_school["Alpha"] == pytest.approx(expected)

    def test_dedup_produces_exactly_two_rows_per_contest(self):
        """Both mirror rows of the same contest collapse to one computation, two output rows."""
        d1 = date(2025, 9, 5)
        games = [
            _game("Alpha", "Beta", d1, location="home", pf=21, pa=14),
            _game("Beta", "Alpha", d1, location="away", pf=14, pa=21),
        ]
        initial = {"Alpha": 1200.0, "Beta": 1000.0}
        rows = compute_pregame_prob_rows(games, elo_snapshots=[], initial_ratings=initial, elo_cfg=_CFG)
        assert len(rows) == 2
        schools = {school for school, _date, _prob in rows}
        assert schools == {"Alpha", "Beta"}

    def test_non_final_game_excluded(self):
        """A not-yet-played game produces no rows."""
        rows = compute_pregame_prob_rows(
            [_game("Alpha", "Beta", date(2025, 9, 5), final=False, result=None, pf=None, pa=None)],
            elo_snapshots=[],
            initial_ratings={"Alpha": 1200.0, "Beta": 1000.0},
            elo_cfg=_CFG,
        )
        assert rows == []

    def test_unrated_team_excluded(self):
        """A contest where either team is unrated (not in any snapshot) produces no rows."""
        rows = compute_pregame_prob_rows(
            [_game("Alpha", "Unknown", date(2025, 9, 5))],
            elo_snapshots=[],
            initial_ratings={"Alpha": 1200.0},  # "Unknown" absent
            elo_cfg=_CFG,
        )
        assert rows == []

    def test_probabilities_are_complementary(self):
        """The two mirror rows for a contest always sum to 1.0."""
        rows = compute_pregame_prob_rows(
            [_game("Alpha", "Beta", date(2025, 9, 5), location="neutral")],
            elo_snapshots=[],
            initial_ratings={"Alpha": 1300.0, "Beta": 900.0},
            elo_cfg=_CFG,
        )
        probs = [prob for _school, _date, prob in rows]
        assert sum(probs) == pytest.approx(1.0)
