"""Complete scenarios cover every outcome exactly as the tiebreaker resolves it.

For each region checked, every way the remaining games can go (winners, and
each margin 1-12) must match at least one listed scenario, and every scenario
it matches must give the tiebreaker's seeding. The existing "backward
coverage" tests only ask whether the seeding appears somewhere in the list,
which a scenario with the wrong conditions still passes.

Regions come from the 2025 season, cut to their last 1-3 region games
(exhaustively checked), plus 3A Region 6 in 2026 with four left (sampled).
The ones in KNOWN_GAPS fail today: the scenario builder describes each
seeding of a margin-sensitive outcome with the conditions around a single
sample margin, so a seeding whose margins form more than one block is only
partly covered. They're marked xfail(strict=True) so the fix has to clear
them from the list.
"""

import pytest

from backend.helpers.data_classes import GameResult, RemainingGame
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.scenario_viewer import build_scenario_atoms, enumerate_division_scenarios, enumerate_outcomes
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games
from backend.tests.scenario_coverage import coverage_problems

# (class, region, games left) that fail today.
KNOWN_GAPS = {
    (1, 1, 3), (1, 2, 3), (1, 3, 3), (1, 4, 3), (1, 7, 3),
    (2, 1, 3), (2, 3, 3), (2, 5, 3),
    (3, 5, 3), (3, 6, 3), (3, 7, 3), (3, 8, 3),
    (4, 3, 2), (4, 3, 3), (4, 5, 3), (4, 6, 3), (4, 8, 3),
    (6, 1, 3),
}  # fmt: skip


def _cut(games: list[dict], left: int):
    """The region with its last *left* region games (by date) still to play."""
    ordered = sorted(games, key=lambda g: g["date"])
    completed = get_completed_games(expand_results(ordered[:-left]))
    remaining = [RemainingGame(*sorted([g["winner"], g["loser"]])) for g in ordered[-left:]]
    return teams_from_games(games), completed, remaining


def _scenarios(teams, completed, remaining):
    """The region's complete scenarios, built the way the region scenarios pipeline builds them."""
    pre = enumerate_outcomes(teams, completed, remaining)
    atoms = build_scenario_atoms(teams, completed, remaining, precomputed=pre)
    return enumerate_division_scenarios(teams, completed, remaining, scenario_atoms=atoms, precomputed=pre)


def _cases():
    for (clazz, region), fixture in sorted(REGION_RESULTS_2025.items()):
        for left in (1, 2, 3):
            if len(fixture["games"]) > left:
                marks = (
                    [pytest.mark.xfail(strict=True, reason="known scenario gap")]
                    if (clazz, region, left) in KNOWN_GAPS
                    else []
                )
                yield pytest.param(clazz, region, left, id=f"{clazz}A-{region}-{left}left", marks=marks)


@pytest.mark.parametrize(("clazz", "region", "left"), list(_cases()))
def test_scenarios_cover_every_outcome_2025(clazz, region, left):
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(clazz, region)]["games"], left)
    report = coverage_problems(teams, completed, remaining, _scenarios(teams, completed, remaining))
    assert report.ok, report.summary(remaining)


# 3A Region 6 on Oct 17, 2026, with four region games left: the case that turned this up.
# "Raleigh beats Jefferson Davis County by 12+, Seminary beats Magee, Raleigh beats Seminary" had no scenario.
_R36_PLAYED = [
    ("Magee", "Jefferson Davis County", 22, 6, "2026-10-02"),
    ("Raleigh", "McLaurin", 48, 0, "2026-10-02"),
    ("Seminary", "Jefferson Davis County", 35, 0, "2026-10-09"),
    ("Magee", "McLaurin", 48, 7, "2026-10-09"),
    ("Magee", "Raleigh", 29, 7, "2026-10-16"),
    ("Seminary", "McLaurin", 63, 7, "2026-10-16"),
]
_R36_LEFT = [
    ("Jefferson Davis County", "McLaurin"),
    ("Jefferson Davis County", "Raleigh"),
    ("Magee", "Seminary"),
    ("Raleigh", "Seminary"),
]


@pytest.mark.xfail(strict=True, reason="known scenario gap")
def test_scenarios_cover_every_outcome_3a_region_6_2026():
    games = [dict(winner=w, loser=l, winner_score=a, loser_score=b, date=d) for w, l, a, b, d in _R36_PLAYED]
    teams = teams_from_games(games)
    completed = get_completed_games(expand_results(games))
    remaining = [RemainingGame(a, b) for a, b in _R36_LEFT]
    report = coverage_problems(
        teams, completed, remaining, _scenarios(teams, completed, remaining), samples_per_mask=300
    )
    assert report.ok, report.summary(remaining)


# ------------------------------------------------------------- the checker itself
# Two teams, one game left: whoever wins it is first. Small enough to list by hand.

_PAIR = ["A", "B"]
_ONE_LEFT = [RemainingGame("A", "B")]


def _scenario(num, winners, seeding, conditions=None):
    return {
        "scenario_num": num,
        "sub_label": "",
        "game_winners": winners,
        "conditions_atom": conditions,
        "seeding": seeding,
    }


_RIGHT = [_scenario(1, [("A", "B")], ("A", "B")), _scenario(2, [("B", "A")], ("B", "A"))]


def test_checker_passes_a_complete_list_and_flags_a_missing_scenario():
    assert coverage_problems(_PAIR, [], _ONE_LEFT, _RIGHT).ok
    report = coverage_problems(_PAIR, [], _ONE_LEFT, _RIGHT[:1])
    assert len(report.uncovered) == 12 and not report.wrong  # B's win, at every margin
    assert "uncovered: B over A by 1 -> ['B', 'A']" in report.summary(_ONE_LEFT)


def test_checker_flags_a_scenario_whose_conditions_match_the_wrong_seeding():
    report = coverage_problems(_PAIR, [], _ONE_LEFT, [_RIGHT[0], _scenario(2, [("B", "A")], ("A", "B"))])
    assert not report.uncovered and len(report.wrong) == 12 and report.wrong[0][3] == ["2"]


def test_checker_reads_margin_conditions():
    narrow = [_scenario(1, [("A", "B")], ("A", "B"), [GameResult("A", "B", 1, 6)]), _RIGHT[1]]
    report = coverage_problems(_PAIR, [], _ONE_LEFT, narrow)
    assert sorted(m[("A", "B")] for _, m, _ in report.uncovered) == list(range(6, 13))


def test_checker_counts_any_coin_flip_result_as_right():
    """A scenario for either result of a coin flip agrees with the tiebreaker's pick."""
    from backend.tests.scenario_coverage import _settled

    flips = [["B", "C"]]
    assert _settled(("A", "C", "B", "D"), flips) == _settled(("A", "B", "C", "D"), flips)
    assert _settled(("C", "A", "B", "D"), flips) != _settled(("A", "B", "C", "D"), flips)  # A's place isn't a flip
