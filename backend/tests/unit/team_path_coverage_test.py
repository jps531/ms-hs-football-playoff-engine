"""Team paths and key insights say only what the tiebreaker decides.

The per-team "what has to happen" paths (``build_scenario_atoms``) and the key
insights (``extract_insights``) are checked against the tiebreaker for every
way the remaining games can go (winners, and each margin 1-12): a path whose
conditions hold must give its place, every place a team can take must have a
path, and an insight must hold for every result meeting its conditions. A
place that fewest points allowed or a coin flip decides is never certain.
The odds agree with the paths: a place has odds above zero exactly when it
has a path.

Regions come from the 2025 season, cut to their last 1-2 region games
(exhaustive) and 3 (sampled), plus 3A Region 6 in 2026 with four left.
"""

import pytest

from backend.helpers.data_classes import GameResult, RemainingGame, TiebreakPlace
from backend.helpers.data_helpers import get_completed_games
from backend.helpers.insights import KeyInsight, extract_insights
from backend.helpers.scenario_viewer import enumerate_division_scenarios, team_atoms_from_scenarios
from backend.helpers.scenarios import determine_odds, determine_scenarios
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games
from backend.tests.scenario_coverage import insight_problems, team_path_problems
from backend.tests.unit.scenario_coverage_test import _R36_LEFT, _R36_PLAYED, _cut


def _cases():
    for (clazz, region), fixture in sorted(REGION_RESULTS_2025.items()):
        for left in (1, 2, 3):
            if len(fixture["games"]) > left:
                yield pytest.param(clazz, region, left, id=f"{clazz}A-{region}-{left}left")


def _check(teams, completed, remaining, samples):
    scenarios = enumerate_division_scenarios(teams, completed, remaining)
    atoms = team_atoms_from_scenarios(scenarios, remaining)
    report = team_path_problems(teams, completed, remaining, atoms, samples_per_mask=samples)
    assert report.ok, report.summary()
    insights = extract_insights(
        atoms, teams, completed, remaining, r_computed=len(remaining), complete_scenarios=scenarios
    )
    assert not insight_problems(teams, completed, remaining, insights, samples_per_mask=samples)


@pytest.mark.parametrize(("clazz", "region", "left"), list(_cases()))
def test_team_paths_and_insights_hold_2025(clazz, region, left):
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(clazz, region)]["games"], left)
    _check(teams, completed, remaining, None if left < 3 else 40)


def test_team_paths_and_insights_hold_3a_region_6_2026():
    games = [dict(winner=w, loser=l, winner_score=a, loser_score=b, date=d) for w, l, a, b, d in _R36_PLAYED]
    teams = teams_from_games(games)
    completed = get_completed_games(expand_results(games))
    remaining = [RemainingGame(a, b) for a, b in _R36_LEFT]
    _check(teams, completed, remaining, 200)


def _odds_and_paths_agree(teams, completed, remaining):
    """Every place with odds above zero has a path, and every place with a path has odds above zero."""
    atoms = team_atoms_from_scenarios(enumerate_division_scenarios(teams, completed, remaining), remaining)
    r = determine_scenarios(teams, completed, remaining)
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom)
    wrong = {}
    for team in teams:
        o = odds[team]
        p = {1: o.p1, 2: o.p2, 3: o.p3, 4: o.p4, 5: 1 - o.p_playoffs}
        with_odds = {seed for seed, x in p.items() if x > 1e-12}
        if with_odds != set(atoms.get(team, {})):
            wrong[team] = (sorted(with_odds), sorted(atoms.get(team, {})))
    return wrong


@pytest.mark.parametrize(("clazz", "region", "left"), [c for c in _cases() if c.values[2] < 3])
def test_odds_and_paths_agree_2025(clazz, region, left):
    """A place only fewest points allowed can give still has odds above zero (e.g. 2A-1's
    Ashland at #2), and no place with odds lacks a path. Mismatches: {team: (odds, paths)}."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(clazz, region)]["games"], left)
    assert _odds_and_paths_agree(teams, completed, remaining) == {}


def test_raleigh_first_in_3a_region_6_is_unlikely_not_impossible():
    """Raleigh is 1st only when it, Magee and Seminary tie (every game won by 12 or more) and points
    allowed favour Raleigh: a few percent, not 0%."""
    games = [dict(winner=w, loser=l, winner_score=a, loser_score=b, date=d) for w, l, a, b, d in _R36_PLAYED]
    teams = teams_from_games(games)
    completed = get_completed_games(expand_results(games))
    remaining = [RemainingGame(a, b) for a, b in _R36_LEFT]
    r = determine_scenarios(teams, completed, remaining)
    assert 0.005 < r.first_counts["Raleigh"] / r.denom < 0.05


# ------------------------------------------------------------- the checker itself
# Two teams, one game left: whoever wins it is first, the other second.

_PAIR = ["A", "B"]
_ONE_LEFT = [RemainingGame("A", "B")]
_RIGHT = {
    "A": {1: [[GameResult("A", "B")]], 2: [[GameResult("B", "A")]]},
    "B": {1: [[GameResult("B", "A")]], 2: [[GameResult("A", "B")]]},
}


def test_path_checker_passes_right_paths_and_flags_false_and_missing_ones():
    assert team_path_problems(_PAIR, [], _ONE_LEFT, _RIGHT).ok
    wrong = {"A": {1: [[]]}, "B": _RIGHT["B"]}  # "A is first whatever happens"
    report = team_path_problems(_PAIR, [], _ONE_LEFT, wrong)
    assert len(report.false) == 12 and report.false[0][:2] == ("A", 1)
    assert {(t, s) for t, s, *_ in report.missing} == {("A", 2)}
    assert "false: A #1" in report.summary()


def test_path_checker_treats_a_place_on_points_allowed_as_uncertain():
    """A tie decided by fewest points allowed, with a team still to play, has no certain order."""
    teams, completed, remaining = _cut(REGION_RESULTS_2025[(1, 2)]["games"], 1)
    atoms = team_atoms_from_scenarios(enumerate_division_scenarios(teams, completed, remaining), remaining)
    assert team_path_problems(teams, completed, remaining, atoms).ok
    # Dropping the tie conditions turns every place in the tie into a claim: certain, and false.
    flat = {
        t: {s: [[c for c in a if not isinstance(c, TiebreakPlace)] for a in al] for s, al in seeds.items()}
        for t, seeds in atoms.items()
    }
    assert team_path_problems(teams, completed, remaining, flat).false


def test_insight_checker_flags_a_false_insight():
    false = KeyInsight("clinch_seed", "A", 1, (GameResult("A", "B", 1, 6),), True, "A clinches", 1)
    true = KeyInsight("clinch_seed", "A", 1, (GameResult("A", "B"),), True, "A clinches too", 1)
    lie = KeyInsight("clinch_seed", "B", 1, (GameResult("A", "B"),), True, "B clinches", 1)
    assert [x[0] for x in insight_problems(_PAIR, [], _ONE_LEFT, [false, true, lie])] == ["B clinches"]


def test_points_allowed_override_replaces_the_assumed_score():
    """A remaining game's given points allowed replace the assumed 14 and 14 plus the margin."""
    from backend.helpers.tiebreakers import standings_from_mask

    left = [RemainingGame("A", "B")]
    assumed = standings_from_mask(["A", "B"], [], left, 1, 14, {("A", "B"): 3})
    given = standings_from_mask(["A", "B"], [], left, 1, 14, {("A", "B"): 3}, points_allowed={("A", "B"): (0, 40)})
    assert (assumed["A"]["pa"], assumed["B"]["pa"]) == (14, 17)
    assert (given["A"]["pa"], given["B"]["pa"]) == (0, 40)


def test_a_result_without_a_points_allowed_tie_has_one_order():
    """Scores are only drawn when a tie reaches fewest points allowed with a tied team still to play."""
    from backend.helpers.scenarios import _resolve_with_scores

    [(order, flips, share)] = _resolve_with_scores(_PAIR, [], _ONE_LEFT, 1, {("A", "B"): 5})
    assert (order, flips, share) == (["A", "B"], [], 1.0)


def test_text_odds_never_round_a_possible_place_to_zero():
    from backend.helpers.scenario_renderer import _pct

    assert [_pct(x) for x in (0.0, 0.0001, 0.25, 0.9999, 1.0)] == ["0.0%", "<0.1%", "25.0%", ">99.9%", "100.0%"]
