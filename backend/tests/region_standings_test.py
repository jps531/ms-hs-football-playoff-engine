"""Unit tests for Region 3-7A (2025 season) standings, scenario enumeration, and odds calculation."""

from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.standings_2025_3_7a import (
    expected_3_7a_completed_games,
    expected_3_7a_completed_games_full,
    expected_3_7a_first_counts,
    expected_3_7a_first_counts_full,
    expected_3_7a_fourth_counts,
    expected_3_7a_fourth_counts_full,
    expected_3_7a_odds,
    expected_3_7a_odds_full,
    expected_3_7a_remaining_games,
    expected_3_7a_remaining_games_full,
    expected_3_7a_second_counts,
    expected_3_7a_second_counts_full,
    expected_3_7a_third_counts,
    expected_3_7a_third_counts_full,
    raw_3_7a_region_results,
    raw_3_7a_region_results_full,
    teams_3_7a,
)

# ---------------------------------------------------------------------------
# PRE-FINAL-WEEK tests (3 games remaining, margin-sensitive tiebreakers)
# ---------------------------------------------------------------------------


def test_get_completed_games_3_7a():
    """CompletedGame objects match expected pre-final-week data for Region 3-7A."""
    actual = get_completed_games(raw_3_7a_region_results)
    assert sorted(actual, key=lambda g: (g.a, g.b)) == sorted(expected_3_7a_completed_games, key=lambda g: (g.a, g.b))


def test_determine_scenarios_3_7a():
    """Scenario seed counts match expected values for Region 3-7A (pre-final-week)."""
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games)
    assert r.first_counts == expected_3_7a_first_counts
    assert r.second_counts == expected_3_7a_second_counts
    assert r.third_counts == expected_3_7a_third_counts
    assert r.fourth_counts == expected_3_7a_fourth_counts


def test_determine_odds_3_7a():
    """Playoff odds match expected values for Region 3-7A (pre-final-week)."""
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games)
    odds = determine_odds(teams_3_7a, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)
    assert odds == expected_3_7a_odds


# ---------------------------------------------------------------------------
# FULL SEASON tests (0 remaining, deterministic — verified against known seeds)
# Ground truth: #1 Oak Grove, #2 Petal, #3 Brandon, #4 Northwest Rankin
# ---------------------------------------------------------------------------


def test_get_completed_games_3_7a_full():
    """CompletedGame objects match expected full-season data for Region 3-7A."""
    actual = get_completed_games(raw_3_7a_region_results_full)
    assert sorted(actual, key=lambda g: (g.a, g.b)) == sorted(
        expected_3_7a_completed_games_full, key=lambda g: (g.a, g.b)
    )


def test_determine_scenarios_3_7a_full():
    """Scenario seed counts match expected values for Region 3-7A (full season, 0 remaining)."""
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    assert r.denom == 1  # NOSONAR — denom is an exact integer count, not a computed float
    assert r.first_counts == expected_3_7a_first_counts_full
    assert r.second_counts == expected_3_7a_second_counts_full
    assert r.third_counts == expected_3_7a_third_counts_full
    assert r.fourth_counts == expected_3_7a_fourth_counts_full
    assert r.minimized_scenarios == {}  # no remaining games → no scenario tree


def test_determine_odds_3_7a_full():
    """Playoff odds match expected values for Region 3-7A (full season, 0 remaining)."""
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    odds = determine_odds(teams_3_7a, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)
    assert odds == expected_3_7a_odds_full


def test_final_seed_order_3_7a():
    """Ground-truth smoke test: full-season standings must match known 2025 playoff seeds."""
    r = determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    odds = determine_odds(teams_3_7a, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    seed_1 = max(teams_3_7a, key=lambda t: odds[t].p1)
    seed_2 = max(teams_3_7a, key=lambda t: odds[t].p2)
    seed_3 = max(teams_3_7a, key=lambda t: odds[t].p3)
    seed_4 = max(teams_3_7a, key=lambda t: odds[t].p4)

    assert seed_1 == "Oak Grove"
    assert seed_2 == "Petal"
    assert seed_3 == "Brandon"
    assert seed_4 == "Northwest Rankin"
    assert odds["Meridian"].eliminated is True
    assert odds["Pearl"].eliminated is True
