"""Tests for scenario_viewer: enumerate_division_scenarios and the condition renderers."""

from itertools import product

from backend.helpers.data_classes import (
    CompletedGame,
    FormatSlot,
    GameResult,
    MarginCondition,
    RemainingGame,
)
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import _render_margin_condition
from backend.helpers.scenario_viewer import (
    _find_tiebreaker_groups,
    _format_team_list,
    _minimize_game_winner_atom,
    _simplify_atom_list,
    build_pre_playoff_home_scenarios,
    build_scenario_atoms,
    enumerate_division_scenarios,
    enumerate_outcomes,
    render_scenarios,
)
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.playoff_brackets_2025 import SLOTS_5A_7A_2025
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_completed_games_full,
    expected_3_7a_remaining_games,
    expected_3_7a_remaining_games_full,
    expected_3_7a_scenarios,
    teams_3_7a,
)
from backend.tests.scenario_coverage import coverage_problems, team_path_problems

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PA_WIN = 14
_BASE_MARGIN_DEFAULT = 7
_REMAINING = expected_3_7a_remaining_games
_PAIRS = [(rg.a, rg.b) for rg in _REMAINING]

# Computed once at module level — reused by multiple tests to avoid redundant builds.
_ATOMS_3_7A = build_scenario_atoms(teams_3_7a, expected_3_7a_completed_games, _REMAINING)
_SCENARIOS_3_7A = enumerate_division_scenarios(
    teams_3_7a, expected_3_7a_completed_games, _REMAINING, scenario_atoms=_ATOMS_3_7A
)


def _all_outcome_branches():
    """Yield (outcome_mask, margins) for all 8 × 12³ = 13,824 combinations."""
    for mask in range(1 << len(_REMAINING)):
        for m0, m1, m2 in product(range(1, 13), repeat=3):
            yield mask, {_PAIRS[0]: m0, _PAIRS[1]: m1, _PAIRS[2]: m2}


def _atom_satisfied(atom, mask, margins):
    """Return True if every condition in the atom is satisfied by the given outcome."""
    return all(cond.satisfied_by(mask, margins, _REMAINING) for cond in atom)


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — structural tests
# ---------------------------------------------------------------------------


def test_3_7a_scenario_count():
    """3-7A lists 6 scenarios: one per set of winners that decides the seeding.

    With Brandon, Pearl and Northwest Rankin all winning, five teams tie and their order has 12
    possible top-4 finishes, more than are listed one by one, so that's a single scenario leaving
    the tie to the tiebreaker.
    """
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    assert len(scenarios) == 6


def test_3_7a_five_way_tie_left_to_the_tiebreaker():
    """The five-way tie is one scenario naming the tie (the four whose places vary; Brandon is always
    fifth), with no order or margins made up for it."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    assert not [sc for sc in scenarios if sc["sub_label"]]
    sc4 = next(sc for sc in scenarios if sc["scenario_num"] == 4)
    assert sc4["open_groups"] == [(3, ("Northwest Rankin", "Oak Grove", "Pearl", "Petal"))]
    assert sc4["conditions_atom"] is None


def test_3_7a_grouped_scenarios_omit_irrelevant_game():
    """Scenarios 1 and 2 (Petal wins NWR game) omit the Brandon/Meridian game."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sc1 = scenarios[0]  # Petal #1, Pearl #2
    sc2 = scenarios[1]  # Petal #1, OG #2

    assert sc1["scenario_num"] == 1 and sc1["sub_label"] == ""
    assert sc2["scenario_num"] == 2 and sc2["sub_label"] == ""

    # Only 2 game conditions each (Brandon/Meridian omitted)
    assert len(sc1["game_winners"]) == 2
    assert len(sc2["game_winners"]) == 2

    # Petal wins and NWR loses in both
    assert ("Petal", "Northwest Rankin") in sc1["game_winners"]
    assert ("Petal", "Northwest Rankin") in sc2["game_winners"]

    # They differ in the Oak Grove / Pearl game
    og_pearl_1 = next(gw for gw in sc1["game_winners"] if set(gw) == {"Oak Grove", "Pearl"})
    og_pearl_2 = next(gw for gw in sc2["game_winners"] if set(gw) == {"Oak Grove", "Pearl"})
    assert og_pearl_1 != og_pearl_2


def test_3_7a_deterministic_scenarios_correct_seedings():
    """The 5 deterministic scenarios have the expected top-4 seedings."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    single = [sc for sc in scenarios if not sc["sub_label"]]
    seedings = {sc["scenario_num"]: sc["seeding"][:4] for sc in single}

    assert seedings[1] == ("Petal", "Pearl", "Oak Grove", "Brandon")
    assert seedings[2] == ("Petal", "Oak Grove", "Brandon", "Northwest Rankin")
    assert seedings[3] == ("Northwest Rankin", "Pearl", "Petal", "Oak Grove")
    assert seedings[5] == ("Oak Grove", "Northwest Rankin", "Petal", "Brandon")
    assert seedings[6] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — backward coverage
# ---------------------------------------------------------------------------


def test_3_7a_every_outcome_covered_by_exactly_one_scenario():
    """Every (mask, margin) combination matches a scenario, and every scenario it matches agrees."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    report = coverage_problems(teams_3_7a, expected_3_7a_completed_games, _REMAINING, scenarios)
    assert report.ok, report.summary(_REMAINING)


def test_3_7a_conditions_match_seedings():
    """For each sub-scenario with an atom, a sample margin satisfying the atom produces the right seeding."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    for sc in scenarios:
        atom = sc.get("conditions_atom")
        if atom is None:
            continue
        # Find a satisfying (mask, margins) by exhaustive search over small range
        # Infer mask from game_winners: bit i=1 if remaining[i].a wins
        winner_set = {gw[0] for gw in sc["game_winners"]}
        candidate_mask = 0
        for i, rg in enumerate(_REMAINING):
            if rg.a in winner_set:
                candidate_mask |= 1 << i

        found = False
        for m0, m1, m2 in product(range(1, 13), repeat=3):
            margins = {_PAIRS[0]: m0, _PAIRS[1]: m1, _PAIRS[2]: m2}
            if _atom_satisfied(atom, candidate_mask, margins):
                order = resolve_standings_for_mask(
                    teams_3_7a,
                    expected_3_7a_completed_games,
                    _REMAINING,
                    candidate_mask,
                    margins,
                    _BASE_MARGIN_DEFAULT,
                    _PA_WIN,
                )
                assert tuple(order) == sc["seeding"], (
                    f"Scenario {sc['scenario_num']}{sc['sub_label']}: "
                    f"atom satisfied by mask={candidate_mask} margins={margins} "
                    f"but seeding is {order}, expected {sc['seeding']}"
                )
                found = True
                break
        assert found, f"Scenario {sc['scenario_num']}{sc['sub_label']}: no satisfying (mask, margins) found for atom"


# ---------------------------------------------------------------------------
# No remaining games — full season deterministic case
# ---------------------------------------------------------------------------


def test_full_season_single_scenario():
    """With 0 remaining games, exactly 1 scenario is returned with no game conditions."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games_full,
        expected_3_7a_remaining_games_full,
    )
    assert len(scenarios) == 1
    sc = scenarios[0]
    assert sc["scenario_num"] == 1
    assert sc["sub_label"] == ""
    assert sc["game_winners"] == []
    assert sc["seeding"][:4] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")


# ---------------------------------------------------------------------------
# MarginCondition op="==" rendering (covers new code paths)
# ---------------------------------------------------------------------------

_NWR_PET = ("Northwest Rankin", "Petal")
_OG_PRL = ("Oak Grove", "Pearl")
_DUMMY_ATOM = [GameResult("Brandon", "Meridian")]


def test_render_margin_condition_sum_eq():
    """op='==' with 2 addends renders as 'combined total exactly N'."""
    mc = MarginCondition(add=(_NWR_PET, _OG_PRL), sub=(), op="==", threshold=10)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Northwest Rankin/Petal's and Oak Grove/Pearl's winning margins add up to exactly 10 (a margin over 12 counts as 12)"


def test_render_margin_condition_diff_eq_positive():
    """op='==' diff with positive t renders as 'A exceeds B by exactly N'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=2)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Northwest Rankin/Petal wins by exactly 2 more points than Oak Grove/Pearl (a margin over 12 counts as 12)"


def test_render_margin_condition_diff_eq_negative():
    """op='==' diff with negative t renders as 'B exceeds A by exactly N'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=-3)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Oak Grove/Pearl wins by exactly 3 more points than Northwest Rankin/Petal (a margin over 12 counts as 12)"


def test_render_margin_condition_diff_eq_zero():
    """op='==' diff with t=0 renders as 'A and B win by the same margin'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=0)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Northwest Rankin/Petal and Oak Grove/Pearl win by the same margin (a margin over 12 counts as 12)"


def test_margin_condition_satisfied_by_eq_op():
    """MarginCondition with op='==' is satisfied only when the value equals the threshold."""
    mc = MarginCondition(add=(_NWR_PET, _OG_PRL), sub=(), op="==", threshold=10)
    margins_eq = {("Northwest Rankin", "Petal"): 5, ("Oak Grove", "Pearl"): 5}
    margins_ne = {("Northwest Rankin", "Petal"): 5, ("Oak Grove", "Pearl"): 6}
    assert mc.satisfied_by(0, margins_eq, _REMAINING) is True
    assert mc.satisfied_by(0, margins_ne, _REMAINING) is False


# ---------------------------------------------------------------------------
# Full render snapshot — 3-7A division scenarios (algorithmic atoms)
# ---------------------------------------------------------------------------

_EXPECTED_3_7A_RENDER = """\
Scenario 1: Pearl beats Oak Grove AND Petal beats Northwest Rankin
1. Petal
2. Pearl
3. Oak Grove
4. Brandon
Eliminated: Meridian, Northwest Rankin

Scenario 2: Oak Grove beats Pearl AND Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl

Scenario 3: Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4: Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
1-4. Northwest Rankin, Oak Grove, Pearl, and Petal: order decided by the tiebreaker (point differential, then fewest points allowed)
Eliminated: Brandon, Meridian

Scenario 5: Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Brandon
Eliminated: Meridian, Pearl

Scenario 6: Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl"""


# ---------------------------------------------------------------------------
# build_scenario_atoms — end-to-end quality tests
#
# These tests exercise the full pipeline: build_scenario_atoms → enumerate →
# render.  They are the regression guard for output quality: the old
# exact-margin-sample implementation would have produced "by exactly N"
# wording (point samples) instead of human-readable ranges.
# ---------------------------------------------------------------------------


class TestBuildScenarioAtoms37A:
    """Tests that build_scenario_atoms produces correct, human-readable atoms for 3-7A."""

    def _build(self):
        """Return build_scenario_atoms output for the 3-7A pre-final-week fixture."""
        return _ATOMS_3_7A

    def _scenarios(self):
        """Return enumerate_division_scenarios output built from algorithmic atoms."""
        return _SCENARIOS_3_7A

    def test_produces_6_scenarios(self):
        """build_scenario_atoms atoms yield the same 6 scenarios (scenarios don't depend on atoms)."""
        assert len(self._scenarios()) == 6

    def test_five_way_tie_is_one_scenario(self):
        """The five-way tie is left to the tiebreaker rather than split into sub-scenarios."""
        assert not [sc for sc in self._scenarios() if sc["sub_label"]]
        assert [sc["open_groups"] for sc in self._scenarios() if sc["scenario_num"] == 4] == [
            [(3, ("Northwest Rankin", "Oak Grove", "Pearl", "Petal"))]
        ]

    def test_render_uses_range_descriptions_not_exact_values(self):
        """Rendered output uses range-based wording, not per-game point samples.

        The old exact-margin-sample implementation produced "Team A beats Team B by exactly N"
        for per-game GameResult conditions (unit-width intervals).  The correct output uses
        ranges like "by 1–5" or "by 6 or more".  Joint MarginCondition rendering ("margin
        exceeds X by exactly 2") is still allowed — we only reject point-sample GameResults.
        """
        output = render_scenarios(self._scenarios())
        for line in output.splitlines():
            if not line.startswith("Scenario 4"):
                continue
            # Split on " AND " so each clause is checked individually.
            # A per-game point-sample clause looks like "Team A beats Team B by exactly N".
            # MarginCondition clauses look like "X wins by exactly N more points than Y" — allowed.
            clauses = line.split(" AND ")
            for clause in clauses:
                if "beats" in clause and "by exactly" in clause:
                    raise AssertionError(
                        f"Per-game point-sample condition found (expected a range): {clause!r}\nFull line: {line!r}"
                    )

    def test_render_contains_joint_constraints(self):
        """The five-way tie renders as left to the tiebreaker, not as margin arithmetic."""
        output = render_scenarios(self._scenarios())
        assert "order decided by the tiebreaker (point differential, then fewest points allowed)" in output
        assert "combined total" not in output and "margin exceeds" not in output

    def test_render_scenario_1_correct(self):
        """Scenario 1 is deterministic: Pearl wins, Petal wins, Brandon game irrelevant."""
        output = render_scenarios(self._scenarios())
        lines = output.splitlines()
        sc1_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Scenario 1:"))
        sc1_header = lines[sc1_idx]
        assert "Pearl beats Oak Grove" in sc1_header
        assert "Petal beats Northwest Rankin" in sc1_header
        assert "1. Petal" in lines[sc1_idx + 1]
        assert "2. Pearl" in lines[sc1_idx + 2]

    def test_render_scenario_6_correct(self):
        """Scenario 6 is deterministic: Brandon wins, Oak Grove wins, NWR wins."""
        output = render_scenarios(self._scenarios())
        lines = output.splitlines()
        sc6_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Scenario 6:"))
        sc6_header = lines[sc6_idx]
        assert "Brandon beats Meridian" in sc6_header
        assert "Oak Grove beats Pearl" in sc6_header
        assert "Northwest Rankin beats Petal" in sc6_header
        assert "1. Oak Grove" in lines[sc6_idx + 1]

    def test_backward_coverage_with_built_atoms(self):
        """Every (mask, margin) combo is covered, and correctly, when using built atoms."""
        report = coverage_problems(teams_3_7a, expected_3_7a_completed_games, _REMAINING, self._scenarios())
        assert report.ok, report.summary(_REMAINING)

    def test_nwr_petal_game_range_not_all_exact(self):
        """The NWR/Petal game in mask=5 sub-scenarios uses ranges, not point samples."""
        atoms = self._build()
        nwr = "Northwest Rankin"
        pet = "Petal"
        # In mask=5, NWR wins the Petal game (bit 1 = NWR wins in remaining index 1)
        nwr_at_1 = atoms.get(nwr, {}).get(1, [])
        for atom in nwr_at_1:
            for cond in atom:
                if isinstance(cond, GameResult) and cond.winner == nwr and cond.loser == pet:
                    # Should have a range (max_margin - min_margin > 1) or be unbounded
                    span = (cond.max_margin - cond.min_margin) if cond.max_margin else 12
                    assert span > 1, f"NWR seed-1 atom has point-sample GameResult: {cond}. Expected a margin range."


# ---------------------------------------------------------------------------
# Soundness: atoms point to the right seeding for EVERY satisfying outcome
# ---------------------------------------------------------------------------


def test_division_scenario_atom_soundness():
    """For every (mask, margins) satisfying a conditions_atom, resolve_standings
    produces exactly that scenario's seeding.

    This is the soundness complement to test_backward_coverage_with_built_atoms:
    completeness says every outcome maps to *some* scenario seeding;
    soundness says every outcome covered by an atom maps to the *right* seeding.
    An over-broad atom would pass the completeness test but fail here.
    """
    from collections import defaultdict

    scenarios = _SCENARIOS_3_7A

    def _scenario_mask(sc):
        """Return the outcome mask implied by a scenario's game_winners list."""
        winner_set = {gw[0] for gw in sc["game_winners"]}
        mask = 0
        for i, rg in enumerate(_REMAINING):
            if rg.a in winner_set:
                mask |= 1 << i
        return mask

    # Only margin-sensitive scenarios have conditions_atoms worth checking
    mask_scenarios: dict = defaultdict(list)
    for sc in scenarios:
        if sc.get("conditions_atom") is not None:
            mask_scenarios[_scenario_mask(sc)].append(sc)

    failures = []
    for mask, margins in _all_outcome_branches():
        for sc in mask_scenarios.get(mask, []):
            if not _atom_satisfied(sc["conditions_atom"], mask, margins):
                continue
            actual = resolve_standings_for_mask(
                teams_3_7a,
                expected_3_7a_completed_games,
                _REMAINING,
                mask,
                margins,
                _BASE_MARGIN_DEFAULT,
                _PA_WIN,
            )
            if tuple(actual) != sc["seeding"]:
                failures.append(
                    f"Scenario {sc['scenario_num']}{sc['sub_label']}: "
                    f"mask={mask} margins={margins} → got {tuple(actual)}, "
                    f"expected {sc['seeding']}"
                )

    assert not failures, f"{len(failures)} soundness violations:\n" + "\n".join(failures[:5])


def test_per_team_atoms_consistent_with_division_scenarios():
    """For every (mask, margins), each team's per-team atoms are right and cover the outcome.

    Every path whose conditions can hold gives a place the team can take there, and every place
    it can take has a path (see ``team_path_problems``), so the per-team format agrees with the
    division-scenario format it's read off.
    """
    report = team_path_problems(teams_3_7a, expected_3_7a_completed_games, _REMAINING, _ATOMS_3_7A)
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# enumerate_outcomes / precomputed path regression tests
#
# Uses Region 4-4A midseason (R=4) — has both margin-sensitive and
# non-sensitive masks plus constrained elimination atoms.
# ---------------------------------------------------------------------------

_4_4A = REGION_RESULTS_2025[(4, 4)]
_4_4A_CUTOFF = "2025-10-17"
_4_4A_ALL = _4_4A["games"]
_4_4A_TEAMS = teams_from_games(_4_4A_ALL)
_4_4A_COMPLETED = get_completed_games(expand_results([g for g in _4_4A_ALL if g["date"] <= _4_4A_CUTOFF]))
_4_4A_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _4_4A_ALL if g["date"] > _4_4A_CUTOFF]

# Compute both paths once at module level for efficiency.
_ATOMS_DIRECT = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)
_SCENARIOS_DIRECT = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)

_PRECOMPUTED = enumerate_outcomes(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)
_ATOMS_PRE = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED)
_SCENARIOS_PRE = enumerate_division_scenarios(
    _4_4A_TEAMS,
    _4_4A_COMPLETED,
    _4_4A_REMAINING,
    scenario_atoms=_ATOMS_PRE,
    precomputed=_PRECOMPUTED,
)


def test_precomputed_atoms_teams_match():
    """Precomputed path produces atoms for the same set of teams."""
    assert set(_ATOMS_PRE.keys()) == set(_ATOMS_DIRECT.keys())


def test_precomputed_atoms_seeds_match():
    """Precomputed path produces atoms for the same seeds per team."""
    for team in _ATOMS_DIRECT:
        assert set(_ATOMS_PRE[team].keys()) == set(_ATOMS_DIRECT[team].keys()), f"{team}: seed keys differ"


def test_precomputed_atoms_count_match():
    """Precomputed path produces the same number of atoms per (team, seed)."""
    for team in _ATOMS_DIRECT:
        for seed in _ATOMS_DIRECT[team]:
            assert len(_ATOMS_PRE[team][seed]) == len(_ATOMS_DIRECT[team][seed]), (
                f"{team} seed {seed}: atom count differs"
            )


def test_precomputed_scenarios_count_match():
    """Precomputed path produces the same number of division scenarios."""
    assert len(_SCENARIOS_PRE) == len(_SCENARIOS_DIRECT)


def test_precomputed_scenarios_seedings_match():
    """Precomputed path produces identical seedings in the same order."""
    for i, (pre, direct) in enumerate(zip(_SCENARIOS_PRE, _SCENARIOS_DIRECT)):
        assert pre["seeding"] == direct["seeding"], (
            f"Scenario {i}: seeding differs — pre={pre['seeding']} direct={direct['seeding']}"
        )
        assert pre["scenario_num"] == direct["scenario_num"], f"Scenario {i}: scenario_num differs"
        assert pre["sub_label"] == direct["sub_label"], f"Scenario {i}: sub_label differs"
        assert pre["game_winners"] == direct["game_winners"], f"Scenario {i}: game_winners differs"


def test_precomputed_non_sensitive_masks_nonempty():
    """enumerate_outcomes identifies at least some non-sensitive masks for R=4."""
    assert len(_PRECOMPUTED.non_sensitive_masks) > 0


def test_precomputed_r_and_pairs():
    """enumerate_outcomes metadata matches remaining game structure."""
    assert _PRECOMPUTED.R == 4
    assert _PRECOMPUTED.total_combos == 12**4
    assert len(_PRECOMPUTED.pairs) == 4


def test_ignore_margins_seedings_subset():
    """Win/loss-only mode produces a seeding for every mask (2^R keys in groups)."""
    wl_outcomes = enumerate_outcomes(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True)
    # One seeding per mask — all masks are non-sensitive in ignore_margins mode.
    assert len(wl_outcomes.non_sensitive_masks) == 1 << 4
    assert len(wl_outcomes.groups) == 1 << 4


def test_ignore_margins_atoms_cover_all_teams():
    """Win/loss-only atoms are produced for every team (no margin conditions)."""
    wl_outcomes = enumerate_outcomes(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True)
    wl_atoms = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=wl_outcomes)
    # Every team that appears in the full atoms should also appear in win/loss-only atoms.
    assert set(wl_atoms.keys()) == set(_ATOMS_DIRECT.keys())


def test_ignore_margins_no_margin_conditions():
    """Win/loss-only atoms contain no MarginCondition objects."""
    from backend.helpers.data_classes import MarginCondition as MC

    wl_outcomes = enumerate_outcomes(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True)
    wl_atoms = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=wl_outcomes)
    for team, seed_map in wl_atoms.items():
        for seed, atom_list in seed_map.items():
            for atom in atom_list:
                for cond in atom:
                    assert not isinstance(cond, MC), (
                        f"{team} seed {seed}: unexpected MarginCondition in win/loss-only atom"
                    )


# ---------------------------------------------------------------------------
# Auto-build-atoms path: precomputed without scenario_atoms
# ---------------------------------------------------------------------------


def test_enumerate_division_scenarios_auto_build_atoms_count():
    """enumerate_division_scenarios auto-builds atoms when given precomputed but no scenario_atoms.

    Covers lines 1396–1405: when margin_sensitive is non-empty and scenario_atoms is None,
    build_scenario_atoms is called internally using the shared precomputed EnumeratedOutcomes.
    The result must have the same number of scenarios as the explicit-atoms path.
    """
    scenarios_auto = enumerate_division_scenarios(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED
    )
    assert len(scenarios_auto) == len(_SCENARIOS_DIRECT)


def test_enumerate_division_scenarios_auto_build_atoms_seedings_match():
    """Auto-built atoms produce identical seedings and scenario numbers as the direct path."""
    scenarios_auto = enumerate_division_scenarios(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED
    )
    for i, (auto, direct) in enumerate(zip(scenarios_auto, _SCENARIOS_DIRECT)):
        assert auto["seeding"] == direct["seeding"], (
            f"Scenario {i}: seeding differs — auto={auto['seeding']} direct={direct['seeding']}"
        )
        assert auto["scenario_num"] == direct["scenario_num"], f"Scenario {i}: scenario_num differs"
        assert auto["sub_label"] == direct["sub_label"], f"Scenario {i}: sub_label differs"
        assert auto["game_winners"] == direct["game_winners"], f"Scenario {i}: game_winners differs"


def test_enumerate_division_scenarios_auto_build_atoms_conditions_populated():
    """Margin-sensitive scenarios in the auto-build path have conditions_atom populated."""
    scenarios_auto = enumerate_division_scenarios(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED
    )
    ms_scenarios = [sc for sc in scenarios_auto if sc["sub_label"] != ""]
    assert len(ms_scenarios) > 0, "Expected at least one margin-sensitive sub-scenario in 4-4A"
    for sc in ms_scenarios:
        assert sc["conditions_atom"] is not None, (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: conditions_atom is None in auto-build path"
        )


# ---------------------------------------------------------------------------
# R=0 early exit — post-season fixture (all games complete)
# ---------------------------------------------------------------------------

# Use 4-4A with cutoff after the last game — R=0.
_4_4A_FINAL_CUTOFF = "2025-11-01"
_4_4A_COMPLETED_FULL = get_completed_games(expand_results([g for g in _4_4A_ALL if g["date"] <= _4_4A_FINAL_CUTOFF]))
_4_4A_REMAINING_ZERO = [
    RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _4_4A_ALL if g["date"] > _4_4A_FINAL_CUTOFF
]


def test_build_scenario_atoms_r0_returns_empty():
    """build_scenario_atoms returns {} when no games remain (R=0 early exit)."""
    atoms = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED_FULL, _4_4A_REMAINING_ZERO)
    assert atoms == {}


def test_enumerate_division_scenarios_r0_returns_single_scenario():
    """enumerate_division_scenarios returns exactly one scenario when R=0."""
    scenarios = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED_FULL, _4_4A_REMAINING_ZERO)
    assert len(scenarios) == 1
    sc = scenarios[0]
    assert sc["scenario_num"] == 1
    assert sc["sub_label"] == ""
    assert sc["game_winners"] == []
    assert sc["conditions_atom"] is None


def test_enumerate_division_scenarios_r0_seeding_matches_ground_truth():
    """R=0 scenario seeding matches 2025 4-4A final seeds."""
    scenarios = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED_FULL, _4_4A_REMAINING_ZERO)
    seeding = scenarios[0]["seeding"]
    expected = _4_4A["seeds"]
    assert seeding[0] == expected[1]
    assert seeding[1] == expected[2]
    assert seeding[2] == expected[3]
    assert seeding[3] == expected[4]


# ---------------------------------------------------------------------------
# render_scenarios eliminated block — 6-team region with eliminated teams
# ---------------------------------------------------------------------------


def test_render_scenarios_includes_eliminated_line():
    """render_scenarios writes 'Eliminated: X, Y' when teams finish outside top 4."""
    # 4-4A has 5 teams; post-season R=0 means one team is always eliminated.
    scenarios = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED_FULL, _4_4A_REMAINING_ZERO)
    text = render_scenarios(scenarios, playoff_seeds=4)
    assert "Eliminated:" in text
    eliminated_team = list(_4_4A["eliminated"])[0]
    assert eliminated_team in text


def test_render_scenarios_no_eliminated_line_when_all_advance():
    """render_scenarios omits 'Eliminated:' when playoff_seeds >= all teams.

    Covers the False branch of `if eliminated:` (line 1709→1712): when every
    team in the seeding fits within the playoff cutoff, the eliminated list is
    empty and no 'Eliminated:' line is written.
    """
    # 4-4A has 5 teams; setting playoff_seeds=5 means everyone advances.
    scenarios = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED_FULL, _4_4A_REMAINING_ZERO)
    text = render_scenarios(scenarios, playoff_seeds=5)
    assert "Eliminated:" not in text


# ---------------------------------------------------------------------------
# _simplify_atom_list — Rule 1 with MarginCondition (line 651)
# ---------------------------------------------------------------------------


class TestSimplifyAtomListRule1WithMarginCondition:
    """Rule 1 merge path appends mc_a[val] when atoms also contain MarginConditions (line 651)."""

    def test_rule1_merge_preserves_identical_margin_condition(self):
        """Two atoms with the same winner and adjacent GameResult ranges plus an
        identical MarginCondition are merged.  During reconstruction, line 651
        appends mc_a[val] for the shared MarginCondition."""
        p_ab = ("A", "B")
        mc = MarginCondition(add=(p_ab,), sub=(), op=">=", threshold=2)

        # Atom 1: A beats B in [1,4) + mc
        atom1 = [GameResult("A", "B", min_margin=1, max_margin=4), mc]
        # Atom 2: A beats B in [3,7) + mc (same winner, overlapping range)
        atom2 = [GameResult("A", "B", min_margin=3, max_margin=7), mc]

        result = _simplify_atom_list([atom1, atom2])

        # Should merge into one atom covering [1,7) plus the MarginCondition
        assert len(result) == 1
        merged = result[0]
        game_conds = [c for c in merged if isinstance(c, GameResult)]
        margin_conds = [c for c in merged if isinstance(c, MarginCondition)]
        assert len(game_conds) == 1
        assert game_conds[0].min_margin == 1
        assert game_conds[0].max_margin == 7
        assert len(margin_conds) == 1
        assert margin_conds[0] == mc


# ---------------------------------------------------------------------------
# _simplify_atom_list — Rule 2 blocked by MarginCondition (line 665)
# ---------------------------------------------------------------------------


class TestSimplifyAtomListRule2BlockedByMarginCondition:
    """Rule 2 returns None when a MarginCondition references the game being dropped (line 665)."""

    def test_rule2_blocked_when_mc_references_game(self):
        """Atoms have opposite unconstrained winners for game (A,B) but a MarginCondition
        that references (A,B) in its .add tuple.  Line 665 fires, preventing the merge."""
        p_ab = ("A", "B")
        # MarginCondition references the very game being considered for Rule-2 elimination
        mc = MarginCondition(add=(p_ab,), sub=(), op=">=", threshold=5)

        atom1 = [GameResult("A", "B", min_margin=1, max_margin=None), mc]
        atom2 = [GameResult("B", "A", min_margin=1, max_margin=None), mc]

        result = _simplify_atom_list([atom1, atom2])

        # Merge blocked by line 665 → atoms unchanged
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _simplify_atom_list — final return None in _try_merge (line 670)
# ---------------------------------------------------------------------------


class TestSimplifyAtomListSameWinnerGappedRanges:
    """Rule 1 does not merge atoms when the same winner's ranges have a gap (line 641 return)."""

    def test_same_winner_gap_in_ranges_not_merged(self):
        """A beats B in [1,4) and [6,∞) — same winner, but a gap between ranges.

        Rule 1 detects the gap at line 641 (first_hi=4 < second_lo=6) and returns None.
        Rule 2 never fires (same winner means ca.loser ≠ cb.winner for game (A,B)).
        Both atoms survive unchanged.

        Note: line 670 (`return None` at end of _try_merge, after both rule blocks)
        is structurally unreachable for well-formed two-team game pairs — for any
        pair (A,B), either Rule 1 (same winner) or Rule 2 (opposite winners)
        always matches, so execution never falls through to line 670."""
        atom1 = [GameResult("A", "B", min_margin=1, max_margin=4)]
        atom2 = [GameResult("A", "B", min_margin=6, max_margin=None)]

        result = _simplify_atom_list([atom1, atom2])

        assert len(result) == 2
        margins = {(c.min_margin, c.max_margin) for atom in result for c in atom if isinstance(c, GameResult)}
        assert (1, 4) in margins
        assert (6, None) in margins


# ---------------------------------------------------------------------------
# _simplify_atom_list — Rule 3 non-overlapping guard (line 753)
# ---------------------------------------------------------------------------


class TestSimplifyAtomListRule3NonOverlapping:
    """_try_rule3 fires the non-overlapping guard (line 752→753 continue) when
    the tightening game's ranges don't overlap."""

    def test_non_overlapping_ranges_block_rule3(self):
        """Atom1: A beats B (unconstrained), G beats H in [1,4).
        Atom2: B beats A (unconstrained), G beats H in [5,∞).

        The tightening game G-H has ranges [1,4) and [5,∞) which don't overlap
        (ca_t.max_margin=4 ≤ cb_t.min_margin=5).  Line 752→753 fires and Rule 3
        returns None.  Both atoms survive unchanged."""
        atom1 = [GameResult("A", "B", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=1, max_margin=4)]
        atom2 = [
            GameResult("B", "A", min_margin=1, max_margin=None),
            GameResult("G", "H", min_margin=5, max_margin=None),
        ]

        result = _simplify_atom_list([atom1, atom2])

        # Rule 3 blocked; Rule 4 also blocked (lower bounds differ: 1 vs 5).
        # Both atoms survive.
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _simplify_atom_list — Rule 4 structural guards (lines 859, 864)
# ---------------------------------------------------------------------------


class TestSimplifyAtomListRule4Guards:
    """Rule 4 structural-reject guards (lower-bound mismatch and range not strictly narrower)."""

    def test_rule4_lower_bound_mismatch_fires_line_859(self):
        """Atoms with different lower bounds for the tightening game trigger line 859.

        Atom1: A beats B (unconstrained), G beats H in [1,3).
        Atom2: B beats A (unconstrained), G beats H in [5,∞).

        First Rule-4 assignment (p_comp=AB, p_tight=GH): min_margins differ (1 vs 5)
        → line 859 fires.  Second assignment (p_comp=GH, p_tight=AB) fails at the
        complementary-game check (G≠H).  Rule 4 returns None; Rule 3 also blocked
        (ca_t.max_margin=3 ≤ cb_t.min_margin=5)."""
        atom1 = [GameResult("A", "B", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=1, max_margin=3)]
        atom2 = [
            GameResult("B", "A", min_margin=1, max_margin=None),
            GameResult("G", "H", min_margin=5, max_margin=None),
        ]

        result = _simplify_atom_list([atom1, atom2])

        assert len(result) == 2

    def test_rule4_range_not_strictly_narrower_fires_line_864(self):
        """First assignment (p_comp=AB, p_tight=GH): both start at min=1, but
        ca_t.max_margin=5 ≥ cb_t.max_margin=3 → line 864 fires.  Second
        assignment fails at the complementary-game check.  Rule 4 returns None.

        Rule 3 also skipped: ca_t.min_margin=1 ≥ cb_t.min_margin=1 → line 749
        fires in _try_rule3, preventing Rule 3 from simplifying first."""
        # Atom 1: A beats B (unconstrained), G beats H in [1,5) — wider range
        atom1 = [GameResult("A", "B", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=1, max_margin=5)]
        # Atom 2: B beats A (unconstrained), G beats H in [1,3) — narrower range
        atom2 = [GameResult("B", "A", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=1, max_margin=3)]

        result = _simplify_atom_list([atom1, atom2])

        assert len(result) == 2


# ---------------------------------------------------------------------------
# Coin flip under margin-sensitive mask (lines 1132, 1299, 1528)
#
# Fixture: 3-team region (A, B, C) with 1 completed game and 2 remaining games.
#
#   Completed : A beats B (margin=6, scores 20–14)
#   Remaining : RemainingGame("A","C"), RemainingGame("B","C")
#
# For mask=2 (C beats A, B beats C) the standings cycle A→C→B→A, producing
# a 3-way 1-1 tie.  Head-to-head PD among the three: at margin combo (6,6)
# all three teams score 0 net PD; subsequent PA tiebreakers are also symmetric,
# so a coin flip is required.  The seeding at corners (m0=1,m1=1) and
# (m0=12,m1=12) differ → the mask IS margin-sensitive, placing the coin-flip
# path inside the sensitive-mask enumeration branch.
# ---------------------------------------------------------------------------

_COIN_TEAMS = ["A", "B", "C"]
# A beats B by 6.  Scores: A scores 20, B scores 14 → pa_a=14 (B's points against A),
# pa_b=20 (A's points against B).  At remaining margin=6 for both games, all three
# teams end up with PA=34, exhausting all tiebreakers and triggering a coin flip.
_COIN_COMPLETED = [
    CompletedGame(a="A", b="B", res_a=1, pd_a=6, pa_a=14, pa_b=20),
]
_COIN_REMAINING = [RemainingGame("A", "C"), RemainingGame("B", "C")]


class TestCoinFlipUnderMarginSensitiveMask:
    """Coin flip under a margin-sensitive mask covers lines 1132, 1299, and 1528."""

    def test_enumerate_outcomes_stores_coin_flip_for_sensitive_mask(self):
        """enumerate_outcomes line 1132: flip_collector non-empty inside the sensitive
        mask branch for at least one margin combo → coin_flips[mask] populated."""
        outcomes = enumerate_outcomes(_COIN_TEAMS, _COIN_COMPLETED, _COIN_REMAINING)

        # mask=2 is margin-sensitive (seedings differ at corners) and produces a
        # coin flip for the margin combo (6, 6).
        assert 2 in outcomes.coin_flips, "mask=2 should have a coin flip recorded"
        assert 2 not in outcomes.non_sensitive_masks, "mask=2 should be margin-sensitive"

    def test_build_scenario_atoms_coin_flip_under_sensitive_mask(self):
        """build_scenario_atoms line 1299: same condition as above — coin flip
        encountered during the sensitive-mask margin enumeration path."""
        atoms = build_scenario_atoms(_COIN_TEAMS, _COIN_COMPLETED, _COIN_REMAINING)

        # The function should complete without error; existence of the coin-flip
        # mask's data in the returned atoms dict confirms the path was exercised.
        # (Coin-flip masks produce no per-team atoms since seedings are
        # non-deterministic, so we just verify the call succeeds.)
        assert isinstance(atoms, dict)

    def test_enumerate_division_scenarios_coin_flip_under_sensitive_mask(self):
        """enumerate_division_scenarios line 1528: coin flip encountered during
        the sensitive-mask inner enumeration path inside the function's own loop."""
        scenarios = enumerate_division_scenarios(_COIN_TEAMS, _COIN_COMPLETED, _COIN_REMAINING)

        # Should return at least one scenario without error.
        assert len(scenarios) >= 1
        scenario_nums = [sc["scenario_num"] for sc in scenarios]
        assert 1 in scenario_nums


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — line 1640→1649: scenario_atoms={} (falsy)
# ---------------------------------------------------------------------------


class TestEnumerateDivisionScenariosNoAtoms:
    """Line 1640→1649: passing scenario_atoms={} leaves conditions_atom as None."""

    def test_empty_scenario_atoms_dict_leaves_conditions_atom_none(self):
        """scenario_atoms doesn't change the scenarios: an empty dict gives the same list as built atoms."""
        with_atoms = enumerate_division_scenarios(
            teams_3_7a, expected_3_7a_completed_games, _REMAINING, scenario_atoms=expected_3_7a_scenarios
        )
        empty = enumerate_division_scenarios(teams_3_7a, expected_3_7a_completed_games, _REMAINING, scenario_atoms={})
        assert empty == with_atoms


# ---------------------------------------------------------------------------
# Outer stability loop — second pass
# (lines 897, 901, 904-910, 911→895, 920-921, 933-936, 938)
# ---------------------------------------------------------------------------


class TestOuterStabilityLoopSecondPassViaRule4:
    """Rule 4 in pass 1 creates atoms that Rule 1 can merge in pass 2.

    Three atoms are constructed so that the pre-loop exhausts no merges
    (all pairs have two differing conditions), then in the outer loop:

    Pass 1:  Rule 4 splits [Alpha-Beta-unc, GD[1,4)] and [Beta-Alpha-unc, GD[1,7)]
             into [GD[1,4)] and [Beta-Alpha-unc, GD[4,7)].
             globally_changed = True → second outer pass fires.

    Pass 2:  Rule 1 merges [GD[1,4)] with the pre-existing [GD[4,∞)] into [GD[1,∞)].
             Lines 904-910 fire (merge recorded), 897 fires (i=2 already in used),
             901 fires (j=2 already used when scanning from i=1), 911→895 fires
             (found_pair=True at i=0, skipping the append and looping back).

    Pass 2 subsumption: [GD[1,∞)] subsumes [Beta-Alpha-unc, GD[4,7)].
             Lines 920-921 fire, shrinking atoms to [[GD[1,∞)]].
    """

    def test_rule4_then_rule1_merge_in_second_pass(self):
        """Rule 4 fires in pass 1 to eliminate a complementary pair, then Rule 1 merges the resulting atoms in pass 2."""
        atom0 = [GameResult("Alpha", "Beta", 1, None), GameResult("Gamma", "Delta", 1, 4)]
        atom1 = [GameResult("Beta", "Alpha", 1, None), GameResult("Gamma", "Delta", 1, 7)]
        atom2 = [GameResult("Gamma", "Delta", 4, None)]

        result = _simplify_atom_list([atom0, atom1, atom2])

        assert result == [[GameResult("Gamma", "Delta", 1, None)]]


class TestOuterStabilityLoopRule3:
    """Rule 3 fires in the outer stability loop (lines 933-936, 938).

    The outer-loop Rule 3 section (lines 923-938) is distinct from the
    pre-stability-loop Rule 3 (lines 799-811).  To reach 933-938, Rule 3
    must fire on atoms that were NOT Rule-3-applicable before the outer loop
    started — only outer-loop Rule 4 can create that opportunity.

    Construction (3 atoms):
      atom0 = [Phi-Rho-unc, Gamma-Delta[1,4), Alpha-Beta-unc]   pairs {PR, GD, AB}
      atom1 = [Rho-Phi-unc, Gamma-Delta[1,7), Alpha-Beta-unc]   pairs {PR, GD, AB}
      atom_x = [Gamma-Delta[3,∞), Beta-Alpha-unc]               pairs {GD, AB}

    Pre-loop Rule 3 does NOT fire: atom0/1 have 3-pair set; atom_x has 2-pair
    set; Rule 3 requires identical pair sets, so no pair fires.

    Outer pass 1 — Rule 4 fires on (atom0, atom1):
      new_a = [GD[1,4), AB-unc]          ← comp game (PR) dropped
      new_b = [Rho-Phi-unc, GD[4,7), AB-unc]

    Outer pass 2 — Rule 3 fires on (new_a, atom_x):
      new_a and atom_x now share the same 2-pair set {GD, AB}.
      new_a is the wider atom (GD[1,4)), atom_x is tighter (GD[3,∞)).
      → atom_x replaced with [GD[3,∞)]   lines 933-936, 938 fire.

    Outer pass 3 — subsumption: [GD[3,∞)] subsumes new_b ([Rho-Phi-unc, GD[4,7), AB-unc]).
    Final: [[GD[1,4), AB-unc], [GD[3,∞)]]
    """

    def test_rule4_exposes_rule3_opportunity_in_outer_loop(self):
        """Rule 4 merges a complementary pair in pass 1, creating a new atom that Rule 3 can then simplify in the outer stability loop."""
        atom0 = [
            GameResult("Phi", "Rho", 1, None),  # comp: Phi beats Rho, unc
            GameResult("Gamma", "Delta", 1, 4),  # tight (narrow): GD [1,4)
            GameResult("Alpha", "Beta", 1, None),  # shared: Alpha beats Beta, unc
        ]
        atom1 = [
            GameResult("Rho", "Phi", 1, None),  # comp (opposite): Rho beats Phi, unc
            GameResult("Gamma", "Delta", 1, 7),  # tight (wide): GD [1,7)
            GameResult("Alpha", "Beta", 1, None),  # shared: same as atom0
        ]
        atom_x = [
            GameResult("Gamma", "Delta", 3, None),  # tight (tighter): GD [3,∞)
            GameResult("Beta", "Alpha", 1, None),  # shared (opposite): Beta beats Alpha, unc
        ]

        result = _simplify_atom_list([atom0, atom1, atom_x])

        assert result == [
            [GameResult("Gamma", "Delta", 1, 4), GameResult("Alpha", "Beta", 1, None)],
            [GameResult("Gamma", "Delta", 3, None)],
        ]


# ---------------------------------------------------------------------------
# Partial-results fixtures — 3-7A with some final-week games already known
# ---------------------------------------------------------------------------

_GAME_BRN_MER = CompletedGame("Brandon", "Meridian", 1, 27, 13, 40)
_GAME_OG_PRL = CompletedGame("Oak Grove", "Pearl", 1, 21, 7, 28)
_GAME_NWR_PET = CompletedGame("Northwest Rankin", "Petal", 1, 6, 28, 34)

# Partial A: Brandon/Meridian settled; OG/Pearl and NWR/Petal still TBD
_COMPLETED_PA = sorted(expected_3_7a_completed_games + [_GAME_BRN_MER], key=lambda g: (g.a, g.b))
_REMAINING_PA = [RemainingGame("Oak Grove", "Pearl"), RemainingGame("Northwest Rankin", "Petal")]
_PAIRS_PA = [(rg.a, rg.b) for rg in _REMAINING_PA]
_SCENARIOS_PA = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PA, _REMAINING_PA)

# Partial B: Brandon + OG/Pearl settled; NWR/Petal still TBD
_COMPLETED_PB = sorted(expected_3_7a_completed_games + [_GAME_BRN_MER, _GAME_OG_PRL], key=lambda g: (g.a, g.b))
_REMAINING_PB = [RemainingGame("Northwest Rankin", "Petal")]
_PAIRS_PB = [(rg.a, rg.b) for rg in _REMAINING_PB]
_SCENARIOS_PB = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PB, _REMAINING_PB)

# Partial C: Brandon + NWR/Petal settled (n=6); OG/Pearl still TBD
_COMPLETED_PC = sorted(expected_3_7a_completed_games + [_GAME_BRN_MER, _GAME_NWR_PET], key=lambda g: (g.a, g.b))
_REMAINING_PC = [RemainingGame("Oak Grove", "Pearl")]
_PAIRS_PC = [(rg.a, rg.b) for rg in _REMAINING_PC]
_SCENARIOS_PC = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PC, _REMAINING_PC)


# ---------------------------------------------------------------------------
# Partial A — Brandon/Meridian known, 2 remaining (OG/Pearl, NWR/Petal)
# ---------------------------------------------------------------------------


def test_partial_a_scenario_count():
    """Partial A (Brandon/Meridian known) produces 4 scenarios, one per set of winners."""
    assert len(_SCENARIOS_PA) == 4


def test_partial_a_scenario_labels():
    """Partial A's five-way tie (Pearl and NWR win) has too many finishes to list: scenario 3 leaves it open.
    Brandon finishes fifth at every margin, so the tie it leaves open is the other four."""
    assert not [sc for sc in _SCENARIOS_PA if sc["sub_label"]]
    sc3 = next(sc for sc in _SCENARIOS_PA if sc["scenario_num"] == 3)
    assert sc3["open_groups"] == [(3, ("Northwest Rankin", "Oak Grove", "Pearl", "Petal"))]


def test_partial_a_deterministic_seedings():
    """Partial A deterministic scenarios (1, 2, 4) produce the expected top-4 seedings."""
    single = {sc["scenario_num"]: sc["seeding"][:4] for sc in _SCENARIOS_PA if not sc["sub_label"]}
    assert single[1] == ("Petal", "Pearl", "Oak Grove", "Brandon")
    assert single[2] == ("Petal", "Oak Grove", "Brandon", "Northwest Rankin")
    assert single[4] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")


def test_partial_a_backward_coverage():
    """Every (mask, margins) is covered by a scenario, and every scenario covering it agrees."""
    report = coverage_problems(teams_3_7a, _COMPLETED_PA, _REMAINING_PA, _SCENARIOS_PA)
    assert report.ok, report.summary(_REMAINING_PA)


def test_partial_a_soundness():
    """For every (mask, margins) satisfying a Partial A conditions_atom, resolve_standings
    produces that scenario's seeding."""

    def _atom_ok(atom, mask, margins):
        """Return True if every condition in the atom is satisfied by the given mask and margins."""
        return all(c.satisfied_by(mask, margins, _REMAINING_PA) for c in atom)

    def _scenario_mask_pa(sc):
        """Convert a Partial A scenario's game_winners into a bitmask over _REMAINING_PA games."""
        winner_set = {gw[0] for gw in sc["game_winners"]}
        m = 0
        for i, rg in enumerate(_REMAINING_PA):
            if rg.a in winner_set:
                m |= 1 << i
        return m

    failures = []
    for sc in _SCENARIOS_PA:
        atom = sc.get("conditions_atom")
        if atom is None:
            continue
        mask = _scenario_mask_pa(sc)
        for m0, m1 in product(range(1, 13), repeat=2):
            margins = {_PAIRS_PA[0]: m0, _PAIRS_PA[1]: m1}
            if not _atom_ok(atom, mask, margins):
                continue
            actual = resolve_standings_for_mask(
                teams_3_7a,
                _COMPLETED_PA,
                _REMAINING_PA,
                mask,
                margins,
                _BASE_MARGIN_DEFAULT,
                _PA_WIN,
            )
            if tuple(actual) != sc["seeding"]:
                failures.append(
                    f"Scenario {sc['scenario_num']}{sc['sub_label']}: "
                    f"mask={mask} margins={margins} → {tuple(actual)}, expected {sc['seeding']}"
                )
    assert not failures, f"{len(failures)} soundness violations:\n" + "\n".join(failures[:3])


# ---------------------------------------------------------------------------
# Partial B — Brandon + OG/Pearl known, 1 remaining (NWR/Petal)
# ---------------------------------------------------------------------------


def test_partial_b_scenario_count():
    """Partial B (Brandon + OG/Pearl known) produces exactly 2 scenarios."""
    assert len(_SCENARIOS_PB) == 2


def test_partial_b_seedings():
    """Partial B scenarios have the expected seedings for both outcomes."""
    seedings = {sc["scenario_num"]: sc["seeding"][:4] for sc in _SCENARIOS_PB}
    # Petal wins NWR game: Petal #1 (best record at 4-1), OG #2 (H2H over Brandon)
    assert seedings[1] == ("Petal", "Oak Grove", "Brandon", "Northwest Rankin")
    # NWR wins: OG #1, NWR still #4 (Brandon beat NWR H2H; Petal beat OG H2H → Petal #2)
    assert seedings[2] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")


def test_partial_b_no_margin_conditions():
    """Partial B scenarios are margin-insensitive (conditions_atom is None for all)."""
    for sc in _SCENARIOS_PB:
        assert sc.get("conditions_atom") is None, (
            f"Scenario {sc['scenario_num']}: expected no conditions_atom but got {sc['conditions_atom']}"
        )


def test_partial_b_backward_coverage():
    """Every (mask, margins) is covered by a scenario, and every scenario covering it agrees."""
    report = coverage_problems(teams_3_7a, _COMPLETED_PB, _REMAINING_PB, _SCENARIOS_PB)
    assert report.ok, report.summary(_REMAINING_PB)


# ---------------------------------------------------------------------------
# Partial C — Brandon + NWR/Petal known (n=6), 1 remaining (OG/Pearl)
# ---------------------------------------------------------------------------


def test_partial_c_scenario_count():
    """Partial C (Brandon + NWR/Petal known) produces exactly 7 scenarios."""
    assert len(_SCENARIOS_PC) == 7


def test_partial_c_scenario_labels():
    """Partial C has 6 sub-labeled scenarios (1a–1f) and 1 unlabeled scenario (2)."""
    labeled = [sc for sc in _SCENARIOS_PC if sc["sub_label"]]
    unlabeled = [sc for sc in _SCENARIOS_PC if not sc["sub_label"]]
    assert len(labeled) == 6
    assert all(sc["scenario_num"] == 1 for sc in labeled)
    assert sorted(sc["sub_label"] for sc in labeled) == list("abcdef")
    assert len(unlabeled) == 1
    assert unlabeled[0]["scenario_num"] == 2


def test_partial_c_deterministic_seeding():
    """Partial C scenario 2 (OG beats Pearl) is deterministic: OG / Petal / Brandon / NWR."""
    sc2 = next(sc for sc in _SCENARIOS_PC if sc["scenario_num"] == 2)
    assert sc2["seeding"][:4] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")
    assert sc2.get("conditions_atom") is None


def test_partial_c_backward_coverage():
    """Every (mask, margins) is covered by a scenario, and every scenario covering it agrees."""
    report = coverage_problems(teams_3_7a, _COMPLETED_PC, _REMAINING_PC, _SCENARIOS_PC)
    assert report.ok, report.summary(_REMAINING_PC)


def test_partial_c_soundness():
    """For every (mask, margin) satisfying a Partial C conditions_atom, resolve_standings
    produces that scenario's seeding."""

    def _atom_ok_pc(atom, mask, margins):
        """Return True if every condition in the atom is satisfied by the given mask and margins."""
        return all(c.satisfied_by(mask, margins, _REMAINING_PC) for c in atom)

    def _scenario_mask_pc(sc):
        """Convert a Partial C scenario's game_winners into a bitmask over _REMAINING_PC games."""
        winner_set = {gw[0] for gw in sc["game_winners"]}
        m = 0
        for i, rg in enumerate(_REMAINING_PC):
            if rg.a in winner_set:
                m |= 1 << i
        return m

    failures = []
    for sc in _SCENARIOS_PC:
        atom = sc.get("conditions_atom")
        if atom is None:
            continue
        mask = _scenario_mask_pc(sc)
        for m in range(1, 13):
            margins = {_PAIRS_PC[0]: m}
            if not _atom_ok_pc(atom, mask, margins):
                continue
            actual = resolve_standings_for_mask(
                teams_3_7a,
                _COMPLETED_PC,
                _REMAINING_PC,
                mask,
                margins,
                _BASE_MARGIN_DEFAULT,
                _PA_WIN,
            )
            if tuple(actual) != sc["seeding"]:
                failures.append(
                    f"Scenario {sc['scenario_num']}{sc['sub_label']}: "
                    f"mask={mask} margin={m} → {tuple(actual)}, expected {sc['seeding']}"
                )
    assert not failures, f"{len(failures)} soundness violations:\n" + "\n".join(failures)


_EXPECTED_PARTIAL_A_RENDER = """\
Scenario 1: Pearl beats Oak Grove AND Petal beats Northwest Rankin
1. Petal
2. Pearl
3. Oak Grove
4. Brandon
Eliminated: Meridian, Northwest Rankin

Scenario 2: Oak Grove beats Pearl AND Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl

Scenario 3: Pearl beats Oak Grove AND Northwest Rankin beats Petal
1-4. Northwest Rankin, Oak Grove, Pearl, and Petal: order decided by the tiebreaker (point differential, then fewest points allowed)
Eliminated: Brandon, Meridian

Scenario 4: Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl"""


def test_partial_a_render_full_output():
    """Full rendered output for Partial A matches expected text exactly.

    Golden-file regression test: update _EXPECTED_PARTIAL_A_RENDER when output changes intentionally.
    """
    result = render_scenarios(_SCENARIOS_PA)
    assert result == _EXPECTED_PARTIAL_A_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_PARTIAL_A_RENDER}\n--- ACTUAL ---\n{result}"
    )


_EXPECTED_PARTIAL_B_RENDER = """\
Scenario 1: Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl

Scenario 2: Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl"""


def test_partial_b_render_full_output():
    """Full rendered output for Partial B matches expected text exactly.

    Golden-file regression test: update _EXPECTED_PARTIAL_B_RENDER when output changes intentionally.
    """
    result = render_scenarios(_SCENARIOS_PB)
    assert result == _EXPECTED_PARTIAL_B_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_PARTIAL_B_RENDER}\n--- ACTUAL ---\n{result}"
    )


_EXPECTED_PARTIAL_C_RENDER = """\
Scenario 1a: Pearl beats Oak Grove by 1–3
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Pearl
Eliminated: Brandon, Meridian

Scenario 1b: Pearl beats Oak Grove by exactly 4
1. Oak Grove
2. Northwest Rankin
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 1c: Pearl beats Oak Grove by exactly 5
1. Northwest Rankin
2. Oak Grove
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 1d: Pearl beats Oak Grove by 6–7
1. Northwest Rankin
2. Pearl
3. Oak Grove
4. Petal
Eliminated: Brandon, Meridian

Scenario 1e: Pearl beats Oak Grove by exactly 8
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 1f: Pearl beats Oak Grove by 9 or more
1. Pearl
2. Northwest Rankin
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 2: Oak Grove beats Pearl
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Meridian, Pearl"""


def test_partial_c_render_full_output():
    """Full rendered output for Partial C matches expected text exactly.

    Golden-file regression test: update _EXPECTED_PARTIAL_C_RENDER when output changes intentionally.
    """
    result = render_scenarios(_SCENARIOS_PC)
    assert result == _EXPECTED_PARTIAL_C_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_PARTIAL_C_RENDER}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# build_scenario_atoms R > 10 gate
# ---------------------------------------------------------------------------


class TestBuildScenarioAtomsLargeRGate:
    """build_scenario_atoms returns {} for R > 10 without computing atoms."""

    def test_r11_returns_empty_dict(self):
        """11 remaining games triggers the R>10 gate and returns {}."""
        # Craft 11 minimal RemainingGame objects — no completed games needed.
        teams = [f"T{i}" for i in range(5)]
        remaining = [RemainingGame(*sorted([f"T{i}", f"T{j}"])) for i in range(5) for j in range(i + 1, 5)]
        # C(5,2)=10 games only — add one dummy to reach 11.
        remaining.append(RemainingGame("T0", "T1"))  # duplicate is fine for gate test
        assert len(remaining) == 11
        result = build_scenario_atoms(teams, [], remaining)
        assert result == {}

    def test_r10_does_not_trigger_gate(self):
        """R=10 is at the boundary and still computes atoms (returns non-empty dict)."""
        fixture = REGION_RESULTS_2025[(1, 8)]  # 5-team region, R=10 at season start
        all_games = fixture["games"]
        teams = teams_from_games(all_games)
        cutoff = "2025-10-02"
        completed = get_completed_games(expand_results([g for g in all_games if g["date"] <= cutoff]))
        remaining = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in all_games if g["date"] > cutoff]
        assert len(remaining) == 10
        eo = enumerate_outcomes(teams, completed, remaining, ignore_margins=True)
        result = build_scenario_atoms(teams, completed, remaining, precomputed=eo)
        assert result != {}


# ---------------------------------------------------------------------------
# _minimize_game_winner_atom edge cases
# ---------------------------------------------------------------------------


class TestMinimizeGameWinnerAtomEdgeCases:
    """Cover defensive branches in _minimize_game_winner_atom."""

    _remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]

    def test_margin_condition_in_atom_is_skipped_by_covered(self):
        """covered() skips non-GameResult conditions (MarginCondition) with continue.

        When the candidate atom contains a MarginCondition, the covered() inner
        function still returns the full mask set (all outcomes possible) because
        the MarginCondition is ignored — it does not constrain which game-winner
        mask is covered.
        """
        mc = MarginCondition(add=(("A", "B"),), sub=(), op=">=", threshold=3)
        # atom: one simple GameResult + one MarginCondition
        atom = [GameResult("A", "B", 1, None), mc]
        # always_covered_set covers all 4 outcomes — so the GameResult is redundant
        result = _minimize_game_winner_atom(atom, {0, 1, 2, 3}, self._remaining, 2)
        # The GameResult is dropped; the MarginCondition is kept
        assert result == [mc]

    def test_non_unit_min_margin_gameresult_is_skipped(self):
        """GameResult with min_margin != 1 is skipped by the outer continue."""
        atom = [GameResult("A", "B", 3, None)]
        result = _minimize_game_winner_atom(atom, {0, 1, 2, 3}, self._remaining, 2)
        assert result == [GameResult("A", "B", 3, None)]

    def test_bounded_max_margin_gameresult_is_skipped(self):
        """GameResult with max_margin set is skipped by the outer continue."""
        atom = [GameResult("A", "B", 1, 4)]
        result = _minimize_game_winner_atom(atom, {0, 1, 2, 3}, self._remaining, 2)
        assert result == [GameResult("A", "B", 1, 4)]

    def test_gameresult_pair_not_in_remaining_exhausts_inner_loop(self):
        """GameResult whose team pair doesn't appear in remaining exhausts the inner
        for loop covering the 1070→1067 (inner-loop fall-through) branch.

        With remaining=[RemainingGame("A","B")] and an atom containing
        GameResult("X","Y",...), the inner loop iterates all pairs and finds no match.
        The outer loop then proceeds to the next condition in conds (branch 1070→1067).
        """
        remaining_one = [RemainingGame("A", "B")]
        # First condition: GameResult for (A,B) — matched, so covered() works.
        # Second condition: GameResult for (X,Y) — NOT in remaining; inner loop exhausts.
        atom = [GameResult("A", "B", 1, None), GameResult("X", "Y", 1, None)]
        # Both conditions are "simple" (min_margin=1, max_margin=None).
        # always_covered_set covers all outcomes → both are redundant → result is [].
        result = _minimize_game_winner_atom(atom, {0, 1}, remaining_one, 1)
        assert result == []


# ---------------------------------------------------------------------------
# _format_team_list: single-team case
# ---------------------------------------------------------------------------


class TestFormatTeamList:
    """_format_team_list covers all three length branches."""

    def test_single_team(self):
        """Single-element list returns the team name directly (line 2007 coverage)."""
        assert _format_team_list(["Alpha"]) == "Alpha"

    def test_two_teams(self):
        """Two-element list uses 'A and B' format."""
        assert _format_team_list(["Alpha", "Beta"]) == "Alpha and Beta"

    def test_three_teams(self):
        """Three-element list uses Oxford-comma 'A, B, and C' format."""
        assert _format_team_list(["Alpha", "Beta", "Gamma"]) == "Alpha, Beta, and Gamma"


# ---------------------------------------------------------------------------
# render_scenarios: tie-group edge cases
# ---------------------------------------------------------------------------


class TestRenderScenariosEdgeCases:
    """render_scenarios branches for cross-boundary tie groups and group interiors."""

    @staticmethod
    def _sc(seeding, open_groups=None):
        """Build a minimal scenario dict for render_scenarios."""
        return {
            "scenario_num": 1,
            "sub_label": "",
            "conditions_atom": None,
            "game_winners": [("A", "B")],
            "seeding": tuple(seeding),
            "open_groups": open_groups,
        }

    def test_tie_group_spanning_playoff_boundary_falls_through(self):
        """A tie straddling the playoff cutoff is shown as one place shared, not as an order.

        Group [D, E] sits at positions 3 and 4 (0-indexed); with playoff_seeds=4 one of them is 4th
        and the other is out, and which one isn't stated.
        """
        sc = self._sc(
            seeding=["A", "B", "C", "D", "E"],
            open_groups=[(3, ("D", "E"))],
        )
        rendered = render_scenarios([sc], playoff_seeds=4)
        assert "4. D or E: order decided by the tiebreaker" in rendered
        assert "Eliminated: the rest of that tie" in rendered

    def test_overlapping_groups_hit_interior_continue(self):
        """Overlapping groups: the first claims its places and the rest render normally."""
        sc = self._sc(
            seeding=["A", "B", "C", "D"],
            open_groups=[(3, ("A", "B")), (6, ("B", "C"))],
        )
        rendered = render_scenarios([sc], playoff_seeds=4)
        assert "1-2. A and B: order decided by the tiebreaker" in rendered
        assert "4. D" in rendered


# ---------------------------------------------------------------------------
# build_pre_playoff_home_scenarios: 5A-7A bracket (is_1a_4a=False) and away seeds
# ---------------------------------------------------------------------------


class TestBuildPrePlayoffHomeScenariosEdgeCases:
    """build_pre_playoff_home_scenarios branches for 5A-7A and away-seed R1."""

    # Use the 3-7A mid-season fixture: 3 remaining games, teams include Brandon
    # which can finish 1st through 4th (some as away-team seeds in SLOTS_5A_7A_2025).
    # Region 3 in SLOTS_5A_7A_2025: seeds 1 and 2 are home, seeds 3 and 4 are away.

    def test_5a_7a_returns_three_rounds(self):
        """5A-7A bracket produces 3 rounds (no Second Round)."""
        home_scenarios, _ = build_pre_playoff_home_scenarios(
            team="Brandon",
            region=3,
            season=2025,
            slots=SLOTS_5A_7A_2025,
            teams=teams_3_7a,
            completed=expected_3_7a_completed_games,
            remaining=expected_3_7a_remaining_games,
        )
        assert len(home_scenarios) == 3
        assert [r.round_name for r in home_scenarios] == ["First Round", "Quarterfinals", "Semifinals"]

    def test_5a_7a_away_seed_paths_produce_will_not_host_r1(self):
        """Brandon finishing as seed 3 or 4 (both away in SLOTS_5A_7A_2025) contributes
        to will_not_host in R1, confirming the was_home_r1=False branch is reached."""
        home_scenarios, _ = build_pre_playoff_home_scenarios(
            team="Brandon",
            region=3,
            season=2025,
            slots=SLOTS_5A_7A_2025,
            teams=teams_3_7a,
            completed=expected_3_7a_completed_games,
            remaining=expected_3_7a_remaining_games,
        )
        r1 = home_scenarios[0]
        assert r1.round_name == "First Round"
        # Brandon can be seed 3 or 4 (away teams) → will_not_host is non-empty
        assert len(r1.will_not_host) > 0

    def test_achievable_seed_with_no_matching_slot_is_skipped(self):
        """An achievable seed with no corresponding slot in this region's bracket
        half (a data inconsistency between the seeding odds and the format) is
        skipped when accumulating R1 overall hosting probability, rather than
        raising. Slots 6/7 (region 3's seed-3/4 away slots in SLOTS_5A_7A_2025)
        are re-pointed to phantom regions so region 3 has no seed-3/4 slot at all,
        while Brandon (per the away-seed test above) can still achieve seed 3/4."""
        custom_slots = [
            FormatSlot(slot=1, home_region=1, home_seed=1, away_region=2, away_seed=4, north_south="N"),
            FormatSlot(slot=2, home_region=2, home_seed=2, away_region=1, away_seed=3, north_south="N"),
            FormatSlot(slot=3, home_region=2, home_seed=1, away_region=1, away_seed=4, north_south="N"),
            FormatSlot(slot=4, home_region=1, home_seed=2, away_region=2, away_seed=3, north_south="N"),
            FormatSlot(slot=5, home_region=3, home_seed=1, away_region=4, away_seed=4, north_south="S"),
            FormatSlot(slot=6, home_region=4, home_seed=2, away_region=13, away_seed=3, north_south="S"),
            FormatSlot(slot=7, home_region=4, home_seed=1, away_region=14, away_seed=4, north_south="S"),
            FormatSlot(slot=8, home_region=3, home_seed=2, away_region=4, away_seed=3, north_south="S"),
        ]
        home_scenarios, _ = build_pre_playoff_home_scenarios(
            team="Brandon",
            region=3,
            season=2025,
            slots=custom_slots,
            teams=teams_3_7a,
            completed=expected_3_7a_completed_games,
            remaining=expected_3_7a_remaining_games,
        )
        assert len(home_scenarios) == 3
        assert home_scenarios[0].round_name == "First Round"


class TestFindTiebreakerGroups:
    """_find_tiebreaker_groups finds maximal spans of mutually-swapped team positions."""

    def test_matching_orders_produce_no_groups(self):
        """Identical orderings have no swapped positions -- no groups."""
        assert _find_tiebreaker_groups(["A", "B", "C"], ["A", "B", "C"]) == []

    def test_adjacent_swap_forms_one_group(self):
        """A simple adjacent-pair swap forms one 2-team group."""
        groups = _find_tiebreaker_groups(["A", "B", "C"], ["B", "A", "C"])
        assert groups == [["A", "B"]]

    def test_non_convergent_suffix_returns_no_group(self):
        """When the trailing positions never resolve to the same team set (the
        two orderings disagree on which teams occupy the tail at all), the scan
        runs off the end of the list without converging and no group is formed."""
        groups = _find_tiebreaker_groups(["A", "B", "C"], ["A", "B", "D"])
        assert groups == []


class TestSimplifyAtomListTiePlaces:
    """Rule 5: a team's every place in one tie, otherwise alike, is the rest alone."""

    def test_every_place_in_the_tie_drops_the_tie(self):
        """A team taking either place in a two-team tie is every place it can take there, so the tie condition drops out."""
        from backend.helpers.data_classes import TiebreakPlace

        g = GameResult("A", "B")
        tie = ("A", "C")
        atoms = [[g, TiebreakPlace("A", 1, tie, 5)], [g, TiebreakPlace("A", 2, tie, 5)]]
        assert _simplify_atom_list(atoms) == [[g]]

    def test_some_places_in_the_tie_stay(self):
        """Two of three places in a three-team tie isn't all of them, so the alternatives stay as they are."""
        from backend.helpers.data_classes import TiebreakPlace

        g = GameResult("A", "B")
        tie = ("A", "C", "D")
        atoms = [[g, TiebreakPlace("A", 1, tie, 5)], [g, TiebreakPlace("A", 2, tie, 5)]]
        assert _simplify_atom_list(atoms) == atoms
