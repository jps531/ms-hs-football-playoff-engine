"""Scenario output tests for Region 8-2A (2025 season, pre-final-week).

Region 8-2A exercises several code paths not present in the cleanest cases:

  - **Five-team region** — one team is always eliminated regardless of results;
    only four playoff seeds are available.
  - **Multiple scenarios** — 4 distinct seeding outcomes (keyed "1", "2", "3", "4");
    no margin-sensitive sub-scenarios (no 3-way tiebreakers involving PD).
  - **Dominant mid-table pair** — North Forrest (3-1 entering final week) and
    Collins (2-1) occupy different upper slots depending on the EM/Collins game:
      North Forrest is always #1 or #2; Collins is always #2 or #3.
  - **Wide-ranging team** — East Marion can finish anywhere from #1 to #4
    depending on both games.
  - **Elimination determined solely by SH/PC game** — whoever wins between
    Perry Central and Sacred Heart takes the last playoff spot; the loser is
    eliminated regardless of what East Marion and Collins do.

Remaining games (2, cutoff 2025-10-24):
  Collins vs East Marion  — East Marion won 30-14 (actual, scenario 3)
  Perry Central vs Sacred Heart — Perry Central won 20-3 (actual, scenario 3)

Known 2025 seeds: East Marion / North Forrest / Collins / Perry Central
Eliminated: Sacred Heart

Code paths exercised:
  - build_scenario_atoms       — EM has three seed entries (1, 3, 4) because it
                                  can land anywhere in the top 4; PC and SH each
                                  have an "eliminated" entry (seed 5)
  - enumerate_division_scenarios — exactly 4 scenarios, numbered 1–4, no sub-labels
  - division_scenarios_as_dict  — 4 keys; each entry has exactly one eliminated team
  - team_scenarios_as_dict      — NF and Collins always have two 50/50 odds entries;
                                   EM has three entries; PC/SH have an "eliminated" key
  - render_team_scenarios       — PC and SH have "Eliminated if:" block in output
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

_FIXTURE = REGION_RESULTS_2025[(2, 8)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Collins, East Marion, North Forrest, Perry Central, Sacred Heart
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining: RemainingGame('Collins', 'East Marion'), RemainingGame('Perry Central', 'Sacred Heart')

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

COLLINS_EXPECTED = """\
Collins

#2 seed if: (50.0%)
1. Collins beats East Marion

#3 seed if: (50.0%)
1. East Marion beats Collins"""

EAST_MARION_EXPECTED = """\
East Marion

#1 seed if: (50.0%)
1. East Marion beats Collins

#3 seed if: (25.0%)
1. Collins beats East Marion AND Sacred Heart beats Perry Central

#4 seed if: (25.0%)
1. Collins beats East Marion AND Perry Central beats Sacred Heart"""

NORTH_FORREST_EXPECTED = """\
North Forrest

#1 seed if: (50.0%)
1. Collins beats East Marion

#2 seed if: (50.0%)
1. East Marion beats Collins"""

PERRY_CENTRAL_EXPECTED = """\
Perry Central

#3 seed if: (25.0%)
1. Collins beats East Marion AND Perry Central beats Sacred Heart

#4 seed if: (25.0%)
1. East Marion beats Collins AND Perry Central beats Sacred Heart

Eliminated if: (50.0%)
1. Sacred Heart beats Perry Central"""

SACRED_HEART_EXPECTED = """\
Sacred Heart

#4 seed if: (50.0%)
1. Sacred Heart beats Perry Central

Eliminated if: (50.0%)
1. Perry Central beats Sacred Heart"""

# ---------------------------------------------------------------------------
# build_scenario_atoms
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_nf_and_collins_two_seeds():
    """North Forrest and Collins each have exactly two seed entries."""
    assert len(_ATOMS["North Forrest"]) == 2
    assert len(_ATOMS["Collins"]) == 2


def test_atoms_east_marion_three_seeds():
    """East Marion has three possible seed entries (1, 3, 4)."""
    assert set(_ATOMS["East Marion"].keys()) == {1, 3, 4}


def test_atoms_nf_correct_seed_keys():
    """North Forrest can be #1 or #2."""
    assert set(_ATOMS["North Forrest"].keys()) == {1, 2}


def test_atoms_collins_correct_seed_keys():
    """Collins can be #2 or #3."""
    assert set(_ATOMS["Collins"].keys()) == {2, 3}


def test_atoms_pc_has_eliminated_entry():
    """Perry Central has a seed=5 entry representing elimination."""
    assert 5 in _ATOMS["Perry Central"]


def test_atoms_sh_has_eliminated_entry():
    """Sacred Heart has a seed=5 entry representing elimination."""
    assert 5 in _ATOMS["Sacred Heart"]


def test_atoms_no_margin_restrictions():
    """All GameResults in all atoms are unconstrained (min_margin=1, max_margin=None)."""
    for team, seed_map in _ATOMS.items():
        for seed, atoms in seed_map.items():
            for atom in atoms:
                for cond in atom:
                    if isinstance(cond, GameResult):
                        assert cond.min_margin == 1, (
                            f"{team!r} seed {seed}: expected min_margin=1, got {cond.min_margin}"
                        )
                        assert cond.max_margin is None, (
                            f"{team!r} seed {seed}: expected max_margin=None, got {cond.max_margin}"
                        )


def test_atoms_nf_seed1_requires_collins_beats_em():
    """North Forrest #1 seed requires Collins to beat East Marion."""
    gr = _ATOMS["North Forrest"][1][0][0]
    assert gr.winner == "Collins"
    assert gr.loser == "East Marion"


def test_atoms_nf_seed2_requires_em_beats_collins():
    """North Forrest #2 seed requires East Marion to beat Collins."""
    gr = _ATOMS["North Forrest"][2][0][0]
    assert gr.winner == "East Marion"
    assert gr.loser == "Collins"


def test_atoms_collins_seed2_requires_collins_beats_em():
    """Collins #2 seed requires Collins to beat East Marion."""
    gr = _ATOMS["Collins"][2][0][0]
    assert gr.winner == "Collins"
    assert gr.loser == "East Marion"


def test_atoms_collins_seed3_requires_em_beats_collins():
    """Collins #3 seed requires East Marion to beat Collins."""
    gr = _ATOMS["Collins"][3][0][0]
    assert gr.winner == "East Marion"
    assert gr.loser == "Collins"


def test_atoms_em_seed1_single_condition():
    """East Marion #1 atom is a single condition: EM beats Collins."""
    atoms = _ATOMS["East Marion"][1]
    assert len(atoms) == 1
    assert len(atoms[0]) == 1
    gr = atoms[0][0]
    assert gr.winner == "East Marion"
    assert gr.loser == "Collins"


def test_atoms_em_seed3_two_conditions():
    """East Marion #3 atom has two conditions (both games required): Collins beats EM AND SH beats PC."""
    atoms = _ATOMS["East Marion"][3]
    assert len(atoms) == 1
    assert len(atoms[0]) == 2
    winners = {c.winner for c in atoms[0]}
    assert "Collins" in winners
    assert "Sacred Heart" in winners


def test_atoms_em_seed4_two_conditions():
    """East Marion #4 atom has two conditions: Collins beats EM AND PC beats SH."""
    atoms = _ATOMS["East Marion"][4]
    assert len(atoms) == 1
    assert len(atoms[0]) == 2
    winners = {c.winner for c in atoms[0]}
    assert "Collins" in winners
    assert "Perry Central" in winners


def test_atoms_nf_collins_game_independent_of_sh_pc():
    """NF and Collins seed atoms reference only the Collins/EM game (independent of SH/PC game)."""
    for team in ("North Forrest", "Collins"):
        for seed, atoms in _ATOMS[team].items():
            assert len(atoms[0]) == 1, f"{team!r} seed {seed} should have exactly 1 condition"
            gr = atoms[0][0]
            assert {gr.winner, gr.loser} == {"Collins", "East Marion"}, (
                f"{team!r} seed {seed} references wrong game: {gr}"
            )


def test_atoms_sh_seed4_single_condition():
    """Sacred Heart #4 requires SH to beat PC."""
    gr = _ATOMS["Sacred Heart"][4][0][0]
    assert gr.winner == "Sacred Heart"
    assert gr.loser == "Perry Central"


def test_atoms_sh_eliminated_single_condition():
    """Sacred Heart eliminated (seed 5) requires PC to beat SH."""
    gr = _ATOMS["Sacred Heart"][5][0][0]
    assert gr.winner == "Perry Central"
    assert gr.loser == "Sacred Heart"


# ---------------------------------------------------------------------------
# enumerate_division_scenarios
# ---------------------------------------------------------------------------


def test_scenario_count():
    """All four outcome combinations produce exactly 4 distinct scenarios."""
    assert len(_SCENARIOS) == 4


def test_scenario_shape():
    """Every scenario has the required keys."""
    required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom", "tiebreaker_groups", "coinflip_groups"}
    for sc in _SCENARIOS:
        assert set(sc.keys()) == required


def test_scenario_nums_sequential():
    """Scenarios are numbered 1 through 4."""
    nums = sorted(sc["scenario_num"] for sc in _SCENARIOS)
    assert nums == [1, 2, 3, 4]


def test_scenario_no_sub_labels():
    """No scenario has a sub-label — no margin-sensitive tiebreaker splits."""
    for sc in _SCENARIOS:
        assert sc["sub_label"] == "", (
            f"scenario {sc['scenario_num']} has unexpected sub_label {sc['sub_label']!r}"
        )


def test_scenario_seedings_five_teams():
    """Every scenario seeding contains all 5 teams (with the 5th being eliminated)."""
    for sc in _SCENARIOS:
        assert len(sc["seeding"]) == 5, (
            f"scenario {sc['scenario_num']} seeding has {len(sc['seeding'])} teams, expected 5"
        )
        assert set(sc["seeding"]) == set(_TEAMS), (
            f"scenario {sc['scenario_num']} seeding missing teams"
        )


def test_scenario_seedings_cover_all_combos():
    """The four scenarios cover all four possible seeding combinations."""
    seedings = {sc["seeding"] for sc in _SCENARIOS}
    expected = {
        ("East Marion",   "North Forrest", "Collins",       "Sacred Heart",   "Perry Central"),
        ("North Forrest", "Collins",       "East Marion",   "Sacred Heart",   "Perry Central"),
        ("East Marion",   "North Forrest", "Collins",       "Perry Central",  "Sacred Heart"),
        ("North Forrest", "Collins",       "Perry Central", "East Marion",    "Sacred Heart"),
    }
    assert seedings == expected


def test_scenario_always_one_eliminated():
    """Exactly one team is in position 5 (eliminated) in every scenario."""
    for sc in _SCENARIOS:
        assert len(sc["seeding"]) == 5


def test_scenario_actual_result_present():
    """Scenario 3 (EM beats Collins AND PC beats SH → actual 2025 result) is among the seedings."""
    seedings = {sc["seeding"] for sc in _SCENARIOS}
    assert ("East Marion", "North Forrest", "Collins", "Perry Central", "Sacred Heart") in seedings


def test_scenario_game_winners_two_games():
    """Every scenario specifies exactly two game winners."""
    for sc in _SCENARIOS:
        assert len(sc["game_winners"]) == 2, (
            f"scenario {sc['scenario_num']} has {len(sc['game_winners'])} game_winners, expected 2"
        )


def test_all_conditions_atom_none():
    """No scenario has a conditions_atom — no margin-sensitive sub-scenarios exist."""
    for sc in _SCENARIOS:
        assert sc["conditions_atom"] is None, (
            f"scenario {sc['scenario_num']}{sc['sub_label']} unexpectedly has conditions_atom"
        )


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_four_keys():
    """Dict has exactly four keys: '1', '2', '3', '4'."""
    assert set(_DIV_DICT.keys()) == {"1", "2", "3", "4"}


def test_div_dict_entry_shape():
    """Each entry has exactly the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"key {key!r} has unexpected shape"


def test_div_dict_no_empty_titles():
    """Every scenario has a non-empty title."""
    for key, entry in _DIV_DICT.items():
        assert entry["title"] != "", f"key {key!r} has empty title"


def test_div_dict_titles_contain_and():
    """Each title is a compound condition joined by AND."""
    for key, entry in _DIV_DICT.items():
        assert "AND" in entry["title"], f"key {key!r} title missing AND: {entry['title']!r}"


def test_div_dict_always_one_eliminated():
    """Every scenario has exactly one eliminated team."""
    for key, entry in _DIV_DICT.items():
        assert len(entry["eliminated"]) == 1, (
            f"key {key!r} has {len(entry['eliminated'])} eliminated teams, expected 1"
        )


def test_div_dict_pc_or_sh_always_eliminated():
    """The eliminated team is always Perry Central or Sacred Heart."""
    for key, entry in _DIV_DICT.items():
        assert entry["eliminated"][0] in {"Perry Central", "Sacred Heart"}, (
            f"key {key!r} unexpected eliminated team: {entry['eliminated'][0]!r}"
        )


def test_div_dict_nf_always_top_two():
    """North Forrest is always #1 or #2."""
    for key, entry in _DIV_DICT.items():
        assert entry["one_seed"] == "North Forrest" or entry["two_seed"] == "North Forrest", (
            f"key {key!r}: North Forrest not in top 2"
        )


def test_div_dict_collins_always_two_or_three():
    """Collins is always #2 or #3."""
    for key, entry in _DIV_DICT.items():
        assert entry["two_seed"] == "Collins" or entry["three_seed"] == "Collins", (
            f"key {key!r}: Collins not in seeds 2 or 3"
        )


def test_div_dict_nf_and_collins_swap_together():
    """NF is #1 iff Collins is #2 (they always swap together)."""
    for key, entry in _DIV_DICT.items():
        nf_is_1 = entry["one_seed"] == "North Forrest"
        col_is_2 = entry["two_seed"] == "Collins"
        assert nf_is_1 == col_is_2, (
            f"key {key!r}: NF and Collins swapped unexpectedly"
        )


def test_div_dict_scenario1_title():
    """Scenario 1: EM beats Collins AND SH beats PC."""
    assert _DIV_DICT["1"]["title"] == "East Marion beats Collins AND Sacred Heart beats Perry Central"


def test_div_dict_scenario2_title():
    """Scenario 2: Collins beats EM AND SH beats PC."""
    assert _DIV_DICT["2"]["title"] == "Collins beats East Marion AND Sacred Heart beats Perry Central"


def test_div_dict_scenario3_title():
    """Scenario 3: EM beats Collins AND PC beats SH (actual 2025 result)."""
    assert _DIV_DICT["3"]["title"] == "East Marion beats Collins AND Perry Central beats Sacred Heart"


def test_div_dict_scenario4_title():
    """Scenario 4: Collins beats EM AND PC beats SH."""
    assert _DIV_DICT["4"]["title"] == "Collins beats East Marion AND Perry Central beats Sacred Heart"


def test_div_dict_scenario3_seeds():
    """Scenario 3 matches the actual 2025 seeds."""
    entry = _DIV_DICT["3"]
    assert entry["one_seed"] == "East Marion"
    assert entry["two_seed"] == "North Forrest"
    assert entry["three_seed"] == "Collins"
    assert entry["four_seed"] == "Perry Central"
    assert entry["eliminated"] == ["Sacred Heart"]


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_nf_two_seeds_no_eliminated():
    """North Forrest has exactly two seed entries and no 'eliminated' key."""
    entry = _TEAM_DICT["North Forrest"]
    assert "eliminated" not in entry
    assert set(entry.keys()) == {1, 2}


def test_team_dict_collins_two_seeds_no_eliminated():
    """Collins has exactly two seed entries and no 'eliminated' key."""
    entry = _TEAM_DICT["Collins"]
    assert "eliminated" not in entry
    assert set(entry.keys()) == {2, 3}


def test_team_dict_em_three_seeds_no_eliminated():
    """East Marion has three seed entries (1, 3, 4) and no 'eliminated' key."""
    entry = _TEAM_DICT["East Marion"]
    assert "eliminated" not in entry
    assert set(entry.keys()) == {1, 3, 4}


def test_team_dict_pc_has_eliminated_key():
    """Perry Central has an 'eliminated' key alongside seed entries."""
    assert "eliminated" in _TEAM_DICT["Perry Central"]


def test_team_dict_sh_has_eliminated_key():
    """Sacred Heart has an 'eliminated' key alongside seed entries."""
    assert "eliminated" in _TEAM_DICT["Sacred Heart"]


def test_team_dict_entry_shape():
    """Every seed/eliminated entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, (
                f"{team!r} key {key!r} has wrong shape"
            )


def test_team_dict_nf_50_50_odds():
    """North Forrest has odds=0.5 for both seed 1 and seed 2."""
    for seed in (1, 2):
        assert _TEAM_DICT["North Forrest"][seed]["odds"] == pytest.approx(0.5)


def test_team_dict_collins_50_50_odds():
    """Collins has odds=0.5 for both seed 2 and seed 3."""
    for seed in (2, 3):
        assert _TEAM_DICT["Collins"][seed]["odds"] == pytest.approx(0.5)


def test_team_dict_em_seed1_odds():
    """East Marion has 50% odds for #1 (EM beats Collins, any SH/PC result)."""
    assert _TEAM_DICT["East Marion"][1]["odds"] == pytest.approx(0.5)


def test_team_dict_em_seed3_odds():
    """East Marion has 25% odds for #3 (Collins beats EM AND SH beats PC)."""
    assert _TEAM_DICT["East Marion"][3]["odds"] == pytest.approx(0.25)


def test_team_dict_em_seed4_odds():
    """East Marion has 25% odds for #4 (Collins beats EM AND PC beats SH)."""
    assert _TEAM_DICT["East Marion"][4]["odds"] == pytest.approx(0.25)


def test_team_dict_pc_odds():
    """Perry Central: 25% for #3, 25% for #4, 50% eliminated."""
    assert _TEAM_DICT["Perry Central"][3]["odds"] == pytest.approx(0.25)
    assert _TEAM_DICT["Perry Central"][4]["odds"] == pytest.approx(0.25)
    assert _TEAM_DICT["Perry Central"]["eliminated"]["odds"] == pytest.approx(0.5)


def test_team_dict_sh_odds():
    """Sacred Heart: 50% for #4, 50% eliminated."""
    assert _TEAM_DICT["Sacred Heart"][4]["odds"] == pytest.approx(0.5)
    assert _TEAM_DICT["Sacred Heart"]["eliminated"]["odds"] == pytest.approx(0.5)


def test_team_dict_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None, (
                f"{team!r} key {key!r}: expected weighted_odds=None"
            )


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Collins",       COLLINS_EXPECTED),
        ("East Marion",   EAST_MARION_EXPECTED),
        ("North Forrest", NORTH_FORREST_EXPECTED),
        ("Perry Central", PERRY_CENTRAL_EXPECTED),
        ("Sacred Heart",  SACRED_HEART_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected condition strings."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


@pytest.mark.parametrize(
    "team,seeds",
    [
        ("Collins",       [2, 3]),
        ("East Marion",   [1, 3, 4]),
        ("North Forrest", [1, 2]),
        ("Perry Central", [3, 4]),
        ("Sacred Heart",  [4]),
    ],
)
def test_render_team_scenarios_without_odds(team, seeds):
    """render_team_scenarios without odds produces '#N seed if:' blocks with no percentages."""
    result = render_team_scenarios(team, _ATOMS)
    for seed in seeds:
        assert f"#{seed} seed if:" in result, (
            f"{team!r}: expected '#{seed} seed if:' in output without odds"
        )
    assert "%" not in result, f"{team!r}: percentage should not appear when odds not supplied"


def test_render_pc_eliminated_block():
    """Perry Central's rendered output includes an 'Eliminated if:' block."""
    result = render_team_scenarios("Perry Central", _ATOMS, odds=_ODDS)
    assert "Eliminated if:" in result


def test_render_sh_eliminated_block():
    """Sacred Heart's rendered output includes an 'Eliminated if:' block."""
    result = render_team_scenarios("Sacred Heart", _ATOMS, odds=_ODDS)
    assert "Eliminated if:" in result


def test_render_nf_no_eliminated_block():
    """North Forrest's rendered output never has an 'Eliminated if:' block."""
    result = render_team_scenarios("North Forrest", _ATOMS, odds=_ODDS)
    assert "Eliminated" not in result


def test_render_em_no_eliminated_block():
    """East Marion's rendered output never has an 'Eliminated if:' block."""
    result = render_team_scenarios("East Marion", _ATOMS, odds=_ODDS)
    assert "Eliminated" not in result
