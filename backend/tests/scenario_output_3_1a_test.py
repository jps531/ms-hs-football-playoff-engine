"""Scenario output tests for Region 3-1A (2025 season, pre-final-week).

Region 3-1A is the prototypical "two independent games" case: the two final-week
games decide seeds 1 & 2 and seeds 3 & 4 completely independently of each other.
There are no tiebreakers, no margin-sensitive sub-scenarios, and no eliminations.

Teams (alphabetical): Calhoun City, Okolona, Vardaman, West Lowndes
Remaining games (cutoff 2025-10-24):
  Calhoun City vs West Lowndes  — Calhoun City won 40-0 (actual, scenario 4)
  Okolona vs Vardaman           — Okolona won 34-26 (actual, scenario 4)

Known 2025 seeds: Calhoun City / West Lowndes / Okolona / Vardaman
Eliminated: none

Code paths exercised:
  - build_scenario_atoms       — each team has exactly two single-condition atoms
                                  (one game result per possible seed); games are
                                  fully independent between the two pairs
  - enumerate_division_scenarios — exactly 4 scenarios, numbered 1–4, no sub-labels;
                                   each title is a simple two-clause AND string
  - division_scenarios_as_dict  — 4 keys with compound title strings; eliminated list
                                   is always empty
  - team_scenarios_as_dict      — every team has odds=0.5 for each of their two
                                   possible seeds; no weighted odds
  - render_team_scenarios       — simple "beats" condition strings; all 50/50 splits
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

_FIXTURE = REGION_RESULTS_2025[(1, 3)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Calhoun City, Okolona, Vardaman, West Lowndes
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: RemainingGame('Calhoun City', 'West Lowndes'), RemainingGame('Okolona', 'Vardaman')

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

CALHOUN_CITY_EXPECTED = """\
Calhoun City

#1 seed if: (50.0%)
1. Calhoun City beats West Lowndes

#2 seed if: (50.0%)
1. West Lowndes beats Calhoun City"""

WEST_LOWNDES_EXPECTED = """\
West Lowndes

#1 seed if: (50.0%)
1. West Lowndes beats Calhoun City

#2 seed if: (50.0%)
1. Calhoun City beats West Lowndes"""

OKOLONA_EXPECTED = """\
Okolona

#3 seed if: (50.0%)
1. Okolona beats Vardaman

#4 seed if: (50.0%)
1. Vardaman beats Okolona"""

VARDAMAN_EXPECTED = """\
Vardaman

#3 seed if: (50.0%)
1. Vardaman beats Okolona

#4 seed if: (50.0%)
1. Okolona beats Vardaman"""

# ---------------------------------------------------------------------------
# build_scenario_atoms
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_each_team_has_two_seeds():
    """Every team has exactly two possible seed positions (50/50 split)."""
    for team, seed_map in _ATOMS.items():
        assert len(seed_map) == 2, f"{team!r} has {len(seed_map)} seed entries, expected 2"


def test_atoms_correct_seed_keys():
    """Each team has the right pair of seed keys."""
    assert set(_ATOMS["Calhoun City"].keys()) == {1, 2}
    assert set(_ATOMS["West Lowndes"].keys()) == {1, 2}
    assert set(_ATOMS["Okolona"].keys()) == {3, 4}
    assert set(_ATOMS["Vardaman"].keys()) == {3, 4}


def test_atoms_each_has_single_condition():
    """Each atom is a single-condition list (one game result, no margin restriction)."""
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            assert len(atoms) == 1, f"{team!r} seed {seed}: expected 1 atom, got {len(atoms)}"
            assert len(atoms[0]) == 1, (
                f"{team!r} seed {seed}: expected 1 condition, got {len(atoms[0])}"
            )
            assert isinstance(atoms[0][0], GameResult), (
                f"{team!r} seed {seed}: condition should be GameResult"
            )


def test_atoms_no_margin_restrictions():
    """All GameResults are unconstrained (min_margin=1, max_margin=None)."""
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            gr = atoms[0][0]
            assert gr.min_margin == 1, (
                f"{team!r} seed {seed}: expected min_margin=1, got {gr.min_margin}"
            )
            assert gr.max_margin is None, (
                f"{team!r} seed {seed}: expected max_margin=None, got {gr.max_margin}"
            )


def test_atoms_calhoun_city_seed1():
    """Calhoun City #1 requires Calhoun City to beat West Lowndes."""
    gr = _ATOMS["Calhoun City"][1][0][0]
    assert gr.winner == "Calhoun City"
    assert gr.loser == "West Lowndes"


def test_atoms_calhoun_city_seed2():
    """Calhoun City #2 requires West Lowndes to beat Calhoun City."""
    gr = _ATOMS["Calhoun City"][2][0][0]
    assert gr.winner == "West Lowndes"
    assert gr.loser == "Calhoun City"


def test_atoms_west_lowndes_seed1():
    """West Lowndes #1 requires West Lowndes to beat Calhoun City."""
    gr = _ATOMS["West Lowndes"][1][0][0]
    assert gr.winner == "West Lowndes"
    assert gr.loser == "Calhoun City"


def test_atoms_west_lowndes_seed2():
    """West Lowndes #2 requires Calhoun City to beat West Lowndes."""
    gr = _ATOMS["West Lowndes"][2][0][0]
    assert gr.winner == "Calhoun City"
    assert gr.loser == "West Lowndes"


def test_atoms_okolona_seed3():
    """Okolona #3 requires Okolona to beat Vardaman."""
    gr = _ATOMS["Okolona"][3][0][0]
    assert gr.winner == "Okolona"
    assert gr.loser == "Vardaman"


def test_atoms_okolona_seed4():
    """Okolona #4 requires Vardaman to beat Okolona."""
    gr = _ATOMS["Okolona"][4][0][0]
    assert gr.winner == "Vardaman"
    assert gr.loser == "Okolona"


def test_atoms_games_independent():
    """Seeds 1 & 2 atoms only reference the Calhoun City/West Lowndes game;
    seeds 3 & 4 atoms only reference the Okolona/Vardaman game."""
    for seed in (1, 2):
        for team in ("Calhoun City", "West Lowndes"):
            gr = _ATOMS[team][seed][0][0]
            assert {gr.winner, gr.loser} == {"Calhoun City", "West Lowndes"}, (
                f"{team!r} seed {seed} references wrong game: {gr}"
            )
    for seed in (3, 4):
        for team in ("Okolona", "Vardaman"):
            gr = _ATOMS[team][seed][0][0]
            assert {gr.winner, gr.loser} == {"Okolona", "Vardaman"}, (
                f"{team!r} seed {seed} references wrong game: {gr}"
            )


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """All four outcome combinations produce exactly 4 distinct scenarios."""
    assert len(_SCENARIOS) == 4


def test_scenario_shape():
    """Every scenario has the required keys."""
    required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom"}
    for sc in _SCENARIOS:
        assert set(sc.keys()) == required


def test_scenario_nums_sequential():
    """Scenarios are numbered 1 through 4."""
    nums = sorted(sc["scenario_num"] for sc in _SCENARIOS)
    assert nums == [1, 2, 3, 4]


def test_scenario_no_sub_labels():
    """No scenario has a sub-label — there are no margin-sensitive splits."""
    for sc in _SCENARIOS:
        assert sc["sub_label"] == "", f"scenario {sc['scenario_num']} has unexpected sub_label {sc['sub_label']!r}"


def test_scenario_seedings_cover_all_combos():
    """The four scenarios cover all four possible seeding combinations."""
    seedings = {sc["seeding"] for sc in _SCENARIOS}
    expected = {
        ("Calhoun City", "West Lowndes", "Okolona",   "Vardaman"),
        ("Calhoun City", "West Lowndes", "Vardaman",  "Okolona"),
        ("West Lowndes", "Calhoun City", "Okolona",   "Vardaman"),
        ("West Lowndes", "Calhoun City", "Vardaman",  "Okolona"),
    }
    assert seedings == expected


def test_scenario_no_eliminated():
    """No team is ever eliminated — all four teams always make the playoffs."""
    for sc in _SCENARIOS:
        seeding = sc["seeding"]
        assert len(seeding) == 4, f"scenario {sc['scenario_num']} seeding has {len(seeding)} teams, expected 4"


def test_scenario_actual_result_present():
    """Scenario 4 (Calhoun City / West Lowndes / Okolona / Vardaman) is among the results."""
    seedings = {sc["seeding"] for sc in _SCENARIOS}
    assert ("Calhoun City", "West Lowndes", "Okolona", "Vardaman") in seedings


def test_scenario_game_winners_two_games():
    """Every scenario specifies exactly two game winners."""
    for sc in _SCENARIOS:
        assert len(sc["game_winners"]) == 2, (
            f"scenario {sc['scenario_num']} has {len(sc['game_winners'])} game_winners, expected 2"
        )


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_four_keys():
    """Dict has exactly four keys: '1', '2', '3', '4'."""
    assert set(_DIV_DICT.keys()) == {"1", "2", "3", "4"}


def test_div_dict_entry_shape():
    """Each entry has exactly the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"key {key!r} has unexpected shape"


def test_div_dict_no_empty_titles():
    """Every scenario has a non-empty title (none are unconditional)."""
    for key, entry in _DIV_DICT.items():
        assert entry["title"] != "", f"key {key!r} has empty title"


def test_div_dict_titles_contain_and():
    """Each title is a compound condition joined by AND."""
    for key, entry in _DIV_DICT.items():
        assert "AND" in entry["title"], f"key {key!r} title missing AND: {entry['title']!r}"


def test_div_dict_no_eliminated_teams():
    """Eliminated list is empty in all scenarios — all four teams always qualify."""
    for key, entry in _DIV_DICT.items():
        assert entry["eliminated"] == [], f"key {key!r} has unexpected eliminated: {entry['eliminated']}"


def test_div_dict_seeds_are_four_teams():
    """one_seed through four_seed always contains all four teams (in some order)."""
    all_teams = set(_TEAMS)
    for key, entry in _DIV_DICT.items():
        seeds_in_entry = {entry["one_seed"], entry["two_seed"], entry["three_seed"], entry["four_seed"]}
        assert seeds_in_entry == all_teams, f"key {key!r} missing teams: {seeds_in_entry}"


def test_div_dict_top_seeds_are_cc_and_wl():
    """Seeds 1 & 2 are always Calhoun City and West Lowndes (in some order)."""
    for key, entry in _DIV_DICT.items():
        top_two = {entry["one_seed"], entry["two_seed"]}
        assert top_two == {"Calhoun City", "West Lowndes"}, (
            f"key {key!r} top two seeds are wrong: {top_two}"
        )


def test_div_dict_bottom_seeds_are_ok_and_var():
    """Seeds 3 & 4 are always Okolona and Vardaman (in some order)."""
    for key, entry in _DIV_DICT.items():
        bottom_two = {entry["three_seed"], entry["four_seed"]}
        assert bottom_two == {"Okolona", "Vardaman"}, (
            f"key {key!r} bottom two seeds are wrong: {bottom_two}"
        )


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_each_has_two_seeds():
    """Every team has exactly two seed keys and no 'eliminated' key."""
    for team, entry in _TEAM_DICT.items():
        assert "eliminated" not in entry, f"{team!r} should not have 'eliminated' key"
        assert len(entry) == 2, f"{team!r} has {len(entry)} seed entries, expected 2"


def test_team_dict_entry_shape():
    """Every entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, (
                f"{team!r} key {key!r} has wrong shape"
            )


def test_team_dict_all_odds_50_percent():
    """Every team has odds=0.5 for each of their two possible seeds."""
    for team, team_entry in _TEAM_DICT.items():
        for seed, val in team_entry.items():
            assert val["odds"] == pytest.approx(0.5), (
                f"{team!r} seed {seed}: expected odds=0.5, got {val['odds']}"
            )


def test_team_dict_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None, (
                f"{team!r} key {key!r}: expected weighted_odds=None"
            )


def test_team_dict_each_has_one_scenario_string():
    """Each seed entry has exactly one scenario string."""
    for team, team_entry in _TEAM_DICT.items():
        for seed, val in team_entry.items():
            assert len(val["scenarios"]) == 1, (
                f"{team!r} seed {seed}: expected 1 scenario string, got {len(val['scenarios'])}"
            )


def test_team_dict_scenario_strings_non_empty():
    """All scenario strings are non-empty (conditions are required)."""
    for team, team_entry in _TEAM_DICT.items():
        for seed, val in team_entry.items():
            assert val["scenarios"][0] != "", (
                f"{team!r} seed {seed}: scenario string should not be empty"
            )


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Calhoun City", CALHOUN_CITY_EXPECTED),
        ("West Lowndes", WEST_LOWNDES_EXPECTED),
        ("Okolona",      OKOLONA_EXPECTED),
        ("Vardaman",     VARDAMAN_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected condition strings with 50% odds."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


@pytest.mark.parametrize(
    "team,seeds",
    [
        ("Calhoun City", [1, 2]),
        ("West Lowndes", [1, 2]),
        ("Okolona",      [3, 4]),
        ("Vardaman",     [3, 4]),
    ],
)
def test_render_team_scenarios_without_odds(team, seeds):
    """render_team_scenarios without odds produces '#N seed if:' blocks with no percentages."""
    result = render_team_scenarios(team, _ATOMS)
    for seed in seeds:
        assert f"#{seed} seed if:" in result, (
            f"{team!r}: expected '#{seed} seed if:' in output without odds"
        )
    assert "%" not in result, f"{team!r}: percentage should not appear when odds not supplied"
