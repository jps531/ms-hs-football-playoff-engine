"""Unit tests for backend.helpers.api_helpers.resolve_standings_snapshot.

``resolve_standings_snapshot`` picks between three data paths depending on
what's been pre-computed by the pipeline (see its docstring). The loader
functions it calls (`_load_standings_snapshot`, `load_scenarios_snapshot`,
`load_completed_region_games`, `load_scenario_atoms`,
`recompute_scenarios_from_games`) all require a live DB connection and are
tested elsewhere / via integration tests; here they're mocked so the branch
selection and data-shaping logic itself gets direct coverage.
"""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

from backend.helpers.api_helpers import resolve_standings_snapshot
from backend.helpers.data_classes import CompletedGame, RemainingGame, StandingsOdds

_CONN = object()  # never touched directly; all DB-facing helpers are mocked


def _standings_row(school: str, as_of_date: date = date(2025, 10, 1)) -> tuple:
    """A 39-column region_standings row (see resolve_standings_snapshot's row-position docstring)."""
    return (
        school, 5, 2, 0, 3, 1, 0,  # 0-6: school, wins, losses, ties, region_wins/losses/ties
        0.4, 0.3, 0.2, 0.1, 0.7,  # 7-11: odds_1st-odds_playoffs
        False, False, False,  # 12-14: clinched, eliminated, coin_flip_needed
        as_of_date,  # 15
        0.4, 0.3, 0.2, 0.1, 0.7,  # 16-20: weighted seeding odds
        *([0.0] * 10),  # 21-30: bracket advancement (unweighted + weighted)
        *([0.0] * 8),  # 31-38: home-game odds (unweighted + weighted)
    )


def _completed() -> list[CompletedGame]:
    """A single completed Alpha-vs-Beta game, for tests that don't care about its details."""
    return [CompletedGame(a="Alpha", b="Beta", res_a=1, pd_a=7, pa_a=14, pa_b=21)]


class TestResolveStandingsSnapshotStoredWithScenarios:
    """Path 1: a stored region_standings snapshot with a matching region_scenarios row."""

    @patch("backend.helpers.api_helpers.load_scenario_atoms", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_completed_region_games", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_scenarios_snapshot", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers._load_standings_snapshot", new_callable=AsyncMock)
    def test_uses_stored_snapshot_and_scenarios(self, mock_load_standings, mock_load_scenarios, mock_completed, mock_atoms):
        """A stored snapshot plus a stored scenarios row is used as-is, with no on-demand recompute."""
        rows = [_standings_row("Alpha"), _standings_row("Beta")]
        mock_load_standings.return_value = rows
        mock_load_scenarios.return_value = ([RemainingGame(a="Alpha", b="Beta")], [{"scenario_num": 1}], [], date(2025, 10, 1))
        mock_completed.return_value = _completed()

        result = asyncio.run(
            resolve_standings_snapshot(_CONN, 2025, 5, 2, date(2025, 10, 3), include_team_scenarios=False)
        )

        assert result.teams == ["Alpha", "Beta"]
        assert result.completed == _completed()
        assert result.snapshot_date == date(2025, 10, 1)
        assert result.complete_scenarios == [{"scenario_num": 1}]
        assert result.remaining == [RemainingGame(a="Alpha", b="Beta")]
        assert set(result.odds_for_order) == {"Alpha", "Beta"}
        # include_team_scenarios=False means scenario_atoms is never fetched.
        mock_atoms.assert_not_awaited()
        assert result.scenario_atoms is None

    @patch("backend.helpers.api_helpers.load_scenario_atoms", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_completed_region_games", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_scenarios_snapshot", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers._load_standings_snapshot", new_callable=AsyncMock)
    def test_include_team_scenarios_fetches_atoms(self, mock_load_standings, mock_load_scenarios, mock_completed, mock_atoms):
        """include_team_scenarios=True triggers a scenario_atoms fetch, populating result.scenario_atoms."""
        mock_load_standings.return_value = [_standings_row("Alpha")]
        mock_load_scenarios.return_value = ([], [], [], date(2025, 10, 1))
        mock_completed.return_value = []
        mock_atoms.return_value = {"Alpha": {"1": [[]]}}

        result = asyncio.run(
            resolve_standings_snapshot(_CONN, 2025, 5, 2, date(2025, 10, 3), include_team_scenarios=True)
        )

        mock_atoms.assert_awaited_once_with(_CONN, 2025, 5, 2, date(2025, 10, 3))
        assert result.scenario_atoms == {"Alpha": {"1": [[]]}}


class TestResolveStandingsSnapshotStoredWithoutScenarios:
    """Path 2: a stored region_standings snapshot, but no region_scenarios row yet."""

    @patch("backend.helpers.api_helpers.recompute_scenarios_from_games", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_completed_region_games", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_scenarios_snapshot", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers._load_standings_snapshot", new_callable=AsyncMock)
    def test_recomputes_only_remaining_games(self, mock_load_standings, mock_load_scenarios, mock_completed, mock_recompute):
        """No stored scenarios row falls back to recomputing just the remaining-games list."""
        rows = [_standings_row("Alpha", as_of_date=date(2025, 9, 28))]
        mock_load_standings.return_value = rows
        mock_load_scenarios.return_value = None  # no region_scenarios row yet
        mock_completed.return_value = []
        mock_recompute.return_value = (
            ["Alpha"],
            [],
            [RemainingGame(a="Alpha", b="Gamma")],
            {},
            set(),
        )

        result = asyncio.run(
            resolve_standings_snapshot(_CONN, 2025, 5, 2, date(2025, 10, 3), include_team_scenarios=False)
        )

        # snapshot_date comes from the stored row (index 15), not `as_of`.
        assert result.snapshot_date == date(2025, 9, 28)
        assert result.complete_scenarios is None
        assert result.key_insights is None
        assert result.remaining == [RemainingGame(a="Alpha", b="Gamma")]
        assert result.teams == ["Alpha"]


class TestResolveStandingsSnapshotFullRecompute:
    """Path 3: no stored region_standings snapshot at all — recompute everything on demand."""

    @patch("backend.helpers.api_helpers.recompute_scenarios_from_games", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers.load_scenarios_snapshot", new_callable=AsyncMock)
    @patch("backend.helpers.api_helpers._load_standings_snapshot", new_callable=AsyncMock)
    def test_recomputes_standings_and_scenarios(self, mock_load_standings, mock_load_scenarios, mock_recompute):
        """No stored snapshot at all recomputes both standings and scenarios entirely on demand."""
        mock_load_standings.return_value = None
        mock_load_scenarios.return_value = None  # unreachable in this branch, but always called
        odds_map = {
            "Alpha": StandingsOdds(
                school="Alpha",
                p1=0.5,
                p2=0.3,
                p3=0.1,
                p4=0.1,
                p_playoffs=0.9,
                final_playoffs=0.9,
                clinched=False,
                eliminated=False,
            )
        }
        mock_recompute.return_value = (
            ["Alpha"],
            _completed(),
            [RemainingGame(a="Alpha", b="Beta")],
            odds_map,
            {"Alpha"},  # coinflip_teams
        )

        as_of = date(2025, 10, 3)
        result = asyncio.run(resolve_standings_snapshot(_CONN, 2025, 5, 2, as_of, include_team_scenarios=False))

        assert result.snapshot_date == as_of
        assert result.complete_scenarios is None
        assert result.key_insights is None
        assert result.odds_for_order == odds_map
        assert result.teams == ["Alpha"]
        assert len(result.team_entries) == 1
        assert result.team_entries[0].school == "Alpha"
