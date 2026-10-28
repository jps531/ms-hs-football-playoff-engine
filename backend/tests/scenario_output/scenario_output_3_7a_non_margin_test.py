"""Non-margin scenario output tests for Region 3-7A (2025 season).

Two checkpoints test the ``ignore_margins=True`` path at different R values:

Checkpoint A — 0 games played (cutoff 2025-10-02, R=15):
  All 15 region games are still unplayed.  With ignore_margins=True, no margin
  enumeration runs.  18773 scenarios result, 1088 of which leave a tie to the
  tiebreaker (``open_groups`` from step 3) instead of ordering it at a default margin.

Checkpoint B — 1 week played (cutoff 2025-10-10, R=12):
  Three games have completed results baked into the standings.  2334 scenarios
  remain, 160 of them with a tie left to the tiebreaker: its order would turn on
  the remaining games' margins.

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
        """R=15, ignore_margins=True produces 19199 scenarios."""
        assert len(_SCENARIOS_A) == 19199

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {
            "scenario_num",
            "sub_label",
            "seeding",
            "game_winners",
            "conditions_atom",
            "alternatives",
            "open_groups",
            "open_places",
            "place_terms",
        }
        for sc in _SCENARIOS_A:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, no scenario has conditions_atom set."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_A)

    def test_coinflip_scenario_count(self):
        """2288 scenarios leave a tie to the tiebreaker (unresolvable by win-loss alone)."""
        assert sum(1 for sc in _SCENARIOS_A if sc["open_groups"]) == 2288

    def test_unique_seedings(self):
        """360 distinct seedings: every order of the playoff seeds, with the two teams out unranked."""
        unique = {sc["seeding"] for sc in _SCENARIOS_A}
        assert len(unique) == 360

    def test_all_teams_reach_top_4(self):
        """Every team appears at least once in a top-4 seeding."""
        top4_teams = {team for sc in _SCENARIOS_A for team in sc["seeding"][:4]}
        assert top4_teams == set(_TEAMS)

    def test_first_scenario_seeding(self):
        """First scenario: Petal / Pearl / Oak Grove / Northwest Rankin (no tie left open)."""
        sc = _SCENARIOS_A[0]
        assert sc["scenario_num"] == 1
        assert sc["sub_label"] == ""
        assert sc["seeding"][:4] == ("Petal", "Pearl", "Oak Grove", "Northwest Rankin")
        assert sc["open_groups"] is None

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes.ignore_margins is True when ignore_margins=True."""
        assert _EO_A.ignore_margins is True

    def test_enumerated_outcomes_no_margin_sensitive(self):
        """All 32768 masks are non-sensitive with ignore_margins=True (R=15)."""
        assert len(_EO_A.non_sensitive_masks) == 32768


# ===========================================================================
# Checkpoint B tests (R=12, 1 week played)
# ===========================================================================


class TestCheckpointB:
    """Structural and count tests for R=12 ignore_margins=True checkpoint."""

    def test_remaining_game_count(self):
        """After 1 week, 12 region games remain."""
        assert len(_REMAINING_B) == 12

    def test_scenario_count(self):
        """R=12, ignore_margins=True produces 2392 scenarios."""
        assert len(_SCENARIOS_B) == 2392

    def test_scenario_keys(self):
        """Every scenario dict has the required keys."""
        required = {
            "scenario_num",
            "sub_label",
            "seeding",
            "game_winners",
            "conditions_atom",
            "alternatives",
            "open_groups",
            "open_places",
            "place_terms",
        }
        for sc in _SCENARIOS_B:
            assert set(sc.keys()) == required

    def test_no_margin_sensitive_scenarios(self):
        """With ignore_margins=True, no scenario has conditions_atom set."""
        assert all(sc["conditions_atom"] is None for sc in _SCENARIOS_B)

    def test_tiebreaker_scenario_count(self):
        """310 scenarios leave a tie to the tiebreaker: its order would turn on margins."""
        assert sum(1 for sc in _SCENARIOS_B if sc["open_groups"]) == 310

    def test_first_scenario_seeding(self):
        """Scenario 1: Petal / Pearl / Oak Grove, with 4th left to a tie."""
        sc = _SCENARIOS_B[0]
        assert sc["scenario_num"] == 1
        assert sc["seeding"][:3] == ("Petal", "Pearl", "Oak Grove")

    def test_first_scenario_leaves_its_tie_open(self):
        """Scenario 1 leaves the 3-way tie for 4th (and two places out) to the tiebreaker."""
        sc = _SCENARIOS_B[0]
        assert sc["open_groups"] == [(3, ("Brandon", "Meridian", "Northwest Rankin"))]
        assert "4. Brandon, Meridian or Northwest Rankin: order decided by the tiebreaker" in render_scenarios([sc])

    def test_tiebreaker_rendered_in_bounds(self):
        """A tie wholly within the top 4 renders as one line over its places, never as an order or a coin flip."""
        for sc in _SCENARIOS_B:
            for _, group in sc.get("open_groups") or []:
                if all(list(sc["seeding"]).index(t) < 4 for t in group):
                    rendered = render_scenarios([sc])
                    assert (
                        "order decided by the tiebreaker (point differential, then fewest points allowed)" in rendered
                    )
                    assert "coin flip" not in rendered
                    return
        pytest.fail("No tie within the top 4 found in checkpoint B")

    @staticmethod
    def _three_way_open():
        """A scenario leaving a 3-way tie between Pearl, Petal, and Brandon (seeds 1-3) open, Oak Grove 4th."""
        return next(
            s
            for s in _SCENARIOS_B
            if s["open_groups"] == [(3, ("Brandon", "Pearl", "Petal"))] and s["seeding"][3] == "Oak Grove"
        )

    def test_scenario_with_three_way_tie_open(self):
        """Some scenario leaves Brandon, Pearl and Petal's 3-way tie at seeds 1-3 open, with Oak Grove 4th."""
        sc = self._three_way_open()
        assert sc["sub_label"] == ""

    def test_three_way_open_tie_renders(self):
        """That scenario renders one '1-3.' line for Brandon, Pearl and Petal, in no order."""
        sc = self._three_way_open()
        rendered = render_scenarios([sc])
        assert "1-3. Brandon, Pearl, and Petal: order decided by the tiebreaker" in rendered

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes.ignore_margins is True for checkpoint B."""
        assert _EO_B.ignore_margins is True
