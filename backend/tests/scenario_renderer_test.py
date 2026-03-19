"""Unit tests for scenario_renderer.render_team_scenarios using Region 3-7A data."""

import pytest

from backend.helpers.scenario_renderer import render_team_scenarios
from backend.tests.data.standings_2025_3_7a import expected_3_7a_scenarios

# ---------------------------------------------------------------------------
# Expected output strings — one per team
# ---------------------------------------------------------------------------

PETAL_EXPECTED = """\
Petal

#1 seed if:
1. Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 9 or less AND Pearl's margin exceeds Northwest Rankin's by 2 or more

#2 seed if:
1. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 10 or more

#3 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal by exactly 4
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5 or more AND Northwest Rankin's margin and Pearl's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin exceeds Northwest Rankin's by 2 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 10 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1"""

PEARL_EXPECTED = """\
Pearl

#1 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 10 or more AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#2 seed if:
1. Petal beats Northwest Rankin AND Pearl beats Oak Grove
2. Meridian beats Brandon AND Northwest Rankin beats Petal AND Pearl beats Oak Grove
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by exactly 6 AND Northwest Rankin beats Petal by exactly 4
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 2

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 4\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 7 or less AND Pearl's margin doesn't exceed Northwest Rankin's by more than 4 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5 or more AND Northwest Rankin's margin and Pearl's margin combined total 10 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 9 or less AND Pearl's margin doesn't exceed Northwest Rankin's by more than 2

Eliminated if:
1. Oak Grove beats Pearl"""

OAK_GROVE_EXPECTED = """\
Oak Grove

#1 seed if:
1. Northwest Rankin beats Petal AND Oak Grove beats Pearl
2. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 10 or less AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if:
1. Petal beats Northwest Rankin AND Oak Grove beats Pearl
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin exceeds Northwest Rankin's by 2 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5 or more AND Northwest Rankin's margin and Pearl's margin combined total 11 or more

#3 seed if:
1. Petal beats Northwest Rankin AND Pearl beats Oak Grove
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 10 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#4 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal AND Pearl beats Oak Grove
2. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by exactly 4
4. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin exceeds Northwest Rankin's by 2 or more"""

NORTHWEST_RANKIN_EXPECTED = """\
Northwest Rankin

#1 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal AND Pearl beats Oak Grove
2. Brandon beats Meridian AND Pearl beats Oak Grove by exactly 6 AND Northwest Rankin beats Petal by exactly 4
3. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal by 5 or more AND Northwest Rankin's margin and Pearl's margin combined total 11 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 2

#2 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal AND Oak Grove beats Pearl
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by exactly 4
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by exactly 4
4. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 5 or more AND Northwest Rankin's margin and Pearl's margin combined total 10 or less
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1\u20135 AND Northwest Rankin beats Petal by 1\u20133 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 2
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 1\u20133 AND Northwest Rankin's margin and Pearl's margin combined total 11 or more

#4 seed if:
1. Petal beats Northwest Rankin AND Oak Grove beats Pearl
2. Brandon beats Meridian AND Northwest Rankin beats Petal AND Oak Grove beats Pearl
3. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal AND Northwest Rankin's margin and Pearl's margin combined total 10 or less AND Pearl's margin exceeds Northwest Rankin's by 3 or more

Eliminated if:
1. Petal beats Northwest Rankin AND Pearl beats Oak Grove"""

BRANDON_EXPECTED = """\
Brandon

#3 seed if:
1. Petal beats Northwest Rankin AND Oak Grove beats Pearl
2. Brandon beats Meridian AND Northwest Rankin beats Petal AND Oak Grove beats Pearl

#4 seed if:
1. Petal beats Northwest Rankin AND Pearl beats Oak Grove
2. Meridian beats Brandon AND Northwest Rankin beats Petal AND Oak Grove beats Pearl

Eliminated if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal AND Pearl beats Oak Grove
2. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal"""

MERIDIAN_EXPECTED = """\
Meridian

Eliminated if:
1. Petal beats Northwest Rankin
2. Meridian beats Brandon AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Northwest Rankin beats Petal AND Oak Grove beats Pearl
4. Brandon beats Meridian AND Pearl beats Oak Grove AND Northwest Rankin beats Petal"""


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
    """render_team_scenarios output matches the expected plain-English scenario string for each team."""
    result = render_team_scenarios(team, expected_3_7a_scenarios)
    assert result == expected, (
        f"\n--- EXPECTED ---\n{expected}\n--- ACTUAL ---\n{result}"
    )
