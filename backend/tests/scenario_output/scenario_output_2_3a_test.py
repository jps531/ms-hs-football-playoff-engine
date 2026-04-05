"""Scenario output tests for Region 2-3A (2025 season, pre-final-week).

Region 2-3A is a 4-team region with no eliminated teams — all four teams
are clinched for the playoffs. The final week produces two independent
tiebreaker situations, each resolved at the same margin threshold of 9.

Teams (alphabetical): Coahoma County, Holly Springs, Independence, North Panola
Remaining games (cutoff 2025-10-24):
  Coahoma County vs Independence — Coahoma County won 30–0, margin 30 (actual, scenario 2)
  Holly Springs vs North Panola  — North Panola won 34–14, margin 20 (actual, scenario 2)

Known 2025 seeds: Coahoma County / North Panola / Independence / Holly Springs
Eliminated: none

Code paths exercised:
  - build_scenario_atoms       — all four teams clinched (no seed-5 atoms);
                                  CC seed-1 second atom: IND by 1–8 + NP wins (margin-sensitive);
                                  CC seed-2 second atom: standalone [IND by 9+] (Rule 3 lifted HS/NP condition);
                                  IND seed-1 second atom: standalone [IND by 9+] (same lift, symmetric);
                                  HS seed-3 second atom: standalone [HS by 9+] (Rule 3 lifted CC/IND condition);
                                  NP seed-4 second atom: standalone [HS by 9+] (same lift, symmetric)
  - enumerate_division_scenarios — 6 scenarios: 1a/1b (IND upsets CC + NP wins, threshold 9);
                                    2 (CC wins + NP wins, non-MS); 3 (IND wins + HS wins, non-MS);
                                    4a/4b (CC wins + HS upsets NP, threshold 9)
  - Three-way tie (CC/IND/NP at 2-1 when IND beats CC + NP wins): perfect H2H cycle;
    threshold 9 on the CC/IND margin (IND by 1–8 → CC #1; IND by 9+ → IND #1)
  - Three-way tie (IND/HS/NP at 1-2 when CC wins + HS wins): perfect H2H cycle;
    threshold 9 on the HS/NP margin (HS by 1–8 → NP #3; HS by 9+ → HS #3)
  - Both thresholds are 9 — one per game, symmetric by structure
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

_FIXTURE = REGION_RESULTS_2025[(3, 2)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Coahoma County, Holly Springs, Independence, North Panola
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Coahoma County/Independence (bit 0), Holly Springs/North Panola (bit 1)

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

COAHOMA_COUNTY_EXPECTED = """\
Coahoma County

#1 seed if: (66.7%)
1. Coahoma County beats Independence
2. Independence beats Coahoma County by 1\u20138 AND North Panola beats Holly Springs

#2 seed if: (33.3%)
1. Independence beats Coahoma County by 9 or more
2. Independence beats Coahoma County AND Holly Springs beats North Panola"""

HOLLY_SPRINGS_EXPECTED = """\
Holly Springs

#3 seed if: (33.3%)
1. Holly Springs beats North Panola by 9 or more
2. Independence beats Coahoma County AND Holly Springs beats North Panola

#4 seed if: (66.7%)
1. North Panola beats Holly Springs
2. Coahoma County beats Independence AND Holly Springs beats North Panola by 1\u20138"""

INDEPENDENCE_EXPECTED = """\
Independence

#1 seed if: (33.3%)
1. Independence beats Coahoma County by 9 or more
2. Independence beats Coahoma County AND Holly Springs beats North Panola

#2 seed if: (41.7%)
1. Coahoma County beats Independence AND Holly Springs beats North Panola
2. Independence beats Coahoma County by 1\u20138 AND North Panola beats Holly Springs

#3 seed if: (25.0%)
1. Coahoma County beats Independence AND North Panola beats Holly Springs"""

NORTH_PANOLA_EXPECTED = """\
North Panola

#2 seed if: (25.0%)
1. Coahoma County beats Independence AND North Panola beats Holly Springs

#3 seed if: (41.7%)
1. Independence beats Coahoma County AND North Panola beats Holly Springs
2. Coahoma County beats Independence AND Holly Springs beats North Panola by 1\u20138

#4 seed if: (33.3%)
1. Holly Springs beats North Panola by 9 or more
2. Independence beats Coahoma County AND Holly Springs beats North Panola"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_no_eliminated_seeds():
    """No team has a seed-5 (eliminated) entry — all four are clinched."""
    for team in _TEAMS:
        assert 5 not in _ATOMS.get(team, {})


def test_atoms_coahoma_county_seed_keys():
    """Coahoma County can finish 1st or 2nd only."""
    assert set(_ATOMS["Coahoma County"].keys()) == {1, 2}


def test_atoms_holly_springs_seed_keys():
    """Holly Springs can finish 3rd or 4th only."""
    assert set(_ATOMS["Holly Springs"].keys()) == {3, 4}


def test_atoms_independence_seed_keys():
    """Independence can finish 1st, 2nd, or 3rd."""
    assert set(_ATOMS["Independence"].keys()) == {1, 2, 3}


def test_atoms_north_panola_seed_keys():
    """North Panola can finish 2nd, 3rd, or 4th."""
    assert set(_ATOMS["North Panola"].keys()) == {2, 3, 4}


# ---------------------------------------------------------------------------
# Coahoma County atoms
# ---------------------------------------------------------------------------


def test_atoms_cc_seed1_count():
    """CC seed-1 has two alternative atoms."""
    assert len(_ATOMS["Coahoma County"][1]) == 2


def test_atoms_cc_seed1_first_atom():
    """First CC seed-1 atom: CC beats IND (any margin) — unconditional on HS/NP."""
    atom = _ATOMS["Coahoma County"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Coahoma County"
    assert gr.loser == "Independence"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_cc_seed1_second_atom():
    """Second CC seed-1 atom: IND beats CC by 1–8 AND NP beats HS (margin-sensitive)."""
    atom = _ATOMS["Coahoma County"][1][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_np = next(c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola")
    assert gr_ind.loser == "Coahoma County"
    assert gr_ind.min_margin == 1
    assert gr_ind.max_margin == 9  # exclusive upper bound: margins 1–8
    assert gr_np.loser == "Holly Springs"
    assert gr_np.min_margin == 1
    assert gr_np.max_margin is None


def test_atoms_cc_seed2_count():
    """CC seed-2 has two alternative atoms."""
    assert len(_ATOMS["Coahoma County"][2]) == 2


def test_atoms_cc_seed2_first_atom():
    """First CC seed-2 atom: standalone IND by 9+ (Rule 3 lifted the HS/NP condition)."""
    atom = _ATOMS["Coahoma County"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Independence"
    assert gr.loser == "Coahoma County"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_cc_seed2_second_atom_standalone():
    """Second CC seed-2 atom: IND wins (any) AND HS wins (any) — both unconstrained."""
    atom = _ATOMS["Coahoma County"][2][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_ind.loser == "Coahoma County"
    assert gr_ind.min_margin == 1
    assert gr_ind.max_margin is None
    assert gr_hs.loser == "North Panola"
    assert gr_hs.min_margin == 1
    assert gr_hs.max_margin is None


# ---------------------------------------------------------------------------
# Holly Springs atoms
# ---------------------------------------------------------------------------


def test_atoms_hs_seed3_count():
    """HS seed-3 has two alternative atoms."""
    assert len(_ATOMS["Holly Springs"][3]) == 2


def test_atoms_hs_seed3_first_atom():
    """First HS seed-3 atom: standalone HS by 9+ (Rule 3 lifted the CC/IND condition)."""
    atom = _ATOMS["Holly Springs"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Holly Springs"
    assert gr.loser == "North Panola"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_hs_seed3_second_atom_standalone():
    """Second HS seed-3 atom: IND wins (any) AND HS wins (any) — both unconstrained."""
    atom = _ATOMS["Holly Springs"][3][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_ind.loser == "Coahoma County"
    assert gr_hs.loser == "North Panola"
    assert gr_hs.min_margin == 1
    assert gr_hs.max_margin is None


def test_atoms_hs_seed4_count():
    """HS seed-4 has two alternative atoms."""
    assert len(_ATOMS["Holly Springs"][4]) == 2


def test_atoms_hs_seed4_first_atom():
    """First HS seed-4 atom: NP beats HS (any margin) — unconditional on CC/IND."""
    atom = _ATOMS["Holly Springs"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "North Panola"
    assert gr.loser == "Holly Springs"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_hs_seed4_second_atom():
    """Second HS seed-4 atom: CC wins (any) AND HS wins by 1–8 (margin-sensitive)."""
    atom = _ATOMS["Holly Springs"][4][1]
    assert len(atom) == 2
    gr_cc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_cc.loser == "Independence"
    assert gr_cc.min_margin == 1
    assert gr_cc.max_margin is None
    assert gr_hs.loser == "North Panola"
    assert gr_hs.min_margin == 1
    assert gr_hs.max_margin == 9  # exclusive upper bound: margins 1–8


# ---------------------------------------------------------------------------
# Independence atoms
# ---------------------------------------------------------------------------


def test_atoms_ind_seed1_count():
    """IND seed-1 has two alternative atoms."""
    assert len(_ATOMS["Independence"][1]) == 2


def test_atoms_ind_seed1_first_atom():
    """First IND seed-1 atom: standalone IND by 9+ (Rule 3 lifted the HS/NP condition)."""
    atom = _ATOMS["Independence"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Independence"
    assert gr.loser == "Coahoma County"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_ind_seed1_second_atom_standalone():
    """Second IND seed-1 atom: IND wins (any) AND HS wins (any) — both unconstrained."""
    atom = _ATOMS["Independence"][1][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_ind.loser == "Coahoma County"
    assert gr_hs.loser == "North Panola"


def test_atoms_ind_seed2_count():
    """IND seed-2 has two alternative atoms."""
    assert len(_ATOMS["Independence"][2]) == 2


def test_atoms_ind_seed2_first_atom():
    """First IND seed-2 atom: CC wins (any) AND HS wins (any) — both unconstrained."""
    atom = _ATOMS["Independence"][2][0]
    assert len(atom) == 2
    gr_cc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_cc.loser == "Independence"
    assert gr_hs.loser == "North Panola"


def test_atoms_ind_seed2_second_atom():
    """Second IND seed-2 atom: IND beats CC by 1–8 AND NP beats HS."""
    atom = _ATOMS["Independence"][2][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_np = next(c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola")
    assert gr_ind.loser == "Coahoma County"
    assert gr_ind.min_margin == 1
    assert gr_ind.max_margin == 9  # exclusive upper bound: margins 1–8
    assert gr_np.loser == "Holly Springs"


def test_atoms_ind_seed3_count():
    """IND seed-3 has exactly one atom."""
    assert len(_ATOMS["Independence"][3]) == 1


def test_atoms_ind_seed3_atom():
    """IND seed-3: CC beats IND (any) AND NP beats HS (any)."""
    atom = _ATOMS["Independence"][3][0]
    assert len(atom) == 2
    gr_cc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County")
    gr_np = next(c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola")
    assert gr_cc.loser == "Independence"
    assert gr_np.loser == "Holly Springs"


# ---------------------------------------------------------------------------
# North Panola atoms
# ---------------------------------------------------------------------------


def test_atoms_np_seed2_count():
    """NP seed-2 has exactly one atom."""
    assert len(_ATOMS["North Panola"][2]) == 1


def test_atoms_np_seed2_atom():
    """NP seed-2: CC beats IND (any) AND NP beats HS (any)."""
    atom = _ATOMS["North Panola"][2][0]
    assert len(atom) == 2
    gr_cc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County")
    gr_np = next(c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola")
    assert gr_cc.loser == "Independence"
    assert gr_np.loser == "Holly Springs"


def test_atoms_np_seed3_count():
    """NP seed-3 has two alternative atoms."""
    assert len(_ATOMS["North Panola"][3]) == 2


def test_atoms_np_seed3_first_atom():
    """First NP seed-3 atom: IND wins (any) AND NP wins (any) — both unconstrained."""
    atom = _ATOMS["North Panola"][3][0]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_np = next(c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola")
    assert gr_ind.loser == "Coahoma County"
    assert gr_np.loser == "Holly Springs"


def test_atoms_np_seed3_second_atom():
    """Second NP seed-3 atom: CC wins (any) AND HS wins by 1–8 (margin-sensitive)."""
    atom = _ATOMS["North Panola"][3][1]
    assert len(atom) == 2
    gr_cc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_cc.loser == "Independence"
    assert gr_hs.loser == "North Panola"
    assert gr_hs.min_margin == 1
    assert gr_hs.max_margin == 9  # exclusive upper bound: margins 1–8


def test_atoms_np_seed4_count():
    """NP seed-4 has two alternative atoms."""
    assert len(_ATOMS["North Panola"][4]) == 2


def test_atoms_np_seed4_first_atom():
    """First NP seed-4 atom: standalone HS by 9+ (Rule 3 lifted the CC/IND condition)."""
    atom = _ATOMS["North Panola"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Holly Springs"
    assert gr.loser == "North Panola"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_np_seed4_second_atom_standalone():
    """Second NP seed-4 atom: IND wins (any) AND HS wins (any) — both unconstrained."""
    atom = _ATOMS["North Panola"][4][1]
    assert len(atom) == 2
    gr_ind = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Independence")
    gr_hs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Holly Springs")
    assert gr_ind.loser == "Coahoma County"
    assert gr_hs.loser == "North Panola"


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1a, 1b, 2, 3, 4a, 4b."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2", "3", "4a", "4b"}


def test_div_dict_scenario1a_title():
    """Scenario 1a: IND beats CC by 1–8 AND NP beats HS."""
    assert _DIV_DICT["1a"]["title"] == "Independence beats Coahoma County by 1\u20138 AND North Panola beats Holly Springs"


def test_div_dict_scenario1b_title():
    """Scenario 1b: IND beats CC by 9 or more AND NP beats HS."""
    assert _DIV_DICT["1b"]["title"] == "Independence beats Coahoma County by 9 or more AND North Panola beats Holly Springs"


def test_div_dict_scenario2_title():
    """Scenario 2: CC beats IND AND NP beats HS (non-MS)."""
    assert _DIV_DICT["2"]["title"] == "Coahoma County beats Independence AND North Panola beats Holly Springs"


def test_div_dict_scenario3_title():
    """Scenario 3: IND beats CC AND HS beats NP (non-MS)."""
    assert _DIV_DICT["3"]["title"] == "Independence beats Coahoma County AND Holly Springs beats North Panola"


def test_div_dict_scenario4a_title():
    """Scenario 4a: CC beats IND AND HS beats NP by 9 or more."""
    assert _DIV_DICT["4a"]["title"] == "Coahoma County beats Independence AND Holly Springs beats North Panola by 9 or more"


def test_div_dict_scenario4b_title():
    """Scenario 4b: CC beats IND AND HS beats NP by 1–8."""
    assert _DIV_DICT["4b"]["title"] == "Coahoma County beats Independence AND Holly Springs beats North Panola by 1\u20138"


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: CC #1, IND #2, NP #3, HS #4."""
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "Coahoma County"
    assert s["two_seed"] == "Independence"
    assert s["three_seed"] == "North Panola"
    assert s["four_seed"] == "Holly Springs"


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: IND #1, CC #2, NP #3, HS #4."""
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "Independence"
    assert s["two_seed"] == "Coahoma County"
    assert s["three_seed"] == "North Panola"
    assert s["four_seed"] == "Holly Springs"


def test_div_dict_scenario2_seeds():
    """Scenario 2: CC #1, NP #2, IND #3, HS #4 (actual result)."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Coahoma County"
    assert s["two_seed"] == "North Panola"
    assert s["three_seed"] == "Independence"
    assert s["four_seed"] == "Holly Springs"


def test_div_dict_scenario3_seeds():
    """Scenario 3: IND #1, CC #2, HS #3, NP #4."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Independence"
    assert s["two_seed"] == "Coahoma County"
    assert s["three_seed"] == "Holly Springs"
    assert s["four_seed"] == "North Panola"


def test_div_dict_scenario4a_seeds():
    """Scenario 4a: CC #1, IND #2, HS #3, NP #4."""
    s = _DIV_DICT["4a"]
    assert s["one_seed"] == "Coahoma County"
    assert s["two_seed"] == "Independence"
    assert s["three_seed"] == "Holly Springs"
    assert s["four_seed"] == "North Panola"


def test_div_dict_scenario4b_seeds():
    """Scenario 4b: CC #1, IND #2, NP #3, HS #4."""
    s = _DIV_DICT["4b"]
    assert s["one_seed"] == "Coahoma County"
    assert s["two_seed"] == "Independence"
    assert s["three_seed"] == "North Panola"
    assert s["four_seed"] == "Holly Springs"


def test_div_dict_no_eliminated_teams():
    """No scenario has any eliminated teams."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["eliminated"] == [], f"Scenario {key} unexpectedly has eliminated teams"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_no_eliminated_keys():
    """No team has an 'eliminated' key in team_dict — all are clinched."""
    for team in _TEAMS:
        assert "eliminated" not in _TEAM_DICT.get(team, {})


def test_team_dict_coahoma_county_keys():
    """CC team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Coahoma County"].keys()) == {1, 2}


def test_team_dict_holly_springs_keys():
    """HS team dict has keys 3 and 4."""
    assert set(_TEAM_DICT["Holly Springs"].keys()) == {3, 4}


def test_team_dict_independence_keys():
    """IND team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Independence"].keys()) == {1, 2, 3}


def test_team_dict_north_panola_keys():
    """NP team dict has keys 2, 3, and 4."""
    assert set(_TEAM_DICT["North Panola"].keys()) == {2, 3, 4}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_all_clinched():
    """All four teams are marked clinched with p_playoffs=1.0."""
    for team in _TEAMS:
        o = _ODDS[team]
        assert o.clinched is True, f"{team} should be clinched"
        assert o.p_playoffs == pytest.approx(1.0), f"{team} p_playoffs should be 1.0"


def test_odds_no_eliminated():
    """No team is marked eliminated."""
    for team in _TEAMS:
        assert _ODDS[team].eliminated is False, f"{team} should not be eliminated"


def test_odds_coahoma_county():
    """CC odds: p1≈66.7%, p2≈33.3%, p3=p4=0."""
    o = _ODDS["Coahoma County"]
    assert o.p1 == pytest.approx(2 / 3)
    assert o.p2 == pytest.approx(1 / 3)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)


def test_odds_holly_springs():
    """HS odds: p1=p2=0, p3≈33.3%, p4≈66.7%."""
    o = _ODDS["Holly Springs"]
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(1 / 3)
    assert o.p4 == pytest.approx(2 / 3)


def test_odds_independence():
    """IND odds: p1≈33.3%, p2≈41.7%, p3=25%, p4=0."""
    o = _ODDS["Independence"]
    assert o.p1 == pytest.approx(1 / 3)
    assert o.p2 == pytest.approx(5 / 12)
    assert o.p3 == pytest.approx(0.25)
    assert o.p4 == pytest.approx(0.0)


def test_odds_north_panola():
    """NP odds: p1=0, p2=25%, p3≈41.7%, p4≈33.3%."""
    o = _ODDS["North Panola"]
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.25)
    assert o.p3 == pytest.approx(5 / 12)
    assert o.p4 == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_coahoma_county():
    """Coahoma County renders correctly with margin-sensitive seed-1 atom."""
    assert render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS) == COAHOMA_COUNTY_EXPECTED


def test_render_holly_springs():
    """Holly Springs renders correctly with standalone seed-3 margin atom."""
    assert render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS) == HOLLY_SPRINGS_EXPECTED


def test_render_independence():
    """Independence renders correctly with standalone seed-1 margin atom."""
    assert render_team_scenarios("Independence", _ATOMS, odds=_ODDS) == INDEPENDENCE_EXPECTED


def test_render_north_panola():
    """North Panola renders correctly with standalone seed-4 margin atom."""
    assert render_team_scenarios("North Panola", _ATOMS, odds=_ODDS) == NORTH_PANOLA_EXPECTED
