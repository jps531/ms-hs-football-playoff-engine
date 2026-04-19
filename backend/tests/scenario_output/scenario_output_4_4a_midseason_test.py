"""Scenario output tests for Region 4-4A (2025 season, two weeks remaining).

Cutoff: 2025-10-17 (three of five weeks of region play completed).

Completed games (6):
  2025-10-03  Kosciusko 45 - Gentry 8
  2025-10-03  Louisville 42 - Yazoo City 8
  2025-10-10  Greenwood 15 - Yazoo City 6
  2025-10-10  Louisville 29 - Kosciusko 24
  2025-10-17  Kosciusko 28 - Greenwood 7
  2025-10-17  Louisville 44 - Gentry 6

Standings at cutoff:
  Louisville:  3-0  (only team with a decided record)
  Kosciusko:   2-1
  Greenwood:   1-1  (2 of 4 games played)
  Yazoo City:  0-2  (2 of 4 games played)
  Gentry:      0-2  (2 of 4 games played)

Remaining games (4 — two weeks of play):
  bit 0: Gentry vs Greenwood    (Greenwood won 32-10,  2025-10-24)
  bit 1: Kosciusko vs Yazoo City (Kosciusko won 46-0,  2025-10-24)
  bit 2: Gentry vs Yazoo City   (Yazoo City won 32-0,  2025-10-30)
  bit 3: Greenwood vs Louisville (Louisville won 37-6,  2025-10-31)

Known 2025 seeds: Louisville #1 / Kosciusko #2 / Greenwood #3 / Yazoo City #4
Eliminated: Gentry

Contrast with ``scenario_output_4_4a_test.py`` (one week remaining):
  - 4 remaining games here vs 2 there → 16 masks vs 4 masks
  - Louisville leads 3-0 rather than being tied at 3-1
  - All five outcomes are achievable for Greenwood (seeds 1-4 AND eliminated)
  - 21 distinct division scenarios (vs 6 in the one-week-out test)

Coverage this test specifically exercises that the one-week-out test does not:
  - ``sometimes_elim_only_masks`` branch in ``build_scenario_atoms`` (lines 847-854):
    Greenwood is eliminated in some masks (5th place) but not all → the algorithm
    generates constrained elimination atoms with explicit margin conditions.
  - Larger scenario space (16 masks, complex multi-game atoms with 3-4 conditions).
  - Louisville clinched from 3-0 start (no longer requires opponents' help).
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
_CUTOFF = "2025-10-17"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Gentry, Greenwood, Kosciusko, Louisville, Yazoo City
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# bit 0: Gentry/Greenwood, bit 1: Kosciusko/Yazoo City, bit 2: Gentry/Yazoo City, bit 3: Greenwood/Louisville

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)


# ---------------------------------------------------------------------------
# Remaining game structure
# ---------------------------------------------------------------------------


def test_remaining_game_count():
    """Four games remain across two weeks."""
    assert len(_REMAINING) == 4


def test_remaining_game_pairs():
    """Remaining game pairs in bit order."""
    assert _REMAINING[0] == RemainingGame("Gentry", "Greenwood")
    assert _REMAINING[1] == RemainingGame("Kosciusko", "Yazoo City")
    assert _REMAINING[2] == RemainingGame("Gentry", "Yazoo City")
    assert _REMAINING[3] == RemainingGame("Greenwood", "Louisville")


def test_scenario_denominator():
    """Denominator is 2^4 = 16 (four remaining games, equal win probabilities)."""
    assert _SR.denom == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """build_scenario_atoms returns an entry for every team in the region."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_louisville_seed_keys():
    """Louisville can finish #1, #2, or #3 — never lower with a 3-0 lead."""
    assert set(_ATOMS["Louisville"].keys()) == {1, 2, 3}


def test_atoms_kosciusko_seed_keys():
    """Kosciusko can finish anywhere #1-#4 depending on remaining results."""
    assert set(_ATOMS["Kosciusko"].keys()) == {1, 2, 3, 4}


def test_atoms_greenwood_seed_keys():
    """Greenwood can finish #1-#4 OR be eliminated (5th)."""
    assert set(_ATOMS["Greenwood"].keys()) == {1, 2, 3, 4, 5}


def test_atoms_yazoo_city_seed_keys():
    """Yazoo City can finish #2-#4 or be eliminated."""
    assert set(_ATOMS["Yazoo City"].keys()) == {2, 3, 4, 5}


def test_atoms_gentry_seed_keys():
    """Gentry can finish #3 or #4 or be eliminated."""
    assert set(_ATOMS["Gentry"].keys()) == {3, 4, 5}


# ---------------------------------------------------------------------------
# sometimes_elim_only_masks: Greenwood and Yazoo City have constrained
# elimination atoms (exercises lines 847-854 of scenario_viewer.py)
# ---------------------------------------------------------------------------


def test_greenwood_has_elimination_atoms():
    """Greenwood is sometimes eliminated — eliminated key present in atoms."""
    assert 5 in _ATOMS["Greenwood"]


def test_greenwood_eliminated_atoms_are_constrained():
    """Greenwood's elimination atoms have explicit conditions (not unconditional).

    This verifies the ``sometimes_elim_only_masks`` branch — Greenwood is
    eliminated in some margin outcomes but not all, so conditions must describe
    the specific margin combinations where it falls to 5th.
    """
    elim_atoms = _ATOMS["Greenwood"][5]
    assert len(elim_atoms) > 0
    for atom in elim_atoms:
        # Every elimination atom must have at least one condition
        assert len(atom) > 0, "Expected conditional elimination atom, got unconditional"


def test_yazoo_city_has_elimination_atoms():
    """Yazoo City is sometimes eliminated."""
    assert 5 in _ATOMS["Yazoo City"]


# ---------------------------------------------------------------------------
# Louisville atoms — two clean seed positions to pin exactly
# ---------------------------------------------------------------------------


def test_atoms_louisville_seed2_count():
    """Louisville seed-2 has exactly two atoms."""
    assert len(_ATOMS["Louisville"][2]) == 2


def test_atoms_louisville_seed2_atom0():
    """Louisville seed-2 atom 0: Greenwood beats Louisville by 1–8 AND Greenwood beats Gentry (KOS/YZ absent)."""
    atom = _ATOMS["Louisville"][2][0]
    gr_lou = next((c for c in atom if isinstance(c, GameResult) and c.loser == "Louisville"), None)
    assert gr_lou is not None
    assert gr_lou.winner == "Greenwood"
    assert gr_lou.min_margin == 1
    assert gr_lou.max_margin == 9  # exclusive upper bound; covers 1-8
    # KOS/YZ game is absent — irrelevant when GRE beats LOU by 1–8
    winners = {c.winner for c in atom if isinstance(c, GameResult)}
    assert "Yazoo City" not in winners
    assert "Kosciusko" not in winners


def test_atoms_louisville_seed2_atom1():
    """Louisville seed-2 atom 1: Yazoo City beats Kosciusko AND Greenwood beats Louisville by 9 or more AND Greenwood beats Gentry."""
    atom = _ATOMS["Louisville"][2][1]
    gr_lou = next((c for c in atom if isinstance(c, GameResult) and c.loser == "Louisville"), None)
    assert gr_lou is not None
    assert gr_lou.winner == "Greenwood"
    assert gr_lou.min_margin == 9
    assert gr_lou.max_margin is None
    winners = {c.winner for c in atom if isinstance(c, GameResult)}
    assert "Yazoo City" in winners


def test_atoms_louisville_seed3_count():
    """Louisville seed-3 has exactly one atom."""
    assert len(_ATOMS["Louisville"][3]) == 1


def test_atoms_louisville_seed3_atom():
    """Louisville seed-3: Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Greenwood beats Louisville by 9+."""
    atom = _ATOMS["Louisville"][3][0]
    gr_lou = next((c for c in atom if isinstance(c, GameResult) and c.loser == "Louisville"), None)
    assert gr_lou is not None
    assert gr_lou.winner == "Greenwood"
    assert gr_lou.min_margin == 9
    assert gr_lou.max_margin is None


# ---------------------------------------------------------------------------
# Kosciusko atoms — seed-4 is the new path vs the one-week-out test
# ---------------------------------------------------------------------------


def test_atoms_kosciusko_seed4_count():
    """Kosciusko seed-4 has exactly one atom."""
    assert len(_ATOMS["Kosciusko"][4]) == 1


def test_atoms_kosciusko_seed4_atom():
    """Kosciusko seed-4: Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville."""
    atom = _ATOMS["Kosciusko"][4][0]
    game_results = [c for c in atom if isinstance(c, GameResult)]
    assert len(game_results) == 3
    winners = {gr.winner for gr in game_results}
    assert "Yazoo City" in winners
    assert "Greenwood" in winners
    assert "Louisville" not in winners  # Louisville loses in this atom


# ---------------------------------------------------------------------------
# Division scenarios dict — structural checks only (20 scenarios total)
# ---------------------------------------------------------------------------


def test_div_dict_scenario_count():
    """There are 21 distinct division scenarios at two weeks out (scenario 3 split into two)."""
    assert len(_DIV_DICT) == 21


def test_div_dict_louisville_wins_always_seed1():
    """In every scenario where Louisville beats Greenwood, Louisville is #1."""
    for key, sc in _DIV_DICT.items():
        if "Louisville beats Greenwood" in sc["title"]:
            assert sc["one_seed"] == "Louisville", f"Scenario {key}: Louisville beat Greenwood but is not #1"


def test_div_dict_scenario3_title():
    """Scenario 3: Greenwood beats Gentry AND KOS beats YZ AND YZ beats Gentry AND LOU beats GRE."""
    assert (
        _DIV_DICT["3"]["title"]
        == "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Louisville beats Greenwood"
    )


def test_div_dict_scenario3_seeds():
    """Scenario 3 (LOU wins all): Louisville #1, Kosciusko #2."""
    s = _DIV_DICT["3"]
    assert s["one_seed"] == "Louisville"
    assert s["two_seed"] == "Kosciusko"
    assert "Gentry" in s["eliminated"]


def test_div_dict_greenwood_can_be_eliminated():
    """At least one scenario has Greenwood eliminated."""
    assert any("Greenwood" in sc.get("eliminated", []) for sc in _DIV_DICT.values())


def test_div_dict_kosciusko_never_eliminated():
    """Kosciusko is never eliminated — even worst-case (2-2) they hold H2H over Gentry."""
    for key, sc in _DIV_DICT.items():
        assert "Kosciusko" not in sc.get("eliminated", []), f"Scenario {key}: Kosciusko unexpectedly eliminated"


def test_div_dict_louisville_never_eliminated():
    """Louisville is never eliminated — always makes playoffs."""
    for key, sc in _DIV_DICT.items():
        assert "Louisville" not in sc.get("eliminated", []), f"Scenario {key}: Louisville unexpectedly eliminated"


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


def test_odds_louisville_clinched():
    """Louisville is clinched (always makes playoffs from 3-0)."""
    assert _ODDS["Louisville"].clinched is True
    assert _ODDS["Louisville"].eliminated is False


def test_odds_louisville_splits():
    """Louisville: p1=3/4, p2=5/24, p3=1/24."""
    o = _ODDS["Louisville"]
    assert o.p1 == pytest.approx(3 / 4)
    assert o.p2 == pytest.approx(5 / 24)
    assert o.p3 == pytest.approx(1 / 24)
    assert o.p4 == pytest.approx(0.0)
    assert o.p_playoffs == pytest.approx(1.0)


def test_odds_kosciusko_clinched():
    """Kosciusko is clinched despite seed uncertainty."""
    assert _ODDS["Kosciusko"].clinched is True
    assert _ODDS["Kosciusko"].eliminated is False


def test_odds_kosciusko_p4():
    """Kosciusko p4 = 1/8 (2 of 16 masks end with Kosciusko as #4)."""
    assert _ODDS["Kosciusko"].p4 == pytest.approx(1 / 8)
    assert _ODDS["Kosciusko"].p_playoffs == pytest.approx(1.0)


def test_odds_greenwood_not_clinched_not_eliminated():
    """Greenwood is neither clinched nor eliminated at this point."""
    assert _ODDS["Greenwood"].clinched is False
    assert _ODDS["Greenwood"].eliminated is False


def test_odds_greenwood_can_finish_first():
    """Greenwood has a non-zero chance at #1 seed."""
    assert _ODDS["Greenwood"].p1 == pytest.approx(1 / 8)


def test_odds_gentry_not_clinched_not_eliminated():
    """Gentry is neither clinched nor eliminated (can still reach #3)."""
    assert _ODDS["Gentry"].clinched is False
    assert _ODDS["Gentry"].eliminated is False
    assert _ODDS["Gentry"].p1 == pytest.approx(0.0)
    assert _ODDS["Gentry"].p2 == pytest.approx(0.0)


def test_odds_yazoo_city_not_clinched_not_eliminated():
    """Yazoo City is neither clinched nor eliminated."""
    assert _ODDS["Yazoo City"].clinched is False
    assert _ODDS["Yazoo City"].eliminated is False
    assert _ODDS["Yazoo City"].p1 == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Renders — per-team seeding possibilities
# ---------------------------------------------------------------------------

# Louisville


def test_render_louisville_seed_sections_present():
    """Louisville shows #1, #2, #3 but never #4 or Eliminated."""
    rendered = render_team_scenarios("Louisville", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" not in rendered
    assert "Eliminated if:" not in rendered


def test_render_louisville_seed1_pct():
    """Louisville's #1-seed section shows 75.0%."""
    rendered = render_team_scenarios("Louisville", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (75.0%)" in rendered


def test_render_louisville_seed2_section():
    """Louisville's #2-seed section shows 20.8%."""
    rendered = render_team_scenarios("Louisville", _ATOMS, odds=_ODDS)
    assert "#2 seed if: (20.8%)" in rendered


def test_render_louisville_seed3_section():
    """Louisville's #3-seed section: Greenwood beats Louisville by 9 or more (4.2%)."""
    rendered = render_team_scenarios("Louisville", _ATOMS, odds=_ODDS)
    assert "#3 seed if: (4.2%)" in rendered
    assert "Greenwood beats Louisville by 9 or more" in rendered


# Kosciusko


def test_render_kosciusko_seed_sections_present():
    """Kosciusko shows #1-#4 but never Eliminated."""
    rendered = render_team_scenarios("Kosciusko", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" not in rendered


def test_render_kosciusko_seed4_atom():
    """Kosciusko #4 atom: Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville."""
    rendered = render_team_scenarios("Kosciusko", _ATOMS, odds=_ODDS)
    assert "Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville" in rendered


def test_render_kosciusko_contains_seed4():
    """Kosciusko's render includes a #4 seed section."""
    rendered = render_team_scenarios("Kosciusko", _ATOMS, odds=_ODDS)
    assert "#4 seed if:" in rendered


# Greenwood


def test_render_greenwood_seed_sections_present():
    """Greenwood shows #1-#4 and Eliminated (all five outcomes)."""
    rendered = render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" in rendered


def test_render_greenwood_seed1_atom():
    """Greenwood's #1 seed requires all three: Greenwood beats Gentry, Yazoo City beats Kosciusko, Greenwood beats Louisville."""
    rendered = render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS)
    assert "Greenwood beats Gentry AND Yazoo City beats Kosciusko AND Greenwood beats Louisville" in rendered


def test_render_greenwood_seed1_pct():
    """Greenwood's #1-seed probability is 12.5%."""
    rendered = render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (12.5%)" in rendered


def test_render_greenwood_eliminated_pct():
    """Greenwood's elimination probability is 6.9%."""
    rendered = render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS)
    assert "Eliminated if: (6.9%)" in rendered


# Yazoo City


def test_render_yazoo_city_seed_sections_present():
    """Yazoo City shows #2-#4 and Eliminated, but never #1."""
    rendered = render_team_scenarios("Yazoo City", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" not in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" in rendered


def test_render_yazoo_city_simple_elimination_atom():
    """Yazoo City's simplest elimination path: Gentry beats Yazoo City (unconditional)."""
    rendered = render_team_scenarios("Yazoo City", _ATOMS, odds=_ODDS)
    assert "Gentry beats Yazoo City" in rendered


def test_render_yazoo_city_eliminated_pct():
    """Yazoo City's elimination probability is 53.3%."""
    rendered = render_team_scenarios("Yazoo City", _ATOMS, odds=_ODDS)
    assert "Eliminated if: (53.3%)" in rendered


# Gentry


def test_render_gentry_seed_sections_present():
    """Gentry shows #3, #4, and Eliminated — never #1 or #2."""
    rendered = render_team_scenarios("Gentry", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" not in rendered
    assert "#2 seed if:" not in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" in rendered


def test_render_gentry_seed3_simplest_atom():
    """Gentry's simplest #3 path: win both remaining games outright."""
    rendered = render_team_scenarios("Gentry", _ATOMS, odds=_ODDS)
    assert "Gentry beats Greenwood AND Gentry beats Yazoo City" in rendered


def test_render_gentry_eliminated_pct():
    """Gentry's elimination probability is 39.8%."""
    rendered = render_team_scenarios("Gentry", _ATOMS, odds=_ODDS)
    assert "Eliminated if: (39.8%)" in rendered


# ---------------------------------------------------------------------------
# Full render snapshots — exact string comparison per team
# (locks the complete human-readable output including all atom conditions)
# ---------------------------------------------------------------------------

_EXPECTED_RENDER = {
    "Gentry": (
        "Gentry\n"
        "\n"
        "#3 seed if: (27.3%)\n"
        "1. Gentry beats Greenwood AND Gentry beats Yazoo City\n"
        "2. Gentry beats Greenwood by 5 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 1 AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by 6 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 2\u20133 AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 7 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 4\u20135 AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by 8 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 6 AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by 8\u201311 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 7 AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by 9\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 8 AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by exactly 10 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 9 AND Louisville beats Greenwood\n"
        "9. Gentry beats Greenwood by exactly 11 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8\u20139 AND Louisville beats Greenwood\n"
        "10. Gentry beats Greenwood by 12 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7\u201310 AND Louisville beats Greenwood\n"
        "\n"
        "#4 seed if: (32.9%)\n"
        "1. Greenwood beats Gentry AND Gentry beats Yazoo City\n"
        "2. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by exactly 1 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20134 AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 2\u20133 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20135 AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by exactly 4 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20136 AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by exactly 5 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 2\u20136 AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by exactly 6 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 4\u20137 AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by exactly 7 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 6\u20137 AND Louisville beats Greenwood\n"
        "9. Gentry beats Greenwood by exactly 8 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 8 AND Louisville beats Greenwood\n"
        "10. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City by 1\u201311 AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood\n"
        "11. Gentry beats Greenwood by 10 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood\n"
        "\n"
        "Eliminated if: (39.8%)\n"
        "1. Greenwood beats Gentry AND Yazoo City beats Gentry\n"
        "2. Yazoo City beats Gentry AND Greenwood beats Louisville\n"
        "3. Gentry beats Greenwood by exactly 1 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 5 or more AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 2\u20133 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 6 or more AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by 4\u20135 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7 or more AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by 6\u20137 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8 or more AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by 8\u20139 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by exactly 10 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 12 or more AND Louisville beats Greenwood"
    ),
    "Greenwood": (
        "Greenwood\n"
        "\n"
        "#1 seed if: (12.5%)\n"
        "1. Greenwood beats Gentry AND Yazoo City beats Kosciusko AND Greenwood beats Louisville\n"
        "\n"
        "#2 seed if: (10.4%)\n"
        "1. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Greenwood beats Louisville by 9 or more\n"
        "2. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville\n"
        "\n"
        "#3 seed if: (39.8%)\n"
        "1. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood by 1\u20133 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry\n"
        "3. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Greenwood beats Louisville by 1\u20138\n"
        "4. Yazoo City beats Kosciusko by 1\u20136 AND Greenwood beats Gentry AND Louisville beats Greenwood\n"
        "5. Greenwood beats Louisville AND Gentry beats Greenwood by 4 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry\n"
        "6. Gentry beats Greenwood by exactly 4 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20136 AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by 4\u20135 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7 or more AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by exactly 5 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 2\u20136 AND Louisville beats Greenwood\n"
        "9. Gentry beats Greenwood by exactly 6 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 4 or more AND Louisville beats Greenwood\n"
        "10. Gentry beats Greenwood by exactly 7 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 6\u201311 AND Louisville beats Greenwood\n"
        "11. Gentry beats Greenwood by exactly 8 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8\u201310 AND Louisville beats Greenwood\n"
        "12. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 9 AND Louisville beats Greenwood\n"
        "13. Gentry beats Yazoo City AND Yazoo City beats Kosciusko by 7 or more AND Greenwood beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "#4 seed if: (30.4%)\n"
        "1. Gentry beats Greenwood AND Gentry beats Yazoo City\n"
        "2. Gentry beats Greenwood by 5 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 1 AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by 6 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 2\u20133 AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 7 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 4\u20135 AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by 7\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 12 or more AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by 8 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 6 AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by 8\u201311 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 7 AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by 8\u20139 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 11 AND Louisville beats Greenwood\n"
        "9. Gentry beats Greenwood by 9\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 8 AND Louisville beats Greenwood\n"
        "10. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 10 AND Louisville beats Greenwood\n"
        "11. Greenwood beats Gentry AND Yazoo City beats Kosciusko by 7 or more AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "Eliminated if: (6.9%)\n"
        "1. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City by 1\u201311 AND Yazoo City beats Gentry by 7 or more AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by 10 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7 or more AND Louisville beats Greenwood"
    ),
    "Kosciusko": (
        "Kosciusko\n"
        "\n"
        "#1 seed if: (12.5%)\n"
        "1. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Greenwood beats Louisville\n"
        "\n"
        "#2 seed if: (61.5%)\n"
        "1. Kosciusko beats Yazoo City AND Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood AND Kosciusko beats Yazoo City AND Greenwood beats Louisville\n"
        "3. Yazoo City beats Kosciusko AND Gentry beats Yazoo City AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Gentry beats Yazoo City AND Greenwood beats Louisville\n"
        "5. Greenwood beats Gentry AND Yazoo City beats Kosciusko by 1\u201310 AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "#3 seed if: (13.5%)\n"
        "1. Yazoo City beats Kosciusko by 11 or more AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "3. Greenwood beats Gentry AND Yazoo City beats Kosciusko AND Gentry beats Yazoo City AND Greenwood beats Louisville\n"
        "\n"
        "#4 seed if: (12.5%)\n"
        "1. Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville"
    ),
    "Louisville": (
        "Louisville\n"
        "\n"
        "#1 seed if: (75.0%)\n"
        "1. Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood AND Greenwood beats Louisville\n"
        "\n"
        "#2 seed if: (20.8%)\n"
        "1. Greenwood beats Louisville by 1\u20138 AND Greenwood beats Gentry\n"
        "2. Yazoo City beats Kosciusko AND Greenwood beats Louisville by 9 or more AND Greenwood beats Gentry\n"
        "\n"
        "#3 seed if: (4.2%)\n"
        "1. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Greenwood beats Louisville by 9 or more"
    ),
    "Yazoo City": (
        "Yazoo City\n"
        "\n"
        "#2 seed if: (7.3%)\n"
        "1. Yazoo City beats Kosciusko by 11 or more AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "2. Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "#3 seed if: (15.2%)\n"
        "1. Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville\n"
        "2. Gentry beats Greenwood by 7\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 12 or more AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by 8\u20139 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 11 AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City by 1\u201311 AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 10 AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by 10 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood\n"
        "7. Greenwood beats Gentry AND Yazoo City beats Kosciusko by 7\u201310 AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "#4 seed if: (24.2%)\n"
        "1. Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Greenwood beats Louisville\n"
        "2. Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by exactly 1 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 5 or more AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 2\u20133 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 6 or more AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by 4\u20135 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7 or more AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by exactly 6 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8 or more AND Louisville beats Greenwood\n"
        "7. Gentry beats Greenwood by exactly 7 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8\u201311 AND Louisville beats Greenwood\n"
        "8. Gentry beats Greenwood by exactly 8 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 9\u201310 AND Louisville beats Greenwood\n"
        "9. Gentry beats Greenwood by 9\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 9 AND Louisville beats Greenwood\n"
        "10. Gentry beats Greenwood by exactly 11 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 8\u20139 AND Louisville beats Greenwood\n"
        "11. Gentry beats Greenwood by 12 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 7\u201310 AND Louisville beats Greenwood\n"
        "12. Greenwood beats Gentry AND Yazoo City beats Kosciusko by 1\u20136 AND Yazoo City beats Gentry AND Louisville beats Greenwood\n"
        "\n"
        "Eliminated if: (53.3%)\n"
        "1. Gentry beats Yazoo City\n"
        "2. Gentry beats Greenwood AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20134 AND Louisville beats Greenwood\n"
        "3. Gentry beats Greenwood by 2 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 5 AND Louisville beats Greenwood\n"
        "4. Gentry beats Greenwood by 4 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 6 AND Louisville beats Greenwood\n"
        "5. Gentry beats Greenwood by 6\u201311 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 7 AND Louisville beats Greenwood\n"
        "6. Gentry beats Greenwood by 8\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 8 AND Louisville beats Greenwood"
    ),
}


def test_render_gentry_full():
    """Full render snapshot for Gentry (locks all atom conditions post-bug-fix)."""
    assert render_team_scenarios("Gentry", _ATOMS, odds=_ODDS) == _EXPECTED_RENDER["Gentry"]


def test_render_greenwood_full():
    """Full render snapshot for Greenwood."""
    assert render_team_scenarios("Greenwood", _ATOMS, odds=_ODDS) == _EXPECTED_RENDER["Greenwood"]


def test_render_kosciusko_full():
    """Full render snapshot for Kosciusko (including corrected 11-or-more atom)."""
    assert render_team_scenarios("Kosciusko", _ATOMS, odds=_ODDS) == _EXPECTED_RENDER["Kosciusko"]


def test_render_louisville_full():
    """Full render snapshot for Louisville."""
    assert render_team_scenarios("Louisville", _ATOMS, odds=_ODDS) == _EXPECTED_RENDER["Louisville"]


def test_render_yazoo_city_full():
    """Full render snapshot for Yazoo City (including corrected 11-or-more atom)."""
    assert render_team_scenarios("Yazoo City", _ATOMS, odds=_ODDS) == _EXPECTED_RENDER["Yazoo City"]


# ---------------------------------------------------------------------------
# Division scenario snapshots — title + seeds + eliminated for all 20
# ---------------------------------------------------------------------------

# Expected: (title, one_seed, two_seed, three_seed, four_seed, eliminated)
_EXPECTED_SCENARIOS = {
    "1a": (
        "Greenwood beats Gentry AND Yazoo City beats Kosciusko by 1\u20136 AND Yazoo City beats Gentry AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Yazoo City",
        ["Gentry"],
    ),
    "1b": (
        "Greenwood beats Gentry AND Yazoo City beats Kosciusko by 7\u201310 AND Yazoo City beats Gentry AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Yazoo City",
        "Greenwood",
        ["Gentry"],
    ),
    "1c": (
        "Greenwood beats Gentry AND Yazoo City beats Kosciusko by 11 or more AND Yazoo City beats Gentry AND Louisville beats Greenwood",
        "Louisville",
        "Yazoo City",
        "Kosciusko",
        "Greenwood",
        ["Gentry"],
    ),
    "2": (
        "Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Louisville beats Greenwood",
        "Louisville",
        "Yazoo City",
        "Kosciusko",
        "Gentry",
        ["Greenwood"],
    ),
    "3": (
        "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Yazoo City",
        ["Gentry"],
    ),
    "4a": (
        "Gentry beats Greenwood by exactly 1 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 1\u20134 AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Gentry",
        ["Yazoo City"],
    ),
    "4b": (
        "Gentry beats Greenwood by exactly 1 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 5 or more AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Yazoo City",
        ["Gentry"],
    ),
    "4c": (
        "Gentry beats Greenwood by 5 or more AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 1 AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Gentry",
        "Greenwood",
        ["Yazoo City"],
    ),
    "4d": (
        "Gentry beats Greenwood by 7\u201310 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by 12 or more AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Yazoo City",
        "Greenwood",
        ["Gentry"],
    ),
    "4e": (
        "Gentry beats Greenwood by exactly 9 AND Kosciusko beats Yazoo City by 1\u201311 AND Yazoo City beats Gentry by 9 or more AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Yazoo City",
        "Gentry",
        ["Greenwood"],
    ),
    "4f": (
        "Gentry beats Greenwood by exactly 10 AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry by exactly 9 AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Gentry",
        "Yazoo City",
        ["Greenwood"],
    ),
    "5": (
        "Greenwood beats Gentry AND Gentry beats Yazoo City AND Louisville beats Greenwood",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Gentry",
        ["Yazoo City"],
    ),
    "6": (
        "Gentry beats Greenwood AND Gentry beats Yazoo City",
        "Louisville",
        "Kosciusko",
        "Gentry",
        "Greenwood",
        ["Yazoo City"],
    ),
    "7": (
        "Greenwood beats Gentry AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville",
        "Greenwood",
        "Louisville",
        "Yazoo City",
        "Kosciusko",
        ["Gentry"],
    ),
    "8": (
        "Gentry beats Greenwood AND Yazoo City beats Kosciusko AND Yazoo City beats Gentry AND Greenwood beats Louisville",
        "Louisville",
        "Greenwood",
        "Yazoo City",
        "Kosciusko",
        ["Gentry"],
    ),
    "9a": (
        "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Greenwood beats Louisville by 1\u20138",
        "Kosciusko",
        "Louisville",
        "Greenwood",
        "Yazoo City",
        ["Gentry"],
    ),
    "9b": (
        "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Greenwood beats Louisville by 9 or more",
        "Kosciusko",
        "Greenwood",
        "Louisville",
        "Yazoo City",
        ["Gentry"],
    ),
    "10": (
        "Gentry beats Greenwood AND Kosciusko beats Yazoo City AND Yazoo City beats Gentry AND Greenwood beats Louisville",
        "Louisville",
        "Kosciusko",
        "Greenwood",
        "Yazoo City",
        ["Gentry"],
    ),
    "11": (
        "Greenwood beats Gentry AND Yazoo City beats Kosciusko AND Gentry beats Yazoo City AND Greenwood beats Louisville",
        "Greenwood",
        "Louisville",
        "Kosciusko",
        "Gentry",
        ["Yazoo City"],
    ),
    "12a": (
        "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Gentry beats Yazoo City AND Greenwood beats Louisville by 1\u20138",
        "Kosciusko",
        "Louisville",
        "Greenwood",
        "Gentry",
        ["Yazoo City"],
    ),
    "12b": (
        "Greenwood beats Gentry AND Kosciusko beats Yazoo City AND Gentry beats Yazoo City AND Greenwood beats Louisville by 9 or more",
        "Kosciusko",
        "Greenwood",
        "Louisville",
        "Gentry",
        ["Yazoo City"],
    ),
}


def _check_scenario(key):
    """Assert title, seeds 1-4, and eliminated list for the named scenario key."""
    title, s1, s2, s3, s4, elim = _EXPECTED_SCENARIOS[key]
    sc = _DIV_DICT[key]
    assert sc["title"] == title, f"scenario {key}: wrong title"
    assert sc["one_seed"] == s1, f"scenario {key}: wrong #1 seed"
    assert sc["two_seed"] == s2, f"scenario {key}: wrong #2 seed"
    assert sc["three_seed"] == s3, f"scenario {key}: wrong #3 seed"
    assert sc["four_seed"] == s4, f"scenario {key}: wrong #4 seed"
    assert sc.get("eliminated", []) == elim, f"scenario {key}: wrong eliminated"


def test_scenario_1a():
    """Scenario 1a: GRE>Gentry AND YZ beats KOS by 1-6 AND YZ>Gentry AND LOU>GRE."""
    _check_scenario("1a")


def test_scenario_1b():
    """Scenario 1b: GRE>Gentry AND YZ beats KOS by 7-10 AND YZ>Gentry AND LOU>GRE."""
    _check_scenario("1b")


def test_scenario_1c():
    """Scenario 1c: GRE>Gentry AND YZ beats KOS by 11+ AND YZ>Gentry AND LOU>GRE."""
    _check_scenario("1c")


def test_scenario_2():
    """Scenario 2: Gentry>GRE AND YZ>KOS AND YZ>Gentry AND LOU>GRE."""
    _check_scenario("2")


def test_scenario_3():
    """Scenario 3: GRE>Gentry AND KOS>YZ AND YZ>Gentry AND LOU>GRE."""
    _check_scenario("3")


def test_scenario_4a():
    """Scenario 4a: Gentry>GRE by exactly 1 AND KOS>YZ AND YZ>Gentry by 1-4 AND LOU>GRE."""
    _check_scenario("4a")


def test_scenario_4b():
    """Scenario 4b: Gentry>GRE by exactly 1 AND KOS>YZ AND YZ>Gentry by 5+ AND LOU>GRE."""
    _check_scenario("4b")


def test_scenario_4c():
    """Scenario 4c: Gentry>GRE by 5+ AND KOS>YZ AND YZ>Gentry by exactly 1 AND LOU>GRE."""
    _check_scenario("4c")


def test_scenario_4d():
    """Scenario 4d: Gentry>GRE by 7-10 AND KOS>YZ AND YZ>Gentry by 12+ AND LOU>GRE."""
    _check_scenario("4d")


def test_scenario_4e():
    """Scenario 4e: Gentry>GRE by exactly 9 AND KOS>YZ by 1-11 AND YZ>Gentry by 9-10 AND LOU>GRE."""
    _check_scenario("4e")


def test_scenario_4f():
    """Scenario 4f: Gentry>GRE by exactly 10 AND KOS>YZ AND YZ>Gentry by exactly 9 AND LOU>GRE."""
    _check_scenario("4f")


def test_scenario_5():
    """Scenario 5: GRE>Gentry AND Gentry>YZ AND LOU>GRE."""
    _check_scenario("5")


def test_scenario_6():
    """Scenario 6: Gentry>GRE AND Gentry>YZ (LOU/GRE result irrelevant)."""
    _check_scenario("6")


def test_scenario_7():
    """Scenario 7: GRE>Gentry AND YZ>KOS AND YZ>Gentry AND GRE>LOU."""
    _check_scenario("7")


def test_scenario_8():
    """Scenario 8: Gentry>GRE AND YZ>KOS AND YZ>Gentry AND GRE>LOU."""
    _check_scenario("8")


def test_scenario_9a():
    """Scenario 9a: GRE>Gentry AND KOS>YZ AND YZ>Gentry AND GRE>LOU by 1-8."""
    _check_scenario("9a")


def test_scenario_9b():
    """Scenario 9b: GRE>Gentry AND KOS>YZ AND YZ>Gentry AND GRE>LOU by 9+."""
    _check_scenario("9b")


def test_scenario_10():
    """Scenario 10: Gentry>GRE AND KOS>YZ AND YZ>Gentry AND GRE>LOU."""
    _check_scenario("10")


def test_scenario_11():
    """Scenario 11: GRE>Gentry AND YZ>KOS AND Gentry>YZ AND GRE>LOU."""
    _check_scenario("11")


def test_scenario_12a():
    """Scenario 12a: GRE>Gentry AND KOS>YZ AND Gentry>YZ AND GRE>LOU by 1-8."""
    _check_scenario("12a")


def test_scenario_12b():
    """Scenario 12b: GRE>Gentry AND KOS>YZ AND Gentry>YZ AND GRE>LOU by 9+."""
    _check_scenario("12b")
