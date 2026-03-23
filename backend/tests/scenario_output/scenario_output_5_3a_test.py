"""Scenario output tests for Region 5-3A (2025 season, pre-final-week).

Region 5-3A is the simplest possible interesting case: all four playoff seeds
are locked before the final week regardless of final-game outcomes.  The two
remaining games (Pisgah vs Union, Quitman vs St. Andrew's) cannot change any
seeding because the tiebreaker chain resolves the same way under all four
outcome combinations.

This exercises the "unconditional / already-set" code path through:
  - build_scenario_atoms        — every team's atom is an empty-condition list
  - enumerate_division_scenarios — collapses to a single scenario with no title
  - division_scenarios_as_dict  — single key "1", empty title string
  - team_scenarios_as_dict      — each team has exactly one seed or eliminated key
  - render_team_scenarios       — "Clinched #N seed." for playoff teams, "Eliminated." for St. Andrew's
"""

import pytest

from backend.helpers.data_classes import RemainingGame
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

_FIXTURE = REGION_RESULTS_2025[(3, 5)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)  # alphabetical: Pisgah, Quitman, SE Lauderdale, St. Andrew's, Union
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [
    RemainingGame(*sorted([g["winner"], g["loser"]]))
    for g in _ALL_GAMES
    if g["date"] > _CUTOFF
]
# Remaining: [RemainingGame('Pisgah', 'Union'), RemainingGame('Quitman', "St. Andrew's")]

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

UNION_EXPECTED = "Union\n\nClinched #1 seed. (100.0%)"
QUITMAN_EXPECTED = "Quitman\n\nClinched #2 seed. (100.0%)"
SE_LAUDERDALE_EXPECTED = "Southeast Lauderdale\n\nClinched #3 seed. (100.0%)"
PISGAH_EXPECTED = "Pisgah\n\nClinched #4 seed. (100.0%)"
ST_ANDREWS_EXPECTED = "St. Andrew's\n\nEliminated. (100.0%)"

# ---------------------------------------------------------------------------
# build_scenario_atoms
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_each_team_has_one_seed():
    """Every team maps to exactly one seed position (no ambiguity)."""
    for team, seed_map in _ATOMS.items():
        assert len(seed_map) == 1, f"{team!r} has {len(seed_map)} seed entries, expected 1"


def test_atoms_correct_seed_assignments():
    """Seed positions match the known 2025 final standings."""
    assert 1 in _ATOMS["Union"]
    assert 2 in _ATOMS["Quitman"]
    assert 3 in _ATOMS["Southeast Lauderdale"]
    assert 4 in _ATOMS["Pisgah"]
    assert 5 in _ATOMS["St. Andrew's"]


def test_atoms_all_unconditional():
    """Every atom is an empty-condition list — outcome is set regardless of final games."""
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            assert atoms == [[]], (
                f"{team!r} seed {seed}: expected [[]] (unconditional), got {atoms!r}"
            )


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """All four outcome combinations collapse into exactly one scenario."""
    assert len(_SCENARIOS) == 1


def test_scenario_single_entry_shape():
    """The single scenario has all required keys."""
    sc = _SCENARIOS[0]
    assert set(sc.keys()) == {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom"}


def test_scenario_num_and_label():
    """Scenario is numbered 1 with no sub-label."""
    sc = _SCENARIOS[0]
    assert sc["scenario_num"] == 1
    assert sc["sub_label"] == ""


def test_scenario_seeding():
    """Seeding tuple matches actual 2025 playoff order plus eliminated team."""
    sc = _SCENARIOS[0]
    assert sc["seeding"] == ("Union", "Quitman", "Southeast Lauderdale", "Pisgah", "St. Andrew's")


def test_scenario_no_conditions():
    """Unconditional scenario has no game_winners and None conditions_atom."""
    sc = _SCENARIOS[0]
    assert sc["game_winners"] == []
    assert sc["conditions_atom"] is None


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)


def test_div_dict_single_key():
    """Dict has exactly one key: '1'."""
    assert set(_DIV_DICT.keys()) == {"1"}


def test_div_dict_entry_shape():
    """Entry has exactly the required keys."""
    entry = _DIV_DICT["1"]
    assert set(entry.keys()) == {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}


def test_div_dict_title_empty():
    """Unconditional scenario has an empty title string."""
    assert _DIV_DICT["1"]["title"] == ""


def test_div_dict_seeds():
    """Seeds match actual 2025 playoff order."""
    entry = _DIV_DICT["1"]
    assert entry["one_seed"] == "Union"
    assert entry["two_seed"] == "Quitman"
    assert entry["three_seed"] == "Southeast Lauderdale"
    assert entry["four_seed"] == "Pisgah"


def test_div_dict_eliminated():
    """Eliminated list contains only St. Andrew's."""
    assert _DIV_DICT["1"]["eliminated"] == ["St. Andrew's"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------

_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_playoff_teams_have_one_seed_key():
    """Each playoff team has exactly one integer seed key and no 'eliminated' key."""
    for team in ("Union", "Quitman", "Southeast Lauderdale", "Pisgah"):
        entry = _TEAM_DICT[team]
        assert "eliminated" not in entry, f"{team!r} should not have 'eliminated' key"
        int_keys = [k for k in entry if isinstance(k, int)]
        assert len(int_keys) == 1, f"{team!r} should have exactly one seed key"


def test_team_dict_st_andrews_eliminated_only():
    """St. Andrew's has only an 'eliminated' key with empty scenarios list."""
    entry = _TEAM_DICT["St. Andrew's"]
    assert set(entry.keys()) == {"eliminated"}
    assert entry["eliminated"]["scenarios"] == []


def test_team_dict_entry_shape():
    """Every entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, (
                f"{team!r} key {key!r} has wrong shape"
            )


def test_team_dict_all_odds_1_0():
    """Every playoff team has odds=1.0 for their single seed."""
    expected = {"Union": 1, "Quitman": 2, "Southeast Lauderdale": 3, "Pisgah": 4}
    for team, seed in expected.items():
        assert _TEAM_DICT[team][seed]["odds"] == pytest.approx(1.0)


def test_team_dict_all_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None, (
                f"{team!r} key {key!r}: expected weighted_odds=None"
            )


def test_team_dict_unconditional_scenario_string():
    """Each playoff team's scenario string is empty (unconditional)."""
    expected = {"Union": 1, "Quitman": 2, "Southeast Lauderdale": 3, "Pisgah": 4}
    for team, seed in expected.items():
        scenarios = _TEAM_DICT[team][seed]["scenarios"]
        assert scenarios == [""], (
            f"{team!r} seed {seed}: expected [''] (unconditional), got {scenarios!r}"
        )


def test_team_dict_st_andrews_elimination_odds():
    """St. Andrew's 'eliminated' entry has odds=1.0."""
    assert _TEAM_DICT["St. Andrew's"]["eliminated"]["odds"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Union", UNION_EXPECTED),
        ("Quitman", QUITMAN_EXPECTED),
        ("Southeast Lauderdale", SE_LAUDERDALE_EXPECTED),
        ("Pisgah", PISGAH_EXPECTED),
        ("St. Andrew's", ST_ANDREWS_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected 'Clinched'/'Eliminated' string."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


@pytest.mark.parametrize(
    "team,expected_seed",
    [
        ("Union", 1),
        ("Quitman", 2),
        ("Southeast Lauderdale", 3),
        ("Pisgah", 4),
    ],
)
def test_render_team_scenarios_without_odds(team, expected_seed):
    """render_team_scenarios without odds produces 'Clinched #N seed.' with no percentage."""
    result = render_team_scenarios(team, _ATOMS)
    assert result == f"{team}\n\nClinched #{expected_seed} seed."


def test_render_st_andrews_without_odds():
    """St. Andrew's renders as 'Eliminated.' (no percentage) when odds not supplied."""
    result = render_team_scenarios("St. Andrew's", _ATOMS)
    assert result == "St. Andrew's\n\nEliminated."
