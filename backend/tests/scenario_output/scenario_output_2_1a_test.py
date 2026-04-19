"""Scenario output tests for Region 2-1A (2025 season, pre-final-week).

Region 2-1A is a margin-sensitive tiebreaker case driven by a three-way tie
for seeds 2–4 in two of the four raw outcome combinations.

Pre-cutoff standings (through 2025-10-24, 4 games played):
  Falkner:    2-0  (beat Ashland, beat H. W. Byers)
  H. W. Byers: 1-1  (beat Potts Camp, lost to Falkner)
  Potts Camp:  1-1  (beat Ashland, lost to H. W. Byers)
  Ashland:    0-2  (lost to Falkner, lost to Potts Camp)

Remaining games (cutoff 2025-10-24):
  Falkner vs Potts Camp       — Falkner won 50-27 (by 23 → margin ≥ 12; actual, scenario 2)
  Ashland vs H. W. Byers      — H. W. Byers won 39-0 (by 39 → margin ≥ 12; actual, scenario 2)

Known 2025 seeds: Falkner / H. W. Byers / Potts Camp / Ashland
Eliminated: none

Scenario structure (7 sub-scenarios):
  Scenario 1 (3 sub-labels a/b/c): Potts Camp beats Falkner AND H. W. Byers beats Ashland
    — Falkner, Potts Camp, and H. W. Byers finish 2-1; tiebreaker splits by PD margin.
    1a: Falkner #1, H. W. Byers #2, Potts Camp #3, Ashland #4  (Falkner PD advantage)
    1b: Falkner #1, Potts Camp #2, H. W. Byers #3, Ashland #4  (Potts Camp PD advantage)
    1c: Potts Camp #1, Falkner #2, H. W. Byers #3, Ashland #4  (Potts Camp large-margin win)
  Scenario 2 (no sub-label):   Falkner beats Potts Camp AND H. W. Byers beats Ashland
    → Falkner #1, H. W. Byers #2, Potts Camp #3, Ashland #4  (actual result)
  Scenario 3 (no sub-label):   Potts Camp beats Falkner AND Ashland beats H. W. Byers
    → Potts Camp #1, Falkner #2, Ashland #3, H. W. Byers #4
  Scenario 4 (2 sub-labels a/b): Falkner beats Potts Camp AND Ashland beats H. W. Byers
    — Ashland, H. W. Byers, and Potts Camp finish 1-2; tiebreaker splits by PD margin.
    4a: Falkner #1, H. W. Byers #2, Potts Camp #3, Ashland #4  (H. W. Byers PD advantage)
    4b: Falkner #1, Potts Camp #2, Ashland #3, H. W. Byers #4  (Potts Camp PD advantage)

Code paths exercised:
  - build_scenario_atoms       — multi-seed atoms for all 4 teams; margin-restricted
                                  GameResults (max_margin=12 cap from H2H PD tiebreaker);
                                  Falkner has 3-atom list for seed 1; H. W. Byers reaches seed 3
  - enumerate_division_scenarios — 7 sub-scenarios: scenario 1 has 3 sub-labels,
                                   scenario 4 has 2 sub-labels
  - division_scenarios_as_dict  — 7 keys (1a, 1b, 1c, 2, 3, 4a, 4b); scenarios 1a/1b/1c
                                   share one title string; 4a/4b share another
  - team_scenarios_as_dict      — fractional odds (72.9%/70.8%/27.1%/2.1%); H. W. Byers
                                   and Potts Camp each have 3 possible seed outcomes
  - render_team_scenarios       — margin-qualified condition strings; Falkner's #1 block
                                   uses both an unconstrained atom and margin-restricted atoms
"""

import pytest

from backend.helpers.data_classes import RemainingGame
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

_FIXTURE = REGION_RESULTS_2025[(1, 2)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Ashland, Falkner, H. W. Byers, Potts Camp
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: RemainingGame('Falkner', 'Potts Camp'), RemainingGame('Ashland', 'H. W. Byers')

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

FALKNER_EXPECTED = """\
Falkner

#1 seed if: (73.1%)
1. Falkner beats Potts Camp
2. Potts Camp beats Falkner by 1\u201311 AND H. W. Byers beats Ashland
3. Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 12 or more

#2 seed if: (26.9%)
1. Potts Camp beats Falkner AND Ashland beats H. W. Byers
2. Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 1\u201311"""

HWB_EXPECTED = """\
H. W. Byers

#2 seed if: (70.8%)
1. Falkner beats Potts Camp AND H. W. Byers beats Ashland
2. Falkner beats Potts Camp AND Ashland beats H. W. Byers by 1\u201311
3. Potts Camp beats Falkner by 1\u201311 AND H. W. Byers beats Ashland

#3 seed if: (2.1%)
1. Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland

#4 seed if: (27.1%)
1. Ashland beats H. W. Byers by 12 or more
2. Potts Camp beats Falkner AND Ashland beats H. W. Byers"""

POTTS_CAMP_EXPECTED = """\
Potts Camp

#1 seed if: (26.9%)
1. Potts Camp beats Falkner AND Ashland beats H. W. Byers
2. Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 1\u201311

#2 seed if: (2.3%)
1. Falkner beats Potts Camp AND Ashland beats H. W. Byers by 12 or more
2. Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 12 or more

#3 seed if: (70.8%)
1. Falkner beats Potts Camp AND H. W. Byers beats Ashland
2. Falkner beats Potts Camp AND Ashland beats H. W. Byers by 1\u201311
3. Potts Camp beats Falkner by 1\u201311 AND H. W. Byers beats Ashland"""

ASHLAND_EXPECTED = """\
Ashland

#3 seed if: (27.1%)
1. Ashland beats H. W. Byers by 12 or more
2. Potts Camp beats Falkner AND Ashland beats H. W. Byers

#4 seed if: (72.9%)
1. H. W. Byers beats Ashland
2. Falkner beats Potts Camp AND Ashland beats H. W. Byers by 1\u201311"""

# ---------------------------------------------------------------------------
# build_scenario_atoms
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_falkner_has_two_seeds():
    """Falkner can only finish #1 or #2 — they are always a top-2 team."""
    assert set(_ATOMS["Falkner"].keys()) == {1, 2}


def test_atoms_hwb_has_three_seeds():
    """H. W. Byers can finish #2, #3, or #4."""
    assert set(_ATOMS["H. W. Byers"].keys()) == {2, 3, 4}


def test_atoms_potts_camp_has_three_seeds():
    """Potts Camp can finish #1, #2, or #3."""
    assert set(_ATOMS["Potts Camp"].keys()) == {1, 2, 3}


def test_atoms_ashland_has_two_seeds():
    """Ashland can finish #3 or #4 — they are always a bottom-2 team."""
    assert set(_ATOMS["Ashland"].keys()) == {3, 4}


def test_atoms_falkner_seed1_three_atoms():
    """Falkner's #1 seed requires 3 atoms: outright win, narrow loss + HWB win,
    or large loss + large HWB win."""
    assert len(_ATOMS["Falkner"][1]) == 3


def test_atoms_falkner_seed1_first_atom_unconstrained():
    """Falkner's simplest path to #1: beat Potts Camp by any margin."""
    atom = _ATOMS["Falkner"][1][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "Falkner"
    assert gr.loser == "Potts Camp"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_falkner_seed1_second_atom_margin_restricted():
    """Falkner's #1 when PC wins by 1–11: PC beats Falkner narrowly AND HWB beats Ashland."""
    atom = _ATOMS["Falkner"][1][1]
    assert len(atom) == 2
    pc_gr = next(g for g in atom if g.winner == "Potts Camp")
    assert pc_gr.loser == "Falkner"
    assert pc_gr.min_margin == 1
    assert pc_gr.max_margin == 12  # exclusive upper bound → margin 1–11


def test_atoms_falkner_seed1_third_atom_double_large_margin():
    """Falkner's #1 via double large-margin wins: PC wins by 12+ AND HWB wins by 12+."""
    atom = _ATOMS["Falkner"][1][2]
    assert len(atom) == 2
    for gr in atom:
        assert gr.min_margin == 12
        assert gr.max_margin is None


def test_atoms_hwb_seed3_is_single_atom():
    """H. W. Byers reaches #3 only via one narrow path: PC beats Falkner by 12+ AND HWB beats Ashland."""
    atoms = _ATOMS["H. W. Byers"][3]
    assert len(atoms) == 1
    atom = atoms[0]
    assert len(atom) == 2
    pc_gr = next(g for g in atom if g.winner == "Potts Camp")
    assert pc_gr.min_margin == 12
    assert pc_gr.max_margin is None


def test_atoms_ashland_seed4_has_two_atoms():
    """Ashland ends up #4 either when HWB beats them outright, or when Falkner beats PC
    and Ashland wins by only 1–11."""
    assert len(_ATOMS["Ashland"][4]) == 2


def test_atoms_ashland_seed4_first_atom_hwb_wins():
    """Ashland #4 simplest path: H. W. Byers beats Ashland by any margin."""
    atom = _ATOMS["Ashland"][4][0]
    assert len(atom) == 1
    gr = atom[0]
    assert gr.winner == "H. W. Byers"
    assert gr.loser == "Ashland"
    assert gr.min_margin == 1
    assert gr.max_margin is None


def test_atoms_no_margin_conditions():
    """No atom contains a MarginCondition object — only GameResult conditions appear."""
    from backend.helpers.data_classes import MarginCondition

    for team, seeds in _ATOMS.items():
        for seed, atom_list in seeds.items():
            for atom in atom_list:
                for condition in atom:
                    assert not isinstance(condition, MarginCondition), (
                        f"{team!r} seed {seed} has unexpected MarginCondition: {condition}"
                    )


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """There are exactly 7 sub-scenarios (4 raw outcomes split by margin tiebreakers)."""
    assert len(_SCENARIOS) == 7


def test_scenario_shape():
    """Every scenario has the required keys."""
    required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom", "tiebreaker_groups", "coinflip_groups"}
    for sc in _SCENARIOS:
        assert set(sc.keys()) == required


def test_scenario_nums_present():
    """Scenario numbers 1, 2, 3, 4 all appear."""
    nums = {sc["scenario_num"] for sc in _SCENARIOS}
    assert nums == {1, 2, 3, 4}


def test_scenario_1_has_three_sub_labels():
    """Scenario 1 (PC beats Falkner, HWB beats Ashland) has 3 margin-sensitive sub-labels."""
    sub_labels = [sc["sub_label"] for sc in _SCENARIOS if sc["scenario_num"] == 1]
    assert sorted(sub_labels) == ["a", "b", "c"]


def test_scenario_4_has_two_sub_labels():
    """Scenario 4 (Falkner beats PC, Ashland beats HWB) has 2 margin-sensitive sub-labels."""
    sub_labels = [sc["sub_label"] for sc in _SCENARIOS if sc["scenario_num"] == 4]
    assert sorted(sub_labels) == ["a", "b"]


def test_scenarios_2_and_3_have_no_sub_labels():
    """Scenarios 2 and 3 produce unambiguous seedings — no sub-label needed."""
    for sc in _SCENARIOS:
        if sc["scenario_num"] in (2, 3):
            assert sc["sub_label"] == "", f"scenario {sc['scenario_num']} should have no sub_label"


def test_scenario_2_seeding():
    """Scenario 2 (Falkner beats PC AND HWB beats Ashland) → actual 2025 result."""
    sc2 = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 2)
    assert sc2["seeding"] == ("Falkner", "H. W. Byers", "Potts Camp", "Ashland")


def test_scenario_3_seeding():
    """Scenario 3 (PC beats Falkner AND Ashland beats HWB) → Potts Camp #1."""
    sc3 = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 3)
    assert sc3["seeding"] == ("Potts Camp", "Falkner", "Ashland", "H. W. Byers")


def test_scenario_1c_seeding():
    """Scenario 1c: PC 12+ AND HWB 12+ → Falkner still #1 (PD advantage)."""
    sc1c = next(sc for sc in _SCENARIOS if sc["scenario_num"] == 1 and sc["sub_label"] == "c")
    assert sc1c["seeding"][0] == "Falkner"


def test_scenario_no_eliminated():
    """All four teams make the playoffs in every scenario — no eliminations."""
    for sc in _SCENARIOS:
        assert len(sc["seeding"]) == 4


def test_scenario_1_game_winners():
    """All three scenario-1 sub-labels share the same game winners."""
    s1_entries = [sc for sc in _SCENARIOS if sc["scenario_num"] == 1]
    game_winner_sets = [tuple(sorted(sc["game_winners"])) for sc in s1_entries]
    assert len(set(game_winner_sets)) == 1, "scenario 1 sub-labels should have identical game winners"


def test_scenario_4_game_winners():
    """Both scenario-4 sub-labels share the same game winners."""
    s4_entries = [sc for sc in _SCENARIOS if sc["scenario_num"] == 4]
    game_winner_sets = [tuple(sorted(sc["game_winners"])) for sc in s4_entries]
    assert len(set(game_winner_sets)) == 1, "scenario 4 sub-labels should have identical game winners"


def test_non_sub_scenarios_conditions_atom_none():
    """Non-sub-labeled scenarios (2 and 3) have conditions_atom=None."""
    for sc in _SCENARIOS:
        if sc["sub_label"] == "":
            assert sc["conditions_atom"] is None, (
                f"scenario {sc['scenario_num']} should have conditions_atom=None"
            )


def test_sub_scenarios_have_conditions_atom():
    """All margin-sensitive sub-scenarios (1a/1b/1c, 4a/4b) have a non-None conditions_atom."""
    for sc in _SCENARIOS:
        if sc["sub_label"] != "":
            assert sc["conditions_atom"] is not None, (
                f"scenario {sc['scenario_num']}{sc['sub_label']}: expected conditions_atom, got None"
            )


def test_scenario_1a_conditions_atom():
    """Scenario 1a: PC wins by 1–11 (max=12, exclusive), HWB wins by any margin."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "a")
    ca = sc["conditions_atom"]
    pc_gr = next(gr for gr in ca if gr.winner == "Potts Camp")
    assert pc_gr.min_margin == 1
    assert pc_gr.max_margin == 12  # exclusive → renders as "by 1–11"
    hwb_gr = next(gr for gr in ca if gr.winner == "H. W. Byers")
    assert hwb_gr.min_margin == 1
    assert hwb_gr.max_margin is None


def test_scenario_1b_conditions_atom():
    """Scenario 1b: PC wins by 12+ AND HWB wins by 1–11 (max=12, exclusive)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "b")
    ca = sc["conditions_atom"]
    pc_gr = next(gr for gr in ca if gr.winner == "Potts Camp")
    assert pc_gr.min_margin == 12
    assert pc_gr.max_margin is None
    hwb_gr = next(gr for gr in ca if gr.winner == "H. W. Byers")
    assert hwb_gr.min_margin == 1
    assert hwb_gr.max_margin == 12  # exclusive → renders as "by 1–11"


def test_scenario_1c_conditions_atom():
    """Scenario 1c: PC wins by 12+ AND HWB wins by 12+."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1 and s["sub_label"] == "c")
    ca = sc["conditions_atom"]
    pc_gr = next(gr for gr in ca if gr.winner == "Potts Camp")
    assert pc_gr.min_margin == 12
    assert pc_gr.max_margin is None
    hwb_gr = next(gr for gr in ca if gr.winner == "H. W. Byers")
    assert hwb_gr.min_margin == 12
    assert hwb_gr.max_margin is None


def test_scenario_4a_conditions_atom():
    """Scenario 4a: Falkner beats PC by any margin, Ashland beats HWB by 1–11."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 4 and s["sub_label"] == "a")
    ca = sc["conditions_atom"]
    falkner_gr = next(gr for gr in ca if gr.winner == "Falkner")
    assert falkner_gr.min_margin == 1
    assert falkner_gr.max_margin is None
    ashland_gr = next(gr for gr in ca if gr.winner == "Ashland")
    assert ashland_gr.min_margin == 1
    assert ashland_gr.max_margin == 12  # exclusive → renders as "by 1–11"


def test_scenario_4b_conditions_atom():
    """Scenario 4b: Falkner beats PC by any margin, Ashland beats HWB by 12+."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 4 and s["sub_label"] == "b")
    ca = sc["conditions_atom"]
    ashland_gr = next(gr for gr in ca if gr.winner == "Ashland")
    assert ashland_gr.min_margin == 12
    assert ashland_gr.max_margin is None


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_seven_keys():
    """Dict has exactly 7 keys: 1a, 1b, 1c, 2, 3, 4a, 4b."""
    assert set(_DIV_DICT.keys()) == {"1a", "1b", "1c", "2", "3", "4a", "4b"}


def test_div_dict_entry_shape():
    """Each entry has exactly the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"key {key!r} has unexpected shape"


def test_div_dict_no_eliminated_teams():
    """Eliminated list is empty in every scenario."""
    for key, entry in _DIV_DICT.items():
        assert entry["eliminated"] == [], f"key {key!r} has unexpected eliminated: {entry['eliminated']}"


def test_div_dict_scenario1_sub_labels_distinct_titles():
    """Scenarios 1a, 1b, 1c each have a distinct margin-qualified title."""
    assert _DIV_DICT["1a"]["title"] == "Potts Camp beats Falkner by 1\u201311 AND H. W. Byers beats Ashland"
    assert _DIV_DICT["1b"]["title"] == "Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 1\u201311"
    assert _DIV_DICT["1c"]["title"] == "Potts Camp beats Falkner by 12 or more AND H. W. Byers beats Ashland by 12 or more"


def test_div_dict_scenario4_sub_labels_distinct_titles():
    """Scenarios 4a and 4b have distinct margin-qualified titles."""
    assert _DIV_DICT["4a"]["title"] == "Falkner beats Potts Camp AND Ashland beats H. W. Byers by 1\u201311"
    assert _DIV_DICT["4b"]["title"] == "Falkner beats Potts Camp AND Ashland beats H. W. Byers by 12 or more"


def test_div_dict_scenario2_title():
    """Scenario 2 title: Falkner beats Potts Camp AND H. W. Byers beats Ashland."""
    assert _DIV_DICT["2"]["title"] == "Falkner beats Potts Camp AND H. W. Byers beats Ashland"


def test_div_dict_scenario3_title():
    """Scenario 3 title: Potts Camp beats Falkner AND Ashland beats H. W. Byers."""
    assert _DIV_DICT["3"]["title"] == "Potts Camp beats Falkner AND Ashland beats H. W. Byers"


def test_div_dict_scenario2_seeds():
    """Scenario 2 seeds match the actual 2025 result."""
    entry = _DIV_DICT["2"]
    assert entry["one_seed"] == "Falkner"
    assert entry["two_seed"] == "H. W. Byers"
    assert entry["three_seed"] == "Potts Camp"
    assert entry["four_seed"] == "Ashland"


def test_div_dict_scenario3_seeds():
    """Scenario 3 seeds: Potts Camp #1, Falkner #2, Ashland #3, H. W. Byers #4."""
    entry = _DIV_DICT["3"]
    assert entry["one_seed"] == "Potts Camp"
    assert entry["two_seed"] == "Falkner"
    assert entry["three_seed"] == "Ashland"
    assert entry["four_seed"] == "H. W. Byers"


def test_div_dict_scenario1c_seeds():
    """Scenario 1c: PC 12+ AND HWB 12+ → Falkner #1, Potts Camp #2 (Falkner PD advantage)."""
    entry = _DIV_DICT["1c"]
    assert entry["one_seed"] == "Falkner"
    assert entry["two_seed"] == "Potts Camp"


def test_div_dict_ashland_always_bottom_two():
    """Ashland is always seed 3 or 4 — never in the top two."""
    for key, entry in _DIV_DICT.items():
        assert entry["one_seed"] != "Ashland", f"key {key!r}: Ashland should not be #1"
        assert entry["two_seed"] != "Ashland", f"key {key!r}: Ashland should not be #2"


def test_div_dict_hwb_never_seed1():
    """H. W. Byers never finishes #1 — they always lose to Falkner in the pre-cutoff games."""
    for key, entry in _DIV_DICT.items():
        assert entry["one_seed"] != "H. W. Byers", f"key {key!r}: H. W. Byers should not be #1"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_no_eliminated_key():
    """No team has an 'eliminated' key — all four always make the playoffs."""
    for team, entry in _TEAM_DICT.items():
        assert "eliminated" not in entry, f"{team!r} should not have 'eliminated' key"


def test_team_dict_entry_shape():
    """Every entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, f"{team!r} key {key!r} has wrong shape"


def test_team_dict_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None


def test_team_dict_falkner_odds():
    """Falkner: 73.1% to be #1, 26.9% to be #2."""
    assert _TEAM_DICT["Falkner"][1]["odds"] == pytest.approx(421 / 576)
    assert _TEAM_DICT["Falkner"][2]["odds"] == pytest.approx(155 / 576)


def test_team_dict_hwb_odds():
    """H. W. Byers: 70.8% #2, 2.1% #3, 27.1% #4."""
    assert _TEAM_DICT["H. W. Byers"][2]["odds"] == pytest.approx(34 / 48)
    assert _TEAM_DICT["H. W. Byers"][3]["odds"] == pytest.approx(1 / 48)
    assert _TEAM_DICT["H. W. Byers"][4]["odds"] == pytest.approx(13 / 48)


def test_team_dict_potts_camp_odds():
    """Potts Camp: 26.9% #1, 2.3% #2, 70.8% #3."""
    assert _TEAM_DICT["Potts Camp"][1]["odds"] == pytest.approx(155 / 576)
    assert _TEAM_DICT["Potts Camp"][2]["odds"] == pytest.approx(13 / 576)
    assert _TEAM_DICT["Potts Camp"][3]["odds"] == pytest.approx(17 / 24)


def test_team_dict_ashland_odds():
    """Ashland: 27.1% #3, 72.9% #4."""
    assert _TEAM_DICT["Ashland"][3]["odds"] == pytest.approx(13 / 48)
    assert _TEAM_DICT["Ashland"][4]["odds"] == pytest.approx(35 / 48)


def test_team_dict_odds_sum_to_one():
    """For each team, odds across all seeds sum to 1.0."""
    for team, team_entry in _TEAM_DICT.items():
        total = sum(val["odds"] for val in team_entry.values())
        assert total == pytest.approx(1.0), f"{team!r} odds sum to {total}, expected 1.0"


def test_team_dict_falkner_seed1_scenarios():
    """Falkner's #1 seed has 3 scenario strings (matching 3 atoms)."""
    assert len(_TEAM_DICT["Falkner"][1]["scenarios"]) == 3


def test_team_dict_hwb_seed2_scenarios():
    """H. W. Byers #2 has 3 scenario strings."""
    assert len(_TEAM_DICT["H. W. Byers"][2]["scenarios"]) == 3


def test_team_dict_hwb_seed3_one_scenario():
    """H. W. Byers #3 has exactly 1 scenario string (narrow path)."""
    assert len(_TEAM_DICT["H. W. Byers"][3]["scenarios"]) == 1


def test_team_dict_potts_camp_seed2_two_scenarios():
    """Potts Camp #2 has 2 scenario strings."""
    assert len(_TEAM_DICT["Potts Camp"][2]["scenarios"]) == 2


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Falkner", FALKNER_EXPECTED),
        ("H. W. Byers", HWB_EXPECTED),
        ("Potts Camp", POTTS_CAMP_EXPECTED),
        ("Ashland", ASHLAND_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected margin-sensitive condition strings."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


@pytest.mark.parametrize(
    "team,seeds",
    [
        ("Falkner", [1, 2]),
        ("H. W. Byers", [2, 3, 4]),
        ("Potts Camp", [1, 2, 3]),
        ("Ashland", [3, 4]),
    ],
)
def test_render_team_scenarios_without_odds(team, seeds):
    """render_team_scenarios without odds produces '#N seed if:' blocks with no percentages."""
    result = render_team_scenarios(team, _ATOMS)
    for seed in seeds:
        assert f"#{seed} seed if:" in result, f"{team!r}: expected '#{seed} seed if:' in output without odds"
    assert "%" not in result, f"{team!r}: percentage should not appear when odds not supplied"
