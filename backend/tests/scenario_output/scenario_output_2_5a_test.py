"""Scenario output tests for Region 2-5A (2025 season, pre-final-week).

Region 2-5A is a 6-team region with a margin-sensitive Lanier/Vicksburg game.
Three remaining games determine the final standings:
  - Cleveland Central vs Provine   (bit 0 — CC almost certainly wins, irrelevant to some seedings)
  - Florence vs Holmes County Central  (bit 1 — FLO=a, HCC=b; bit=0 → HCC wins)
  - Lanier vs Vicksburg            (bit 2 — margin-sensitive; determines #2/#3 ordering)

Actual results (2025-11-06):
  Cleveland Central beat Provine   (bit 0=1 → CC wins)
  Holmes County Central beat Florence  (bit 1=0 → HCC wins)
  Lanier beat Vicksburg            (bit 2=1 → Lanier wins)
  → mask = 1 + 0 + 4 = 5 → scenario "5"

Teams (alphabetical):
  Cleveland Central, Florence, Holmes County Central, Lanier, Provine, Vicksburg

Known 2025 seeds: Cleveland Central #1 / Lanier #2 / Holmes County Central #3 / Vicksburg #4
Eliminated: Florence, Provine

Code paths exercised:
  - Provine is always eliminated (seed 5: [[]])
  - Cleveland Central and Lanier both clinched playoffs
  - Margin sensitivity in Lanier/Vicksburg game; two different thresholds:
      When Provine beats CC:  VB wins by 1–9  → Lanier #2; by 10+  → VB #2
      When CC beats Provine:  VB wins by 1–8  → Lanier #2; by  9+  → VB #2
  - 9 total scenarios: 4 MS sub-scenarios (1a/1b, 2a/2b) + 5 non-MS (3–7)
  - Scenarios 1a and 2a produce identical full seedings; 1b and 2b likewise
  - CC/PRO game absent from several atoms (HCC, FLO, VB seed-3/4 atoms)
  - Odds require fractional margin weights: Lanier p2 = 41/96, p3 = 31/96
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

_FIXTURE = REGION_RESULTS_2025[(5, 2)]
_CUTOFF = "2025-10-31"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Cleveland Central/Provine (bit 0), Florence/HCC (bit 1), Lanier/Vicksburg (bit 2)

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

PROVINE_EXPECTED = "Provine\n\nEliminated. (100.0%)"

CLEVELAND_CENTRAL_EXPECTED = """\
Cleveland Central

#1 seed if: (75.0%)
1. Vicksburg beats Lanier
2. Cleveland Central beats Provine AND Lanier beats Vicksburg

#2 seed if: (12.5%)
1. Provine beats Cleveland Central AND Holmes County Central beats Florence AND Lanier beats Vicksburg

#3 seed if: (12.5%)
1. Provine beats Cleveland Central AND Florence beats Holmes County Central AND Lanier beats Vicksburg"""

FLORENCE_EXPECTED = """\
Florence

#2 seed if: (12.5%)
1. Provine beats Cleveland Central AND Florence beats Holmes County Central AND Lanier beats Vicksburg

#3 seed if: (12.5%)
1. Cleveland Central beats Provine AND Florence beats Holmes County Central AND Lanier beats Vicksburg

#4 seed if: (25.0%)
1. Florence beats Holmes County Central AND Vicksburg beats Lanier

Eliminated if: (50.0%)
1. Holmes County Central beats Florence"""

HCC_EXPECTED = """\
Holmes County Central

#3 seed if: (25.0%)
1. Holmes County Central beats Florence AND Lanier beats Vicksburg

#4 seed if: (50.0%)
1. Florence beats Holmes County Central AND Lanier beats Vicksburg
2. Holmes County Central beats Florence AND Vicksburg beats Lanier

Eliminated if: (25.0%)
1. Florence beats Holmes County Central AND Vicksburg beats Lanier"""

LANIER_EXPECTED = """\
Lanier

#1 seed if: (25.0%)
1. Provine beats Cleveland Central AND Lanier beats Vicksburg

#2 seed if: (41.7%)
1. Cleveland Central beats Provine AND Lanier beats Vicksburg
2. Holmes County Central beats Florence AND Vicksburg beats Lanier by 1\u20138

#3 seed if: (33.3%)
1. Vicksburg beats Lanier by 9 or more
2. Florence beats Holmes County Central AND Vicksburg beats Lanier"""

VICKSBURG_EXPECTED = """\
Vicksburg

#2 seed if: (33.3%)
1. Vicksburg beats Lanier by 9 or more
2. Florence beats Holmes County Central AND Vicksburg beats Lanier

#3 seed if: (16.7%)
1. Holmes County Central beats Florence AND Vicksburg beats Lanier by 1\u20138

#4 seed if: (25.0%)
1. Holmes County Central beats Florence AND Lanier beats Vicksburg

Eliminated if: (25.0%)
1. Florence beats Holmes County Central AND Lanier beats Vicksburg"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_provine_seed_keys():
    """Provine is always eliminated — only seed 5."""
    assert set(_ATOMS["Provine"].keys()) == {5}


def test_atoms_cleveland_central_seed_keys():
    """Cleveland Central finishes #1, #2, or #3 — always makes playoffs."""
    assert set(_ATOMS["Cleveland Central"].keys()) == {1, 2, 3}


def test_atoms_florence_seed_keys():
    """Florence can finish #2, #3, #4, or be eliminated."""
    assert set(_ATOMS["Florence"].keys()) == {2, 3, 4, 5}


def test_atoms_hcc_seed_keys():
    """Holmes County Central can finish #3, #4, or be eliminated."""
    assert set(_ATOMS["Holmes County Central"].keys()) == {3, 4, 5}


def test_atoms_lanier_seed_keys():
    """Lanier finishes #1, #2, or #3 — always makes playoffs."""
    assert set(_ATOMS["Lanier"].keys()) == {1, 2, 3}


def test_atoms_vicksburg_seed_keys():
    """Vicksburg can finish #2, #3, #4, or be eliminated."""
    assert set(_ATOMS["Vicksburg"].keys()) == {2, 3, 4, 5}


def test_atoms_provine_unconditional():
    """Provine is always eliminated — atom is [[]]."""
    assert _ATOMS["Provine"][5] == [[]]


# ---------------------------------------------------------------------------
# Cleveland Central atoms
# ---------------------------------------------------------------------------


def test_atoms_cc_seed1_count():
    """CC seed-1 has exactly two atoms."""
    assert len(_ATOMS["Cleveland Central"][1]) == 2


def test_atoms_cc_seed1_atom0():
    """CC seed-1 atom 0: Vicksburg beats Lanier (any margin). CC/PRO game absent."""
    atom = _ATOMS["Cleveland Central"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Vicksburg"
    assert gr.loser == "Lanier"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_cc_seed1_atom0_cc_pro_absent():
    """CC/PRO game is absent from CC seed-1 atom 0 — VB winning is sufficient."""
    atom = _ATOMS["Cleveland Central"][1][0]
    pairs = {(gr.winner, gr.loser) for gr in atom if isinstance(gr, GameResult)}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_cc_seed1_atom1():
    """CC seed-1 atom 1: CC beats Provine AND Lanier beats Vicksburg."""
    atom = _ATOMS["Cleveland Central"][1][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Cleveland Central" in winners
    assert "Lanier" in winners


def test_atoms_cc_seed2_count():
    """CC seed-2 has exactly one atom."""
    assert len(_ATOMS["Cleveland Central"][2]) == 1


def test_atoms_cc_seed2_atom():
    """CC seed-2: Provine beats CC AND HCC beats FLO AND Lanier beats VB."""
    atom = _ATOMS["Cleveland Central"][2][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Provine" in winners
    assert "Holmes County Central" in winners
    assert "Lanier" in winners


def test_atoms_cc_seed3_count():
    """CC seed-3 has exactly one atom."""
    assert len(_ATOMS["Cleveland Central"][3]) == 1


def test_atoms_cc_seed3_atom():
    """CC seed-3: Provine beats CC AND Florence beats HCC AND Lanier beats VB."""
    atom = _ATOMS["Cleveland Central"][3][0]
    assert len(atom) == 3
    winners = {gr.winner for gr in atom}
    assert "Provine" in winners
    assert "Florence" in winners
    assert "Lanier" in winners


# ---------------------------------------------------------------------------
# Florence atoms
# ---------------------------------------------------------------------------


def test_atoms_florence_seed2_count():
    """Florence seed-2 has exactly one atom."""
    assert len(_ATOMS["Florence"][2]) == 1


def test_atoms_florence_seed2_atom():
    """Florence seed-2: Provine beats CC AND FLO beats HCC AND Lanier beats VB."""
    atom = _ATOMS["Florence"][2][0]
    winners = {gr.winner for gr in atom}
    assert "Provine" in winners
    assert "Florence" in winners
    assert "Lanier" in winners


def test_atoms_florence_seed4_count():
    """Florence seed-4 has exactly one atom."""
    assert len(_ATOMS["Florence"][4]) == 1


def test_atoms_florence_seed4_atom():
    """Florence seed-4: Florence beats HCC AND Vicksburg beats Lanier. CC/PRO absent."""
    atom = _ATOMS["Florence"][4][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Florence" in winners
    assert "Vicksburg" in winners


def test_atoms_florence_seed4_cc_pro_absent():
    """CC/PRO game absent from Florence seed-4 atom."""
    atom = _ATOMS["Florence"][4][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_florence_eliminated_count():
    """Florence eliminated (seed-5) has exactly one atom."""
    assert len(_ATOMS["Florence"][5]) == 1


def test_atoms_florence_eliminated_atom():
    """Florence is eliminated whenever HCC beats Florence (any margin)."""
    atom = _ATOMS["Florence"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Holmes County Central"
    assert gr.loser == "Florence"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Holmes County Central atoms
# ---------------------------------------------------------------------------


def test_atoms_hcc_seed3_count():
    """HCC seed-3 has exactly one atom."""
    assert len(_ATOMS["Holmes County Central"][3]) == 1


def test_atoms_hcc_seed3_atom():
    """HCC seed-3: HCC beats FLO AND Lanier beats VB. CC/PRO game absent."""
    atom = _ATOMS["Holmes County Central"][3][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Holmes County Central" in winners
    assert "Lanier" in winners


def test_atoms_hcc_seed3_cc_pro_absent():
    """CC/PRO game absent from HCC seed-3 atom."""
    atom = _ATOMS["Holmes County Central"][3][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_hcc_seed4_count():
    """HCC seed-4 has exactly two atoms."""
    assert len(_ATOMS["Holmes County Central"][4]) == 2


def test_atoms_hcc_seed4_atom0():
    """HCC seed-4 atom 0: Florence beats HCC AND Lanier beats VB. CC/PRO absent."""
    atom = _ATOMS["Holmes County Central"][4][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Florence" in winners
    assert "Lanier" in winners


def test_atoms_hcc_seed4_atom1():
    """HCC seed-4 atom 1: HCC beats FLO AND Vicksburg beats Lanier. CC/PRO absent."""
    atom = _ATOMS["Holmes County Central"][4][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Holmes County Central" in winners
    assert "Vicksburg" in winners


def test_atoms_hcc_eliminated_atom():
    """HCC is eliminated only when Florence beats HCC AND Vicksburg beats Lanier."""
    atom = _ATOMS["Holmes County Central"][5][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Florence" in winners
    assert "Vicksburg" in winners


# ---------------------------------------------------------------------------
# Lanier atoms — margin-sensitive
# ---------------------------------------------------------------------------


def test_atoms_lanier_seed1_count():
    """Lanier seed-1 has exactly one atom."""
    assert len(_ATOMS["Lanier"][1]) == 1


def test_atoms_lanier_seed1_atom():
    """Lanier seed-1: Provine beats CC AND Lanier beats VB. FLO/HCC absent."""
    atom = _ATOMS["Lanier"][1][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Provine" in winners
    assert "Lanier" in winners


def test_atoms_lanier_seed1_flo_hcc_absent():
    """Florence/HCC game is absent from Lanier seed-1 atom."""
    atom = _ATOMS["Lanier"][1][0]
    pairs = {(gr.winner, gr.loser) for gr in atom if isinstance(gr, GameResult)}
    assert ("Florence", "Holmes County Central") not in pairs
    assert ("Holmes County Central", "Florence") not in pairs


def test_atoms_lanier_seed2_count():
    """Lanier seed-2 has exactly two atoms."""
    assert len(_ATOMS["Lanier"][2]) == 2


def test_atoms_lanier_seed2_atom0():
    """Lanier seed-2 atom 0: CC beats Provine AND Lanier beats VB (any margin)."""
    atom = _ATOMS["Lanier"][2][0]
    assert len(atom) == 2
    gr_cc = next(g for g in atom if isinstance(g, GameResult) and g.winner == "Cleveland Central")
    gr_lai = next(g for g in atom if isinstance(g, GameResult) and g.winner == "Lanier")
    assert gr_cc.loser == "Provine"
    assert gr_lai.loser == "Vicksburg"
    assert gr_lai.max_margin is None


def test_atoms_lanier_seed2_atom1_margin():
    """Lanier seed-2 atom 1: HCC beats FLO AND VB beats Lanier by 1–8 (max_margin=9); CC/PRO absent."""
    atom = _ATOMS["Lanier"][2][1]
    gr_vb = next(g for g in atom if isinstance(g, GameResult) and g.winner == "Vicksburg")
    assert gr_vb.loser == "Lanier"
    assert gr_vb.min_margin == 1
    assert gr_vb.max_margin == 9
    # CC/Provine game is absent — irrelevant when VB wins by 1–8
    pairs = {(g.winner, g.loser) for g in atom if isinstance(g, GameResult)}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_lanier_seed3_count():
    """Lanier seed-3 has exactly two atoms."""
    assert len(_ATOMS["Lanier"][3]) == 2


def test_atoms_lanier_seed3_atom0():
    """Lanier seed-3 atom 0: Vicksburg beats Lanier by 9 or more (min_margin=9)."""
    atom = _ATOMS["Lanier"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Vicksburg"
    assert gr.loser == "Lanier"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_lanier_seed3_atom1_margin():
    """Lanier seed-3 atom 1: Florence beats HCC AND Vicksburg beats Lanier (any margin)."""
    atom = _ATOMS["Lanier"][3][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom if isinstance(gr, GameResult)}
    assert "Florence" in winners
    assert "Vicksburg" in winners


# ---------------------------------------------------------------------------
# Vicksburg atoms — mirror of Lanier in the margin-sensitive game
# ---------------------------------------------------------------------------


def test_atoms_vicksburg_seed2_count():
    """Vicksburg seed-2 has exactly two atoms (mirrors Lanier seed-3)."""
    assert len(_ATOMS["Vicksburg"][2]) == 2


def test_atoms_vicksburg_seed2_atom0():
    """Vicksburg seed-2 atom 0: Vicksburg beats Lanier by 9 or more (min_margin=9)."""
    atom = _ATOMS["Vicksburg"][2][0]
    assert len(atom) == 1
    gr_vb = next(g for g in atom if isinstance(g, GameResult) and g.winner == "Vicksburg")
    assert gr_vb.loser == "Lanier"
    assert gr_vb.min_margin == 9
    assert gr_vb.max_margin is None


def test_atoms_vicksburg_seed2_atom1_margin():
    """Vicksburg seed-2 atom 1: Florence beats HCC AND Vicksburg beats Lanier (any margin)."""
    atom = _ATOMS["Vicksburg"][2][1]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom if isinstance(gr, GameResult)}
    assert "Florence" in winners
    assert "Vicksburg" in winners


def test_atoms_vicksburg_seed3_count():
    """Vicksburg seed-3 has exactly one atom (mirrors Lanier seed-2 atom 1)."""
    assert len(_ATOMS["Vicksburg"][3]) == 1


def test_atoms_vicksburg_seed3_atom0_margin():
    """Vicksburg seed-3 atom 0: HCC beats FLO AND VB beats Lanier by 1–8; CC/PRO absent."""
    atom = _ATOMS["Vicksburg"][3][0]
    gr_vb = next(g for g in atom if isinstance(g, GameResult) and g.winner == "Vicksburg")
    assert gr_vb.min_margin == 1
    assert gr_vb.max_margin == 9
    # CC/Provine game is absent — irrelevant when VB wins by 1–8
    pairs = {(g.winner, g.loser) for g in atom if isinstance(g, GameResult)}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_vicksburg_seed4_atom():
    """Vicksburg seed-4: HCC beats FLO AND Lanier beats VB. CC/PRO absent."""
    atom = _ATOMS["Vicksburg"][4][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Holmes County Central" in winners
    assert "Lanier" in winners


def test_atoms_vicksburg_seed4_cc_pro_absent():
    """CC/PRO game absent from Vicksburg seed-4 atom."""
    atom = _ATOMS["Vicksburg"][4][0]
    pairs = {(gr.winner, gr.loser) for gr in atom}
    assert ("Cleveland Central", "Provine") not in pairs
    assert ("Provine", "Cleveland Central") not in pairs


def test_atoms_vicksburg_eliminated_atom():
    """Vicksburg is eliminated when Florence beats HCC AND Lanier beats VB."""
    atom = _ATOMS["Vicksburg"][5][0]
    assert len(atom) == 2
    winners = {gr.winner for gr in atom}
    assert "Florence" in winners
    assert "Lanier" in winners


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly 7 keys: 1a, 1b, 2, 3, 4, 5, 6.

    With the corrected tiebreaker (restart H2H after sub-group split), the old
    '2b' scenario (CC beats Provine AND HCC beats FLO AND VB by 9+) is now merged
    into '1b' (HCC beats FLO AND VB by 9+, CC/PRO irrelevant) because the CC/PRO
    result no longer affects seeding when VB beats LAN by 9+.
    """
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2", "3", "4", "5", "6"}


def test_div_dict_scenario1a_title():
    """Scenario 1a: HCC beats FLO AND VB beats Lanier by 1–8 (CC/PRO irrelevant)."""
    assert _DIV_DICT["1a"]["title"] == (
        "Holmes County Central beats Florence AND Vicksburg beats Lanier by 1\u20138"
    )


def test_div_dict_scenario1b_title():
    """Scenario 1b: HCC beats FLO AND VB beats Lanier by 9 or more (CC/PRO irrelevant)."""
    assert _DIV_DICT["1b"]["title"] == (
        "Holmes County Central beats Florence AND Vicksburg beats Lanier by 9 or more"
    )


def test_div_dict_scenario2_title():
    """Scenario 2: Florence beats HCC AND Vicksburg beats Lanier (CC/PRO irrelevant)."""
    assert _DIV_DICT["2"]["title"] == "Florence beats Holmes County Central AND Vicksburg beats Lanier"


def test_div_dict_scenario3_seeds():
    """Scenario 3: Lanier #1, CC #2, HCC #3, VB #4."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Lanier"
    assert s["two_seed"] == "Cleveland Central"
    assert s["three_seed"] == "Holmes County Central"
    assert s["four_seed"] == "Vicksburg"


def test_div_dict_scenario4_seeds():
    """Scenario 4 (actual result): CC #1, Lanier #2, HCC #3, VB #4."""
    s = _DIV_DICT["4"]
    assert s["one_seed"] == "Cleveland Central"
    assert s["two_seed"] == "Lanier"
    assert s["three_seed"] == "Holmes County Central"
    assert s["four_seed"] == "Vicksburg"


def test_div_dict_scenario5_seeds():
    """Scenario 5: Lanier #1, Florence #2, CC #3, HCC #4."""
    s = _DIV_DICT["5"]
    assert s["one_seed"] == "Lanier"
    assert s["two_seed"] == "Florence"
    assert s["three_seed"] == "Cleveland Central"
    assert s["four_seed"] == "Holmes County Central"


def test_div_dict_scenario6_seeds():
    """Scenario 6: CC #1, Lanier #2, Florence #3, HCC #4."""
    s = _DIV_DICT["6"]
    assert s["one_seed"] == "Cleveland Central"
    assert s["two_seed"] == "Lanier"
    assert s["three_seed"] == "Florence"
    assert s["four_seed"] == "Holmes County Central"


def test_div_dict_provine_always_eliminated():
    """Provine is eliminated in every scenario."""
    for key, scenario in _DIV_DICT.items():
        assert "Provine" in scenario["eliminated"], f"Scenario {key}: Provine should be eliminated"


def test_div_dict_cc_never_four():
    """Cleveland Central is never the #4 seed."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["four_seed"] != "Cleveland Central", f"Scenario {key}: CC should not be #4"


def test_div_dict_lanier_never_four():
    """Lanier is never the #4 seed."""
    for key, scenario in _DIV_DICT.items():
        assert scenario["four_seed"] != "Lanier", f"Scenario {key}: Lanier should not be #4"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_provine_key():
    """Provine team dict uses 'eliminated' key only."""
    assert set(_TEAM_DICT["Provine"].keys()) == {"eliminated"}


def test_team_dict_cc_keys():
    """Cleveland Central team dict has keys 1, 2, 3 only."""
    assert set(_TEAM_DICT["Cleveland Central"].keys()) == {1, 2, 3}


def test_team_dict_lanier_keys():
    """Lanier team dict has keys 1, 2, 3 only (never #4 with correct tiebreaker)."""
    assert set(_TEAM_DICT["Lanier"].keys()) == {1, 2, 3}


def test_team_dict_florence_keys():
    """Florence team dict has keys 2, 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Florence"].keys()) == {2, 3, 4, "eliminated"}


def test_team_dict_hcc_keys():
    """HCC team dict has keys 3, 4, and 'eliminated'."""
    assert set(_TEAM_DICT["Holmes County Central"].keys()) == {3, 4, "eliminated"}


def test_team_dict_vicksburg_keys():
    """Vicksburg team dict has keys 2, 3, 4, and 'eliminated' (never #1 with correct tiebreaker)."""
    assert set(_TEAM_DICT["Vicksburg"].keys()) == {2, 3, 4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_provine_eliminated():
    """Provine is eliminated with zero playoff odds."""
    o = _ODDS["Provine"]
    assert o.eliminated is True
    assert o.p_playoffs == pytest.approx(0.0)


def test_odds_cleveland_central():
    """Cleveland Central has clinched with p1=3/4, p2=p3=1/8."""
    o = _ODDS["Cleveland Central"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(3 / 4)
    assert o.p2 == pytest.approx(1 / 8)
    assert o.p3 == pytest.approx(1 / 8)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_lanier():
    """Lanier has clinched with p1=1/4, p2=5/12, p3=1/3.

    The margin boundary shifted from VB-by-9 giving Lanier #2 (old, buggy) to
    VB-by-9 giving Vicksburg #2 (new, correct — VB beat LAN, so H2H restart
    at Step 1 resolves the sub-group in VB's favour).
    """
    o = _ODDS["Lanier"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(1 / 4)
    assert o.p2 == pytest.approx(5 / 12)
    assert o.p3 == pytest.approx(1 / 3)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_florence():
    """Florence: p2=p3=1/8, p4=1/4, p_playoffs=1/2."""
    o = _ODDS["Florence"]
    assert o.clinched is False
    assert o.p2 == pytest.approx(1 / 8)
    assert o.p3 == pytest.approx(1 / 8)
    assert o.p4 == pytest.approx(1 / 4)
    assert o.p_playoffs == pytest.approx(1 / 2)


def test_odds_hcc():
    """Holmes County Central: p3=1/4, p4=1/2, p_playoffs=3/4."""
    o = _ODDS["Holmes County Central"]
    assert o.clinched is False
    assert o.p3 == pytest.approx(1 / 4)
    assert o.p4 == pytest.approx(1 / 2)
    assert o.p_playoffs == pytest.approx(3 / 4)


def test_odds_vicksburg():
    """Vicksburg: p2=1/3, p3=1/6, p4=1/4, p_playoffs=3/4."""
    o = _ODDS["Vicksburg"]
    assert o.clinched is False
    assert o.p2 == pytest.approx(1 / 3)
    assert o.p3 == pytest.approx(1 / 6)
    assert o.p4 == pytest.approx(1 / 4)
    assert o.p_playoffs == pytest.approx(3 / 4)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_provine():
    """Provine renders as simple eliminated string."""
    assert render_team_scenarios("Provine", _ATOMS, odds=_ODDS) == PROVINE_EXPECTED


def test_render_cleveland_central():
    """Cleveland Central renders correctly with 2-atom seed-1 structure."""
    assert render_team_scenarios("Cleveland Central", _ATOMS, odds=_ODDS) == CLEVELAND_CENTRAL_EXPECTED


def test_render_florence():
    """Florence renders with 3 playoff seeds and an eliminated section."""
    assert render_team_scenarios("Florence", _ATOMS, odds=_ODDS) == FLORENCE_EXPECTED


def test_render_hcc():
    """Holmes County Central renders with seed-3/4/eliminated structure."""
    assert render_team_scenarios("Holmes County Central", _ATOMS, odds=_ODDS) == HCC_EXPECTED


def test_render_lanier():
    """Lanier renders with margin-sensitive seed-2 and seed-3 sections."""
    assert render_team_scenarios("Lanier", _ATOMS, odds=_ODDS) == LANIER_EXPECTED


def test_render_vicksburg():
    """Vicksburg renders with margin-sensitive seed-2 and seed-3 sections."""
    assert render_team_scenarios("Vicksburg", _ATOMS, odds=_ODDS) == VICKSBURG_EXPECTED
