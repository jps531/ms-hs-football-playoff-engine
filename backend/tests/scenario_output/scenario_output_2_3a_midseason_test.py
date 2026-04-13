"""Scenario output tests for Region 2-3A (Class 3A, Region 2), 2025 season midseason.

Cutoff: 2025-10-10 (first two weeks of five-week region play completed).

Completed games (2):
  2025-10-03  Independence 47 - Holly Springs 6
  2025-10-10  Coahoma County 36 - North Panola 12

Standings at cutoff:
  Coahoma County:  1-0
  Independence:    1-0
  Holly Springs:   0-1
  North Panola:    0-1

Remaining games (4 — three weeks of play):
  bit 0: Independence vs North Panola  (North Panola won 20-14,  2025-10-17)
  bit 1: Coahoma County vs Holly Springs (Coahoma County won 52-6, 2025-10-24)
  bit 2: Coahoma County vs Independence (Coahoma County won 30-0, 2025-10-31)
  bit 3: Holly Springs vs North Panola  (North Panola won 34-14,  2025-10-30)

Known 2025 seeds: Coahoma County #1 / North Panola #2 / Independence #3 / Holly Springs #4
Eliminated: none (all four teams advance to the playoffs)

Actual outcome mask: 6 (bits 1 and 2 set — Coahoma County wins both their remaining
games; North Panola wins both theirs). Falls in scenario 5 (non-sensitive: every
remaining game is margin-irrelevant for the top-4 seeding).

Key structural properties:
  - Two symmetric tied pairs at cutoff: {Coahoma County, Independence} (both 1-0)
    and {Holly Springs, North Panola} (both 0-1).
  - Both tied pairs have a remaining H2H game (Oct 30), so the tiebreaker is never
    a coin flip — Step 1 (H2H record) always resolves the tie once the H2H game is
    played.  This exercises ``build_h2h_maps`` reading remaining-game outcomes from
    the outcome mask, which is the mid-season H2H-in-remaining path.
  - All four teams clinch playoffs (p_playoffs = 1.0); the ``if eliminated:`` block
    in ``render_scenarios`` is never reached (covers the False branch from a real
    mid-season fixture rather than the synthetic all-advance case in
    ``scenario_output_3_1a_test.py``).
  - 3-way tie scenario (mask = bit0=0, bit1=1, bit2=0, bit3=0 → CC/NP/Ind all 2-1)
    drives Steps 1-4 tiebreakers with margin sensitivity, producing 5 sub-labels in
    scenario 3 (3a-3e).
  - Symmetric odds: Coahoma County and Independence are interchangeable (both 1-0
    with identical schedule structure), as are Holly Springs and North Panola.
  - Denominator is 2^4 = 16 (four remaining games, equal win probabilities).

Coverage this test specifically adds:
  - Real mid-season data with H2H game in remaining (``build_h2h_maps`` remaining path).
  - 3-way tie resolution with margin sensitivity (5 sub-labels in one scenario group).
  - All-advance region (no eliminated teams) from real data.
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
_CUTOFF = "2025-10-10"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Coahoma County, Holly Springs, Independence, North Panola
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# bit 0: Independence/North Panola, bit 1: Coahoma County/Holly Springs,
# bit 2: Coahoma County/Independence, bit 3: Holly Springs/North Panola

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
    """Four games remain across three weeks."""
    assert len(_REMAINING) == 4


def test_remaining_game_pairs():
    """Remaining game pairs match bit order (alphabetical within each pair)."""
    assert _REMAINING[0] == RemainingGame("Independence", "North Panola")
    assert _REMAINING[1] == RemainingGame("Coahoma County", "Holly Springs")
    assert _REMAINING[2] == RemainingGame("Coahoma County", "Independence")
    assert _REMAINING[3] == RemainingGame("Holly Springs", "North Panola")


def test_scenario_denominator():
    """Denominator is 2^4 = 16 (four remaining games, equal win probabilities)."""
    assert _SR.denom == pytest.approx(16.0)


def test_scenario_count():
    """28 distinct division scenarios (margin sensitivity creates sub-labels)."""
    assert len(_SCENARIOS) == 28


# ---------------------------------------------------------------------------
# Atom seed key structure — all four teams reach all four seeds
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """build_scenario_atoms returns an entry for every team."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_coahoma_county_seed_keys():
    """Coahoma County can finish any seed 1-4."""
    assert set(_ATOMS["Coahoma County"].keys()) == {1, 2, 3, 4}


def test_atoms_independence_seed_keys():
    """Independence can finish any seed 1-4."""
    assert set(_ATOMS["Independence"].keys()) == {1, 2, 3, 4}


def test_atoms_holly_springs_seed_keys():
    """Holly Springs can finish any seed 1-4."""
    assert set(_ATOMS["Holly Springs"].keys()) == {1, 2, 3, 4}


def test_atoms_north_panola_seed_keys():
    """North Panola can finish any seed 1-4."""
    assert set(_ATOMS["North Panola"].keys()) == {1, 2, 3, 4}


def test_no_eliminated_seed_key():
    """No team has a seed-5 (elimination) atom — all four advance."""
    for team in _TEAMS:
        assert 5 not in _ATOMS.get(team, {})


# ---------------------------------------------------------------------------
# Odds — all teams clinched; symmetric between the two tied pairs
# ---------------------------------------------------------------------------


def test_all_teams_clinched():
    """All four teams clinch playoffs (p_playoffs = 1.0)."""
    for team in _TEAMS:
        assert _ODDS[team].p_playoffs == pytest.approx(1.0)


def test_no_team_eliminated():
    """No team is flagged as eliminated."""
    for team in _TEAMS:
        assert not _ODDS[team].eliminated


def test_coahoma_county_and_independence_have_equal_odds():
    """Coahoma County and Independence have near-identical odds (symmetric 1-0 records).

    Floating-point accumulation order causes differences of ~6e-6; abs=1e-4 tolerance
    is tight enough to catch real bugs while tolerating this numerical noise.
    """
    cc = _ODDS["Coahoma County"]
    ind = _ODDS["Independence"]
    assert cc.p1 == pytest.approx(ind.p1, abs=1e-4)
    assert cc.p2 == pytest.approx(ind.p2, abs=1e-4)
    assert cc.p3 == pytest.approx(ind.p3, abs=1e-4)
    assert cc.p4 == pytest.approx(ind.p4, abs=1e-4)


def test_holly_springs_and_north_panola_have_equal_odds():
    """Holly Springs and North Panola have near-identical odds (symmetric 0-1 records)."""
    hs = _ODDS["Holly Springs"]
    np_ = _ODDS["North Panola"]
    assert hs.p1 == pytest.approx(np_.p1, abs=1e-4)
    assert hs.p2 == pytest.approx(np_.p2, abs=1e-4)
    assert hs.p3 == pytest.approx(np_.p3, abs=1e-4)
    assert hs.p4 == pytest.approx(np_.p4, abs=1e-4)


def test_coahoma_county_seed1_odds():
    """Coahoma County seed-1 probability is approximately 43.75%.

    Margin-sensitive masks distribute probability fractionally, so the value
    is not exactly 7/16; abs=0.001 (0.1%) tolerance accommodates this.
    """
    assert _ODDS["Coahoma County"].p1 == pytest.approx(7 / 16, abs=0.001)


def test_coahoma_county_seed4_odds():
    """Coahoma County seed-4 probability is approximately 6.25%."""
    assert _ODDS["Coahoma County"].p4 == pytest.approx(1 / 16, abs=0.001)


def test_holly_springs_seed4_odds():
    """Holly Springs seed-4 probability is approximately 43.75% (mirror of CC seed-1)."""
    assert _ODDS["Holly Springs"].p4 == pytest.approx(7 / 16, abs=0.001)


def test_no_coin_flip_teams():
    """No coin flip needed — all ties resolve through H2H in remaining games."""
    assert _SR.coinflip_teams == set()


# ---------------------------------------------------------------------------
# Coahoma County seed-1 atoms — simplest unconditional atom first
# ---------------------------------------------------------------------------


def test_coahoma_county_seed1_first_atom_conditions():
    """CC seed-1 first atom: CC beats Ind (any margin) AND NP beats HS (any margin).

    This is the simplest path to CC at seed 1: CC beats their strongest remaining
    opponent (Ind) and their H2H rival's opponent (NP beats HS) — forcing a 3-0
    or 2-1 CC record where CC beats NP by H2H (from the Oct 10 completed game).
    """
    atom = _ATOMS["Coahoma County"][1][0]
    cc_beats_ind = next(
        (c for c in atom if isinstance(c, GameResult) and c.winner == "Coahoma County" and c.loser == "Independence"),
        None,
    )
    np_beats_hs = next(
        (c for c in atom if isinstance(c, GameResult) and c.winner == "North Panola" and c.loser == "Holly Springs"),
        None,
    )
    assert cc_beats_ind is not None, "CC beats Ind condition missing"
    assert cc_beats_ind.min_margin == 1
    assert cc_beats_ind.max_margin is None  # any winning margin qualifies
    assert np_beats_hs is not None, "NP beats HS condition missing"
    assert np_beats_hs.min_margin == 1
    assert np_beats_hs.max_margin is None


def test_coahoma_county_seed1_atom_count():
    """CC seed-1 has 14 atoms (margin-sensitive tiebreaker paths when 3-way ties occur)."""
    assert len(_ATOMS["Coahoma County"][1]) == 14


def test_coahoma_county_seed4_atom_count():
    """CC seed-4 has only 2 atoms (rare outcome — CC loses both remaining games)."""
    assert len(_ATOMS["Coahoma County"][4]) == 2


def test_coahoma_county_seed4_first_atom():
    """CC seed-4 atom 0: NP beats Ind AND HS beats CC AND Ind beats CC AND NP beats HS.

    CC finishes 1-2 (kept only the completed win over NP) while all three opponents
    beat CC or leapfrog it — CC falls to 4th.
    """
    atom = _ATOMS["Coahoma County"][4][0]
    winners = {(c.winner, c.loser) for c in atom if isinstance(c, GameResult)}
    assert ("North Panola", "Independence") in winners
    assert ("Holly Springs", "Coahoma County") in winners
    assert ("Independence", "Coahoma County") in winners
    assert ("North Panola", "Holly Springs") in winners


# ---------------------------------------------------------------------------
# Scenario 5 — the actual 2025 outcome (mask = 6)
# ---------------------------------------------------------------------------


def test_scenario5_seeding_matches_actual_2025():
    """Scenario 5 produces the actual 2025 seeding: CC #1, NP #2, Ind #3, HS #4."""
    sc5 = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 5 and sc["sub_label"] == "")
    assert list(sc5["seeding"]) == [
        "Coahoma County", "North Panola", "Independence", "Holly Springs"
    ]


def test_scenario5_is_non_sensitive():
    """Scenario 5 has no conditions_atom — it is a non-margin-sensitive scenario.

    When CC=3-0 or CC=2-1 (H2H tie-break over NP), NP=2-1, Ind=1-2, HS=0-3
    the standings are determined by W-L record alone, so no margin qualifiers are
    needed.  ``conditions_atom`` is None in this case.
    """
    sc5 = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 5 and sc["sub_label"] == "")
    assert sc5["conditions_atom"] is None


def test_scenario5_game_winners():
    """Scenario 5 game winners: NP beats Ind, CC beats Ind, NP beats HS.

    The CC vs HS game (bit 1) is absent — irrelevant to the top-4 seeding in
    this scenario regardless of which team wins it.
    """
    sc5 = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 5 and sc["sub_label"] == "")
    winners = set(sc5["game_winners"])
    assert ("North Panola", "Independence") in winners
    assert ("Coahoma County", "Independence") in winners
    assert ("North Panola", "Holly Springs") in winners
    # CC vs HS game is margin-irrelevant in this scenario
    assert ("Coahoma County", "Holly Springs") not in winners
    assert ("Holly Springs", "Coahoma County") not in winners


# ---------------------------------------------------------------------------
# Scenario 3 — 3-way tie (CC/NP/Ind all 2-1) with margin-sensitive sub-labels
# ---------------------------------------------------------------------------


def test_scenario3_has_five_sub_labels():
    """Scenario 3 has five sub-labels (a-e) due to 3-way 2-1 tie requiring tiebreakers.

    Mask: NP beats Ind (bit 0), CC beats HS (bit 1), Ind beats CC (bit 2),
    NP beats HS (bit 3) → CC=2-1, NP=2-1, Ind=2-1 (3-way tie), HS=0-3.
    Steps 1-4 tiebreakers produce five margin-distinct orderings.
    """
    sc3_labels = sorted(sc["sub_label"] for sc in _SCENARIOS if sc["scenario_num"] == 3)
    assert sc3_labels == ["a", "b", "c", "d", "e"]


def test_scenario3_all_have_conditions_atom():
    """All scenario 3 sub-scenarios are margin-sensitive and have a conditions_atom."""
    for sc in _SCENARIOS:
        if sc["scenario_num"] == 3:
            assert sc["conditions_atom"] is not None, (
                f"scenario 3{sc['sub_label']} missing conditions_atom"
            )


def test_scenario3_game_winners_consistent():
    """All scenario 3 sub-scenarios share the same 4 game winners (same mask).

    The sub-labels differ only in margin qualifiers — the underlying outcome
    (which team won each game) is the same for all five variants.
    """
    sc3_winners = [
        tuple(sorted(sc["game_winners"]))
        for sc in _SCENARIOS
        if sc["scenario_num"] == 3
    ]
    assert len(set(sc3_winners)) == 1, "All sub-scenarios should share the same game winners"


# ---------------------------------------------------------------------------
# render_team_scenarios — sanity checks on output strings
# ---------------------------------------------------------------------------


def test_render_coahoma_county_contains_seed1_header():
    """Coahoma County's rendered output has a '#1 seed if:' section."""
    output = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in output


def test_render_coahoma_county_references_independence():
    """Coahoma County's rendered conditions mention Independence (the H2H rival)."""
    output = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "Independence" in output


def test_render_all_teams_present_in_team_dict():
    """team_scenarios_as_dict returns an entry for every team."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


# ---------------------------------------------------------------------------
# Division scenario dict — structural checks
# ---------------------------------------------------------------------------


def test_div_dict_key_count():
    """division_scenarios_as_dict has 28 entries (one per scenario sub-label)."""
    assert len(_DIV_DICT) == 28


def test_div_dict_contains_scenario5():
    """Scenario 5 (no sub-label) is present as key '5' in the division dict."""
    assert "5" in _DIV_DICT


def test_div_dict_scenario3_sub_keys():
    """Scenario 3 appears under keys '3a' through '3e'."""
    for lbl in ("3a", "3b", "3c", "3d", "3e"):
        assert lbl in _DIV_DICT, f"Missing key '{lbl}'"


# ---------------------------------------------------------------------------
# Renders — per-team seed sections, percentages, and specific condition strings
# ---------------------------------------------------------------------------

# Coahoma County


def test_render_coahoma_county_seed_sections_present():
    """Coahoma County shows all four seed sections but never Eliminated."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" not in rendered


def test_render_coahoma_county_seed1_pct():
    """Coahoma County's #1-seed section shows 43.7%."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (43.7%)" in rendered


def test_render_coahoma_county_seed2_pct():
    """Coahoma County's #2-seed section shows 33.9%."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#2 seed if: (33.9%)" in rendered


def test_render_coahoma_county_seed3_pct():
    """Coahoma County's #3-seed section shows 16.1%."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#3 seed if: (16.1%)" in rendered


def test_render_coahoma_county_seed4_pct():
    """Coahoma County's #4-seed section shows 6.3%."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "#4 seed if: (6.3%)" in rendered


def test_render_coahoma_county_seed1_simplest_atom():
    """CC's simplest #1-seed path: beats Independence AND NP beats Holly Springs."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "Coahoma County beats Independence AND North Panola beats Holly Springs" in rendered


def test_render_coahoma_county_seed4_first_atom():
    """CC's first #4 atom: NP beats Ind AND HS beats CC AND Ind beats CC AND NP beats HS."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert (
        "North Panola beats Independence AND Holly Springs beats Coahoma County AND "
        "Independence beats Coahoma County AND North Panola beats Holly Springs"
    ) in rendered


def test_render_coahoma_county_has_margin_conditions():
    """CC's render contains margin-sensitive conditions (from 3-way tie resolution)."""
    rendered = render_team_scenarios("Coahoma County", _ATOMS, odds=_ODDS)
    assert "by exactly" in rendered


# Independence


def test_render_independence_seed_sections_present():
    """Independence shows all four seed sections but never Eliminated."""
    rendered = render_team_scenarios("Independence", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" not in rendered


def test_render_independence_seed1_pct():
    """Independence's #1-seed section shows 43.7%."""
    rendered = render_team_scenarios("Independence", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (43.7%)" in rendered


def test_render_independence_seed4_pct():
    """Independence's #4-seed section shows 6.3%."""
    rendered = render_team_scenarios("Independence", _ATOMS, odds=_ODDS)
    assert "#4 seed if: (6.3%)" in rendered


def test_render_independence_seed1_simplest_atom():
    """Independence's simplest #1 path: beats Coahoma County AND Holly Springs beats North Panola."""
    rendered = render_team_scenarios("Independence", _ATOMS, odds=_ODDS)
    assert "Independence beats Coahoma County AND Holly Springs beats North Panola" in rendered


def test_render_independence_seed4_first_atom():
    """Independence's first #4 atom: NP beats Ind AND HS beats CC AND CC beats Ind AND NP beats HS."""
    rendered = render_team_scenarios("Independence", _ATOMS, odds=_ODDS)
    assert (
        "North Panola beats Independence AND Holly Springs beats Coahoma County AND "
        "Coahoma County beats Independence AND Holly Springs beats North Panola"
    ) in rendered


# Holly Springs


def test_render_holly_springs_seed_sections_present():
    """Holly Springs shows all four seed sections but never Eliminated."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" not in rendered


def test_render_holly_springs_seed1_pct():
    """Holly Springs's #1-seed section shows 6.3%."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (6.3%)" in rendered


def test_render_holly_springs_seed3_pct():
    """Holly Springs's #3-seed section shows 33.9% (mirror of CC's #2)."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert "#3 seed if: (33.9%)" in rendered


def test_render_holly_springs_seed4_pct():
    """Holly Springs's #4-seed section shows 43.7% (mirror of CC's #1)."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert "#4 seed if: (43.7%)" in rendered


def test_render_holly_springs_seed1_first_atom():
    """Holly Springs's simplest #1 path: NP beats Ind AND HS beats CC AND CC beats Ind AND HS beats NP."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert (
        "North Panola beats Independence AND Holly Springs beats Coahoma County AND "
        "Coahoma County beats Independence AND Holly Springs beats North Panola"
    ) in rendered


def test_render_holly_springs_seed4_first_atom():
    """Holly Springs's first #4 atom: CC beats Independence AND NP beats Holly Springs."""
    rendered = render_team_scenarios("Holly Springs", _ATOMS, odds=_ODDS)
    assert "Coahoma County beats Independence AND North Panola beats Holly Springs" in rendered


# North Panola


def test_render_north_panola_seed_sections_present():
    """North Panola shows all four seed sections but never Eliminated."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert "#1 seed if:" in rendered
    assert "#2 seed if:" in rendered
    assert "#3 seed if:" in rendered
    assert "#4 seed if:" in rendered
    assert "Eliminated if:" not in rendered


def test_render_north_panola_seed1_pct():
    """North Panola's #1-seed section shows 6.3%."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert "#1 seed if: (6.3%)" in rendered


def test_render_north_panola_seed3_pct():
    """North Panola's #3-seed section shows 33.9% (mirror of Ind's #2)."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert "#3 seed if: (33.9%)" in rendered


def test_render_north_panola_seed4_pct():
    """North Panola's #4-seed section shows 43.7% (mirror of Ind's #1)."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert "#4 seed if: (43.7%)" in rendered


def test_render_north_panola_seed1_first_atom():
    """North Panola's simplest #1 path: NP beats Ind AND HS beats CC AND Ind beats CC AND NP beats HS."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert (
        "North Panola beats Independence AND Holly Springs beats Coahoma County AND "
        "Independence beats Coahoma County AND North Panola beats Holly Springs"
    ) in rendered


def test_render_north_panola_seed4_first_atom():
    """North Panola's first #4 atom: Ind beats CC AND HS beats NP."""
    rendered = render_team_scenarios("North Panola", _ATOMS, odds=_ODDS)
    assert "Independence beats Coahoma County AND Holly Springs beats North Panola" in rendered
