"""Benchmark script for build_scenario_atoms at various values of R.

Run from repo root:
    source .venv/bin/activate
    python -m backend.scripts.benchmark_scenario_engine

Phase 1: Baseline timing for the existing R=4 fixture (Region 4-4A midseason).
Phase 2: After short-circuit optimization, re-run this script and compare.

Output format:
    R=N  masks=M  evals=E  elapsed=X.XXXs  evals/s=Y
"""

import time

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import build_scenario_atoms
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

# ---------------------------------------------------------------------------
# Region 4-4A midseason — R=4 baseline fixture
# ---------------------------------------------------------------------------

_FIXTURE = REGION_RESULTS_2025[(4, 4)]
_CUTOFF = "2025-10-17"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = teams_from_games(_ALL_GAMES)
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(teams, completed, remaining, label: str, runs: int = 3) -> None:
    "Runs the scenario for benchmarking."
    R = len(remaining)
    masks = 1 << R
    evals = masks * (12**R)

    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        build_scenario_atoms(teams, completed, remaining)
        times.append(time.perf_counter() - t0)

    best = min(times)
    avg = sum(times) / len(times)
    print(
        f"  {label:<30}  R={R}  masks={masks:>4}  evals={evals:>12,}"
        f"  best={best:.3f}s  avg={avg:.3f}s  evals/s={evals / avg:,.0f}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 80)
    print("build_scenario_atoms benchmark  (with corner-evaluation short-circuit)")
    print("=" * 80)
    print()

    print("Phase 1 — R=4 baseline (Region 4-4A midseason)")
    _run(_TEAMS, _COMPLETED, _REMAINING, "4-4A midseason (R=4)", runs=3)

    print()
    print("Extrapolated estimates (from R=4 avg):")
    r4_avg = None  # will be computed inline below — just a note for Phase 2 comparison

    # Re-run once to capture timing for extrapolation
    t0 = time.perf_counter()
    build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING)
    r4_avg = time.perf_counter() - t0

    r4_evals = (1 << 4) * (12**4)
    evals_per_sec = r4_evals / r4_avg

    for R in range(5, 9):
        masks = 1 << R
        evals = masks * (12**R)
        est_sec = evals / evals_per_sec
        if est_sec < 120:
            est_str = f"{est_sec:.1f}s"
        elif est_sec < 3600:
            est_str = f"{est_sec / 60:.1f}min"
        else:
            est_str = f"{est_sec / 3600:.1f}hr"
        print(f"  R={R}  masks={masks:>4}  evals={evals:>14,}  estimated ~{est_str}")

    print()
    print("Done. Compare these numbers after implementing short-circuit optimization.")
    print("=" * 80)
