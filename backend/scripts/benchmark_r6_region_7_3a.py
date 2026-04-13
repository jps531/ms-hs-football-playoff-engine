"""One-off benchmark: Region 3-7A (Brandon/Petal/Pearl/Oak Grove/NWR/Meridian) at R=6.

Cutoff: 2025-10-24  →  6 remaining games (2025-10-31 + 2025-11-07 week).

Run from repo root:
    source .venv/bin/activate
    python -m backend.scripts.benchmark_r6_region_7_3a
"""

import time

from backend.helpers.data_classes import RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_renderer import render_team_scenarios
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios, enumerate_outcomes
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import (
    REGION_RESULTS_2025,
    expand_results,
    teams_from_games,
)

_FIXTURE = REGION_RESULTS_2025[(7, 3)]
_CUTOFF = "2025-10-24"
_ALL_GAMES = _FIXTURE["games"]

_TEAMS = sorted(teams_from_games(_ALL_GAMES))
_COMPLETED = get_completed_games(expand_results([g for g in _ALL_GAMES if g["date"] <= _CUTOFF]))
_REMAINING = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in _ALL_GAMES if g["date"] > _CUTOFF]

if __name__ == "__main__":
    R = len(_REMAINING)
    masks = 1 << R
    evals_worst_case = masks * (12**R)

    print("=" * 72)
    print("Region 3-7A  —  R=6 benchmark")
    print("=" * 72)
    print(f"Teams      : {', '.join(_TEAMS)}")
    print(f"Completed  : {len(_COMPLETED)} games")
    print(f"Remaining  : {R} games")
    for i, rg in enumerate(_REMAINING):
        print(f"  bit {i}: {rg.a} vs {rg.b}")
    print(f"Win/loss masks : {masks}")
    print(f"Worst-case evals: {evals_worst_case:,}  (full 12^R per mask)")
    print()

    # -----------------------------------------------------------------------
    # enumerate_outcomes (shared enumeration — runs once)
    # -----------------------------------------------------------------------
    print("Running enumerate_outcomes ...", flush=True)
    t0 = time.perf_counter()
    precomputed = enumerate_outcomes(_TEAMS, _COMPLETED, _REMAINING)
    t_enum = time.perf_counter() - t0
    print(f"  Done in {t_enum:.2f}s")
    print()

    # -----------------------------------------------------------------------
    # build_scenario_atoms  (uses precomputed)
    # -----------------------------------------------------------------------
    print("Running build_scenario_atoms ...", flush=True)
    t1 = time.perf_counter()
    atoms = build_scenario_atoms(_TEAMS, _COMPLETED, _REMAINING, precomputed=precomputed)
    t_atoms = time.perf_counter() - t1
    print(f"  Done in {t_atoms:.2f}s")
    print()

    # -----------------------------------------------------------------------
    # enumerate_division_scenarios  (uses precomputed + atoms)
    # -----------------------------------------------------------------------
    print("Running enumerate_division_scenarios ...", flush=True)
    t2 = time.perf_counter()
    scenarios = enumerate_division_scenarios(
        _TEAMS, _COMPLETED, _REMAINING, scenario_atoms=atoms, precomputed=precomputed
    )
    t_scen = time.perf_counter() - t2
    print(f"  Done in {t_scen:.2f}s")
    print()

    # -----------------------------------------------------------------------
    # determine_scenarios / odds  (win/loss enumeration only — always fast)
    # -----------------------------------------------------------------------
    sr = determine_scenarios(_TEAMS, _COMPLETED, _REMAINING)
    odds = determine_odds(
        _TEAMS,
        sr.first_counts,
        sr.second_counts,
        sr.third_counts,
        sr.fourth_counts,
        sr.denom,
    )

    # -----------------------------------------------------------------------
    # Results summary
    # -----------------------------------------------------------------------
    t_total = t_enum + t_atoms + t_scen
    print("=" * 72)
    print("RESULTS")
    print("=" * 72)
    print(f"Total time : {t_total:.2f}s  (enum {t_enum:.2f}s + atoms {t_atoms:.2f}s + scenarios {t_scen:.2f}s)")
    print(f"Distinct division scenarios: {len(scenarios)}")
    print()

    print("Odds:")
    for team in _TEAMS:
        o = odds.get(team)
        if o is None:
            continue
        if o.clinched:
            status = "CLINCHED"
        elif o.eliminated:
            status = "ELIMINATED"
        else:
            status = ""
        print(
            f"  {team:<22}  "
            f"p1={o.p1:5.1%}  p2={o.p2:5.1%}  "
            f"p3={o.p3:5.1%}  p4={o.p4:5.1%}  "
            f"playoffs={o.p_playoffs:5.1%}  {status}"
        )
    print()

    print("Per-team scenario atoms:")
    for team in _TEAMS:
        team_atoms = atoms.get(team, {})
        for seed in sorted(team_atoms):
            label = f"seed {seed}" if seed <= 4 else "eliminated"
            print(f"  {team:<22}  {label}: {len(team_atoms[seed])} atom(s)")
    print()

    print("Scenario text output:")
    print("-" * 72)
    for team in _TEAMS:
        text = render_team_scenarios(team, atoms, odds=odds)
        if text:
            print(text)
            print()
    print("=" * 72)
