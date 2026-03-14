"""
One-shot script to compute correct expected values for Region 3-7A unit tests.

Outputs Python literals ready to paste into:
    prefect_files/tests/data/test_region_standings.py

Run from the project root:
    python scripts/compute_test_expected_values.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefect_files.data_classes import RawCompletedGame, RemainingGame
from prefect_files.data_helpers import get_completed_games
from prefect_files.scenarios import determine_odds, determine_scenarios
from prefect_files.tests.data.test_region_standings import (
    expected_3_7a_remaining_games,
    raw_3_7a_region_results,
    teams_3_7a,
)

_BRANDON = "Brandon"
_MERIDIAN = "Meridian"
_OAK_GROVE = "Oak Grove"
_NORTHWEST_RANKIN = "Northwest Rankin"
_PEARL = "Pearl"
_PETAL = "Petal"

# ---------------------------------------------------------------------------
# Full-season raw data: pre-final-week rows + the 3 final-week games
# ---------------------------------------------------------------------------

raw_3_7a_final_week: list[RawCompletedGame] = [
    # Brandon vs Meridian (Brandon wins 40-13)
    {
        "school": _BRANDON,
        "opponent": _MERIDIAN,
        "date": "2025-11-07",
        "result": "W",
        "points_for": 40,
        "points_against": 13,
    },
    {
        "school": _MERIDIAN,
        "opponent": _BRANDON,
        "date": "2025-11-07",
        "result": "L",
        "points_for": 13,
        "points_against": 40,
    },
    # Oak Grove vs Pearl (Oak Grove wins 28-7)
    {
        "school": _OAK_GROVE,
        "opponent": _PEARL,
        "date": "2025-11-07",
        "result": "W",
        "points_for": 28,
        "points_against": 7,
    },
    {
        "school": _PEARL,
        "opponent": _OAK_GROVE,
        "date": "2025-11-07",
        "result": "L",
        "points_for": 7,
        "points_against": 28,
    },
    # Northwest Rankin vs Petal (Northwest Rankin wins 34-28)
    {
        "school": _NORTHWEST_RANKIN,
        "opponent": _PETAL,
        "date": "2025-11-07",
        "result": "W",
        "points_for": 34,
        "points_against": 28,
    },
    {
        "school": _PETAL,
        "opponent": _NORTHWEST_RANKIN,
        "date": "2025-11-07",
        "result": "L",
        "points_for": 28,
        "points_against": 34,
    },
]

raw_3_7a_full: list[RawCompletedGame] = list(raw_3_7a_region_results) + raw_3_7a_final_week

# ---------------------------------------------------------------------------
# Compute CompletedGame objects
# ---------------------------------------------------------------------------

print("=" * 70)
print("PENULTIMATE WEEK — CompletedGame objects (pre-final-week)")
print("=" * 70)
penultimate_completed = get_completed_games(raw_3_7a_region_results)
penultimate_completed_sorted = sorted(penultimate_completed, key=lambda g: (g.a, g.b))
print("expected_3_7a_completed_games: list[CompletedGame] = [")
for g in penultimate_completed_sorted:
    print(f"    CompletedGame({g.a!r}, {g.b!r}, {g.res_a}, {g.pd_a}, {g.pa_a}, {g.pa_b}),")
print("]")
print()

print("=" * 70)
print("FULL SEASON — CompletedGame objects (all 15 games)")
print("=" * 70)
full_completed = get_completed_games(raw_3_7a_full)
full_completed_sorted = sorted(full_completed, key=lambda g: (g.a, g.b))
print("expected_3_7a_completed_games_full: list[CompletedGame] = [")
for g in full_completed_sorted:
    print(f"    CompletedGame({g.a!r}, {g.b!r}, {g.res_a}, {g.pd_a}, {g.pa_a}, {g.pa_b}),")
print("]")
print()

# ---------------------------------------------------------------------------
# Full season: 0 remaining — verify known playoff seeds
# ---------------------------------------------------------------------------

print("=" * 70)
print("FULL SEASON — Final standings (ground-truth verification)")
print("=" * 70)
no_remaining: list[RemainingGame] = []
(
    full_first,
    full_second,
    full_third,
    full_fourth,
    full_denom,
    full_scenarios,
) = determine_scenarios(teams_3_7a, full_completed, no_remaining)

full_odds = determine_odds(teams_3_7a, full_first, full_second, full_third, full_fourth, full_denom)

# Reconstruct final seed order from odds (clinched teams)
seed_order = sorted(
    teams_3_7a,
    key=lambda t: (
        -full_first.get(t, 0),
        -full_second.get(t, 0),
        -full_third.get(t, 0),
        -full_fourth.get(t, 0),
    ),
)
print(f"Final seed order: {seed_order}")

KNOWN_SEEDS = [_OAK_GROVE, _PETAL, _BRANDON, _NORTHWEST_RANKIN]
computed_top4 = seed_order[:4]
assert computed_top4 == KNOWN_SEEDS, f"GROUND TRUTH MISMATCH!\n  Expected: {KNOWN_SEEDS}\n  Got:      {computed_top4}"
print("✓ Ground truth verified: seeds 1-4 match known 2025 playoff results")
print()

print("Full season first_counts:", dict(full_first))
print("Full season second_counts:", dict(full_second))
print("Full season third_counts:", dict(full_third))
print("Full season fourth_counts:", dict(full_fourth))
print("Full season denom:", full_denom)
print()
print("Full season odds:")
for school, o in full_odds.items():
    print(
        f"  {school}: p1={o.p1:.4f} p2={o.p2:.4f} p3={o.p3:.4f} p4={o.p4:.4f} "
        f"playoffs={o.p_playoffs:.4f} clinched={o.clinched} eliminated={o.eliminated}"
    )
print()

# ---------------------------------------------------------------------------
# Pre-final-week: 3 remaining games — scenario enumeration
# ---------------------------------------------------------------------------

print("=" * 70)
print("PRE-FINAL-WEEK — determine_scenarios output")
print("=" * 70)
(
    p_first,
    p_second,
    p_third,
    p_fourth,
    p_denom,
    p_scenarios,
) = determine_scenarios(
    teams_3_7a,
    penultimate_completed,
    expected_3_7a_remaining_games,
    debug=False,
)
p_odds = determine_odds(teams_3_7a, p_first, p_second, p_third, p_fourth, p_denom)

print(f"expected_3_7a_first_counts: dict[str, float] = {dict(p_first)!r}")
print(f"expected_3_7a_second_counts: dict[str, float] = {dict(p_second)!r}")
print(f"expected_3_7a_third_counts: dict[str, float] = {dict(p_third)!r}")
print(f"expected_3_7a_fourth_counts: dict[str, float] = {dict(p_fourth)!r}")
print(f"denom = {p_denom}")
print()
print("Minimized scenarios (per team, per seed):")
for team, seed_map in sorted(p_scenarios.items()):
    for seed_num, atoms in sorted(seed_map.items()):
        print(f"  {team} seed {seed_num}: {atoms}")
print()
print("expected_3_7a_minimized_scenarios:")
print(repr(dict(p_scenarios)))
print()
print("Odds:")
print("expected_3_7a_odds: dict[str, StandingsOdds] = {")
for school, o in p_odds.items():
    print(
        f"    {school!r}: StandingsOdds("
        f"{school!r}, {o.p1}, {o.p2}, {o.p3}, {o.p4}, "
        f"{o.p_playoffs}, {o.final_playoffs}, {o.clinched}, {o.eliminated}),"
    )
print("}")
print()

# ---------------------------------------------------------------------------
# Full-season expected values (for the full-season test)
# ---------------------------------------------------------------------------

print("=" * 70)
print("FULL SEASON — expected values for test")
print("=" * 70)
print(f"expected_3_7a_first_counts_full: dict[str, float] = {dict(full_first)!r}")
print(f"expected_3_7a_second_counts_full: dict[str, float] = {dict(full_second)!r}")
print(f"expected_3_7a_third_counts_full: dict[str, float] = {dict(full_third)!r}")
print(f"expected_3_7a_fourth_counts_full: dict[str, float] = {dict(full_fourth)!r}")
print(f"denom_full = {full_denom}")
print()
print("Full season minimized scenarios:")
print(repr(dict(full_scenarios)))
print()
print("expected_3_7a_odds_full: dict[str, StandingsOdds] = {")
for school, o in full_odds.items():
    print(
        f"    {school!r}: StandingsOdds("
        f"{school!r}, {o.p1}, {o.p2}, {o.p3}, {o.p4}, "
        f"{o.p_playoffs}, {o.final_playoffs}, {o.clinched}, {o.eliminated}),"
    )
print("}")
