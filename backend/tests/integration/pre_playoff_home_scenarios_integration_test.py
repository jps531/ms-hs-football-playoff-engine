"""End-to-end integration tests for build_pre_playoff_home_scenarios and
render_team_pre_playoff_home_scenarios.

Exercises the full pipeline:
  1. build_scenario_atoms (atoms from region game data)
  2. determine_scenarios + determine_odds (seeding probabilities)
  3. compute_bracket_advancement_odds / r2/qf/sf home-odds helpers
  4. enumerate_home_game_scenarios(seed=None, ...)
  5. render_pre_playoff_team_home_scenarios (combined render)

All tested against real 2025 Region 8-1A data at the pre-final-week cutoff.
"""

import pytest

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import (
    build_pre_playoff_home_scenarios,
    render_team_pre_playoff_home_scenarios,
)
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

_CUTOFF = "2025-10-24"
_REGION = 8
_SEASON = 2025
_TEAM = "Taylorsville"


def _region_8_inputs():
    """Return (teams, completed, remaining) for Region 8-1A at the cutoff."""
    fixture = REGION_RESULTS_2025[(1, 8)]
    all_games = fixture["games"]
    completed_compact = [g for g in all_games if g["date"] <= _CUTOFF]
    remaining_compact = [g for g in all_games if g["date"] > _CUTOFF]
    teams = teams_from_games(all_games)
    completed = get_completed_games(expand_results(completed_compact))
    remaining = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in remaining_compact]
    return teams, completed, remaining


@pytest.fixture(scope="module")
def region_8_inputs():
    """Return (teams, completed, remaining) for Region 8-1A at the 2025-10-24 cutoff."""
    return _region_8_inputs()


@pytest.fixture(scope="module")
def home_scenarios_and_atoms(region_8_inputs):
    """Return (home_scenarios, atoms) from build_pre_playoff_home_scenarios for Taylorsville."""
    teams, completed, remaining = region_8_inputs
    return build_pre_playoff_home_scenarios(
        team=_TEAM,
        region=_REGION,
        season=_SEASON,
        slots=SLOTS_1A_4A_2025,
        teams=teams,
        completed=completed,
        remaining=remaining,
    )


@pytest.fixture(scope="module")
def rendered(region_8_inputs):
    """Return the rendered string from render_team_pre_playoff_home_scenarios for Taylorsville."""
    teams, completed, remaining = region_8_inputs
    return render_team_pre_playoff_home_scenarios(
        team=_TEAM,
        region=_REGION,
        season=_SEASON,
        slots=SLOTS_1A_4A_2025,
        teams=teams,
        completed=completed,
        remaining=remaining,
    )


# ---------------------------------------------------------------------------
# Return-type and structure tests
# ---------------------------------------------------------------------------


class TestReturnTypes:
    """build_pre_playoff_home_scenarios returns the correct types and shapes."""

    def test_returns_tuple(self, home_scenarios_and_atoms):
        """Return value is a 2-tuple of (home_scenarios, atoms)."""
        assert isinstance(home_scenarios_and_atoms, tuple)
        assert len(home_scenarios_and_atoms) == 2

    def test_home_scenarios_is_list(self, home_scenarios_and_atoms):
        """home_scenarios is a list of exactly four rounds for a 1A–4A bracket."""
        home_scenarios, _ = home_scenarios_and_atoms
        assert isinstance(home_scenarios, list)
        assert len(home_scenarios) == 4  # 1A-4A: R1, R2, QF, SF

    def test_atoms_contains_team(self, home_scenarios_and_atoms):
        """atoms dict contains an entry for the target team."""
        _, atoms = home_scenarios_and_atoms
        assert _TEAM in atoms

    def test_atoms_has_seed1_and_seed2(self, home_scenarios_and_atoms):
        """atoms for the team include entries for both achievable seeds (1 and 2)."""
        _, atoms = home_scenarios_and_atoms
        assert 1 in atoms[_TEAM]
        assert 2 in atoms[_TEAM]

    def test_render_returns_string(self, rendered):
        """render_team_pre_playoff_home_scenarios returns a non-empty string."""
        assert isinstance(rendered, str)
        assert len(rendered) > 0


# ---------------------------------------------------------------------------
# Correct odds (Q3 regression: ensure determine_scenarios is used, not the
# inaccurate compute_odds_from_precomputed path)
# ---------------------------------------------------------------------------


class TestRealOdds:
    """Odds must match the margin-accurate determination from determine_scenarios."""

    def test_r1_host_is_100_percent(self, rendered):
        """Both achievable seeds (1 and 2) are home in R1 → 100.0%."""
        assert "Will Host First Round (100.0%)" in rendered

    def test_r2_host_matches_fixture_odds(self, rendered):
        """R2 host probability ≈ 43.2% — verifies margin-accurate seeding odds."""
        assert "Will Host Second Round (43.2%)" in rendered

    def test_r2_away_is_complement(self, rendered):
        """R2 away probability is the complement of the host probability (56.8%)."""
        assert "Will Not Host Second Round (56.8%)" in rendered

    def test_qf_host_matches_fixture_odds(self, rendered):
        """Quarterfinal host probability matches the fixture value (9.8%)."""
        assert "Will Host Quarterfinals (9.8%)" in rendered

    def test_sf_host_matches_fixture_odds(self, rendered):
        """Semifinal host probability matches the fixture value (8.5%)."""
        assert "Will Host Semifinals (8.5%)" in rendered


# ---------------------------------------------------------------------------
# Atom expansion in combined render (Q2)
# ---------------------------------------------------------------------------


class TestAtomExpansion:
    """Combined renderer expands seed_required conditions into actual game atoms."""

    def test_no_seed_required_phrase(self, rendered):
        """Combined render never shows raw 'finishes as the #N seed'."""
        assert "finishes as the #" not in rendered

    def test_r1_seed1_atom_present(self, rendered):
        """Seed-1 atom 'Taylorsville beats Lumberton' appears in R1 output."""
        assert "Taylorsville beats Lumberton" in rendered

    def test_r1_seed1_margin_atom_present(self, rendered):
        """Margin-conditional seed-1 atom appears in R1 output."""
        assert "Lumberton beats Taylorsville by 1\u201311" in rendered

    def test_r1_seed2_atoms_present(self, rendered):
        """Both seed-2 atoms appear in R1 output."""
        assert "Lumberton beats Taylorsville by 12 or more" in rendered
        assert "Resurrection beats Stringer AND Lumberton beats Taylorsville" in rendered

    def test_r2_atoms_include_playoff_advance(self, rendered):
        """R2 scenarios combine game atoms with playoff advance conditions."""
        assert "Taylorsville beats Lumberton AND Taylorsville advances to Second Round" in rendered


# ---------------------------------------------------------------------------
# Eliminated team raises ValueError
# ---------------------------------------------------------------------------


class TestEliminatedTeam:
    """build_pre_playoff_home_scenarios raises ValueError for eliminated or unknown teams."""

    def test_resurrection_raises_value_error(self, region_8_inputs):
        """Resurrection is eliminated before the final week — must raise."""
        teams, completed, remaining = region_8_inputs
        with pytest.raises(ValueError, match="eliminated"):
            build_pre_playoff_home_scenarios(
                team="Resurrection",
                region=_REGION,
                season=_SEASON,
                slots=SLOTS_1A_4A_2025,
                teams=teams,
                completed=completed,
                remaining=remaining,
            )

    def test_unknown_team_raises_value_error(self, region_8_inputs):
        """A team name not found in the region raises ValueError."""
        teams, completed, remaining = region_8_inputs
        with pytest.raises(ValueError):
            build_pre_playoff_home_scenarios(
                team="Nonexistent School",
                region=_REGION,
                season=_SEASON,
                slots=SLOTS_1A_4A_2025,
                teams=teams,
                completed=completed,
                remaining=remaining,
            )


# ---------------------------------------------------------------------------
# Correct structure of returned home_scenarios
# ---------------------------------------------------------------------------


class TestHomeScenarioStructure:
    """Structural checks on the returned home_scenarios list."""

    def test_round_names(self, home_scenarios_and_atoms):
        """Round names follow the canonical 1A–4A order."""
        home_scenarios, _ = home_scenarios_and_atoms
        names = [r.round_name for r in home_scenarios]
        assert names == ["First Round", "Second Round", "Quarterfinals", "Semifinals"]

    def test_r1_all_scenarios_are_home(self, home_scenarios_and_atoms):
        """Region 8 seeds 1 and 2 are both home in R1 → 2 will_host, 0 will_not_host."""
        home_scenarios, _ = home_scenarios_and_atoms
        r1 = home_scenarios[0]
        assert len(r1.will_host) == 2  # one scenario per achievable seed
        assert len(r1.will_not_host) == 0

    def test_r2_has_both_host_and_away(self, home_scenarios_and_atoms):
        """R2 has at least one home scenario and one away scenario."""
        home_scenarios, _ = home_scenarios_and_atoms
        r2 = home_scenarios[1]
        assert len(r2.will_host) >= 1
        assert len(r2.will_not_host) >= 1

    def test_odds_attached_to_rounds(self, home_scenarios_and_atoms):
        """Every round has non-None p_reach and p_host_marginal odds."""
        home_scenarios, _ = home_scenarios_and_atoms
        for rnd in home_scenarios:
            assert rnd.p_reach is not None
            assert rnd.p_host_marginal is not None
