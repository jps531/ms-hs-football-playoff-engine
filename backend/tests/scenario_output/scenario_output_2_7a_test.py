"""Scenario output tests for Region 2-7A (2025 season, pre-final-week).

Region 2-7A has a clean structure: two teams are locked into seeds 1 and 2,
one team is always eliminated, and three teams compete for seeds 3 and 4 with
a single margin-sensitive threshold.

Pre-cutoff records (cutoff 2025-10-31):
  Oxford          4-0  — clinched #1 outright (no competition)
  Germantown      3-1  — clinched #2 outright (no competition regardless of GER/MUR result)
  Madison Central 2-2
  Starkville      2-2
  Clinton         1-3
  Murrah          0-4  — already eliminated (cannot reach top-4)

Remaining games (all 2025-11-07):
  Germantown vs Murrah     — irrelevant to seeding (GER already locked at #2)
  Clinton vs Madison Central — bit 1; determines seeds 3-4 and elimination
  Oxford vs Starkville       — bit 2; matters only if Clinton beats MC

Margin-sensitive threshold (bit 1 game):
  Clinton beats Madison Central by 1–7 AND Oxford beats Starkville
      → 3-way tie CLN/STV/MC all at 2-3; Clinton loses H2H PD vs MC
      → Oxford #1, Germantown #2, Starkville #3, Madison Central #4, Clinton eliminated

  Clinton beats Madison Central by 8 or more (any Oxford/Starkville result)
      → Clinton wins H2H PD advantage over MC in 3-way tiebreaker
      → Oxford #1, Germantown #2, Starkville #3, Clinton #4, Madison Central eliminated

Actual 2025 result: Madison Central beat Clinton; Starkville beat Oxford
  → Final seeds: Oxford, Germantown, Madison Central, Starkville (Scenario 1)

Known 2025 seeds: Oxford / Germantown / Madison Central / Starkville
Eliminated: Clinton, Murrah

Scenario keys: 1, 2, 3a, 3b
  (enumerate_division_scenarios deduplicates scenarios with identical conditions
   and seeding, so formerly-duplicate 4a/4b are suppressed.)

Teams (alphabetical): Clinton, Germantown, Madison Central, Murrah, Oxford, Starkville
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

_FIXTURE = REGION_RESULTS_2025[(7, 2)]
_CUTOFF = "2025-10-31"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Clinton, Germantown, Madison Central, Murrah, Oxford, Starkville
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Germantown/Murrah (bit 0), Clinton/Madison Central (bit 1), Oxford/Starkville (bit 2)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

OXFORD_EXPECTED = "Oxford\n\nClinched #1 seed. (100.0%)"

GERMANTOWN_EXPECTED = "Germantown\n\nClinched #2 seed. (100.0%)"

MURRAH_EXPECTED = "Murrah\n\nEliminated. (100.0%)"

STARKVILLE_EXPECTED = """\
Starkville

#3 seed if: (50.0%)
1. Clinton beats Madison Central

#4 seed if: (50.0%)
1. Madison Central beats Clinton"""

MADISON_CENTRAL_EXPECTED = """\
Madison Central

#3 seed if: (50.0%)
1. Madison Central beats Clinton

#4 seed if: (14.6%)
1. Clinton beats Madison Central by 1\u20137 AND Oxford beats Starkville

Eliminated if: (35.4%)
1. Clinton beats Madison Central by 8 or more
2. Clinton beats Madison Central AND Starkville beats Oxford"""

CLINTON_EXPECTED = """\
Clinton

#4 seed if: (35.4%)
1. Clinton beats Madison Central by 8 or more
2. Clinton beats Madison Central AND Starkville beats Oxford

Eliminated if: (64.6%)
1. Madison Central beats Clinton
2. Clinton beats Madison Central by 1\u20137 AND Oxford beats Starkville"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_oxford_seed_keys():
    """Oxford is always #1 — only seed 1."""
    assert set(_ATOMS["Oxford"].keys()) == {1}


def test_atoms_germantown_seed_keys():
    """Germantown is always #2 — only seed 2."""
    assert set(_ATOMS["Germantown"].keys()) == {2}


def test_atoms_murrah_seed_keys():
    """Murrah is always eliminated — only seed 5."""
    assert set(_ATOMS["Murrah"].keys()) == {5}


def test_atoms_starkville_seed_keys():
    """Starkville can finish #3 or #4 — never higher or lower than that."""
    assert set(_ATOMS["Starkville"].keys()) == {3, 4}


def test_atoms_madison_central_seed_keys():
    """Madison Central can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["Madison Central"].keys()) == {3, 4, 5}


def test_atoms_clinton_seed_keys():
    """Clinton can finish #4 or be eliminated — never #3 or higher."""
    assert set(_ATOMS["Clinton"].keys()) == {4, 5}


# ---------------------------------------------------------------------------
# Unconditional atoms
# ---------------------------------------------------------------------------


def test_atoms_oxford_unconditional():
    """Oxford is #1 unconditionally — atom is [[]]."""
    assert _ATOMS["Oxford"][1] == [[]]


def test_atoms_germantown_unconditional():
    """Germantown is #2 unconditionally — atom is [[]]."""
    assert _ATOMS["Germantown"][2] == [[]]


def test_atoms_murrah_unconditional():
    """Murrah is eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["Murrah"][5] == [[]]


# ---------------------------------------------------------------------------
# Starkville atoms
# ---------------------------------------------------------------------------


def test_atoms_starkville_seed3_count():
    """Starkville seed-3 has exactly one atom."""
    assert len(_ATOMS["Starkville"][3]) == 1


def test_atoms_starkville_seed3_atom():
    """Starkville seed-3: Clinton beats Madison Central (any margin)."""
    atom = _ATOMS["Starkville"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Clinton"
    assert gr.loser == "Madison Central"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_starkville_seed4_count():
    """Starkville seed-4 has exactly one atom."""
    assert len(_ATOMS["Starkville"][4]) == 1


def test_atoms_starkville_seed4_atom():
    """Starkville seed-4: Madison Central beats Clinton (any margin)."""
    atom = _ATOMS["Starkville"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Madison Central"
    assert gr.loser == "Clinton"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Madison Central atoms
# ---------------------------------------------------------------------------


def test_atoms_mc_seed3_count():
    """Madison Central seed-3 has exactly one atom."""
    assert len(_ATOMS["Madison Central"][3]) == 1


def test_atoms_mc_seed3_atom():
    """Madison Central seed-3: MC beats Clinton (any margin — MC goes to 3-2 and wins H2H over STV)."""
    atom = _ATOMS["Madison Central"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Madison Central"
    assert gr.loser == "Clinton"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_mc_seed4_count():
    """Madison Central seed-4 has exactly one atom."""
    assert len(_ATOMS["Madison Central"][4]) == 1


def test_atoms_mc_seed4_atom():
    """Madison Central seed-4: Clinton by 1-7 AND Oxford beats Starkville (3-way tie; MC wins H2H PD at low margin)."""
    atom = _ATOMS["Madison Central"][4][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clinton"
    assert gr0.loser == "Madison Central"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 8  # exclusive; covers margins 1-7
    gr1 = atom[1]
    assert gr1.winner == "Oxford"
    assert gr1.loser == "Starkville"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_mc_eliminated_count():
    """Madison Central has exactly two elimination atoms."""
    assert len(_ATOMS["Madison Central"][5]) == 2


def test_atoms_mc_eliminated_atom0():
    """MC elimination first atom: Clinton beats MC by 8+ (Clinton wins 3-way H2H PD even if OXF beats STV)."""
    atom = _ATOMS["Madison Central"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Clinton"
    assert gr.loser == "Madison Central"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_mc_eliminated_atom1():
    """MC elimination second atom: Clinton beats MC AND Starkville beats Oxford (Clinton wins H2H vs MC)."""
    atom = _ATOMS["Madison Central"][5][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clinton"
    assert gr0.loser == "Madison Central"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Starkville"
    assert gr1.loser == "Oxford"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Clinton atoms
# ---------------------------------------------------------------------------


def test_atoms_clinton_seed4_count():
    """Clinton seed-4 has exactly two atoms."""
    assert len(_ATOMS["Clinton"][4]) == 2


def test_atoms_clinton_seed4_atom0():
    """Clinton seed-4 first atom: Clinton beats MC by 8+ (any OXF/STV result — Clinton wins H2H PD)."""
    atom = _ATOMS["Clinton"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Clinton"
    assert gr.loser == "Madison Central"
    assert gr.min_margin == 8
    assert gr.max_margin is None


def test_atoms_clinton_seed4_atom1():
    """Clinton seed-4 second atom: Clinton beats MC AND Starkville beats Oxford (Clinton wins H2H)."""
    atom = _ATOMS["Clinton"][4][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clinton"
    assert gr0.loser == "Madison Central"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Starkville"
    assert gr1.loser == "Oxford"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_clinton_eliminated_count():
    """Clinton has exactly two elimination atoms."""
    assert len(_ATOMS["Clinton"][5]) == 2


def test_atoms_clinton_eliminated_atom0():
    """Clinton elimination first atom: Madison Central beats Clinton (MC wins H2H, CLN cannot reach top-4)."""
    atom = _ATOMS["Clinton"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Madison Central"
    assert gr.loser == "Clinton"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_clinton_eliminated_atom1():
    """Clinton elimination second atom: Clinton by 1-7 AND Oxford beats Starkville (MC wins 3-way H2H PD)."""
    atom = _ATOMS["Clinton"][5][1]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Clinton"
    assert gr0.loser == "Madison Central"
    assert gr0.min_margin == 1
    assert gr0.max_margin == 8  # exclusive; covers margins 1-7
    gr1 = atom[1]
    assert gr1.winner == "Oxford"
    assert gr1.loser == "Starkville"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1, 2, 3a, 3b."""
    assert set(_DIV_DICT.keys()) == {"1", "2", "3a", "3b"}


def test_div_dict_scenario1_title():
    """Scenario 1: Madison Central beats Clinton (no margin condition — MC wins outright)."""
    assert _DIV_DICT["1"]["title"] == "Madison Central beats Clinton"


def test_div_dict_scenario2_title():
    """Scenario 2: Clinton beats MC AND Starkville beats Oxford (no margin condition)."""
    assert _DIV_DICT["2"]["title"] == "Clinton beats Madison Central AND Starkville beats Oxford"


def test_div_dict_scenario3a_title():
    """Scenario 3a: Clinton beats MC by 8+ (covers all OXF/STV outcomes)."""
    assert _DIV_DICT["3a"]["title"] == "Clinton beats Madison Central by 8 or more"


def test_div_dict_scenario3b_title():
    """Scenario 3b: Clinton by 1-7 AND Oxford beats Starkville (3-way tie; MC wins H2H PD)."""
    assert _DIV_DICT["3b"]["title"] == "Clinton beats Madison Central by 1\u20137 AND Oxford beats Starkville"


def test_div_dict_scenario1_seeds():
    """Scenario 1 (actual result): Oxford #1, Germantown #2, MC #3, Starkville #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "Oxford"
    assert s["two_seed"] == "Germantown"
    assert s["three_seed"] == "Madison Central"
    assert s["four_seed"] == "Starkville"
    assert set(s["eliminated"]) == {"Clinton", "Murrah"}


def test_div_dict_scenario2_seeds():
    """Scenario 2: Oxford #1, Germantown #2, Starkville #3, Clinton #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Oxford"
    assert s["two_seed"] == "Germantown"
    assert s["three_seed"] == "Starkville"
    assert s["four_seed"] == "Clinton"
    assert set(s["eliminated"]) == {"Madison Central", "Murrah"}


def test_div_dict_scenario3a_seeds():
    """Scenario 3a: Oxford #1, Germantown #2, Starkville #3, Clinton #4 (CLN wins H2H PD by 8+)."""
    s = _DIV_DICT["3a"]
    assert s["one_seed"] == "Oxford"
    assert s["two_seed"] == "Germantown"
    assert s["three_seed"] == "Starkville"
    assert s["four_seed"] == "Clinton"
    assert set(s["eliminated"]) == {"Madison Central", "Murrah"}


def test_div_dict_scenario3b_seeds():
    """Scenario 3b: Oxford #1, Germantown #2, Starkville #3, Madison Central #4 (MC wins H2H PD at low margin)."""
    s = _DIV_DICT["3b"]
    assert s["one_seed"] == "Oxford"
    assert s["two_seed"] == "Germantown"
    assert s["three_seed"] == "Starkville"
    assert s["four_seed"] == "Madison Central"
    assert set(s["eliminated"]) == {"Clinton", "Murrah"}


def test_div_dict_oxford_always_one():
    """Oxford is #1 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["one_seed"] == "Oxford", f"Scenario {key}: Oxford unexpectedly not #1"


def test_div_dict_germantown_always_two():
    """Germantown is #2 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["two_seed"] == "Germantown", f"Scenario {key}: Germantown unexpectedly not #2"


def test_div_dict_murrah_always_eliminated():
    """Murrah is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Murrah" in scenario["eliminated"], f"Scenario {key}: Murrah unexpectedly not eliminated"


def test_div_dict_starkville_seed():
    """Starkville is #4 when MC beats Clinton (MC goes 3-1, beats STV in tiebreakers), #3 otherwise."""
    assert _DIV_DICT["1"]["four_seed"] == "Starkville", "Scenario 1: Starkville should be #4"
    assert _DIV_DICT["2"]["three_seed"] == "Starkville", "Scenario 2: Starkville should be #3"
    assert _DIV_DICT["3a"]["three_seed"] == "Starkville", "Scenario 3a: Starkville should be #3"
    assert _DIV_DICT["3b"]["three_seed"] == "Starkville", "Scenario 3b: Starkville should be #3"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_oxford_key():
    """Oxford team dict uses only seed 1."""
    assert set(_TEAM_DICT["Oxford"].keys()) == {1}


def test_team_dict_germantown_key():
    """Germantown team dict uses only seed 2."""
    assert set(_TEAM_DICT["Germantown"].keys()) == {2}


def test_team_dict_murrah_key():
    """Murrah team dict uses only 'eliminated' key."""
    assert set(_TEAM_DICT["Murrah"].keys()) == {"eliminated"}


def test_team_dict_starkville_keys():
    """Starkville team dict has seeds 3 and 4."""
    assert set(_TEAM_DICT["Starkville"].keys()) == {3, 4}


def test_team_dict_madison_central_keys():
    """Madison Central team dict has seeds 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Madison Central"].keys()) == {3, 4, "eliminated"}


def test_team_dict_clinton_keys():
    """Clinton team dict has seed 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Clinton"].keys()) == {4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_oxford_clinched():
    """Oxford is clinched at #1 with p1=1.0."""
    o = _ODDS["Oxford"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_germantown_clinched():
    """Germantown is clinched at #2 with p2=1.0."""
    o = _ODDS["Germantown"]
    assert o.clinched is True
    assert o.p2 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_murrah_eliminated():
    """Murrah is eliminated with zero playoff odds."""
    o = _ODDS["Murrah"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_starkville():
    """Starkville: clinched; p3=1/2, p4=1/2 — always makes playoffs, never above #4."""
    o = _ODDS["Starkville"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.5)
    assert o.p4 == pytest.approx(0.5)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_madison_central():
    """Madison Central: p3=1/2, p4=7/48, p_playoffs=31/48."""
    o = _ODDS["Madison Central"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.5)
    assert o.p4 == pytest.approx(7 / 48)
    assert o.p_playoffs == pytest.approx(31 / 48)


def test_odds_clinton():
    """Clinton: p4=17/48, p_playoffs=17/48 — only path to playoffs is #4 seed."""
    o = _ODDS["Clinton"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(17 / 48)
    assert o.p_playoffs == pytest.approx(17 / 48)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_oxford():
    """Oxford renders as clinched #1 string."""
    assert render_team_scenarios("Oxford", _ATOMS, odds=_ODDS) == OXFORD_EXPECTED


def test_render_germantown():
    """Germantown renders as clinched #2 string."""
    assert render_team_scenarios("Germantown", _ATOMS, odds=_ODDS) == GERMANTOWN_EXPECTED


def test_render_murrah():
    """Murrah renders as simple eliminated string."""
    assert render_team_scenarios("Murrah", _ATOMS, odds=_ODDS) == MURRAH_EXPECTED


def test_render_starkville():
    """Starkville renders with one seed-3 and one seed-4 path."""
    assert render_team_scenarios("Starkville", _ATOMS, odds=_ODDS) == STARKVILLE_EXPECTED


def test_render_madison_central():
    """Madison Central renders with one seed-3, one seed-4, and two elimination paths."""
    assert render_team_scenarios("Madison Central", _ATOMS, odds=_ODDS) == MADISON_CENTRAL_EXPECTED


def test_render_clinton():
    """Clinton renders with two seed-4 paths and two elimination paths."""
    assert render_team_scenarios("Clinton", _ATOMS, odds=_ODDS) == CLINTON_EXPECTED
