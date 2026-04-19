"""Non-margin scenario output tests for Region 3-7A (2025 season).

Two checkpoints test the ``ignore_margins=True`` path at different R values:

Checkpoint A — 0 games played (cutoff 2025-10-02, R=15):
  All 15 region games are still unplayed.  With ignore_margins=True, no margin
  enumeration runs.  22910 scenarios result, 1934 of which contain coin-flip
  ties (``coinflip_groups``).  No tiebreaker groups appear because completed
  game point differentials haven't yet separated any teams' PD.

Checkpoint B — 1 week played (cutoff 2025-10-10, R=12):
  Three games have completed results baked into the standings.  2869 scenarios
  remain.  216 of them contain ``tiebreaker_groups`` — masks where the seeding
  would differ between margin=1 and margin=7 for the remaining 12 games.
  No coin-flip scenarios at this checkpoint (real PD resolves ties).

Teams: Brandon, Meridian, Northwest Rankin, Oak Grove, Pearl, Petal
"""

import pytest

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import enumerate_division_scenarios, enumerate_outcomes, render_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(7, 3)]
_ALL_GAMES = _FIXTURE["games"]
_TEAMS = teams_from_games(_ALL_GAMES)

_CUTOFF_A = "2025-10-02"  # 0 games played — all 15 games remaining
_CUTOFF_B = "2025-10-10"  # 1 week played — 12 games remaining

# ---------------------------------------------------------------------------
# Checkpoint A: R=15, ignore_margins=True — built once at module level
# ---------------------------------------------------------------------------

_COMPLETED_A = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_A]))
_REMAINING_A = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_A]

_EO_A = enumerate_outcomes(_TEAMS, _COMPLETED_A, _REMAINING_A, ignore_margins=True)
_SCENARIOS_A = enumerate_division_scenarios(_TEAMS, _COMPLETED_A, _REMAINING_A, precomputed=_EO_A)

# ---------------------------------------------------------------------------
# Checkpoint B: R=12, ignore_margins=True — built once at module level
# ---------------------------------------------------------------------------

_COMPLETED_B = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_B]))
_REMAINING_B = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_B]

_EO_B = enumerate_outcomes(_TEAMS, _COMPLETED_B, _REMAINING_B, ignore_margins=True)
_SCENARIOS_B = enumerate_division_scenarios(_TEAMS, _COMPLETED_B, _REMAINING_B, precomputed=_EO_B)


# ===========================================================================
# Checkpoint A tests (R=15, 0 games played)
# ===========================================================================


class TestCheckpointA:
    """Structural and count tests for R=15 ignore_margins=True checkpoint."""

    def test_teams(self):
        """Region 3-7A has the expected 6 teams."""
        assert sorted(_TEAMS) == ["Brandon", "Meridian", "Northwest Rankin", "Oak Grove", "Pearl", "Petal"]

    def test_remaining_game_count(self):
        """0 games played → all 15 region games are remaining."""
        assert len(_REMAINING_A) == 15

    def test_scenario_count(self):
        """R=15, ignore_margins=True produces 18607 scenarios."""
        assert len(_SCENARIOS_A) == 18607

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom",
                    "tiebreaker_groups", "coinflip_groups"}
        for sc in _SCENARIOS_A:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, no scenario has conditions_atom set."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_A)

    def test_no_tiebreaker_groups(self):
        """With 0 completed games (no PD differentiation), no tiebreaker_groups appear."""
        assert all(sc["tiebreaker_groups"] is None for sc in _SCENARIOS_A)

    def test_coinflip_scenario_count(self):
        """1508 scenarios have coinflip_groups (ties unresolvable by win-loss alone)."""
        cf_count = sum(1 for sc in _SCENARIOS_A if sc["coinflip_groups"] is not None)
        assert cf_count == 1508

    def test_coinflip_scenarios_have_no_sub_label(self):
        """Collapsed coin-flip scenarios use sub_label='' — no sub-scenario expansion."""
        for sc in _SCENARIOS_A:
            if sc["coinflip_groups"] is not None:
                assert sc["sub_label"] == ""

    def test_unique_seedings(self):
        """The 22910 scenarios cover all 720 possible orderings of 6 teams."""
        unique = {sc["seeding"] for sc in _SCENARIOS_A}
        assert len(unique) == 720

    def test_all_teams_reach_top_4(self):
        """Every team appears at least once in a top-4 seeding."""
        top4_teams = {team for sc in _SCENARIOS_A for team in sc["seeding"][:4]}
        assert top4_teams == set(_TEAMS)

    def test_first_scenario_seeding(self):
        """First scenario: Petal / Pearl / Oak Grove / Northwest Rankin (no tie, no cf)."""
        sc = _SCENARIOS_A[0]
        assert sc["scenario_num"] == 1
        assert sc["sub_label"] == ""
        assert sc["seeding"][:4] == ("Petal", "Pearl", "Oak Grove", "Northwest Rankin")
        assert sc["tiebreaker_groups"] is None
        assert sc["coinflip_groups"] is None

    def test_coinflip_groups_format(self):
        """coinflip_groups is a list of lists of team name strings."""
        for sc in _SCENARIOS_A:
            if sc["coinflip_groups"] is not None:
                assert isinstance(sc["coinflip_groups"], list)
                for group in sc["coinflip_groups"]:
                    assert isinstance(group, list)
                    assert all(isinstance(t, str) for t in group)
                    assert all(t in _TEAMS for t in group)
                break  # only need to check one

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes.ignore_margins is True when ignore_margins=True."""
        assert _EO_A.ignore_margins is True

    def test_enumerated_outcomes_no_margin_sensitive(self):
        """All 32768 masks are non-sensitive with ignore_margins=True (R=15)."""
        assert len(_EO_A.non_sensitive_masks) == 32768

    def test_coinflip_sample_rendering(self):
        """A coin-flip group renders '1-3. Tie between … — depends on point differential'."""
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
        pytest.skip("No fully-in-bounds coin-flip group found (all span boundary)")


# ===========================================================================
# Checkpoint B tests (R=12, 1 week played)
# ===========================================================================


class TestCheckpointB:
    """Structural and count tests for R=12 ignore_margins=True checkpoint."""

    def test_remaining_game_count(self):
        """After 1 week, 12 region games remain."""
        assert len(_REMAINING_B) == 12

    def test_scenario_count(self):
        """R=12, ignore_margins=True produces 2478 scenarios."""
        assert len(_SCENARIOS_B) == 2478

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom",
                    "tiebreaker_groups", "coinflip_groups"}
        for sc in _SCENARIOS_B:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, no scenario has conditions_atom set."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_B)

    def test_no_coinflip_scenarios(self):
        """Real game PD data resolves all coin-flip ties at 1-week checkpoint."""
        assert all(sc["coinflip_groups"] is None for sc in _SCENARIOS_B)

    def test_tiebreaker_scenario_count(self):
        """179 scenarios have tiebreaker_groups (margin-sensitive under full enumeration)."""
        tb_count = sum(1 for sc in _SCENARIOS_B if sc["tiebreaker_groups"] is not None)
        assert tb_count == 179

    def test_tiebreaker_scenarios_have_no_sub_label(self):
        """Collapsed tiebreaker scenarios use sub_label='' — no margin sub-scenarios."""
        for sc in _SCENARIOS_B:
            if sc["tiebreaker_groups"] is not None:
                assert sc["sub_label"] == ""

    def test_first_scenario_seeding(self):
        """Scenario 1: Petal / Pearl / Oak Grove / Northwest Rankin."""
        sc = _SCENARIOS_B[0]
        assert sc["scenario_num"] == 1
        assert sc["seeding"][:4] == ("Petal", "Pearl", "Oak Grove", "Northwest Rankin")
        assert sc["coinflip_groups"] is None

    def test_first_scenario_tiebreaker_groups(self):
        """Scenario 1 has tiebreaker_groups covering the 3-way PD tie for seeds 4-eliminated."""
        sc = _SCENARIOS_B[0]
        tb = sc["tiebreaker_groups"]
        assert tb is not None
        assert len(tb) == 1
        assert set(tb[0]) == {"Northwest Rankin", "Meridian", "Brandon"}

    def test_tiebreaker_rendered_in_bounds(self):
        """A tiebreaker group fully within top-4 renders '… depends on point differential'."""
        for sc in _SCENARIOS_B:
            tb = sc.get("tiebreaker_groups")
            if not tb:
                continue
            seeding_list = list(sc["seeding"])
            for group in tb:
                positions = sorted(seeding_list.index(t) for t in group if t in seeding_list)
                if all(p < 4 for p in positions):
                    rendered = render_scenarios([sc])
                    assert "depends on point differential" in rendered
                    # Should not say 'depends on coin flip'
                    assert "coin flip" not in rendered
                    return
        pytest.fail("No fully-in-bounds tiebreaker_groups found in checkpoint B")

    def test_scenario_29_seeding_and_tb(self):
        """Scenario 29 has a 3-way PD tie between Pearl, Petal, and Brandon (seeds 1-3)."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 29 and s["sub_label"] == "")
        assert sc["seeding"][:4] == ("Pearl", "Petal", "Brandon", "Oak Grove")
        tb = sc["tiebreaker_groups"]
        assert tb is not None
        assert set(tb[0]) == {"Pearl", "Petal", "Brandon"}

    def test_scenario_29_renders_tb(self):
        """Scenario 29 renders a '1-3. Tie between Pearl, Petal, and Brandon' line."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 29 and s["sub_label"] == "")
        rendered = render_scenarios([sc])
        assert "1-3. Tie between Pearl, Petal, and Brandon — depends on point differential" in rendered

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes.ignore_margins is True for checkpoint B."""
        assert _EO_B.ignore_margins is True
