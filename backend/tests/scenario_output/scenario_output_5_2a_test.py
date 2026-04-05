"""Scenario output tests for Region 5-2A (2025 season, pre-final-week).

Region 5-2A exercises several distinctive code paths:

  - **Trivially determined teams** — Newton (1-3 entering final week, no games
    remaining) always finishes #4; Puckett (0-3, one meaningless game left) is
    always eliminated.  Their atoms are empty-condition lists ``[[]]`` rather
    than ``None``.

  - **Scenario consolidation across different game outcomes** — "Lake beats
    Scott Central" covers two underlying masks (Pelahatchie wins OR Puckett
    wins), so the resulting scenario 3 carries only one game-winner clause
    (the Pelahatchie/Puckett result is irrelevant).

  - **PD-split sub-scenarios** — When Pelahatchie beats Puckett AND Scott
    Central beats Lake, the three-way tie (Lake, SC, Pelahatchie all 3-1) is
    resolved by H2H point differential (Step 3, ±12 cap):
      "2a": SC wins by 1–4  → Lake still #1 (Lake's H2H PD higher)
      "2b": SC wins by 5+   → SC #1 (cap shifts advantage to SC)
    Threshold is at 5 because the only other within-group game that created
    asymmetry was Lake 32 – Pelahatchie 24 (margin 8) and Pelahatchie 17 –
    SC 16 (margin 1).

  - **Multi-alternative atoms** — Lake and Scott Central each have two-clause
    OR atoms for some seeds (e.g. Lake #1: "Lake beats SC" OR
    "Pelahatchie wins AND SC wins by 1-4").

Remaining games (2, cutoff 2025-10-24):
  Pelahatchie vs Puckett — Pelahatchie won 55-0 (actual, part of scenario 2b)
  Lake vs Scott Central  — Scott Central won 35-28 (actual, scenario 2b)

Known 2025 seeds: Scott Central / Lake / Pelahatchie / Newton
Eliminated: Puckett
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

_FIXTURE = REGION_RESULTS_2025[(2, 5)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Lake, Newton, Pelahatchie, Puckett, Scott Central
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: RemainingGame('Pelahatchie', 'Puckett'), RemainingGame('Lake', 'Scott Central')

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

LAKE_EXPECTED = """\
Lake

#1 seed if: (58.3%)
1. Lake beats Scott Central
2. Pelahatchie beats Puckett AND Scott Central beats Lake by 1\u20134

#2 seed if: (41.7%)
1. Scott Central beats Lake by 5 or more
2. Puckett beats Pelahatchie AND Scott Central beats Lake"""

NEWTON_EXPECTED = "Newton\n\nClinched #4 seed. (100.0%)"

PELAHATCHIE_EXPECTED = """\
Pelahatchie

#2 seed if: (50.0%)
1. Lake beats Scott Central

#3 seed if: (50.0%)
1. Scott Central beats Lake"""

PUCKETT_EXPECTED = "Puckett\n\nEliminated. (100.0%)"

SCOTT_CENTRAL_EXPECTED = """\
Scott Central

#1 seed if: (41.7%)
1. Scott Central beats Lake by 5 or more
2. Puckett beats Pelahatchie AND Scott Central beats Lake

#2 seed if: (8.3%)
1. Pelahatchie beats Puckett AND Scott Central beats Lake by 1\u20134

#3 seed if: (50.0%)
1. Lake beats Scott Central"""

# ---------------------------------------------------------------------------
# build_scenario_atoms
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_newton_clinched():
    """Newton has exactly one seed entry (4) with an empty-condition atom."""
    assert set(_ATOMS["Newton"].keys()) == {4}
    atom = _ATOMS["Newton"][4]
    assert len(atom) == 1
    assert atom[0] == []


def test_atoms_puckett_eliminated():
    """Puckett has exactly one seed entry (5) with an empty-condition atom."""
    assert set(_ATOMS["Puckett"].keys()) == {5}
    atom = _ATOMS["Puckett"][5]
    assert len(atom) == 1
    assert atom[0] == []


def test_atoms_pelahatchie_two_seeds():
    """Pelahatchie has exactly two seed entries: #2 and #3."""
    assert set(_ATOMS["Pelahatchie"].keys()) == {2, 3}


def test_atoms_pelahatchie_single_condition_each():
    """Pelahatchie's atoms each have exactly one atom with one condition."""
    for seed in (2, 3):
        atoms = _ATOMS["Pelahatchie"][seed]
        assert len(atoms) == 1, f"Pelahatchie seed {seed}: expected 1 atom, got {len(atoms)}"
        assert len(atoms[0]) == 1, f"Pelahatchie seed {seed}: expected 1 condition"


def test_atoms_pelahatchie_seed2_requires_lake_beats_sc():
    """Pelahatchie #2 requires Lake to beat Scott Central."""
    gr = _ATOMS["Pelahatchie"][2][0][0]
    assert gr.winner == "Lake"
    assert gr.loser == "Scott Central"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_pelahatchie_seed3_requires_sc_beats_lake():
    """Pelahatchie #3 requires Scott Central to beat Lake."""
    gr = _ATOMS["Pelahatchie"][3][0][0]
    assert gr.winner == "Scott Central"
    assert gr.loser == "Lake"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_lake_seed1_two_alternatives():
    """Lake #1 has two OR-alternatives: 'Lake beats SC' or 'Pelahatchie wins AND SC by 1-4'."""
    atoms = _ATOMS["Lake"][1]
    assert len(atoms) == 2, f"Lake seed 1: expected 2 atoms, got {len(atoms)}"


def test_atoms_lake_seed1_first_alt_single_condition():
    """Lake #1 first alternative is a single condition: Lake beats SC."""
    atom = _ATOMS["Lake"][1]
    # Find the single-condition alternative
    single = next(a for a in atom if len(a) == 1)
    gr = single[0]
    assert gr.winner == "Lake"
    assert gr.loser == "Scott Central"


def test_atoms_lake_seed1_second_alt_margin_constrained():
    """Lake #1 second alternative requires SC beats Lake by 1-4 (max_margin=5 exclusive)."""
    atoms = _ATOMS["Lake"][1]
    two_cond = next(a for a in atoms if len(a) == 2)
    sc_gr = next(gr for gr in two_cond if gr.winner == "Scott Central")
    assert sc_gr.min_margin == 1
    assert sc_gr.max_margin == 5  # exclusive upper bound → renders as "by 1–4"


def test_atoms_lake_seed2_two_alternatives():
    """Lake #2 has two OR-alternatives (Puckett wins + SC wins, or Pelahatchie wins + SC wins by 5+)."""
    atoms = _ATOMS["Lake"][2]
    assert len(atoms) == 2


def test_atoms_sc_seed1_two_alternatives():
    """Scott Central #1 has two OR-alternatives."""
    assert len(_ATOMS["Scott Central"][1]) == 2


def test_atoms_sc_seed1_includes_margin_5_plus():
    """One of SC's #1 alternatives requires SC to beat Lake by 5 or more."""
    atoms = _ATOMS["Scott Central"][1]
    # Find the atom that contains a margin-constrained SC GameResult
    margin_alt = next(
        (a for a in atoms if any(isinstance(gr, GameResult) and gr.winner == "Scott Central" and gr.min_margin == 5 for gr in a)),
        None,
    )
    assert margin_alt is not None, "No 5+ margin alternative found for SC seed 1"


def test_atoms_sc_seed2_margin_constrained():
    """Scott Central #2 requires SC to beat Lake by 1-4."""
    atoms = _ATOMS["Scott Central"][2]
    assert len(atoms) == 1
    sc_gr = next(gr for gr in atoms[0] if isinstance(gr, GameResult) and gr.winner == "Scott Central")
    assert sc_gr.min_margin == 1
    assert sc_gr.max_margin == 5  # exclusive → renders as "by 1–4"


def test_atoms_sc_seed3_single_unconditional():
    """Scott Central #3 requires only Lake to beat SC (single, unconstrained condition)."""
    atoms = _ATOMS["Scott Central"][3]
    assert len(atoms) == 1
    assert len(atoms[0]) == 1
    gr = atoms[0][0]
    assert gr.winner == "Lake"
    assert gr.loser == "Scott Central"
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """Four distinct seeding outcomes produce exactly 4 scenario entries (2a+2b count as 2)."""
    assert len(_SCENARIOS) == 4


def test_scenario_shape():
    """Every scenario has the required keys."""
    required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom"}
    for sc in _SCENARIOS:
        assert set(sc.keys()) == required


def test_scenario_nums():
    """Scenario numbers are 1, 2, 2, 3 (scenario 2 has two sub-labels)."""
    nums = [sc["scenario_num"] for sc in _SCENARIOS]
    assert sorted(nums) == [1, 2, 2, 3]


def test_scenario_sub_labels():
    """Only scenario 2 has sub-labels ('a' and 'b'); scenarios 1 and 3 have no sub-label."""
    for sc in _SCENARIOS:
        if sc["scenario_num"] == 2:
            assert sc["sub_label"] in ("a", "b"), (
                f"Scenario 2 unexpected sub_label: {sc['sub_label']!r}"
            )
        else:
            assert sc["sub_label"] == "", (
                f"Scenario {sc['scenario_num']} should have no sub_label"
            )


def test_scenario_seedings_five_teams():
    """Every scenario seeding contains all 5 teams."""
    for sc in _SCENARIOS:
        assert len(sc["seeding"]) == 5
        assert set(sc["seeding"]) == set(_TEAMS)


def test_newton_always_fourth():
    """Newton is always #4 (position index 3) in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][3] == "Newton", (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: Newton not at #4"
        )


def test_puckett_always_eliminated():
    """Puckett is always last (position index 4, eliminated) in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][4] == "Puckett", (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: Puckett not eliminated"
        )


def test_scenario_seedings_cover_all_combos():
    """The four scenarios cover the three possible top-3 orderings (2a and 2b differ)."""
    seedings = {sc["seeding"] for sc in _SCENARIOS}
    expected = {
        ("Lake",          "Pelahatchie",   "Scott Central", "Newton", "Puckett"),  # scenario 3
        ("Lake",          "Scott Central", "Pelahatchie",   "Newton", "Puckett"),  # scenario 2a
        ("Scott Central", "Lake",          "Pelahatchie",   "Newton", "Puckett"),  # scenarios 1 and 2b
    }
    assert seedings == expected


def test_scenario3_single_game_winner():
    """Scenario 3 carries only one game-winner clause (Pelahatchie/Puckett result is irrelevant)."""
    sc3 = next(s for s in _SCENARIOS if s["scenario_num"] == 3)
    assert len(sc3["game_winners"]) == 1
    winner, loser = sc3["game_winners"][0]
    assert winner == "Lake"
    assert loser == "Scott Central"


def test_scenario_actual_result_present():
    """Scenario 2b (Pelahatchie wins AND SC wins by 5+) matches the actual 2025 result."""
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc2b["seeding"] == ("Scott Central", "Lake", "Pelahatchie", "Newton", "Puckett")


def test_non_sub_scenarios_conditions_atom_none():
    """Scenarios 1 and 3 (no sub-labels) have conditions_atom=None."""
    for sc in _SCENARIOS:
        if sc["sub_label"] == "":
            assert sc["conditions_atom"] is None, (
                f"Scenario {sc['scenario_num']} unexpectedly has conditions_atom"
            )


def test_sub_scenarios_have_conditions_atom():
    """Scenarios 2a and 2b both have a non-None conditions_atom."""
    for sc in _SCENARIOS:
        if sc["scenario_num"] == 2:
            assert sc["conditions_atom"] is not None, (
                f"Scenario 2{sc['sub_label']} missing conditions_atom"
            )


def test_scenario_2a_conditions_atom():
    """Scenario 2a: SC beats Lake by 1-4 (max_margin=5, exclusive) AND Pelahatchie beats Puckett unconstrained."""
    sc2a = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    ca = sc2a["conditions_atom"]
    sc_gr = next(gr for gr in ca if isinstance(gr, GameResult) and gr.winner == "Scott Central")
    assert sc_gr.loser == "Lake"
    assert sc_gr.min_margin == 1
    assert sc_gr.max_margin == 5  # exclusive upper bound → "by 1–4"
    pel_gr = next(gr for gr in ca if isinstance(gr, GameResult) and gr.winner == "Pelahatchie")
    assert pel_gr.loser == "Puckett"
    assert pel_gr.min_margin == 1
    assert pel_gr.max_margin is None


def test_scenario_2b_conditions_atom():
    """Scenario 2b conditions_atom: standalone 'SC beats Lake by 5+' — no Pelahatchie clause.

    Rule 3 simplification: the Pelahatchie/Puckett result is irrelevant when SC wins by 5+,
    so conditions_atom contains only the one sufficient game condition.
    """
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    ca = sc2b["conditions_atom"]
    assert len(ca) == 1, "conditions_atom should have exactly one condition after Rule 3 simplification"
    sc_gr = ca[0]
    assert sc_gr.winner == "Scott Central"
    assert sc_gr.loser == "Lake"
    assert sc_gr.min_margin == 5
    assert sc_gr.max_margin is None


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_four_keys():
    """Dict has exactly four keys: '1', '2a', '2b', '3'."""
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "3"}


def test_div_dict_entry_shape():
    """Each entry has exactly the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"key {key!r} has unexpected shape"


def test_div_dict_always_one_eliminated():
    """Every scenario has exactly one eliminated team."""
    for key, entry in _DIV_DICT.items():
        assert len(entry["eliminated"]) == 1


def test_div_dict_puckett_always_eliminated():
    """Puckett is always the eliminated team."""
    for key, entry in _DIV_DICT.items():
        assert entry["eliminated"] == ["Puckett"], (
            f"key {key!r}: unexpected eliminated team {entry['eliminated']}"
        )


def test_div_dict_newton_always_four_seed():
    """Newton is always the four_seed."""
    for key, entry in _DIV_DICT.items():
        assert entry["four_seed"] == "Newton", (
            f"key {key!r}: Newton not at #4"
        )


def test_div_dict_scenario1_title():
    """Scenario 1: Puckett beats Pelahatchie AND SC beats Lake."""
    assert _DIV_DICT["1"]["title"] == "Puckett beats Pelahatchie AND Scott Central beats Lake"


def test_div_dict_scenario2a_title():
    """Scenario 2a: Pelahatchie wins AND SC wins by 1-4 (margin split renders in title)."""
    assert _DIV_DICT["2a"]["title"] == "Pelahatchie beats Puckett AND Scott Central beats Lake by 1\u20134"


def test_div_dict_scenario2b_title():
    """Scenario 2b: SC wins by 5 or more (standalone — Pelahatchie/Puckett result not mentioned)."""
    assert _DIV_DICT["2b"]["title"] == "Scott Central beats Lake by 5 or more"


def test_div_dict_scenario3_title():
    """Scenario 3: Lake beats SC (Pelahatchie/Puckett game not mentioned — irrelevant)."""
    assert _DIV_DICT["3"]["title"] == "Lake beats Scott Central"


def test_div_dict_scenario2a_2b_distinct_titles():
    """Scenarios 2a and 2b have different titles (margin range distinguishes them)."""
    assert _DIV_DICT["2a"]["title"] != _DIV_DICT["2b"]["title"]


def test_div_dict_scenario_2b_matches_scenario_1():
    """Scenarios 1 and 2b produce the same seeding (SC #1, Lake #2, Pelahatchie #3)."""
    assert _DIV_DICT["1"]["one_seed"] == _DIV_DICT["2b"]["one_seed"] == "Scott Central"
    assert _DIV_DICT["1"]["two_seed"] == _DIV_DICT["2b"]["two_seed"] == "Lake"
    assert _DIV_DICT["1"]["three_seed"] == _DIV_DICT["2b"]["three_seed"] == "Pelahatchie"


def test_div_dict_scenario_2a_seeds():
    """Scenario 2a: Lake #1, SC #2, Pelahatchie #3 (Lake wins PD battle at narrow SC margin)."""
    entry = _DIV_DICT["2a"]
    assert entry["one_seed"] == "Lake"
    assert entry["two_seed"] == "Scott Central"
    assert entry["three_seed"] == "Pelahatchie"


def test_div_dict_scenario_3_seeds():
    """Scenario 3: Lake #1, Pelahatchie #2, SC #3 (Lake beats SC outright)."""
    entry = _DIV_DICT["3"]
    assert entry["one_seed"] == "Lake"
    assert entry["two_seed"] == "Pelahatchie"
    assert entry["three_seed"] == "Scott Central"


def test_div_dict_scenario3_actual_result():
    """Scenario 2b matches the actual 2025 seeds (SC #1, Lake #2, Pelahatchie #3, Newton #4)."""
    entry = _DIV_DICT["2b"]
    assert entry["one_seed"] == "Scott Central"
    assert entry["two_seed"] == "Lake"
    assert entry["three_seed"] == "Pelahatchie"
    assert entry["four_seed"] == "Newton"
    assert entry["eliminated"] == ["Puckett"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_newton_clinched():
    """Newton has only seed 4 with odds=1.0 (clinched)."""
    entry = _TEAM_DICT["Newton"]
    assert set(entry.keys()) == {4}
    assert entry[4]["odds"] == pytest.approx(1.0)


def test_team_dict_puckett_eliminated():
    """Puckett has only 'eliminated' key with odds=1.0."""
    entry = _TEAM_DICT["Puckett"]
    assert set(entry.keys()) == {"eliminated"}
    assert entry["eliminated"]["odds"] == pytest.approx(1.0)


def test_team_dict_pelahatchie_two_seeds():
    """Pelahatchie has seeds 2 and 3, each at 50%."""
    entry = _TEAM_DICT["Pelahatchie"]
    assert set(entry.keys()) == {2, 3}
    assert entry[2]["odds"] == pytest.approx(0.5)
    assert entry[3]["odds"] == pytest.approx(0.5)


def test_team_dict_lake_seed1_odds():
    """Lake #1 odds are 7/12 ≈ 58.3% (2 masks Lake wins + 4/12 of SC-wins mask)."""
    assert _TEAM_DICT["Lake"][1]["odds"] == pytest.approx(7 / 12)


def test_team_dict_lake_seed2_odds():
    """Lake #2 odds are 5/12 ≈ 41.7%."""
    assert _TEAM_DICT["Lake"][2]["odds"] == pytest.approx(5 / 12)


def test_team_dict_sc_seed1_odds():
    """Scott Central #1 odds are 5/12 ≈ 41.7% (1 mask where Puckett wins + 8/12 where Pelahatchie wins)."""
    assert _TEAM_DICT["Scott Central"][1]["odds"] == pytest.approx(5 / 12)


def test_team_dict_sc_seed2_odds():
    """Scott Central #2 odds are 1/12 ≈ 8.3% (4/12 of one mask)."""
    assert _TEAM_DICT["Scott Central"][2]["odds"] == pytest.approx(1 / 12)


def test_team_dict_sc_seed3_odds():
    """Scott Central #3 odds are 50% (Lake wins game)."""
    assert _TEAM_DICT["Scott Central"][3]["odds"] == pytest.approx(0.5)


def test_team_dict_lake_seed1_has_two_scenario_strings():
    """Lake #1 entry has two scenario strings (OR-alternatives)."""
    assert len(_TEAM_DICT["Lake"][1]["scenarios"]) == 2


def test_team_dict_sc_seed1_has_two_scenario_strings():
    """Scott Central #1 entry has two scenario strings (OR-alternatives)."""
    assert len(_TEAM_DICT["Scott Central"][1]["scenarios"]) == 2


def test_team_dict_weighted_odds_none():
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
        ("Lake",          LAKE_EXPECTED),
        ("Newton",        NEWTON_EXPECTED),
        ("Pelahatchie",   PELAHATCHIE_EXPECTED),
        ("Puckett",       PUCKETT_EXPECTED),
        ("Scott Central", SCOTT_CENTRAL_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected condition strings."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


def test_render_newton_clinched_no_conditions():
    """Newton's output shows 'Clinched' with no game conditions."""
    result = render_team_scenarios("Newton", _ATOMS, odds=_ODDS)
    assert "Clinched #4 seed" in result
    assert "if:" not in result


def test_render_puckett_eliminated_no_conditions():
    """Puckett's output shows 'Eliminated' with no game conditions."""
    result = render_team_scenarios("Puckett", _ATOMS, odds=_ODDS)
    assert "Eliminated." in result
    assert "if:" not in result


def test_render_lake_contains_margin_text():
    """Lake's output includes margin condition text for the PD-split scenario."""
    result = render_team_scenarios("Lake", _ATOMS, odds=_ODDS)
    assert "by 1\u20134" in result
    assert "by 5 or more" in result


def test_render_sc_contains_margin_text():
    """Scott Central's output includes margin condition text."""
    result = render_team_scenarios("Scott Central", _ATOMS, odds=_ODDS)
    assert "by 1\u20134" in result
    assert "by 5 or more" in result


@pytest.mark.parametrize(
    "team,seeds",
    [
        ("Lake",          [1, 2]),
        ("Pelahatchie",   [2, 3]),
        ("Scott Central", [1, 2, 3]),
    ],
)
def test_render_team_scenarios_without_odds(team, seeds):
    """render_team_scenarios without odds produces '#N seed if:' blocks with no percentages."""
    result = render_team_scenarios(team, _ATOMS)
    for seed in seeds:
        assert f"#{seed} seed if:" in result
    assert "%" not in result
