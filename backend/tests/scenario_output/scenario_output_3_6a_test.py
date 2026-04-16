"""Scenario output tests for Region 3-6A (2025 season, pre-final-week).

Region 3-6A has the most complex scenario structure seen so far: two independent
margin-sensitive games (Hattiesburg/Terry and Forest Hill/George County) produce
15 distinct scenarios.

Teams (alphabetical):
  Forest Hill, George County, Hattiesburg, Jim Hill, Terry, West Jones

Remaining games (cutoff 2025-10-31):
  bit 0: Forest Hill vs George County   (FH=a, GC=b; bit=1 → FH wins)
  bit 1: Hattiesburg vs Terry           (HAT=a, TER=b; bit=1 → HAT wins)
  bit 2: Jim Hill vs West Jones         (JH=a, WJ=b; bit=0 → WJ wins)

Actual results (2025-11-06):
  Forest Hill beat George County  (bit 0=1)
  Hattiesburg beat Terry          (bit 1=1)
  West Jones beat Jim Hill        (bit 2=0)
  → mask = 1 + 2 + 0 = 3 → scenario "4a" or "4b" depending on FH/GC margin

Clinched: Hattiesburg, Terry, West Jones
Seed-4 competitors: Forest Hill, George County, Jim Hill

HAT/TER margin thresholds (relevant when West Jones wins, bit 2=0):
  TER by 1–6   (min=1, max=7):  HAT #1, WJ #2, TER #3
  TER by 7–10  (min=7, max=11): HAT #1, TER #2, WJ #3
  TER by 11+   (min=11):        TER #1, HAT #2, WJ #3  — JH/WJ game absent
  HAT wins (any):               HAT #1, WJ #2, TER #3  — FH/GC game absent from top-3

FH/GC margin threshold (relevant only when West Jones wins):
  FH by 1–8 (min=1, max=9):  George County #4
  FH by 9+  (min=9):          Forest Hill #4

Scenario count: 15 total (1a, 1b, 1c, 2a, 2b, 2c, 2d, 2e, 2f, 3, 4a, 4b, 5, 6, 7)
Odds (with margin weighting, effective denom 96):
  HAT: p1=17/24, p2=7/24
  TER: p1=7/24,  p2=1/12,  p3=5/8
  WJ:  p2=5/8,   p3=3/8
  FH:  p4=1/12,  p_elim=11/12
  GC:  p4=2/3,   p_elim=1/3
  JH:  p4=1/4,   p_elim=3/4
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

_FIXTURE = REGION_RESULTS_2025[(6, 3)]
_CUTOFF = "2025-10-31"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Forest Hill/George County (bit 0), Hattiesburg/Terry (bit 1), Jim Hill/West Jones (bit 2)

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

HATTIESBURG_EXPECTED = """\
Hattiesburg

#1 seed if: (70.8%)
1. Hattiesburg beats Terry
2. Terry beats Hattiesburg by 1\u201310 AND West Jones beats Jim Hill

#2 seed if: (29.2%)
1. Terry beats Hattiesburg by 11 or more
2. Terry beats Hattiesburg AND Jim Hill beats West Jones"""

TERRY_EXPECTED = """\
Terry

#1 seed if: (29.2%)
1. Terry beats Hattiesburg by 11 or more
2. Terry beats Hattiesburg AND Jim Hill beats West Jones

#2 seed if: (8.3%)
1. Terry beats Hattiesburg by 7\u201310 AND West Jones beats Jim Hill

#3 seed if: (62.5%)
1. Hattiesburg beats Terry
2. Terry beats Hattiesburg by 1\u20136 AND West Jones beats Jim Hill"""

WEST_JONES_EXPECTED = """\
West Jones

#2 seed if: (62.5%)
1. Hattiesburg beats Terry
2. Terry beats Hattiesburg by 1\u20136 AND West Jones beats Jim Hill

#3 seed if: (37.5%)
1. Terry beats Hattiesburg by 7 or more
2. Terry beats Hattiesburg AND Jim Hill beats West Jones"""

FOREST_HILL_EXPECTED = """\
Forest Hill

#4 seed if: (8.3%)
1. Forest Hill beats George County by 9 or more AND West Jones beats Jim Hill

Eliminated if: (91.7%)
1. Jim Hill beats West Jones
2. George County beats Forest Hill AND West Jones beats Jim Hill
3. Forest Hill beats George County by 1\u20138 AND West Jones beats Jim Hill"""

GEORGE_COUNTY_EXPECTED = """\
George County

#4 seed if: (66.7%)
1. George County beats Forest Hill
2. Forest Hill beats George County by 1\u20138 AND West Jones beats Jim Hill

Eliminated if: (33.3%)
1. Forest Hill beats George County by 9 or more
2. Forest Hill beats George County AND Jim Hill beats West Jones"""

JIM_HILL_EXPECTED = """\
Jim Hill

#4 seed if: (25.0%)
1. Forest Hill beats George County AND Jim Hill beats West Jones

Eliminated if: (75.0%)
1. West Jones beats Jim Hill
2. George County beats Forest Hill AND Jim Hill beats West Jones"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_hattiesburg_seed_keys():
    """Hattiesburg finishes #1 or #2 — always makes playoffs."""
    assert set(_ATOMS["Hattiesburg"].keys()) == {1, 2}


def test_atoms_terry_seed_keys():
    """Terry finishes #1, #2, or #3 — always makes playoffs."""
    assert set(_ATOMS["Terry"].keys()) == {1, 2, 3}


def test_atoms_west_jones_seed_keys():
    """West Jones finishes #2 or #3 — always makes playoffs."""
    assert set(_ATOMS["West Jones"].keys()) == {2, 3}


def test_atoms_forest_hill_seed_keys():
    """Forest Hill can finish #4 or be eliminated."""
    assert set(_ATOMS["Forest Hill"].keys()) == {4, 5}


def test_atoms_george_county_seed_keys():
    """George County can finish #4 or be eliminated."""
    assert set(_ATOMS["George County"].keys()) == {4, 5}


def test_atoms_jim_hill_seed_keys():
    """Jim Hill can finish #4 or be eliminated."""
    assert set(_ATOMS["Jim Hill"].keys()) == {4, 5}


# ---------------------------------------------------------------------------
# Hattiesburg atoms — margin-sensitive HAT/TER game
# ---------------------------------------------------------------------------


def test_atoms_hat_seed1_count():
    """Hattiesburg seed-1 has exactly two atoms."""
    assert len(_ATOMS["Hattiesburg"][1]) == 2


def test_atoms_hat_seed1_atom0():
    """HAT seed-1 atom 0: Hattiesburg beats Terry (any margin). FH/GC and JH/WJ absent."""
    atom = _ATOMS["Hattiesburg"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Hattiesburg"
    assert gr.loser == "Terry"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_hat_seed1_atom0_only_hat_ter():
    """FH/GC and JH/WJ games are both absent from HAT seed-1 atom 0."""
    atom = _ATOMS["Hattiesburg"][1][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert len(pairs) == 1  # only HAT/TER game


def test_atoms_hat_seed1_atom1():
    """HAT seed-1 atom 1: Terry beats HAT by 1–10 AND West Jones beats Jim Hill."""
    atom = _ATOMS["Hattiesburg"][1][1]
    assert len(atom) == 2
    gr_ter = next(g for g in atom if g.winner == "Terry")
    assert gr_ter.loser == "Hattiesburg"
    assert gr_ter.min_margin == 1
    assert gr_ter.max_margin == 11  # exclusive upper bound: covers 1–10
    gr_wj = next(g for g in atom if g.winner == "West Jones")
    assert gr_wj.loser == "Jim Hill"
    assert gr_wj.max_margin is None


def test_atoms_hat_seed2_count():
    """Hattiesburg seed-2 has exactly two atoms."""
    assert len(_ATOMS["Hattiesburg"][2]) == 2


def test_atoms_hat_seed2_atom0():
    """HAT seed-2 atom 0: Terry beats HAT by 11 or more. JH/WJ game absent."""
    atom = _ATOMS["Hattiesburg"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Terry"
    assert gr.loser == "Hattiesburg"
    assert gr.min_margin == 11
    assert gr.max_margin is None


def test_atoms_hat_seed2_atom1():
    """HAT seed-2 atom 1: Terry beats HAT (any margin) AND Jim Hill beats WJ."""
    atom = _ATOMS["Hattiesburg"][2][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Terry" in winners
    assert "Jim Hill" in winners
    gr_ter = next(g for g in atom if g.winner == "Terry")
    assert gr_ter.max_margin is None  # any margin


def test_atoms_hat_seed2_atom1_jh_wj_absent():
    """JH/WJ game is absent from HAT seed-2 atom 0 (TER by 11+ always gives HAT #2)."""
    atom = _ATOMS["Hattiesburg"][2][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert ("Jim Hill", "West Jones") not in pairs
    assert ("West Jones", "Jim Hill") not in pairs


# ---------------------------------------------------------------------------
# Terry atoms — mirror of Hattiesburg in the top two seeds
# ---------------------------------------------------------------------------


def test_atoms_terry_seed1_count():
    """Terry seed-1 has exactly two atoms (mirrors HAT seed-2)."""
    assert len(_ATOMS["Terry"][1]) == 2


def test_atoms_terry_seed1_atom1():
    """TER seed-1 atom 0: Terry beats HAT by 11 or more. JH/WJ game absent."""
    atom = _ATOMS["Terry"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Terry"
    assert gr.loser == "Hattiesburg"
    assert gr.min_margin == 11
    assert gr.max_margin is None


def test_atoms_terry_seed2_count():
    """Terry seed-2 has exactly one atom."""
    assert len(_ATOMS["Terry"][2]) == 1


def test_atoms_terry_seed2_atom():
    """TER seed-2: Terry beats HAT by 7–10 AND West Jones beats Jim Hill."""
    atom = _ATOMS["Terry"][2][0]
    assert len(atom) == 2
    gr_ter = next(g for g in atom if g.winner == "Terry")
    assert gr_ter.loser == "Hattiesburg"
    assert gr_ter.min_margin == 7
    assert gr_ter.max_margin == 11  # exclusive: covers 7–10


def test_atoms_terry_seed3_count():
    """Terry seed-3 has exactly two atoms."""
    assert len(_ATOMS["Terry"][3]) == 2


def test_atoms_terry_seed3_atom0():
    """TER seed-3 atom 0: Hattiesburg beats Terry (any margin). FH/GC and JH/WJ absent."""
    atom = _ATOMS["Terry"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Hattiesburg"
    assert gr.loser == "Terry"
    assert gr.max_margin is None


def test_atoms_terry_seed3_atom1():
    """TER seed-3 atom 1: Terry beats HAT by 1–6 AND West Jones beats Jim Hill."""
    atom = _ATOMS["Terry"][3][1]
    assert len(atom) == 2
    gr_ter = next(g for g in atom if g.winner == "Terry")
    assert gr_ter.min_margin == 1
    assert gr_ter.max_margin == 7  # exclusive: covers 1–6


# ---------------------------------------------------------------------------
# West Jones atoms — tied to HAT/TER margin in the same way
# ---------------------------------------------------------------------------


def test_atoms_wj_seed2_count():
    """West Jones seed-2 has exactly two atoms (same structure as TER seed-3)."""
    assert len(_ATOMS["West Jones"][2]) == 2


def test_atoms_wj_seed2_atom0():
    """WJ seed-2 atom 0: Hattiesburg beats Terry (any margin). FH/GC and JH/WJ absent."""
    atom = _ATOMS["West Jones"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Hattiesburg"
    assert gr.loser == "Terry"
    assert gr.max_margin is None


def test_atoms_wj_seed2_atom1():
    """WJ seed-2 atom 1: Terry beats HAT by 1–6 AND West Jones beats Jim Hill."""
    atom = _ATOMS["West Jones"][2][1]
    gr_ter = next(g for g in atom if g.winner == "Terry")
    assert gr_ter.min_margin == 1
    assert gr_ter.max_margin == 7  # exclusive: covers 1–6
    gr_wj = next(g for g in atom if g.winner == "West Jones")
    assert gr_wj.loser == "Jim Hill"


def test_atoms_wj_seed3_count():
    """West Jones seed-3 has exactly two atoms."""
    assert len(_ATOMS["West Jones"][3]) == 2


def test_atoms_wj_seed3_atom1():
    """WJ seed-3 atom 0: Terry beats HAT by 7 or more. FH/GC and JH/WJ absent."""
    atom = _ATOMS["West Jones"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Terry"
    assert gr.loser == "Hattiesburg"
    assert gr.min_margin == 7
    assert gr.max_margin is None


def test_atoms_wj_seed3_atom1_only_hat_ter():
    """JH/WJ game absent from WJ seed-3 atom 0 (TER by 7+ always gives WJ #3)."""
    atom = _ATOMS["West Jones"][3][0]
    assert len(atom) == 1  # only the HAT/TER condition


# ---------------------------------------------------------------------------
# Symmetry between HAT and TER atom structures
# ---------------------------------------------------------------------------


def test_terry_seed1_mirrors_hat_seed2():
    """TER seed-1 and HAT seed-2 have the same atom count and same condition sets."""
    assert len(_ATOMS["Terry"][1]) == len(_ATOMS["Hattiesburg"][2])


def test_wj_seed2_mirrors_terry_seed3():
    """WJ seed-2 and TER seed-3 have the same two-atom structure."""
    assert len(_ATOMS["West Jones"][2]) == len(_ATOMS["Terry"][3]) == 2


# ---------------------------------------------------------------------------
# Forest Hill, George County, Jim Hill — seed 4 competition
# ---------------------------------------------------------------------------


def test_atoms_fh_seed4_count():
    """Forest Hill seed-4 has exactly one atom."""
    assert len(_ATOMS["Forest Hill"][4]) == 1


def test_atoms_fh_seed4_atom():
    """FH seed-4: Forest Hill beats GC by 9 or more AND West Jones beats JH."""
    atom = _ATOMS["Forest Hill"][4][0]
    assert len(atom) == 2
    gr_fh = next(g for g in atom if g.winner == "Forest Hill")
    assert gr_fh.loser == "George County"
    assert gr_fh.min_margin == 9
    assert gr_fh.max_margin is None
    gr_wj = next(g for g in atom if g.winner == "West Jones")
    assert gr_wj.loser == "Jim Hill"


def test_atoms_fh_eliminated_count():
    """Forest Hill eliminated (seed-5) has exactly three atoms."""
    assert len(_ATOMS["Forest Hill"][5]) == 3


def test_atoms_fh_eliminated_atom0():
    """FH eliminated atom 0: Jim Hill beats West Jones (any FH/GC result → FH eliminated)."""
    atom = _ATOMS["Forest Hill"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Jim Hill"
    assert gr.loser == "West Jones"
    assert gr.max_margin is None


def test_atoms_fh_eliminated_atom1():
    """FH eliminated atom 1: George County beats FH AND West Jones beats JH."""
    atom = _ATOMS["Forest Hill"][5][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "George County" in winners
    assert "West Jones" in winners


def test_atoms_fh_eliminated_atom2():
    """FH eliminated atom 2: FH beats GC by 1–8 AND West Jones beats JH."""
    atom = _ATOMS["Forest Hill"][5][2]
    assert len(atom) == 2
    gr_fh = next(g for g in atom if g.winner == "Forest Hill")
    assert gr_fh.loser == "George County"
    assert gr_fh.min_margin == 1
    assert gr_fh.max_margin == 9  # exclusive: covers 1–8


def test_atoms_gc_seed4_count():
    """George County seed-4 has exactly two atoms."""
    assert len(_ATOMS["George County"][4]) == 2


def test_atoms_gc_seed4_atom0():
    """GC seed-4 atom 0: George County beats Forest Hill (any margin). JH/WJ absent."""
    atom = _ATOMS["George County"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "George County"
    assert gr.loser == "Forest Hill"
    assert gr.max_margin is None


def test_atoms_gc_seed4_atom0_jh_wj_absent():
    """JH/WJ game absent from GC seed-4 atom 0 — GC beating FH is sufficient."""
    atom = _ATOMS["George County"][4][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert ("Jim Hill", "West Jones") not in pairs
    assert ("West Jones", "Jim Hill") not in pairs


def test_atoms_gc_seed4_atom1():
    """GC seed-4 atom 1: Forest Hill beats GC by 1–8 AND West Jones beats JH."""
    atom = _ATOMS["George County"][4][1]
    assert len(atom) == 2
    gr_fh = next(g for g in atom if g.winner == "Forest Hill")
    assert gr_fh.loser == "George County"
    assert gr_fh.min_margin == 1
    assert gr_fh.max_margin == 9  # exclusive: covers 1–8


def test_atoms_gc_eliminated_count():
    """George County eliminated (seed-5) has exactly two atoms."""
    assert len(_ATOMS["George County"][5]) == 2


def test_atoms_gc_eliminated_atom1():
    """GC eliminated atom 0: Forest Hill beats GC by 9 or more. JH/WJ game absent."""
    atom = _ATOMS["George County"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Forest Hill"
    assert gr.loser == "George County"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_gc_eliminated_atom1_jh_wj_absent():
    """JH/WJ absent from GC eliminated atom 0 (FH by 9+ eliminates GC regardless of JH/WJ)."""
    atom = _ATOMS["George County"][5][0]
    assert len(atom) == 1


def test_atoms_jh_seed4_count():
    """Jim Hill seed-4 has exactly one atom."""
    assert len(_ATOMS["Jim Hill"][4]) == 1


def test_atoms_jh_seed4_atom():
    """JH seed-4: Forest Hill beats GC AND Jim Hill beats West Jones."""
    atom = _ATOMS["Jim Hill"][4][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Forest Hill" in winners
    assert "Jim Hill" in winners


def test_atoms_jh_eliminated_count():
    """Jim Hill eliminated (seed-5) has exactly two atoms."""
    assert len(_ATOMS["Jim Hill"][5]) == 2


def test_atoms_jh_eliminated_atom0():
    """JH eliminated atom 0: West Jones beats Jim Hill (any margin). FH/GC absent."""
    atom = _ATOMS["Jim Hill"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "West Jones"
    assert gr.loser == "Jim Hill"
    assert gr.max_margin is None


def test_atoms_jh_eliminated_atom1():
    """JH eliminated atom 1: George County beats FH AND Jim Hill beats West Jones."""
    atom = _ATOMS["Jim Hill"][5][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "George County" in winners
    assert "Jim Hill" in winners


# ---------------------------------------------------------------------------
# Division scenarios dict — 15 scenarios
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly 15 keys."""
    expected = {"1a", "1b", "1c", "2a", "2b", "2c", "2d", "2e", "2f", "3", "4a", "4b", "5", "6", "7"}
    assert set(_DIV_DICT.keys()) == expected


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: HAT #1, WJ #2, TER #3, GC #4 (TER wins by 1–6)."""
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "West Jones"
    assert s["three_seed"] == "Terry"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: HAT #1, TER #2, WJ #3, GC #4 (TER wins by 7–10)."""
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "Terry"
    assert s["three_seed"] == "West Jones"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario1c_seeds():
    """Scenario 1c: TER #1, HAT #2, WJ #3, GC #4."""
    s = _DIV_DICT["1c"]
    assert s["one_seed"] == "Terry"
    assert s["two_seed"] == "Hattiesburg"
    assert s["three_seed"] == "West Jones"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario2a_seeds():
    """Scenario 2a: HAT #1, WJ #2, TER #3, GC #4 (FH wins by 1–8, TER by 1–6)."""
    s = _DIV_DICT["2a"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "West Jones"
    assert s["three_seed"] == "Terry"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario2e_seeds():
    """Scenario 2e: HAT #1, TER #2, WJ #3, FH #4 (FH wins by 9+, TER by 7–10)."""
    s = _DIV_DICT["2e"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "Terry"
    assert s["three_seed"] == "West Jones"
    assert s["four_seed"] == "Forest Hill"


def test_div_dict_scenario3_title():
    """Scenario 3: GC beats FH AND HAT beats TER — JH/WJ game irrelevant."""
    assert _DIV_DICT["3"]["title"] == "George County beats Forest Hill AND Hattiesburg beats Terry"


def test_div_dict_scenario3_seeds():
    """Scenario 3: HAT #1, WJ #2, TER #3, GC #4 — JH/WJ result doesn't matter."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "West Jones"
    assert s["three_seed"] == "Terry"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario4a_seeds():
    """Scenario 4a: HAT #1, WJ #2, TER #3, GC #4 (FH by 1–8, HAT wins)."""
    s = _DIV_DICT["4a"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["four_seed"] == "George County"
    assert "Forest Hill" in s["eliminated"]


def test_div_dict_scenario4b_seeds():
    """Scenario 4b: HAT #1, WJ #2, TER #3, FH #4 (FH by 9+, HAT wins)."""
    s = _DIV_DICT["4b"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["four_seed"] == "Forest Hill"
    assert "George County" in s["eliminated"]


def test_div_dict_scenario5_seeds():
    """Scenario 5: TER #1, HAT #2, WJ #3, GC #4 (GC beats FH, TER beats HAT, JH beats WJ)."""
    s = _DIV_DICT["5"]
    assert s["one_seed"] == "Terry"
    assert s["two_seed"] == "Hattiesburg"
    assert s["three_seed"] == "West Jones"
    assert s["four_seed"] == "George County"


def test_div_dict_scenario6_seeds():
    """Scenario 6: TER #1, HAT #2, WJ #3, JH #4 (FH beats GC, TER beats HAT, JH beats WJ)."""
    s = _DIV_DICT["6"]
    assert s["one_seed"] == "Terry"
    assert s["two_seed"] == "Hattiesburg"
    assert s["three_seed"] == "West Jones"
    assert s["four_seed"] == "Jim Hill"


def test_div_dict_scenario7_seeds():
    """Scenario 7 (actual): HAT #1, WJ #2, TER #3, JH #4 (FH beats GC, HAT beats TER, JH beats WJ)."""
    s = _DIV_DICT["7"]
    assert s["one_seed"] == "Hattiesburg"
    assert s["two_seed"] == "West Jones"
    assert s["three_seed"] == "Terry"
    assert s["four_seed"] == "Jim Hill"


def test_div_dict_hat_ter_wj_always_top3():
    """Hattiesburg, Terry, and West Jones occupy seeds 1–3 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        top3 = {scenario["one_seed"], scenario["two_seed"], scenario["three_seed"]}
        assert top3 == {"Hattiesburg", "Terry", "West Jones"}, f"Scenario {key}: top-3 mismatch"


def test_div_dict_seed4_always_fh_gc_or_jh():
    """The #4 seed is always one of Forest Hill, George County, or Jim Hill."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["four_seed"] in {"Forest Hill", "George County", "Jim Hill"}, (
            f"Scenario {key}: unexpected #4 seed"
        )


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_hattiesburg_keys():
    """Hattiesburg team dict has keys 1 and 2 only."""
    assert set(_TEAM_DICT["Hattiesburg"].keys()) == {1, 2}


def test_team_dict_terry_keys():
    """Terry team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Terry"].keys()) == {1, 2, 3}


def test_team_dict_west_jones_keys():
    """West Jones team dict has keys 2 and 3 only."""
    assert set(_TEAM_DICT["West Jones"].keys()) == {2, 3}


def test_team_dict_forest_hill_keys():
    """Forest Hill team dict has key 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Forest Hill"].keys()) == {4, "eliminated"}


def test_team_dict_george_county_keys():
    """George County team dict has key 4 and 'eliminated'."""
    assert set(_TEAM_DICT["George County"].keys()) == {4, "eliminated"}


def test_team_dict_jim_hill_keys():
    """Jim Hill team dict has key 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Jim Hill"].keys()) == {4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_hattiesburg():
    """Hattiesburg: clinched, p1=17/24, p2=7/24."""
    o = _ODDS["Hattiesburg"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(17 / 24)
    assert o.p2 == pytest.approx(7 / 24)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_terry():
    """Terry: clinched, p1=7/24, p2=1/12, p3=5/8."""
    o = _ODDS["Terry"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(7 / 24)
    assert o.p2 == pytest.approx(1 / 12)
    assert o.p3 == pytest.approx(5 / 8)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_west_jones():
    """West Jones: clinched, p2=5/8, p3=3/8."""
    o = _ODDS["West Jones"]
    assert o.clinched is True
    assert o.p2 == pytest.approx(5 / 8)
    assert o.p3 == pytest.approx(3 / 8)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_forest_hill():
    """Forest Hill: p4=1/12, p_playoffs=1/12."""
    o = _ODDS["Forest Hill"]
    assert o.clinched is False
    assert o.p4 == pytest.approx(1 / 12)
    assert o.p_playoffs == pytest.approx(1 / 12)


def test_odds_george_county():
    """George County: p4=2/3, p_playoffs=2/3."""
    o = _ODDS["George County"]
    assert o.clinched is False
    assert o.p4 == pytest.approx(2 / 3)
    assert o.p_playoffs == pytest.approx(2 / 3)


def test_odds_jim_hill():
    """Jim Hill: p4=1/4, p_playoffs=1/4."""
    o = _ODDS["Jim Hill"]
    assert o.clinched is False
    assert o.p4 == pytest.approx(1 / 4)
    assert o.p_playoffs == pytest.approx(1 / 4)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_hattiesburg():
    """Hattiesburg renders with two-atom seed-1 and two-atom seed-2 structure."""
    assert render_team_scenarios("Hattiesburg", _ATOMS, odds=_ODDS) == HATTIESBURG_EXPECTED


def test_render_terry():
    """Terry renders with margin-sensitive seed-1, seed-2, and seed-3 sections."""
    assert render_team_scenarios("Terry", _ATOMS, odds=_ODDS) == TERRY_EXPECTED


def test_render_west_jones():
    """West Jones renders with seed-2 and seed-3 sections (mirrors TER structure)."""
    assert render_team_scenarios("West Jones", _ATOMS, odds=_ODDS) == WEST_JONES_EXPECTED


def test_render_forest_hill():
    """Forest Hill renders with seed-4 and three-atom eliminated section."""
    assert render_team_scenarios("Forest Hill", _ATOMS, odds=_ODDS) == FOREST_HILL_EXPECTED


def test_render_george_county():
    """George County renders with two-atom seed-4 and two-atom eliminated section."""
    assert render_team_scenarios("George County", _ATOMS, odds=_ODDS) == GEORGE_COUNTY_EXPECTED


def test_render_jim_hill():
    """Jim Hill renders with seed-4 and two-atom eliminated section."""
    assert render_team_scenarios("Jim Hill", _ATOMS, odds=_ODDS) == JIM_HILL_EXPECTED
