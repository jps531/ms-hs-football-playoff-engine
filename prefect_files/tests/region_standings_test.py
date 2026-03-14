from prefect_files.data_helpers import get_completed_games
from prefect_files.scenarios import determine_odds, determine_scenarios
from prefect_files.tests.data.test_region_standings import (
    expected_3_7a_completed_games,
    expected_3_7a_completed_games_full,
    expected_3_7a_first_counts,
    expected_3_7a_first_counts_full,
    expected_3_7a_fourth_counts,
    expected_3_7a_fourth_counts_full,
    expected_3_7a_minimized_scenarios,
    expected_3_7a_minimized_scenarios_full,
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


def _normalize_scenarios(scenarios: dict) -> dict:
    """Sort scenario atom lists so comparison is order-independent."""
    return {
        team: {
            seed: sorted([tuple(sorted(atom.items())) for atom in atoms])
            for seed, atoms in seed_map.items()
        }
        for team, seed_map in scenarios.items()
    }


# ---------------------------------------------------------------------------
# PRE-FINAL-WEEK tests (3 games remaining, margin-sensitive tiebreakers)
# ---------------------------------------------------------------------------


def test_get_completed_games_3_7a():
    actual = get_completed_games(raw_3_7a_region_results)
    assert sorted(actual, key=lambda g: (g.a, g.b)) == sorted(
        expected_3_7a_completed_games, key=lambda g: (g.a, g.b)
    )


def test_determine_scenarios_3_7a():
    first_counts, second_counts, third_counts, fourth_counts, _, minimized_scenarios = (
        determine_scenarios(teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games)
    )
    assert first_counts == expected_3_7a_first_counts
    assert second_counts == expected_3_7a_second_counts
    assert third_counts == expected_3_7a_third_counts
    assert fourth_counts == expected_3_7a_fourth_counts
    assert _normalize_scenarios(minimized_scenarios) == _normalize_scenarios(expected_3_7a_minimized_scenarios)


def test_determine_odds_3_7a():
    first_counts, second_counts, third_counts, fourth_counts, denom, _ = (
        determine_scenarios(teams_3_7a, expected_3_7a_completed_games, expected_3_7a_remaining_games)
    )
    odds = determine_odds(teams_3_7a, first_counts, second_counts, third_counts, fourth_counts, denom)
    assert odds == expected_3_7a_odds


# ---------------------------------------------------------------------------
# FULL SEASON tests (0 remaining, deterministic — verified against known seeds)
# Ground truth: #1 Oak Grove, #2 Petal, #3 Brandon, #4 Northwest Rankin
# ---------------------------------------------------------------------------


def test_get_completed_games_3_7a_full():
    actual = get_completed_games(raw_3_7a_region_results_full)
    assert sorted(actual, key=lambda g: (g.a, g.b)) == sorted(
        expected_3_7a_completed_games_full, key=lambda g: (g.a, g.b)
    )


def test_determine_scenarios_3_7a_full():
    first_counts, second_counts, third_counts, fourth_counts, denom, minimized_scenarios = (
        determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    )
    assert denom == 1  # NOSONAR — denom is an exact integer count, not a computed float
    assert first_counts == expected_3_7a_first_counts_full
    assert second_counts == expected_3_7a_second_counts_full
    assert third_counts == expected_3_7a_third_counts_full
    assert fourth_counts == expected_3_7a_fourth_counts_full
    assert _normalize_scenarios(minimized_scenarios) == _normalize_scenarios(expected_3_7a_minimized_scenarios_full)


def test_determine_odds_3_7a_full():
    first_counts, second_counts, third_counts, fourth_counts, denom, _ = (
        determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    )
    odds = determine_odds(teams_3_7a, first_counts, second_counts, third_counts, fourth_counts, denom)
    assert odds == expected_3_7a_odds_full


def test_final_seed_order_3_7a():
    """Ground-truth smoke test: full-season standings must match known 2025 playoff seeds."""
    first_counts, second_counts, third_counts, fourth_counts, denom, _ = (
        determine_scenarios(teams_3_7a, expected_3_7a_completed_games_full, expected_3_7a_remaining_games_full)
    )
    odds = determine_odds(teams_3_7a, first_counts, second_counts, third_counts, fourth_counts, denom)

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
