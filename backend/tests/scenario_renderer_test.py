"""Unit tests for scenario_renderer.render_team_scenarios using Region 3-7A data."""

import pytest

from backend.helpers.scenario_renderer import render_team_scenarios
from backend.helpers.scenario_viewer import build_scenario_atoms
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
