"""Scenario output tests for Region 4-4A (2025 season, pre-final-week).

Region 4-4A has two structurally independent sub-decisions:
  1. Greenwood/Louisville determines seeds 1–3.  When Greenwood wins, Louisville,
     Kosciusko, and Greenwood all finish 3-1 in a 3-way H2H cycle.  Kosciusko
     always wins the H2H PD step (fixed at +7 regardless of margin).  Louisville
     vs Greenwood is then resolved by H2H PD with threshold 9 on the
     Greenwood/Louisville margin: Greenwood wins by ≤8 → Kosciusko #1, Louisville
     #2, Greenwood #3; Greenwood wins by ≥9 → Kosciusko #1, Greenwood #2,
     Louisville #3.
  2. Gentry/Yazoo City determines only seed #4 and elimination — entirely
     independent of the Greenwood/Louisville game.

Teams (alphabetical): Gentry, Greenwood, Kosciusko, Louisville, Yazoo City
Remaining games (cutoff 2025-10-24):
  Gentry vs Yazoo City     — Yazoo City won 32–0   (actual, scenario 1; bit 0)
  Greenwood vs Louisville  — Louisville won 37–6   (actual, scenario 1; bit 1)

Known 2025 seeds: Louisville / Kosciusko / Greenwood / Yazoo City
Eliminated: Gentry

Code paths exercised:
  - 3-way tie (Louisville/Kosciusko/Greenwood all 3-1 when Greenwood wins):
    H2H PD threshold at margin 9 on the Greenwood/Louisville game
  - Louisville has atoms for seeds 1, 2, and 3 (unique margin ranges)
  - Greenwood seed-3 has 2 atoms: Louisville wins OR Greenwood wins by 1–8
  - Gentry/Yazoo City game absent from all Louisville/Kosciusko/Greenwood atoms
    (cross-game independence verified by test)
  - 6 scenarios: 1 (non-MS actual, YC+LOU wins), 2 (non-MS, GEN+LOU wins),
    3a/3b (Greenwood wins + Yazoo City wins), 4a/4b (Greenwood wins + Gentry wins)
  - Conditions atoms lead with the Gentry/Yazoo City result because it is bit 0
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

_FIXTURE = REGION_RESULTS_2025[(4, 4)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Gentry, Greenwood, Kosciusko, Louisville, Yazoo City
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: Gentry/Yazoo City (bit 0), Greenwood/Louisville (bit 1)

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

GENTRY_EXPECTED = """\
Gentry

#4 seed if: (50.0%)
1. Gentry beats Yazoo City

Eliminated if: (50.0%)
1. Yazoo City beats Gentry"""

YAZOO_CITY_EXPECTED = """\
Yazoo City

#4 seed if: (50.0%)
1. Yazoo City beats Gentry

Eliminated if: (50.0%)
1. Gentry beats Yazoo City"""

KOSCIUSKO_EXPECTED = """\
Kosciusko

#1 seed if: (50.0%)
1. Greenwood beats Louisville

#2 seed if: (50.0%)
1. Louisville beats Greenwood"""

GREENWOOD_EXPECTED = """\
Greenwood

#2 seed if: (16.7%)
1. Greenwood beats Louisville by 9 or more

#3 seed if: (83.3%)
1. Louisville beats Greenwood
2. Greenwood beats Louisville by 1\u20138"""

LOUISVILLE_EXPECTED = """\
Louisville

#1 seed if: (50.0%)
1. Louisville beats Greenwood

#2 seed if: (33.3%)
1. Greenwood beats Louisville by 1\u20138

#3 seed if: (16.7%)
1. Greenwood beats Louisville by 9 or more"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_louisville_seed_keys():
    """Louisville can finish #1, #2, or #3 depending on the Greenwood/Louisville margin."""
    assert set(_ATOMS["Louisville"].keys()) == {1, 2, 3}


def test_atoms_kosciusko_seed_keys():
    """Kosciusko finishes #1 (Greenwood wins) or #2 (Louisville wins) — never lower."""
    assert set(_ATOMS["Kosciusko"].keys()) == {1, 2}


def test_atoms_greenwood_seed_keys():
    """Greenwood finishes #2 (wins by 9+) or #3 — never #1 or lower than #3."""
    assert set(_ATOMS["Greenwood"].keys()) == {2, 3}


def test_atoms_yazoo_city_seed_keys():
    """Yazoo City is either #4 or eliminated — never in the top three."""
    assert set(_ATOMS["Yazoo City"].keys()) == {4, 5}


def test_atoms_gentry_seed_keys():
    """Gentry is either #4 or eliminated — never in the top three."""
    assert set(_ATOMS["Gentry"].keys()) == {4, 5}


# ---------------------------------------------------------------------------
# Louisville atoms — all three seed ranges derived from a single game
# ---------------------------------------------------------------------------


def test_atoms_louisville_seed1_count():
    """Louisville seed-1 has exactly one atom."""
    assert len(_ATOMS["Louisville"][1]) == 1


def test_atoms_louisville_seed1_atom():
    """Louisville seed-1: Louisville beats Greenwood (any margin) — records give clear #1."""
    atom = _ATOMS["Louisville"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Louisville"
    assert gr.loser == "Greenwood"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_louisville_seed2_count():
    """Louisville seed-2 has exactly one atom."""
    assert len(_ATOMS["Louisville"][2]) == 1


def test_atoms_louisville_seed2_atom():
    """Louisville seed-2: Greenwood wins by 1–8 (H2H PD still favours Louisville over Greenwood)."""
    atom = _ATOMS["Louisville"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Greenwood"
    assert gr.loser == "Louisville"
    assert gr.min_margin == 1
    assert gr.max_margin == 9  # exclusive upper bound; covers margins 1–8


def test_atoms_louisville_seed3_count():
    """Louisville seed-3 has exactly one atom."""
    assert len(_ATOMS["Louisville"][3]) == 1


def test_atoms_louisville_seed3_atom():
    """Louisville seed-3: Greenwood wins by 9 or more (H2H PD tips to Greenwood)."""
    atom = _ATOMS["Louisville"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Greenwood"
    assert gr.loser == "Louisville"
    assert gr.min_margin == 9
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Kosciusko atoms — always determined by who wins the Greenwood/Louisville game
# ---------------------------------------------------------------------------


def test_atoms_kosciusko_seed1_count():
    """Kosciusko seed-1 has exactly one atom."""
    assert len(_ATOMS["Kosciusko"][1]) == 1


def test_atoms_kosciusko_seed1_atom():
    """Kosciusko seed-1: Greenwood beats Louisville (any margin — KOS always tops 3-way H2H PD)."""
    atom = _ATOMS["Kosciusko"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Greenwood"
    assert gr.loser == "Louisville"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_kosciusko_seed2_count():
    """Kosciusko seed-2 has exactly one atom."""
    assert len(_ATOMS["Kosciusko"][2]) == 1


def test_atoms_kosciusko_seed2_atom():
    """Kosciusko seed-2: Louisville beats Greenwood (any margin)."""
    atom = _ATOMS["Kosciusko"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Louisville"
    assert gr.loser == "Greenwood"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Greenwood atoms — threshold atom for seed-2; two-atom seed-3
# ---------------------------------------------------------------------------


def test_atoms_greenwood_seed2_count():
    """Greenwood seed-2 has exactly one atom."""
    assert len(_ATOMS["Greenwood"][2]) == 1


def test_atoms_greenwood_seed2_atom():
    """Greenwood seed-2: Greenwood beats Louisville by 9 or more (H2H PD tips over Louisville)."""
    atom = _ATOMS["Greenwood"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Greenwood"
    assert gr.loser == "Louisville"
    assert gr.min_margin == 9
    assert gr.max_margin is None


def test_atoms_greenwood_seed3_count():
    """Greenwood seed-3 has exactly two atoms: Louisville wins OR Greenwood wins by 1–8."""
    assert len(_ATOMS["Greenwood"][3]) == 2


def test_atoms_greenwood_seed3_first_atom():
    """Greenwood seed-3 first atom: Louisville beats Greenwood (any margin)."""
    atom = _ATOMS["Greenwood"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Louisville"
    assert gr.loser == "Greenwood"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_greenwood_seed3_second_atom():
    """Greenwood seed-3 second atom: Greenwood beats Louisville by 1–8."""
    atom = _ATOMS["Greenwood"][3][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Greenwood"
    assert gr.loser == "Louisville"
    assert gr.min_margin == 1
    assert gr.max_margin == 9  # exclusive; covers 1–8


# ---------------------------------------------------------------------------
# Yazoo City and Gentry atoms — driven only by the Gentry/Yazoo City game
# ---------------------------------------------------------------------------


def test_atoms_yazoo_city_seed4_count():
    """Yazoo City seed-4 has exactly one atom."""
    assert len(_ATOMS["Yazoo City"][4]) == 1


def test_atoms_yazoo_city_seed4_atom():
    """Yazoo City seed-4: Yazoo City beats Gentry (any margin)."""
    atom = _ATOMS["Yazoo City"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Yazoo City"
    assert gr.loser == "Gentry"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_gentry_seed4_count():
    """Gentry seed-4 has exactly one atom."""
    assert len(_ATOMS["Gentry"][4]) == 1


def test_atoms_gentry_seed4_atom():
    """Gentry seed-4: Gentry beats Yazoo City (any margin)."""
    atom = _ATOMS["Gentry"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Gentry"
    assert gr.loser == "Yazoo City"
    assert gr.min_margin == 1
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# Cross-game independence: Gentry/Yazoo City game absent from seeds 1–3
# ---------------------------------------------------------------------------


def test_atoms_gentry_yazoo_city_absent_from_top_seeds():
    """The Gentry/Yazoo City game never appears in any atom for Louisville, Kosciusko, or Greenwood."""
    gen_yc_teams = {"Gentry", "Yazoo City"}
    for team in ("Louisville", "Kosciusko", "Greenwood"):
        for seed, atoms in _ATOMS[team].items():
            for atom in atoms:
                for cond in atom:
                    if isinstance(cond, GameResult):
                        pair = {cond.winner, cond.loser}
                        assert pair != gen_yc_teams, (
                            f"{team} seed {seed} atom references the Gentry/Yazoo City game"
                        )


# ---------------------------------------------------------------------------
# Division scenarios dict
# ---------------------------------------------------------------------------


def test_div_dict_scenario_keys():
    """Division scenarios dict has exactly keys 1, 2, 3a, 3b, 4a, 4b.

    Scenarios 1 and 2 are non-MS (Louisville wins both; only #4 differs).
    Scenarios 3a/3b and 4a/4b are margin-sensitive (Greenwood wins).
    """
    assert set(_DIV_DICT.keys()) == {"1", "2", "3a", "3b", "4a", "4b"}


def test_div_dict_scenario1_title():
    """Scenario 1 (actual): Yazoo City wins AND Louisville wins (both non-MS games)."""
    assert _DIV_DICT["1"]["title"] == "Yazoo City beats Gentry AND Louisville beats Greenwood"


def test_div_dict_scenario2_title():
    """Scenario 2: Gentry wins AND Louisville wins."""
    assert _DIV_DICT["2"]["title"] == "Gentry beats Yazoo City AND Louisville beats Greenwood"


def test_div_dict_scenario3a_title():
    """Scenario 3a: Yazoo City wins + Greenwood wins by 1–8 (LOU stays #2; ascending margin order)."""
    assert _DIV_DICT["3a"]["title"] == "Yazoo City beats Gentry AND Greenwood beats Louisville by 1\u20138"


def test_div_dict_scenario3b_title():
    """Scenario 3b: Yazoo City wins + Greenwood wins by 9+ (GRE #2)."""
    assert _DIV_DICT["3b"]["title"] == "Yazoo City beats Gentry AND Greenwood beats Louisville by 9 or more"


def test_div_dict_scenario4a_title():
    """Scenario 4a: Gentry wins + Greenwood wins by 1–8 (LOU stays #2; ascending margin order)."""
    assert _DIV_DICT["4a"]["title"] == "Gentry beats Yazoo City AND Greenwood beats Louisville by 1\u20138"


def test_div_dict_scenario4b_title():
    """Scenario 4b: Gentry wins + Greenwood wins by 9+ (GRE #2)."""
    assert _DIV_DICT["4b"]["title"] == "Gentry beats Yazoo City AND Greenwood beats Louisville by 9 or more"


def test_div_dict_scenario1_seeds():
    """Scenario 1 (actual): Louisville #1, Kosciusko #2, Greenwood #3, Yazoo City #4."""
    s = _DIV_DICT["1"]
    assert s["one_seed"] == "Louisville"
    assert s["two_seed"] == "Kosciusko"
    assert s["three_seed"] == "Greenwood"
    assert s["four_seed"] == "Yazoo City"
    assert "Gentry" in s["eliminated"]


def test_div_dict_scenario2_seeds():
    """Scenario 2 (GEN wins, LOU wins): Louisville #1, Kosciusko #2, Greenwood #3, Gentry #4."""
    s = _DIV_DICT["2"]
    assert s["one_seed"] == "Louisville"
    assert s["two_seed"] == "Kosciusko"
    assert s["three_seed"] == "Greenwood"
    assert s["four_seed"] == "Gentry"
    assert "Yazoo City" in s["eliminated"]


def test_div_dict_scenario3a_seeds():
    """Scenario 3a (GRE wins by 1–8, YC wins): Kosciusko #1, Louisville #2, Greenwood #3."""
    s = _DIV_DICT["3a"]
    assert s["one_seed"] == "Kosciusko"
    assert s["two_seed"] == "Louisville"
    assert s["three_seed"] == "Greenwood"
    assert s["four_seed"] == "Yazoo City"
    assert "Gentry" in s["eliminated"]


def test_div_dict_scenario3b_seeds():
    """Scenario 3b (GRE wins by 9+, YC wins): Kosciusko #1, Greenwood #2, Louisville #3."""
    s = _DIV_DICT["3b"]
    assert s["one_seed"] == "Kosciusko"
    assert s["two_seed"] == "Greenwood"
    assert s["three_seed"] == "Louisville"
    assert s["four_seed"] == "Yazoo City"
    assert "Gentry" in s["eliminated"]


def test_div_dict_scenario4a_seeds():
    """Scenario 4a (GRE wins by 1–8, GEN wins): Kosciusko #1, Louisville #2, Greenwood #3, Gentry #4."""
    s = _DIV_DICT["4a"]
    assert s["one_seed"] == "Kosciusko"
    assert s["two_seed"] == "Louisville"
    assert s["three_seed"] == "Greenwood"
    assert s["four_seed"] == "Gentry"
    assert "Yazoo City" in s["eliminated"]


def test_div_dict_scenario4b_seeds():
    """Scenario 4b (GRE wins by 9+, GEN wins): Kosciusko #1, Greenwood #2, Louisville #3, Gentry #4."""
    s = _DIV_DICT["4b"]
    assert s["one_seed"] == "Kosciusko"
    assert s["two_seed"] == "Greenwood"
    assert s["three_seed"] == "Louisville"
    assert s["four_seed"] == "Gentry"
    assert "Yazoo City" in s["eliminated"]


def test_div_dict_kosciusko_never_lower_than_two():
    """Kosciusko is always #1 or #2 across all scenarios."""
    for key, scenario in _DIV_DICT.items():
        is_one_or_two = scenario.get("one_seed") == "Kosciusko" or scenario.get("two_seed") == "Kosciusko"
        assert is_one_or_two, f"Scenario {key}: expected Kosciusko in seed 1 or 2"


def test_div_dict_greenwood_never_lower_than_three():
    """Greenwood is always #2 or #3 across all scenarios."""
    seed_fields = ["one_seed", "two_seed", "three_seed", "four_seed"]
    for key, scenario in _DIV_DICT.items():
        gre_seed = next(
            (i + 1 for i, f in enumerate(seed_fields) if scenario.get(f) == "Greenwood"),
            None,
        )
        assert gre_seed in (2, 3), f"Scenario {key}: Greenwood is #{gre_seed}, expected #2 or #3"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict structure
# ---------------------------------------------------------------------------


def test_team_dict_louisville_keys():
    """Louisville team dict has keys 1, 2, and 3."""
    assert set(_TEAM_DICT["Louisville"].keys()) == {1, 2, 3}


def test_team_dict_kosciusko_keys():
    """Kosciusko team dict has keys 1 and 2."""
    assert set(_TEAM_DICT["Kosciusko"].keys()) == {1, 2}


def test_team_dict_greenwood_keys():
    """Greenwood team dict has keys 2 and 3."""
    assert set(_TEAM_DICT["Greenwood"].keys()) == {2, 3}


def test_team_dict_yazoo_city_keys():
    """Yazoo City team dict has keys 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Yazoo City"].keys()) == {4, "eliminated"}


def test_team_dict_gentry_keys():
    """Gentry team dict has keys 4 and 'eliminated'."""
    assert set(_TEAM_DICT["Gentry"].keys()) == {4, "eliminated"}


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_louisville_splits():
    """Louisville: p1=1/2, p2=1/3, p3=1/6; clinched (always makes playoffs)."""
    o = _ODDS["Louisville"]
    assert o.clinched is True
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.5)
    assert o.p2 == pytest.approx(1 / 3)
    assert o.p3 == pytest.approx(1 / 6)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_kosciusko_even_split():
    """Kosciusko: exactly 50/50 on #1 vs #2; clinched."""
    o = _ODDS["Kosciusko"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.5)
    assert o.p2 == pytest.approx(0.5)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_greenwood_clinched():
    """Greenwood: clinched (always makes playoffs); p2=1/6, p3=5/6."""
    o = _ODDS["Greenwood"]
    assert o.clinched is True
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(1 / 6)
    assert o.p3 == pytest.approx(5 / 6)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_yazoo_city():
    """Yazoo City: 50% chance at #4; not clinched, not eliminated."""
    o = _ODDS["Yazoo City"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.5)
    assert o.p_playoffs == pytest.approx(0.5)


def test_odds_gentry():
    """Gentry: 50% chance at #4; not clinched, not eliminated."""
    o = _ODDS["Gentry"]
    assert o.clinched is False
    assert o.eliminated is False
    assert o.p1 == pytest.approx(0.0)
    assert o.p2 == pytest.approx(0.0)
    assert o.p3 == pytest.approx(0.0)
    assert o.p4 == pytest.approx(0.5)
    assert o.p_playoffs == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


def test_render_gentry():
    """Gentry renders with #4 seed and elimination sections."""
    assert render_team_scenarios("Gentry", _ATOMS, odds=_ODDS) == GENTRY_EXPECTED


def test_render_yazoo_city():
    """Yazoo City renders with #4 seed and elimination sections."""
    assert render_team_scenarios("Yazoo City", _ATOMS, odds=_ODDS) == YAZOO_CITY_EXPECTED


def test_render_kosciusko():
    """Kosciusko renders as simple #1-or-#2 scenario."""
    assert render_team_scenarios("Kosciusko", _ATOMS, odds=_ODDS) == KOSCIUSKO_EXPECTED


def test_render_greenwood():
    """Greenwood renders with threshold-sensitive #2 and two-atom #3 sections."""
    assert render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS) == GREENWOOD_EXPECTED


def test_render_louisville():
    """Louisville renders all three possible seed positions with distinct margin conditions."""
    assert render_team_scenarios("Louisville", _ATOMS, odds=_ODDS) == LOUISVILLE_EXPECTED
