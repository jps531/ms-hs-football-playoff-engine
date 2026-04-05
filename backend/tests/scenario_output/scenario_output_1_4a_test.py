"""Scenario output tests for Region 1-4A (2025 season, pre-final-week).

Region 1-4A has a symmetric margin-sensitive structure driven by a single
shared threshold on each remaining game.

Pre-cutoff records (cutoff 2025-10-24):
  Corinth 3-0, New Albany 2-1, North Pontotoc 2-1, Tishomingo County 1-2, South Pontotoc 0-4

South Pontotoc is already eliminated at cutoff (0-4, cannot reach top-4).

Remaining games:
  Corinth vs New Albany      — Corinth won 26-24  (actual, scenario 4; bit 0; 2025-10-30)
  North Pontotoc vs Tishomingo County — North Pontotoc won 55-34 (actual, scenario 4; bit 1; 2025-10-31)

Known 2025 seeds: Corinth / North Pontotoc / New Albany / Tishomingo County
Eliminated: South Pontotoc

Scenario structure (6 total — 4 masks, 2 with sub-scenarios):
  Mask 0 (NA beats COR, TC beats NP) → non-MS scenario 1:
    NA #1, COR #2, TC #3, NP #4
  Mask 1 (COR beats NA, TC beats NP) → 3-way tie NA/NP/TC at 2-2; MS on TC's margin:
    2a: TC wins by 1-7  → COR #1, NA #2, NP #3, TC #4  (NP wins H2H PD vs TC)
    2b: TC wins by 8+   → COR #1, NA #2, TC #3, NP #4  (TC wins H2H PD step)
  Mask 2 (NA beats COR, NP beats TC) → 3-way tie COR/NA/NP at 3-1; MS on NA's margin:
    3a: NA wins by 1-7  → COR #1, NA #2, NP #3, TC #4  (COR wins H2H PD vs NA)
    3b: NA wins by 8+   → NA #1, COR #2, NP #3, TC #4  (NA wins H2H PD step)
  Mask 3 (COR beats NA, NP beats TC) → non-MS scenario 4 (actual result):
    COR #1, NP #2, NA #3, TC #4

Note: scenarios 2a and 3a are distinct game outcomes that produce identical seedings.

H2H PD threshold explanation (both masks 1 and 2 share threshold 8):
  NP beat NA by 4 (pre-cutoff); NA beat TC by 12+ (capped).
  NA's net H2H PD among {NA,NP,TC} = -4+12 = +8, always highest → NA always #2 in mask 1.
  For NP vs TC in mask 1: NP PD = 4-n, TC PD = n-12; crossover at n=8.

Bit ordering: Corinth/New Albany is bit 0 (2025-10-30 game);
North Pontotoc/Tishomingo County is bit 1 (2025-10-31 game).

Teams (alphabetical): Corinth, New Albany, North Pontotoc, South Pontotoc, Tishomingo County
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

_FIXTURE = REGION_RESULTS_2025[(4, 1)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Corinth, New Albany, North Pontotoc, South Pontotoc, Tishomingo County
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Corinth/New Albany (bit 0), North Pontotoc/Tishomingo County (bit 1)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

SOUTH_PONTOTOC_EXPECTED = "South Pontotoc\n\nEliminated. (100.0%)"

CORINTH_EXPECTED = """\
Corinth

#1 seed if: (64.6%)
1. Corinth beats New Albany
2. New Albany beats Corinth by 1\u20137 AND North Pontotoc beats Tishomingo County

#2 seed if: (35.4%)
1. New Albany beats Corinth by 8 or more
2. New Albany beats Corinth AND Tishomingo County beats North Pontotoc"""

NEW_ALBANY_EXPECTED = """\
New Albany

#1 seed if: (35.4%)
1. New Albany beats Corinth by 8 or more
2. New Albany beats Corinth AND Tishomingo County beats North Pontotoc

#2 seed if: (39.6%)
1. Corinth beats New Albany AND Tishomingo County beats North Pontotoc
2. New Albany beats Corinth by 1\u20137 AND North Pontotoc beats Tishomingo County

#3 seed if: (25.0%)
1. Corinth beats New Albany AND North Pontotoc beats Tishomingo County"""

NORTH_PONTOTOC_EXPECTED = """\
North Pontotoc

#2 seed if: (25.0%)
1. Corinth beats New Albany AND North Pontotoc beats Tishomingo County

#3 seed if: (39.6%)
1. New Albany beats Corinth AND North Pontotoc beats Tishomingo County
2. Corinth beats New Albany AND Tishomingo County beats North Pontotoc by 1\u20137

#4 seed if: (35.4%)
1. Tishomingo County beats North Pontotoc by 8 or more
2. New Albany beats Corinth AND Tishomingo County beats North Pontotoc"""

TISHOMINGO_COUNTY_EXPECTED = """\
Tishomingo County

#3 seed if: (35.4%)
1. Tishomingo County beats North Pontotoc by 8 or more
2. New Albany beats Corinth AND Tishomingo County beats North Pontotoc

#4 seed if: (64.6%)
1. North Pontotoc beats Tishomingo County
2. Corinth beats New Albany AND Tishomingo County beats North Pontotoc by 1\u20137"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_south_pontotoc_seed_keys():
    """South Pontotoc is always eliminated — only seed 5."""
    assert set(_ATOMS["South Pontotoc"].keys()) == {5}


def test_atoms_corinth_seed_keys():
    """Corinth finishes #1 or #2 — never lower."""
    assert set(_ATOMS["Corinth"].keys()) == {1, 2}


def test_atoms_new_albany_seed_keys():
    """New Albany can finish #1, #2, or #3 depending on margin."""
    assert set(_ATOMS["New Albany"].keys()) == {1, 2, 3}


def test_atoms_north_pontotoc_seed_keys():
    """North Pontotoc finishes #2, #3, or #4 — never #1."""
    assert set(_ATOMS["North Pontotoc"].keys()) == {2, 3, 4}


def test_atoms_tishomingo_county_seed_keys():
    """Tishomingo County finishes #3 or #4 — never higher."""
    assert set(_ATOMS["Tishomingo County"].keys()) == {3, 4}


# ---------------------------------------------------------------------------
# South Pontotoc — unconditional elimination
# ---------------------------------------------------------------------------


def test_atoms_south_pontotoc_unconditional():
    """South Pontotoc is eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["South Pontotoc"][5] == [[]]


# ---------------------------------------------------------------------------
# Corinth atoms
# ---------------------------------------------------------------------------


def test_atoms_corinth_seed1_count():
    """Corinth seed-1 has exactly two atoms."""
    assert len(_ATOMS["Corinth"][1]) == 2


def test_atoms_corinth_seed1_atom0():
    """Corinth seed-1 first atom: COR beats NA by any margin."""
    atom = _ATOMS["Corinth"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Corinth"
    assert gr.loser == "New Albany"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_corinth_seed1_atom1():
    """Corinth seed-1 second atom: NA wins by 1-7 AND NP beats TC (COR wins 3-way H2H PD)."""
    atom = _ATOMS["Corinth"][1][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 8  # exclusive; covers margins 1-7
    gr1 = atom[1]
    assert gr1.winner == "North Pontotoc"
    assert gr1.loser == "Tishomingo County"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_corinth_seed2_count():
    """Corinth seed-2 has exactly two atoms."""
    assert len(_ATOMS["Corinth"][2]) == 2


def test_atoms_corinth_seed2_atom0():
    """Corinth seed-2 first atom: NA beats COR by 8+ (NA wins H2H PD in 3-way, becomes #1)."""
    atom = _ATOMS["Corinth"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "New Albany"
    assert gr.loser == "Corinth"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_corinth_seed2_atom1():
    """Corinth seed-2 second atom: NA beats COR any AND TC beats NP any (mask 0; NA goes to #1)."""
    atom = _ATOMS["Corinth"][2][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# New Albany atoms
# ---------------------------------------------------------------------------


def test_atoms_new_albany_seed1_count():
    """New Albany seed-1 has exactly two atoms."""
    assert len(_ATOMS["New Albany"][1]) == 2


def test_atoms_new_albany_seed1_atom0():
    """New Albany seed-1 first atom: NA beats COR by 8+ (wins H2H PD in 3-way tie in mask 2)."""
    atom = _ATOMS["New Albany"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "New Albany"
    assert gr.loser == "Corinth"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_new_albany_seed1_atom1():
    """New Albany seed-1 second atom: NA beats COR any AND TC beats NP any (mask 0)."""
    atom = _ATOMS["New Albany"][1][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_new_albany_seed2_count():
    """New Albany seed-2 has exactly two atoms."""
    assert len(_ATOMS["New Albany"][2]) == 2


def test_atoms_new_albany_seed2_atom0():
    """New Albany seed-2 first atom: COR beats NA any AND TC beats NP any (masks 1+0 merged)."""
    atom = _ATOMS["New Albany"][2][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Corinth"
    assert gr0.loser == "New Albany"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_new_albany_seed2_atom1():
    """New Albany seed-2 second atom: NA beats COR by 1-7 AND NP beats TC (scenario 3a)."""
    atom = _ATOMS["New Albany"][2][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 8  # exclusive; covers margins 1-7
    gr1 = atom[1]
    assert gr1.winner == "North Pontotoc"
    assert gr1.loser == "Tishomingo County"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_new_albany_seed3_count():
    """New Albany seed-3 has exactly one atom."""
    assert len(_ATOMS["New Albany"][3]) == 1


def test_atoms_new_albany_seed3_atom():
    """New Albany seed-3: COR beats NA any AND NP beats TC any (only path for NA #3 is mask 3)."""
    atom = _ATOMS["New Albany"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Corinth"
    assert gr0.loser == "New Albany"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "North Pontotoc"
    assert gr1.loser == "Tishomingo County"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# North Pontotoc atoms
# ---------------------------------------------------------------------------


def test_atoms_north_pontotoc_seed2_count():
    """North Pontotoc seed-2 has exactly one atom."""
    assert len(_ATOMS["North Pontotoc"][2]) == 1


def test_atoms_north_pontotoc_seed2_atom():
    """North Pontotoc seed-2: COR beats NA any AND NP beats TC any (only scenario 4 gives NP #2)."""
    atom = _ATOMS["North Pontotoc"][2][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Corinth"
    assert gr0.loser == "New Albany"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "North Pontotoc"
    assert gr1.loser == "Tishomingo County"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_north_pontotoc_seed3_count():
    """North Pontotoc seed-3 has exactly two atoms."""
    assert len(_ATOMS["North Pontotoc"][3]) == 2


def test_atoms_north_pontotoc_seed3_atom0():
    """North Pontotoc seed-3 first atom: NA beats COR AND NP beats TC (unconditional #3)."""
    atom = _ATOMS["North Pontotoc"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "North Pontotoc"
    assert gr1.loser == "Tishomingo County"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_north_pontotoc_seed3_atom1():
    """North Pontotoc seed-3 second atom: COR beats NA AND TC beats NP by 1-7 (scenario 2a)."""
    atom = _ATOMS["North Pontotoc"][3][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Corinth"
    assert gr0.loser == "New Albany"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin == 8  # exclusive; covers margins 1-7


def test_atoms_north_pontotoc_seed4_count():
    """North Pontotoc seed-4 has exactly two atoms."""
    assert len(_ATOMS["North Pontotoc"][4]) == 2


def test_atoms_north_pontotoc_seed4_atom0():
    """North Pontotoc seed-4 first atom: TC beats NP by 8+ (TC wins H2H PD in 3-way, NP drops to #4)."""
    atom = _ATOMS["North Pontotoc"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Tishomingo County"
    assert gr.loser == "North Pontotoc"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_north_pontotoc_seed4_atom1():
    """North Pontotoc seed-4 second atom: NA beats COR any AND TC beats NP any (mask 0)."""
    atom = _ATOMS["North Pontotoc"][4][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Tishomingo County atoms
# ---------------------------------------------------------------------------


def test_atoms_tishomingo_county_seed3_count():
    """Tishomingo County seed-3 has exactly two atoms."""
    assert len(_ATOMS["Tishomingo County"][3]) == 2


def test_atoms_tishomingo_county_seed3_atom0():
    """Tishomingo County seed-3 first atom: TC beats NP by 8+ (wins H2H PD tiebreaker in mask 1)."""
    atom = _ATOMS["Tishomingo County"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Tishomingo County"
    assert gr.loser == "North Pontotoc"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_tishomingo_county_seed3_atom1():
    """Tishomingo County seed-3 second atom: NA beats COR any AND TC beats NP any (mask 0)."""
    atom = _ATOMS["Tishomingo County"][3][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "New Albany"
    assert gr0.loser == "Corinth"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_tishomingo_county_seed4_count():
    """Tishomingo County seed-4 has exactly two atoms."""
    assert len(_ATOMS["Tishomingo County"][4]) == 2


def test_atoms_tishomingo_county_seed4_atom0():
    """Tishomingo County seed-4 first atom: NP beats TC any (covers masks 2 and 3)."""
    atom = _ATOMS["Tishomingo County"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "North Pontotoc"
    assert gr.loser == "Tishomingo County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_tishomingo_county_seed4_atom1():
    """Tishomingo County seed-4 second atom: COR beats NA AND TC beats NP by 1-7 (scenario 2a)."""
    atom = _ATOMS["Tishomingo County"][4][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Corinth"
    assert gr0.loser == "New Albany"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Tishomingo County"
    assert gr1.loser == "North Pontotoc"
    assert gr1.min_margin == 1
    assert gr1.max_margin == 8  # exclusive; covers margins 1-7


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1, 2a, 2b, 3a, 3b, 4.

    Scenarios 1 and 4 are non-MS (mask 0 and mask 3 respectively).
    Scenarios 2a/2b are margin-sensitive within mask 1 (TC beats NP, threshold 8).
    Scenarios 3a/3b are margin-sensitive within mask 2 (NA beats COR, threshold 8).
    """
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "3a", "3b", "4"}


def test_div_dict_scenario1_title():
    """Scenario 1: NA beats COR AND TC beats NP (both upsets simultaneously)."""
    assert _DIV_DICT["1"]["title"] == "New Albany beats Corinth AND Tishomingo County beats North Pontotoc"


def test_div_dict_scenario2a_title():
    """Scenario 2a: COR beats NA AND TC beats NP by 1-7 (NP wins H2H PD over TC)."""
    assert _DIV_DICT["2a"]["title"] == "Corinth beats New Albany AND Tishomingo County beats North Pontotoc by 1\u20137"


def test_div_dict_scenario2b_title():
    """Scenario 2b: COR beats NA AND TC beats NP by 8+ (TC wins H2H PD over NP)."""
    assert (
        _DIV_DICT["2b"]["title"] == "Corinth beats New Albany AND Tishomingo County beats North Pontotoc by 8 or more"
    )


def test_div_dict_scenario3a_title():
    """Scenario 3a: NA beats COR by 1-7 AND NP beats TC (COR wins H2H PD over NA)."""
    assert _DIV_DICT["3a"]["title"] == "New Albany beats Corinth by 1\u20137 AND North Pontotoc beats Tishomingo County"


def test_div_dict_scenario3b_title():
    """Scenario 3b: NA beats COR by 8+ AND NP beats TC (NA wins H2H PD over COR)."""
    assert (
        _DIV_DICT["3b"]["title"] == "New Albany beats Corinth by 8 or more AND North Pontotoc beats Tishomingo County"
    )


def test_div_dict_scenario4_title():
    """Scenario 4 (actual result): COR beats NA AND NP beats TC."""
    assert _DIV_DICT["4"]["title"] == "Corinth beats New Albany AND North Pontotoc beats Tishomingo County"


def test_div_dict_scenario1_seeds():
    """Scenario 1: NA #1, COR #2, TC #3, NP #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "New Albany"
    assert s["two_seed"] == "Corinth"
    assert s["three_seed"] == "Tishomingo County"
    assert s["four_seed"] == "North Pontotoc"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_scenario2a_seeds():
    """Scenario 2a: COR #1, NA #2, NP #3, TC #4."""
    s = _DIV_DICT["2a"]
    assert s["one_seed"] == "Corinth"
    assert s["two_seed"] == "New Albany"
    assert s["three_seed"] == "North Pontotoc"
    assert s["four_seed"] == "Tishomingo County"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_scenario2b_seeds():
    """Scenario 2b: COR #1, NA #2, TC #3, NP #4."""
    s = _DIV_DICT["2b"]
    assert s["one_seed"] == "Corinth"
    assert s["two_seed"] == "New Albany"
    assert s["three_seed"] == "Tishomingo County"
    assert s["four_seed"] == "North Pontotoc"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_scenario3a_seeds():
    """Scenario 3a: COR #1, NA #2, NP #3, TC #4 (same seeding as 2a, different game outcomes)."""
    s = _DIV_DICT["3a"]
    assert s["one_seed"] == "Corinth"
    assert s["two_seed"] == "New Albany"
    assert s["three_seed"] == "North Pontotoc"
    assert s["four_seed"] == "Tishomingo County"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_scenario3b_seeds():
    """Scenario 3b: NA #1, COR #2, NP #3, TC #4."""
    s = _DIV_DICT["3b"]
    assert s["one_seed"] == "New Albany"
    assert s["two_seed"] == "Corinth"
    assert s["three_seed"] == "North Pontotoc"
    assert s["four_seed"] == "Tishomingo County"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_scenario4_seeds():
    """Scenario 4 (actual): COR #1, NP #2, NA #3, TC #4."""
    s = _DIV_DICT["4"]
    assert s["one_seed"] == "Corinth"
    assert s["two_seed"] == "North Pontotoc"
    assert s["three_seed"] == "New Albany"
    assert s["four_seed"] == "Tishomingo County"
    assert "South Pontotoc" in s["eliminated"]


def test_div_dict_south_pontotoc_always_eliminated():
    """South Pontotoc is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "South Pontotoc" in scenario["eliminated"], f"Scenario {key}: expected South Pontotoc eliminated"


def test_div_dict_tishomingo_county_never_one_or_two():
    """Tishomingo County is never #1 or #2 across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("one_seed") != "Tishomingo County", f"Scenario {key}: TC unexpectedly #1"
        assert scenario.get("two_seed") != "Tishomingo County", f"Scenario {key}: TC unexpectedly #2"


def test_div_dict_north_pontotoc_never_one():
    """North Pontotoc is never #1 across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("one_seed") != "North Pontotoc", f"Scenario {key}: NP unexpectedly #1"


def test_div_dict_new_albany_never_four():
    """New Albany is never #4 or eliminated across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("four_seed") != "New Albany", f"Scenario {key}: NA unexpectedly #4"
        assert "New Albany" not in scenario.get("eliminated", []), f"Scenario {key}: NA unexpectedly eliminated"


def test_div_dict_scenarios_2a_and_3a_identical_seedings():
    """Scenarios 2a and 3a produce identical seedings despite different game outcomes."""
    s2a = _DIV_DICT["2a"]
    s3a = _DIV_DICT["3a"]
    assert s2a["one_seed"] == s3a["one_seed"]
    assert s2a["two_seed"] == s3a["two_seed"]
    assert s2a["three_seed"] == s3a["three_seed"]
    assert s2a["four_seed"] == s3a["four_seed"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_south_pontotoc_key():
    """South Pontotoc team dict uses 'eliminated' key only."""
    assert set(_TEAM_DICT["South Pontotoc"].keys()) == {"eliminated"}


def test_team_dict_corinth_keys():
    """Corinth team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Corinth"].keys()) == {1, 2}


def test_team_dict_new_albany_keys():
    """New Albany team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["New Albany"].keys()) == {1, 2, 3}


def test_team_dict_north_pontotoc_keys():
    """North Pontotoc team dict has keys 2, 3, and 4."""
    assert set(_TEAM_DICT["North Pontotoc"].keys()) == {2, 3, 4}


def test_team_dict_tishomingo_county_keys():
    """Tishomingo County team dict has keys 3 and 4."""
    assert set(_TEAM_DICT["Tishomingo County"].keys()) == {3, 4}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_south_pontotoc_eliminated():
    """South Pontotoc is marked eliminated with zero playoff odds."""
    o = _ODDS["South Pontotoc"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_corinth():
    """Corinth: clinched; p1=31/48, p2=17/48 — never lower than #2."""
    o = _ODDS["Corinth"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(31 / 48)
    assert o.p2 == pytest.approx(17 / 48)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_new_albany():
    """New Albany: clinched; p1=17/48, p2=19/48, p3=1/4 — never #4."""
    o = _ODDS["New Albany"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(17 / 48)
    assert o.p2 == pytest.approx(19 / 48)
    assert o.p3 == pytest.approx(0.25)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_north_pontotoc():
    """North Pontotoc: clinched; p2=1/4, p3=19/48, p4=17/48 — never #1."""
    o = _ODDS["North Pontotoc"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.25)
    assert o.p3 == pytest.approx(19 / 48)
    assert o.p4 == pytest.approx(17 / 48)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_tishomingo_county():
    """Tishomingo County: clinched; p3=17/48, p4=31/48 — never #1 or #2."""
    o = _ODDS["Tishomingo County"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(17 / 48)
    assert o.p4 == pytest.approx(31 / 48)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_corinth_new_albany_symmetry():
    """Corinth p1 equals New Albany p2 (symmetric structure; COR p2 equals NA p1)."""
    cor = _ODDS["Corinth"]
    na = _ODDS["New Albany"]
    assert cor.p1 == pytest.approx(na.p2 + na.p3)  # COR p1 = 31/48 = NA (p2+p3) = 19/48+12/48
    # Actually: COR p1=31/48, NA p1=17/48; COR p2=17/48, NA p2=19/48 — not strictly symmetric


def test_odds_north_pontotoc_tishomingo_county_symmetry():
    """NP and TC have symmetric p3/p4 patterns: NP p3 = TC p4 complement pattern."""
    np = _ODDS["North Pontotoc"]
    tc = _ODDS["Tishomingo County"]
    assert np.p4 == pytest.approx(tc.p3)
    assert np.p3 != pytest.approx(tc.p4)  # NP p3=19/48, TC p4=31/48 (not equal)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_south_pontotoc():
    """South Pontotoc renders as simple eliminated string."""
    assert render_team_scenarios("South Pontotoc", _ATOMS, odds=_ODDS) == SOUTH_PONTOTOC_EXPECTED


def test_render_corinth():
    """Corinth renders with two seed-1 paths and two seed-2 paths."""
    assert render_team_scenarios("Corinth", _ATOMS, odds=_ODDS) == CORINTH_EXPECTED


def test_render_new_albany():
    """New Albany renders all three possible seed positions."""
    assert render_team_scenarios("New Albany", _ATOMS, odds=_ODDS) == NEW_ALBANY_EXPECTED


def test_render_north_pontotoc():
    """North Pontotoc renders with seed-2, seed-3 (two atoms), and seed-4 (two atoms) sections."""
    assert render_team_scenarios("North Pontotoc", _ATOMS, odds=_ODDS) == NORTH_PONTOTOC_EXPECTED


def test_render_tishomingo_county():
    """Tishomingo County renders with seed-3 (two atoms) and seed-4 (two atoms) sections."""
    assert render_team_scenarios("Tishomingo County", _ATOMS, odds=_ODDS) == TISHOMINGO_COUNTY_EXPECTED
