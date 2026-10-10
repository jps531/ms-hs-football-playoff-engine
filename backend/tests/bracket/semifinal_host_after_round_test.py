"""Semifinal hosting stays a fact after the semifinal is played.

Before the fix, once a semifinal was over its loser dropped out of the current
odds, the winner's opponent couldn't be found, and both teams' semifinal
hosting odds fell to 0 for the rest of the season. Rebuilds each class's
post-round survivor snapshots from the real 2025 bracket and checks that, after
the semifinals (whichever team won), the home team still reads 1.0 and the
visitor 0.0.
"""

import pytest

from backend.helpers.bracket_home_odds import compute_semifinal_home_odds
from backend.helpers.data_classes import StandingsOdds
from backend.tests.data.playoff_brackets_2025 import PLAYOFF_BRACKETS_2025, SLOTS_1A_4A_2025, SLOTS_5A_7A_2025


def _odds(alive: set[tuple[int, int]], regions: int) -> dict[int, dict[str, StandingsOdds]]:
    """Per-region odds where every (region, seed) in *alive* holds its seed and the rest are out."""
    out: dict[int, dict[str, StandingsOdds]] = {}
    for r in range(1, regions + 1):
        out[r] = {}
        for s in range(1, 5):
            on = (r, s) in alive
            seeds = [1.0 if on and s == k else 0.0 for k in (1, 2, 3, 4)]
            out[r][f"R{r}S{s}"] = StandingsOdds(f"R{r}S{s}", *seeds, float(on), float(on), True, not on)
    return out


def _teams(games: list[tuple[int, int, int, int]]) -> set[tuple[int, int]]:
    """Every (region, seed) playing in a round's games."""
    return {(g[0], g[1]) for g in games} | {(g[2], g[3]) for g in games}


CASES = [
    (clazz, winner)
    for clazz, rounds in sorted(PLAYOFF_BRACKETS_2025.items())
    if rounds.get("semifinals")
    for winner in ("home", "away")
]


@pytest.mark.parametrize(("clazz", "winner"), CASES)
def test_semifinal_host_kept_after_the_semifinal(clazz: int, winner: str):
    """After the semifinals, the home team reads 1.0 and the visitor 0.0, win or lose."""
    rounds = PLAYOFF_BRACKETS_2025[clazz]
    small = clazz >= 5
    slots, regions = (SLOTS_5A_7A_2025, 4) if small else (SLOTS_1A_4A_2025, 8)
    order = ["quarterfinals", "semifinals"] if small else ["second_round", "quarterfinals", "semifinals"]
    # Survivors after round rc are the teams playing the next round.
    snapshots = {rc: _odds(_teams(rounds[name]), regions) for rc, name in enumerate(order, start=1)}
    finalists = {(g[0], g[1]) if winner == "home" else (g[2], g[3]) for g in rounds["semifinals"]}
    now = _odds(finalists, regions)
    rounds_completed = len(order) + 1

    for home_r, home_s, away_r, away_s in rounds["semifinals"]:
        for r, s, expected in ((home_r, home_s, 1.0), (away_r, away_s, 0.0)):
            res = compute_semifinal_home_odds(
                r,
                now[r],
                slots,
                2025,
                rounds_completed=rounds_completed,
                all_region_odds=now,
                round_snapshots=snapshots,
            )
            assert res[f"R{r}S{s}"] == expected, f"{clazz}A {r}-{s} ({winner} won)"
