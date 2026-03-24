"""Scenario output tests for Region 5-1A (2025 season, pre-final-week).

Region 5-1A is a richly margin-sensitive case with 6 teams, 3 remaining games,
and 14 distinct scenario outcomes (scenarios 3 and 6 each split into 4 sub-labels).

Teams (alphabetical): Ethel, Leake County, McAdams, Nanih Waiya, Noxapater, Sebastopol
Remaining games (cutoff 2025-10-24):
  Ethel vs Sebastopol  — Ethel beat Sebastopol 32-12 (actual, scenario 4)
  Leake County vs Noxapater — Leake County beat Noxapater 30-8 (actual)
  McAdams vs Nanih Waiya — Nanih Waiya beat McAdams 42-12 (actual)

Known 2025 seeds: Nanih Waiya / Leake County / Ethel / Noxapater
Eliminated: McAdams, Sebastopol

Code paths exercised:
  - build_scenario_atoms       — multi-seed atoms for 4 teams; unconditional for McAdams
  - enumerate_division_scenarios — 14 scenarios; groups 3 and 6 have 4 margin-sensitive
                                   sub-labels (a/b/c/d) each; group 2 and 5 have 2 (a/b)
  - division_scenarios_as_dict  — 14 keys; eliminated list varies across scenarios
  - team_scenarios_as_dict      — non-trivial odds (fractional); 5 of 6 teams have
                                   more than one possible outcome
  - render_team_scenarios       — margin-qualified condition strings; "Eliminated if:" block
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

_FIXTURE = REGION_RESULTS_2025[(1, 5)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
# alphabetical: Ethel, Leake County, McAdams, Nanih Waiya, Noxapater, Sebastopol
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]
# Remaining order: Ethel/Sebastopol, Leake County/Noxapater, McAdams/Nanih Waiya

_ATOMS = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
_SCENARIOS = enumerate_division_scenarios(_TEAMS, _COMPLETED, _REMAINING)

_SR = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
_ODDS = determine_odds(_TEAMS, _SR.first_counts, _SR.second_counts, _SR.third_counts, _SR.fourth_counts, _SR.denom)

_DIV_DICT = division_scenarios_as_dict(_SCENARIOS)
_TEAM_DICT = team_scenarios_as_dict(_ATOMS, odds=_ODDS)

# ---------------------------------------------------------------------------
# Expected human-readable strings
# ---------------------------------------------------------------------------

NANIH_WAIYA_EXPECTED = "Nanih Waiya\n\nClinched #1 seed. (100.0%)"
MCADAMS_EXPECTED = "McAdams\n\nEliminated. (100.0%)"

LEAKE_COUNTY_EXPECTED = """\
Leake County

#2 seed if: (64.6%)
1. Leake County beats Noxapater
2. Ethel beats Sebastopol AND Noxapater beats Leake County by 1\u20137

#3 seed if: (35.4%)
1. Sebastopol beats Ethel AND Noxapater beats Leake County
2. Noxapater beats Leake County by 8 or more"""

NOXAPATER_EXPECTED = """\
Noxapater

#2 seed if: (35.4%)
1. Sebastopol beats Ethel AND Noxapater beats Leake County
2. Noxapater beats Leake County by 8 or more

#3 seed if: (27.1%)
1. Ethel beats Sebastopol AND Noxapater beats Leake County by 1\u20137
2. Sebastopol beats Ethel by 3\u20138 AND Leake County beats Noxapater

#4 seed if: (37.5%)
1. Ethel beats Sebastopol AND Leake County beats Noxapater
2. Sebastopol beats Ethel by 1\u20132 AND Leake County beats Noxapater
3. Sebastopol beats Ethel by 9 or more AND Leake County beats Noxapater"""

ETHEL_EXPECTED = """\
Ethel

#3 seed if: (29.2%)
1. Ethel beats Sebastopol AND Leake County beats Noxapater
2. Sebastopol beats Ethel by 1\u20132 AND Leake County beats Noxapater

#4 seed if: (29.2%)
1. Ethel beats Sebastopol AND Noxapater beats Leake County
2. Sebastopol beats Ethel by 3\u20134 AND Leake County beats Noxapater

Eliminated if: (41.7%)
1. Sebastopol beats Ethel AND Noxapater beats Leake County
2. Sebastopol beats Ethel by 5 or more"""

SEBASTOPOL_EXPECTED = """\
Sebastopol

#3 seed if: (8.3%)
1. Sebastopol beats Ethel by 9 or more AND Leake County beats Noxapater

#4 seed if: (33.3%)
1. Sebastopol beats Ethel AND Noxapater beats Leake County
2. Sebastopol beats Ethel by 5\u20138

Eliminated if: (58.3%)
1. Ethel beats Sebastopol
2. Sebastopol beats Ethel by 1\u20134 AND Leake County beats Noxapater"""

# ---------------------------------------------------------------------------
# build_scenario_atoms — seed key structure
# ---------------------------------------------------------------------------


def test_atoms_all_teams_present():
    """Every team in the region appears in the atoms dict."""
    assert set(_ATOMS.keys()) == set(_TEAMS)


def test_atoms_nanih_waiya_seed_keys():
    """Nanih Waiya has only seed 1 — clinched unconditionally."""
    assert set(_ATOMS["Nanih Waiya"].keys()) == {1}


def test_atoms_leake_county_seed_keys():
    """Leake County can finish 2nd or 3rd."""
    assert set(_ATOMS["Leake County"].keys()) == {2, 3}


def test_atoms_mcadams_seed_keys():
    """McAdams is always eliminated (seed 5 = out-of-playoffs slot)."""
    assert set(_ATOMS["McAdams"].keys()) == {5}


def test_atoms_noxapater_seed_keys():
    """Noxapater can finish 2nd, 3rd, or 4th."""
    assert set(_ATOMS["Noxapater"].keys()) == {2, 3, 4}


def test_atoms_ethel_seed_keys():
    """Ethel can finish 3rd, 4th, or be eliminated (seed 5)."""
    assert set(_ATOMS["Ethel"].keys()) == {3, 4, 5}


def test_atoms_sebastopol_seed_keys():
    """Sebastopol can finish 3rd, 4th, or be eliminated (seed 5)."""
    assert set(_ATOMS["Sebastopol"].keys()) == {3, 4, 5}


def test_atoms_mcadams_unconditional():
    """McAdams' elimination is unconditional — atom is [[]]."""
    assert _ATOMS["McAdams"][5] == [[]]


def test_atoms_nanih_waiya_unconditional():
    """After boolean minimisation Nanih Waiya's seed-1 collapses to a single [[]] atom (clinched)."""
    assert _ATOMS["Nanih Waiya"][1] == [[]]


# ---------------------------------------------------------------------------
# enumerate_division_scenarios — count and structure
# ---------------------------------------------------------------------------


def test_scenario_count():
    """14 distinct scenario entries from 8 outcome × margin combinations."""
    assert len(_SCENARIOS) == 14


def test_scenario_keys():
    """Scenario keys are exactly {'1','2a','2b','3a','3b','3c','3d','4','5a','5b','6a','6b','6c','6d'}."""
    keys = {f"{s['scenario_num']}{s['sub_label']}" for s in _SCENARIOS}
    assert keys == {"1", "2a", "2b", "3a", "3b", "3c", "3d", "4", "5a", "5b", "6a", "6b", "6c", "6d"}


def test_scenario_entry_shape():
    """Every scenario dict has the required keys."""
    required = {"scenario_num", "sub_label", "seeding", "game_winners", "conditions_atom"}
    for sc in _SCENARIOS:
        assert set(sc.keys()) == required


def test_nanih_waiya_always_first():
    """Nanih Waiya is the #1 seed in every scenario."""
    for sc in _SCENARIOS:
        assert sc["seeding"][0] == "Nanih Waiya", (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: expected Nanih Waiya at #1"
        )


def test_mcadams_never_in_top4():
    """McAdams never appears in positions 0-3 of any scenario seeding."""
    for sc in _SCENARIOS:
        assert "McAdams" not in sc["seeding"][:4], (
            f"Scenario {sc['scenario_num']}{sc['sub_label']}: McAdams unexpectedly in top 4"
        )


def test_scenario_4_is_actual_result():
    """Scenario 4 (Ethel beats Sebastopol AND Leake County beats Noxapater) matches 2025 final seeds."""
    sc4 = next(s for s in _SCENARIOS if s["scenario_num"] == 4 and s["sub_label"] == "")
    assert sc4["seeding"][:4] == ("Nanih Waiya", "Leake County", "Ethel", "Noxapater")


def test_scenario_1_seeding():
    """Scenario 1 (Sebastopol & Noxapater both upset): Noxapater jumps to #2."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 1)
    assert sc["seeding"][:4] == ("Nanih Waiya", "Noxapater", "Leake County", "Sebastopol")
    assert sc["game_winners"] == [("Sebastopol", "Ethel"), ("Noxapater", "Leake County")]


def test_scenario_2a_2b_same_game_winners():
    """Scenarios 2a and 2b share game_winners (same W/L, different margin on Noxapater win)."""
    sc2a = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    sc2b = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc2a["game_winners"] == sc2b["game_winners"]
    expected_winners = [
        ("Ethel", "Sebastopol"),
        ("Noxapater", "Leake County"),
        ("Nanih Waiya", "McAdams"),
    ]
    assert sc2a["game_winners"] == expected_winners


def test_scenario_2a_seeding():
    """Scenario 2a (Noxapater wins by 8+, Nanih Waiya wins): Leake County holds #2."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    assert sc["seeding"][:4] == ("Nanih Waiya", "Leake County", "Noxapater", "Ethel")


def test_scenario_2b_seeding():
    """Scenario 2b (Noxapater wins by 1-7, Nanih Waiya wins): Noxapater jumps to #2."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    assert sc["seeding"][:4] == ("Nanih Waiya", "Noxapater", "Leake County", "Ethel")


def test_scenario_3_group_same_game_winners():
    """All four 3-group sub-scenarios share the same game_winners."""
    scs = [s for s in _SCENARIOS if s["scenario_num"] == 3]
    assert len(scs) == 4
    assert all(s["game_winners"] == scs[0]["game_winners"] for s in scs)
    expected_winners = [
        ("Sebastopol", "Ethel"),
        ("Leake County", "Noxapater"),
        ("Nanih Waiya", "McAdams"),
    ]
    assert scs[0]["game_winners"] == expected_winners


def test_scenario_3_sub_labels():
    """Group 3 has sub-labels a, b, c, d in that order."""
    scs = sorted([s for s in _SCENARIOS if s["scenario_num"] == 3], key=lambda s: s["sub_label"])
    assert [s["sub_label"] for s in scs] == ["a", "b", "c", "d"]


def test_scenario_3a_seeding():
    """Scenario 3a: Nanih Waiya / Leake County / Ethel / Noxapater."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == "a")
    assert sc["seeding"][:4] == ("Nanih Waiya", "Leake County", "Ethel", "Noxapater")


def test_scenario_3d_seeding():
    """Scenario 3d: Sebastopol earns #3 (largest margin variant)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == "d")
    assert sc["seeding"][:4] == ("Nanih Waiya", "Leake County", "Sebastopol", "Noxapater")


def test_scenario_6_group_has_four_sub_labels():
    """Group 6 (same W/L as group 3 but McAdams beats Nanih Waiya) also has 4 sub-scenarios."""
    scs = [s for s in _SCENARIOS if s["scenario_num"] == 6]
    assert len(scs) == 4
    assert {s["sub_label"] for s in scs} == {"a", "b", "c", "d"}


def test_unconditional_scenario_has_none_conditions():
    """Scenario 4 (no sub-label, W/L fully determines outcome) has conditions_atom=None."""
    sc4 = next(s for s in _SCENARIOS if s["scenario_num"] == 4 and s["sub_label"] == "")
    assert sc4["conditions_atom"] is None


def test_sub_scenarios_have_conditions_atom():
    """All margin-sensitive sub-scenarios have a non-None conditions_atom."""
    for sc in _SCENARIOS:
        if sc["sub_label"] != "":
            assert sc["conditions_atom"] is not None, (
                f"scenario {sc['scenario_num']}{sc['sub_label']}: expected conditions_atom, got None"
            )


def test_scenario_2a_conditions_atom():
    """Scenario 2a: Noxapater beats Leake County by 1–7 (max_margin=8, exclusive upper bound)."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "a")
    nox_gr = next(gr for gr in sc["conditions_atom"] if gr.winner == "Noxapater")
    assert nox_gr.min_margin == 1
    assert nox_gr.max_margin == 8  # exclusive → renders as "by 1–7"


def test_scenario_2b_conditions_atom():
    """Scenario 2b: Noxapater beats Leake County by 8 or more."""
    sc = next(s for s in _SCENARIOS if s["scenario_num"] == 2 and s["sub_label"] == "b")
    nox_gr = next(gr for gr in sc["conditions_atom"] if gr.winner == "Noxapater")
    assert nox_gr.min_margin == 8
    assert nox_gr.max_margin is None


def test_scenario_3_group_conditions_atoms():
    """Scenarios 3a–3d encode the Sebastopol margin range as their conditions_atom key."""
    expected = {"a": (1, 3), "b": (3, 5), "c": (5, 9), "d": (9, None)}
    for sub, (lo, hi) in expected.items():
        sc = next(s for s in _SCENARIOS if s["scenario_num"] == 3 and s["sub_label"] == sub)
        seb_gr = next(gr for gr in sc["conditions_atom"] if gr.winner == "Sebastopol")
        assert seb_gr.min_margin == lo, f"3{sub}: expected min={lo}, got {seb_gr.min_margin}"
        assert seb_gr.max_margin == hi, f"3{sub}: expected max={hi}, got {seb_gr.max_margin}"


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------


def test_div_dict_keys():
    """Dict has 8 keys after deduplication (5a/5b/6a-6d merged with 3a/3b/3c/3d which share conditions+seeding)."""
    assert set(_DIV_DICT.keys()) == {"1", "2a", "2b", "3a", "3b", "3c", "3d", "4"}


def test_div_dict_entry_shape():
    """Every entry has the required keys."""
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in _DIV_DICT.items():
        assert set(entry.keys()) == required, f"scenario {key!r} has wrong shape"


def test_div_dict_scenario_1():
    """Scenario 1: Sebastopol and Noxapater both upset; Ethel and McAdams eliminated."""
    entry = _DIV_DICT["1"]
    assert entry["title"] == "Sebastopol beats Ethel AND Noxapater beats Leake County"
    assert entry["one_seed"] == "Nanih Waiya"
    assert entry["two_seed"] == "Noxapater"
    assert entry["three_seed"] == "Leake County"
    assert entry["four_seed"] == "Sebastopol"
    assert set(entry["eliminated"]) == {"Ethel", "McAdams"}


def test_div_dict_scenario_4():
    """Scenario 4: actual 2025 result; McAdams and Sebastopol eliminated."""
    entry = _DIV_DICT["4"]
    assert entry["title"] == "Ethel beats Sebastopol AND Leake County beats Noxapater"
    assert entry["one_seed"] == "Nanih Waiya"
    assert entry["two_seed"] == "Leake County"
    assert entry["three_seed"] == "Ethel"
    assert entry["four_seed"] == "Noxapater"
    assert set(entry["eliminated"]) == {"Sebastopol", "McAdams"}


def test_div_dict_scenario_2a_2b_distinct_titles():
    """Sub-scenarios 2a and 2b have distinct margin-qualified titles."""
    assert _DIV_DICT["2a"]["title"] == "Ethel beats Sebastopol AND Noxapater beats Leake County by 1\u20137"
    assert _DIV_DICT["2b"]["title"] == "Ethel beats Sebastopol AND Noxapater beats Leake County by 8 or more"


def test_div_dict_scenario_3_group_distinct_titles():
    """All four 3-group sub-scenarios have distinct margin-qualified titles."""
    assert _DIV_DICT["3a"]["title"] == "Sebastopol beats Ethel by 1\u20132 AND Leake County beats Noxapater"
    assert _DIV_DICT["3b"]["title"] == "Sebastopol beats Ethel by 3\u20134 AND Leake County beats Noxapater"
    assert _DIV_DICT["3c"]["title"] == "Sebastopol beats Ethel by 5\u20138 AND Leake County beats Noxapater"
    assert _DIV_DICT["3d"]["title"] == "Sebastopol beats Ethel by 9 or more AND Leake County beats Noxapater"


def test_div_dict_scenario_3d_sebastopol_third():
    """Scenario 3d: Sebastopol earns #3 seed."""
    entry = _DIV_DICT["3d"]
    assert entry["three_seed"] == "Sebastopol"
    assert entry["four_seed"] == "Noxapater"


def test_div_dict_nanih_waiya_always_one_seed():
    """Nanih Waiya is one_seed in every scenario."""
    for key, entry in _DIV_DICT.items():
        assert entry["one_seed"] == "Nanih Waiya", f"scenario {key!r}: expected Nanih Waiya as one_seed"


def test_div_dict_mcadams_always_eliminated():
    """McAdams appears in the eliminated list of every scenario."""
    for key, entry in _DIV_DICT.items():
        assert "McAdams" in entry["eliminated"], f"scenario {key!r}: McAdams not in eliminated"


# ---------------------------------------------------------------------------
# team_scenarios_as_dict (with odds)
# ---------------------------------------------------------------------------


def test_team_dict_all_teams_present():
    """Every team appears as a key."""
    assert set(_TEAM_DICT.keys()) == set(_TEAMS)


def test_team_dict_entry_shape():
    """Every entry has odds, weighted_odds, and scenarios keys."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert set(val.keys()) == {"odds", "weighted_odds", "scenarios"}, f"{team!r} key {key!r} has wrong shape"


def test_team_dict_nanih_waiya_clinched():
    """Nanih Waiya has exactly one seed key (1) with odds=1.0."""
    entry = _TEAM_DICT["Nanih Waiya"]
    assert set(entry.keys()) == {1}
    assert entry[1]["odds"] == pytest.approx(1.0)


def test_team_dict_mcadams_eliminated_only():
    """McAdams has only an 'eliminated' key with empty scenarios list."""
    entry = _TEAM_DICT["McAdams"]
    assert set(entry.keys()) == {"eliminated"}
    assert entry["eliminated"]["scenarios"] == []
    assert entry["eliminated"]["odds"] == pytest.approx(1.0)


def test_team_dict_leake_county_seed_keys():
    """Leake County has seed keys 2 and 3, no 'eliminated'."""
    entry = _TEAM_DICT["Leake County"]
    assert set(entry.keys()) == {2, 3}


def test_team_dict_noxapater_seed_keys():
    """Noxapater has seed keys 2, 3, and 4."""
    entry = _TEAM_DICT["Noxapater"]
    assert set(entry.keys()) == {2, 3, 4}


def test_team_dict_ethel_seed_keys():
    """Ethel has seed keys 3, 4, and 'eliminated'."""
    entry = _TEAM_DICT["Ethel"]
    assert set(entry.keys()) == {3, 4, "eliminated"}


def test_team_dict_sebastopol_seed_keys():
    """Sebastopol has seed keys 3, 4, and 'eliminated'."""
    entry = _TEAM_DICT["Sebastopol"]
    assert set(entry.keys()) == {3, 4, "eliminated"}


def test_team_dict_leake_county_odds():
    """Leake County: p2≈64.6%, p3≈35.4%."""
    lc = _TEAM_DICT["Leake County"]
    assert lc[2]["odds"] == pytest.approx(0.6458333333333334, abs=1e-9)
    assert lc[3]["odds"] == pytest.approx(0.3541666666666667, abs=1e-9)


def test_team_dict_noxapater_odds():
    """Noxapater: p2≈35.4%, p3≈27.1%, p4≈37.5%."""
    nx = _TEAM_DICT["Noxapater"]
    assert nx[2]["odds"] == pytest.approx(0.3541666666666667, abs=1e-9)
    assert nx[3]["odds"] == pytest.approx(0.2708333333333333, abs=1e-9)
    assert nx[4]["odds"] == pytest.approx(0.375, abs=1e-9)


def test_team_dict_noxapater_odds_sum_to_one():
    """Noxapater's seed odds sum to 1.0."""
    nx = _TEAM_DICT["Noxapater"]
    total = sum(val["odds"] for val in nx.values())
    assert total == pytest.approx(1.0, abs=1e-9)


def test_team_dict_ethel_odds():
    """Ethel: p3≈29.2%, p4≈29.2%, eliminated≈41.7%."""
    e = _TEAM_DICT["Ethel"]
    assert e[3]["odds"] == pytest.approx(0.2916666666666667, abs=1e-9)
    assert e[4]["odds"] == pytest.approx(0.2916666666666667, abs=1e-9)
    assert e["eliminated"]["odds"] == pytest.approx(0.4166666666666667, abs=1e-9)


def test_team_dict_sebastopol_odds():
    """Sebastopol: p3≈8.3%, p4≈33.3%, eliminated≈58.3%."""
    s = _TEAM_DICT["Sebastopol"]
    assert s[3]["odds"] == pytest.approx(0.08333333333333333, abs=1e-9)
    assert s[4]["odds"] == pytest.approx(0.3333333333333333, abs=1e-9)
    assert s["eliminated"]["odds"] == pytest.approx(0.5833333333333334, abs=1e-9)


def test_team_dict_all_weighted_odds_none():
    """weighted_odds is None for all entries (no win-probability function supplied)."""
    for team, team_entry in _TEAM_DICT.items():
        for key, val in team_entry.items():
            assert val["weighted_odds"] is None, f"{team!r} key {key!r}: expected weighted_odds=None"


# ---------------------------------------------------------------------------
# render_team_scenarios (with odds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Nanih Waiya", NANIH_WAIYA_EXPECTED),
        ("McAdams", MCADAMS_EXPECTED),
        ("Leake County", LEAKE_COUNTY_EXPECTED),
        ("Noxapater", NOXAPATER_EXPECTED),
        ("Ethel", ETHEL_EXPECTED),
        ("Sebastopol", SEBASTOPOL_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios output matches expected string for each team."""
    result = render_team_scenarios(team, _ATOMS, odds=_ODDS)
    assert result == expected, f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"


def test_render_nanih_waiya_without_odds():
    """Nanih Waiya renders as 'Clinched #1 seed.' (no percentage) without odds."""
    result = render_team_scenarios("Nanih Waiya", _ATOMS)
    assert result == "Nanih Waiya\n\nClinched #1 seed."


def test_render_mcadams_without_odds():
    """McAdams renders as 'Eliminated.' (no percentage) without odds."""
    result = render_team_scenarios("McAdams", _ATOMS)
    assert result == "McAdams\n\nEliminated."
