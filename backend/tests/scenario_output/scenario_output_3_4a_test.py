"""Scenario output tests for Region 3-4A (2025 season, pre-final-week).

Region 3-4A has two highly coupled remaining games that produce a complex
margin-sensitive scenario tree.

Pre-cutoff records (cutoff 2025-10-24):
  Clarksdale 3-0, Senatobia 2-1, Rosa Fort 2-1, Ripley 1-2, Byhalia 0-4

Byhalia is already eliminated at cutoff (0-4, cannot reach top-4).

Remaining games (both 2025-10-30):
  Clarksdale vs Rosa Fort  — Clarksdale won 32-30 (actual, scenario 2; bit 0)
  Ripley vs Senatobia      — Senatobia won 35-7  (actual, scenario 2; bit 1)

Known 2025 seeds: Clarksdale / Senatobia / Rosa Fort / Ripley
Eliminated: Byhalia

Scenario structure (7 total — 4 masks, 3 with sub-scenarios):
  Mask 0 (RF beats CLA, SEN beats RIP) → three-way tie CLA/SEN/RF all 3-1:
    1a: RF wins by 1-6  → CLA #1, SEN #2, RF #3, RIP #4  (CLA H2H PD wins)
    1b: RF wins by 7-10 → SEN #1, CLA #2, RF #3, RIP #4  (SEN H2H PD wins)
    1c: RF wins by 11+  → SEN #1, RF #2, CLA #3, RIP #4  (RF overtakes CLA in PD)
  Mask 1 (CLA beats RF, SEN beats RIP) → scenario 2 (non-MS, actual result):
    CLA #1 (4-0), SEN #2 (3-1), RF #3 (2-2), RIP #4 (1-3)
  Mask 2 (RF beats CLA, RIP beats SEN) → scenario 3 (non-MS):
    RF #1 (3-1), CLA #2 (3-1, H2H loss to RF), RIP #3 (2-2), SEN #4 (2-2)
  Mask 3 (CLA beats RF, RIP beats SEN) → three-way tie SEN/RF/RIP all 2-2:
    4a: CLA wins by 1-8  AND RIP wins by 12+ → CLA #1, RF #2, SEN #3, RIP #4
        (All three tied in H2H PD; RF has best PD vs outside CLA)
    4b: otherwise (CLA beats RF) → CLA #1, SEN #2, RF #3, RIP #4
        (H2H PD breaks SEN/RF/RIP; SEN leads due to +12 vs RF)

Bit ordering: Clarksdale/Rosa Fort is bit 0 (first remaining game in data);
Ripley/Senatobia is bit 1.  All conditions_atom entries lead with the
Clarksdale/Rosa Fort result because remaining[0] is processed first in
_find_combined_atom.

Teams (alphabetical): Byhalia, Clarksdale, Ripley, Rosa Fort, Senatobia
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

_FIXTURE = REGION_RESULTS_2025[(4, 3)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Byhalia, Clarksdale, Ripley, Rosa Fort, Senatobia
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Clarksdale/Rosa Fort (bit 0), Ripley/Senatobia (bit 1)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

BYHALIA_EXPECTED = "Byhalia\n\nEliminated. (100.0%)"

CLARKSDALE_EXPECTED = """\
Clarksdale

#1 seed if: (62.5%)
1. Clarksdale beats Rosa Fort
2. Rosa Fort beats Clarksdale by 1\u20136 AND Senatobia beats Ripley

#2 seed if: (33.3%)
1. Rosa Fort beats Clarksdale AND Ripley beats Senatobia
2. Rosa Fort beats Clarksdale by 7\u201310

#3 seed if: (4.2%)
1. Rosa Fort beats Clarksdale by 11 or more AND Senatobia beats Ripley"""

RIPLEY_EXPECTED = """\
Ripley

#3 seed if: (25.0%)
1. Rosa Fort beats Clarksdale AND Ripley beats Senatobia

#4 seed if: (75.0%)
1. Senatobia beats Ripley
2. Clarksdale beats Rosa Fort AND Ripley beats Senatobia"""

ROSA_FORT_EXPECTED = """\
Rosa Fort

#1 seed if: (25.0%)
1. Rosa Fort beats Clarksdale AND Ripley beats Senatobia

#2 seed if: (5.6%)
1. Rosa Fort beats Clarksdale by 11 or more AND Senatobia beats Ripley
2. Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 12 or more

#3 seed if: (69.4%)
1. Clarksdale beats Rosa Fort AND Senatobia beats Ripley
2. Rosa Fort beats Clarksdale by 1\u201310 AND Senatobia beats Ripley
3. Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 1\u201311
4. Clarksdale beats Rosa Fort by 9 or more"""

SENATOBIA_EXPECTED = """\
Senatobia

#1 seed if: (12.5%)
1. Rosa Fort beats Clarksdale by 7 or more AND Senatobia beats Ripley

#2 seed if: (61.1%)
1. Clarksdale beats Rosa Fort AND Senatobia beats Ripley
2. Rosa Fort beats Clarksdale by 1\u20136 AND Senatobia beats Ripley
3. Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 1\u201311
4. Clarksdale beats Rosa Fort by 9 or more

#3 seed if: (1.4%)
1. Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 12 or more

#4 seed if: (25.0%)
1. Rosa Fort beats Clarksdale AND Ripley beats Senatobia"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_byhalia_seed_keys():
    """Byhalia is always eliminated — only seed 5."""
    assert set(_ATOMS["Byhalia"].keys()) == {5}


def test_atoms_clarksdale_seed_keys():
    """Clarksdale can finish #1, #2, or #3 depending on the RF/CLA margin."""
    assert set(_ATOMS["Clarksdale"].keys()) == {1, 2, 3}


def test_atoms_ripley_seed_keys():
    """Ripley finishes #3 (when RF wins and RIP wins) or #4 — never higher."""
    assert set(_ATOMS["Ripley"].keys()) == {3, 4}


def test_atoms_rosa_fort_seed_keys():
    """Rosa Fort can finish #1, #2, or #3 — never #4 or lower."""
    assert set(_ATOMS["Rosa Fort"].keys()) == {1, 2, 3}


def test_atoms_senatobia_seed_keys():
    """Senatobia can finish anywhere from #1 to #4."""
    assert set(_ATOMS["Senatobia"].keys()) == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# Byhalia — unconditional elimination
# ---------------------------------------------------------------------------


def test_atoms_byhalia_unconditional():
    """Byhalia is eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["Byhalia"][5] == [[]]


# ---------------------------------------------------------------------------
# Clarksdale atoms
# ---------------------------------------------------------------------------


def test_atoms_clarksdale_seed1_count():
    """Clarksdale seed-1 has exactly two atoms: CLA wins (any), or RF wins narrow + SEN wins."""
    assert len(_ATOMS["Clarksdale"][1]) == 2


def test_atoms_clarksdale_seed1_atom0():
    """Clarksdale seed-1 first atom: CLA beats RF by any margin (clear #1 when CLA wins)."""
    atom = _ATOMS["Clarksdale"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Clarksdale"
    assert gr.loser == "Rosa Fort"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_clarksdale_seed1_atom1():
    """Clarksdale seed-1 second atom: RF wins by 1-6 AND SEN beats RIP (CLA wins 3-way H2H PD)."""
    atom = _ATOMS["Clarksdale"][1][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 7  # exclusive; covers margins 1-6


def test_atoms_clarksdale_seed1_atom1_second_cond():
    """Clarksdale seed-1 second atom second condition: SEN beats RIP (any margin)."""
    gr1 = _ATOMS["Clarksdale"][1][1][1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_clarksdale_seed2_count():
    """Clarksdale seed-2 has exactly two atoms."""
    assert len(_ATOMS["Clarksdale"][2]) == 2


def test_atoms_clarksdale_seed2_atom0():
    """Clarksdale seed-2 first atom: RF beats CLA AND RIP beats SEN (RF goes to #1 via H2H)."""
    atom = _ATOMS["Clarksdale"][2][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_clarksdale_seed2_atom1():
    """Clarksdale seed-2 second atom: RF beats CLA by 7-10 (SEN leads H2H PD, becomes #1)."""
    atom = _ATOMS["Clarksdale"][2][1]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Rosa Fort"
    assert gr.loser == "Clarksdale"
    assert gr.min_margin == 7
    assert gr.max_margin == 11  # exclusive; covers margins 7-10


def test_atoms_clarksdale_seed3_count():
    """Clarksdale seed-3 has exactly one atom."""
    assert len(_ATOMS["Clarksdale"][3]) == 1


def test_atoms_clarksdale_seed3_atom():
    """Clarksdale seed-3: RF beats CLA by 11+ AND SEN beats RIP (RF overtakes CLA in H2H PD)."""
    atom = _ATOMS["Clarksdale"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 11
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Ripley atoms
# ---------------------------------------------------------------------------


def test_atoms_ripley_seed3_count():
    """Ripley seed-3 has exactly one atom."""
    assert len(_ATOMS["Ripley"][3]) == 1


def test_atoms_ripley_seed3_atom():
    """Ripley seed-3: RF beats CLA AND RIP beats SEN (only path to #3 for Ripley)."""
    atom = _ATOMS["Ripley"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_ripley_seed4_count():
    """Ripley seed-4 has exactly two atoms: SEN wins (any), or CLA wins + RIP wins."""
    assert len(_ATOMS["Ripley"][4]) == 2


def test_atoms_ripley_seed4_atom0():
    """Ripley seed-4 first atom: SEN beats RIP (any margin — covers both CLA-wins and RF-wins cases)."""
    atom = _ATOMS["Ripley"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Senatobia"
    assert gr.loser == "Ripley"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_ripley_seed4_atom1():
    """Ripley seed-4 second atom: CLA beats RF AND RIP beats SEN (mask 3; RIP finishes 2-2 but in bottom half)."""
    atom = _ATOMS["Ripley"][4][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clarksdale"
    assert gr0.loser == "Rosa Fort"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Rosa Fort atoms
# ---------------------------------------------------------------------------


def test_atoms_rosa_fort_seed1_count():
    """Rosa Fort seed-1 has exactly one atom."""
    assert len(_ATOMS["Rosa Fort"][1]) == 1


def test_atoms_rosa_fort_seed1_atom():
    """Rosa Fort seed-1: RF beats CLA AND RIP beats SEN (RF finishes 3-1, wins H2H over CLA)."""
    atom = _ATOMS["Rosa Fort"][1][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_rosa_fort_seed2_count():
    """Rosa Fort seed-2 has exactly two atoms."""
    assert len(_ATOMS["Rosa Fort"][2]) == 2


def test_atoms_rosa_fort_seed2_atom0():
    """Rosa Fort seed-2 first atom: RF beats CLA by 11+ AND SEN beats RIP (RF wins H2H PD step)."""
    atom = _ATOMS["Rosa Fort"][2][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 11
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_rosa_fort_seed2_atom1():
    """Rosa Fort seed-2 second atom: CLA wins by 1-8 AND RIP wins by 12+ (scenario 4a; RF gets #2 via step 3)."""
    atom = _ATOMS["Rosa Fort"][2][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clarksdale"
    assert gr0.loser == "Rosa Fort"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 9  # exclusive; covers margins 1-8
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 12
    assert gr1.max_margin is None


def test_atoms_rosa_fort_seed3_count():
    """Rosa Fort seed-3 has exactly four atoms."""
    assert len(_ATOMS["Rosa Fort"][3]) == 4


def test_atoms_rosa_fort_seed3_atom0():
    """Rosa Fort seed-3 first atom: CLA beats RF AND SEN beats RIP (mask 1 — CLA is 4-0, RF is #3)."""
    atom = _ATOMS["Rosa Fort"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clarksdale"
    assert gr0.loser == "Rosa Fort"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_rosa_fort_seed3_atom1():
    """Rosa Fort seed-3 second atom: RF beats CLA by 1-10 AND SEN beats RIP (mask 0 sub-scenarios 1a/1b)."""
    atom = _ATOMS["Rosa Fort"][3][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 11  # exclusive; covers margins 1-10
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Senatobia atoms
# ---------------------------------------------------------------------------


def test_atoms_senatobia_seed1_count():
    """Senatobia seed-1 has exactly one atom."""
    assert len(_ATOMS["Senatobia"][1]) == 1


def test_atoms_senatobia_seed1_atom():
    """Senatobia seed-1: RF beats CLA by 7+ AND SEN beats RIP (SEN wins H2H PD step in 3-way tie)."""
    atom = _ATOMS["Senatobia"][1][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 7
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_senatobia_seed2_count():
    """Senatobia seed-2 has exactly four atoms."""
    assert len(_ATOMS["Senatobia"][2]) == 4


def test_atoms_senatobia_seed2_atom0():
    """Senatobia seed-2 first atom: CLA beats RF AND SEN beats RIP (mask 1 — SEN finishes 3-1 as #2)."""
    atom = _ATOMS["Senatobia"][2][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clarksdale"
    assert gr0.loser == "Rosa Fort"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_senatobia_seed2_atom1():
    """Senatobia seed-2 second atom: RF beats CLA by 1-6 AND SEN beats RIP (mask 0 sub-scenario 1a)."""
    atom = _ATOMS["Senatobia"][2][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 7  # exclusive; covers margins 1-6
    gr1 = atom[1]
    assert gr1.winner == "Senatobia"
    assert gr1.loser == "Ripley"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_senatobia_seed3_count():
    """Senatobia seed-3 has exactly one atom."""
    assert len(_ATOMS["Senatobia"][3]) == 1


def test_atoms_senatobia_seed3_atom():
    """Senatobia seed-3: CLA wins by 1-8 AND RIP wins by 12+ (scenario 4a; SEN is #3 behind RF)."""
    atom = _ATOMS["Senatobia"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clarksdale"
    assert gr0.loser == "Rosa Fort"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 9  # exclusive; covers margins 1-8
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 12
    assert gr1.max_margin is None


def test_atoms_senatobia_seed4_count():
    """Senatobia seed-4 has exactly one atom."""
    assert len(_ATOMS["Senatobia"][4]) == 1


def test_atoms_senatobia_seed4_atom():
    """Senatobia seed-4: RF beats CLA AND RIP beats SEN (mask 2; SEN finishes 2-2 but loses H2H to RIP)."""
    atom = _ATOMS["Senatobia"][4][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Rosa Fort"
    assert gr0.loser == "Clarksdale"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Ripley"
    assert gr1.loser == "Senatobia"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1a, 1b, 1c, 2, 3, 4a, 4b.

    Scenarios 1a/1b/1c are margin-sensitive sub-scenarios from mask 0 (RF beats CLA).
    Scenario 2 is non-MS (actual result: CLA beats RF, SEN beats RIP).
    Scenario 3 is non-MS (RF beats CLA, RIP beats SEN).
    Scenarios 4a/4b are margin-sensitive sub-scenarios from mask 3 (CLA beats RF, RIP beats SEN).
    """
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "1c", "2", "3", "4a", "4b"}


def test_div_dict_scenario1a_title():
    """Scenario 1a: RF beats CLA by 1-6 AND SEN beats RIP."""
    assert _DIV_DICT["1a"]["title"] == "Rosa Fort beats Clarksdale by 1\u20136 AND Senatobia beats Ripley"


def test_div_dict_scenario1b_title():
    """Scenario 1b: RF beats CLA by 7-10 AND SEN beats RIP."""
    assert _DIV_DICT["1b"]["title"] == "Rosa Fort beats Clarksdale by 7\u201310 AND Senatobia beats Ripley"


def test_div_dict_scenario1c_title():
    """Scenario 1c: RF beats CLA by 11+ AND SEN beats RIP."""
    assert _DIV_DICT["1c"]["title"] == "Rosa Fort beats Clarksdale by 11 or more AND Senatobia beats Ripley"


def test_div_dict_scenario2_title():
    """Scenario 2 (actual result): CLA beats RF AND SEN beats RIP (both games decided simply)."""
    assert _DIV_DICT["2"]["title"] == "Clarksdale beats Rosa Fort AND Senatobia beats Ripley"


def test_div_dict_scenario3_title():
    """Scenario 3: RF beats CLA AND RIP beats SEN."""
    assert _DIV_DICT["3"]["title"] == "Rosa Fort beats Clarksdale AND Ripley beats Senatobia"


def test_div_dict_scenario4a_title():
    """Scenario 4a: CLA wins by 1-8 AND RIP wins by 12+ (step-3 PD tiebreaker resolves 3-way)."""
    assert _DIV_DICT["4a"]["title"] == "Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 12 or more"


def test_div_dict_scenario4b_title():
    """Scenario 4b: CLA by 1-8 AND RIP by 1-11 (SEN wins H2H PD tiebreaker over RF)."""
    assert _DIV_DICT["4b"]["title"] == "Clarksdale beats Rosa Fort by 1\u20138 AND Ripley beats Senatobia by 1\u201311"


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: CLA #1, SEN #2, RF #3, RIP #4 (CLA wins 3-way H2H PD)."""
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "Clarksdale"
    assert s["two_seed"] == "Senatobia"
    assert s["three_seed"] == "Rosa Fort"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: SEN #1, CLA #2, RF #3, RIP #4 (SEN wins 3-way H2H PD)."""
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "Senatobia"
    assert s["two_seed"] == "Clarksdale"
    assert s["three_seed"] == "Rosa Fort"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario1c_seeds():
    """Scenario 1c: SEN #1, RF #2, CLA #3, RIP #4 (RF overtakes CLA in H2H PD)."""
    s = _DIV_DICT["1c"]
    assert s["one_seed"] == "Senatobia"
    assert s["two_seed"] == "Rosa Fort"
    assert s["three_seed"] == "Clarksdale"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario2_seeds():
    """Scenario 2 (actual): CLA #1, SEN #2, RF #3, RIP #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Clarksdale"
    assert s["two_seed"] == "Senatobia"
    assert s["three_seed"] == "Rosa Fort"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario3_seeds():
    """Scenario 3: RF #1, CLA #2, RIP #3, SEN #4 (RF wins H2H over CLA; RIP wins H2H over SEN)."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Rosa Fort"
    assert s["two_seed"] == "Clarksdale"
    assert s["three_seed"] == "Ripley"
    assert s["four_seed"] == "Senatobia"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario4a_seeds():
    """Scenario 4a: CLA #1, RF #2, SEN #3, RIP #4 (RF wins step-3 PD vs CLA tiebreaker)."""
    s = _DIV_DICT["4a"]
    assert s["one_seed"] == "Clarksdale"
    assert s["two_seed"] == "Rosa Fort"
    assert s["three_seed"] == "Senatobia"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_scenario4b_seeds():
    """Scenario 4b: CLA #1, SEN #2, RF #3, RIP #4 (SEN wins H2H PD tiebreaker over RF)."""
    s = _DIV_DICT["4b"]
    assert s["one_seed"] == "Clarksdale"
    assert s["two_seed"] == "Senatobia"
    assert s["three_seed"] == "Rosa Fort"
    assert s["four_seed"] == "Ripley"
    assert "Byhalia" in s["eliminated"]


def test_div_dict_byhalia_always_eliminated():
    """Byhalia is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Byhalia" in scenario["eliminated"], f"Scenario {key}: expected Byhalia eliminated"


def test_div_dict_ripley_never_one_or_two():
    """Ripley is never #1 or #2 across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("one_seed") != "Ripley", f"Scenario {key}: Ripley unexpectedly #1"
        assert scenario.get("two_seed") != "Ripley", f"Scenario {key}: Ripley unexpectedly #2"


def test_div_dict_rosa_fort_never_four():
    """Rosa Fort is never #4 or eliminated across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("four_seed") != "Rosa Fort", f"Scenario {key}: Rosa Fort unexpectedly #4"
        assert "Rosa Fort" not in scenario.get("eliminated", []), f"Scenario {key}: Rosa Fort unexpectedly eliminated"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_byhalia_key():
    """Byhalia team dict uses 'eliminated' key only."""
    assert set(_TEAM_DICT["Byhalia"].keys()) == {"eliminated"}


def test_team_dict_clarksdale_keys():
    """Clarksdale team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Clarksdale"].keys()) == {1, 2, 3}


def test_team_dict_ripley_keys():
    """Ripley team dict has keys 3 and 4."""
    assert set(_TEAM_DICT["Ripley"].keys()) == {3, 4}


def test_team_dict_rosa_fort_keys():
    """Rosa Fort team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Rosa Fort"].keys()) == {1, 2, 3}


def test_team_dict_senatobia_keys():
    """Senatobia team dict has keys 1, 2, 3, and 4."""
    assert set(_TEAM_DICT["Senatobia"].keys()) == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_byhalia_eliminated():
    """Byhalia is marked eliminated with zero playoff odds."""
    o = _ODDS["Byhalia"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_clarksdale():
    """Clarksdale: clinched; p1=5/8, p2=1/3, p3=1/24."""  # NOSONAR
    o = _ODDS["Clarksdale"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.625)
    assert o.p2 == pytest.approx(1 / 3)
    assert o.p3 == pytest.approx(1 / 24)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_ripley():
    """Ripley: clinched; p3=1/4, p4=3/4 — never #1 or #2."""
    o = _ODDS["Ripley"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.25)
    assert o.p4 == pytest.approx(0.75)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_rosa_fort():
    """Rosa Fort: clinched; p1=1/4, p2=1/18, p3=25/36 — never #4."""
    o = _ODDS["Rosa Fort"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.25)
    assert o.p2 == pytest.approx(1 / 18)
    assert o.p3 == pytest.approx(25 / 36)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_senatobia():
    """Senatobia: clinched; p1=1/8, p2=11/18, p3=1/72, p4=1/4."""  # NOSONAR
    o = _ODDS["Senatobia"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.125)
    assert o.p2 == pytest.approx(11 / 18)
    assert o.p3 == pytest.approx(1 / 72)
    assert o.p4 == pytest.approx(0.25)
    assert o.p_playoffs == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_byhalia():
    """Byhalia renders as simple eliminated string."""
    assert render_team_scenarios("Byhalia", _ATOMS, odds=_ODDS) == BYHALIA_EXPECTED


def test_render_clarksdale():
    """Clarksdale renders with three seed-1 paths, two seed-2 paths, one seed-3 path."""
    assert render_team_scenarios("Clarksdale", _ATOMS, odds=_ODDS) == CLARKSDALE_EXPECTED


def test_render_ripley():
    """Ripley renders with one seed-3 path and three seed-4 paths."""
    assert render_team_scenarios("Ripley", _ATOMS, odds=_ODDS) == RIPLEY_EXPECTED


def test_render_rosa_fort():
    """Rosa Fort renders with one seed-1, two seed-2, and two seed-3 paths."""
    assert render_team_scenarios("Rosa Fort", _ATOMS, odds=_ODDS) == ROSA_FORT_EXPECTED


def test_render_senatobia():
    """Senatobia renders all four possible seed positions."""
    assert render_team_scenarios("Senatobia", _ATOMS, odds=_ODDS) == SENATOBIA_EXPECTED
