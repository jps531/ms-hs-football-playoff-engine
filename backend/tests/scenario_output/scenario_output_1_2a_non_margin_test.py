"""Non-margin scenario output tests for Region 1-2A (2025 season).

Two checkpoints test different enumeration modes:

Checkpoint A — 0 games played (cutoff 2025-10-15, R=6, ignore_margins=True):
  All 6 region games are unplayed.  41 scenarios result.  16 of them have
  ``coinflip_groups`` — ties that require a coin flip.  No tiebreaker_groups
  appear since no completed-game PD differentiates any teams.

Checkpoint B — 1 week played (cutoff 2025-10-17, R=4, ignore_margins=False):
  Two games have completed:
    Hamilton beat Walnut 49-22
    Baldwyn beat Hatley 53-18
  4 games remain.  Full margin enumeration runs (12^4 = 20736 combos per mask).
  28 scenarios result: 8 plain (no margin constraint) and 20 margin-sensitive
  (sub-labelled a/b/c/…).  No coinflip_groups (ignore_margins=False uses the
  expanded coinflip sub-scenario format instead).

Teams (4): Baldwyn, Hamilton, Hatley, Walnut
"""

from backend.helpers.data_classes import GameResult, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import enumerate_division_scenarios, enumerate_outcomes, render_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(2, 1)]
_ALL_GAMES = _FIXTURE["games"]
_TEAMS = teams_from_games(_ALL_GAMES)

_CUTOFF_A = "2025-10-15"  # 0 games played — all 6 games remaining
_CUTOFF_B = "2025-10-17"  # 1 week played — 4 games remaining

# ---------------------------------------------------------------------------
# Checkpoint A: R=6, ignore_margins=True
# ---------------------------------------------------------------------------

_COMPLETED_A = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_A]))
_REMAINING_A = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_A]

_EO_A = enumerate_outcomes(_TEAMS, _COMPLETED_A, _REMAINING_A, ignore_margins=True)
_SCENARIOS_A = enumerate_division_scenarios(_TEAMS, _COMPLETED_A, _REMAINING_A, precomputed=_EO_A)

# ---------------------------------------------------------------------------
# Checkpoint B: R=4, ignore_margins=False (full margin enumeration)
# ---------------------------------------------------------------------------

_COMPLETED_B = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF_B]))
_REMAINING_B = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF_B]

_EO_B = enumerate_outcomes(_TEAMS, _COMPLETED_B, _REMAINING_B, ignore_margins=False)
_SCENARIOS_B = enumerate_division_scenarios(_TEAMS, _COMPLETED_B, _REMAINING_B, precomputed=_EO_B)


# ===========================================================================
# Checkpoint A tests (R=6, 0 games played, ignore_margins=True)
# ===========================================================================


class TestCheckpointA:
    """R=6, ignore_margins=True — 0 games played."""

    def test_teams(self):
        """Region 1-2A has the expected 4 teams."""
        assert sorted(_TEAMS) == ["Baldwyn", "Hamilton", "Hatley", "Walnut"]

    def test_remaining_game_count(self):
        """0 games played → all 6 region games are remaining."""
        assert len(_REMAINING_A) == 6

    def test_scenario_count(self):
        """R=6, ignore_margins=True produces 40 scenarios."""
        assert len(_SCENARIOS_A) == 40

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
        """No tiebreaker_groups with 0 completed games."""
        assert all(sc["tiebreaker_groups"] is None for sc in _SCENARIOS_A)

    def test_coinflip_scenario_count(self):
        """16 scenarios have coinflip_groups."""
        cf_count = sum(1 for sc in _SCENARIOS_A if sc["coinflip_groups"] is not None)
        assert cf_count == 16

    def test_coinflip_scenarios_have_no_sub_label(self):
        """Collapsed coin-flip scenarios use sub_label=''."""
        for sc in _SCENARIOS_A:
            if sc["coinflip_groups"] is not None:
                assert sc["sub_label"] == ""

    def test_unique_seedings(self):
        """All 24 permutations of 4 teams appear."""
        unique = {sc["seeding"] for sc in _SCENARIOS_A}
        assert len(unique) == 24

    def test_first_scenario_seeding(self):
        """First scenario: Walnut / Hatley / Hamilton / Baldwyn (definitive, no tie)."""
        sc = _SCENARIOS_A[0]
        assert sc["scenario_num"] == 1
        assert sc["sub_label"] == ""
        assert sc["seeding"] == ("Walnut", "Hatley", "Hamilton", "Baldwyn")
        assert sc["tiebreaker_groups"] is None
        assert sc["coinflip_groups"] is None

    def test_scenario_2_coinflip_three_way(self):
        """Scenario 2 has a 3-way tie among Hamilton, Hatley, Walnut — coin flip."""
        sc = _SCENARIOS_A[1]
        assert sc["scenario_num"] == 2
        assert sc["sub_label"] == ""
        cf = sc["coinflip_groups"]
        assert cf is not None
        assert len(cf) == 1
        assert set(cf[0]) == {"Hamilton", "Hatley", "Walnut"}

    def test_scenario_2_renders_coinflip_tie(self):
        """Scenario 2 renders '1-3. Tie between … — depends on point differential'."""
        sc = _SCENARIOS_A[1]
        rendered = render_scenarios([sc])
        assert "1-3. Tie between" in rendered
        assert "depends on point differential" in rendered

    def test_scenario_3_coinflip_three_way(self):
        """Scenario 3 has a 3-way coin-flip tie among Baldwyn, Hamilton, Hatley."""
        sc = _SCENARIOS_A[2]
        assert sc["scenario_num"] == 3
        cf = sc["coinflip_groups"]
        assert cf is not None
        assert set(cf[0]) == {"Baldwyn", "Hamilton", "Hatley"}

    def test_scenario_3_renders_below_top4(self):
        """Scenario 3 has Walnut at seed 1 and '2-4. Tie…' for the remaining three."""
        sc = _SCENARIOS_A[2]
        rendered = render_scenarios([sc])
        assert "1. Walnut" in rendered
        assert "2-4. Tie between" in rendered
        assert "depends on point differential" in rendered

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes built with ignore_margins=True sets the flag."""
        assert _EO_A.ignore_margins is True

    def test_enumerated_outcomes_all_non_sensitive(self):
        """All 64 masks are non-sensitive with ignore_margins=True (R=6)."""
        assert len(_EO_A.non_sensitive_masks) == 64


# ===========================================================================
# Checkpoint B tests (R=4, 1 week played, ignore_margins=False)
# ===========================================================================


class TestCheckpointB:
    """R=4, ignore_margins=False — full margin enumeration, 1 week played."""

    def test_remaining_game_count(self):
        """After week 1, 4 games remain."""
        assert len(_REMAINING_B) == 4

    def test_scenario_count(self):
        """R=4, full enumeration produces 28 scenarios (8 plain + 20 margin-sensitive)."""
        assert len(_SCENARIOS_B) == 28

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

    def test_no_tiebreaker_groups(self):
        """ignore_margins=False: tiebreaker_groups is always None."""
        assert all(sc["tiebreaker_groups"] is None for sc in _SCENARIOS_B)

    def test_no_coinflip_groups(self):
        """ignore_margins=False: coin flips are expanded into sub-scenarios, not collapsed."""
        assert all(sc["coinflip_groups"] is None for sc in _SCENARIOS_B)

    def test_plain_scenario_count(self):
        """8 scenarios have no margin constraint (conditions_atom is None)."""
        plain = sum(1 for sc in _SCENARIOS_B if sc["conditions_atom"] is None)
        assert plain == 8

    def test_margin_sensitive_scenario_count(self):
        """20 scenarios are margin-sensitive (conditions_atom is not None)."""
        ms = sum(1 for sc in _SCENARIOS_B if sc["conditions_atom"] is not None)
        assert ms == 20

    def test_margin_sensitive_have_sub_label(self):
        """All margin-sensitive scenarios have a non-empty sub_label (a/b/c/…)."""
        for sc in _SCENARIOS_B:
            if sc["conditions_atom"] is not None:
                assert sc["sub_label"] != ""

    def test_plain_scenarios_no_sub_label(self):
        """Plain non-margin scenarios have sub_label=''."""
        for sc in _SCENARIOS_B:
            if sc["conditions_atom"] is None:
                assert sc["sub_label"] == ""

    def test_scenario_1_plain(self):
        """Scenario 1: Hamilton / Walnut / Baldwyn / Hatley — plain, no margin condition."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 1)
        assert sc["sub_label"] == ""
        assert sc["seeding"] == ("Hamilton", "Walnut", "Baldwyn", "Hatley")
        assert sc["conditions_atom"] is None

    def test_scenario_6_has_three_sub_scenarios(self):
        """Scenario 6 has at least 3 sub-scenarios (6a, 6b, 6c…)."""
        sub6 = [s for s in _SCENARIOS_B if s["scenario_num"] == 6]
        assert len(sub6) >= 3
        sub_labels = {s["sub_label"] for s in sub6}
        assert "a" in sub_labels
        assert "b" in sub_labels

    def test_scenario_6a_seeding_and_condition(self):
        """Scenario 6a: Baldwyn / Hamilton / Hatley / Walnut with margin condition."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 6 and s["sub_label"] == "a")
        assert sc["seeding"] == ("Baldwyn", "Hamilton", "Hatley", "Walnut")
        assert sc["conditions_atom"] is not None
        # conditions_atom must include a GameResult with margin constraint
        assert any(
            isinstance(c, GameResult) and (c.min_margin > 1 or c.max_margin is not None) for c in sc["conditions_atom"]
        )

    def test_completed_games_two_played(self):
        """Two games are completed at the 1-week checkpoint (Hamilton beat Walnut, Baldwyn beat Hatley)."""
        assert len(_COMPLETED_B) == 2
        # CompletedGame uses: a, b, res_a (1=win for a, 0=loss)
        pairs = {(g.a, g.b) for g in _COMPLETED_B}
        assert ("Hamilton", "Walnut") in pairs
        assert ("Baldwyn", "Hatley") in pairs

    def test_scenario_4_seeding(self):
        """Scenario 4 (all remaining games resolved without margin ties): Baldwyn / Hatley / Hamilton / Walnut."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 4 and s["sub_label"] == "")
        assert sc["seeding"] == ("Baldwyn", "Hatley", "Hamilton", "Walnut")

    def test_enumerated_outcomes_ignore_margins_flag(self):
        """EnumeratedOutcomes.ignore_margins is False for full enumeration."""
        assert _EO_B.ignore_margins is False

    def test_scenario_1_renders_correctly(self):
        """Scenario 1 renders without any margin or tie annotation."""
        sc = next(s for s in _SCENARIOS_B if s["scenario_num"] == 1 and s["sub_label"] == "")
        rendered = render_scenarios([sc])
        assert "1. Hamilton" in rendered
        assert "2. Walnut" in rendered
        assert "depends on" not in rendered
