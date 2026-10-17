"""Tests for coin-flip scenario paths using a synthetic 4-team fixture.

Fixture: Alpha and Beta each beat Gamma and Delta (identical 2-0 records, no
H2H game between them).  The only remaining game is Delta vs Gamma — it doesn't
affect Alpha or Beta at all.  Therefore:
  - For both outcome masks (Delta wins / Gamma wins), Alpha and Beta exhaust all
    seven deterministic tiebreaker steps without being separated → coin flip.
  - The coin flip is always relevant (both teams are within the 2-seed playoff
    cutoff).

This fixture exercises:
  build_scenario_atoms giving each team its place in the flip (scenario_viewer.py)
  enumerate_division_scenarios leaving a certain coin flip to the flip (scenario_viewer.py)
  TiebreakPlace dispatch in _render_condition (scenario_renderer.py)
  _accumulate_slots with flip_groups (scenarios.py lines 105–134)
"""

import pytest

from backend.helpers.data_classes import CoinFlipResult, CompletedGame, RemainingGame, TiebreakPlace
from backend.helpers.scenario_renderer import render_team_scenarios
from backend.helpers.scenario_viewer import (
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
    CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=10, pa_a=14, pa_b=24),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=10, pa_a=14, pa_b=24),
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
    _r.first_counts,
    _r.second_counts,
    _r.third_counts,
    _r.fourth_counts,
    _r.denom,
)


# ---------------------------------------------------------------------------
# Integration tests: build_scenario_atoms (Step 3b)
# ---------------------------------------------------------------------------


class TestBuildScenarioAtomsCoinFlip:
    """build_scenario_atoms gives both playoff teams each place, by their place in the coin flip."""

    def test_alpha_has_atoms_at_both_seeds(self):
        """Alpha can win either seed → atoms exist at seeds 1 and 2."""
        assert 1 in _ATOMS.get("Alpha", {})
        assert 2 in _ATOMS.get("Alpha", {})

    def test_beta_has_atoms_at_both_seeds(self):
        """Beta can win either seed → atoms exist at seeds 1 and 2."""
        assert 1 in _ATOMS.get("Beta", {})
        assert 2 in _ATOMS.get("Beta", {})

    def test_alpha_seed1_atom_is_first_place_in_the_flip(self):
        """Alpha's seed-1 atom is its first place in the Alpha/Beta coin flip (step 6), nothing else."""
        assert _ATOMS["Alpha"][1] == [[TiebreakPlace("Alpha", 1, ("Alpha", "Beta"), 6)]]

    def test_alpha_seed2_atom_is_second_place_in_the_flip(self):
        """Alpha's seed-2 atom is its second place in the coin flip."""
        assert _ATOMS["Alpha"][2] == [[TiebreakPlace("Alpha", 2, ("Alpha", "Beta"), 6)]]

    def test_beta_seed1_atom_names_beta(self):
        """When Beta takes seed 1, the condition is Beta's first place in the flip."""
        assert _ATOMS["Beta"][1] == [[TiebreakPlace("Beta", 1, ("Alpha", "Beta"), 6)]]

    def test_no_coin_flip_results(self):
        """The old per-result CoinFlipResult atoms are gone: the flip is a place in the tie."""
        assert not any(
            isinstance(c, CoinFlipResult) for seeds in _ATOMS.values() for al in seeds.values() for a in al for c in a
        )

    def test_eliminated_teams_not_in_atoms(self):
        """Delta and Gamma have no seed-1 or seed-2 atoms."""
        for team in ("Delta", "Gamma"):
            assert 1 not in _ATOMS.get(team, {})
            assert 2 not in _ATOMS.get(team, {})


# ---------------------------------------------------------------------------
# Integration tests: enumerate_division_scenarios ("coinflip" branch)
# ---------------------------------------------------------------------------


class TestEnumerateDivisionScenariosCoinFlip:
    """enumerate_division_scenarios leaves a genuine coin flip to the flip, without guessing it.

    Alpha and Beta have finished their region games, so their points allowed are final and
    equal: nothing left to play can separate them, and it's a coin flip for certain.
    """

    def test_one_scenario_whatever_the_delta_gamma_result(self):
        """Delta-Gamma decides nothing that's shown (both are out), so the two masks are one scenario."""
        assert len(_SCENARIOS) == 1
        assert _SCENARIOS[0]["game_winners"] == [] and _SCENARIOS[0]["sub_label"] == ""

    def test_the_tie_is_left_to_a_coin_flip(self):
        """Step 6 (the coin flip) for Alpha and Beta, not an order made up for them."""
        assert _SCENARIOS[0]["open_groups"] == [(6, ("Alpha", "Beta"))]
        assert set(_SCENARIOS[0]["seeding"][:2]) == {"Alpha", "Beta"}

    def test_title_says_a_coin_flip_decides(self):
        from backend.helpers.scenario_renderer import render_scenario_title

        assert render_scenario_title(_SCENARIOS[0]) == (
            "Alpha and Beta are level on every tiebreaker: a coin flip decides their order"
        )


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
    """render_team_scenarios says a flip-determined seed turns on the team's place in the coin flip."""

    def test_alpha_seed1_shows_alpha_ahead_on_the_flip(self):
        """Alpha's seed-1 section says Alpha finishes ahead of Beta on the coin flip."""
        output = render_team_scenarios("Alpha", _ATOMS)
        assert "Alpha finishes ahead of Beta in their tie, which a coin flip decides" in output

    def test_alpha_seed2_shows_alpha_behind_on_the_flip(self):
        """Alpha's seed-2 section says Alpha finishes behind Beta on the coin flip."""
        output = render_team_scenarios("Alpha", _ATOMS)
        assert "Alpha finishes behind Beta in their tie, which a coin flip decides" in output

    def test_beta_render_names_beta(self):
        """Beta's rendered output is about Beta's place in the flip."""
        output = render_team_scenarios("Beta", _ATOMS)
        assert "Beta finishes ahead of Alpha in their tie, which a coin flip decides" in output

    def test_render_with_odds_shows_fifty_percent(self):
        """With 50/50 odds, both seed sections show 50.0%."""
        output = render_team_scenarios("Alpha", _ATOMS, odds=_ODDS)
        assert "(50.0%)" in output


# ---------------------------------------------------------------------------
# Precomputed path: enumerate_outcomes → build_scenario_atoms /
#                   enumerate_division_scenarios with coin-flip region
#
# Passing a precomputed EnumeratedOutcomes gives the same atoms and scenarios.
# ---------------------------------------------------------------------------

_PRECOMPUTED = enumerate_outcomes(_TEAMS, _COMPLETED, _REMAINING)
_ATOMS_PRE = build_scenario_atoms(
    _TEAMS, _COMPLETED, _REMAINING, playoff_seeds=_PLAYOFF_SEEDS, precomputed=_PRECOMPUTED
)
_SCENARIOS_PRE = enumerate_division_scenarios(
    _TEAMS,
    _COMPLETED,
    _REMAINING,
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

    def test_precomputed_atoms_match_direct_exactly(self):
        """The precomputed path gives the same atoms, the place in the flip included."""
        assert _ATOMS_PRE == _ATOMS

    def test_precomputed_scenario_count_matches(self):
        """Precomputed path produces the same number of scenarios as direct path."""
        assert len(_SCENARIOS_PRE) == len(_SCENARIOS)

    def test_precomputed_scenarios_leave_the_coin_flip_open(self):
        """The precomputed path gives the same coin-flip scenario."""
        assert [sc["open_groups"] for sc in _SCENARIOS_PRE] == [[(6, ("Alpha", "Beta"))]]

    def test_precomputed_seedings_match_direct(self):
        """The set of seedings produced matches between precomputed and direct paths."""
        direct_seedings = {(sc["scenario_num"], sc["sub_label"]): tuple(sc["seeding"]) for sc in _SCENARIOS}
        pre_seedings = {(sc["scenario_num"], sc["sub_label"]): tuple(sc["seeding"]) for sc in _SCENARIOS_PRE}
        assert direct_seedings == pre_seedings

    def test_enumerate_outcomes_coin_flips_populated(self):
        """enumerate_outcomes records coin flips for both masks in this fixture."""
        assert len(_PRECOMPUTED.coin_flips) == 2  # both masks (Delta wins / Gamma wins)
        for mask_flips in _PRECOMPUTED.coin_flips.values():
            assert any("Alpha" in g and "Beta" in g for g in mask_flips)


# ---------------------------------------------------------------------------
# Below-cutoff coin-flip fixture
# ---------------------------------------------------------------------------
#
# Fixture design (lines 1307→1305 and 1540→1534 in scenario_viewer.py):
#   Alpha and Beta each beat Gamma and Delta.  The only remaining game is
#   Alpha vs Beta — whichever team wins is clearly seed 1; the other is seed 2.
#   Gamma and Delta both end at 0-2 with identical margins and no H2H game,
#   so they tie on all 7 tiebreaker steps → coin flip between them.
#
#   With playoff_seeds=2, Gamma and Delta are BOTH outside the playoff cutoff
#   regardless of the coin-flip outcome.  _relevant_flip_groups therefore
#   returns [] for both masks, and the `if relevant:` guard at lines 1307
#   (build_scenario_atoms) and 1540 (enumerate_division_scenarios) evaluates
#   to False — the previously uncovered branch.
#
#   Expected behavior:
#     • No sub-scenarios (no "a"/"b" labels): the below-cutoff flip does not
#       expand into multiple scenario variants.
#     • Gamma and Delta appear in seedings at positions 3 and 4 (alphabetical
#       proxy ordering) but have no atoms and no CoinFlipResult conditions.
#     • Alpha and Beta get standard game-winner atoms for the A-vs-B game.

_BC_TEAMS = ["Alpha", "Beta", "Delta", "Gamma"]
_BC_PLAYOFF_SEEDS = 2

# Alpha and Beta each beat Gamma and Delta by the same margin.
# pa_a=14 → alpha allowed 14 points; pa_b=21 → gamma/delta allowed 21 points.
_BC_COMPLETED = [
    CompletedGame(a="Alpha", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Alpha", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Beta", b="Gamma", res_a=1, pd_a=7, pa_a=14, pa_b=21),
    CompletedGame(a="Beta", b="Delta", res_a=1, pd_a=7, pa_a=14, pa_b=21),
]

# The only remaining game: Alpha vs Beta.  Gamma and Delta don't play it, so
# their standings (0-2, same margins) are unaffected by the outcome or margin.
_BC_REMAINING = [RemainingGame(a="Alpha", b="Beta")]

_BC_ATOMS = build_scenario_atoms(_BC_TEAMS, _BC_COMPLETED, _BC_REMAINING, playoff_seeds=_BC_PLAYOFF_SEEDS)
_BC_SCENARIOS = enumerate_division_scenarios(
    _BC_TEAMS,
    _BC_COMPLETED,
    _BC_REMAINING,
    playoff_seeds=_BC_PLAYOFF_SEEDS,
    scenario_atoms=_BC_ATOMS,
)
_BC_PRECOMPUTED = enumerate_outcomes(_BC_TEAMS, _BC_COMPLETED, _BC_REMAINING)
_BC_SCENARIOS_PRE = enumerate_division_scenarios(
    _BC_TEAMS,
    _BC_COMPLETED,
    _BC_REMAINING,
    playoff_seeds=_BC_PLAYOFF_SEEDS,
    scenario_atoms=build_scenario_atoms(
        _BC_TEAMS,
        _BC_COMPLETED,
        _BC_REMAINING,
        playoff_seeds=_BC_PLAYOFF_SEEDS,
        precomputed=_BC_PRECOMPUTED,
    ),
    precomputed=_BC_PRECOMPUTED,
)


class TestBelowCutoffCoinFlipAtoms:
    """build_scenario_atoms: below-cutoff flip does not produce CoinFlipResult atoms."""

    def test_alpha_has_seed1_and_seed2_atoms(self):
        """Alpha can finish 1st or 2nd → atoms at seeds 1 and 2."""
        assert 1 in _BC_ATOMS.get("Alpha", {})
        assert 2 in _BC_ATOMS.get("Alpha", {})

    def test_beta_has_seed1_and_seed2_atoms(self):
        """Beta can finish 1st or 2nd → atoms at seeds 1 and 2."""
        assert 1 in _BC_ATOMS.get("Beta", {})
        assert 2 in _BC_ATOMS.get("Beta", {})

    def test_delta_has_no_playoff_atoms(self):
        """Delta finishes at seed 3 — outside playoff_seeds=2 → no atoms."""
        for seed in (1, 2):
            assert seed not in _BC_ATOMS.get("Delta", {})

    def test_gamma_has_no_playoff_atoms(self):
        """Gamma finishes at seed 4 — outside playoff_seeds=2 → no atoms."""
        for seed in (1, 2):
            assert seed not in _BC_ATOMS.get("Gamma", {})

    def test_alpha_seed1_has_no_coin_flip_result(self):
        """Alpha's seed-1 atom reflects winning the Alpha/Beta game — no CoinFlipResult."""
        for atom in _BC_ATOMS["Alpha"][1]:
            assert not any(isinstance(c, CoinFlipResult) for c in atom), (
                f"Unexpected CoinFlipResult in below-cutoff fixture atom: {atom}"
            )

    def test_beta_seed1_has_no_coin_flip_result(self):
        """Beta's seed-1 atom reflects winning the Alpha/Beta game — no CoinFlipResult."""
        for atom in _BC_ATOMS["Beta"][1]:
            assert not any(isinstance(c, CoinFlipResult) for c in atom), (
                f"Unexpected CoinFlipResult in below-cutoff fixture atom: {atom}"
            )


class TestBelowCutoffCoinFlipScenarios:
    """enumerate_division_scenarios: below-cutoff flip produces no sub-scenario expansion."""

    def test_produces_exactly_two_scenarios(self):
        """Two outcome masks (Alpha wins / Beta wins) → exactly 2 scenarios."""
        assert len(_BC_SCENARIOS) == 2

    def test_no_sub_labels(self):
        """No sub-labels: the below-cutoff flip does not generate 'a'/'b' variants."""
        assert all(sc["sub_label"] == "" for sc in _BC_SCENARIOS)

    def test_alpha_and_beta_each_appear_at_seed1_once(self):
        """Alpha is seed 1 in one scenario; Beta is seed 1 in the other."""
        seed1_teams = {sc["seeding"][0] for sc in _BC_SCENARIOS}
        assert seed1_teams == {"Alpha", "Beta"}

    def test_gamma_and_delta_never_at_seed1_or_seed2(self):
        """Gamma and Delta are always at positions 3 and 4 in every scenario."""
        for sc in _BC_SCENARIOS:
            assert sc["seeding"][0] not in ("Gamma", "Delta")
            assert sc["seeding"][1] not in ("Gamma", "Delta")

    def test_delta_before_gamma_alphabetical_proxy(self):
        """Tied Gamma/Delta are resolved alphabetically: Delta (index 2) before Gamma (3)."""
        for sc in _BC_SCENARIOS:
            assert sc["seeding"][2] == "Delta"
            assert sc["seeding"][3] == "Gamma"

    def test_precomputed_path_produces_same_scenario_count(self):
        """Precomputed path agrees: 2 scenarios with no sub-labels."""
        assert len(_BC_SCENARIOS_PRE) == 2
        assert all(sc["sub_label"] == "" for sc in _BC_SCENARIOS_PRE)

    def test_precomputed_path_seedings_match(self):
        """Precomputed and direct paths produce identical seedings."""
        direct = {sc["scenario_num"]: tuple(sc["seeding"]) for sc in _BC_SCENARIOS}
        pre = {sc["scenario_num"]: tuple(sc["seeding"]) for sc in _BC_SCENARIOS_PRE}
        assert direct == pre
