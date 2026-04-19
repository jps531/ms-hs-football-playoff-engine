"""Scenario output tests for Region 4-5A (2025 season, pre-final-week).

Region 4-5A is notable for two clinched seeds and four teams competing for
the remaining two playoff spots (plus two elimination spots).

Pre-cutoff records (cutoff 2025-10-31):
  Stone 4-0, Wayne County 3-1, Purvis 2-2, Northeast Jones 1-3,
  East Central 1-3, Vancleave 1-3

Stone is clinched #1 (4-0, unbeatable record).
Wayne County is clinched #2 (3-1; only loss to Stone; leads all others by at
least one game with no path for any 2-loss team to catch it).

All three remaining games are on 2025-11-06:
  Northeast Jones vs Wayne County  — Northeast Jones won 14–7  (actual, scenario 3; bit 0)
  Purvis vs Vancleave              — Purvis won 33–0           (actual, scenario 3; bit 1)
  East Central vs Stone            — Stone won 35–21           (actual, scenario 3; bit 2)

Known 2025 seeds: Stone / Wayne County / Purvis / Northeast Jones
Eliminated: East Central, Vancleave

Scenario structure (6 total, no margin sensitivity):
  1: Vancleave beats Purvis AND Stone beats East Central
     → Stone #1, WC #2, Vancleave #3, Purvis #4 (NJ and EC eliminated)
  2: WC beats NJ AND Purvis beats VAN AND Stone beats EC
     → Stone #1, WC #2, Purvis #3, NJ #4 (VAN and EC eliminated)
  3: NJ beats WC AND Purvis beats VAN (actual result; Stone/EC irrelevant)
     → Stone #1, WC #2, Purvis #3, NJ #4 (EC and VAN eliminated)
  4: WC beats NJ AND VAN beats Purvis AND EC beats Stone
     → Stone #1, WC #2, EC #3, VAN #4 (Purvis and NJ eliminated)
  5: WC beats NJ AND Purvis beats VAN AND EC beats Stone
     → Stone #1, WC #2, Purvis #3, EC #4 (VAN and NJ eliminated)

Note: scenarios 1 and 5 produce identical top-4 seedings from different game outcomes.
Scenarios 2 and 3 also produce identical seedings from different game outcomes.

Bit ordering: Northeast Jones/Wayne County is bit 0; Purvis/Vancleave is bit 1;
East Central/Stone is bit 2.

Teams (alphabetical): East Central, Northeast Jones, Purvis, Stone, Vancleave, Wayne County
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

_FIXTURE = REGION_RESULTS_2025[(5, 4)]
_CUTOFF = "2025-10-31"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: East Central, Northeast Jones, Purvis, Stone, Vancleave, Wayne County
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Northeast Jones/Wayne County (bit 0), Purvis/Vancleave (bit 1), East Central/Stone (bit 2)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

STONE_EXPECTED = "Stone\n\nClinched #1 seed. (100.0%)"
WAYNE_COUNTY_EXPECTED = "Wayne County\n\nClinched #2 seed. (100.0%)"

EAST_CENTRAL_EXPECTED = """\
East Central

#3 seed if: (12.5%)
1. Wayne County beats Northeast Jones AND Vancleave beats Purvis AND East Central beats Stone

#4 seed if: (12.5%)
1. Wayne County beats Northeast Jones AND Purvis beats Vancleave AND East Central beats Stone

Eliminated if: (75.0%)
1. Northeast Jones beats Wayne County
2. Stone beats East Central"""

NORTHEAST_JONES_EXPECTED = """\
Northeast Jones

#4 seed if: (37.5%)
1. Purvis beats Vancleave AND Stone beats East Central
2. Northeast Jones beats Wayne County AND Purvis beats Vancleave AND East Central beats Stone

Eliminated if: (62.5%)
1. Vancleave beats Purvis
2. Wayne County beats Northeast Jones AND East Central beats Stone"""

PURVIS_EXPECTED = """\
Purvis

#3 seed if: (50.0%)
1. Purvis beats Vancleave

#4 seed if: (37.5%)
1. Vancleave beats Purvis AND Stone beats East Central
2. Northeast Jones beats Wayne County AND Vancleave beats Purvis AND East Central beats Stone

Eliminated if: (12.5%)
1. Wayne County beats Northeast Jones AND Vancleave beats Purvis AND East Central beats Stone"""

VANCLEAVE_EXPECTED = """\
Vancleave

#3 seed if: (37.5%)
1. Vancleave beats Purvis AND Stone beats East Central
2. Northeast Jones beats Wayne County AND Vancleave beats Purvis AND East Central beats Stone

#4 seed if: (12.5%)
1. Wayne County beats Northeast Jones AND Vancleave beats Purvis AND East Central beats Stone

Eliminated if: (50.0%)
1. Purvis beats Vancleave"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_stone_seed_keys():
    """Stone is always #1 — only seed 1."""
    assert set(_ATOMS["Stone"].keys()) == {1}


def test_atoms_wayne_county_seed_keys():
    """Wayne County is always #2 — only seed 2."""
    assert set(_ATOMS["Wayne County"].keys()) == {2}


def test_atoms_purvis_seed_keys():
    """Purvis can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["Purvis"].keys()) == {3, 4, 5}


def test_atoms_northeast_jones_seed_keys():
    """Northeast Jones can finish #4 or be eliminated — never in the top three."""
    assert set(_ATOMS["Northeast Jones"].keys()) == {4, 5}


def test_atoms_east_central_seed_keys():
    """East Central can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["East Central"].keys()) == {3, 4, 5}


def test_atoms_vancleave_seed_keys():
    """Vancleave can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["Vancleave"].keys()) == {3, 4, 5}


# ---------------------------------------------------------------------------
# Stone and Wayne County — unconditional clinches
# ---------------------------------------------------------------------------


def test_atoms_stone_unconditional():
    """Stone clinched #1 unconditionally — atom is [[]]."""
    assert _ATOMS["Stone"][1] == [[]]


def test_atoms_wayne_county_unconditional():
    """Wayne County clinched #2 unconditionally — atom is [[]]."""
    assert _ATOMS["Wayne County"][2] == [[]]


# ---------------------------------------------------------------------------
# East Central eliminated atoms — two conditions cover all 6 elimination masks
# ---------------------------------------------------------------------------


def test_atoms_east_central_eliminated_count():
    """East Central seed-5 has exactly two atoms."""
    assert len(_ATOMS["East Central"][5]) == 2


def test_atoms_east_central_eliminated_atom0():
    """EC eliminated atom 0: NJ beats WC — covers all masks where NJ beats WC."""
    atom = _ATOMS["East Central"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Northeast Jones"
    assert gr.loser == "Wayne County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_east_central_eliminated_atom1():
    """EC eliminated atom 1: Stone beats EC — covers remaining elimination masks."""
    atom = _ATOMS["East Central"][5][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Stone"
    assert gr.loser == "East Central"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Northeast Jones eliminated atoms — two conditions cover all 5 elimination masks
# ---------------------------------------------------------------------------


def test_atoms_northeast_jones_eliminated_count():
    """Northeast Jones seed-5 has exactly two atoms."""
    assert len(_ATOMS["Northeast Jones"][5]) == 2


def test_atoms_northeast_jones_eliminated_atom0():
    """NJ eliminated atom 0: Vancleave beats Purvis (any margin) — NJ can never reach top-4."""
    atom = _ATOMS["Northeast Jones"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Vancleave"
    assert gr.loser == "Purvis"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_northeast_jones_eliminated_atom1():
    """NJ eliminated atom 1: WC beats NJ AND EC beats Stone — Purvis/Vancleave dropped as redundant."""
    atom = _ATOMS["Northeast Jones"][5][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Wayne County" in winners
    assert "East Central" in winners


# ---------------------------------------------------------------------------
# Purvis atoms — three seed positions, no margin sensitivity
# ---------------------------------------------------------------------------


def test_atoms_purvis_seed3_count():
    """Purvis seed-3 has exactly one atom."""
    assert len(_ATOMS["Purvis"][3]) == 1


def test_atoms_purvis_seed3_atom():
    """Purvis seed-3: Purvis beats Vancleave (any margin) — always #3 when Purvis wins."""
    atom = _ATOMS["Purvis"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Purvis"
    assert gr.loser == "Vancleave"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_purvis_seed4_count():
    """Purvis seed-4 has exactly two atoms."""
    assert len(_ATOMS["Purvis"][4]) == 2


def test_atoms_purvis_seed4_atom0():
    """Purvis seed-4 first atom: VAN beats Purvis AND Stone beats EC (NJ/WC game irrelevant)."""
    atom = _ATOMS["Purvis"][4][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Vancleave"
    assert gr0.loser == "Purvis"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Stone"
    assert gr1.loser == "East Central"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_purvis_seed4_atom1():
    """Purvis seed-4 second atom: NJ beats WC AND VAN beats Purvis AND EC beats Stone."""
    atom = _ATOMS["Purvis"][4][1]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Northeast Jones" in winners
    assert "Vancleave" in winners
    assert "East Central" in winners


def test_atoms_purvis_seed5_count():
    """Purvis seed-5 (eliminated) has exactly one atom."""
    assert len(_ATOMS["Purvis"][5]) == 1


def test_atoms_purvis_seed5_atom():
    """Purvis eliminated: WC beats NJ AND VAN beats Purvis AND EC beats Stone (scenario 4)."""
    atom = _ATOMS["Purvis"][5][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Wayne County" in winners
    assert "Vancleave" in winners
    assert "East Central" in winners


# ---------------------------------------------------------------------------
# Vancleave atoms — mirror of Purvis with reversed game outcomes
# ---------------------------------------------------------------------------


def test_atoms_vancleave_seed3_count():
    """Vancleave seed-3 has exactly two atoms."""
    assert len(_ATOMS["Vancleave"][3]) == 2


def test_atoms_vancleave_seed3_atom0():
    """Vancleave seed-3 first atom: VAN beats Purvis AND Stone beats EC (NJ/WC irrelevant)."""
    atom = _ATOMS["Vancleave"][3][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Vancleave"
    assert gr0.loser == "Purvis"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Stone"
    assert gr1.loser == "East Central"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_vancleave_seed3_atom1():
    """Vancleave seed-3 second atom: NJ beats WC AND VAN beats Purvis AND EC beats Stone."""
    atom = _ATOMS["Vancleave"][3][1]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Northeast Jones" in winners
    assert "Vancleave" in winners
    assert "East Central" in winners


def test_atoms_vancleave_seed4_count():
    """Vancleave seed-4 has exactly one atom."""
    assert len(_ATOMS["Vancleave"][4]) == 1


def test_atoms_vancleave_seed4_atom():
    """Vancleave seed-4: WC beats NJ AND VAN beats Purvis AND EC beats Stone (scenario 4)."""
    atom = _ATOMS["Vancleave"][4][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Wayne County" in winners
    assert "Vancleave" in winners
    assert "East Central" in winners


def test_atoms_vancleave_seed5_count():
    """Vancleave seed-5 (eliminated) has exactly one atom."""
    assert len(_ATOMS["Vancleave"][5]) == 1


def test_atoms_vancleave_seed5_atom():
    """Vancleave eliminated: Purvis beats Vancleave (any margin) — no path to playoffs when Purvis wins."""
    atom = _ATOMS["Vancleave"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Purvis"
    assert gr.loser == "Vancleave"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Northeast Jones atoms
# ---------------------------------------------------------------------------


def test_atoms_northeast_jones_seed4_count():
    """Northeast Jones seed-4 has exactly two atoms."""
    assert len(_ATOMS["Northeast Jones"][4]) == 2


def test_atoms_northeast_jones_seed4_atom0():
    """NJ seed-4 first atom: Purvis beats VAN AND Stone beats EC (NJ/WC game absent)."""
    atom = _ATOMS["Northeast Jones"][4][0]
    assert len(atom) == 2
    gr0 = atom[0]
    assert gr0.winner == "Purvis"
    assert gr0.loser == "Vancleave"
    assert gr0.min_margin == 1
    assert gr0.max_margin is None
    gr1 = atom[1]
    assert gr1.winner == "Stone"
    assert gr1.loser == "East Central"
    assert gr1.min_margin == 1
    assert gr1.max_margin is None


def test_atoms_northeast_jones_seed4_atom0_nj_wc_absent():
    """NJ seed-4 first atom omits the NJ/WC game — that result is irrelevant to NJ's #4 finish here."""
    atom = _ATOMS["Northeast Jones"][4][0]
    nj_wc_teams = {"Northeast Jones", "Wayne County"}
    for gr in atom:
        assert {gr.winner, gr.loser} != nj_wc_teams


def test_atoms_northeast_jones_seed4_atom1():
    """NJ seed-4 second atom: NJ beats WC AND Purvis beats VAN AND EC beats Stone."""
    atom = _ATOMS["Northeast Jones"][4][1]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Northeast Jones" in winners
    assert "Purvis" in winners
    assert "East Central" in winners


# ---------------------------------------------------------------------------
# East Central atoms
# ---------------------------------------------------------------------------


def test_atoms_east_central_seed3_count():
    """East Central seed-3 has exactly one atom."""
    assert len(_ATOMS["East Central"][3]) == 1


def test_atoms_east_central_seed3_atom():
    """EC seed-3: WC beats NJ AND VAN beats Purvis AND EC beats Stone (only path to #3 for EC)."""
    atom = _ATOMS["East Central"][3][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Wayne County" in winners
    assert "Vancleave" in winners
    assert "East Central" in winners


def test_atoms_east_central_seed4_count():
    """East Central seed-4 has exactly one atom."""
    assert len(_ATOMS["East Central"][4]) == 1


def test_atoms_east_central_seed4_atom():
    """EC seed-4: WC beats NJ AND Purvis beats VAN AND EC beats Stone (only path to #4 for EC)."""
    atom = _ATOMS["East Central"][4][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Wayne County" in winners
    assert "Purvis" in winners
    assert "East Central" in winners


# ---------------------------------------------------------------------------
# Cross-game independence: NJ/WC game absent from Purvis/VAN/NJ seed-4 atom-0
# ---------------------------------------------------------------------------


def test_nj_wc_absent_from_purvis_seed4_atom0():
    """Purvis seed-4 first atom omits NJ/WC — irrelevant when VAN wins AND Stone wins."""
    atom = _ATOMS["Purvis"][4][0]
    nj_wc_teams = {"Northeast Jones", "Wayne County"}
    for gr in atom:
        assert {gr.winner, gr.loser} != nj_wc_teams


def test_nj_wc_absent_from_vancleave_seed3_atom0():
    """Vancleave seed-3 first atom omits NJ/WC — irrelevant when VAN wins AND Stone wins."""
    atom = _ATOMS["Vancleave"][3][0]
    nj_wc_teams = {"Northeast Jones", "Wayne County"}
    for gr in atom:
        assert {gr.winner, gr.loser} != nj_wc_teams


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1–6 (no margin sensitivity; scenario 1 split by Stone/EC result)."""
    assert set(_DIV_DICT.keys()) == {"1", "2", "3", "4", "5", "6"}


def test_div_dict_scenario1_title():
    """Scenario 1: Vancleave beats Purvis AND Stone beats East Central."""
    assert _DIV_DICT["1"]["title"] == "Vancleave beats Purvis AND Stone beats East Central"


def test_div_dict_scenario2_title():
    """Scenario 2: WC beats NJ AND Purvis beats VAN AND Stone beats EC."""
    assert (
        _DIV_DICT["2"]["title"]
        == "Wayne County beats Northeast Jones AND Purvis beats Vancleave AND Stone beats East Central"
    )


def test_div_dict_scenario3_title():
    """Scenario 3 (actual): NJ beats WC AND Purvis beats VAN (Stone/EC irrelevant)."""
    assert _DIV_DICT["3"]["title"] == "Northeast Jones beats Wayne County AND Purvis beats Vancleave"


def test_div_dict_scenario4_title():
    """Scenario 4: WC beats NJ AND VAN beats Purvis AND EC beats Stone."""
    assert (
        _DIV_DICT["4"]["title"]
        == "Wayne County beats Northeast Jones AND Vancleave beats Purvis AND East Central beats Stone"
    )


def test_div_dict_scenario5_title():
    """Scenario 5: NJ beats WC AND Vancleave beats Purvis AND EC beats Stone → Stone/WC/VAN/Purvis."""
    assert (
        _DIV_DICT["5"]["title"]
        == "Northeast Jones beats Wayne County AND Vancleave beats Purvis AND East Central beats Stone"
    )


def test_div_dict_scenario6_title():
    """Scenario 6: WC beats NJ AND Purvis beats VAN AND EC beats Stone → Stone/WC/Purvis/EC."""
    assert (
        _DIV_DICT["6"]["title"]
        == "Wayne County beats Northeast Jones AND Purvis beats Vancleave AND East Central beats Stone"
    )


def test_div_dict_scenario1_seeds():
    """Scenario 1: Stone #1, WC #2, Vancleave #3, Purvis #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "Vancleave"
    assert s["four_seed"] == "Purvis"
    assert "Northeast Jones" in s["eliminated"]
    assert "East Central" in s["eliminated"]


def test_div_dict_scenario2_seeds():
    """Scenario 2: Stone #1, WC #2, Purvis #3, NJ #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "Purvis"
    assert s["four_seed"] == "Northeast Jones"
    assert "Vancleave" in s["eliminated"]
    assert "East Central" in s["eliminated"]


def test_div_dict_scenario3_seeds():
    """Scenario 3 (actual): Stone #1, WC #2, Purvis #3, NJ #4."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "Purvis"
    assert s["four_seed"] == "Northeast Jones"
    assert "East Central" in s["eliminated"]
    assert "Vancleave" in s["eliminated"]


def test_div_dict_scenario4_seeds():
    """Scenario 4: Stone #1, WC #2, EC #3, Vancleave #4."""
    s = _DIV_DICT["4"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "East Central"
    assert s["four_seed"] == "Vancleave"
    assert "Purvis" in s["eliminated"]
    assert "Northeast Jones" in s["eliminated"]


def test_div_dict_scenario5_seeds():
    """Scenario 5: Stone #1, WC #2, Vancleave #3, Purvis #4 (NJ and EC eliminated)."""
    s = _DIV_DICT["5"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "Vancleave"
    assert s["four_seed"] == "Purvis"
    assert "Northeast Jones" in s["eliminated"]
    assert "East Central" in s["eliminated"]


def test_div_dict_scenario6_seeds():
    """Scenario 6: Stone #1, WC #2, Purvis #3, EC #4."""
    s = _DIV_DICT["6"]
    assert s["one_seed"] == "Stone"
    assert s["two_seed"] == "Wayne County"
    assert s["three_seed"] == "Purvis"
    assert s["four_seed"] == "East Central"
    assert "Vancleave" in s["eliminated"]
    assert "Northeast Jones" in s["eliminated"]


def test_div_dict_stone_always_one():
    """Stone is #1 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["one_seed"] == "Stone", f"Scenario {key}: Stone unexpectedly not #1"


def test_div_dict_wayne_county_always_two():
    """Wayne County is #2 in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["two_seed"] == "Wayne County", f"Scenario {key}: WC unexpectedly not #2"


def test_div_dict_northeast_jones_never_one_two_three():
    """Northeast Jones is never in the top three."""
    for key, scenario in _DIV_DICT.items():
        assert scenario.get("one_seed") != "Northeast Jones"
        assert scenario.get("two_seed") != "Northeast Jones"
        assert scenario.get("three_seed") != "Northeast Jones"


def test_div_dict_scenarios_2_and_3_identical_seedings():
    """Scenarios 2 and 3 produce identical seedings from different game outcomes."""
    s2 = _DIV_DICT["2"]
    s3 = _DIV_DICT["3"]
    assert s2["one_seed"] == s3["one_seed"]
    assert s2["two_seed"] == s3["two_seed"]
    assert s2["three_seed"] == s3["three_seed"]
    assert s2["four_seed"] == s3["four_seed"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_stone_key():
    """Stone team dict uses numeric key 1 only."""
    assert list(_TEAM_DICT["Stone"].keys()) == [1]


def test_team_dict_wayne_county_key():
    """Wayne County team dict uses numeric key 2 only."""
    assert list(_TEAM_DICT["Wayne County"].keys()) == [2]


def test_team_dict_purvis_keys():
    """Purvis team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Purvis"].keys()) == {3, 4, "eliminated"}


def test_team_dict_northeast_jones_keys():
    """Northeast Jones team dict has keys 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Northeast Jones"].keys()) == {4, "eliminated"}


def test_team_dict_east_central_keys():
    """East Central team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["East Central"].keys()) == {3, 4, "eliminated"}


def test_team_dict_vancleave_keys():
    """Vancleave team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Vancleave"].keys()) == {3, 4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_stone_clinched():
    """Stone is clinched #1 with p1=1.0."""
    o = _ODDS["Stone"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_wayne_county_clinched():
    """Wayne County is clinched #2 with p2=1.0."""
    o = _ODDS["Wayne County"]
    assert o.clinched is True
    assert o.p2 == pytest.approx(1.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_purvis():
    """Purvis: not clinched; p3=1/2, p4=3/8, p_playoffs=7/8."""  # NOSONAR
    o = _ODDS["Purvis"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(0.5)
    assert o.p4 == pytest.approx(0.375)
    assert o.p_playoffs == pytest.approx(0.875)


def test_odds_northeast_jones():
    """Northeast Jones: not clinched; p4=3/8, p_playoffs=3/8 (never seeds 1-3)."""
    o = _ODDS["Northeast Jones"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.375)
    assert o.p_playoffs == pytest.approx(0.375)


def test_odds_east_central():
    """East Central: not clinched; p3=1/8, p4=1/8, p_playoffs=1/4."""
    o = _ODDS["East Central"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(0.125)
    assert o.p4 == pytest.approx(0.125)
    assert o.p_playoffs == pytest.approx(0.25)


def test_odds_vancleave():
    """Vancleave: not clinched; p3=3/8, p4=1/8, p_playoffs=1/2."""  # NOSONAR
    o = _ODDS["Vancleave"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p3 == pytest.approx(0.375)
    assert o.p4 == pytest.approx(0.125)
    assert o.p_playoffs == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_stone():
    """Stone renders as simple clinched #1 string."""
    assert render_team_scenarios("Stone", _ATOMS, odds=_ODDS) == STONE_EXPECTED


def test_render_wayne_county():
    """Wayne County renders as simple clinched #2 string."""
    assert render_team_scenarios("Wayne County", _ATOMS, odds=_ODDS) == WAYNE_COUNTY_EXPECTED


def test_render_east_central():
    """East Central renders with #3, #4, and unconditional elimination sections."""
    assert render_team_scenarios("East Central", _ATOMS, odds=_ODDS) == EAST_CENTRAL_EXPECTED


def test_render_northeast_jones():
    """Northeast Jones renders with two-atom #4 and unconditional elimination sections."""
    assert render_team_scenarios("Northeast Jones", _ATOMS, odds=_ODDS) == NORTHEAST_JONES_EXPECTED


def test_render_purvis():
    """Purvis renders with #3 (simple), #4 (two atoms), and explicit elimination sections."""
    assert render_team_scenarios("Purvis", _ATOMS, odds=_ODDS) == PURVIS_EXPECTED


def test_render_vancleave():
    """Vancleave renders with #3 (two atoms), #4, and elimination sections."""
    assert render_team_scenarios("Vancleave", _ATOMS, odds=_ODDS) == VANCLEAVE_EXPECTED
