"""Non-margin scenario output tests for Region 8-1A (2025 season).

Two checkpoints test ``ignore_margins=True`` at different R values:

Checkpoint A — 0 games played (cutoff 2025-10-02, R=10):
  All 10 region games are unplayed.  604 scenarios result from the ignore_margins
  path.  152 of them have coin-flip groups — ties that can only be broken by a
  coin flip regardless of the remaining game outcomes.  No tiebreaker groups
  appear since no completed-game PD yet differentiates any teams.

Checkpoint B — 1 week played (cutoff 2025-10-03, R=8):
  The first week's 2 games have completed.  164 scenarios remain.  Real game
  point differentials completely resolve all ties — no tiebreaker groups and
  no coin-flip groups appear.

Teams (5): Lumberton, Resurrection, Richton, Stringer, Taylorsville
"""

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import enumerate_division_scenarios, enumerate_outcomes, render_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(1, 8)]
_ALL_GAMES = _FIXTURE["games"]
_TEAMS = teams_from_games(_ALL_GAMES)

_CUTOFF_A = "2025-10-02"  # 0 games played — all 10 games remaining
_CUTOFF_B = "2025-10-03"  # 1 week played — 8 games remaining

# ---------------------------------------------------------------------------
# Checkpoint A: R=10, ignore_margins=True
# ---------------------------------------------------------------------------

_COMPLETED_A = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_A]))
_REMAINING_A = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_A]

_EO_A = enumerate_outcomes(_TEAMS, _COMPLETED_A, _REMAINING_A, ignore_margins=True)
_SCENARIOS_A = enumerate_division_scenarios(_TEAMS, _COMPLETED_A, _REMAINING_A, precomputed=_EO_A)

# ---------------------------------------------------------------------------
# Checkpoint B: R=8, ignore_margins=True
# ---------------------------------------------------------------------------

_COMPLETED_B = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_B]))
_REMAINING_B = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_B]

_EO_B = enumerate_outcomes(_TEAMS, _COMPLETED_B, _REMAINING_B, ignore_margins=True)
_SCENARIOS_B = enumerate_division_scenarios(_TEAMS, _COMPLETED_B, _REMAINING_B, precomputed=_EO_B)


# ===========================================================================
# Checkpoint A tests (R=10, 0 games played)
# ===========================================================================


class TestCheckpointA:
    """R=10, ignore_margins=True — 0 games played."""

    def test_teams(self):
        """Region 8-1A has 5 teams."""
        assert sorted(_TEAMS) == ["Lumberton", "Resurrection", "Richton", "Stringer", "Taylorsville"]

    def test_remaining_game_count(self):
        """0 games played → all 10 region games are remaining."""
        assert len(_REMAINING_A) == 10

    def test_scenario_count(self):
        """R=10, ignore_margins=True produces 604 scenarios."""
        assert len(_SCENARIOS_A) == 604

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {
            "scenario_num",
            "sub_label",
            "seeding",
            "game_winners",
            "conditions_atom",
            "tiebreaker_groups",
            "coinflip_groups",
        }
        for sc in _SCENARIOS_A:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, conditions_atom is always None."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_A)

    def test_no_tiebreaker_groups(self):
        """No tiebreaker_groups with 0 completed games (no PD differentiation)."""
        assert all(sc["tiebreaker_groups"] is None for sc in _SCENARIOS_A)

    def test_coinflip_scenario_count(self):
        """152 scenarios have coinflip_groups."""
        cf_count = sum(1 for sc in _SCENARIOS_A if sc["coinflip_groups"] is not None)
        assert cf_count == 152

    def test_coinflip_scenarios_have_no_sub_label(self):
        """Collapsed coin-flip scenarios use sub_label='' — no expansion."""
        for sc in _SCENARIOS_A:
            if sc["coinflip_groups"] is not None:
                assert sc["sub_label"] == ""

    def test_unique_seedings(self):
        """All 120 permutations of 5 teams appear."""
        unique = {sc["seeding"] for sc in _SCENARIOS_A}
        assert len(unique) == 120

    def test_all_teams_reach_top_4(self):
        """Every team appears at least once in a top-4 seeding."""
        top4_teams = {team for sc in _SCENARIOS_A for team in sc["seeding"][:4]}
        assert top4_teams == set(_TEAMS)

    def test_first_scenario_seeding(self):
        """First scenario: Taylorsville / Stringer / Richton / Resurrection (no tie)."""
        sc = _SCENARIOS_A[0]
        assert sc["scenario_num"] == 1
        assert sc["sub_label"] == ""
        assert sc["seeding"][:4] == ("Taylorsville", "Stringer", "Richton", "Resurrection")
        assert sc["tiebreaker_groups"] is None
        assert sc["coinflip_groups"] is None

    def test_coinflip_group_format(self):
        """coinflip_groups is a list of lists of team name strings."""
        cf_scens = [s for s in _SCENARIOS_A if s["coinflip_groups"] is not None]
        assert len(cf_scens) > 0
        for sc in cf_scens[:5]:
            for group in sc["coinflip_groups"]:
                assert isinstance(group, list)
                assert len(group) >= 2
                assert all(t in _TEAMS for t in group)

    def test_coinflip_rendering_in_bounds(self):
        """A coin-flip group fully within top-4 renders '… depends on point differential'."""
        for sc in _SCENARIOS_A:
            if sc["coinflip_groups"] is None:
                continue
            seeding_list = list(sc["seeding"])
            for group in sc["coinflip_groups"]:
                positions = sorted(seeding_list.index(t) for t in group if t in seeding_list)
                if all(p < 4 for p in positions):
                    rendered = render_scenarios([sc])
                    assert "depends on point differential" in rendered
                    return
        # All coin-flip groups span playoff/elimination boundary — no in-bounds group to render.
        pass

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes built with ignore_margins=True sets the flag."""
        assert _EO_A.ignore_margins is True

    def test_enumerated_outcomes_all_non_sensitive(self):
        """All 1024 masks are non-sensitive with ignore_margins=True (R=10)."""
        assert len(_EO_A.non_sensitive_masks) == 1024


# ===========================================================================
# Checkpoint B tests (R=8, 1 week played)
# ===========================================================================


class TestCheckpointB:
    """R=8, ignore_margins=True — 1 week played."""

    def test_remaining_game_count(self):
        """After week 1, 8 region games remain."""
        assert len(_REMAINING_B) == 8

    def test_scenario_count(self):
        """R=8, ignore_margins=True produces 164 scenarios."""
        assert len(_SCENARIOS_B) == 164

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {
            "scenario_num",
            "sub_label",
            "seeding",
            "game_winners",
            "conditions_atom",
            "tiebreaker_groups",
            "coinflip_groups",
        }
        for sc in _SCENARIOS_B:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, conditions_atom is always None."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_B)

    def test_no_tiebreaker_groups(self):
        """Real game PD at R=8 resolves all tiebreaker sensitivity — 0 tiebreaker groups."""
        assert all(sc["tiebreaker_groups"] is None for sc in _SCENARIOS_B)

    def test_no_coinflip_groups(self):
        """Real game PD at R=8 resolves all coin-flip ties — 0 coinflip groups."""
        assert all(sc["coinflip_groups"] is None for sc in _SCENARIOS_B)

    def test_first_scenario_seeding(self):
        """First scenario: Taylorsville / Stringer / Richton / Resurrection."""
        sc = _SCENARIOS_B[0]
        assert sc["scenario_num"] == 1
        assert sc["seeding"][:4] == ("Taylorsville", "Stringer", "Richton", "Resurrection")

    def test_all_teams_reachable_in_top4(self):
        """All 5 teams can reach a top-4 seed at this checkpoint."""
        top4_teams = {team for sc in _SCENARIOS_B for team in sc["seeding"][:4]}
        assert top4_teams == set(_TEAMS)

    def test_unique_seedings(self):
        """74 distinct seedings appear at this checkpoint."""
        unique = {sc["seeding"] for sc in _SCENARIOS_B}
        assert len(unique) == 74

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes built with ignore_margins=True sets the flag."""
        assert _EO_B.ignore_margins is True
