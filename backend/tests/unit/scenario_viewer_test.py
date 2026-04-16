"""Tests for scenario_viewer: enumerate_division_scenarios and render_division_scenarios."""

from itertools import product

from backend.helpers.data_classes import CoinFlipResult, CompletedGame, GameResult, MarginCondition, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import _render_margin_condition
from backend.helpers.scenario_viewer import (
    _derive_atom,
    _eval_mc,
    _find_combined_atom,
    _simplify_atom_list,
    _split_non_rectangular_atom,
    build_scenario_atoms,
    enumerate_division_scenarios,
    enumerate_outcomes,
    render_division_scenarios,
    render_scenarios,
)
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_completed_games_full,
    expected_3_7a_remaining_games,
    expected_3_7a_remaining_games_full,
    expected_3_7a_scenarios,
    teams_3_7a,
)

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
    """3-7A produces exactly 17 distinct complete seeding scenarios."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    assert len(scenarios) == 17


def test_3_7a_margin_sensitive_group_labeled():
    """The margin-sensitive mask produces sub-scenarios labeled 4a through 4l."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sub_scenarios = [sc for sc in scenarios if sc["sub_label"]]
    assert len(sub_scenarios) == 12
    assert all(sc["scenario_num"] == 4 for sc in sub_scenarios)
    labels = sorted(sc["sub_label"] for sc in sub_scenarios)
    assert labels == list("abcdefghijkl")


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
    """Every (mask, margin) combination is covered by the seeding of exactly one scenario."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    seeding_map = {sc["seeding"]: sc for sc in scenarios}

    failures = []
    for mask, margins in _all_outcome_branches():
        order = resolve_standings_for_mask(
            teams_3_7a,
            expected_3_7a_completed_games,
            _REMAINING,
            mask,
            margins,
            _BASE_MARGIN_DEFAULT,
            _PA_WIN,
        )
        seeding = tuple(order)
        if seeding not in seeding_map:
            failures.append(f"mask={mask} margins={margins}: seeding {seeding} not in scenarios")

    assert not failures, f"{len(failures)} uncovered outcomes:\n" + "\n".join(failures[:5])


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
                candidate_mask |= (1 << i)

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
        assert found, (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: "
            f"no satisfying (mask, margins) found for atom"
        )


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


def test_full_season_render_contains_no_remaining():
    """Full-season render starts with the deterministic message."""
    output = render_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games_full,
        expected_3_7a_remaining_games_full,
    )
    assert "(no remaining games — standings are final)" in output
    assert "1. Oak Grove" in output


# ---------------------------------------------------------------------------
# render_division_scenarios — structural render checks
# ---------------------------------------------------------------------------


def test_render_contains_all_scenario_labels():
    """Rendered output contains all 17 scenario labels."""
    output = render_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    for n in range(1, 7):
        assert f"Scenario {n}" in output
    for letter in "abcdefghijkl":
        assert f"Scenario 4{letter}:" in output


def test_render_eliminated_teams_shown():
    """Render includes 'Eliminated:' lines listing non-seeded teams."""
    output = render_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    assert "Eliminated:" in output
    # Meridian is always eliminated (all 17 scenarios)
    for line in output.splitlines():
        if line.startswith("Eliminated:"):
            assert "Meridian" in line


def test_render_without_explicit_atoms_auto_computes():
    """Without explicit scenario_atoms, enumerate_division_scenarios auto-builds atoms for
    margin-sensitive scenarios so conditions_atom is populated and margin text appears."""
    output = render_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=None,
    )
    # Should still have 17 scenarios (Scenario 1–6 with 4a–4l for the margin-sensitive mask)
    assert output.count("Scenario 4") == 12  # exactly 4a through 4l
    # Margin condition text IS present — atoms are auto-computed even without explicit atoms arg
    assert "or more" in output


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
    assert result == "Northwest Rankin/Petal's margin and Oak Grove/Pearl's margin combined total exactly 10"


def test_render_margin_condition_diff_eq_positive():
    """op='==' diff with positive t renders as 'A exceeds B by exactly N'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=2)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Northwest Rankin/Petal's margin exceeds Oak Grove/Pearl's by exactly 2"


def test_render_margin_condition_diff_eq_negative():
    """op='==' diff with negative t renders as 'B exceeds A by exactly N'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=-3)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Oak Grove/Pearl's margin exceeds Northwest Rankin/Petal's by exactly 3"


def test_render_margin_condition_diff_eq_zero():
    """op='==' diff with t=0 renders as 'A's margin equals B's'."""
    mc = MarginCondition(add=(_NWR_PET,), sub=(_OG_PRL,), op="==", threshold=0)
    result = _render_margin_condition(mc, _DUMMY_ATOM)
    assert result == "Northwest Rankin/Petal's margin equals Oak Grove/Pearl's"


def test_margin_condition_satisfied_by_eq_op():
    """MarginCondition with op='==' is satisfied only when the value equals the threshold."""
    mc = MarginCondition(add=(_NWR_PET, _OG_PRL), sub=(), op="==", threshold=10)
    margins_eq = {("Northwest Rankin", "Petal"): 5, ("Oak Grove", "Pearl"): 5}
    margins_ne = {("Northwest Rankin", "Petal"): 5, ("Oak Grove", "Pearl"): 6}
    assert mc.satisfied_by(0, margins_eq, _REMAINING) is True
    assert mc.satisfied_by(0, margins_ne, _REMAINING) is False


# ---------------------------------------------------------------------------
# 4c, 4d, 4i, 4j: verify "==" simplification was applied by _find_combined_atom
# ---------------------------------------------------------------------------


def test_4c_has_exact_sum_condition():
    """Scenario 4c's atom includes a 'combined total exactly 10' condition.

    After ascending-margin sort, the p∈[1,5], n∈[5,9], p+n=10 scenario is 4c
    (sort key (1,5) — third-smallest minimum margin pair).
    """
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sc_4c = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "c")
    assert sc_4c is not None
    atom = sc_4c["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    assert any(c.threshold == 10 for c in eq_conds)


def test_4e_has_exact_diff_condition():
    """Scenario 4e's atom includes a 'diff exactly 2' condition (Pearl exceeds NWR by exactly 2).

    After ascending-margin sort, the p∈[3,5], n∈[1,3], p–n=2 scenario is 4e
    (sort key (3,1) — fifth-smallest minimum margin pair).
    """
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sc_4e = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "e")
    assert sc_4e is not None
    atom = sc_4e["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    # diff == -2 means NWR_margin - Pearl_margin == -2, i.e. Pearl exceeds NWR by exactly 2
    assert any(c.threshold == -2 and len(c.add) == 1 and len(c.sub) == 1 for c in eq_conds)


def test_4h_has_exact_diff_condition():
    """Scenario 4h's atom includes a 'diff exactly 2' condition (Pearl exceeds NWR by exactly 2).

    After ascending-margin sort, the p≥6, n∈[4,10], p–n=2 scenario is 4h
    (sort key (6,4) — eighth-smallest minimum margin pair).
    Uses build_scenario_atoms (algorithmic) because the hand-crafted fixture encodes the
    n=4, p=6 boundary as exact GameResult bounds with no MarginCondition.
    """
    scenarios = _SCENARIOS_3_7A
    sc_4h = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "h")
    atom = sc_4h["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    # Either add=Pearl/sub=NWR with threshold=2 or add=NWR/sub=Pearl with threshold=-2 —
    # both encode "Pearl's margin exceeds NWR's by exactly 2"
    assert any(
        abs(c.threshold) == 2 and len(c.add) == 1 and len(c.sub) == 1 for c in eq_conds
    )


def test_4j_has_exact_sum_condition():
    """Scenario 4j's atom includes a 'combined total exactly 10' condition.

    After ascending-margin sort, the p∈[7,9], n∈[1,3], p+n=10 scenario is 4j
    (sort key (7,1) — tenth-smallest minimum margin pair).
    Uses build_scenario_atoms (algorithmic) for the same reason as test_4h above.
    """
    scenarios = _SCENARIOS_3_7A
    sc_4j = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "j")
    atom = sc_4j["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    assert any(c.threshold == 10 for c in eq_conds)


# ---------------------------------------------------------------------------
# Full render snapshot — 3-7A division scenarios (algorithmic atoms)
# ---------------------------------------------------------------------------

_EXPECTED_3_7A_RENDER = """\
Scenario 1: Pearl beats Oak Grove AND Petal beats Northwest Rankin
1. Petal
2. Pearl
3. Oak Grove
4. Brandon
Eliminated: Northwest Rankin, Meridian

Scenario 2: Oak Grove beats Pearl AND Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian

Scenario 3: Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4a: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Oak Grove
2. Petal
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4b: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4c: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Oak Grove
2. Northwest Rankin
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4d: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Northwest Rankin
2. Oak Grove
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4e: Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Petal
2. Oak Grove
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4f: Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Petal
2. Oak Grove
3. Pearl
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4g: Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Petal
2. Pearl
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4h: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4i: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Northwest Rankin
2. Pearl
3. Oak Grove
4. Petal
Eliminated: Brandon, Meridian

Scenario 4j: Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Pearl
2. Petal
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4k: Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Pearl
2. Northwest Rankin
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4l: Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Pearl
2. Petal
3. Northwest Rankin
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 5: Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Brandon
Eliminated: Pearl, Meridian

Scenario 6: Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian"""


def test_render_division_scenarios_full_output():
    """Full rendered output of all 17 division scenarios matches expected text exactly.

    This is a golden-file regression test: if the rendered conditions for any
    scenario change, the test fails.  Update _EXPECTED_3_7A_RENDER when the
    output is intentionally changed.
    """
    result = render_division_scenarios(
        teams_3_7a, expected_3_7a_completed_games, _REMAINING, scenario_atoms=_ATOMS_3_7A
    )
    assert result == _EXPECTED_3_7A_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_3_7A_RENDER}\n--- ACTUAL ---\n{result}"
    )


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

    def test_produces_17_scenarios(self):
        """build_scenario_atoms atoms yield exactly 17 distinct scenarios."""
        assert len(self._scenarios()) == 17

    def test_sub_scenarios_labeled_4a_through_4l(self):
        """Margin-sensitive group produces sub-scenarios 4a–4l."""
        subs = [sc for sc in self._scenarios() if sc["sub_label"]]
        assert len(subs) == 12
        assert sorted(sc["sub_label"] for sc in subs) == list("abcdefghijkl")

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
            # MarginCondition clauses look like "X's margin exceeds Y's by exactly N" — allowed.
            clauses = line.split(" AND ")
            for clause in clauses:
                if "beats" in clause and "by exactly" in clause:
                    raise AssertionError(
                        f"Per-game point-sample condition found (expected a range): {clause!r}\n"
                        f"Full line: {line!r}"
                    )

    def test_render_contains_joint_constraints(self):
        """Rendered output for mask=5 sub-scenarios includes joint margin constraint phrases."""
        output = render_scenarios(self._scenarios())
        # The 3-7A mask=5 sub-scenarios all involve sum or diff constraints
        assert "combined total" in output or "margin exceeds" in output or "margin equals" in output

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
        """Every (mask, margin) combo is covered by some scenario when using built atoms."""
        scenarios = self._scenarios()
        seeding_map = {sc["seeding"]: sc for sc in scenarios}
        failures = []
        for mask, margins in _all_outcome_branches():
            order = resolve_standings_for_mask(
                teams_3_7a,
                expected_3_7a_completed_games,
                _REMAINING,
                mask,
                margins,
                _BASE_MARGIN_DEFAULT,
                _PA_WIN,
            )
            if tuple(order) not in seeding_map:
                failures.append(f"mask={mask} margins={margins}: {tuple(order)} not found")
        assert not failures, f"{len(failures)} uncovered outcomes:\n" + "\n".join(failures[:3])

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
                    assert span > 1, (
                        f"NWR seed-1 atom has point-sample GameResult: {cond}. "
                        "Expected a margin range."
                    )


# ---------------------------------------------------------------------------
# Synthetic unit tests — _find_combined_atom, _split_non_rectangular_atom,
# _derive_atom (coverage-gap fill)
# ---------------------------------------------------------------------------

_SYNTH_REMAINING = [RemainingGame("A", "B"), RemainingGame("C", "D")]
_SYNTH_PAIRS = [("A", "B"), ("C", "D")]
_AB = ("A", "B")
_CD = ("C", "D")
_SYNTH_MASK = 0b11  # A wins game 0 (AB), C wins game 1 (CD)


class TestFindCombinedAtom:
    """Synthetic tests for _find_combined_atom — MarginCondition paths and None returns."""

    def _call(self, scenario_atoms, sample_margins, seeding, playoff_seeds=2):
        """Invoke _find_combined_atom with synthetic remaining games and mask."""
        return _find_combined_atom(
            seeding=seeding,
            playoff_seeds=playoff_seeds,
            mask=_SYNTH_MASK,
            sample_margins=sample_margins,
            scenario_atoms=scenario_atoms,
            remaining=_SYNTH_REMAINING,
        )

    def test_ge_intersection_keeps_tightest(self):
        """Two '>=' atoms on same key — merged result keeps the higher (tighter) threshold."""
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=5)]]},
            "C": {2: [[GameResult("C", "D", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=3)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "C", "B", "D"))
        assert result is not None
        mc = [c for c in result if isinstance(c, MarginCondition)]
        assert len(mc) == 1
        assert mc[0].op == ">=" and mc[0].threshold == 5

    def test_lt_op_converted_to_le(self):
        """op='<' threshold N is normalised to '<=' threshold N-1 (line 144-145)."""
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op="<", threshold=10)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "B", "C", "D"))
        assert result is not None
        mc = [c for c in result if isinstance(c, MarginCondition)]
        assert len(mc) == 1
        assert mc[0].op == "<=" and mc[0].threshold == 9

    def test_gt_op_converted_to_ge(self):
        """op='>' threshold N is normalised to '>=' threshold N+1 (line 146-147)."""
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op=">", threshold=5)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "B", "C", "D"))
        assert result is not None
        mc = [c for c in result if isinstance(c, MarginCondition)]
        assert len(mc) == 1
        assert mc[0].op == ">=" and mc[0].threshold == 6

    def test_eq_op_collapses_to_eq(self):
        """op='==' contributes both ge and le directions; reconstructed as op='==' (lines 151-152)."""
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op="==", threshold=7)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "B", "C", "D"))
        assert result is not None
        mc = [c for c in result if isinstance(c, MarginCondition)]
        assert len(mc) == 1
        assert mc[0].op == "==" and mc[0].threshold == 7

    def test_returns_none_when_all_atoms_unsatisfied(self):
        """Returns None when every playoff-seeded team has no matching atom (line 171)."""
        # Both atoms require margin >= 10, but sample margin is only 7
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=10)]]},
            "C": {2: [[GameResult("C", "D", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=10)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "C", "B", "D"))
        assert result is None

    def test_skips_team_with_no_matching_atom_uses_others(self):
        """Skips (line 120 continue) a team whose atom is unsatisfied; uses remaining teams' atoms."""
        # A's atom: requires >= 10 (not satisfied with margin=7) → skipped
        # C's atom: requires >= 3 (satisfied) → used
        atoms = {
            "A": {1: [[GameResult("A", "B", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=10)]]},
            "C": {2: [[GameResult("C", "D", 1, None), MarginCondition(add=(_AB,), sub=(), op=">=", threshold=3)]]},
        }
        result = self._call(atoms, {_AB: 7, _CD: 4}, ("A", "C", "B", "D"))
        assert result is not None
        mc = [c for c in result if isinstance(c, MarginCondition)]
        assert len(mc) == 1 and mc[0].threshold == 3


class TestSplitNonRectangularAtom:
    """Synthetic tests for _split_non_rectangular_atom — reverse direction paths."""

    _base = [GameResult("A", "B", 1, None), GameResult("C", "D", 1, None)]

    def _call(self, valid_margins_list, lows, highs):
        """Invoke _split_non_rectangular_atom with synthetic remaining games and base atom."""
        return _split_non_rectangular_atom(
            _SYNTH_MASK,
            valid_margins_list,
            _SYNTH_REMAINING,
            _SYNTH_PAIRS,
            lows,
            highs,
            self._base,
        )

    def test_reverse_direction_succeeds(self):
        """Forward fails (game0 non-contiguous for same game1 set); reverse succeeds (line 334).

        valid_2d = {(1,2),(2,1),(2,2),(3,2)}
        Forward: frozenset({2}) → game0=[1,3] non-contiguous → fails at line 267-268.
        Reverse: frozenset({2}) → game1=[1]; frozenset({1,2,3}) → game1=[2] — both contiguous.
        """
        valid = [
            {_AB: 1, _CD: 2}, {_AB: 2, _CD: 1},
            {_AB: 2, _CD: 2}, {_AB: 3, _CD: 2},
        ]
        result = self._call(valid, lows=[1, 1], highs=[3, 2])
        assert result is not None
        assert len(result) == 2

    def test_forward_and_reverse_game0_noncont_returns_none(self):
        """Forward fails (game0 non-contiguous); reverse fails (game0 frozenset non-contiguous).

        valid_2d = {(1,1),(1,2),(3,1),(3,2)}
        Forward: frozenset({1,2}) → game0=[1,3] non-contiguous → fails at line 267-268.
        Reverse: frozenset({1,3}) → game1=[1,2] (contiguous), but s_sorted=[1,3]
                 non-contiguous → fails at line 312-313.
        Returns None (line 337).
        """
        valid = [
            {_AB: 1, _CD: 1}, {_AB: 1, _CD: 2},
            {_AB: 3, _CD: 1}, {_AB: 3, _CD: 2},
        ]
        result = self._call(valid, lows=[1, 1], highs=[3, 2])
        assert result is None

    def test_forward_and_reverse_game1_noncont_returns_none(self):
        """Forward fails (game1 frozenset non-contiguous); reverse fails (game1 list non-contiguous).

        valid_2d = {(1,1),(1,3),(2,1),(2,3)}
        Forward: frozenset({1,3}) → game0=[1,2] (contiguous), but p_sorted=[1,3]
                 non-contiguous → fails at line 270-271.
        Reverse: frozenset({1,2}) → game1=[1,3] non-contiguous → fails at line 309-310.
        Returns None (line 337).
        """
        valid = [
            {_AB: 1, _CD: 1}, {_AB: 1, _CD: 3},
            {_AB: 2, _CD: 1}, {_AB: 2, _CD: 3},
        ]
        result = self._call(valid, lows=[1, 1], highs=[2, 3])
        assert result is None


class TestDeriveAtom:
    """Synthetic tests for _derive_atom — all-margins-valid and unconstrained fallback paths."""

    def test_all_margins_valid_returns_unconstrained_atom(self):
        """all_margins_valid=True skips margin iteration and returns one unconstrained atom (lines 404-410)."""
        result = _derive_atom(
            mask=_SYNTH_MASK,
            valid_margins_list=[],  # not consulted when all_margins_valid=True
            remaining=_SYNTH_REMAINING,
            pairs=_SYNTH_PAIRS,
            all_margins_valid=True,
        )
        assert len(result) == 1
        atom = result[0]
        grs = [c for c in atom if isinstance(c, GameResult)]
        assert len(grs) == 2
        assert all(gr.min_margin == 1 and gr.max_margin is None for gr in grs)
        assert not any(isinstance(c, MarginCondition) for c in atom)

    def test_unconstrained_per_game_fallback(self):
        """Joint constraints alone reproduce valid_2d → per-game bounds dropped (lines 504-510).

        valid_2d = {(1,1),(1,2),(2,1)} = all (v0,v1) in [1,12]² with v0+v1 <= 3.
        predicted_full([1,12]×[1,12], sum<=3) equals valid_2d, so the unconstrained
        GameResult path fires and the atom has max_margin=None for both games.
        """
        valid = [
            {_AB: 1, _CD: 1}, {_AB: 1, _CD: 2}, {_AB: 2, _CD: 1},
        ]
        result = _derive_atom(
            mask=_SYNTH_MASK,
            valid_margins_list=valid,
            remaining=_SYNTH_REMAINING,
            pairs=_SYNTH_PAIRS,
        )
        assert len(result) == 1
        atom = result[0]
        grs = [c for c in atom if isinstance(c, GameResult)]
        assert all(gr.max_margin is None for gr in grs), "GameResults should be unconstrained"
        mcs = [c for c in atom if isinstance(c, MarginCondition)]
        assert len(mcs) == 1
        assert mcs[0].op == "<=" and mcs[0].threshold == 3


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
    """For every (mask, margins), each top-4 team's per-team atom covers the outcome.

    For each outcome this test:
    1. Resolves actual standings via resolve_standings_for_mask
    2. For each team at seeds 1–4, verifies at least one per-team atom is satisfied

    This cross-validates the per-team format (render_team_scenarios) against
    the division-scenario format (render_division_scenarios): if a team appears
    at seed k in a division scenario but has no per-team atom covering that
    outcome, the two formats are inconsistent.
    """
    atoms = _ATOMS_3_7A

    failures = []
    for mask, margins in _all_outcome_branches():
        order = resolve_standings_for_mask(
            teams_3_7a,
            expected_3_7a_completed_games,
            _REMAINING,
            mask,
            margins,
            _BASE_MARGIN_DEFAULT,
            _PA_WIN,
        )
        for seed_idx in range(4):
            team = order[seed_idx]
            seed = seed_idx + 1
            team_seed_atoms = atoms.get(team, {}).get(seed, [])
            if not any(_atom_satisfied(atom, mask, margins) for atom in team_seed_atoms):
                failures.append(
                    f"{team} seed {seed}: mask={mask} margins={margins} "
                    f"not covered by any per-team atom "
                    f"(full order: {tuple(order)})"
                )

    assert not failures, (
        f"{len(failures)} per-team / division inconsistencies:\n"
        + "\n".join(failures[:5])
    )


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
_4_4A_COMPLETED = get_completed_games(
    expand_results([g for g in _4_4A_ALL if g["date"] <= _4_4A_CUTOFF])
)
_4_4A_REMAINING = [
    RemainingGame(*sorted([g["winner"], g["loser"]]))
    for g in _4_4A_ALL
    if g["date"] > _4_4A_CUTOFF
]

# Compute both paths once at module level for efficiency.
_ATOMS_DIRECT = build_scenario_atoms(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)
_SCENARIOS_DIRECT = enumerate_division_scenarios(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)

_PRECOMPUTED = enumerate_outcomes(_4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING)
_ATOMS_PRE = build_scenario_atoms(
    _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED
)
_SCENARIOS_PRE = enumerate_division_scenarios(
    _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING,
    scenario_atoms=_ATOMS_PRE, precomputed=_PRECOMPUTED,
)


def test_precomputed_atoms_teams_match():
    """Precomputed path produces atoms for the same set of teams."""
    assert set(_ATOMS_PRE.keys()) == set(_ATOMS_DIRECT.keys())


def test_precomputed_atoms_seeds_match():
    """Precomputed path produces atoms for the same seeds per team."""
    for team in _ATOMS_DIRECT:
        assert set(_ATOMS_PRE[team].keys()) == set(_ATOMS_DIRECT[team].keys()), \
            f"{team}: seed keys differ"


def test_precomputed_atoms_count_match():
    """Precomputed path produces the same number of atoms per (team, seed)."""
    for team in _ATOMS_DIRECT:
        for seed in _ATOMS_DIRECT[team]:
            assert len(_ATOMS_PRE[team][seed]) == len(_ATOMS_DIRECT[team][seed]), \
                f"{team} seed {seed}: atom count differs"


def test_precomputed_scenarios_count_match():
    """Precomputed path produces the same number of division scenarios."""
    assert len(_SCENARIOS_PRE) == len(_SCENARIOS_DIRECT)


def test_precomputed_scenarios_seedings_match():
    """Precomputed path produces identical seedings in the same order."""
    for i, (pre, direct) in enumerate(zip(_SCENARIOS_PRE, _SCENARIOS_DIRECT)):
        assert pre["seeding"] == direct["seeding"], \
            f"Scenario {i}: seeding differs — pre={pre['seeding']} direct={direct['seeding']}"
        assert pre["scenario_num"] == direct["scenario_num"], \
            f"Scenario {i}: scenario_num differs"
        assert pre["sub_label"] == direct["sub_label"], \
            f"Scenario {i}: sub_label differs"
        assert pre["game_winners"] == direct["game_winners"], \
            f"Scenario {i}: game_winners differs"


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
    wl_outcomes = enumerate_outcomes(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True
    )
    # One seeding per mask — all masks are non-sensitive in ignore_margins mode.
    assert len(wl_outcomes.non_sensitive_masks) == 1 << 4
    assert len(wl_outcomes.groups) == 1 << 4


def test_ignore_margins_atoms_cover_all_teams():
    """Win/loss-only atoms are produced for every team (no margin conditions)."""
    wl_outcomes = enumerate_outcomes(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True
    )
    wl_atoms = build_scenario_atoms(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=wl_outcomes
    )
    # Every team that appears in the full atoms should also appear in win/loss-only atoms.
    assert set(wl_atoms.keys()) == set(_ATOMS_DIRECT.keys())


def test_ignore_margins_no_margin_conditions():
    """Win/loss-only atoms contain no MarginCondition objects."""
    from backend.helpers.data_classes import MarginCondition as MC
    wl_outcomes = enumerate_outcomes(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, ignore_margins=True
    )
    wl_atoms = build_scenario_atoms(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=wl_outcomes
    )
    for team, seed_map in wl_atoms.items():
        for seed, atom_list in seed_map.items():
            for atom in atom_list:
                for cond in atom:
                    assert not isinstance(cond, MC), \
                        f"{team} seed {seed}: unexpected MarginCondition in win/loss-only atom"


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
        assert auto["seeding"] == direct["seeding"], \
            f"Scenario {i}: seeding differs — auto={auto['seeding']} direct={direct['seeding']}"
        assert auto["scenario_num"] == direct["scenario_num"], \
            f"Scenario {i}: scenario_num differs"
        assert auto["sub_label"] == direct["sub_label"], \
            f"Scenario {i}: sub_label differs"
        assert auto["game_winners"] == direct["game_winners"], \
            f"Scenario {i}: game_winners differs"


def test_enumerate_division_scenarios_auto_build_atoms_conditions_populated():
    """Margin-sensitive scenarios in the auto-build path have conditions_atom populated."""
    scenarios_auto = enumerate_division_scenarios(
        _4_4A_TEAMS, _4_4A_COMPLETED, _4_4A_REMAINING, precomputed=_PRECOMPUTED
    )
    ms_scenarios = [sc for sc in scenarios_auto if sc["sub_label"] != ""]
    assert len(ms_scenarios) > 0, "Expected at least one margin-sensitive sub-scenario in 4-4A"
    for sc in ms_scenarios:
        assert sc["conditions_atom"] is not None, \
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: conditions_atom is None in auto-build path"


# ---------------------------------------------------------------------------
# R=0 early exit — post-season fixture (all games complete)
# ---------------------------------------------------------------------------

# Use 4-4A with cutoff after the last game — R=0.
_4_4A_FINAL_CUTOFF = "2025-11-01"
_4_4A_COMPLETED_FULL = get_completed_games(
    expand_results([g for g in _4_4A_ALL if g["date"] <= _4_4A_FINAL_CUTOFF])
)
_4_4A_REMAINING_ZERO = [
    RemainingGame(*sorted([g["winner"], g["loser"]]))
    for g in _4_4A_ALL
    if g["date"] > _4_4A_FINAL_CUTOFF
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
# Synthetic gap-closure tests — scenario_viewer.py internal helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _find_combined_atom — line 142→123: CoinFlipResult in atom is silently skipped
# ---------------------------------------------------------------------------


class TestFindCombinedAtomCoinFlipResult:
    """_find_combined_atom skips CoinFlipResult conditions (line 142→123 branch)."""

    def test_coin_flip_result_in_atom_is_skipped(self):
        """CoinFlipResult in an atom passes the satisfied_by check but is not
        processed as GameResult or MarginCondition, exercising the 142→123 branch."""
        remaining = [RemainingGame("A", "B")]
        # Atom contains a real GameResult plus a CoinFlipResult.
        # CoinFlipResult.satisfied_by always returns True, so the atom is found.
        atom = [
            GameResult("A", "B", min_margin=1, max_margin=None),
            CoinFlipResult(winner="A", loser="C"),
        ]
        scenario_atoms = {"A": {1: [atom]}}
        seeding = ("A", "C")
        mask = 1  # bit 0 = 1 → A wins
        sample_margins = {("A", "B"): 7}

        result = _find_combined_atom(seeding, 2, mask, sample_margins, scenario_atoms, remaining)

        # The CoinFlipResult is skipped; the GameResult is captured normally.
        assert result is not None
        game_results = [c for c in result if isinstance(c, GameResult)]
        assert len(game_results) == 1
        assert game_results[0].winner == "A"

    def test_atom_with_only_coin_flip_result_returns_empty_list(self):
        """When the atom contains only a CoinFlipResult, the combined atom has no
        game or margin conditions (result is an empty list, not None)."""
        remaining = [RemainingGame("A", "B")]
        atom = [CoinFlipResult(winner="A", loser="B")]
        scenario_atoms = {"A": {1: [atom]}}
        seeding = ("A",)
        mask = 1
        sample_margins = {("A", "B"): 7}

        result = _find_combined_atom(seeding, 1, mask, sample_margins, scenario_atoms, remaining)

        # found_any=True, but no GameResult/MarginCondition collected → empty list returned
        assert result == []


# ---------------------------------------------------------------------------
# _eval_mc — line 217: unknown operator falls through to return True
# ---------------------------------------------------------------------------


class TestEvalMcUnknownOperator:
    """_eval_mc returns True for an unrecognised operator (line 217 fallback)."""

    def test_gt_operator_returns_true(self):
        """op='>' is not one of '<=', '>=', '==' — line 217 fires and returns True."""
        mc = MarginCondition(add=(("A", "B"),), sub=(), op=">", threshold=5)
        margins = {("A", "B"): 3}  # value 3 is NOT > 5, but fallback returns True anyway
        assert _eval_mc(mc, margins) is True

    def test_lt_operator_returns_true(self):
        """op='<' also exercises the unknown-operator fallback."""
        mc = MarginCondition(add=(("A", "B"),), sub=(), op="<", threshold=1)
        margins = {("A", "B"): 5}  # value 5 is NOT < 1, but fallback returns True
        assert _eval_mc(mc, margins) is True


# ---------------------------------------------------------------------------
# _derive_atom — line 445→447: 1 sensitive game, non-rectangular, split returns None
# ---------------------------------------------------------------------------


class TestDeriveAtomSingleSensitiveSplitFails:
    """_derive_atom falls back to [atom] when split returns None (line 445→447)."""

    def test_one_sensitive_game_noncontiguous_margins(self):
        """With R=1 and a non-contiguous valid set (e.g. {3, 5}), _split_non_rectangular_atom
        returns None (its inner loop never runs for R=1), so line 447 fires."""
        remaining = [RemainingGame("A", "B")]
        pairs = [("A", "B")]
        # Valid margins: only 3 and 5 — skips 4. Range [3,5] has 3 values but only 2 are valid.
        valid_margins_list = [{("A", "B"): 3}, {("A", "B"): 5}]
        mask = 1  # A wins bit 0

        result = _derive_atom(mask, valid_margins_list, remaining, pairs, all_margins_valid=False)

        # Should return a single broad atom covering [3, 6) (max_margin=hi+1=5+1=6)
        assert len(result) == 1
        atom = result[0]
        assert len(atom) == 1
        gr = atom[0]
        assert isinstance(gr, GameResult)
        assert gr.winner == "A"
        assert gr.min_margin == 3
        assert gr.max_margin == 6  # exclusive: 5+1=6


# ---------------------------------------------------------------------------
# _derive_atom — line 526: 2 sensitive games, predicted set doesn't match, split fails
# ---------------------------------------------------------------------------


class TestDeriveAtomTwoSensitiveSplitFails:
    """_derive_atom fallback [atom] when predicted set ≠ valid set and split fails (line 526)."""

    def test_diamond_valid_set_forces_fallback(self):
        """valid_2d = {(1,2),(2,1),(3,2),(2,3)} — a diamond pattern.

        The sum constraint IS binding (sum in [3,5]), so margin_conds is non-empty
        and the early-return at line 496 is not taken.  The sum constraint doesn't
        fully reproduce the valid set (predicted has 7 points vs actual 4), so
        line 514 isn't taken either.  Both forward and reverse groupings in
        _split_non_rectangular_atom have non-contiguous outer indices ([1,3] missing
        2), so it returns None.  Line 526 fires.
        """
        remaining = [RemainingGame("A", "B"), RemainingGame("C", "D")]
        pairs = [("A", "B"), ("C", "D")]
        # Diamond: four corners of a rotated square in margin space
        valid_margins_list = [
            {("A", "B"): 1, ("C", "D"): 2},
            {("A", "B"): 2, ("C", "D"): 1},
            {("A", "B"): 3, ("C", "D"): 2},
            {("A", "B"): 2, ("C", "D"): 3},
        ]
        mask = 3  # both A and C win

        result = _derive_atom(mask, valid_margins_list, remaining, pairs, all_margins_valid=False)

        # Fallback: single broad atom [GameResult(A,B,1,4), GameResult(C,D,1,4)]
        # (lows=[1,1], highs=[3,3] → max_margin=4 for both)
        assert len(result) == 1
        atom = result[0]
        gr_ab = next(c for c in atom if isinstance(c, GameResult) and c.winner == "A")
        assert gr_ab.min_margin == 1
        assert gr_ab.max_margin == 4
        gr_cd = next(c for c in atom if isinstance(c, GameResult) and c.winner == "C")
        assert gr_cd.min_margin == 1
        assert gr_cd.max_margin == 4


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
        atom2 = [GameResult("B", "A", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=5, max_margin=None)]

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
        atom2 = [GameResult("B", "A", min_margin=1, max_margin=None), GameResult("G", "H", min_margin=5, max_margin=None)]

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
        """When scenario_atoms is an empty dict (falsy), the margin-sensitive
        sub-scenario path at line 1640 takes the False branch, leaving
        conditions_atom=None for all sub-scenarios."""
        # Use the 3-7A fixture which has margin-sensitive scenarios.
        scenarios = enumerate_division_scenarios(
            teams_3_7a,
            expected_3_7a_completed_games,
            _REMAINING,
            scenario_atoms={},  # explicitly empty — falsy, bypasses auto-build
        )

        ms_scenarios = [sc for sc in scenarios if sc["sub_label"] != ""]
        assert len(ms_scenarios) > 0, "Need at least one margin-sensitive sub-scenario"

        for sc in ms_scenarios:
            assert sc["conditions_atom"] is None, (
                f"Scenario {sc['scenario_num']}{sc['sub_label']}: expected None "
                f"but got {sc['conditions_atom']}"
            )


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
            GameResult("Phi", "Rho", 1, None),    # comp: Phi beats Rho, unc
            GameResult("Gamma", "Delta", 1, 4),   # tight (narrow): GD [1,4)
            GameResult("Alpha", "Beta", 1, None), # shared: Alpha beats Beta, unc
        ]
        atom1 = [
            GameResult("Rho", "Phi", 1, None),    # comp (opposite): Rho beats Phi, unc
            GameResult("Gamma", "Delta", 1, 7),   # tight (wide): GD [1,7)
            GameResult("Alpha", "Beta", 1, None), # shared: same as atom0
        ]
        atom_x = [
            GameResult("Gamma", "Delta", 3, None),  # tight (tighter): GD [3,∞)
            GameResult("Beta", "Alpha", 1, None),   # shared (opposite): Beta beats Alpha, unc
        ]

        result = _simplify_atom_list([atom0, atom1, atom_x])

        assert result == [
            [GameResult("Gamma", "Delta", 1, 4), GameResult("Alpha", "Beta", 1, None)],
            [GameResult("Gamma", "Delta", 3, None)],
        ]


# ---------------------------------------------------------------------------
# Partial-results fixtures — 3-7A with some final-week games already known
# ---------------------------------------------------------------------------

_GAME_BRN_MER = CompletedGame("Brandon",          "Meridian", 1, 27, 13, 40)
_GAME_OG_PRL  = CompletedGame("Oak Grove",        "Pearl",    1, 21,  7, 28)
_GAME_NWR_PET = CompletedGame("Northwest Rankin", "Petal",    1,  6, 28, 34)

# Partial A: Brandon/Meridian settled; OG/Pearl and NWR/Petal still TBD
_COMPLETED_PA = sorted(
    expected_3_7a_completed_games + [_GAME_BRN_MER], key=lambda g: (g.a, g.b)
)
_REMAINING_PA = [RemainingGame("Oak Grove", "Pearl"), RemainingGame("Northwest Rankin", "Petal")]
_PAIRS_PA = [(rg.a, rg.b) for rg in _REMAINING_PA]
_SCENARIOS_PA = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PA, _REMAINING_PA)

# Partial B: Brandon + OG/Pearl settled; NWR/Petal still TBD
_COMPLETED_PB = sorted(
    expected_3_7a_completed_games + [_GAME_BRN_MER, _GAME_OG_PRL], key=lambda g: (g.a, g.b)
)
_REMAINING_PB = [RemainingGame("Northwest Rankin", "Petal")]
_PAIRS_PB = [(rg.a, rg.b) for rg in _REMAINING_PB]
_SCENARIOS_PB = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PB, _REMAINING_PB)

# Partial C: Brandon + NWR/Petal settled (n=6); OG/Pearl still TBD
_COMPLETED_PC = sorted(
    expected_3_7a_completed_games + [_GAME_BRN_MER, _GAME_NWR_PET], key=lambda g: (g.a, g.b)
)
_REMAINING_PC = [RemainingGame("Oak Grove", "Pearl")]
_PAIRS_PC = [(rg.a, rg.b) for rg in _REMAINING_PC]
_SCENARIOS_PC = enumerate_division_scenarios(teams_3_7a, _COMPLETED_PC, _REMAINING_PC)


# ---------------------------------------------------------------------------
# Partial A — Brandon/Meridian known, 2 remaining (OG/Pearl, NWR/Petal)
# ---------------------------------------------------------------------------


def test_partial_a_scenario_count():
    """Partial A (Brandon/Meridian known) produces 15 distinct scenarios."""
    assert len(_SCENARIOS_PA) == 15


def test_partial_a_scenario_labels():
    """Partial A has 12 sub-labeled scenarios (3a–3l) and 3 unlabeled (1, 2, 4)."""
    labeled = [sc for sc in _SCENARIOS_PA if sc["sub_label"]]
    unlabeled = [sc for sc in _SCENARIOS_PA if not sc["sub_label"]]
    assert len(labeled) == 12
    assert all(sc["scenario_num"] == 3 for sc in labeled)
    assert sorted(sc["sub_label"] for sc in labeled) == list("abcdefghijkl")
    assert {sc["scenario_num"] for sc in unlabeled} == {1, 2, 4}


def test_partial_a_deterministic_seedings():
    """Partial A deterministic scenarios (1, 2, 4) produce the expected top-4 seedings."""
    single = {sc["scenario_num"]: sc["seeding"][:4] for sc in _SCENARIOS_PA if not sc["sub_label"]}
    assert single[1] == ("Petal", "Pearl", "Oak Grove", "Brandon")
    assert single[2] == ("Petal", "Oak Grove", "Brandon", "Northwest Rankin")
    assert single[4] == ("Oak Grove", "Petal", "Brandon", "Northwest Rankin")


def test_partial_a_backward_coverage():
    """Every (mask, margins) over 2 remaining games is covered by some Partial A scenario seeding."""
    seeding_map = {sc["seeding"] for sc in _SCENARIOS_PA}
    failures = []
    for mask in range(1 << 2):
        for m0, m1 in product(range(1, 13), repeat=2):
            margins = {_PAIRS_PA[0]: m0, _PAIRS_PA[1]: m1}
            order = resolve_standings_for_mask(
                teams_3_7a, _COMPLETED_PA, _REMAINING_PA,
                mask, margins, _BASE_MARGIN_DEFAULT, _PA_WIN,
            )
            if tuple(order) not in seeding_map:
                failures.append(f"mask={mask} margins={margins}: {tuple(order)} not in scenarios")
    assert not failures, f"{len(failures)} uncovered:\n" + "\n".join(failures[:3])


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
                teams_3_7a, _COMPLETED_PA, _REMAINING_PA,
                mask, margins, _BASE_MARGIN_DEFAULT, _PA_WIN,
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
            f"Scenario {sc['scenario_num']}: expected no conditions_atom "
            f"but got {sc['conditions_atom']}"
        )


def test_partial_b_backward_coverage():
    """Every (mask, margin) with 1 remaining NWR/Petal game maps to a Partial B scenario seeding."""
    seeding_map = {sc["seeding"] for sc in _SCENARIOS_PB}
    failures = []
    for mask in range(1 << 1):
        for m in range(1, 13):
            margins = {_PAIRS_PB[0]: m}
            order = resolve_standings_for_mask(
                teams_3_7a, _COMPLETED_PB, _REMAINING_PB,
                mask, margins, _BASE_MARGIN_DEFAULT, _PA_WIN,
            )
            if tuple(order) not in seeding_map:
                failures.append(f"mask={mask} margin={m}: {tuple(order)} not in scenarios")
    assert not failures, f"{len(failures)} uncovered:\n" + "\n".join(failures)


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
    """Every (mask, margin) with 1 remaining OG/Pearl game maps to a Partial C scenario seeding."""
    seeding_map = {sc["seeding"] for sc in _SCENARIOS_PC}
    failures = []
    for mask in range(1 << 1):
        for m in range(1, 13):
            margins = {_PAIRS_PC[0]: m}
            order = resolve_standings_for_mask(
                teams_3_7a, _COMPLETED_PC, _REMAINING_PC,
                mask, margins, _BASE_MARGIN_DEFAULT, _PA_WIN,
            )
            if tuple(order) not in seeding_map:
                failures.append(f"mask={mask} margin={m}: {tuple(order)} not in scenarios")
    assert not failures, f"{len(failures)} uncovered:\n" + "\n".join(failures)


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
                teams_3_7a, _COMPLETED_PC, _REMAINING_PC,
                mask, margins, _BASE_MARGIN_DEFAULT, _PA_WIN,
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
Eliminated: Northwest Rankin, Meridian

Scenario 2: Oak Grove beats Pearl AND Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian

Scenario 3a: Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Oak Grove
2. Petal
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 3b: Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Pearl
Eliminated: Brandon, Meridian

Scenario 3c: Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Oak Grove
2. Northwest Rankin
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 3d: Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Northwest Rankin
2. Oak Grove
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 3e: Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Petal
2. Oak Grove
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 3f: Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Petal
2. Oak Grove
3. Pearl
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 3g: Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Petal
2. Pearl
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 3h: Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 3i: Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Northwest Rankin
2. Pearl
3. Oak Grove
4. Petal
Eliminated: Brandon, Meridian

Scenario 3j: Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Pearl
2. Petal
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 3k: Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Pearl
2. Northwest Rankin
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 3l: Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Pearl
2. Petal
3. Northwest Rankin
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4: Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian"""


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
Eliminated: Pearl, Meridian

Scenario 2: Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian"""


def test_partial_b_render_full_output():
    """Full rendered output for Partial B matches expected text exactly.

    Golden-file regression test: update _EXPECTED_PARTIAL_B_RENDER when output changes intentionally.
    """
    result = render_scenarios(_SCENARIOS_PB)
    assert result == _EXPECTED_PARTIAL_B_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_PARTIAL_B_RENDER}\n--- ACTUAL ---\n{result}"
    )


_EXPECTED_PARTIAL_C_RENDER = """\
Scenario 1a: Pearl beats Oak Grove by 1\u20133
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

Scenario 1d: Pearl beats Oak Grove by 6\u20137
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
Eliminated: Pearl, Meridian"""


def test_partial_c_render_full_output():
    """Full rendered output for Partial C matches expected text exactly.

    Golden-file regression test: update _EXPECTED_PARTIAL_C_RENDER when output changes intentionally.
    """
    result = render_scenarios(_SCENARIOS_PC)
    assert result == _EXPECTED_PARTIAL_C_RENDER, (
        f"\n--- EXPECTED ---\n{_EXPECTED_PARTIAL_C_RENDER}\n--- ACTUAL ---\n{result}"
    )


def test_partial_c_consistent_with_partial_a():
    """With NWR/Petal fixed at n=6, each Partial C scenario maps to the expected Partial A scenario.

    Correspondence (NWR wins by 6), using new ascending-margin sub-labels:
      PC 1a (p=1)  → PA 3b  (p∈[1,5], n∈[4,8], p+n≤9  → 1+6=7 ✓)
      PC 1b (p=4)  → PA 3c  (p∈[1,5], n∈[5,9], p+n=10 → 4+6=10 ✓)
      PC 1c (p=5)  → PA 3d  (p∈[1,5], n≥6, p+n≥11     → 5+6=11 ✓)
      PC 1d (p=6)  → PA 3i  (p≥6, n≥5, p–n≤1)
      PC 1e (p=8)  → PA 3h  (p≥6, n∈[4,10], p–n=2     → 8–6=2 ✓)
      PC 1f (p=9)  → PA 3k  (p≥7, n∈[4,9], p–n≥3      → 9–6=3 ✓)
      PC 2         → PA 4   (OG wins, NWR wins)
    """
    pa_seeding_to_label = {
        sc["seeding"]: f"{sc['scenario_num']}{sc['sub_label']}"
        for sc in _SCENARIOS_PA
    }

    # (pc_key, sample_p for Pearl-wins cases or None for OG-wins, expected_pa_label)
    cases = [
        ("1a", 1,    "3b"),
        ("1b", 4,    "3c"),
        ("1c", 5,    "3d"),
        ("1d", 6,    "3i"),
        ("1e", 8,    "3h"),
        ("1f", 9,    "3k"),
        ("2",  None, "4"),
    ]

    # _REMAINING_PA: index 0 = OG/Pearl (bit 0=1 → OG wins), index 1 = NWR/Petal (bit 1=1 → NWR wins)
    _og_pearl  = _PAIRS_PA[0]
    _nwr_petal = _PAIRS_PA[1]
    _n = 6  # NWR beats Petal by 6

    failures = []
    for pc_key, p, expected_pa in cases:
        if p is None:  # OG wins the Pearl game
            mask_pc   = 1       # bit 0=1 → OG wins
            mask_pa   = 0b11    # bit 0=OG wins, bit 1=NWR wins
            margins_pc = {_PAIRS_PC[0]: 7}
            margins_pa = {_og_pearl: 7, _nwr_petal: _n}
        else:          # Pearl wins the OG game
            mask_pc   = 0       # bit 0=0 → Pearl wins
            mask_pa   = 0b10    # bit 0=Pearl wins, bit 1=NWR wins
            margins_pc = {_PAIRS_PC[0]: p}
            margins_pa = {_og_pearl: p, _nwr_petal: _n}

        seeding_pc = tuple(resolve_standings_for_mask(
            teams_3_7a, _COMPLETED_PC, _REMAINING_PC,
            mask_pc, margins_pc, _BASE_MARGIN_DEFAULT, _PA_WIN,
        ))
        seeding_pa = tuple(resolve_standings_for_mask(
            teams_3_7a, _COMPLETED_PA, _REMAINING_PA,
            mask_pa, margins_pa, _BASE_MARGIN_DEFAULT, _PA_WIN,
        ))

        if seeding_pc != seeding_pa:
            failures.append(
                f"PC {pc_key} (p={p}, n={_n}): seedings differ — "
                f"PC={seeding_pc}, PA={seeding_pa}"
            )
            continue

        actual_pa = pa_seeding_to_label.get(seeding_pa, "?")
        if actual_pa != expected_pa:
            failures.append(
                f"PC {pc_key} (p={p}, n={_n}): PA scenario is {actual_pa}, expected {expected_pa}"
            )

    assert not failures, "\n".join(failures)
