"""Ground-truth integration tests: 2025 full-season results → actual playoff seeds.

Each parametrized case feeds a complete region's game results through the full
pipeline and asserts that the computed seeds match the official 2025 MHSAA
playoff bracket.

Stubs (empty ``games`` list) are automatically skipped.
"""

import pytest

from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

# Build parametrize IDs and args from the fixture dict, skipping stubs.
_PARAMS = [
    pytest.param(
        clazz,
        region,
        fixture,
        id=f"region_{region}_{clazz}A",
        marks=pytest.mark.skip(reason="No game data yet") if not fixture["games"] else [],
    )
    for (clazz, region), fixture in sorted(REGION_RESULTS_2025.items())
]


@pytest.mark.parametrize("clazz,region,fixture", _PARAMS)
def test_ground_truth_seeds_2025(clazz, region, fixture):
    """Full-season standings must match known 2025 playoff seeds for every region."""
    games = fixture["games"]
    seeds = fixture["seeds"]
    eliminated = fixture["eliminated"]

    teams = teams_from_games(games)
    raw = expand_results(games)
    completed = get_completed_games(raw)

    r = determine_scenarios(teams, completed, [])
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    seed_1 = max(teams, key=lambda t: odds[t].p1)
    seed_2 = max(teams, key=lambda t: odds[t].p2)
    seed_3 = max(teams, key=lambda t: odds[t].p3)
    seed_4 = max(teams, key=lambda t: odds[t].p4)

    assert seed_1 == seeds[1], f"Region {region}-{clazz}A seed 1: got {seed_1!r}, expected {seeds[1]!r}"
    assert seed_2 == seeds[2], f"Region {region}-{clazz}A seed 2: got {seed_2!r}, expected {seeds[2]!r}"
    assert seed_3 == seeds[3], f"Region {region}-{clazz}A seed 3: got {seed_3!r}, expected {seeds[3]!r}"
    assert seed_4 == seeds[4], f"Region {region}-{clazz}A seed 4: got {seed_4!r}, expected {seeds[4]!r}"

    for team in eliminated:
        assert odds[team].eliminated is True, (
            f"Region {region}-{clazz}A: {team!r} should be eliminated but is not"
        )
