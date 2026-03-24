"""Scenario output tests for Region 7-3A (2025 season, pre-final-week).

Region 7-3A has two pre-determined outcomes (Port Gibson clinched #4,
Crystal Springs eliminated) and a three-way tie scenario when Jefferson
County upsets Franklin County while Hazlehurst wins.

Teams (alphabetical): Crystal Springs, Franklin County, Hazlehurst,
                       Jefferson County, Port Gibson
Remaining games (cutoff 2025-10-24):
  Franklin County vs Jefferson County — Franklin County won 14–6, margin 8 (actual, scenario 2)
  Crystal Springs vs Hazlehurst       — Hazlehurst won 45–0 (actual)

Known 2025 seeds: Franklin County / Hazlehurst / Jefferson County / Port Gibson
Eliminated: Crystal Springs

Code paths exercised:
  - build_scenario_atoms       — PG/CS unconditional; FC/HAZ/JC each have 1–2 atoms per seed;
                                  FC seed-2 has 2 atoms: JC wins + CS wins (unconstrained) and
                                  JC wins by 1–7 + HAZ wins (margin-sensitive, max_margin=8 excl.)
  - enumerate_division_scenarios — 4 scenarios: 2 MS sub-scenarios when JC wins + HAZ wins
                                    (1a: JC by 1–7; 1b: JC by 8+); 1 non-MS for FC wins
                                    (consolidates both HAZ-wins and CS-wins cases); 1 non-MS
                                    for JC wins + CS wins
  - Three-way tie (HAZ/FC/JC all 3-1): H2H is a perfect cycle; resolved by H2H PD at threshold 8
    (HAZ always #1; FC #2 if JC wins by ≤7; JC #2 if JC wins by 8+)
  - Scenario 2 consolidation: FC beating JC produces FC #1 / HAZ #2 / JC #3 regardless of the
    HAZ/CS game result, so both masks collapse to a single non-MS scenario
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

_FIXTURE = REGION_RESULTS_2025[(3, 7)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Crystal Springs, Franklin County, Hazlehurst, Jefferson County, Port Gibson
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Franklin County/Jefferson County (bit 0), Crystal Springs/Hazlehurst (bit 1)

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

PORT_GIBSON_EXPECTED = "Port Gibson\n\nClinched #4 seed. (100.0%)"
CRYSTAL_SPRINGS_EXPECTED = "Crystal Springs\n\nEliminated. (100.0%)"

FRANKLIN_COUNTY_EXPECTED = """\
Franklin County

#1 seed if: (50.0%)
1. Franklin County beats Jefferson County

#2 seed if: (39.6%)
1. Jefferson County beats Franklin County AND Crystal Springs beats Hazlehurst
2. Jefferson County beats Franklin County by 1\u20137 AND Hazlehurst beats Crystal Springs

#3 seed if: (10.4%)
1. Jefferson County beats Franklin County by 8 or more AND Hazlehurst beats Crystal Springs"""

HAZLEHURST_EXPECTED = """\
Hazlehurst

#1 seed if: (25.0%)
1. Jefferson County beats Franklin County AND Hazlehurst beats Crystal Springs

#2 seed if: (50.0%)
1. Franklin County beats Jefferson County

#3 seed if: (25.0%)
1. Jefferson County beats Franklin County AND Crystal Springs beats Hazlehurst"""

JEFFERSON_COUNTY_EXPECTED = """\
Jefferson County

#1 seed if: (25.0%)
1. Jefferson County beats Franklin County AND Crystal Springs beats Hazlehurst

#2 seed if: (10.4%)
1. Jefferson County beats Franklin County by 8 or more AND Hazlehurst beats Crystal Springs

#3 seed if: (64.6%)
1. Franklin County beats Jefferson County
2. Jefferson County beats Franklin County by 1\u20137 AND Hazlehurst beats Crystal Springs"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_crystal_springs_seed_keys():
    """Crystal Springs is always eliminated — only seed 5."""
    assert set(_ATOMS["Crystal Springs"].keys()) == {5}


def test_atoms_port_gibson_seed_keys():
    """Port Gibson is always #4 — only seed 4."""
    assert set(_ATOMS["Port Gibson"].keys()) == {4}


def test_atoms_franklin_county_seed_keys():
    """Franklin County can finish 1st, 2nd, or 3rd."""
    assert set(_ATOMS["Franklin County"].keys()) == {1, 2, 3}


def test_atoms_hazlehurst_seed_keys():
    """Hazlehurst can finish 1st, 2nd, or 3rd."""
    assert set(_ATOMS["Hazlehurst"].keys()) == {1, 2, 3}


def test_atoms_jefferson_county_seed_keys():
    """Jefferson County can finish 1st, 2nd, or 3rd."""
    assert set(_ATOMS["Jefferson County"].keys()) == {1, 2, 3}


def test_atoms_crystal_springs_unconditional():
    """Crystal Springs is eliminated unconditionally — atom is [[]]."""
    assert _ATOMS["Crystal Springs"][5] == [[]]


def test_atoms_port_gibson_unconditional():
    """Port Gibson clinched #4 unconditionally — atom is [[]]."""
    assert _ATOMS["Port Gibson"][4] == [[]]


# ---------------------------------------------------------------------------
# Franklin County atoms
# ---------------------------------------------------------------------------


def test_atoms_fc_seed1_count():
    """FC seed-1 has exactly one atom."""
    assert len(_ATOMS["Franklin County"][1]) == 1


def test_atoms_fc_seed1_atom():
    """FC seed-1: FC beats JC (any margin)."""
    atom = _ATOMS["Franklin County"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Franklin County"
    assert gr.loser == "Jefferson County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_fc_seed2_count():
    """FC seed-2 has two alternative atoms."""
    assert len(_ATOMS["Franklin County"][2]) == 2


def test_atoms_fc_seed2_first_atom():
    """First FC seed-2 atom: JC wins (any margin) AND CS wins (any margin)."""
    atom = _ATOMS["Franklin County"][2][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_cs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Crystal Springs")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 1
    assert gr_jc.max_margin is None
    assert gr_cs.loser == "Hazlehurst"
    assert gr_cs.min_margin == 1
    assert gr_cs.max_margin is None


def test_atoms_fc_seed2_second_atom_margin_sensitive():
    """Second FC seed-2 atom: JC wins by 1–7 AND HAZ wins (margin-sensitive)."""
    atom = _ATOMS["Franklin County"][2][1]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_haz = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Hazlehurst")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 1
    assert gr_jc.max_margin == 8  # exclusive upper bound: margins 1–7
    assert gr_haz.loser == "Crystal Springs"
    assert gr_haz.min_margin == 1
    assert gr_haz.max_margin is None


def test_atoms_fc_seed3_count():
    """FC seed-3 has exactly one atom."""
    assert len(_ATOMS["Franklin County"][3]) == 1


def test_atoms_fc_seed3_atom():
    """FC seed-3: JC wins by 8 or more AND HAZ wins."""
    atom = _ATOMS["Franklin County"][3][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_haz = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Hazlehurst")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 8
    assert gr_jc.max_margin is None
    assert gr_haz.loser == "Crystal Springs"
    assert gr_haz.min_margin == 1
    assert gr_haz.max_margin is None


# ---------------------------------------------------------------------------
# Hazlehurst atoms
# ---------------------------------------------------------------------------


def test_atoms_hazlehurst_seed1_count():
    """HAZ seed-1 has exactly one atom."""
    assert len(_ATOMS["Hazlehurst"][1]) == 1


def test_atoms_hazlehurst_seed1_atom():
    """HAZ seed-1: JC beats FC (any margin) AND HAZ beats CS (any margin)."""
    atom = _ATOMS["Hazlehurst"][1][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_haz = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Hazlehurst")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 1
    assert gr_jc.max_margin is None
    assert gr_haz.loser == "Crystal Springs"


def test_atoms_hazlehurst_seed2_count():
    """HAZ seed-2 has exactly one atom."""
    assert len(_ATOMS["Hazlehurst"][2]) == 1


def test_atoms_hazlehurst_seed2_atom():
    """HAZ seed-2: FC beats JC (any margin) — unconditional on HAZ/CS result."""
    atom = _ATOMS["Hazlehurst"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Franklin County"
    assert gr.loser == "Jefferson County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_hazlehurst_seed3_count():
    """HAZ seed-3 has exactly one atom."""
    assert len(_ATOMS["Hazlehurst"][3]) == 1


def test_atoms_hazlehurst_seed3_atom():
    """HAZ seed-3: JC beats FC (any margin) AND CS beats HAZ."""
    atom = _ATOMS["Hazlehurst"][3][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_cs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Crystal Springs")
    assert gr_jc.loser == "Franklin County"
    assert gr_cs.loser == "Hazlehurst"


# ---------------------------------------------------------------------------
# Jefferson County atoms
# ---------------------------------------------------------------------------


def test_atoms_jc_seed1_count():
    """JC seed-1 has exactly one atom."""
    assert len(_ATOMS["Jefferson County"][1]) == 1


def test_atoms_jc_seed1_atom():
    """JC seed-1: JC beats FC (any margin) AND CS beats HAZ."""
    atom = _ATOMS["Jefferson County"][1][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_cs = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Crystal Springs")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 1
    assert gr_jc.max_margin is None
    assert gr_cs.loser == "Hazlehurst"


def test_atoms_jc_seed2_count():
    """JC seed-2 has exactly one atom."""
    assert len(_ATOMS["Jefferson County"][2]) == 1


def test_atoms_jc_seed2_atom():
    """JC seed-2: JC beats FC by 8 or more AND HAZ beats CS."""
    atom = _ATOMS["Jefferson County"][2][0]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_haz = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Hazlehurst")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 8
    assert gr_jc.max_margin is None
    assert gr_haz.loser == "Crystal Springs"


def test_atoms_jc_seed3_count():
    """JC seed-3 has two alternative atoms."""
    assert len(_ATOMS["Jefferson County"][3]) == 2


def test_atoms_jc_seed3_first_atom():
    """First JC seed-3 atom: FC beats JC (any margin)."""
    atom = _ATOMS["Jefferson County"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Franklin County"
    assert gr.loser == "Jefferson County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_jc_seed3_second_atom():
    """Second JC seed-3 atom: JC beats FC by 1–7 AND HAZ beats CS."""
    atom = _ATOMS["Jefferson County"][3][1]
    assert len(atom) == 2
    gr_jc = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Jefferson County")
    gr_haz = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Hazlehurst")
    assert gr_jc.loser == "Franklin County"
    assert gr_jc.min_margin == 1
    assert gr_jc.max_margin == 8  # exclusive upper bound: margins 1–7
    assert gr_haz.loser == "Crystal Springs"


# ---------------------------------------------------------------------------
# Division scenarios dict — keys and count
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1a, 1b, 2, 3."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2", "3"}


def test_div_dict_scenario1a_title():
    """Scenario 1a title: JC beats FC by 1–7 AND HAZ beats CS."""
    assert _DIV_DICT["1a"]["title"] == "Jefferson County beats Franklin County by 1\u20137 AND Hazlehurst beats Crystal Springs"


def test_div_dict_scenario1b_title():
    """Scenario 1b title: JC beats FC by 8 or more AND HAZ beats CS."""
    assert _DIV_DICT["1b"]["title"] == "Jefferson County beats Franklin County by 8 or more AND Hazlehurst beats Crystal Springs"


def test_div_dict_scenario2_title():
    """Scenario 2 title: FC beats JC (no HAZ/CS mention — consolidated)."""
    assert _DIV_DICT["2"]["title"] == "Franklin County beats Jefferson County"


def test_div_dict_scenario3_title():
    """Scenario 3 title: JC beats FC AND CS beats HAZ."""
    assert _DIV_DICT["3"]["title"] == "Jefferson County beats Franklin County AND Crystal Springs beats Hazlehurst"


def test_div_dict_scenario1a_seeds():
    """Scenario 1a: HAZ #1, FC #2, JC #3, PG #4."""
    s = _DIV_DICT["1a"]
    assert s["one_seed"] == "Hazlehurst"
    assert s["two_seed"] == "Franklin County"
    assert s["three_seed"] == "Jefferson County"
    assert s["four_seed"] == "Port Gibson"


def test_div_dict_scenario1b_seeds():
    """Scenario 1b: HAZ #1, JC #2, FC #3, PG #4."""
    s = _DIV_DICT["1b"]
    assert s["one_seed"] == "Hazlehurst"
    assert s["two_seed"] == "Jefferson County"
    assert s["three_seed"] == "Franklin County"
    assert s["four_seed"] == "Port Gibson"


def test_div_dict_scenario2_seeds():
    """Scenario 2: FC #1, HAZ #2, JC #3, PG #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Franklin County"
    assert s["two_seed"] == "Hazlehurst"
    assert s["three_seed"] == "Jefferson County"
    assert s["four_seed"] == "Port Gibson"


def test_div_dict_scenario3_seeds():
    """Scenario 3: JC #1, FC #2, HAZ #3, PG #4."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Jefferson County"
    assert s["two_seed"] == "Franklin County"
    assert s["three_seed"] == "Hazlehurst"
    assert s["four_seed"] == "Port Gibson"


def test_div_dict_all_scenarios_eliminated():
    """Crystal Springs is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Crystal Springs" in scenario["eliminated"], f"Scenario {key} missing CS in eliminated"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_crystal_springs_key():
    """Crystal Springs team dict uses 'eliminated' key."""
    cs = _TEAM_DICT["Crystal Springs"]
    assert "eliminated" in cs


def test_team_dict_port_gibson_key():
    """Port Gibson team dict uses numeric key 4 only."""
    pg = _TEAM_DICT["Port Gibson"]
    assert list(pg.keys()) == [4]


def test_team_dict_port_gibson_clinched():
    """Port Gibson #4 odds = 1.0."""
    pg = _TEAM_DICT["Port Gibson"]
    assert pg[4]["odds"] == pytest.approx(1.0)


def test_team_dict_franklin_county_keys():
    """Franklin County team dict has keys 1, 2, 3."""
    assert set(_TEAM_DICT["Franklin County"].keys()) == {1, 2, 3}


def test_team_dict_hazlehurst_keys():
    """Hazlehurst team dict has keys 1, 2, 3."""
    assert set(_TEAM_DICT["Hazlehurst"].keys()) == {1, 2, 3}


def test_team_dict_jefferson_county_keys():
    """Jefferson County team dict has keys 1, 2, 3."""
    assert set(_TEAM_DICT["Jefferson County"].keys()) == {1, 2, 3}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_crystal_springs_eliminated():
    """Crystal Springs is marked eliminated with zero playoff odds."""
    o = _ODDS["Crystal Springs"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_port_gibson_clinched():
    """Port Gibson is marked clinched with p4=1.0."""
    o = _ODDS["Port Gibson"]
    assert o.clinched is True
    assert o.p4 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_franklin_county_clinched():
    """Franklin County is clinched for the playoffs."""
    assert _ODDS["Franklin County"].clinched is True
    assert _ODDS["Franklin County"].p_playoffs == pytest.approx(1.0)


def test_odds_franklin_county_p1():
    """Franklin County has 50% chance at #1 seed."""
    assert _ODDS["Franklin County"].p1 == pytest.approx(0.5)


def test_odds_franklin_county_p2():
    """Franklin County has ~39.6% chance at #2 seed."""
    assert _ODDS["Franklin County"].p2 == pytest.approx(0.39583333333333337)


def test_odds_franklin_county_p3():
    """Franklin County has ~10.4% chance at #3 seed."""
    assert _ODDS["Franklin County"].p3 == pytest.approx(0.10416666666666667)


def test_odds_hazlehurst_clinched():
    """Hazlehurst is clinched for the playoffs."""
    assert _ODDS["Hazlehurst"].clinched is True
    assert _ODDS["Hazlehurst"].p_playoffs == pytest.approx(1.0)


def test_odds_hazlehurst_equal():
    """Hazlehurst has equal 25/50/25% spread across seeds 1/2/3."""
    o = _ODDS["Hazlehurst"]
    assert o.p1 == pytest.approx(0.25)
    assert o.p2 == pytest.approx(0.5)
    assert o.p3 == pytest.approx(0.25)


def test_odds_jefferson_county_clinched():
    """Jefferson County is clinched for the playoffs."""
    assert _ODDS["Jefferson County"].clinched is True
    assert _ODDS["Jefferson County"].p_playoffs == pytest.approx(1.0)


def test_odds_jefferson_county_p1():
    """Jefferson County has 25% chance at #1 seed."""
    assert _ODDS["Jefferson County"].p1 == pytest.approx(0.25)


def test_odds_jefferson_county_p2():
    """Jefferson County has ~10.4% chance at #2 seed."""
    assert _ODDS["Jefferson County"].p2 == pytest.approx(0.10416666666666667)


def test_odds_jefferson_county_p3():
    """Jefferson County has ~64.6% chance at #3 seed."""
    assert _ODDS["Jefferson County"].p3 == pytest.approx(0.6458333333333334)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_crystal_springs():
    """Crystal Springs renders as simple eliminated string."""
    assert render_team_scenarios("Crystal Springs", _ATOMS, odds=_ODDS) == CRYSTAL_SPRINGS_EXPECTED


def test_render_port_gibson():
    """Port Gibson renders as clinched #4 string."""
    assert render_team_scenarios("Port Gibson", _ATOMS, odds=_ODDS) == PORT_GIBSON_EXPECTED


def test_render_franklin_county():
    """Franklin County renders correctly with margin-sensitive seed-2 atoms."""
    assert render_team_scenarios("Franklin County", _ATOMS, odds=_ODDS) == FRANKLIN_COUNTY_EXPECTED


def test_render_hazlehurst():
    """Hazlehurst renders correctly across three possible seeds."""
    assert render_team_scenarios("Hazlehurst", _ATOMS, odds=_ODDS) == HAZLEHURST_EXPECTED


def test_render_jefferson_county():
    """Jefferson County renders correctly with margin-sensitive seed-3 atoms."""
    assert render_team_scenarios("Jefferson County", _ATOMS, odds=_ODDS) == JEFFERSON_COUNTY_EXPECTED
