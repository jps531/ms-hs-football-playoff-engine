"""Tests for scenario_viewer: enumerate_division_scenarios and render_division_scenarios."""

from itertools import product

from backend.helpers.data_classes import GameResult, MarginCondition
from backend.helpers.scenario_renderer import _render_margin_condition
from backend.helpers.scenario_viewer import enumerate_division_scenarios, render_division_scenarios
from backend.helpers.tiebreakers import resolve_standings_for_mask
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


def test_render_without_atoms_uses_game_winners():
    """Without scenario_atoms, render uses plain game winners (no margin conditions)."""
    output = render_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        _REMAINING,
        scenario_atoms=None,
    )
    # Should still have 17 scenarios (Scenario 1–6 with 4a–4l for the margin-sensitive mask)
    assert output.count("Scenario 4") == 12  # exactly 4a through 4l
    # No "exactly" or "or more" phrases (no margin condition text)
    assert "or more" not in output
    assert "or less" not in output
    assert "exactly" not in output


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
# 4d and 4j: verify "==" simplification was applied
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
