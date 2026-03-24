"""Scenario output tests for Region 2-2A (2025 season, pre-final-week).

Region 2-2A has two pre-determined seeds (Water Valley clinched #1, Myrtle clinched #2)
and a richly margin-sensitive Bruce/Strayhorn game with four sub-scenarios when Bruce
wins and Water Valley wins their respective games.

Teams (alphabetical): Bruce, East Union, Myrtle, Strayhorn, Water Valley
Remaining games (cutoff 2025-10-24):
  Bruce vs Strayhorn      — Strayhorn beat Bruce 32–28, margin 4 (actual, scenario 1)
  East Union vs Water Valley — Water Valley beat East Union 32–22, margin 10 (actual)

Known 2025 seeds: Water Valley / Myrtle / Strayhorn / East Union
Eliminated: Bruce

Code paths exercised:
  - build_scenario_atoms       — WV/Myrtle unconditional; EU seed-4 has 3 non-contiguous atoms;
                                  EU seed-3 second atom is standalone [Bruce 3–8] (Rule 3 lift);
                                  Bruce/Strayhorn seed-4 atoms each include a Rule-3-simplified
                                  standalone margin condition
  - enumerate_division_scenarios — 6 scenarios (1 non-MS, 4 MS sub-scenarios for Bruce wins +
                                    WV wins, 1 non-MS for Bruce wins + EU wins)
  - Scenario 2d: Strayhorn loses by 1–2 but still earns #3 seed via tiebreaker
  - Scenario 2b: conditions_atom only mentions Bruce/Strayhorn margin (WV/EU dropped)
  - team_scenarios_as_dict      — EU has two possible seeds (no elimination); Bruce/Strayhorn
                                   each have three possible outcomes including elimination
  - render_team_scenarios       — standalone margin conditions after boolean simplification
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

_FIXTURE = REGION_RESULTS_2025[(2, 2)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Bruce, East Union, Myrtle, Strayhorn, Water Valley
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Bruce/Strayhorn (bit 0), East Union/Water Valley (bit 1)

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

WATER_VALLEY_EXPECTED = "Water Valley\n\nClinched #1 seed. (100.0%)"
MYRTLE_EXPECTED = "Myrtle\n\nClinched #2 seed. (100.0%)"

BRUCE_EXPECTED = """\
Bruce

#3 seed if: (8.3%)
1. Bruce beats Strayhorn by 9 or more AND Water Valley beats East Union

#4 seed if: (33.3%)
1. Bruce beats Strayhorn AND East Union beats Water Valley
2. Bruce beats Strayhorn by 5\u20138

Eliminated if: (58.3%)
1. Strayhorn beats Bruce
2. Bruce beats Strayhorn by 1\u20134 AND Water Valley beats East Union"""

EAST_UNION_EXPECTED = """\
East Union

#3 seed if: (37.5%)
1. Bruce beats Strayhorn AND East Union beats Water Valley
2. Bruce beats Strayhorn by 3\u20138

#4 seed if: (62.5%)
1. Strayhorn beats Bruce
2. Bruce beats Strayhorn by 1\u20132 AND Water Valley beats East Union
3. Bruce beats Strayhorn by 9 or more AND Water Valley beats East Union"""

STRAYHORN_EXPECTED = """\
Strayhorn

#3 seed if: (54.2%)
1. Strayhorn beats Bruce
2. Bruce beats Strayhorn by 1\u20132 AND Water Valley beats East Union

#4 seed if: (4.2%)
1. Bruce beats Strayhorn by 3\u20134 AND Water Valley beats East Union

Eliminated if: (41.7%)
1. Bruce beats Strayhorn AND East Union beats Water Valley
2. Bruce beats Strayhorn by 5 or more"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_water_valley_seed_keys():
    """Water Valley only has seed 1 — clinched unconditionally."""
    assert set(_ATOMS["Water Valley"].keys()) == {1}


def test_atoms_myrtle_seed_keys():
    """Myrtle only has seed 2 — clinched unconditionally."""
    assert set(_ATOMS["Myrtle"].keys()) == {2}


def test_atoms_bruce_seed_keys():
    """Bruce can finish 3rd, 4th, or be eliminated."""
    assert set(_ATOMS["Bruce"].keys()) == {3, 4, 5}


def test_atoms_east_union_seed_keys():
    """East Union can finish 3rd or 4th — never eliminated."""
    assert set(_ATOMS["East Union"].keys()) == {3, 4}


def test_atoms_strayhorn_seed_keys():
    """Strayhorn can finish 3rd, 4th, or be eliminated."""
    assert set(_ATOMS["Strayhorn"].keys()) == {3, 4, 5}


def test_atoms_water_valley_unconditional():
    """Water Valley's seed 1 collapses to [[]]."""
    assert _ATOMS["Water Valley"][1] == [[]]


def test_atoms_myrtle_unconditional():
    """Myrtle's seed 2 collapses to [[]]."""
    assert _ATOMS["Myrtle"][2] == [[]]


# ---------------------------------------------------------------------------
# Bruce atoms
# ---------------------------------------------------------------------------


def test_atoms_bruce_seed3_atom():
    """Bruce seed-3: only one atom — Bruce wins by 9+ AND WV wins."""
    assert len(_ATOMS["Bruce"][3]) == 1
    atom = _ATOMS["Bruce"][3][0]
    assert len(atom) == 2
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Bruce")
    gr_wv = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Water Valley")
    assert gr_bruce.loser == "Strayhorn"
    assert gr_bruce.min_margin == 9
    assert gr_bruce.max_margin is None
    assert gr_wv.loser == "East Union"
    assert gr_wv.min_margin == 1
    assert gr_wv.max_margin is None


def test_atoms_bruce_seed4_count():
    """Bruce seed-4 has two alternative atoms."""
    assert len(_ATOMS["Bruce"][4]) == 2


def test_atoms_bruce_seed4_first_atom():
    """First Bruce seed-4 atom: Bruce wins (any) AND East Union wins."""
    atom = _ATOMS["Bruce"][4][0]
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Bruce")
    gr_eu = next(c for c in atom if isinstance(c, GameResult) and c.winner == "East Union")
    assert gr_bruce.min_margin == 1 and gr_bruce.max_margin is None
    assert gr_eu.loser == "Water Valley"


def test_atoms_bruce_seed4_second_atom_standalone():
    """Second Bruce seed-4 atom: standalone Bruce wins by 5–8 (Rule 3 lifted WV condition)."""
    atom = _ATOMS["Bruce"][4][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Bruce"
    assert gr.loser == "Strayhorn"
    assert gr.min_margin == 5
    assert gr.max_margin == 9  # exclusive upper bound: margins 5–8


def test_atoms_bruce_seed5_count():
    """Bruce elimination has two alternative atoms."""
    assert len(_ATOMS["Bruce"][5]) == 2


def test_atoms_bruce_seed5_first_atom():
    """First Bruce elimination atom: Strayhorn wins (any margin)."""
    atom = _ATOMS["Bruce"][5][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Strayhorn"
    assert gr.loser == "Bruce"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_bruce_seed5_second_atom():
    """Second Bruce elimination atom: Bruce wins by 1–4 AND Water Valley wins."""
    atom = _ATOMS["Bruce"][5][1]
    assert len(atom) == 2
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.loser == "Strayhorn")
    gr_wv = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Water Valley")
    assert gr_bruce.winner == "Bruce"
    assert gr_bruce.min_margin == 1
    assert gr_bruce.max_margin == 5  # exclusive upper bound: margins 1–4
    assert gr_wv.loser == "East Union"


# ---------------------------------------------------------------------------
# East Union atoms
# ---------------------------------------------------------------------------


def test_atoms_east_union_seed3_count():
    """East Union seed-3 has two alternative atoms."""
    assert len(_ATOMS["East Union"][3]) == 2


def test_atoms_east_union_seed3_first_atom():
    """First EU seed-3 atom: Bruce wins (any) AND East Union wins."""
    atom = _ATOMS["East Union"][3][0]
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Bruce")
    gr_eu = next(c for c in atom if isinstance(c, GameResult) and c.winner == "East Union")
    assert gr_bruce.min_margin == 1 and gr_bruce.max_margin is None
    assert gr_eu.loser == "Water Valley"


def test_atoms_east_union_seed3_second_atom_standalone():
    """Second EU seed-3 atom: standalone Bruce wins by 3–8 (WV condition lifted by Rule 3)."""
    atom = _ATOMS["East Union"][3][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Bruce"
    assert gr.loser == "Strayhorn"
    assert gr.min_margin == 3
    assert gr.max_margin == 9  # exclusive upper bound: margins 3–8


def test_atoms_east_union_seed4_count():
    """East Union seed-4 has three non-contiguous alternative atoms."""
    assert len(_ATOMS["East Union"][4]) == 3


def test_atoms_east_union_seed4_strayhorn_wins_atom():
    """One EU seed-4 atom: Strayhorn wins (any margin, any WV/EU result)."""
    atoms = _ATOMS["East Union"][4]
    strayhorn_atom = next(
        (a for a in atoms if len(a) == 1 and a[0].winner == "Strayhorn"),
        None,
    )
    assert strayhorn_atom is not None
    assert strayhorn_atom[0].loser == "Bruce"
    assert strayhorn_atom[0].min_margin == 1
    assert strayhorn_atom[0].max_margin is None


def test_atoms_east_union_seed4_bruce_low_margin_atom():
    """One EU seed-4 atom: Bruce wins by 1–2 AND WV wins."""
    atoms = _ATOMS["East Union"][4]
    low_atom = next(
        (
            a for a in atoms
            if any(isinstance(c, GameResult) and c.winner == "Bruce" and c.max_margin == 3 for c in a)
        ),
        None,
    )
    assert low_atom is not None
    gr_bruce = next(c for c in low_atom if isinstance(c, GameResult) and c.winner == "Bruce")
    assert gr_bruce.min_margin == 1
    assert gr_bruce.max_margin == 3  # exclusive upper bound: margins 1–2


def test_atoms_east_union_seed4_bruce_high_margin_atom():
    """One EU seed-4 atom: Bruce wins by 9+ AND WV wins."""
    atoms = _ATOMS["East Union"][4]
    high_atom = next(
        (
            a for a in atoms
            if any(isinstance(c, GameResult) and c.winner == "Bruce" and c.min_margin == 9 for c in a)
        ),
        None,
    )
    assert high_atom is not None
    gr_bruce = next(c for c in high_atom if isinstance(c, GameResult) and c.winner == "Bruce")
    assert gr_bruce.min_margin == 9
    assert gr_bruce.max_margin is None


# ---------------------------------------------------------------------------
# Strayhorn atoms
# ---------------------------------------------------------------------------


def test_atoms_strayhorn_seed3_count():
    """Strayhorn seed-3 has two alternative atoms."""
    assert len(_ATOMS["Strayhorn"][3]) == 2


def test_atoms_strayhorn_seed3_first_atom():
    """First Strayhorn seed-3 atom: Strayhorn wins (any margin)."""
    atom = _ATOMS["Strayhorn"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Strayhorn"
    assert gr.min_margin == 1 and gr.max_margin is None


def test_atoms_strayhorn_seed3_second_atom():
    """Second Strayhorn seed-3 atom: Bruce wins by 1–2 AND WV wins (Strayhorn loses but makes playoffs)."""
    atom = _ATOMS["Strayhorn"][3][1]
    assert len(atom) == 2
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Bruce")
    gr_wv = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Water Valley")
    assert gr_bruce.loser == "Strayhorn"
    assert gr_bruce.min_margin == 1
    assert gr_bruce.max_margin == 3  # exclusive upper bound: margins 1–2
    assert gr_wv.loser == "East Union"


def test_atoms_strayhorn_seed4_count():
    """Strayhorn seed-4 has exactly one atom — a narrow 3–4 margin window."""
    assert len(_ATOMS["Strayhorn"][4]) == 1


def test_atoms_strayhorn_seed4_atom():
    """Strayhorn seed-4 atom: Bruce wins by 3–4 AND WV wins."""
    atom = _ATOMS["Strayhorn"][4][0]
    assert len(atom) == 2
    gr_bruce = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Bruce")
    gr_wv = next(c for c in atom if isinstance(c, GameResult) and c.winner == "Water Valley")
    assert gr_bruce.min_margin == 3
    assert gr_bruce.max_margin == 5  # exclusive upper bound: margins 3–4
    assert gr_wv.loser == "East Union"


def test_atoms_strayhorn_seed5_count():
    """Strayhorn elimination has two alternative atoms."""
    assert len(_ATOMS["Strayhorn"][5]) == 2


def test_atoms_strayhorn_seed5_second_atom_standalone():
    """Second Strayhorn elimination atom: standalone Bruce wins by 5+ (Rule 3 lifted EU condition)."""
    atoms = _ATOMS["Strayhorn"][5]
    standalone = next(
        (a for a in atoms if len(a) == 1 and a[0].winner == "Bruce"),
        None,
    )
    assert standalone is not None
    gr = standalone[0]
    assert gr.min_margin == 5
    assert gr.max_margin is None


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — count and structure
# ---------------------------------------------------------------------------


def test_scenario_count():
    """6 distinct scenario entries."""
    assert len(_SCENARIOS) == 6


def test_scenario_keys():
    """Scenario keys are exactly {'1', '2a', '2b', '2c', '2d', '3'}."""
    keys = {f"{s['scenario_num']}{s['sub_label']}" for s in _SCENARIOS}
    assert keys == {"1", "2a", "2b", "2c", "2d", "3"}


def test_water_valley_always_first():
    """Water Valley is #1 in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][0] == "Water Valley"


def test_myrtle_always_second():
    """Myrtle is #2 in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][1] == "Myrtle"


def test_scenario_1_is_actual_result():
    """Scenario 1 (Strayhorn beats Bruce) matches 2025 final seeds."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "Strayhorn", "East Union", "Bruce")


def test_scenario_1_eu_wv_irrelevant():
    """Scenario 1 game_winners only lists Strayhorn beats Bruce (EU/WV irrelevant)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "")
    assert sc["game_winners"] == [("Strayhorn", "Bruce")]
    assert sc["conditions_atom"] is None


def test_scenario_3_seeding():
    """Scenario 3 (Bruce wins, EU wins): EU #3, Bruce #4, Strayhorn eliminated."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == "")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "East Union", "Bruce", "Strayhorn")


def test_scenario_2a_seeding():
    """Scenario 2a (Bruce wins by 9+, WV wins): Bruce #3, EU #4."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "Bruce", "East Union", "Strayhorn")


def test_scenario_2b_seeding():
    """Scenario 2b (Bruce wins by 5–8): EU #3, Bruce #4."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "East Union", "Bruce", "Strayhorn")


def test_scenario_2c_seeding():
    """Scenario 2c (Bruce wins by 3–4, WV wins): EU #3, Strayhorn #4."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "c")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "East Union", "Strayhorn", "Bruce")


def test_scenario_2d_seeding():
    """Scenario 2d (Bruce wins by 1–2, WV wins): Strayhorn #3 despite losing the game."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "d")
    assert sc["seeding"][:5] == ("Water Valley", "Myrtle", "Strayhorn", "East Union", "Bruce")


def test_scenario_2b_conditions_atom_no_eu_wv():
    """Scenario 2b conditions_atom only specifies Bruce margin — no EU/WV game condition."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    ca = sc["conditions_atom"]
    assert ca is not None
    assert len(ca) == 1
    gr = ca[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Bruce"
    assert gr.min_margin == 5
    assert gr.max_margin == 9  # exclusive upper bound: margins 5–8
    assert {gr.winner, gr.loser} == {"Bruce", "Strayhorn"}


def test_scenario_2a_conditions_atom():
    """Scenario 2a conditions_atom: Bruce wins by 9+ AND WV wins."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    ca = sc["conditions_atom"]
    assert ca is not None
    gr_bruce = next(c for c in ca if isinstance(c, GameResult) and c.winner == "Bruce")
    assert gr_bruce.min_margin == 9 and gr_bruce.max_margin is None


def test_scenario_2c_conditions_atom():
    """Scenario 2c conditions_atom: Bruce wins by 3–4 AND WV wins."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "c")
    ca = sc["conditions_atom"]
    gr_bruce = next(c for c in ca if isinstance(c, GameResult) and c.winner == "Bruce")
    assert gr_bruce.min_margin == 3
    assert gr_bruce.max_margin == 5  # exclusive: margins 3–4


def test_scenario_2d_conditions_atom():
    """Scenario 2d conditions_atom: Bruce wins by 1–2 AND WV wins."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "d")
    ca = sc["conditions_atom"]
    gr_bruce = next(c for c in ca if isinstance(c, GameResult) and c.winner == "Bruce")
    assert gr_bruce.min_margin == 1
    assert gr_bruce.max_margin == 3  # exclusive: margins 1–2


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_keys():
    """division_scenarios_as_dict produces keys '1', '2a', '2b', '2c', '2d', '3'."""
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "2c", "2d", "3"}


def test_div_dict_scenario1_title():
    """Scenario 1 title: Strayhorn beats Bruce."""
    assert _DIV_DICT["1"]["title"] == "Strayhorn beats Bruce"


def test_div_dict_scenario3_title():
    """Scenario 3 title: Bruce beats Strayhorn AND East Union beats Water Valley."""
    title = _DIV_DICT["3"]["title"]
    assert "Bruce beats Strayhorn" in title
    assert "East Union beats Water Valley" in title


def test_div_dict_scenario2b_title():
    """Scenario 2b title: only the Bruce margin condition (no EU/WV clause)."""
    assert _DIV_DICT["2b"]["title"] == "Bruce beats Strayhorn by 5\u20138"


def test_div_dict_scenario1_seeds():
    """Scenario 1 seeds: WV #1, Myrtle #2, Strayhorn #3, EU #4."""
    sc = _DIV_DICT["1"]
    assert sc["one_seed"] == "Water Valley"
    assert sc["two_seed"] == "Myrtle"
    assert sc["three_seed"] == "Strayhorn"
    assert sc["four_seed"] == "East Union"


def test_div_dict_scenario2a_seeds():
    """Scenario 2a seeds: Bruce #3, EU #4."""
    sc = _DIV_DICT["2a"]
    assert sc["three_seed"] == "Bruce"
    assert sc["four_seed"] == "East Union"


def test_div_dict_eliminated_always_includes_either_bruce_or_strayhorn():
    """In every scenario exactly one of Bruce/Strayhorn is eliminated."""
    for key, entry in _DIV_DICT.items():
        elim = entry["eliminated"]
        assert len(elim) == 1
        assert elim[0] in {"Bruce", "Strayhorn"}


def test_div_dict_scenario3_eliminated():
    """Scenario 3 (Bruce wins, EU wins): Strayhorn eliminated."""
    assert _DIV_DICT["3"]["eliminated"] == ["Strayhorn"]


def test_div_dict_scenario1_eliminated():
    """Scenario 1 (Strayhorn wins): Bruce eliminated."""
    assert _DIV_DICT["1"]["eliminated"] == ["Bruce"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_team_dict_water_valley():
    """Water Valley team dict has only seed 1 at 100%."""
    wv = _TEAM_DICT["Water Valley"]
    assert list(wv.keys()) == [1]
    assert wv[1]["odds"] == pytest.approx(1.0, abs=1e-9)


def test_team_dict_myrtle():
    """Myrtle team dict has only seed 2 at 100%."""
    my = _TEAM_DICT["Myrtle"]
    assert list(my.keys()) == [2]
    assert my[2]["odds"] == pytest.approx(1.0, abs=1e-9)


def test_team_dict_bruce_odds():
    """Bruce: p3≈8.3%, p4≈33.3%, eliminated≈58.3%."""
    b = _TEAM_DICT["Bruce"]
    assert b[3]["odds"] == pytest.approx(1 / 12, abs=1e-9)
    assert b[4]["odds"] == pytest.approx(4 / 12, abs=1e-9)
    assert b["eliminated"]["odds"] == pytest.approx(7 / 12, abs=1e-9)


def test_team_dict_bruce_odds_sum_to_one():
    """Bruce seed odds sum to 1.0."""
    assert sum(v["odds"] for v in _TEAM_DICT["Bruce"].values()) == pytest.approx(1.0, abs=1e-9)


def test_team_dict_east_union_odds():
    """East Union: p3≈37.5%, p4≈62.5% — never eliminated."""
    eu = _TEAM_DICT["East Union"]
    assert eu[3]["odds"] == pytest.approx(0.375, abs=1e-9)
    assert eu[4]["odds"] == pytest.approx(0.625, abs=1e-9)
    assert "eliminated" not in eu


def test_team_dict_strayhorn_odds():
    """Strayhorn: p3≈54.2%, p4≈4.2%, eliminated≈41.7%."""
    s = _TEAM_DICT["Strayhorn"]
    assert s[3]["odds"] == pytest.approx(13 / 24, abs=1e-9)
    assert s[4]["odds"] == pytest.approx(1 / 24, abs=1e-9)
    assert s["eliminated"]["odds"] == pytest.approx(10 / 24, abs=1e-9)


def test_team_dict_strayhorn_odds_sum_to_one():
    """Strayhorn seed odds sum to 1.0."""
    assert sum(v["odds"] for v in _TEAM_DICT["Strayhorn"].values()) == pytest.approx(1.0, abs=1e-9)


def test_team_dict_all_weighted_odds_none():
    """weighted_odds is None for all entries."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Water Valley", WATER_VALLEY_EXPECTED),
        ("Myrtle", MYRTLE_EXPECTED),
        ("Bruce", BRUCE_EXPECTED),
        ("East Union", EAST_UNION_EXPECTED),
        ("Strayhorn", STRAYHORN_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected string for each team."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


def test_render_water_valley_without_odds():
    """Water Valley renders as 'Clinched #1 seed.' without odds."""
    assert render_team_scenarios("Water Valley", _ATOMS) == "Water Valley\n\nClinched #1 seed."


def test_render_myrtle_without_odds():
    """Myrtle renders as 'Clinched #2 seed.' without odds."""
    assert render_team_scenarios("Myrtle", _ATOMS) == "Myrtle\n\nClinched #2 seed."
