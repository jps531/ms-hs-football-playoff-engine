"""Tests for scenario_viewer: enumerate_division_scenarios and render_division_scenarios."""

from itertools import product

from backend.helpers.data_classes import GameResult, MarginCondition, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import _render_margin_condition
from backend.helpers.scenario_viewer import (
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


def test_4d_has_exact_sum_condition():
    """Scenario 4d's atom includes a 'combined total exactly 10' condition."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sc_4d = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "d")
    assert sc_4d is not None
    atom = sc_4d["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    assert any(c.threshold == 10 for c in eq_conds)


def test_4j_has_exact_diff_condition():
    """Scenario 4j's atom includes a 'diff exactly 2' condition (Pearl exceeds NWR by exactly 2)."""
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=expected_3_7a_scenarios,
    )
    sc_4j = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "j")
    assert sc_4j is not None
    atom = sc_4j["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    # diff == -2 means NWR_margin - Pearl_margin == -2, i.e. Pearl exceeds NWR by exactly 2
    assert any(c.threshold == -2 and len(c.add) == 1 and len(c.sub) == 1 for c in eq_conds)


def test_4c_has_exact_diff_condition():
    """Scenario 4c's atom includes a 'diff exactly 2' condition (Pearl exceeds NWR by exactly 2).

    Uses build_scenario_atoms (algorithmic) because the hand-crafted fixture encodes the
    n=4, p=6 boundary as exact GameResult bounds with no MarginCondition, so the sample
    point for 4c falls there and no diff condition appears from the hand-crafted atoms.
    The algorithmic atoms always carry the diff constraint explicitly.
    """
    scenarios = _SCENARIOS_3_7A
    sc_4c = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "c")
    atom = sc_4c["conditions_atom"]
    eq_conds = [c for c in atom if isinstance(c, MarginCondition) and c.op == "=="]
    assert len(eq_conds) >= 1
    # Either add=Pearl/sub=NWR with threshold=2 or add=NWR/sub=Pearl with threshold=-2 —
    # both encode "Pearl's margin exceeds NWR's by exactly 2"
    assert any(
        abs(c.threshold) == 2 and len(c.add) == 1 and len(c.sub) == 1 for c in eq_conds
    )


def test_4i_has_exact_sum_condition():
    """Scenario 4i's atom includes a 'combined total exactly 10' condition.

    Uses build_scenario_atoms (algorithmic) for the same reason as test_4c above.
    """
    scenarios = _SCENARIOS_3_7A
    sc_4i = next(sc for sc in scenarios if sc["scenario_num"] == 4 and sc["sub_label"] == "i")
    atom = sc_4i["conditions_atom"]
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

Scenario 4a: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Northwest Rankin
2. Oak Grove
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4b: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Northwest Rankin
2. Pearl
3. Oak Grove
4. Petal
Eliminated: Brandon, Meridian

Scenario 4c: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4d: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Oak Grove
2. Northwest Rankin
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4e: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4f: Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Oak Grove
2. Petal
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4g: Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Pearl
2. Northwest Rankin
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4h: Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Pearl
2. Petal
3. Northwest Rankin
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4i: Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Pearl
2. Petal
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4j: Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Petal
2. Oak Grove
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4k: Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Petal
2. Oak Grove
3. Pearl
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4l: Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Petal
2. Pearl
3. Oak Grove
4. Northwest Rankin
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
