"""Scenario output tests for Region 6-4A (2025 season, pre-final-week).

Region 6-4A is the simplest possible scenario structure: three seeds are
pre-determined (Mendenhall #3, Richland #4, Raymond eliminated) and only
one remaining game determines the final two seeds (Forest vs Morton for #1/#2).
The Mendenhall/Raymond game is irrelevant to seedings.

Teams (alphabetical): Forest, Mendenhall, Morton, Raymond, Richland
Remaining games (cutoff 2025-10-24):
  Forest vs Morton     — Forest won 20–14 (actual, scenario 2)
  Mendenhall vs Raymond — Mendenhall won 32–0 (irrelevant to seedings)

Known 2025 seeds: Forest / Morton / Mendenhall / Richland
Eliminated: Raymond

Code paths exercised:
  - build_scenario_atoms  — Mendenhall/Richland unconditional; Raymond eliminated unconditionally;
                             Forest/Morton atoms reference only the Forest/Morton game (the
                             Mendenhall/Raymond game is invisible in all atoms)
  - enumerate_division_scenarios — only 2 non-MS scenarios (no margin sensitivity anywhere)
  - Scenario consolidation: both Forest-wins and Morton-wins scenarios are non-MS because
    Mendenhall/Raymond result never changes any seeding
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

_FIXTURE = REGION_RESULTS_2025[(4, 6)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Forest, Mendenhall, Morton, Raymond, Richland
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Forest/Morton (bit 0), Mendenhall/Raymond (bit 1 — irrelevant to seedings)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(
    _TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom
)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

RAYMOND_EXPECTED = "Raymond\n\nEliminated. (100.0%)"
MENDENHALL_EXPECTED = "Mendenhall\n\nClinched #3 seed. (100.0%)"
RICHLAND_EXPECTED = "Richland\n\nClinched #4 seed. (100.0%)"

FOREST_EXPECTED = """\
Forest

#1 seed if: (50.0%)
1. Forest beats Morton

#2 seed if: (50.0%)
1. Morton beats Forest"""

MORTON_EXPECTED = """\
Morton

#1 seed if: (50.0%)
1. Morton beats Forest

#2 seed if: (50.0%)
1. Forest beats Morton"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_raymond_seed_keys():
    """Raymond is always eliminated — only seed 5."""
    assert set(_ATOMS["Raymond"].keys()) == {5}


def test_atoms_richland_seed_keys():
    """Richland is always #4 — only seed 4."""
    assert set(_ATOMS["Richland"].keys()) == {4}


def test_atoms_mendenhall_seed_keys():
    """Mendenhall is always #3 — only seed 3."""
    assert set(_ATOMS["Mendenhall"].keys()) == {3}


def test_atoms_forest_seed_keys():
    """Forest finishes #1 or #2 — never lower."""
    assert set(_ATOMS["Forest"].keys()) == {1, 2}


def test_atoms_morton_seed_keys():
    """Morton finishes #1 or #2 — never lower."""
    assert set(_ATOMS["Morton"].keys()) == {1, 2}


def test_atoms_raymond_unconditional():
    """Raymond is eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["Raymond"][5] == [[]]


def test_atoms_richland_unconditional():
    """Richland clinched #4 unconditionally — atom is [[]]."""
    assert _ATOMS["Richland"][4] == [[]]


def test_atoms_mendenhall_unconditional():
    """Mendenhall clinched #3 unconditionally — atom is [[]]."""
    assert _ATOMS["Mendenhall"][3] == [[]]


# ---------------------------------------------------------------------------
# Forest and Morton atoms — only Forest/Morton game referenced
# ---------------------------------------------------------------------------


def test_atoms_forest_seed1_count():
    """Forest seed-1 has exactly one atom."""
    assert len(_ATOMS["Forest"][1]) == 1


def test_atoms_forest_seed1_atom():
    """Forest seed-1: Forest beats Morton (any margin) — Mendenhall/Raymond game absent."""
    atom = _ATOMS["Forest"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Forest"
    assert gr.loser == "Morton"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_forest_seed2_count():
    """Forest seed-2 has exactly one atom."""
    assert len(_ATOMS["Forest"][2]) == 1


def test_atoms_forest_seed2_atom():
    """Forest seed-2: Morton beats Forest (any margin) — Mendenhall/Raymond game absent."""
    atom = _ATOMS["Forest"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Morton"
    assert gr.loser == "Forest"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_morton_seed1_count():
    """Morton seed-1 has exactly one atom."""
    assert len(_ATOMS["Morton"][1]) == 1


def test_atoms_morton_seed1_atom():
    """Morton seed-1: Morton beats Forest (any margin)."""
    atom = _ATOMS["Morton"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Morton"
    assert gr.loser == "Forest"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_morton_seed2_count():
    """Morton seed-2 has exactly one atom."""
    assert len(_ATOMS["Morton"][2]) == 1


def test_atoms_morton_seed2_atom():
    """Morton seed-2: Forest beats Morton (any margin)."""
    atom = _ATOMS["Morton"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Forest"
    assert gr.loser == "Morton"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_mendenhall_raymond_game_absent():
    """The Mendenhall/Raymond game never appears in any atom for any team."""
    men_ray_teams = {"Mendenhall", "Raymond"}
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            for atom in atoms:
                for cond in atom:
                    if isinstance(cond, GameResult):
                        pair = {cond.winner, cond.loser}
                        assert pair != men_ray_teams, (
                            f"{team} seed {seed} atom references Mendenhall/Raymond game"
                        )


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1 and 2 — no margin sub-scenarios."""
    assert set(_DIV_DICT.keys()) == {"1", "2"}


def test_div_dict_scenario1_title():
    """Scenario 1: Morton beats Forest."""
    assert _DIV_DICT["1"]["title"] == "Morton beats Forest"


def test_div_dict_scenario2_title():
    """Scenario 2: Forest beats Morton (actual result)."""
    assert _DIV_DICT["2"]["title"] == "Forest beats Morton"


def test_div_dict_scenario1_seeds():
    """Scenario 1: Morton #1, Forest #2, Mendenhall #3, Richland #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "Morton"
    assert s["two_seed"] == "Forest"
    assert s["three_seed"] == "Mendenhall"
    assert s["four_seed"] == "Richland"
    assert "Raymond" in s["eliminated"]


def test_div_dict_scenario2_seeds():
    """Scenario 2: Forest #1, Morton #2, Mendenhall #3, Richland #4 (actual result)."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Forest"
    assert s["two_seed"] == "Morton"
    assert s["three_seed"] == "Mendenhall"
    assert s["four_seed"] == "Richland"
    assert "Raymond" in s["eliminated"]


def test_div_dict_mendenhall_always_three():
    """Mendenhall is #3 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["three_seed"] == "Mendenhall", f"Scenario {key}: expected Mendenhall #3"


def test_div_dict_richland_always_four():
    """Richland is #4 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["four_seed"] == "Richland", f"Scenario {key}: expected Richland #4"


def test_div_dict_raymond_always_eliminated():
    """Raymond is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Raymond" in scenario["eliminated"], f"Scenario {key}: expected Raymond eliminated"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_raymond_key():
    """Raymond team dict uses 'eliminated' key only."""
    assert set(_TEAM_DICT["Raymond"].keys()) == {"eliminated"}


def test_team_dict_richland_key():
    """Richland team dict uses numeric key 4 only."""
    assert list(_TEAM_DICT["Richland"].keys()) == [4]


def test_team_dict_mendenhall_key():
    """Mendenhall team dict uses numeric key 3 only."""
    assert list(_TEAM_DICT["Mendenhall"].keys()) == [3]


def test_team_dict_forest_keys():
    """Forest team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Forest"].keys()) == {1, 2}


def test_team_dict_morton_keys():
    """Morton team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Morton"].keys()) == {1, 2}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_raymond_eliminated():
    """Raymond is marked eliminated with zero playoff odds."""
    o = _ODDS["Raymond"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_richland_clinched():
    """Richland is clinched #4 with p4=1.0."""
    o = _ODDS["Richland"]
    assert o.clinched is True
    assert o.p4 == pytest.approx(1.0)


def test_odds_mendenhall_clinched():
    """Mendenhall is clinched #3 with p3=1.0."""
    o = _ODDS["Mendenhall"]
    assert o.clinched is True
    assert o.p3 == pytest.approx(1.0)


def test_odds_forest_even_split():
    """Forest has exactly 50/50 odds on #1 vs #2."""
    o = _ODDS["Forest"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.5)
    assert o.p2 == pytest.approx(0.5)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_morton_even_split():
    """Morton has exactly 50/50 odds on #1 vs #2."""
    o = _ODDS["Morton"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.5)
    assert o.p2 == pytest.approx(0.5)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_raymond():
    """Raymond renders as simple eliminated string."""
    assert render_team_scenarios("Raymond", _ATOMS, odds=_ODDS) == RAYMOND_EXPECTED


def test_render_richland():
    """Richland renders as clinched #4 string."""
    assert render_team_scenarios("Richland", _ATOMS, odds=_ODDS) == RICHLAND_EXPECTED


def test_render_mendenhall():
    """Mendenhall renders as clinched #3 string."""
    assert render_team_scenarios("Mendenhall", _ATOMS, odds=_ODDS) == MENDENHALL_EXPECTED


def test_render_forest():
    """Forest renders correctly as a simple 50/50 seed-1-or-2 scenario."""
    assert render_team_scenarios("Forest", _ATOMS, odds=_ODDS) == FOREST_EXPECTED


def test_render_morton():
    """Morton renders correctly as a simple 50/50 seed-1-or-2 scenario."""
    assert render_team_scenarios("Morton", _ATOMS, odds=_ODDS) == MORTON_EXPECTED
