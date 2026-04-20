"""Unit tests for scenario_renderer using Region 3-7A data."""

import pytest

from backend.helpers.data_classes import (
    CompletedGame,
    GameResult,
    HomeGameCondition,
    HomeGameScenario,
    MarginCondition,
    MatchupEntry,
    RemainingGame,
    RoundHomeScenarios,
    RoundMatchups,
)
from backend.helpers.scenario_renderer import (
    _render_condition,
    _render_condition_label,
    _render_home_scenario_block,
    _render_margin_condition,
    _render_pre_playoff_block,
    _winner_label,
    division_scenarios_as_dict,
    render_pre_playoff_team_home_scenarios,
    render_team_home_scenarios,
    render_team_matchups,
    render_team_scenarios,
    team_home_scenarios_as_dict,
    team_scenarios_as_dict,
)
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    teams_3_7a,
)

# Computed once at module level — reused by all tests to avoid redundant builds.
_ATOMS_3_7A = build_scenario_atoms(
    teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
)
_SCENARIOS_3_7A = enumerate_division_scenarios(
    teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games,
    scenario_atoms=_ATOMS_3_7A,
)
_r_3_7a = determine_scenarios(
    teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
)
_ODDS_3_7A = determine_odds(
    teams_3_7a,
    _r_3_7a.first_counts, _r_3_7a.second_counts,
    _r_3_7a.third_counts, _r_3_7a.fourth_counts,
    _r_3_7a.denom,
)

# ---------------------------------------------------------------------------
# Expected output strings — algorithmic output from build_scenario_atoms
# ---------------------------------------------------------------------------

PETAL_EXPECTED = """\
Petal

#1 seed if:
1. Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less

#2 seed if:
1. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#3 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1"""

PEARL_EXPECTED = """\
Pearl

#1 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#2 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2

Eliminated if:
1. Oak Grove beats Pearl"""

OAK_GROVE_EXPECTED = """\
Oak Grove

#1 seed if:
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#2 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#4 seed if:
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more"""

NORTHWEST_RANKIN_EXPECTED = """\
Northwest Rankin

#1 seed if:
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if:
1. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#4 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
5. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

Eliminated if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin"""

BRANDON_EXPECTED = """\
Brandon

#3 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

#4 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

Eliminated if:
1. Pearl beats Oak Grove AND Northwest Rankin beats Petal"""

MERIDIAN_EXPECTED = """\
Meridian

Eliminated."""


# ---------------------------------------------------------------------------
# Expected output strings — with odds (algorithmic, from determine_scenarios)
# ---------------------------------------------------------------------------

PETAL_WITH_ODDS_EXPECTED = """\
Petal

#1 seed if: (51.0%)
1. Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less

#2 seed if: (14.6%)
1. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#3 seed if: (28.7%)
1. Meridian beats Brandon AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (5.6%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1"""

PEARL_WITH_ODDS_EXPECTED = """\
Pearl

#1 seed if: (3.1%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#2 seed if: (41.7%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#3 seed if: (2.9%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (2.3%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2

Eliminated if: (50.0%)
1. Oak Grove beats Pearl"""

OAK_GROVE_WITH_ODDS_EXPECTED = """\
Oak Grove

#1 seed if: (27.5%)
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#2 seed if: (27.7%)
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (28.8%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#4 seed if: (16.0%)
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more"""

NORTHWEST_RANKIN_WITH_ODDS_EXPECTED = """\
Northwest Rankin

#1 seed if: (18.3%)
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if: (16.1%)
1. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (2.1%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#4 seed if: (38.5%)
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
5. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

Eliminated if: (25.0%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin"""

BRANDON_WITH_ODDS_EXPECTED = """\
Brandon

#3 seed if: (37.5%)
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

#4 seed if: (37.5%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

Eliminated if: (25.0%)
1. Pearl beats Oak Grove AND Northwest Rankin beats Petal"""

MERIDIAN_WITH_ODDS_EXPECTED = """\
Meridian

Eliminated. (100.0%)"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Petal", PETAL_EXPECTED),
        ("Pearl", PEARL_EXPECTED),
        ("Oak Grove", OAK_GROVE_EXPECTED),
        ("Northwest Rankin", NORTHWEST_RANKIN_EXPECTED),
        ("Brandon", BRANDON_EXPECTED),
        ("Meridian", MERIDIAN_EXPECTED),
    ],
)
def test_render_team_scenarios(team, expected):
    """render_team_scenarios output from build_scenario_atoms matches expected string for each team."""
    result = render_team_scenarios(team, _ATOMS_3_7A)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Petal", PETAL_WITH_ODDS_EXPECTED),
        ("Pearl", PEARL_WITH_ODDS_EXPECTED),
        ("Oak Grove", OAK_GROVE_WITH_ODDS_EXPECTED),
        ("Northwest Rankin", NORTHWEST_RANKIN_WITH_ODDS_EXPECTED),
        ("Brandon", BRANDON_WITH_ODDS_EXPECTED),
        ("Meridian", MERIDIAN_WITH_ODDS_EXPECTED),
    ],
)
def test_render_team_scenarios_with_odds(team, expected):
    """render_team_scenarios with odds appends per-seed and elimination probabilities."""
    result = render_team_scenarios(team, _ATOMS_3_7A, odds=_ODDS_3_7A)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------

def _div_dict():
    """Build a ``division_scenarios_as_dict`` result for the Region 3-7A fixture."""
    return division_scenarios_as_dict(_SCENARIOS_3_7A)


def test_division_scenarios_dict_keys():
    """All 17 scenario keys are present (1–3, 4a–4l, 5–6)."""
    d = _div_dict()
    expected_keys = {
        "1", "2", "3",
        "4a", "4b", "4c", "4d", "4e", "4f", "4g", "4h", "4i", "4j", "4k", "4l",
        "5", "6",
    }
    assert set(d.keys()) == expected_keys


def test_division_scenarios_dict_entry_shape():
    """Every entry has exactly the required keys."""
    d = _div_dict()
    required = {"title", "one_seed", "two_seed", "three_seed", "four_seed", "eliminated"}
    for key, entry in d.items():
        assert set(entry.keys()) == required, f"scenario {key!r} missing keys"


def test_division_scenarios_dict_scenario_1():
    """Scenario 1 (simple win conditions, no margins) renders correctly."""
    entry = _div_dict()["1"]
    assert entry["title"] == "Pearl beats Oak Grove AND Petal beats Northwest Rankin"
    assert entry["one_seed"] == "Petal"
    assert entry["two_seed"] == "Pearl"
    assert entry["three_seed"] == "Oak Grove"
    assert entry["four_seed"] == "Brandon"
    assert set(entry["eliminated"]) == {"Northwest Rankin", "Meridian"}


def test_division_scenarios_dict_scenario_3():
    """Scenario 3 (Meridian upset) renders correctly."""
    entry = _div_dict()["3"]
    assert entry["title"] == (
        "Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal"
    )
    assert entry["one_seed"] == "Northwest Rankin"
    assert entry["two_seed"] == "Pearl"
    assert set(entry["eliminated"]) == {"Brandon", "Meridian"}


def test_division_scenarios_dict_scenario_4a_title():
    """Scenario 4a title includes margin conditions.

    After ascending-margin sort, 4a is the smallest-margin sub-scenario:
    p∈[1,4], n∈[1,3], Pearl's margin doesn't exceed NWR's by more than 1.
    """
    entry = _div_dict()["4a"]
    assert entry["title"] == (
        "Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND "
        "Northwest Rankin beats Petal by 1\u20133 AND "
        "Pearl's margin doesn't exceed Northwest Rankin's by more than 1"
    )
    assert entry["one_seed"] == "Oak Grove"
    assert entry["two_seed"] == "Petal"
    assert entry["four_seed"] == "Pearl"
    assert set(entry["eliminated"]) == {"Brandon", "Meridian"}


def test_division_scenarios_dict_scenario_6():
    """Scenario 6 (Brandon wins a seed) has Brandon in the top 4."""
    entry = _div_dict()["6"]
    assert entry["one_seed"] == "Oak Grove"
    assert entry["two_seed"] == "Petal"
    assert entry["three_seed"] == "Brandon"
    assert entry["four_seed"] == "Northwest Rankin"
    assert set(entry["eliminated"]) == {"Pearl", "Meridian"}


# ---------------------------------------------------------------------------
# team_scenarios_as_dict
# ---------------------------------------------------------------------------

def _team_dict(with_odds=False):
    """Build a ``team_scenarios_as_dict`` result for the Region 3-7A fixture."""
    if not with_odds:
        return team_scenarios_as_dict(_ATOMS_3_7A)
    return team_scenarios_as_dict(_ATOMS_3_7A, odds=_ODDS_3_7A)


def test_team_scenarios_dict_all_teams_present():
    """Every team in the region appears as a key."""
    d = _team_dict()
    assert set(d.keys()) == set(teams_3_7a)


def test_team_scenarios_dict_entry_shape():
    """Each seed/eliminated entry has odds, weighted_odds, and scenarios keys."""
    d = _team_dict()
    for team, team_entry in d.items():
        for key, entry in team_entry.items():
            assert set(entry.keys()) == {"odds", "weighted_odds", "scenarios"}, (
                f"{team!r} key {key!r} has wrong shape"
            )


def test_team_scenarios_dict_meridian_fully_eliminated():
    """Meridian (fully eliminated) has only an 'eliminated' key with empty scenarios."""
    entry = _team_dict()["Meridian"]
    assert set(entry.keys()) == {"eliminated"}
    assert entry["eliminated"]["scenarios"] == []
    assert entry["eliminated"]["odds"] is None
    assert entry["eliminated"]["weighted_odds"] is None


def test_team_scenarios_dict_brandon_structure():
    """Brandon has seed 3, seed 4, and 'eliminated' entries."""
    entry = _team_dict()["Brandon"]
    assert set(entry.keys()) == {3, 4, "eliminated"}
    assert len(entry[3]["scenarios"]) == 2
    assert len(entry[4]["scenarios"]) == 2
    assert len(entry["eliminated"]["scenarios"]) == 1
    assert entry["eliminated"]["scenarios"][0] == (
        "Pearl beats Oak Grove AND Northwest Rankin beats Petal"
    )


def test_team_scenarios_dict_petal_no_elimination():
    """Petal has seeds 1–4 but no 'eliminated' key."""
    entry = _team_dict()["Petal"]
    assert set(entry.keys()) == {1, 2, 3, 4}
    assert len(entry[1]["scenarios"]) == 4
    assert entry[1]["scenarios"][0] == "Petal beats Northwest Rankin"


def test_team_scenarios_dict_oak_grove_no_elimination():
    """Oak Grove (clinched playoffs) has seeds 1–4 but no 'eliminated' key."""
    entry = _team_dict()["Oak Grove"]
    assert set(entry.keys()) == {1, 2, 3, 4}


def test_team_scenarios_dict_with_odds_no_weighted():
    """With odds= provided, per-seed odds are floats and weighted_odds is None."""
    d = _team_dict(with_odds=True)
    petal = d["Petal"]
    assert petal[1]["odds"] == pytest.approx(0.510416666666674)
    assert petal[1]["weighted_odds"] is None
    assert petal[2]["odds"] == pytest.approx(0.14583333333333334)
    assert petal[3]["odds"] == pytest.approx(0.28732638888888845)
    assert petal[4]["odds"] == pytest.approx(0.05642361111111103)


def test_team_scenarios_dict_with_odds_eliminated_section():
    """Pearl's 'eliminated' entry carries the correct elimination probability."""
    d = _team_dict(with_odds=True)
    pearl = d["Pearl"]
    assert pearl["eliminated"]["odds"] == pytest.approx(0.5)
    assert pearl["eliminated"]["weighted_odds"] is None
    assert pearl["eliminated"]["scenarios"] == ["Oak Grove beats Pearl"]


def test_team_scenarios_dict_with_odds_fully_eliminated():
    """Meridian's 'eliminated' entry carries elimination odds of 1.0."""
    d = _team_dict(with_odds=True)
    meridian = d["Meridian"]
    assert meridian["eliminated"]["odds"] == pytest.approx(1.0)
    assert meridian["eliminated"]["scenarios"] == []


# ---------------------------------------------------------------------------
# Synthetic coverage tests — private rendering helpers
# ---------------------------------------------------------------------------


class TestWinnerLabel:
    """Synthetic tests for the _winner_label helper (line 32→31 branch coverage)."""

    def test_skips_non_game_result_condition(self):
        """_winner_label iterates past a MarginCondition to find the GameResult (line 32→31)."""
        atom = [
            MarginCondition(add=(("A", "B"),), sub=(), op=">=", threshold=1),
            GameResult("A", "B", 1, None),
        ]
        assert _winner_label(("A", "B"), atom) == "A"


class TestRenderMarginCondition:
    """Synthetic tests for _render_margin_condition edge cases (lines 67, 74, 78–80)."""

    def _atom(self, *pairs):
        """Build a minimal atom with one A-beats-B GameResult per pair."""
        return [GameResult(a, b, 1, None) for a, b in pairs]

    def test_two_add_no_sub_eq(self):
        """len(add)==2, no sub, op=='==' renders 'combined total exactly N' (line 67)."""
        cond = MarginCondition(
            add=(("A", "B"), ("C", "D")), sub=(), op="==", threshold=10
        )
        atom = self._atom(("A", "B"), ("C", "D"))
        result = _render_margin_condition(cond, atom)
        assert result == "A's margin and C's margin combined total exactly 10"

    def test_one_add_one_sub_ge_threshold_zero(self):
        """op='>=' with adjusted t==0 renders 'add is at least as large as sub' (line 67)."""
        cond = MarginCondition(
            add=(("A", "B"),), sub=(("C", "D"),), op=">=", threshold=0
        )
        atom = self._atom(("A", "B"), ("C", "D"))
        result = _render_margin_condition(cond, atom)
        assert result == "A's margin is at least as large as C's"

    def test_one_add_one_sub_le_threshold_zero(self):
        """op='<=' with adjusted t==0 renders 'sub is at least as large as add' (line 74)."""
        cond = MarginCondition(
            add=(("A", "B"),), sub=(("C", "D"),), op="<=", threshold=0
        )
        atom = self._atom(("A", "B"), ("C", "D"))
        result = _render_margin_condition(cond, atom)
        assert result == "C's margin is at least as large as A's"

    def test_fallback_multiple_operands(self):
        """len(add)==2, len(sub)==1 falls back to generic sum expression (lines 78–80)."""
        cond = MarginCondition(
            add=(("A", "B"), ("C", "D")), sub=(("E", "F"),), op=">=", threshold=5
        )
        atom = self._atom(("A", "B"), ("C", "D"), ("E", "F"))
        result = _render_margin_condition(cond, atom)
        assert result == "A's margin + C's margin + \u2212E's margin >= 5"


class TestRenderConditionUnknownType:
    """Synthetic test for _render_condition unknown-type fallback (line 91)."""

    def test_unknown_type_returns_str(self):
        """_render_condition falls back to str() for unrecognised condition types (line 91)."""
        result = _render_condition("mystery_object", [])
        assert result == "mystery_object"


class TestRenderConditionPDRank:
    """Tests for the PDRankCondition branch of _render_condition."""

    def test_rank_1_renders_1st(self):
        """rank=1 renders as '1st in point differential'."""
        from backend.helpers.data_classes import PDRankCondition
        cond = PDRankCondition("Hamilton", 1, ("Hamilton", "Hatley", "Walnut"))
        assert _render_condition(cond, []) == "Hamilton finishes 1st in point differential"

    def test_rank_2_renders_2nd(self):
        """rank=2 renders as '2nd in point differential'."""
        from backend.helpers.data_classes import PDRankCondition
        cond = PDRankCondition("Hatley", 2, ("Hamilton", "Hatley", "Walnut"))
        assert _render_condition(cond, []) == "Hatley finishes 2nd in point differential"

    def test_rank_3_renders_3rd(self):
        """rank=3 renders as '3rd in point differential'."""
        from backend.helpers.data_classes import PDRankCondition
        cond = PDRankCondition("Walnut", 3, ("Hamilton", "Hatley", "Walnut"))
        assert _render_condition(cond, []) == "Walnut finishes 3rd in point differential"

    def test_render_atom_with_pd_rank_condition(self):
        """_render_atom joins a GameResult and PDRankCondition with AND."""
        from backend.helpers.data_classes import PDRankCondition
        from backend.helpers.scenario_renderer import _render_atom
        atom = [
            GameResult("Hamilton", "Baldwyn"),
            PDRankCondition("Hamilton", 1, ("Hamilton", "Hatley", "Walnut")),
        ]
        result = _render_atom(atom)
        assert result == "Hamilton beats Baldwyn AND Hamilton finishes 1st in point differential"


class TestOddsSuffixWeightedPaths:
    """Cover the weighted-only and both-provided branches of _odds_suffix."""

    def _make_odds(self, p1, p2, p3, p4):
        """Build a StandingsOdds fixture from raw seed probabilities."""
        from backend.helpers.data_classes import StandingsOdds
        p = p1 + p2 + p3 + p4
        return StandingsOdds("T", p1, p2, p3, p4, p, p, False, False)

    def test_weighted_only_suffix(self):
        """When only weighted_odds is provided, suffix shows 'XX.X% Weighted'."""
        odds = self._make_odds(0.5, 0.2, 0.2, 0.1)
        atoms = {"T": {1: [[GameResult("T", "X")]]}}
        rendered = render_team_scenarios("T", atoms, weighted_odds={"T": odds})
        assert "50.0% Weighted" in rendered
        assert "\u2013" not in rendered  # no en-dash (no dual display)

    def test_both_odds_suffix(self):
        """When both odds and weighted_odds are provided, suffix shows both values."""
        odds_u = self._make_odds(0.4, 0.2, 0.2, 0.1)
        odds_w = self._make_odds(0.6, 0.2, 0.1, 0.05)
        atoms = {"T": {1: [[GameResult("T", "X")]]}}
        rendered = render_team_scenarios("T", atoms, odds={"T": odds_u}, weighted_odds={"T": odds_w})
        assert "40.0%" in rendered
        assert "60.0% Weighted" in rendered
        assert "\u2013" in rendered  # en-dash separates the two values


# ---------------------------------------------------------------------------
# Synthetic coverage tests — home-game renderers
# ---------------------------------------------------------------------------

_UNCOND_EXPL = HomeGameScenario(conditions=(), explanation="Higher seed")
_UNCOND_NO_EXPL = HomeGameScenario(conditions=(), explanation=None)


def _rhs(will_host=(), will_not_host=()):
    """Build a minimal RoundHomeScenarios with all probability fields as None."""
    return RoundHomeScenarios(
        round_name="First Round",
        will_host=will_host,
        will_not_host=will_not_host,
        p_reach=None,
        p_host_conditional=None,
        p_host_marginal=None,
        p_reach_weighted=None,
        p_host_conditional_weighted=None,
        p_host_marginal_weighted=None,
    )


class TestRenderConditionLabel:
    """Synthetic tests for _render_condition_label seed_required path (lines 347–348)."""

    def test_seed_required_no_team_name(self):
        """kind='seed_required' with no team_name renders region/seed label (lines 347–348)."""
        cond = HomeGameCondition(
            kind="seed_required", round_name=None, region=2, seed=3, team_name=None
        )
        assert _render_condition_label(cond) == "Region 2 #3 Seed finishes as the #3 seed"

    def test_seed_required_with_team_name(self):
        """kind='seed_required' with a team_name uses the name directly (lines 347–348)."""
        cond = HomeGameCondition(
            kind="seed_required", round_name=None, region=2, seed=1, team_name="Oak Grove"
        )
        assert _render_condition_label(cond) == "Oak Grove finishes as the #1 seed"


class TestRenderHomeScenarioBlock:
    """Synthetic tests for _render_home_scenario_block unconditional paths (lines 384–385, 384→378)."""

    def test_unconditional_scenario_with_explanation(self):
        """Unconditional scenario (no conditions) with explanation renders as indented note (lines 384–385)."""
        lines = _render_home_scenario_block((_UNCOND_EXPL,), "TeamA")
        assert lines == ["   [Higher seed]"]

    def test_unconditional_scenario_without_explanation(self):
        """Unconditional scenario (no conditions, no explanation) contributes no lines (line 384→378)."""
        lines = _render_home_scenario_block((_UNCOND_NO_EXPL,), "TeamA")
        assert lines == []


class TestRenderTeamHomeScenarios:
    """Synthetic tests for render_team_home_scenarios unconditional host/not-host paths (lines 463, 479)."""

    def test_unconditional_host_no_explanation(self):
        """Unconditional host with no explanation renders bare header line (line 463)."""
        result = render_team_home_scenarios("TeamA", [_rhs(will_host=(_UNCOND_NO_EXPL,))])
        assert "Will Host First Round:" in result
        assert "[" not in result

    def test_unconditional_not_host_no_explanation(self):
        """Unconditional not-host with no explanation renders bare header line (line 479)."""
        result = render_team_home_scenarios("TeamA", [_rhs(will_not_host=(_UNCOND_NO_EXPL,))])
        assert "Will Not Host First Round:" in result
        assert "[" not in result


class TestTeamHomeScenasAsDict:
    """Synthetic tests for team_home_scenarios_as_dict region-label fallback (line 542)."""

    def test_region_condition_gets_region_label(self):
        """Condition with region but no team_name generates 'Region X #Y Seed' label (line 542)."""
        cond = HomeGameCondition(
            kind="advances", round_name="Quarterfinals", region=3, seed=2, team_name=None
        )
        sc = HomeGameScenario(conditions=(cond,), explanation=None)
        rnd = _rhs(will_host=(sc,))
        result = team_home_scenarios_as_dict("TeamA", [rnd])
        assert result["first_round"]["will_host"][0]["conditions"][0]["team"] == "Region 3 #2 Seed"


class TestRenderTeamMatchups:
    """Synthetic tests for render_team_matchups explanation branch (lines 633→634, 633→635)."""

    def _rnd(self, explanation):
        """Build a RoundMatchups with a single home-matchup entry."""
        entry = MatchupEntry(
            opponent="Pearl",
            opponent_region=3,
            opponent_seed=2,
            home=True,
            p_conditional=0.5,
            p_conditional_weighted=None,
            p_marginal=0.25,
            p_marginal_weighted=None,
            explanation=explanation,
        )
        return RoundMatchups(
            round_name="First Round",
            p_reach=0.5,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
            entries=(entry,),
        )

    def test_entry_with_explanation_appends_bracket(self):
        """MatchupEntry with explanation appends it to the rendered line (line 633→634)."""
        result = render_team_matchups("TeamA", [self._rnd("Region tiebreak")])
        assert "[Region tiebreak]" in result

    def test_entry_without_explanation_omits_bracket(self):
        """MatchupEntry with no explanation renders without a bracket suffix (line 633→635)."""
        result = render_team_matchups("TeamA", [self._rnd(None)])
        assert "[" not in result


# ===========================================================================
# Partial-results peace-of-mind tests — Region 3-7A (2025)
#
# These tests simulate mid-final-week states where some results are known and
# others are not.  All three scenarios use the real 2025 final-week scores.
#
# Real results:
#   Brandon  beat Meridian        40–13  (margin 27)
#   Oak Grove beat Pearl          28–7   (margin 21)
#   Northwest Rankin beat Petal   34–28  (margin  6)
# ===========================================================================

# Convenience: the three final-week completed games
_BRN_MER = CompletedGame("Brandon",          "Meridian", 1, 27, 13, 40)
_OG_PRL  = CompletedGame("Oak Grove",        "Pearl",    1, 21,  7, 28)
_NWR_PET = CompletedGame("Northwest Rankin", "Petal",    1,  6, 28, 34)

# ---------------------------------------------------------------------------
# Partial A: Brandon/Meridian known; OG/Pearl and NWR/Petal still TBD
# ---------------------------------------------------------------------------
# Brandon's win eliminates all Meridian-wins-Brandon scenarios, but the
# margin-sensitive 5-way-tie atoms (which all require Brandon to win) survive
# intact.  Two remaining games, same complex structure as the full 3-game view
# but without any Meridian-wins branch.
# ---------------------------------------------------------------------------

_completed_pa = sorted(
    expected_3_7a_completed_games + [_BRN_MER],
    key=lambda g: (g.a, g.b),
)
_remaining_pa = [
    RemainingGame("Oak Grove", "Pearl"),
    RemainingGame("Northwest Rankin", "Petal"),
]

_atoms_pa  = build_scenario_atoms(teams_3_7a, _completed_pa, _remaining_pa)
_sr_pa     = determine_scenarios(teams_3_7a, _completed_pa, _remaining_pa)
_odds_pa   = determine_odds(
    teams_3_7a,
    _sr_pa.first_counts, _sr_pa.second_counts,
    _sr_pa.third_counts, _sr_pa.fourth_counts,
    _sr_pa.denom,
)

_PARTIAL_A_BRANDON = """\
Brandon

#3 seed if: (50.0%)
1. Oak Grove beats Pearl

#4 seed if: (25.0%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin

Eliminated if: (25.0%)
1. Pearl beats Oak Grove AND Northwest Rankin beats Petal"""

_PARTIAL_A_MERIDIAN = """\
Meridian

Eliminated. (100.0%)"""

_PARTIAL_A_NWR = """\
Northwest Rankin

#1 seed if: (11.6%)
1. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
2. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if: (7.1%)
1. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
2. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
3. Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (4.2%)
1. Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#4 seed if: (52.1%)
1. Oak Grove beats Pearl
2. Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

Eliminated if: (25.0%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin"""

_PARTIAL_A_OAK_GROVE = """\
Oak Grove

#1 seed if: (30.0%)
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#2 seed if: (30.4%)
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (32.6%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
4. Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#4 seed if: (6.9%)
1. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
2. Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more"""

_PARTIAL_A_PEARL = """\
Pearl

#1 seed if: (6.3%)
1. Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#2 seed if: (33.3%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#3 seed if: (5.7%)
1. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (4.7%)
1. Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2

Eliminated if: (50.0%)
1. Oak Grove beats Pearl"""

_PARTIAL_A_PETAL = """\
Petal

#1 seed if: (52.1%)
1. Petal beats Northwest Rankin
2. Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less

#2 seed if: (29.2%)
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#3 seed if: (7.5%)
1. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
2. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (11.3%)
1. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1"""


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Brandon",          _PARTIAL_A_BRANDON),
        ("Meridian",         _PARTIAL_A_MERIDIAN),
        ("Northwest Rankin", _PARTIAL_A_NWR),
        ("Oak Grove",        _PARTIAL_A_OAK_GROVE),
        ("Pearl",            _PARTIAL_A_PEARL),
        ("Petal",            _PARTIAL_A_PETAL),
    ],
)
def test_partial_a_brandon_meridian_known(team, expected):
    """After Brandon beats Meridian, the Meridian-wins branch vanishes but all
    margin-sensitive 5-way-tie scenarios (which require Brandon to win) remain.
    Two games still undecided: OG/Pearl and NWR/Petal."""
    result = render_team_scenarios(team, _atoms_pa, odds=_odds_pa)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# Partial B: Brandon/Meridian AND OG/Pearl known; only NWR/Petal TBD
# ---------------------------------------------------------------------------
# OG beating Pearl eliminates Pearl (2-3 final) and removes every mask-5
# scenario (which required Pearl to beat OG).  The remaining game determines
# only #1/#2 between OG and Petal; Brandon and NWR are clinched at #3/#4
# because Petal's H2H win over OG determines tiebreakers in the NWR/Brandon
# 2-way if Petal beats NWR, and step-2 (record vs OG) locks Petal at #2 over
# NWR and Brandon if NWR beats Petal.
# ---------------------------------------------------------------------------

_completed_pb = sorted(
    expected_3_7a_completed_games + [_BRN_MER, _OG_PRL],
    key=lambda g: (g.a, g.b),
)
_remaining_pb = [RemainingGame("Northwest Rankin", "Petal")]

_atoms_pb  = build_scenario_atoms(teams_3_7a, _completed_pb, _remaining_pb)
_sr_pb     = determine_scenarios(teams_3_7a, _completed_pb, _remaining_pb)
_odds_pb   = determine_odds(
    teams_3_7a,
    _sr_pb.first_counts, _sr_pb.second_counts,
    _sr_pb.third_counts, _sr_pb.fourth_counts,
    _sr_pb.denom,
)

_PARTIAL_B_BRANDON = """\
Brandon

Clinched #3 seed. (100.0%)"""

_PARTIAL_B_MERIDIAN = """\
Meridian

Eliminated. (100.0%)"""

_PARTIAL_B_NWR = """\
Northwest Rankin

Clinched #4 seed. (100.0%)"""

_PARTIAL_B_OAK_GROVE = """\
Oak Grove

#1 seed if: (50.0%)
1. Northwest Rankin beats Petal

#2 seed if: (50.0%)
1. Petal beats Northwest Rankin"""

_PARTIAL_B_PEARL = """\
Pearl

Eliminated. (100.0%)"""

_PARTIAL_B_PETAL = """\
Petal

#1 seed if: (50.0%)
1. Petal beats Northwest Rankin

#2 seed if: (50.0%)
1. Northwest Rankin beats Petal"""


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Brandon",          _PARTIAL_B_BRANDON),
        ("Meridian",         _PARTIAL_B_MERIDIAN),
        ("Northwest Rankin", _PARTIAL_B_NWR),
        ("Oak Grove",        _PARTIAL_B_OAK_GROVE),
        ("Pearl",            _PARTIAL_B_PEARL),
        ("Petal",            _PARTIAL_B_PETAL),
    ],
)
def test_partial_b_brandon_meridian_and_og_pearl_known(team, expected):
    """After Brandon beats Meridian AND OG beats Pearl, all margin-sensitive
    scenarios are gone.  Pearl is eliminated; Brandon and NWR are clinched at
    #3/#4; the sole remaining game (NWR/Petal) decides only #1 vs #2 between
    OG and Petal."""
    result = render_team_scenarios(team, _atoms_pb, odds=_odds_pb)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# Partial C: Brandon/Meridian AND NWR/Petal known; only OG/Pearl TBD
# ---------------------------------------------------------------------------
# NWR beat Petal by 6 (the real result).  With NWR's margin fixed at 6,
# the 5-way-tie tiebreaker becomes a function of Pearl's margin alone, so
# new single-game margin atoms appear on the OG/Pearl game.  This is the
# most interesting partial state: complex structure remains but is now
# one-dimensional rather than two-dimensional.
# ---------------------------------------------------------------------------

_completed_pc = sorted(
    expected_3_7a_completed_games + [_BRN_MER, _NWR_PET],
    key=lambda g: (g.a, g.b),
)
_remaining_pc = [RemainingGame("Oak Grove", "Pearl")]

_atoms_pc  = build_scenario_atoms(teams_3_7a, _completed_pc, _remaining_pc)
_sr_pc     = determine_scenarios(teams_3_7a, _completed_pc, _remaining_pc)
_odds_pc   = determine_odds(
    teams_3_7a,
    _sr_pc.first_counts, _sr_pc.second_counts,
    _sr_pc.third_counts, _sr_pc.fourth_counts,
    _sr_pc.denom,
)

_PARTIAL_C_BRANDON = """\
Brandon

#3 seed if: (50.0%)
1. Oak Grove beats Pearl

Eliminated if: (50.0%)
1. Pearl beats Oak Grove"""

_PARTIAL_C_MERIDIAN = """\
Meridian

Eliminated. (100.0%)"""

_PARTIAL_C_NWR = """\
Northwest Rankin

#1 seed if: (16.7%)
1. Pearl beats Oak Grove by 5\u20138

#2 seed if: (33.3%)
1. Pearl beats Oak Grove by 1\u20134
2. Pearl beats Oak Grove by 9 or more

#4 seed if: (50.0%)
1. Oak Grove beats Pearl"""

_PARTIAL_C_OAK_GROVE = """\
Oak Grove

#1 seed if: (66.7%)
1. Oak Grove beats Pearl
2. Pearl beats Oak Grove by 1\u20134

#2 seed if: (4.2%)
1. Pearl beats Oak Grove by exactly 5

#3 seed if: (8.3%)
1. Pearl beats Oak Grove by 6\u20137

#4 seed if: (20.8%)
1. Pearl beats Oak Grove by 8 or more"""

_PARTIAL_C_PEARL = """\
Pearl

#1 seed if: (16.7%)
1. Pearl beats Oak Grove by 9 or more

#2 seed if: (12.5%)
1. Pearl beats Oak Grove by 6\u20138

#3 seed if: (8.3%)
1. Pearl beats Oak Grove by 4\u20135

#4 seed if: (12.5%)
1. Pearl beats Oak Grove by 1\u20133

Eliminated if: (50.0%)
1. Oak Grove beats Pearl"""

_PARTIAL_C_PETAL = """\
Petal

#2 seed if: (50.0%)
1. Oak Grove beats Pearl

#3 seed if: (33.3%)
1. Pearl beats Oak Grove by 1\u20133
2. Pearl beats Oak Grove by 8 or more

#4 seed if: (16.7%)
1. Pearl beats Oak Grove by 4\u20137"""


@pytest.mark.parametrize(
    "team,expected",
    [
        ("Brandon",          _PARTIAL_C_BRANDON),
        ("Meridian",         _PARTIAL_C_MERIDIAN),
        ("Northwest Rankin", _PARTIAL_C_NWR),
        ("Oak Grove",        _PARTIAL_C_OAK_GROVE),
        ("Pearl",            _PARTIAL_C_PEARL),
        ("Petal",            _PARTIAL_C_PETAL),
    ],
)
def test_partial_c_brandon_meridian_and_nwr_petal_known(team, expected):
    """After Brandon beats Meridian AND NWR beats Petal by 6, the 2-D
    margin space collapses to 1-D: all tiebreaker conditions now depend only
    on Pearl's winning margin vs OG.  The NWR #3 seed disappears (NWR always
    beats Petal in step 2 vs OG), and the remaining game produces new
    single-game margin thresholds driven by the known n=6 boundary."""
    result = render_team_scenarios(team, _atoms_pc, odds=_odds_pc)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# Partial C — cross-validation against full-season ground truth
# ---------------------------------------------------------------------------
# Partial C was computed independently (build_scenario_atoms on 14 completed
# games + 1 remaining).  This class verifies it is consistent with the full-
# season computation (determine_scenarios on all 15 games, remaining=[]).
#
# For each unique seeding outcome in Partial C — determined by Pearl's winning
# margin vs OG — we construct the complete 15-game record with a specific
# OG/Pearl score, run determine_scenarios, and confirm every team's seed.
#
# The 5-way-tie H2H PD formula (n=6 fixed, p=Pearl's margin):
#   OG = 8-p,  Petal = 0,  Pearl = p-4,  NWR = 4,  Brandon = -8
# Boundary crossings: p=4 (OG/NWR tie resolved by OG's H2H win over NWR),
#   p=5 (NWR takes #1 outright), p=6 (Pearl=OG at 2; Pearl wins H2H vs OG),
#   p=8 (NWR=Pearl at 4; NWR wins H2H over Pearl), p=9 (Pearl surpasses NWR).
# ---------------------------------------------------------------------------


def _og_wins_game(margin: int) -> CompletedGame:
    """OG beats Pearl by *margin*."""
    return CompletedGame("Oak Grove", "Pearl", 1, margin, 28 - margin, 28)


def _pearl_wins_game(p: int) -> CompletedGame:
    """Pearl beats OG by *p* (OG scores 21, Pearl scores 21+p)."""
    return CompletedGame("Oak Grove", "Pearl", -1, -p, 21 + p, 21)


def _full_season_seeds(og_pearl: CompletedGame) -> dict[str, int]:
    """Return {team: seed_1_to_4_or_5} for the fully-resolved 15-game season."""
    completed = sorted(
        expected_3_7a_completed_games + [_BRN_MER, _NWR_PET, og_pearl],
        key=lambda g: (g.a, g.b),
    )
    sr = determine_scenarios(teams_3_7a, completed, [])
    odds = determine_odds(
        teams_3_7a,
        sr.first_counts, sr.second_counts, sr.third_counts, sr.fourth_counts,
        sr.denom,
    )
    result = {}
    for team, o in odds.items():
        if abs(o.p1 - 1.0) < 1e-9:
            result[team] = 1
        elif abs(o.p2 - 1.0) < 1e-9:
            result[team] = 2
        elif abs(o.p3 - 1.0) < 1e-9:
            result[team] = 3
        elif abs(o.p4 - 1.0) < 1e-9:
            result[team] = 4
        else:
            result[team] = 5  # eliminated
    return result


@pytest.mark.parametrize(
    "og_pearl_game,expected_seeds",
    [
        # OG wins: not a 5-way tie; Petal beats OG H2H → Petal #2; then
        # Brandon beats NWR H2H → Brandon #3, NWR #4.
        (
            _og_wins_game(21),
            {"Oak Grove": 1, "Petal": 2, "Brandon": 3, "Northwest Rankin": 4,
             "Pearl": 5, "Meridian": 5},
        ),
        # Pearl by 2: OG PD=6, NWR PD=4, Petal=0, Pearl=-2, Brandon=-8 → all unique.
        (
            _pearl_wins_game(2),
            {"Oak Grove": 1, "Northwest Rankin": 2, "Petal": 3, "Pearl": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 3: OG PD=5 > NWR PD=4 > Petal=0 > Pearl=-1 > Brandon=-8.
        (
            _pearl_wins_game(3),
            {"Oak Grove": 1, "Northwest Rankin": 2, "Petal": 3, "Pearl": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 4 (boundary): OG=NWR=4; OG beat NWR H2H → OG #1, NWR #2.
        # Petal=Pearl=0; Pearl beat Petal H2H → Pearl #3, Petal #4.
        (
            _pearl_wins_game(4),
            {"Oak Grove": 1, "Northwest Rankin": 2, "Pearl": 3, "Petal": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 5 (boundary): NWR PD=4 > OG PD=3 → NWR #1 outright.
        (
            _pearl_wins_game(5),
            {"Northwest Rankin": 1, "Oak Grove": 2, "Pearl": 3, "Petal": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 6 (boundary): NWR #1 (PD=4). OG=Pearl=2; Pearl beat OG H2H
        # (in this game) → Pearl #2, OG #3.  Petal #4, Brandon #5.
        (
            _pearl_wins_game(6),
            {"Northwest Rankin": 1, "Pearl": 2, "Oak Grove": 3, "Petal": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 7: NWR PD=4 > Pearl PD=3 > OG PD=1 > Petal=0 > Brandon — all unique.
        (
            _pearl_wins_game(7),
            {"Northwest Rankin": 1, "Pearl": 2, "Oak Grove": 3, "Petal": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 8 (boundary): NWR=Pearl=4; NWR beat Pearl H2H → NWR #1, Pearl #2.
        # OG=Petal=0; Petal beat OG H2H → Petal #3, OG #4.
        (
            _pearl_wins_game(8),
            {"Northwest Rankin": 1, "Pearl": 2, "Petal": 3, "Oak Grove": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 9 (boundary): Pearl PD=5 > NWR PD=4 → Pearl #1 outright.
        (
            _pearl_wins_game(9),
            {"Pearl": 1, "Northwest Rankin": 2, "Petal": 3, "Oak Grove": 4,
             "Brandon": 5, "Meridian": 5},
        ),
        # Pearl by 12 (max): Pearl PD=8 > NWR PD=4 — same outcome category as p=9.
        (
            _pearl_wins_game(12),
            {"Pearl": 1, "Northwest Rankin": 2, "Petal": 3, "Oak Grove": 4,
             "Brandon": 5, "Meridian": 5},
        ),
    ],
    ids=[
        "og_wins_21",
        "pearl_by_2",
        "pearl_by_3",
        "pearl_by_4_boundary",
        "pearl_by_5_boundary",
        "pearl_by_6_boundary",
        "pearl_by_7",
        "pearl_by_8_boundary",
        "pearl_by_9_boundary",
        "pearl_by_12_max",
    ],
)
def test_partial_c_consistent_with_full_season(og_pearl_game, expected_seeds):
    """Full-season seedings (0 remaining games) match what Partial C predicts
    for every unique outcome category, confirming the two independent
    computations — partial atom-building vs. full-season resolution — agree."""
    assert _full_season_seeds(og_pearl_game) == expected_seeds


# ---------------------------------------------------------------------------
# _render_pre_playoff_block edge cases
# ---------------------------------------------------------------------------


class TestRenderPrePlayoffBlockEdgeCases:
    """Cover defensive branches in _render_pre_playoff_block."""

    def test_empty_conditions_with_explanation(self):
        """Scenario with no conditions renders only the bracketed explanation."""
        sc = HomeGameScenario(conditions=(), explanation="Designated home team in bracket")
        lines = _render_pre_playoff_block((sc,), "Team", {})
        assert lines == ["   [Designated home team in bracket]"]

    def test_empty_conditions_without_explanation_produces_no_lines(self):
        """Scenario with no conditions and no explanation is silently skipped."""
        sc = HomeGameScenario(conditions=(), explanation=None)
        lines = _render_pre_playoff_block((sc,), "Team", {})
        assert lines == []

    def test_seed_required_with_no_atoms_for_that_seed(self):
        """seed_required scenario produces no numbered lines when seed_atoms is missing the seed."""
        cond = HomeGameCondition(kind="seed_required", round_name=None, region=None, seed=3, team_name=None)
        sc = HomeGameScenario(conditions=(cond,), explanation=None)
        # seed_atoms has entries for seeds 1 and 2 but not 3 → atoms=[] → loop body skipped
        lines = _render_pre_playoff_block((sc,), "TeamX", {"TeamX": {1: [[]], 2: [[]]}})
        assert lines == []

    def test_non_seed_required_first_condition_uses_fallback_rendering(self):
        """Scenario not starting with seed_required falls back to a single numbered line."""
        cond = HomeGameCondition(kind="advances", round_name="Quarterfinals", region=1, seed=1, team_name="Alpha")
        sc = HomeGameScenario(conditions=(cond,), explanation="Higher seed (#1) hosts")
        lines = _render_pre_playoff_block((sc,), "Team", {})
        assert len(lines) == 2
        assert lines[0].startswith("1. ")
        assert "Alpha" in lines[0]
        assert lines[1] == "   [Higher seed (#1) hosts]"

    def test_non_seed_required_team_substitution_in_fallback(self):
        """'Team advances' / 'Team finishes' substitution works in the fallback path."""
        cond = HomeGameCondition(kind="advances", round_name="QF", region=None, seed=1, team_name=None)
        sc = HomeGameScenario(conditions=(cond,), explanation=None)
        lines = _render_pre_playoff_block((sc,), "Taylorsville", {})
        assert "Taylorsville" in lines[0]

    def test_seed_required_with_atoms_and_no_explanation(self):
        """seed_required scenario with atoms but explanation=None produces numbered lines only.

        Covers the False path of 'if sc.explanation:' inside the atom loop
        (branch 473→468): the loop body executes, but the explanation line is skipped.
        """
        cond = HomeGameCondition(kind="seed_required", round_name=None, region=None, seed=1, team_name=None)
        sc = HomeGameScenario(conditions=(cond,), explanation=None)
        # Provide one minimal atom (a list with a single GameResult-like object is fine
        # for rendering purposes — _render_atom just formats the list).
        from backend.helpers.data_classes import GameResult
        atom = [GameResult("Taylorsville", "Lumberton", 1, None)]
        seed_atoms = {"Taylorsville": {1: [atom]}}
        lines = _render_pre_playoff_block((sc,), "Taylorsville", seed_atoms)
        assert len(lines) == 1
        assert lines[0].startswith("1. ")


# ---------------------------------------------------------------------------
# render_pre_playoff_team_home_scenarios: empty will_host branch
# ---------------------------------------------------------------------------


class TestRenderPrePlayoffTeamHomeScenariosEmptyWillHost:
    """Rounds where will_host is empty skip the 'Will Host' section entirely."""

    def test_empty_will_host_skips_host_block(self):
        """When will_host=(), the 'Will Host <round>' header is not emitted."""
        seed_cond = HomeGameCondition(kind="seed_required", round_name=None, region=None, seed=1, team_name=None)
        sc_away = HomeGameScenario(conditions=(seed_cond,), explanation="Higher seed hosts")
        rnd = RoundHomeScenarios(
            round_name="Quarterfinals",
            will_host=(),
            will_not_host=(sc_away,),
            p_reach=None,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
        )
        result = render_pre_playoff_team_home_scenarios("Team", [rnd], {})
        assert "Will Host Quarterfinals" not in result
        assert "Will Not Host Quarterfinals" in result

    def test_empty_will_not_host_skips_away_block(self):
        """Symmetrically, when will_not_host=(), the 'Will Not Host' header is not emitted."""
        seed_cond = HomeGameCondition(kind="seed_required", round_name=None, region=None, seed=1, team_name=None)
        sc_home = HomeGameScenario(conditions=(seed_cond,), explanation="Designated home team in bracket")
        rnd = RoundHomeScenarios(
            round_name="First Round",
            will_host=(sc_home,),
            will_not_host=(),
            p_reach=None,
            p_host_conditional=None,
            p_host_marginal=None,
            p_reach_weighted=None,
            p_host_conditional_weighted=None,
            p_host_marginal_weighted=None,
        )
        result = render_pre_playoff_team_home_scenarios("Team", [rnd], {})
        assert "Will Host First Round" in result
        assert "Will Not Host First Round" not in result
