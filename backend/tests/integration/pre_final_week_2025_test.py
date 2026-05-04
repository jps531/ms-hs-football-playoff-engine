"""Pre-final-week 2025 scenario tests across all MHSAA regions.

For 1A–4A regions, "completed" games are those on or before 2025-10-24 and
remaining games are those played on 2025-10-30/31.

For 5A–7A regions, "completed" games are those on or before 2025-10-31 and
remaining games are those played on 2025-11-06/07.

Each parametrized case asserts four concrete expected properties:

1. **Probability conservation** — sum of p1 across all teams == 1.0, and
   likewise for p2, p3, p4 (each seeding slot is awarded exactly once per
   outcome, so the average must sum to 1.0).

2. **Denominator** — ``r.denom == 2 ** len(remaining_games)`` (one
   equal-probability binary outcome per remaining game).

3. **Seed reachability** — for every team that actually earned a playoff seed
   (positions 1–4), their probability at that position is > 0 in the
   pre-final-week state.  A zero here would mean the engine never placed the
   team in a seat they actually won, which indicates a bug.

4. **Pre-final-week elimination** — if any full-season-eliminated team had
   already been knocked out of playoff contention *before* the final week,
   the engine correctly marks them ``eliminated=True``.  (Not all
   full-season-eliminated teams are necessarily out before the final week, so
   this only asserts the subset that the engine has already marked.)

Stubs (empty ``games`` list) are automatically skipped.
"""

import pytest

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CUTOFFS = {
    1: "2025-10-24",
    2: "2025-10-24",
    3: "2025-10-24",
    4: "2025-10-24",
    5: "2025-10-31",
    6: "2025-10-31",
    7: "2025-10-31",
}


def _split_games(fixture, clazz):
    """Return (completed_raw, remaining_games) split at the class cutoff date.

    Args:
        fixture: A RegionFixture dict from REGION_RESULTS_2025.
        clazz: Integer class (1–7).

    Returns:
        Tuple of (raw completed-game list, list[RemainingGame]).
    """
    cutoff = _CUTOFFS[clazz]
    all_games = fixture["games"]

    completed_compact = [g for g in all_games if g["date"] <= cutoff]
    remaining_compact = [g for g in all_games if g["date"] > cutoff]

    completed_raw = expand_results(completed_compact)
    remaining_games = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in remaining_compact]
    return completed_raw, remaining_games


# ---------------------------------------------------------------------------
# Parametrize — skip stubs with no game data
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Test 1: probability conservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region,fixture", _PARAMS)
def test_pre_final_week_probability_conservation(clazz, region, fixture):
    """p1/p2/p3/p4 each sum to 1.0 across all teams (one seed per slot per outcome)."""
    completed_raw, remaining_games = _split_games(fixture, clazz)
    teams = teams_from_games(fixture["games"])
    completed = get_completed_games(completed_raw)

    r = determine_scenarios(teams, completed, remaining_games)
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    assert sum(odds[t].p1 for t in teams) == pytest.approx(1.0, abs=1e-9), (
        f"Region {region}-{clazz}A: p1 probabilities do not sum to 1.0"
    )
    assert sum(odds[t].p2 for t in teams) == pytest.approx(1.0, abs=1e-9), (
        f"Region {region}-{clazz}A: p2 probabilities do not sum to 1.0"
    )
    assert sum(odds[t].p3 for t in teams) == pytest.approx(1.0, abs=1e-9), (
        f"Region {region}-{clazz}A: p3 probabilities do not sum to 1.0"
    )
    assert sum(odds[t].p4 for t in teams) == pytest.approx(1.0, abs=1e-9), (
        f"Region {region}-{clazz}A: p4 probabilities do not sum to 1.0"
    )


# ---------------------------------------------------------------------------
# Test 2: denominator matches 2^(remaining games)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region,fixture", _PARAMS)
def test_pre_final_week_denom(clazz, region, fixture):
    """r.denom == 2 ** len(remaining_games) (one binary outcome per game)."""
    completed_raw, remaining_games = _split_games(fixture, clazz)
    teams = teams_from_games(fixture["games"])
    completed = get_completed_games(completed_raw)

    r = determine_scenarios(teams, completed, remaining_games)

    expected_denom = 2 ** len(remaining_games)
    assert r.denom == expected_denom, (
        f"Region {region}-{clazz}A: denom={r.denom}, expected {expected_denom} ({len(remaining_games)} remaining games)"
    )


# ---------------------------------------------------------------------------
# Test 3: actual playoff seeds were reachable from the pre-final-week state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region,fixture", _PARAMS)
def test_pre_final_week_seeds_reachable(clazz, region, fixture):
    """Every actual 2025 playoff seed had > 0 probability at their actual seed position."""
    completed_raw, remaining_games = _split_games(fixture, clazz)
    teams = teams_from_games(fixture["games"])
    completed = get_completed_games(completed_raw)

    r = determine_scenarios(teams, completed, remaining_games)
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    seeds = fixture["seeds"]
    seed_probs = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}

    for seed_num, team in seeds.items():
        prob_attr = seed_probs[seed_num]
        prob = getattr(odds[team], prob_attr)
        assert prob > 0, (
            f"Region {region}-{clazz}A: actual seed {seed_num} team {team!r} "
            f"has {prob_attr}=0 at pre-final-week state — outcome was unreachable"
        )


# ---------------------------------------------------------------------------
# Test 4: teams already eliminated before the final week are flagged correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region,fixture", _PARAMS)
def test_pre_final_week_early_eliminations(clazz, region, fixture):
    """Teams the engine marks eliminated before the final week must be in the full-season eliminated set."""
    completed_raw, remaining_games = _split_games(fixture, clazz)
    teams = teams_from_games(fixture["games"])
    completed = get_completed_games(completed_raw)

    r = determine_scenarios(teams, completed, remaining_games)
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)

    full_season_eliminated = fixture["eliminated"]

    for team in teams:
        if odds[team].eliminated:
            assert team in full_season_eliminated, (
                f"Region {region}-{clazz}A: engine marks {team!r} eliminated before "
                f"the final week, but {team!r} is NOT in the full-season eliminated set "
                f"— engine incorrectly eliminated a playoff qualifier"
            )
