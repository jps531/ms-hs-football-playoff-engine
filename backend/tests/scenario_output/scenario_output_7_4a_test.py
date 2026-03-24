"""Scenario output tests for Region 7-4A (2025 season, pre-final-week).

Region 7-4A has Lawrence County pre-eliminated and two independent tiebreaker
situations that each resolve at margin threshold 7 — one on the Columbia/Poplarville
game and one on the McComb/South Pike game.

Teams (alphabetical): Columbia, Lawrence County, McComb, Poplarville, South Pike
Remaining games (cutoff 2025-10-24):
  Columbia vs Poplarville — Columbia won 49–28, margin 21 (actual, scenario 4)
  McComb vs South Pike    — McComb won 41–12, margin 29 (actual, scenario 4)

Known 2025 seeds: Columbia / McComb / Poplarville / South Pike
Eliminated: Lawrence County

Code paths exercised:
  - build_scenario_atoms       — LC eliminated unconditionally; Columbia always seeds 1–2;
                                  South Pike always seeds 3–4; Rule 3 produces four standalone
                                  atoms: COL seed-2 and POP seed-1 share [POP by 7+] (lifted
                                  MCB/SP condition); SP seed-3 and MCB seed-4 share [SP by 7+]
                                  (lifted COL/POP condition)
  - enumerate_division_scenarios — 6 scenarios: 1 non-MS (POP+SP wins); 2a/2b COL wins+SP wins
                                    at threshold 7; 3a/3b POP wins+MCB wins at threshold 7;
                                    4 non-MS (COL+MCB wins)
  - Three-way tie COL/POP/MCB at 3-1 (scenarios 3a/3b): perfect H2H cycle;
    H2H PDs: COL = 12−M, POP = M−1, MCB = −11 always.
    MCB always #3; COL #1 when M ≤ 6, POP #1 when M ≥ 7.
  - Three-way tie POP/MCB/SP at 2-2 (scenarios 2a/2b): perfect H2H cycle;
    H2H PDs: POP = +11 always, MCB = 1−M', SP = M'−12.
    POP always #2; MCB #3 when M' ≤ 6, SP #3 when M' ≥ 7.
  - Both thresholds are 7 — the same value arising from different H2H PD coefficients
  - Scenario 4 is non-MS: COL wins + MCB wins always produces COL #1, MCB #2, POP #3, SP #4
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

_FIXTURE = REGION_RESULTS_2025[(4, 7)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Columbia, Lawrence County, McComb, Poplarville, South Pike
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Columbia/Poplarville (bit 0), McComb/South Pike (bit 1)

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

LAWRENCE_COUNTY_EXPECTED = "Lawrence County\n\nEliminated. (100.0%)"

COLUMBIA_EXPECTED = """\
Columbia

#1 seed if: (62.5%)
1. Columbia beats Poplarville
2. Poplarville beats Columbia by 1\u20136 AND McComb beats South Pike

#2 seed if: (37.5%)
1. Poplarville beats Columbia AND South Pike beats McComb
2. Poplarville beats Columbia by 7 or more"""

MCCOMB_EXPECTED = """\
McComb

#2 seed if: (25.0%)
1. Columbia beats Poplarville AND McComb beats South Pike

#3 seed if: (37.5%)
1. Columbia beats Poplarville AND South Pike beats McComb by 1\u20136
2. Poplarville beats Columbia AND McComb beats South Pike

#4 seed if: (37.5%)
1. Poplarville beats Columbia AND South Pike beats McComb
2. South Pike beats McComb by 7 or more"""

POPLARVILLE_EXPECTED = """\
Poplarville

#1 seed if: (37.5%)
1. Poplarville beats Columbia AND South Pike beats McComb
2. Poplarville beats Columbia by 7 or more

#2 seed if: (37.5%)
1. Columbia beats Poplarville AND South Pike beats McComb
2. Poplarville beats Columbia by 1\u20136 AND McComb beats South Pike

#3 seed if: (25.0%)
1. Columbia beats Poplarville AND McComb beats South Pike"""

SOUTH_PIKE_EXPECTED = """\
South Pike

#3 seed if: (37.5%)
1. Poplarville beats Columbia AND South Pike beats McComb
2. South Pike beats McComb by 7 or more

#4 seed if: (62.5%)
1. McComb beats South Pike
2. Columbia beats Poplarville AND South Pike beats McComb by 1\u20136"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_lawrence_county_seed_keys():
    """Lawrence County is always eliminated — only seed 5."""
    assert set(_ATOMS["Lawrence County"].keys()) == {5}


def test_atoms_columbia_seed_keys():
    """Columbia always finishes 1st or 2nd — never lower."""
    assert set(_ATOMS["Columbia"].keys()) == {1, 2}


def test_atoms_mccomb_seed_keys():
    """McComb can finish 2nd, 3rd, or 4th."""
    assert set(_ATOMS["McComb"].keys()) == {2, 3, 4}


def test_atoms_poplarville_seed_keys():
    """Poplarville can finish 1st, 2nd, or 3rd."""
    assert set(_ATOMS["Poplarville"].keys()) == {1, 2, 3}


def test_atoms_south_pike_seed_keys():
    """South Pike always finishes 3rd or 4th — never higher."""
    assert set(_ATOMS["South Pike"].keys()) == {3, 4}


def test_atoms_lawrence_county_unconditional():
    """Lawrence County eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["Lawrence County"][5] == [[]]


# ---------------------------------------------------------------------------
# Columbia atoms
# ---------------------------------------------------------------------------


def test_atoms_col_seed1_count():
    """Columbia seed-1 has two alternative atoms."""
    assert len(_ATOMS["Columbia"][1]) == 2


def test_atoms_col_seed1_first_atom_standalone():
    """First COL seed-1 atom: standalone COL beats POP (any margin, any MCB/SP result)."""
    atom = _ATOMS["Columbia"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Columbia"
    assert gr.loser == "Poplarville"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_col_seed1_second_atom():
    """Second COL seed-1 atom: POP beats COL by 1–6 AND MCB beats SP (three-way PD)."""
    atom = _ATOMS["Columbia"][1][1]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_mcb = next(c for c in atom if isinstance(c, GameResult) and c.winner == "McComb")
    assert gr_pop.loser == "Columbia"
    assert gr_pop.min_margin == 1
    assert gr_pop.max_margin == 7  # exclusive upper bound: margins 1–6
    assert gr_mcb.loser == "South Pike"


def test_atoms_col_seed2_count():
    """Columbia seed-2 has two alternative atoms."""
    assert len(_ATOMS["Columbia"][2]) == 2


def test_atoms_col_seed2_first_atom():
    """First COL seed-2 atom: POP wins (any) AND SP wins (any) — both unconstrained."""
    atom = _ATOMS["Columbia"][2][0]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_pop.loser == "Columbia"
    assert gr_pop.min_margin == 1
    assert gr_pop.max_margin is None
    assert gr_sp.loser == "McComb"


def test_atoms_col_seed2_second_atom_standalone():
    """Second COL seed-2 atom: standalone POP by 7+ (Rule 3 lifted MCB/SP condition)."""
    atom = _ATOMS["Columbia"][2][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Poplarville"
    assert gr.loser == "Columbia"
    assert gr.min_margin == 7
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# McComb atoms
# ---------------------------------------------------------------------------


def test_atoms_mcb_seed2_count():
    """McComb seed-2 has exactly one atom."""
    assert len(_ATOMS["McComb"][2]) == 1


def test_atoms_mcb_seed2_atom():
    """MCB seed-2: COL beats POP (any) AND MCB beats SP (any)."""
    atom = _ATOMS["McComb"][2][0]
    assert len(atom) == 2
    gr_col = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Columbia")
    gr_mcb = next(c for c in atom if isinstance(c, GameResult) and c.winner == "McComb")
    assert gr_col.loser == "Poplarville"
    assert gr_mcb.loser == "South Pike"


def test_atoms_mcb_seed3_count():
    """McComb seed-3 has two alternative atoms."""
    assert len(_ATOMS["McComb"][3]) == 2


def test_atoms_mcb_seed3_first_atom():
    """First MCB seed-3 atom: COL wins (any) AND SP wins by 1–6 (three-way PD)."""
    atom = _ATOMS["McComb"][3][0]
    assert len(atom) == 2
    gr_col = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Columbia")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_col.loser == "Poplarville"
    assert gr_sp.loser == "McComb"
    assert gr_sp.min_margin == 1
    assert gr_sp.max_margin == 7  # exclusive upper bound: margins 1–6


def test_atoms_mcb_seed3_second_atom():
    """Second MCB seed-3 atom: POP wins (any) AND MCB wins (any) — both unconstrained."""
    atom = _ATOMS["McComb"][3][1]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_mcb = next(c for c in atom if isinstance(c, GameResult) and c.winner == "McComb")
    assert gr_pop.loser == "Columbia"
    assert gr_mcb.loser == "South Pike"


def test_atoms_mcb_seed4_count():
    """McComb seed-4 has two alternative atoms."""
    assert len(_ATOMS["McComb"][4]) == 2


def test_atoms_mcb_seed4_first_atom():
    """First MCB seed-4 atom: POP wins (any) AND SP wins (any) — both unconstrained."""
    atom = _ATOMS["McComb"][4][0]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_pop.loser == "Columbia"
    assert gr_sp.loser == "McComb"


def test_atoms_mcb_seed4_second_atom_standalone():
    """Second MCB seed-4 atom: standalone SP by 7+ (Rule 3 lifted COL/POP condition)."""
    atom = _ATOMS["McComb"][4][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "South Pike"
    assert gr.loser == "McComb"
    assert gr.min_margin == 7
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Poplarville atoms
# ---------------------------------------------------------------------------


def test_atoms_pop_seed1_count():
    """Poplarville seed-1 has two alternative atoms."""
    assert len(_ATOMS["Poplarville"][1]) == 2


def test_atoms_pop_seed1_first_atom():
    """First POP seed-1 atom: POP wins (any) AND SP wins (any) — both unconstrained."""
    atom = _ATOMS["Poplarville"][1][0]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_pop.loser == "Columbia"
    assert gr_sp.loser == "McComb"


def test_atoms_pop_seed1_second_atom_standalone():
    """Second POP seed-1 atom: standalone POP by 7+ (Rule 3 lifted MCB/SP condition)."""
    atom = _ATOMS["Poplarville"][1][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Poplarville"
    assert gr.loser == "Columbia"
    assert gr.min_margin == 7
    assert gr.max_margin is None


def test_atoms_pop_seed2_count():
    """Poplarville seed-2 has two alternative atoms."""
    assert len(_ATOMS["Poplarville"][2]) == 2


def test_atoms_pop_seed2_first_atom():
    """First POP seed-2 atom: COL wins (any) AND SP wins (any) — both unconstrained."""
    atom = _ATOMS["Poplarville"][2][0]
    assert len(atom) == 2
    gr_col = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Columbia")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_col.loser == "Poplarville"
    assert gr_sp.loser == "McComb"


def test_atoms_pop_seed2_second_atom():
    """Second POP seed-2 atom: POP beats COL by 1–6 AND MCB beats SP (three-way PD)."""
    atom = _ATOMS["Poplarville"][2][1]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_mcb = next(c for c in atom if isinstance(c, GameResult) and c.winner == "McComb")
    assert gr_pop.loser == "Columbia"
    assert gr_pop.min_margin == 1
    assert gr_pop.max_margin == 7  # exclusive upper bound: margins 1–6
    assert gr_mcb.loser == "South Pike"


def test_atoms_pop_seed3_count():
    """Poplarville seed-3 has exactly one atom."""
    assert len(_ATOMS["Poplarville"][3]) == 1


def test_atoms_pop_seed3_atom():
    """POP seed-3: COL beats POP (any) AND MCB beats SP (any)."""
    atom = _ATOMS["Poplarville"][3][0]
    assert len(atom) == 2
    gr_col = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Columbia")
    gr_mcb = next(c for c in atom if isinstance(c, GameResult) and c.winner == "McComb")
    assert gr_col.loser == "Poplarville"
    assert gr_mcb.loser == "South Pike"


# ---------------------------------------------------------------------------
# South Pike atoms
# ---------------------------------------------------------------------------


def test_atoms_sp_seed3_count():
    """South Pike seed-3 has two alternative atoms."""
    assert len(_ATOMS["South Pike"][3]) == 2


def test_atoms_sp_seed3_first_atom():
    """First SP seed-3 atom: POP wins (any) AND SP wins (any) — both unconstrained."""
    atom = _ATOMS["South Pike"][3][0]
    assert len(atom) == 2
    gr_pop = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Poplarville")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_pop.loser == "Columbia"
    assert gr_sp.loser == "McComb"


def test_atoms_sp_seed3_second_atom_standalone():
    """Second SP seed-3 atom: standalone SP by 7+ (Rule 3 lifted COL/POP condition)."""
    atom = _ATOMS["South Pike"][3][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "South Pike"
    assert gr.loser == "McComb"
    assert gr.min_margin == 7
    assert gr.max_margin is None


def test_atoms_sp_seed4_count():
    """South Pike seed-4 has two alternative atoms."""
    assert len(_ATOMS["South Pike"][4]) == 2


def test_atoms_sp_seed4_first_atom_standalone():
    """First SP seed-4 atom: standalone MCB beats SP (any margin, any COL/POP result)."""
    atom = _ATOMS["South Pike"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "McComb"
    assert gr.loser == "South Pike"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_sp_seed4_second_atom():
    """Second SP seed-4 atom: COL wins (any) AND SP wins by 1–6 (three-way PD)."""
    atom = _ATOMS["South Pike"][4][1]
    assert len(atom) == 2
    gr_col = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Columbia")
    gr_sp = next(c for c in atom if isinstance(c, GameResult) and c.winner == "South Pike")
    assert gr_col.loser == "Poplarville"
    assert gr_sp.loser == "McComb"
    assert gr_sp.min_margin == 1
    assert gr_sp.max_margin == 7  # exclusive upper bound: margins 1–6


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1, 2a, 2b, 3a, 3b, 4."""
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "3a", "3b", "4"}


def test_div_dict_scenario1_title():
    """Scenario 1: POP beats COL AND SP beats MCB (non-MS)."""
    assert _DIV_DICT["1"]["title"] == "Poplarville beats Columbia AND South Pike beats McComb"


def test_div_dict_scenario2a_title():
    """Scenario 2a: COL beats POP AND SP beats MCB by 1–6."""
    assert _DIV_DICT["2a"]["title"] == "Columbia beats Poplarville AND South Pike beats McComb by 1\u20136"


def test_div_dict_scenario2b_title():
    """Scenario 2b: COL beats POP AND SP beats MCB by 7 or more."""
    assert _DIV_DICT["2b"]["title"] == "Columbia beats Poplarville AND South Pike beats McComb by 7 or more"


def test_div_dict_scenario3a_title():
    """Scenario 3a: POP beats COL by 1–6 AND MCB beats SP."""
    assert _DIV_DICT["3a"]["title"] == "Poplarville beats Columbia by 1\u20136 AND McComb beats South Pike"


def test_div_dict_scenario3b_title():
    """Scenario 3b: POP beats COL by 7 or more AND MCB beats SP."""
    assert _DIV_DICT["3b"]["title"] == "Poplarville beats Columbia by 7 or more AND McComb beats South Pike"


def test_div_dict_scenario4_title():
    """Scenario 4: COL beats POP AND MCB beats SP (non-MS, actual result)."""
    assert _DIV_DICT["4"]["title"] == "Columbia beats Poplarville AND McComb beats South Pike"


def test_div_dict_scenario1_seeds():
    """Scenario 1: POP #1, COL #2, SP #3, MCB #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "Poplarville"
    assert s["two_seed"] == "Columbia"
    assert s["three_seed"] == "South Pike"
    assert s["four_seed"] == "McComb"


def test_div_dict_scenario2a_seeds():
    """Scenario 2a: COL #1, POP #2, MCB #3, SP #4."""
    s = _DIV_DICT["2a"]
    assert s["one_seed"] == "Columbia"
    assert s["two_seed"] == "Poplarville"
    assert s["three_seed"] == "McComb"
    assert s["four_seed"] == "South Pike"


def test_div_dict_scenario2b_seeds():
    """Scenario 2b: COL #1, POP #2, SP #3, MCB #4."""
    s = _DIV_DICT["2b"]
    assert s["one_seed"] == "Columbia"
    assert s["two_seed"] == "Poplarville"
    assert s["three_seed"] == "South Pike"
    assert s["four_seed"] == "McComb"


def test_div_dict_scenario3a_seeds():
    """Scenario 3a: COL #1, POP #2, MCB #3, SP #4 (small POP upset — COL wins H2H PD)."""
    s = _DIV_DICT["3a"]
    assert s["one_seed"] == "Columbia"
    assert s["two_seed"] == "Poplarville"
    assert s["three_seed"] == "McComb"
    assert s["four_seed"] == "South Pike"


def test_div_dict_scenario3b_seeds():
    """Scenario 3b: POP #1, COL #2, MCB #3, SP #4 (large POP upset — POP wins H2H PD)."""
    s = _DIV_DICT["3b"]
    assert s["one_seed"] == "Poplarville"
    assert s["two_seed"] == "Columbia"
    assert s["three_seed"] == "McComb"
    assert s["four_seed"] == "South Pike"


def test_div_dict_scenario4_seeds():
    """Scenario 4: COL #1, MCB #2, POP #3, SP #4 (actual result)."""
    s = _DIV_DICT["4"]
    assert s["one_seed"] == "Columbia"
    assert s["two_seed"] == "McComb"
    assert s["three_seed"] == "Poplarville"
    assert s["four_seed"] == "South Pike"


def test_div_dict_all_scenarios_eliminated():
    """Lawrence County is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Lawrence County" in scenario["eliminated"], f"Scenario {key} missing LC"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_lawrence_county_key():
    """Lawrence County team dict uses 'eliminated' key only."""
    assert "eliminated" in _TEAM_DICT["Lawrence County"]
    assert len(_TEAM_DICT["Lawrence County"]) == 1


def test_team_dict_columbia_keys():
    """Columbia team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Columbia"].keys()) == {1, 2}


def test_team_dict_mccomb_keys():
    """McComb team dict has keys 2, 3, and 4."""
    assert set(_TEAM_DICT["McComb"].keys()) == {2, 3, 4}


def test_team_dict_poplarville_keys():
    """Poplarville team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Poplarville"].keys()) == {1, 2, 3}


def test_team_dict_south_pike_keys():
    """South Pike team dict has keys 3 and 4."""
    assert set(_TEAM_DICT["South Pike"].keys()) == {3, 4}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_lawrence_county_eliminated():
    """Lawrence County is marked eliminated with zero playoff odds."""
    o = _ODDS["Lawrence County"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_columbia_clinched():
    """Columbia is clinched for the playoffs."""
    o = _ODDS["Columbia"]
    assert o.clinched is True
    assert o.p_playoffs == pytest.approx(1.0)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)


def test_odds_columbia_p1():
    """Columbia has 62.5% chance at #1 seed."""
    assert _ODDS["Columbia"].p1 == pytest.approx(0.625)


def test_odds_columbia_p2():
    """Columbia has 37.5% chance at #2 seed."""
    assert _ODDS["Columbia"].p2 == pytest.approx(0.375)


def test_odds_mccomb_clinched():
    """McComb is clinched for the playoffs."""
    o = _ODDS["McComb"]
    assert o.clinched is True
    assert o.p_playoffs == pytest.approx(1.0)
    assert o.p1 == pytest.approx(0.0)


def test_odds_mccomb():
    """McComb odds: p2=25%, p3=37.5%, p4=37.5%."""
    o = _ODDS["McComb"]
    assert o.p2 == pytest.approx(0.25)
    assert o.p3 == pytest.approx(0.375)
    assert o.p4 == pytest.approx(0.375)


def test_odds_poplarville_clinched():
    """Poplarville is clinched for the playoffs."""
    o = _ODDS["Poplarville"]
    assert o.clinched is True
    assert o.p_playoffs == pytest.approx(1.0)
    assert o.p4 == pytest.approx(0.0)


def test_odds_poplarville():
    """Poplarville odds: p1=37.5%, p2=37.5%, p3=25%."""
    o = _ODDS["Poplarville"]
    assert o.p1 == pytest.approx(0.375)
    assert o.p2 == pytest.approx(0.375)
    assert o.p3 == pytest.approx(0.25)


def test_odds_south_pike_clinched():
    """South Pike is clinched for the playoffs."""
    o = _ODDS["South Pike"]
    assert o.clinched is True
    assert o.p_playoffs == pytest.approx(1.0)
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)


def test_odds_south_pike():
    """South Pike odds: p3=37.5%, p4=62.5%."""
    o = _ODDS["South Pike"]
    assert o.p3 == pytest.approx(0.375)
    assert o.p4 == pytest.approx(0.625)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_lawrence_county():
    """Lawrence County renders as simple eliminated string."""
    assert render_team_scenarios("Lawrence County", _ATOMS, odds=_ODDS) == LAWRENCE_COUNTY_EXPECTED


def test_render_columbia():
    """Columbia renders correctly with standalone first atom and constrained second atom."""
    assert render_team_scenarios("Columbia", _ATOMS, odds=_ODDS) == COLUMBIA_EXPECTED


def test_render_mccomb():
    """McComb renders correctly across three possible seeds."""
    assert render_team_scenarios("McComb", _ATOMS, odds=_ODDS) == MCCOMB_EXPECTED


def test_render_poplarville():
    """Poplarville renders correctly with standalone seed-1 atom."""
    assert render_team_scenarios("Poplarville", _ATOMS, odds=_ODDS) == POPLARVILLE_EXPECTED


def test_render_south_pike():
    """South Pike renders correctly with standalone seed-3 atom."""
    assert render_team_scenarios("South Pike", _ATOMS, odds=_ODDS) == SOUTH_PIKE_EXPECTED
