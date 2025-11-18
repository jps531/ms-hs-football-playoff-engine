
from prefect_files.data_helpers import get_completed_games
from prefect_files.tests.data.test_region_standings import raw_3_7a_region_results, expected_3_7a_completed_games

# Test get_completed_games function
def test_get_completed_games():
    actual = get_completed_games(raw_3_7a_region_results)

    # BEST assertion — pytest gives great diffs for lists of dataclasses
    assert actual.sort(key=lambda g: (g.a, g.b)) == expected_3_7a_completed_games.sort(key=lambda g: (g.a, g.b))