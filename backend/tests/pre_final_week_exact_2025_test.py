"""Exact pre-final-week scenario counts and odds tests for selected 2025 regions.

These tests pin the engine's output for specific (class, region) combinations
against hand-verifiable expected values computed from the 2025 season data.
They complement the structural tests in pre_final_week_2025_test.py with
*exact* assertions you can cross-check manually.

Target regions and their cutoff dates:
    7A: — cutoff 2025-10-31, 3 remaining games (denom=8)
    6A: — cutoff 2025-10-31, 3 remaining games (denom=8)
    5A: — cutoff 2025-10-31, 3 remaining games (denom=8)
    4A: — cutoff 2025-10-24, 2/3 remaining games (denom=8)
    3A: — cutoff 2025-10-24, 2/3 remaining games (denom=8)
    2A: — cutoff 2025-10-24, 2/3 remaining games (denom=8)
    1A: — cutoff 2025-10-24, 2/3 remaining games (denom=8)

Counts are raw scenario tallies (floats due to coin-flip fractional allocation).
Odds are exact ``StandingsOdds`` instances with rounded probability floats.
"""

import pytest

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.pre_final_week_2025_expected import PRE_FINAL_WEEK_EXPECTED
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

# ---------------------------------------------------------------------------
# Helpers (shared with pre_final_week_2025_test.py)
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


def _run_engine(clazz: int, region: int):
    """Return (teams, ScenarioResults, odds) for a region at the pre-final-week cutoff."""
    fixture = REGION_RESULTS_2025[(clazz, region)]
    cutoff = _CUTOFFS[clazz]
    all_games = fixture["games"]

    completed_raw = expand_results([g for g in all_games if g["date"] <= cutoff])
    remaining_games = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in all_games if g["date"] > cutoff]
    teams = teams_from_games(all_games)
    completed = get_completed_games(completed_raw)

    r = determine_scenarios(teams, completed, remaining_games)
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)
    return teams, r, odds


# ---------------------------------------------------------------------------
# Parametrize over all target regions
# ---------------------------------------------------------------------------

_TARGETS = sorted(PRE_FINAL_WEEK_EXPECTED.keys())

_PARAMS = [pytest.param(clazz, region, id=f"region_{region}_{clazz}A") for clazz, region in _TARGETS]


# ---------------------------------------------------------------------------
# Test: exact seed counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_first_counts(clazz, region):
    """first_counts matches pre-computed fixture for region {region}-{clazz}A."""
    _, r, _ = _run_engine(clazz, region)
    expected = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]
    assert r.first_counts == pytest.approx(expected["first_counts"], abs=1e-9), (
        f"Region {region}-{clazz}A: first_counts mismatch"
    )


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_second_counts(clazz, region):
    """second_counts matches pre-computed fixture for region {region}-{clazz}A."""
    _, r, _ = _run_engine(clazz, region)
    expected = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]
    assert r.second_counts == pytest.approx(expected["second_counts"], abs=1e-9), (
        f"Region {region}-{clazz}A: second_counts mismatch"
    )


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_third_counts(clazz, region):
    """third_counts matches pre-computed fixture for region {region}-{clazz}A."""
    _, r, _ = _run_engine(clazz, region)
    expected = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]
    assert r.third_counts == pytest.approx(expected["third_counts"], abs=1e-9), (
        f"Region {region}-{clazz}A: third_counts mismatch"
    )


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_fourth_counts(clazz, region):
    """fourth_counts matches pre-computed fixture for region {region}-{clazz}A."""
    _, r, _ = _run_engine(clazz, region)
    expected = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]
    assert r.fourth_counts == pytest.approx(expected["fourth_counts"], abs=1e-9), (
        f"Region {region}-{clazz}A: fourth_counts mismatch"
    )


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_denom(clazz, region):
    """denom matches pre-computed fixture for region {region}-{clazz}A."""
    _, r, _ = _run_engine(clazz, region)
    expected = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]
    assert r.denom == expected["denom"], f"Region {region}-{clazz}A: denom={r.denom}, expected {expected['denom']}"


# ---------------------------------------------------------------------------
# Test: exact per-team odds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clazz,region", _PARAMS)
def test_exact_odds(clazz, region):
    """Per-team StandingsOdds matches pre-computed fixture for region {region}-{clazz}A."""
    teams, _, odds = _run_engine(clazz, region)
    expected_odds = PRE_FINAL_WEEK_EXPECTED[(clazz, region)]["odds"]

    for team in teams:
        actual = odds[team]
        expected = expected_odds[team]
        assert actual.p1 == pytest.approx(expected.p1, abs=1e-9), (
            f"Region {region}-{clazz}A {team!r}: p1={actual.p1}, expected {expected.p1}"
        )
        assert actual.p2 == pytest.approx(expected.p2, abs=1e-9), (
            f"Region {region}-{clazz}A {team!r}: p2={actual.p2}, expected {expected.p2}"
        )
        assert actual.p3 == pytest.approx(expected.p3, abs=1e-9), (
            f"Region {region}-{clazz}A {team!r}: p3={actual.p3}, expected {expected.p3}"
        )
        assert actual.p4 == pytest.approx(expected.p4, abs=1e-9), (
            f"Region {region}-{clazz}A {team!r}: p4={actual.p4}, expected {expected.p4}"
        )
        assert actual.p_playoffs == pytest.approx(expected.p_playoffs, abs=1e-9), (
            f"Region {region}-{clazz}A {team!r}: p_playoffs={actual.p_playoffs}, expected {expected.p_playoffs}"
        )
        assert actual.clinched == expected.clinched, (
            f"Region {region}-{clazz}A {team!r}: clinched={actual.clinched}, expected {expected.clinched}"
        )
        assert actual.eliminated == expected.eliminated, (
            f"Region {region}-{clazz}A {team!r}: eliminated={actual.eliminated}, expected {expected.eliminated}"
        )
