"""Unit tests for scenario_renderer using Region 3-7A data."""

import pytest

from backend.helpers.data_classes import (
    GameResult,
    HomeGameCondition,
    HomeGameScenario,
    MarginCondition,
    MatchupEntry,
    RoundHomeScenarios,
    RoundMatchups,
)
from backend.helpers.scenario_renderer import (
    _render_condition,
    _render_condition_label,
    _render_home_scenario_block,
    _render_margin_condition,
    _winner_label,
    division_scenarios_as_dict,
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
    """Scenario 4a title includes margin conditions."""
    entry = _div_dict()["4a"]
    assert entry["title"] == (
        "Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND "
        "Northwest Rankin beats Petal by 6 or more AND "
        "Pearl's margin and Northwest Rankin's margin combined total 11 or more"
    )
    assert entry["one_seed"] == "Northwest Rankin"
    assert entry["two_seed"] == "Oak Grove"
    assert entry["four_seed"] == "Petal"
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
