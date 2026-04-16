"""Scenario output tests for Region 8-1A (2025 season, pre-final-week).

Region 8-1A exercises several code paths not present in the fully-determined
Region 5-3A case:

  - **Multiple scenarios** — 4 distinct seeding outcomes (keyed "1", "2a", "2b", "3").
  - **Margin-sensitive sub-scenarios** — When Stringer beats Resurrection AND
    Lumberton beats Taylorsville, the 3-way tie (Taylorsville, Stringer, Lumberton
    all 3-1) is resolved by H2H point differential (Step 3, ±12 cap), NOT a coin
    flip.  Two sub-scenarios emerge from the same game_winners (ascending margin order):
      "2a": Lumberton wins by 1-11  → Taylorsville #1 (PD still favors Taylorsville)
      "2b": Lumberton wins by 12+   → Lumberton #1 (cap zeroes all three; later steps
            break the remaining tie in Lumberton's favour)
    The ±12 threshold is the tiebreaker's H2H PD cap, not a coin-flip boundary.
  - **Teams spanning two seeds** — Taylorsville can land at #1 or #2; Lumberton at
    #1 or #3; Stringer at #2 or #3.
  - **Clinched single seed** — Richton is always #4; Resurrection is always
    eliminated.

Remaining games (2, cutoff 2025-10-24):
  Resurrection vs Stringer  — Stringer beat Resurrection 40-7 (actual)
  Lumberton vs Taylorsville — Taylorsville beat Lumberton 32-7 (actual)

Known 2025 seeds: Taylorsville / Stringer / Lumberton / Richton
"""

import pytest

from backend.helpers.data_classes import GameResult, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import (
    division_scenarios_as_dict,
    render_team_scenarios,
    team_scenarios_as_dict,
)
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games

# ---------------------------------------------------------------------------
# Shared fixtures (module-level, built once)
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(1, 8)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)  # alphabetical: Lumberton, Resurrection, Richton, Stringer, Taylorsville
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

LUMBERTON_EXPECTED = """\
Lumberton

#1 seed if: (27.1%)
1. Lumberton beats Taylorsville by 12 or more
2. Resurrection beats Stringer AND Lumberton beats Taylorsville

#3 seed if: (72.9%)
1. Taylorsville beats Lumberton
2. Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311"""

RESURRECTION_EXPECTED = "Resurrection\n\nEliminated. (100.0%)"

RICHTON_EXPECTED = "Richton\n\nClinched #4 seed. (100.0%)"

STRINGER_EXPECTED = """\
Stringer

#2 seed if: (72.9%)
1. Taylorsville beats Lumberton
2. Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311

#3 seed if: (27.1%)
1. Lumberton beats Taylorsville by 12 or more
2. Resurrection beats Stringer AND Lumberton beats Taylorsville"""

TAYLORSVILLE_EXPECTED = """\
Taylorsville

#1 seed if: (72.9%)
1. Taylorsville beats Lumberton
2. Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311

#2 seed if: (27.1%)
1. Lumberton beats Taylorsville by 12 or more
2. Resurrection beats Stringer AND Lumberton beats Taylorsville"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_taylorsville_has_seeds_1_and_2():
    """Taylorsville can finish #1 or #2."""
    assert set(_ATOMS["Taylorsville"].keys()) == {1, 2}


def test_atoms_lumberton_has_seeds_1_and_3():
    """Lumberton can finish #1 or #3 (never #2 due to H2H with Stringer)."""
    assert set(_ATOMS["Lumberton"].keys()) == {1, 3}


def test_atoms_stringer_has_seeds_2_and_3():
    """Stringer can finish #2 or #3."""
    assert set(_ATOMS["Stringer"].keys()) == {2, 3}


def test_atoms_richton_clinched_seed_4():
    """Richton is always #4 — boolean minimisation collapses all atoms to a single [[]]."""
    assert set(_ATOMS["Richton"].keys()) == {4}
    assert _ATOMS["Richton"][4] == [[]]


def test_atoms_resurrection_eliminated():
    """Resurrection's only entry is seed 5 (eliminated) with an unconditional atom."""
    assert set(_ATOMS["Resurrection"].keys()) == {5}
    assert _ATOMS["Resurrection"][5] == [[]]


# ---------------------------------------------------------------------------
# build_scenario_atoms — margin-sensitive conditions
# ---------------------------------------------------------------------------


def test_atoms_lumberton_seed1_margin_condition():
    """Lumberton's first seed-1 atom is a standalone 'wins by 12+' condition (no Stringer clause).

    Rule 3 simplification: [Resurrection+Lumb(any)] ∨ [Stringer+Lumb(12+)]
    becomes [Resurrection+Lumb(any)] ∨ [Lumb(12+)], dropping the Stringer game
    since 'Lumberton wins by 12+' is sufficient regardless of the Stringer result.
    Sorts first because it is shorter (1 game vs 2 games).
    """
    first_atom = _ATOMS["Lumberton"][1][0]
    assert len(first_atom) == 1, "first atom should have exactly one condition after Rule 3 simplification"
    margin_result = first_atom[0]
    assert isinstance(margin_result, GameResult)
    assert margin_result.winner == "Lumberton"
    assert margin_result.loser == "Taylorsville"
    assert margin_result.min_margin == 12
    assert margin_result.max_margin is None


def test_atoms_lumberton_seed3_margin_condition():
    """Lumberton's second seed-3 atom requires winning by 1-11 (max_margin=12)."""
    atom = _ATOMS["Lumberton"][3][1]
    margin_result = atom[1]
    assert isinstance(margin_result, GameResult)
    assert margin_result.winner == "Lumberton"
    assert margin_result.loser == "Taylorsville"
    assert margin_result.min_margin == 1
    assert margin_result.max_margin == 12


def test_atoms_taylorsville_seed1_two_atoms():
    """Taylorsville reaches #1 via two different game outcome combinations."""
    assert len(_ATOMS["Taylorsville"][1]) == 2


def test_atoms_taylorsville_seed1_atom1_direct_win():
    """Taylorsville seed-1 atom 1: Taylorsville beats Lumberton (direct win)."""
    atom = _ATOMS["Taylorsville"][1][0]
    assert len(atom) == 1
    assert atom[0] == GameResult("Taylorsville", "Lumberton")


def test_atoms_taylorsville_seed1_atom2_stringer_wins_lumberton_narrow():
    """Taylorsville seed-1 atom 2: Stringer beats Resurrection AND Lumberton wins by 1-11."""
    atom = _ATOMS["Taylorsville"][1][1]
    assert len(atom) == 2
    assert atom[0] == GameResult("Stringer", "Resurrection")
    assert atom[1] == GameResult("Lumberton", "Taylorsville", 1, 12)


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """Region 8-1A produces exactly 4 scenario entries (including 2a and 2b)."""
    assert len(_SCENARIOS) == 4


def test_scenario_keys():
    """Scenario labels are '1', '2a', '2b', and '3'."""
    keys = {str(sc["scenario_num"]) + sc["sub_label"] for sc in _SCENARIOS}
    assert keys == {"1", "2a", "2b", "3"}


def test_scenario_1_seeding():
    """Scenario 1 (Taylorsville beats Lumberton): Taylorsville / Stringer / Lumberton / Richton."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1)
    assert sc["seeding"][:4] == ("Taylorsville", "Stringer", "Lumberton", "Richton")
    assert sc["game_winners"] == [("Taylorsville", "Lumberton")]


def test_scenario_2a_seeding():
    """Scenario 2a (margin 1–11, ascending-margin order): Taylorsville / Stringer / Lumberton / Richton."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert sc["seeding"][:4] == ("Taylorsville", "Stringer", "Lumberton", "Richton")


def test_scenario_2b_seeding():
    """Scenario 2b (margin ≥12): Lumberton / Taylorsville / Stringer / Richton."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc["seeding"][:4] == ("Lumberton", "Taylorsville", "Stringer", "Richton")


def test_scenario_2a_2b_same_game_winners():
    """Scenarios 2a and 2b share the same game_winners (same W/L outcomes, different margins)."""
    sc2a = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc2a["game_winners"] == sc2b["game_winners"]
    assert sc2a["game_winners"] == [("Stringer", "Resurrection"), ("Lumberton", "Taylorsville")]


def test_scenario_3_seeding():
    """Scenario 3 (Resurrection beats Stringer, Lumberton beats Taylorsville): Lumberton / Taylorsville / Stringer / Richton."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 3)
    assert sc["seeding"][:4] == ("Lumberton", "Taylorsville", "Stringer", "Richton")


def test_all_scenarios_resurrection_eliminated():
    """Resurrection is the eliminated team in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][4] == "Resurrection"


def test_all_scenarios_richton_seed_4():
    """Richton is always seed 4."""
    for sc in _SCENARIOS:
        assert sc["seeding"][3] == "Richton"


def test_non_sub_scenarios_conditions_atom_none():
    """Non-sub-labeled scenarios (1 and 3) have conditions_atom=None."""
    for sc in _SCENARIOS:
        if sc["sub_label"] == "":
            assert sc["conditions_atom"] is None, (
                f"scenario {sc['scenario_num']} should have conditions_atom=None"
            )


def test_scenario_2a_conditions_atom():
    """Scenario 2a conditions_atom: Lumberton beats Taylorsville by 1–11 (ascending-margin order)."""
    sc2a = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    ca = sc2a["conditions_atom"]
    assert ca is not None, "conditions_atom should be populated for margin-sensitive sub-scenario"
    lb_gr = next(gr for gr in ca if gr.winner == "Lumberton")
    assert lb_gr.loser == "Taylorsville"
    assert lb_gr.min_margin == 1
    assert lb_gr.max_margin == 12  # exclusive upper bound → displayed as 1–11


def test_scenario_2b_conditions_atom():
    """Scenario 2b conditions_atom: Lumberton beats Taylorsville by 12 or more."""
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    ca = sc2b["conditions_atom"]
    assert ca is not None
    lb_gr = next(gr for gr in ca if gr.winner == "Lumberton")
    assert lb_gr.loser == "Taylorsville"
    assert lb_gr.min_margin == 12
    assert lb_gr.max_margin is None


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_keys():
    """Dict has exactly keys '1', '2a', '2b', '3'."""
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "3"}


def test_div_dict_entry_shape():
    """Every entry has the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"scenario {key!r} missing keys"


def test_div_dict_scenario_1():
    """Scenario 1: title, seeds, and eliminated."""
    entry = _DIV_DICT["1"]
    assert entry["title"] == "Taylorsville beats Lumberton"
    assert entry["one_seed"] == "Taylorsville"
    assert entry["two_seed"] == "Stringer"
    assert entry["three_seed"] == "Lumberton"
    assert entry["four_seed"] == "Richton"
    assert entry["eliminated"] == ["Resurrection"]


def test_div_dict_scenario_2a():
    """Scenario 2a (Lumberton wins by 1–11, ascending-margin order): Taylorsville gets seed 1."""
    entry = _DIV_DICT["2a"]
    assert entry["title"] == "Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311"
    assert entry["one_seed"] == "Taylorsville"
    assert entry["two_seed"] == "Stringer"
    assert entry["three_seed"] == "Lumberton"
    assert entry["four_seed"] == "Richton"


def test_div_dict_scenario_2b():
    """Scenario 2b (Lumberton wins by 12+): Lumberton gets seed 1; title is standalone margin condition."""
    entry = _DIV_DICT["2b"]
    assert entry["title"] == "Lumberton beats Taylorsville by 12 or more"
    assert entry["one_seed"] == "Lumberton"
    assert entry["two_seed"] == "Taylorsville"
    assert entry["three_seed"] == "Stringer"
    assert entry["four_seed"] == "Richton"


def test_div_dict_scenario_2a_2b_distinct_titles():
    """Margin-sensitive sub-scenarios have distinct margin-qualified titles (no longer share same string)."""
    assert _DIV_DICT["2a"]["title"] != _DIV_DICT["2b"]["title"]
    assert "1\u201311" in _DIV_DICT["2a"]["title"]
    assert "12 or more" in _DIV_DICT["2b"]["title"]


def test_div_dict_scenario_3():
    """Scenario 3: Resurrection upsets Stringer, Lumberton beats Taylorsville."""
    entry = _DIV_DICT["3"]
    assert entry["title"] == "Resurrection beats Stringer AND Lumberton beats Taylorsville"
    assert entry["one_seed"] == "Lumberton"
    assert entry["two_seed"] == "Taylorsville"
    assert entry["three_seed"] == "Stringer"
    assert entry["four_seed"] == "Richton"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_entry_shape():
    """Every seed/eliminated entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, f"{team!r} key {key!r} has wrong shape"


def test_team_dict_taylorsville_seeds():
    """Taylorsville has seed 1 and seed 2 entries, no eliminated key."""
    entry = _TEAM_DICT["Taylorsville"]
    assert set(entry.keys()) == {1, 2}


def test_team_dict_lumberton_seeds():
    """Lumberton has seed 1 and seed 3 entries, no eliminated key."""
    entry = _TEAM_DICT["Lumberton"]
    assert set(entry.keys()) == {1, 3}


def test_team_dict_stringer_seeds():
    """Stringer has seed 2 and seed 3 entries, no eliminated key."""
    entry = _TEAM_DICT["Stringer"]
    assert set(entry.keys()) == {2, 3}


def test_team_dict_richton_clinched_4():
    """Richton has only seed 4 with odds=1.0; unconditional atom produces one empty scenario string."""
    entry = _TEAM_DICT["Richton"]
    assert set(entry.keys()) == {4}
    assert entry[4]["odds"] == pytest.approx(1.0)
    assert entry[4]["scenarios"] == [""]


def test_team_dict_resurrection_eliminated():
    """Resurrection has only 'eliminated' with odds=1.0 and empty scenarios."""
    entry = _TEAM_DICT["Resurrection"]
    assert set(entry.keys()) == {"eliminated"}
    assert entry["eliminated"]["odds"] == pytest.approx(1.0)
    assert entry["eliminated"]["scenarios"] == []


def test_team_dict_taylorsville_seed1_odds():
    """Taylorsville seed-1 odds ≈ 72.9% (3 full outcomes + fractional margin-sensitive split)."""
    assert _TEAM_DICT["Taylorsville"][1]["odds"] == pytest.approx(0.7291666666666666)


def test_team_dict_taylorsville_seed2_odds():
    """Taylorsville seed-2 odds ≈ 27.1%."""
    assert _TEAM_DICT["Taylorsville"][2]["odds"] == pytest.approx(0.2708333333333333)


def test_team_dict_lumberton_seed1_odds():
    """Lumberton seed-1 odds ≈ 27.1%."""
    assert _TEAM_DICT["Lumberton"][1]["odds"] == pytest.approx(0.2708333333333333)


def test_team_dict_lumberton_seed3_odds():
    """Lumberton seed-3 odds ≈ 72.9%."""
    assert _TEAM_DICT["Lumberton"][3]["odds"] == pytest.approx(0.7291666666666666)


def test_team_dict_taylorsville_seed1_scenario_strings():
    """Taylorsville seed-1 has two scenario strings — direct win and narrow Lumberton win."""
    scenarios = _TEAM_DICT["Taylorsville"][1]["scenarios"]
    assert len(scenarios) == 2
    assert scenarios[0] == "Taylorsville beats Lumberton"
    assert scenarios[1] == "Stringer beats Resurrection AND Lumberton beats Taylorsville by 1\u201311"


def test_team_dict_taylorsville_seed2_scenario_strings():
    """Taylorsville seed-2 has two scenario strings — Lumberton wins big (first, shorter) then Resurrection upsets."""
    scenarios = _TEAM_DICT["Taylorsville"][2]["scenarios"]
    assert len(scenarios) == 2
    assert scenarios[0] == "Lumberton beats Taylorsville by 12 or more"
    assert scenarios[1] == "Resurrection beats Stringer AND Lumberton beats Taylorsville"


def test_team_dict_weighted_odds_all_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Lumberton", LUMBERTON_EXPECTED),
        ("Resurrection", RESURRECTION_EXPECTED),
        ("Richton", RICHTON_EXPECTED),
        ("Stringer", STRINGER_EXPECTED),
        ("Taylorsville", TAYLORSVILLE_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios matches expected string for each team."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


def test_render_richton_without_odds():
    """Richton without odds renders as 'Clinched #4 seed.' with no percentage."""
    result = render_team_scenarios("Richton", _ATOMS)
    assert result == "Richton\n\nClinched #4 seed."


def test_render_resurrection_without_odds():
    """Resurrection without odds renders as 'Eliminated.' with no percentage."""
    result = render_team_scenarios("Resurrection", _ATOMS)
    assert result == "Resurrection\n\nEliminated."
