"""Scenario output tests for Region 1-6A (2025 season, pre-final-week).

Region 1-6A has an unusual property: the Lake Cormorant/Olive Branch game is
completely irrelevant to seedings — no atom for any team references it.

Teams (alphabetical):
  Center Hill, Grenada, Lake Cormorant, Olive Branch, Saltillo, South Panola

Remaining games (cutoff 2025-10-31):
  bit 0: Grenada vs Saltillo         (GRE=a, SAL=b; bit=1 → GRE wins)
  bit 1: Lake Cormorant vs Olive Branch  (irrelevant to all seedings)
  bit 2: Center Hill vs South Panola (CH=a, SP=b;  bit=0 → SP wins)

Actual results (2025-11-06):
  Grenada beat Saltillo      (bit 0=1)
  Lake Cormorant beat Olive Branch  (bit 1=1, irrelevant)
  South Panola beat Center Hill     (bit 2=0)
  → mask = 1 + 2 + 0 = 3 → scenario "2" (Grenada beats Saltillo)

Clinched unconditionally:  South Panola #1, Lake Cormorant #2
Eliminated unconditionally: Olive Branch
Center Hill clinched playoffs (always #3 or #4)

Effective games for seedings 3–5: only GRE/SAL (bit 0) and CH/SP (bit 2)

Margin sensitivity (only when SAL beats GRE AND SP beats CH):
  SAL by 12+ AND SP by 1–6 (max_margin=7): CH #3, GRE #4  [scenario 1a/3a]
  All other SAL-wins, SP-wins margins:       GRE #3, CH #4  [scenario 1b/3b]

The 12+/1–6 condition is so rare that the equal-probability model yields p=0.0%
for Grenada seed-4 despite the atom existing.

Scenarios (6 total): 1a, 1b, 2, 3a, 3b, 4
  Scenarios 1a and 3a are identical (LC wins vs OB wins, same seedings/title)
  Scenarios 1b and 3b are identical for the same reason

Odds (equal mask weighting, 12^N margin enumeration for tied masks):
  SP:  p1=1.0
  LC:  p2=1.0
  OB:  p_elim=1.0
  CH:  p3=25/96, p4=71/96  (clinched playoffs)
  GRE: p3=71/96, p4=1/96, p_elim=1/4
  SAL: p4=1/4, p_elim=3/4
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

_FIXTURE = REGION_RESULTS_2025[(6, 1)]
_CUTOFF = "2025-10-31"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Grenada/Saltillo (bit 0), Lake Cormorant/Olive Branch (bit 1), Center Hill/South Panola (bit 2)

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

SOUTH_PANOLA_EXPECTED = "South Panola\n\nClinched #1 seed. (100.0%)"
LAKE_CORMORANT_EXPECTED = "Lake Cormorant\n\nClinched #2 seed. (100.0%)"
OLIVE_BRANCH_EXPECTED = "Olive Branch\n\nEliminated. (100.0%)"

CENTER_HILL_EXPECTED = """\
Center Hill

#3 seed if: (26.0%)
1. Saltillo beats Grenada AND Center Hill beats South Panola
2. Saltillo beats Grenada by 12 or more AND South Panola beats Center Hill by 1\u20136

#4 seed if: (74.0%)
1. Grenada beats Saltillo
2. Saltillo beats Grenada by 1\u201311 AND South Panola beats Center Hill
3. Saltillo beats Grenada by 12 or more AND South Panola beats Center Hill by 7 or more"""

GRENADA_EXPECTED = """\
Grenada

#3 seed if: (74.0%)
1. Grenada beats Saltillo
2. Saltillo beats Grenada by 1\u201311 AND South Panola beats Center Hill
3. Saltillo beats Grenada by 12 or more AND South Panola beats Center Hill by 7 or more

#4 seed if: (1.0%)
1. Saltillo beats Grenada by 12 or more AND South Panola beats Center Hill by 1\u20136

Eliminated if: (25.0%)
1. Saltillo beats Grenada AND Center Hill beats South Panola"""

SALTILLO_EXPECTED = """\
Saltillo

#4 seed if: (25.0%)
1. Saltillo beats Grenada AND Center Hill beats South Panola

Eliminated if: (75.0%)
1. South Panola beats Center Hill
2. Grenada beats Saltillo AND Center Hill beats South Panola"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_south_panola_seed_keys():
    """South Panola is always #1 — only seed 1."""
    assert set(_ATOMS["South Panola"].keys()) == {1}


def test_atoms_lake_cormorant_seed_keys():
    """Lake Cormorant is always #2 — only seed 2."""
    assert set(_ATOMS["Lake Cormorant"].keys()) == {2}


def test_atoms_olive_branch_seed_keys():
    """Olive Branch is always eliminated — only seed 5."""
    assert set(_ATOMS["Olive Branch"].keys()) == {5}


def test_atoms_center_hill_seed_keys():
    """Center Hill finishes #3 or #4 — always makes playoffs."""
    assert set(_ATOMS["Center Hill"].keys()) == {3, 4}


def test_atoms_grenada_seed_keys():
    """Grenada can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["Grenada"].keys()) == {3, 4, 5}


def test_atoms_saltillo_seed_keys():
    """Saltillo can finish #4 or be eliminated."""
    assert set(_ATOMS["Saltillo"].keys()) == {4, 5}


# ---------------------------------------------------------------------------
# Unconditional clinched / eliminated atoms
# ---------------------------------------------------------------------------


def test_atoms_south_panola_unconditional():
    """South Panola clinched #1 unconditionally — atom is [[]]."""
    assert _ATOMS["South Panola"][1] == [[]]


def test_atoms_lake_cormorant_unconditional():
    """Lake Cormorant clinched #2 unconditionally — atom is [[]]."""
    assert _ATOMS["Lake Cormorant"][2] == [[]]


def test_atoms_olive_branch_unconditional():
    """Olive Branch is always eliminated — atom is [[]]."""
    assert _ATOMS["Olive Branch"][5] == [[]]


# ---------------------------------------------------------------------------
# Lake Cormorant / Olive Branch game is completely irrelevant
# ---------------------------------------------------------------------------


def test_lc_ob_game_absent_from_all_atoms():
    """The LC/OB game never appears in any atom for any team."""
    lc_ob = {"Lake Cormorant", "Olive Branch"}
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            for atom in atoms:
                for cond in atom:
                    if isinstance(cond, GameResult):
                        assert {cond.winner, cond.loser} != lc_ob, (
                            f"{team} seed {seed} atom references LC/OB game"
                        )


# ---------------------------------------------------------------------------
# Center Hill atoms — always makes playoffs, margin-sensitive #3 condition
# ---------------------------------------------------------------------------


def test_atoms_ch_seed3_count():
    """Center Hill seed-3 has exactly two atoms."""
    assert len(_ATOMS["Center Hill"][3]) == 2


def test_atoms_ch_seed3_atom0():
    """CH seed-3 atom 0: Saltillo beats Grenada (any margin) AND Center Hill beats SP."""
    atom = _ATOMS["Center Hill"][3][0]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 1
    assert gr_sal.max_margin is None  # any margin
    gr_ch = next(g for g in atom if g.winner == "Center Hill")
    assert gr_ch.loser == "South Panola"


def test_atoms_ch_seed3_atom1():
    """CH seed-3 atom 1: Saltillo beats Grenada by 12+ AND SP beats CH by 1–6."""
    atom = _ATOMS["Center Hill"][3][1]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 12
    assert gr_sal.max_margin is None  # 12 or more
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.loser == "Center Hill"
    assert gr_sp.min_margin == 1
    assert gr_sp.max_margin == 7  # exclusive upper bound → covers 1–6


def test_atoms_ch_seed4_count():
    """Center Hill seed-4 has exactly three atoms."""
    assert len(_ATOMS["Center Hill"][4]) == 3


def test_atoms_ch_seed4_atom0():
    """CH seed-4 atom 0: Grenada beats Saltillo (any margin). CH/SP game absent."""
    atom = _ATOMS["Center Hill"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Grenada"
    assert gr.loser == "Saltillo"
    assert gr.max_margin is None


def test_atoms_ch_seed4_atom0_ch_sp_absent():
    """CH/SP game absent from CH seed-4 atom 0 — Grenada winning is sufficient."""
    atom = _ATOMS["Center Hill"][4][0]
    pairs = {(g.winner, g.loser) for g in atom}
    assert ("Center Hill", "South Panola") not in pairs
    assert ("South Panola", "Center Hill") not in pairs


def test_atoms_ch_seed4_atom1():
    """CH seed-4 atom 1: Saltillo beats Grenada by 1–11 AND South Panola beats CH (any)."""
    atom = _ATOMS["Center Hill"][4][1]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 1
    assert gr_sal.max_margin == 12  # exclusive upper bound → covers 1–11
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.loser == "Center Hill"
    assert gr_sp.max_margin is None  # any margin


def test_atoms_ch_seed4_atom2():
    """CH seed-4 atom 2: Saltillo beats Grenada by 12+ AND South Panola beats CH by 7+."""
    atom = _ATOMS["Center Hill"][4][2]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 12
    assert gr_sal.max_margin is None  # 12 or more
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.loser == "Center Hill"
    assert gr_sp.min_margin == 7
    assert gr_sp.max_margin is None  # 7 or more


# ---------------------------------------------------------------------------
# Grenada atoms — symmetric to Center Hill, plus an elimination path
# ---------------------------------------------------------------------------


def test_atoms_grenada_seed3_count():
    """Grenada seed-3 has exactly three atoms."""
    assert len(_ATOMS["Grenada"][3]) == 3


def test_atoms_grenada_seed3_atom0():
    """GRE seed-3 atom 0: Grenada beats Saltillo (any margin). CH/SP game absent."""
    atom = _ATOMS["Grenada"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Grenada"
    assert gr.loser == "Saltillo"
    assert gr.max_margin is None


def test_atoms_grenada_seed3_atom1():
    """GRE seed-3 atom 1: Saltillo beats Grenada by 1–11 AND SP beats CH (any margin)."""
    atom = _ATOMS["Grenada"][3][1]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 1
    assert gr_sal.max_margin == 12  # exclusive upper bound → covers 1–11
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.loser == "Center Hill"
    assert gr_sp.max_margin is None  # any margin


def test_atoms_grenada_seed3_atom2():
    """GRE seed-3 atom 2: Saltillo beats Grenada by 12+ AND SP beats CH by 7+."""
    atom = _ATOMS["Grenada"][3][2]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.loser == "Grenada"
    assert gr_sal.min_margin == 12
    assert gr_sal.max_margin is None  # 12 or more
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.loser == "Center Hill"
    assert gr_sp.min_margin == 7
    assert gr_sp.max_margin is None  # 7 or more


def test_atoms_grenada_seed4_count():
    """Grenada seed-4 has exactly one atom."""
    assert len(_ATOMS["Grenada"][4]) == 1


def test_atoms_grenada_seed4_atom():
    """GRE seed-4: Saltillo beats Grenada by 12+ AND SP beats CH by 1–6."""
    atom = _ATOMS["Grenada"][4][0]
    assert len(atom) == 2
    gr_sal = next(g for g in atom if g.winner == "Saltillo")
    assert gr_sal.min_margin == 12
    assert gr_sal.max_margin is None
    gr_sp = next(g for g in atom if g.winner == "South Panola")
    assert gr_sp.min_margin == 1
    assert gr_sp.max_margin == 7  # exclusive → covers 1–6


def test_atoms_grenada_eliminated_count():
    """Grenada eliminated (seed-5) has exactly one atom."""
    assert len(_ATOMS["Grenada"][5]) == 1


def test_atoms_grenada_eliminated_atom():
    """GRE eliminated: Saltillo beats Grenada AND Center Hill beats South Panola."""
    atom = _ATOMS["Grenada"][5][0]
    assert len(atom) == 2
    winners = {g.winner for g in atom}
    assert "Saltillo" in winners
    assert "Center Hill" in winners


# ---------------------------------------------------------------------------
# Saltillo atoms
# ---------------------------------------------------------------------------


def test_atoms_saltillo_seed4_count():
    """Saltillo seed-4 has exactly one atom."""
    assert len(_ATOMS["Saltillo"][4]) == 1


def test_atoms_saltillo_seed4_atom():
    """Saltillo seed-4: Saltillo beats Grenada AND Center Hill beats South Panola."""
    atom = _ATOMS["Saltillo"][4][0]
    assert len(atom) == 2
    winners = {g.winner for g in atom}
    assert "Saltillo" in winners
    assert "Center Hill" in winners


def test_atoms_saltillo_eliminated_count():
    """Saltillo eliminated (seed-5) has exactly two atoms."""
    assert len(_ATOMS["Saltillo"][5]) == 2


def test_atoms_saltillo_eliminated_atom0():
    """SAL eliminated atom 0: South Panola beats Center Hill (any margin). GRE/SAL absent."""
    atom = _ATOMS["Saltillo"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "South Panola"
    assert gr.loser == "Center Hill"
    assert gr.max_margin is None


def test_atoms_saltillo_eliminated_atom0_gre_sal_absent():
    """GRE/SAL game absent from SAL eliminated atom 0 — SP beating CH is sufficient."""
    atom = _ATOMS["Saltillo"][5][0]
    pairs = {(g.winner, g.loser) for g in atom}
    assert ("Saltillo", "Grenada") not in pairs
    assert ("Grenada", "Saltillo") not in pairs


def test_atoms_saltillo_eliminated_atom1():
    """SAL eliminated atom 1: Grenada beats Saltillo AND Center Hill beats South Panola."""
    atom = _ATOMS["Saltillo"][5][1]
    assert len(atom) == 2
    winners = {g.winner for g in atom}
    assert "Grenada" in winners
    assert "Center Hill" in winners


# ---------------------------------------------------------------------------
# Division scenarios dict — 6 scenarios
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly 4 keys: 1a, 1b, 2, 3 (3a/3b/old-4 renumbered after dedup)."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2", "3"}


def test_div_dict_scenario2_title():
    """Scenario 2 (actual): Grenada beats Saltillo. LC/OB and CH/SP both absent."""
    assert _DIV_DICT["2"]["title"] == "Grenada beats Saltillo"


def test_div_dict_scenario2_seeds():
    """Scenario 2: SP #1, LC #2, GRE #3, CH #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "South Panola"
    assert s["two_seed"] == "Lake Cormorant"
    assert s["three_seed"] == "Grenada"
    assert s["four_seed"] == "Center Hill"


def test_div_dict_scenario3_seeds():
    """Scenario 3 (was 4): SP #1, LC #2, CH #3, SAL #4."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "South Panola"
    assert s["two_seed"] == "Lake Cormorant"
    assert s["three_seed"] == "Center Hill"
    assert s["four_seed"] == "Saltillo"
    assert "Grenada" in s["eliminated"]


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: SP #1, LC #2, CH #3, GRE #4 (SAL by 12+, SP by 1–6)."""
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "South Panola"
    assert s["two_seed"] == "Lake Cormorant"
    assert s["three_seed"] == "Center Hill"
    assert s["four_seed"] == "Grenada"


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: SP #1, LC #2, GRE #3, CH #4."""
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "South Panola"
    assert s["two_seed"] == "Lake Cormorant"
    assert s["three_seed"] == "Grenada"
    assert s["four_seed"] == "Center Hill"




def test_div_dict_sp_always_one():
    """South Panola is #1 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["one_seed"] == "South Panola", f"Scenario {key}: SP should be #1"


def test_div_dict_lc_always_two():
    """Lake Cormorant is #2 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["two_seed"] == "Lake Cormorant", f"Scenario {key}: LC should be #2"


def test_div_dict_ob_always_eliminated():
    """Olive Branch is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Olive Branch" in scenario["eliminated"], f"Scenario {key}: OB should be eliminated"


def test_div_dict_saltillo_never_three():
    """Saltillo is never the #3 seed."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["three_seed"] != "Saltillo", f"Scenario {key}: SAL should not be #3"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_south_panola_key():
    """South Panola team dict uses numeric key 1 only."""
    assert list(_TEAM_DICT["South Panola"].keys()) == [1]


def test_team_dict_lake_cormorant_key():
    """Lake Cormorant team dict uses numeric key 2 only."""
    assert list(_TEAM_DICT["Lake Cormorant"].keys()) == [2]


def test_team_dict_olive_branch_key():
    """Olive Branch team dict uses 'eliminated' key only."""
    assert set(_TEAM_DICT["Olive Branch"].keys()) == {"eliminated"}


def test_team_dict_center_hill_keys():
    """Center Hill team dict has keys 3 and 4 (always playoffs, no elimination)."""
    assert set(_TEAM_DICT["Center Hill"].keys()) == {3, 4}


def test_team_dict_grenada_keys():
    """Grenada team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Grenada"].keys()) == {3, 4, "eliminated"}


def test_team_dict_saltillo_keys():
    """Saltillo team dict has keys 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Saltillo"].keys()) == {4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_south_panola():
    """South Panola clinched #1 with p1=1.0."""
    o = _ODDS["South Panola"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_lake_cormorant():
    """Lake Cormorant clinched #2 with p2=1.0."""
    o = _ODDS["Lake Cormorant"]
    assert o.clinched is True
    assert o.p2 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_olive_branch():
    """Olive Branch is eliminated with p_playoffs=0."""
    o = _ODDS["Olive Branch"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_center_hill():
    """Center Hill clinched playoffs: p3=25/96, p4=71/96."""
    o = _ODDS["Center Hill"]
    assert o.clinched is True
    assert o.p3 == pytest.approx(25 / 96)
    assert o.p4 == pytest.approx(71 / 96)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_grenada():
    """Grenada: p3=71/96, p4=1/96 (2D margin threshold), p_playoffs=3/4."""
    o = _ODDS["Grenada"]
    assert o.clinched is False
    assert o.p3 == pytest.approx(71 / 96)
    assert o.p4 == pytest.approx(1 / 96)
    assert o.p_playoffs == pytest.approx(3 / 4)


def test_odds_saltillo():
    """Saltillo: p4=1/4, p_playoffs=1/4."""
    o = _ODDS["Saltillo"]
    assert o.clinched is False
    assert o.p4 == pytest.approx(1 / 4)
    assert o.p_playoffs == pytest.approx(1 / 4)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_south_panola():
    """South Panola renders as clinched #1."""
    assert render_team_scenarios("South Panola", _ATOMS, odds=_ODDS) == SOUTH_PANOLA_EXPECTED


def test_render_lake_cormorant():
    """Lake Cormorant renders as clinched #2."""
    assert render_team_scenarios("Lake Cormorant", _ATOMS, odds=_ODDS) == LAKE_CORMORANT_EXPECTED


def test_render_olive_branch():
    """Olive Branch renders as fully eliminated."""
    assert render_team_scenarios("Olive Branch", _ATOMS, odds=_ODDS) == OLIVE_BRANCH_EXPECTED


def test_render_center_hill():
    """Center Hill renders with two-atom seed-3 and three-atom seed-4."""
    assert render_team_scenarios("Center Hill", _ATOMS, odds=_ODDS) == CENTER_HILL_EXPECTED


def test_render_grenada():
    """Grenada renders with three-atom seed-3, a (1.0%) seed-4, and eliminated sections."""
    assert render_team_scenarios("Grenada", _ATOMS, odds=_ODDS) == GRENADA_EXPECTED


def test_render_saltillo():
    """Saltillo renders with seed-4 and two-atom eliminated section."""
    assert render_team_scenarios("Saltillo", _ATOMS, odds=_ODDS) == SALTILLO_EXPECTED
