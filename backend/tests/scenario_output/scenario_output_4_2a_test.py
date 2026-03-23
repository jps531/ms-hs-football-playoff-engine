"""Scenario output tests for Region 4-2A (2025 season, pre-final-week).

Region 4-2A is the simplest possible margin-sensitive case: two remaining games,
only one of which (Kemper County vs Philadelphia) affects seedings.  East Webster
has clinched #1 unconditionally; Eupora is always eliminated.

Teams (alphabetical): East Webster, Eupora, Kemper County, Philadelphia, Velma Jackson
Remaining games (cutoff 2025-10-24):
  East Webster vs Eupora        — East Webster beat Eupora 26–0 (actual)
  Kemper County vs Philadelphia — Kemper County beat Philadelphia 40–6 (actual, scenario 3)

Known 2025 seeds: East Webster / Kemper County / Velma Jackson / Philadelphia
Eliminated: Eupora

Code paths exercised:
  - build_scenario_atoms       — EW and Eupora unconditional; KC two-alternative atom for #2;
                                  VJ margin-insensitive; Philly three possible seeds
  - enumerate_division_scenarios — 5 scenarios (1a/1b from Eupora-upsets-EW masks,
                                    2a/2b from EW-wins masks, 3 from KC-wins mask)
  - EW/Eupora game appears in game_winners for MS sub-scenarios but not in any atom conditions
  - team_scenarios_as_dict      — exact fractional odds (75/25/50)
  - render_team_scenarios       — margin-qualified condition for KC/Philly threshold at 7
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

_FIXTURE = REGION_RESULTS_2025[(2, 4)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: East Webster, Eupora, Kemper County, Philadelphia, Velma Jackson
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: East Webster/Eupora, Kemper County/Philadelphia

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

EAST_WEBSTER_EXPECTED = "East Webster\n\nClinched #1 seed. (100.0%)"
EUPORA_EXPECTED = "Eupora\n\nEliminated. (100.0%)"

KEMPER_COUNTY_EXPECTED = """\
Kemper County

#2 seed if: (75.0%)
1. Kemper County beats Philadelphia
2. Philadelphia beats Kemper County by 1\u20136

#3 seed if: (25.0%)
1. Philadelphia beats Kemper County by 7 or more"""

PHILADELPHIA_EXPECTED = """\
Philadelphia

#2 seed if: (25.0%)
1. Philadelphia beats Kemper County by 7 or more

#3 seed if: (25.0%)
1. Philadelphia beats Kemper County by 1\u20136

#4 seed if: (50.0%)
1. Kemper County beats Philadelphia"""

VELMA_JACKSON_EXPECTED = """\
Velma Jackson

#3 seed if: (50.0%)
1. Kemper County beats Philadelphia

#4 seed if: (50.0%)
1. Philadelphia beats Kemper County"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_east_webster_seed_keys():
    """East Webster only has seed 1 — clinched unconditionally."""
    assert set(_ATOMS["East Webster"].keys()) == {1}


def test_atoms_eupora_seed_keys():
    """Eupora only has seed 5 — always eliminated."""
    assert set(_ATOMS["Eupora"].keys()) == {5}


def test_atoms_kemper_county_seed_keys():
    """Kemper County can finish 2nd or 3rd."""
    assert set(_ATOMS["Kemper County"].keys()) == {2, 3}


def test_atoms_philadelphia_seed_keys():
    """Philadelphia can finish 2nd, 3rd, or 4th."""
    assert set(_ATOMS["Philadelphia"].keys()) == {2, 3, 4}


def test_atoms_velma_jackson_seed_keys():
    """Velma Jackson can finish 3rd or 4th."""
    assert set(_ATOMS["Velma Jackson"].keys()) == {3, 4}


def test_atoms_east_webster_unconditional():
    """East Webster's clinched seed 1 collapses to a single [[]] atom."""
    assert _ATOMS["East Webster"][1] == [[]]


def test_atoms_eupora_unconditional():
    """Eupora's elimination is unconditional — atom is [[]]."""
    assert _ATOMS["Eupora"][5] == [[]]


def test_atoms_kemper_county_seed2_count():
    """Kemper County's seed-2 atom has two alternatives (KC wins OR Philly wins by 1–6)."""
    assert len(_ATOMS["Kemper County"][2]) == 2


def test_atoms_kemper_county_seed2_first_atom():
    """First KC seed-2 atom: KC beats Philly (unconditional)."""
    atom = _ATOMS["Kemper County"][2][0]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Kemper County"
    assert gr.loser == "Philadelphia"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_kemper_county_seed2_second_atom():
    """Second KC seed-2 atom: Philly beats KC by 1–6."""
    atom = _ATOMS["Kemper County"][2][1]
    assert len(atom) == 1
    gr = atom[0]
    assert isinstance(gr, GameResult)
    assert gr.winner == "Philadelphia"
    assert gr.loser == "Kemper County"
    assert gr.min_margin == 1
    assert gr.max_margin == 7  # exclusive upper bound: margins 1–6


def test_atoms_kemper_county_seed3_atom():
    """KC seed-3 atom: Philly beats KC by 7 or more."""
    assert len(_ATOMS["Kemper County"][3]) == 1
    atom = _ATOMS["Kemper County"][3][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Philadelphia"
    assert gr.loser == "Kemper County"
    assert gr.min_margin == 7
    assert gr.max_margin is None


def test_atoms_velma_jackson_seed3_atom():
    """VJ seed-3 atom: KC beats Philly (no margin constraint)."""
    assert len(_ATOMS["Velma Jackson"][3]) == 1
    gr = _ATOMS["Velma Jackson"][3][0][0]
    assert gr.winner == "Kemper County"
    assert gr.loser == "Philadelphia"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_velma_jackson_seed4_atom():
    """VJ seed-4 atom: Philly beats KC (no margin constraint)."""
    assert len(_ATOMS["Velma Jackson"][4]) == 1
    gr = _ATOMS["Velma Jackson"][4][0][0]
    assert gr.winner == "Philadelphia"
    assert gr.loser == "Kemper County"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_no_ew_eupora_condition_in_kc():
    """No East Webster / Eupora GameResult appears in any KC atom condition."""
    ew_eupora_pair = {"East Webster", "Eupora"}
    for seed, atoms in _ATOMS["Kemper County"].items():
        for atom in atoms:
            for cond in atom:
                if isinstance(cond, GameResult):
                    assert {cond.winner, cond.loser} != ew_eupora_pair, (
                        f"KC seed {seed} atom contains EW/Eupora condition"
                    )


def test_atoms_no_ew_eupora_condition_in_philly():
    """No East Webster / Eupora GameResult appears in any Philadelphia atom condition."""
    ew_eupora_pair = {"East Webster", "Eupora"}
    for seed, atoms in _ATOMS["Philadelphia"].items():
        for atom in atoms:
            for cond in atom:
                if isinstance(cond, GameResult):
                    assert {cond.winner, cond.loser} != ew_eupora_pair


def test_atoms_no_ew_eupora_condition_in_vj():
    """No East Webster / Eupora GameResult appears in any Velma Jackson atom condition."""
    ew_eupora_pair = {"East Webster", "Eupora"}
    for seed, atoms in _ATOMS["Velma Jackson"].items():
        for atom in atoms:
            for cond in atom:
                if isinstance(cond, GameResult):
                    assert {cond.winner, cond.loser} != ew_eupora_pair


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — count and structure
# ---------------------------------------------------------------------------


def test_scenario_count():
    """5 distinct scenario entries: 1a, 1b, 2a, 2b, 3."""
    assert len(_SCENARIOS) == 5


def test_scenario_keys():
    """Scenario keys are exactly {'1a', '1b', '2a', '2b', '3'}."""
    keys = {f"{s['scenario_num']}{s['sub_label']}" for s in _SCENARIOS}
    assert keys == {"1a", "1b", "2a", "2b", "3"}


def test_east_webster_always_first():
    """East Webster is the #1 seed in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][0] == "East Webster"


def test_eupora_always_eliminated():
    """Eupora never appears in positions 0–3 of any scenario seeding."""
    for sc in _SCENARIOS:
        assert "Eupora" not in sc["seeding"][:4]


def test_scenario_3_is_actual_result():
    """Scenario 3 (Kemper County beats Philadelphia) matches 2025 final seeds."""
    sc3 = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == "")
    assert sc3["seeding"][:4] == ("East Webster", "Kemper County", "Velma Jackson", "Philadelphia")


def test_scenario_3_game_winners():
    """Scenario 3 game_winners only lists the KC/Philly game (EW/Eupora is irrelevant)."""
    sc3 = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == "")
    assert sc3["game_winners"] == [("Kemper County", "Philadelphia")]
    assert sc3["conditions_atom"] is None


def test_scenario_1a_seeding():
    """Scenario 1a (Eupora upsets EW, Philly wins by 1–6): KC #2, Philly #3."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "a")
    assert sc["seeding"][:4] == ("East Webster", "Kemper County", "Philadelphia", "Velma Jackson")


def test_scenario_1b_seeding():
    """Scenario 1b (Eupora upsets EW, Philly wins by 7+): Philly #2, KC #3."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "b")
    assert sc["seeding"][:4] == ("East Webster", "Philadelphia", "Kemper County", "Velma Jackson")


def test_scenario_2a_seeding():
    """Scenario 2a (EW wins, Philly wins by 1–6): KC #2, Philly #3."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert sc["seeding"][:4] == ("East Webster", "Kemper County", "Philadelphia", "Velma Jackson")


def test_scenario_2b_seeding():
    """Scenario 2b (EW wins, Philly wins by 7+): Philly #2, KC #3."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc["seeding"][:4] == ("East Webster", "Philadelphia", "Kemper County", "Velma Jackson")


def test_scenarios_1a_2a_same_seeding():
    """Scenarios 1a and 2a produce identical seedings (EW/Eupora result irrelevant)."""
    sc1a = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "a")
    sc2a = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert sc1a["seeding"] == sc2a["seeding"]


def test_scenarios_1b_2b_same_seeding():
    """Scenarios 1b and 2b produce identical seedings."""
    sc1b = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "b")
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc1b["seeding"] == sc2b["seeding"]


def test_scenario_1a_game_winners_include_eupora():
    """Scenario 1a game_winners include the Eupora/EW result (Eupora wins that mask)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "a")
    assert ("Eupora", "East Webster") in sc["game_winners"]


def test_scenario_2a_game_winners_include_ew():
    """Scenario 2a game_winners include the EW/Eupora result (EW wins that mask)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert ("East Webster", "Eupora") in sc["game_winners"]


def test_scenario_1a_conditions_atom():
    """Scenario 1a conditions_atom: Philly beats KC with max_margin=7 (margins 1–6)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "a")
    ca = sc["conditions_atom"]
    assert ca is not None
    gr = next(c for c in ca if isinstance(c, GameResult))
    assert gr.winner == "Philadelphia"
    assert gr.loser == "Kemper County"
    assert gr.min_margin == 1
    assert gr.max_margin == 7


def test_scenario_1b_conditions_atom():
    """Scenario 1b conditions_atom: Philly beats KC with min_margin=7 (7 or more)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "b")
    ca = sc["conditions_atom"]
    assert ca is not None
    gr = next(c for c in ca if isinstance(c, GameResult))
    assert gr.winner == "Philadelphia"
    assert gr.loser == "Kemper County"
    assert gr.min_margin == 7
    assert gr.max_margin is None


def test_velma_jackson_never_margin_sensitive():
    """Velma Jackson appears in no margin-sensitive sub-scenario at position 1 or 2."""
    for sc in _SCENARIOS:
        if sc["sub_label"] != "":
            # In all sub-scenarios VJ is always at the same position
            vj_pos = sc["seeding"].index("Velma Jackson") if "Velma Jackson" in sc["seeding"] else -1
            assert vj_pos == 3, f"VJ at unexpected position {vj_pos} in scenario {sc['scenario_num']}{sc['sub_label']}"


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_keys():
    """division_scenarios_as_dict produces keys '1a','1b','2a','2b','3'."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "2a", "2b", "3"}


def test_div_dict_scenario3_title():
    """Scenario 3 title is 'Kemper County beats Philadelphia'."""
    assert _DIV_DICT["3"]["title"] == "Kemper County beats Philadelphia"


def test_div_dict_scenario1a_title():
    """Scenario 1a title is the conditions_atom: Philly wins by 1–6 (no EW/Eupora clause)."""
    assert _DIV_DICT["1a"]["title"] == "Philadelphia beats Kemper County by 1\u20136"


def test_div_dict_scenario2b_title():
    """Scenario 2b title is the conditions_atom: Philly wins by 7 or more."""
    assert _DIV_DICT["2b"]["title"] == "Philadelphia beats Kemper County by 7 or more"


def test_div_dict_scenario3_seeds():
    """Scenario 3 seeds: EW #1, KC #2, VJ #3, Philly #4."""
    sc = _DIV_DICT["3"]
    assert sc["one_seed"] == "East Webster"
    assert sc["two_seed"] == "Kemper County"
    assert sc["three_seed"] == "Velma Jackson"
    assert sc["four_seed"] == "Philadelphia"


def test_div_dict_scenario1b_seeds():
    """Scenario 1b seeds (Philly wins by 7+): Philly #2, KC #3."""
    sc = _DIV_DICT["1b"]
    assert sc["two_seed"] == "Philadelphia"
    assert sc["three_seed"] == "Kemper County"


def test_div_dict_eliminated_always_eupora():
    """In every scenario the eliminated list is exactly ['Eupora']."""
    for key, entry in _DIV_DICT.items():
        assert entry["eliminated"] == ["Eupora"], f"Scenario {key}: unexpected eliminated list"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_team_dict_east_webster_clinched():
    """East Webster team dict has only seed 1 at 100%."""
    ew = _TEAM_DICT["East Webster"]
    assert list(ew.keys()) == [1]
    assert ew[1]["odds"] == pytest.approx(1.0, abs=1e-9)


def test_team_dict_eupora_eliminated():
    """Eupora team dict has only an 'eliminated' entry at 100%."""
    assert "eliminated" in _TEAM_DICT["Eupora"]
    assert _TEAM_DICT["Eupora"]["eliminated"]["odds"] == pytest.approx(1.0, abs=1e-9)


def test_team_dict_kemper_county_odds():
    """KC: p2=75%, p3=25%."""
    kc = _TEAM_DICT["Kemper County"]
    assert kc[2]["odds"] == pytest.approx(0.75, abs=1e-9)
    assert kc[3]["odds"] == pytest.approx(0.25, abs=1e-9)


def test_team_dict_kemper_county_odds_sum_to_one():
    """KC seed odds sum to 1.0."""
    kc = _TEAM_DICT["Kemper County"]
    assert sum(v["odds"] for v in kc.values()) == pytest.approx(1.0, abs=1e-9)


def test_team_dict_philadelphia_odds():
    """Philadelphia: p2=25%, p3=25%, p4=50%."""
    ph = _TEAM_DICT["Philadelphia"]
    assert ph[2]["odds"] == pytest.approx(0.25, abs=1e-9)
    assert ph[3]["odds"] == pytest.approx(0.25, abs=1e-9)
    assert ph[4]["odds"] == pytest.approx(0.50, abs=1e-9)


def test_team_dict_philadelphia_odds_sum_to_one():
    """Philadelphia seed odds sum to 1.0."""
    ph = _TEAM_DICT["Philadelphia"]
    assert sum(v["odds"] for v in ph.values()) == pytest.approx(1.0, abs=1e-9)


def test_team_dict_velma_jackson_odds():
    """Velma Jackson: p3=50%, p4=50%."""
    vj = _TEAM_DICT["Velma Jackson"]
    assert vj[3]["odds"] == pytest.approx(0.50, abs=1e-9)
    assert vj[4]["odds"] == pytest.approx(0.50, abs=1e-9)


def test_team_dict_all_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("East Webster", EAST_WEBSTER_EXPECTED),
        ("Eupora", EUPORA_EXPECTED),
        ("Kemper County", KEMPER_COUNTY_EXPECTED),
        ("Philadelphia", PHILADELPHIA_EXPECTED),
        ("Velma Jackson", VELMA_JACKSON_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected string for each team."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


def test_render_east_webster_without_odds():
    """East Webster renders as 'Clinched #1 seed.' without odds."""
    assert render_team_scenarios("East Webster", _ATOMS) == "East Webster\n\nClinched #1 seed."


def test_render_eupora_without_odds():
    """Eupora renders as 'Eliminated.' without odds."""
    assert render_team_scenarios("Eupora", _ATOMS) == "Eupora\n\nEliminated."
