"""Tests for coin-flip scenario paths using a synthetic 4-team fixture.

Fixture: Alpha and Beta each beat Gamma and Delta (identical 2-0 records, no
H2H game between them).  The only remaining game is Delta vs Gamma — it doesn't
affect Alpha or Beta at all.  Therefore:
  - For both outcome masks (Delta wins / Gamma wins), Alpha and Beta exhaust all
    seven deterministic tiebreaker steps without being separated → coin flip.
  - The coin flip is always relevant (both teams are within the 2-seed playoff
    cutoff).

This fixture exercises:
  _relevant_flip_groups          (scenario_viewer.py)
  _expand_coin_flip_seedings     (scenario_viewer.py)
  _build_coin_flip_conds         (scenario_viewer.py)
  Step 3b in build_scenario_atoms (scenario_viewer.py)
  "coinflip" branch of enumerate_division_scenarios (scenario_viewer.py)
  CoinFlipResult dispatch in _render_condition (scenario_renderer.py)
  _accumulate_slots with flip_groups (scenarios.py lines 105–134)
"""

import pytest

from backend.helpers.data_classes import CoinFlipResult, CompletedGame, RemainingGame
from backend.helpers.scenario_renderer import render_team_scenarios
from backend.helpers.scenario_viewer import (
    _build_coin_flip_conds,
    _expand_coin_flip_seedings,
    _relevant_flip_groups,
    build_scenario_atoms,
    enumerate_division_scenarios,
    enumerate_outcomes,
)
from backend.helpers.scenarios import determine_odds, determine_scenarios

# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

_TEAMS = ["Alpha", "Beta", "Delta", "Gamma"]  # alphabetical
_PLAYOFF_SEEDS = 2

# Alpha and Beta each beat Delta and Gamma by 10, with identical margins.
# CompletedGame(a, b, res_a, pd_a, pa_a, pa_b):
#   res_a=1 → a wins; pd_a=10 → a won by 10; pa_a=14 → points allowed by a;
#   pa_b=24 → points allowed by b.
_COMPLETED = [
    CompletedGame(a="Alpha", b="Delta",  res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Alpha", b="Gamma",  res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Beta",  b="Delta",  res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Beta",  b="Gamma",  res_a=1, pd_a=10, pa_a=14, pa_b=24),
]

# Only remaining game is Delta vs Gamma — doesn't touch Alpha or Beta.
_REMAINING = [RemainingGame(a="Delta", b="Gamma")]

# Computed once at module level.
_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING, playoff_seeds=_PLAYOFF_SEEDS)
_SCENARIOS = enumerate_division_scenarios(
    _TEAMS, _COMPLETED, _REMAINING, playoff_seeds=_PLAYOFF_SEEDS, scenario_atoms=_ATOMS
)
_r = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(
    _TEAMS,
    _r.first_counts, _r.second_counts, _r.third_counts, _r.fourth_counts,
    _r.denom,
)


# ---------------------------------------------------------------------------
# Unit tests: _relevant_flip_groups
# ---------------------------------------------------------------------------


class TestRelevantFlipGroups:
    """_relevant_flip_groups keeps only groups with a member inside playoff range."""

    _SEEDING = ["Alpha", "Beta", "Delta", "Gamma"]

    def test_keeps_group_spanning_playoff_boundary(self):
        """Flip group whose members are all within playoff range → included."""
        groups = [["Alpha", "Beta"]]
        result = _relevant_flip_groups(groups, self._SEEDING, playoff_seeds=2)
        assert result == [["Alpha", "Beta"]]

    def test_drops_group_entirely_outside_playoff_range(self):
        """Flip group where no member is in top-N → excluded."""
        groups = [["Delta", "Gamma"]]  # positions 2 and 3, outside top-2
        result = _relevant_flip_groups(groups, self._SEEDING, playoff_seeds=2)
        assert result == []

    def test_keeps_group_straddling_boundary(self):
        """Group with one member at the last playoff seed → included."""
        groups = [["Beta", "Delta"]]  # Beta at index 1 (< 2)
        result = _relevant_flip_groups(groups, self._SEEDING, playoff_seeds=2)
        assert result == [["Beta", "Delta"]]

    def test_multiple_groups_filtered_correctly(self):
        """Only groups with a playoff-range member are returned."""
        groups = [["Alpha", "Beta"], ["Delta", "Gamma"]]
        result = _relevant_flip_groups(groups, self._SEEDING, playoff_seeds=2)
        assert result == [["Alpha", "Beta"]]


# ---------------------------------------------------------------------------
# Unit tests: _expand_coin_flip_seedings
# ---------------------------------------------------------------------------


class TestExpandCoinFlipSeedings:
    """_expand_coin_flip_seedings generates all permutations of each flip group."""

    def test_two_team_flip_produces_two_seedings(self):
        """A 2-team flip group yields 2 expanded seedings."""
        canonical = ["Alpha", "Beta", "Delta", "Gamma"]
        result = _expand_coin_flip_seedings(canonical, [["Alpha", "Beta"]])
        assert len(result) == 2

    def test_both_orderings_present(self):
        """Both (Alpha, Beta, ...) and (Beta, Alpha, ...) appear."""
        canonical = ["Alpha", "Beta", "Delta", "Gamma"]
        result = _expand_coin_flip_seedings(canonical, [["Alpha", "Beta"]])
        seedings = {s[:2] for s in result}
        assert ("Alpha", "Beta") in seedings
        assert ("Beta", "Alpha") in seedings

    def test_non_flip_positions_unchanged(self):
        """Teams not in any flip group stay in their original positions."""
        canonical = ["Alpha", "Beta", "Delta", "Gamma"]
        result = _expand_coin_flip_seedings(canonical, [["Alpha", "Beta"]])
        for seeding in result:
            assert seeding[2] == "Delta"
            assert seeding[3] == "Gamma"

    def test_empty_flip_groups_returns_original(self):
        """With no flip groups, returns the canonical seeding unchanged."""
        canonical = ["Alpha", "Beta", "Delta", "Gamma"]
        result = _expand_coin_flip_seedings(canonical, [])
        assert result == [tuple(canonical)]

    def test_three_team_flip_produces_six_seedings(self):
        """A 3-team flip group yields 3! = 6 expanded seedings."""
        canonical = ["Alpha", "Beta", "Delta", "Gamma"]
        result = _expand_coin_flip_seedings(canonical, [["Alpha", "Beta", "Delta"]])
        assert len(result) == 6


# ---------------------------------------------------------------------------
# Unit tests: _build_coin_flip_conds
# ---------------------------------------------------------------------------


class TestBuildCoinFlipConds:
    """_build_coin_flip_conds emits pairwise CoinFlipResult conditions."""

    def test_two_team_group_produces_one_condition(self):
        """A 2-team group emits one CoinFlipResult covering the pair."""
        seeding = ["Alpha", "Beta", "Delta", "Gamma"]
        conds = _build_coin_flip_conds(seeding, [["Alpha", "Beta"]])
        assert len(conds) == 1

    def test_condition_reflects_seeding_order(self):
        """Winner is the team ranked higher in the seeding."""
        seeding = ["Alpha", "Beta", "Delta", "Gamma"]
        conds = _build_coin_flip_conds(seeding, [["Alpha", "Beta"]])
        assert conds[0] == CoinFlipResult(winner="Alpha", loser="Beta")

    def test_reverse_seeding_flips_winner(self):
        """When Beta is ranked higher, Beta is the winner."""
        seeding = ["Beta", "Alpha", "Delta", "Gamma"]
        conds = _build_coin_flip_conds(seeding, [["Alpha", "Beta"]])
        assert conds[0] == CoinFlipResult(winner="Beta", loser="Alpha")

    def test_three_team_group_produces_two_conditions(self):
        """A 3-team group emits 2 consecutive-pair CoinFlipResults."""
        seeding = ["Alpha", "Beta", "Delta", "Gamma"]
        conds = _build_coin_flip_conds(seeding, [["Alpha", "Beta", "Delta"]])
        assert len(conds) == 2
        assert conds[0] == CoinFlipResult(winner="Alpha", loser="Beta")
        assert conds[1] == CoinFlipResult(winner="Beta", loser="Delta")

    def test_empty_groups_produces_no_conditions(self):
        """With no flip groups, no CoinFlipResult conditions are emitted."""
        seeding = ["Alpha", "Beta", "Delta", "Gamma"]
        conds = _build_coin_flip_conds(seeding, [])
        assert conds == []


# ---------------------------------------------------------------------------
# Integration tests: build_scenario_atoms (Step 3b)
# ---------------------------------------------------------------------------


class TestBuildScenarioAtomsCoinFlip:
    """build_scenario_atoms emits coin-flip atoms for both playoff teams."""

    def test_alpha_has_atoms_at_both_seeds(self):
        """Alpha can win either seed → atoms exist at seeds 1 and 2."""
        assert 1 in _ATOMS.get("Alpha", {})
        assert 2 in _ATOMS.get("Alpha", {})

    def test_beta_has_atoms_at_both_seeds(self):
        """Beta can win either seed → atoms exist at seeds 1 and 2."""
        assert 1 in _ATOMS.get("Beta", {})
        assert 2 in _ATOMS.get("Beta", {})

    def test_alpha_seed1_atom_contains_coin_flip_result(self):
        """Alpha's seed-1 atoms each contain a CoinFlipResult condition."""
        for atom in _ATOMS["Alpha"][1]:
            assert any(isinstance(c, CoinFlipResult) for c in atom), (
                f"No CoinFlipResult in atom: {atom}"
            )

    def test_alpha_seed1_coin_flip_names_alpha_as_winner(self):
        """When Alpha wins seed 1, the CoinFlipResult has Alpha as winner."""
        for atom in _ATOMS["Alpha"][1]:
            flip_conds = [c for c in atom if isinstance(c, CoinFlipResult)]
            assert all(c.winner == "Alpha" for c in flip_conds)

    def test_beta_seed1_coin_flip_names_beta_as_winner(self):
        """When Beta wins seed 1, the CoinFlipResult has Beta as winner."""
        for atom in _ATOMS["Beta"][1]:
            flip_conds = [c for c in atom if isinstance(c, CoinFlipResult)]
            assert all(c.winner == "Beta" for c in flip_conds)

    def test_eliminated_teams_not_in_atoms(self):
        """Delta and Gamma have no seed-1 or seed-2 atoms."""
        for team in ("Delta", "Gamma"):
            assert 1 not in _ATOMS.get(team, {})
            assert 2 not in _ATOMS.get(team, {})


# ---------------------------------------------------------------------------
# Integration tests: enumerate_division_scenarios ("coinflip" branch)
# ---------------------------------------------------------------------------


class TestEnumerateDivisionScenariosCoinFlip:
    """enumerate_division_scenarios produces coinflip sub-scenarios."""

    def test_produces_four_scenarios(self):
        """2 masks × 2 flip outcomes = 4 scenarios total."""
        assert len(_SCENARIOS) == 4

    def test_all_scenarios_have_sub_labels(self):
        """All scenarios are sub-labeled (a/b) since they involve coin flips."""
        assert all(sc["sub_label"] != "" for sc in _SCENARIOS)

    def test_sub_labels_are_a_and_b_per_group(self):
        """Each scenario number has sub-labels 'a' and 'b'."""
        from collections import defaultdict
        by_num = defaultdict(list)
        for sc in _SCENARIOS:
            by_num[sc["scenario_num"]].append(sc["sub_label"])
        for num, labels in by_num.items():
            assert sorted(labels) == ["a", "b"], (
                f"Scenario {num} has unexpected labels: {labels}"
            )

    def test_conditions_atoms_contain_coin_flip_result(self):
        """Every scenario's conditions_atom includes a CoinFlipResult."""
        for sc in _SCENARIOS:
            atom = sc.get("conditions_atom")
            assert atom is not None, f"Scenario {sc['scenario_num']}{sc['sub_label']} has no atom"
            assert any(isinstance(c, CoinFlipResult) for c in atom), (
                f"No CoinFlipResult in scenario {sc['scenario_num']}{sc['sub_label']}: {atom}"
            )

    def test_alpha_and_beta_each_win_seed1_in_two_scenarios(self):
        """Alpha wins seed 1 in exactly 2 scenarios; Beta in exactly 2."""
        alpha_seed1 = sum(1 for sc in _SCENARIOS if sc["seeding"][0] == "Alpha")
        beta_seed1 = sum(1 for sc in _SCENARIOS if sc["seeding"][0] == "Beta")
        assert alpha_seed1 == 2
        assert beta_seed1 == 2


# ---------------------------------------------------------------------------
# Integration tests: determine_scenarios (_accumulate_slots with flip_groups)
# ---------------------------------------------------------------------------


class TestDetermineScenariosCoinFlip:
    """determine_scenarios correctly distributes weight across coin-flip permutations."""

    def test_coinflip_teams_identified(self):
        """Alpha and Beta are flagged as coin-flip teams."""
        assert "Alpha" in _r.coinflip_teams
        assert "Beta" in _r.coinflip_teams

    def test_denom_equals_two(self):
        """Two outcome masks → denom = 2."""
        assert _r.denom == pytest.approx(2.0)

    def test_alpha_first_count_is_one(self):
        """Alpha accumulates 1.0 first-seed count across both masks (0.5 each)."""
        assert _r.first_counts["Alpha"] == pytest.approx(1.0)

    def test_beta_first_count_is_one(self):
        """Beta accumulates 1.0 first-seed count across both masks (0.5 each)."""
        assert _r.first_counts["Beta"] == pytest.approx(1.0)

    def test_alpha_second_count_is_one(self):
        """Alpha accumulates 1.0 second-seed count across both masks (0.5 each)."""
        assert _r.second_counts["Alpha"] == pytest.approx(1.0)

    def test_beta_second_count_is_one(self):
        """Beta accumulates 1.0 second-seed count across both masks (0.5 each)."""
        assert _r.second_counts["Beta"] == pytest.approx(1.0)

    def test_eliminated_teams_have_zero_counts(self):
        """Delta and Gamma have no counts at any playoff seed."""
        for team in ("Delta", "Gamma"):
            assert _r.first_counts[team] == pytest.approx(0.0)
            assert _r.second_counts[team] == pytest.approx(0.0)

    def test_odds_are_fifty_fifty(self):
        """Each team has exactly 50% probability for each of seeds 1 and 2."""
        assert _ODDS["Alpha"].p1 == pytest.approx(0.5)
        assert _ODDS["Alpha"].p2 == pytest.approx(0.5)
        assert _ODDS["Beta"].p1 == pytest.approx(0.5)
        assert _ODDS["Beta"].p2 == pytest.approx(0.5)

    def test_playoff_probability_is_one(self):
        """Alpha and Beta are always in the playoffs."""
        assert _ODDS["Alpha"].p_playoffs == pytest.approx(1.0)
        assert _ODDS["Beta"].p_playoffs == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Integration tests: rendering (CoinFlipResult dispatch in _render_condition)
# ---------------------------------------------------------------------------


class TestRenderCoinFlipScenario:
    """render_team_scenarios surfaces 'wins coin flip vs' for flip-determined seeds."""

    def test_alpha_render_contains_coin_flip_phrasing(self):
        """Alpha's rendered output includes 'wins coin flip vs'."""
        output = render_team_scenarios("Alpha", _ATOMS)
        assert "wins coin flip vs" in output

    def test_beta_render_contains_coin_flip_phrasing(self):
        """Beta's rendered output includes 'wins coin flip vs'."""
        output = render_team_scenarios("Beta", _ATOMS)
        assert "wins coin flip vs" in output

    def test_alpha_seed1_shows_alpha_winning_flip(self):
        """Alpha's seed-1 section lists 'Alpha wins coin flip vs Beta'."""
        output = render_team_scenarios("Alpha", _ATOMS)
        assert "Alpha wins coin flip vs Beta" in output

    def test_alpha_seed2_shows_beta_winning_flip(self):
        """Alpha's seed-2 section lists 'Beta wins coin flip vs Alpha'."""
        output = render_team_scenarios("Alpha", _ATOMS)
        assert "Beta wins coin flip vs Alpha" in output

    def test_render_with_odds_shows_fifty_percent(self):
        """With 50/50 odds, both seed sections show 50.0%."""
        output = render_team_scenarios("Alpha", _ATOMS, odds=_ODDS)
        assert "(50.0%)" in output


# ---------------------------------------------------------------------------
# Precomputed path: enumerate_outcomes → build_scenario_atoms /
#                   enumerate_division_scenarios with coin-flip region
#
# Covers the `if precomputed is not None:` blocks in both consumers, including
# the coin-flip branch at lines ~1261-1262 (build_scenario_atoms) and the
# coin-flip metadata loop at lines ~1537-1542 (enumerate_division_scenarios).
# ---------------------------------------------------------------------------

_PRECOMPUTED = enumerate_outcomes(_TEAMS, _COMPLETED, _REMAINING)
_ATOMS_PRE = build_scenario_atoms(
    _TEAMS, _COMPLETED, _REMAINING, playoff_seeds=_PLAYOFF_SEEDS, precomputed=_PRECOMPUTED
)
_SCENARIOS_PRE = enumerate_division_scenarios(
    _TEAMS, _COMPLETED, _REMAINING,
    playoff_seeds=_PLAYOFF_SEEDS,
    scenario_atoms=_ATOMS_PRE,
    precomputed=_PRECOMPUTED,
)


class TestPrecomputedPathCoinFlip:
    """build_scenario_atoms and enumerate_division_scenarios give identical results
    when passed a precomputed EnumeratedOutcomes for a coin-flip region."""

    def test_precomputed_atoms_match_direct_atoms(self):
        """Alpha's seed-1 atom count is the same via precomputed and direct paths."""
        assert len(_ATOMS_PRE["Alpha"][1]) == len(_ATOMS["Alpha"][1])
        assert len(_ATOMS_PRE["Beta"][2]) == len(_ATOMS["Beta"][2])

    def test_precomputed_atoms_contain_coin_flip_result(self):
        """Alpha's seed-1 atoms (precomputed path) each have a CoinFlipResult."""
        for atom in _ATOMS_PRE["Alpha"][1]:
            assert any(isinstance(c, CoinFlipResult) for c in atom), (
                f"No CoinFlipResult in precomputed atom: {atom}"
            )

    def test_precomputed_scenario_count_matches(self):
        """Precomputed path produces the same number of scenarios as direct path."""
        assert len(_SCENARIOS_PRE) == len(_SCENARIOS)

    def test_precomputed_scenarios_have_coin_flip_conditions(self):
        """Every scenario from the precomputed path includes a CoinFlipResult."""
        for sc in _SCENARIOS_PRE:
            atom = sc.get("conditions_atom")
            assert atom is not None, (
                f"Precomputed scenario {sc['scenario_num']}{sc['sub_label']} has no atom"
            )
            assert any(isinstance(c, CoinFlipResult) for c in atom), (
                f"No CoinFlipResult in precomputed scenario conditions: {atom}"
            )

    def test_precomputed_seedings_match_direct(self):
        """The set of seedings produced matches between precomputed and direct paths."""
        direct_seedings = {
            (sc["scenario_num"], sc["sub_label"]): tuple(sc["seeding"])
            for sc in _SCENARIOS
        }
        pre_seedings = {
            (sc["scenario_num"], sc["sub_label"]): tuple(sc["seeding"])
            for sc in _SCENARIOS_PRE
        }
        assert direct_seedings == pre_seedings

    def test_enumerate_outcomes_coin_flips_populated(self):
        """enumerate_outcomes records coin flips for both masks in this fixture."""
        assert len(_PRECOMPUTED.coin_flips) == 2  # both masks (Delta wins / Gamma wins)
        for mask_flips in _PRECOMPUTED.coin_flips.values():
            assert any("Alpha" in g and "Beta" in g for g in mask_flips)
