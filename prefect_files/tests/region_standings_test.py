
from prefect_files.data_helpers import get_completed_games
from prefect_files.region_scenarios_pipeline import determine_odds, determine_scenarios
from prefect_files.tests.data.test_region_standings import (
    raw_3_7a_region_results,
    expected_3_7a_completed_games,
    expected_3_7a_remaining_games,
    teams_3_7a,
    expected_3_7a_first_counts,
    expected_3_7a_second_counts,
    expected_3_7a_third_counts,
    expected_3_7a_fourth_counts,
    expected_3_7a_minimized_scenarios,
    expected_3_7a_odds
)

# Test get_completed_games function
def test_get_completed_games_3_7A():
    actual = get_completed_games(raw_3_7a_region_results)

    # BEST assertion — pytest gives great diffs for lists of dataclasses
    assert actual.sort(key=lambda g: (g.a, g.b)) == expected_3_7a_completed_games.sort(key=lambda g: (g.a, g.b))

# Test determine_scenarios function
def test_determine_scenarios_3_7A():

    clazz = 7
    region = 3
    teams = teams_3_7a
    completed = expected_3_7a_completed_games
    remaining = expected_3_7a_remaining_games

    first_counts, second_counts, third_counts, fourth_counts, denom, minimized_scenarios = determine_scenarios(
        clazz, region, teams, completed, remaining, debug=False
    )

    assert first_counts == expected_3_7a_first_counts
    assert second_counts == expected_3_7a_second_counts
    assert third_counts == expected_3_7a_third_counts
    assert fourth_counts == expected_3_7a_fourth_counts
    assert minimized_scenarios == expected_3_7a_minimized_scenarios

# Test determine_odds function
def test_determine_odds_3_7A():

    clazz = 7
    region = 3
    teams = teams_3_7a
    completed = expected_3_7a_completed_games
    remaining = expected_3_7a_remaining_games

    first_counts, second_counts, third_counts, fourth_counts, denom, minimized_scenarios = determine_scenarios(
        clazz, region, teams, completed, remaining, debug=False
    )

    odds = determine_odds(teams, first_counts, second_counts, third_counts, fourth_counts, denom)

    assert odds == expected_3_7a_odds