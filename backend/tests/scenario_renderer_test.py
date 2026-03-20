"""Unit tests for scenario_renderer using Region 3-7A data."""

import pytest

from backend.helpers.scenario_renderer import (
    division_scenarios_as_dict,
    render_team_scenarios,
    team_scenarios_as_dict,
)
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    teams_3_7a,
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

#1 seed if: (51.3%)
1. Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less

#2 seed if: (14.3%)
1. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#3 seed if: (31.1%)
1. Meridian beats Brandon AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (3.3%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1"""

PEARL_WITH_ODDS_EXPECTED = """\
Pearl

#1 seed if: (4.2%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#2 seed if: (40.6%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#3 seed if: (1.6%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if: (3.6%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2

Eliminated if: (50.0%)
1. Oak Grove beats Pearl"""

OAK_GROVE_WITH_ODDS_EXPECTED = """\
Oak Grove

#1 seed if: (29.7%)
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#2 seed if: (25.5%)
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20132 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (28.0%)
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6\u20138 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7\u20139 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#4 seed if: (16.8%)
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more"""

NORTHWEST_RANKIN_WITH_ODDS_EXPECTED = """\
Northwest Rankin

#1 seed if: (14.8%)
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4\u201310 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if: (19.5%)
1. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 4\u20138 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5\u20139 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4\u20139 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if: (1.8%)
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20134 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#4 seed if: (38.8%)
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
    atoms = build_scenario_atoms(
        teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
    )
    result = render_team_scenarios(team, atoms)
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
    atoms = build_scenario_atoms(
        teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
    )
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games)
    odds = determine_odds(
        teams_3_7a, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom
    )
    result = render_team_scenarios(team, atoms, odds=odds)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )


# ---------------------------------------------------------------------------
# division_scenarios_as_dict
# ---------------------------------------------------------------------------

# Shared fixture helpers — build once per module via module-scoped helpers
def _div_dict():
    atoms = build_scenario_atoms(
        teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
    )
    scenarios = enumerate_division_scenarios(
        teams_3_7a,
        expected_3_7a_completed_games,
        expected_3_7a_remaining_games,
        scenario_atoms=atoms,
    )
    return division_scenarios_as_dict(scenarios)


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
    atoms = build_scenario_atoms(
        teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
    )
    if not with_odds:
        return team_scenarios_as_dict(atoms)
    r = determine_scenarios(
        teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games
    )
    odds = determine_odds(
        teams_3_7a, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom
    )
    return team_scenarios_as_dict(atoms, odds=odds)


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
    assert petal[1]["odds"] == pytest.approx(0.5130208333333334)
    assert petal[1]["weighted_odds"] is None
    assert petal[2]["odds"] == pytest.approx(0.14322916666666666)
    assert petal[3]["odds"] == pytest.approx(0.31076388888888884)
    assert petal[4]["odds"] == pytest.approx(0.032986111111111116)


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
