"""How a finished region's ties were broken: each step stated is the step the tiebreaker applied,
with its actual numbers, and every team's stated place is the place it finished.

The checks don't trust the explainer's own arithmetic: every number a step compared is recomputed
here from the games, and every place is read back against the tiebreaker's order. Random regions
with close, repeated scores reach every step, coin flip included; the 2025 regions are the real
cases.
"""

import random
import re
from collections import Counter
from itertools import combinations

import pytest

from backend.helpers.api_helpers import finished_region_tiebreaks
from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.data_helpers import get_completed_games, normalize_pair
from backend.helpers.tiebreak_explainer import _join, _ordinal, explain_tiebreaks
from backend.helpers.tiebreakers import resolve_standings_for_mask
from backend.tests.data.results_2025_ground_truth import REGION_RESULTS_2025, expand_results, teams_from_games


def _game(winner: str, loser: str, ws: int, ls: int) -> CompletedGame:
    """A played game, stored from the lexicographically first team's side."""
    a, b, _ = normalize_pair(winner, loser)
    pf_a, pa_a = (ws, ls) if winner == a else (ls, ws)
    res_a = 0 if ws == ls else (1 if pf_a > pa_a else -1)
    return CompletedGame(a, b, res_a, pf_a - pa_a, pa_a, pf_a)


def _random_region(rng: random.Random) -> tuple[list[str], list[CompletedGame]]:
    """A finished region whose scores repeat a few values, so ties reach the later steps."""
    teams = [f"T{i}" for i in range(rng.randint(3, 7))]
    scores = rng.choice([[(14, 7)], [(14, 7), (21, 7)], [(14, 7), (20, 7), (10, 7), (35, 0)]])
    games = []
    for x, y in combinations(teams, 2):
        r = rng.random()
        if r < 0.04:
            continue  # never played
        ws, ls = rng.choice(scores)
        if r < 0.08:
            ls = ws  # a tie game
        winner, loser = (x, y) if rng.random() < 0.5 else (y, x)
        games.append(_game(winner, loser, ws, ls))
    return teams, games


# ---------------------------------------------------------------- independent arithmetic


def _result(games, team, opp):
    """(points of the result, capped differential, points allowed) for *team* v *opp*; None if unplayed."""
    a, b, _ = normalize_pair(team, opp)
    for g in games:
        if (g.a, g.b) == (a, b):
            res, pd, pa = (g.res_a, g.pd_a, g.pa_a) if team == a else (-g.res_a, -g.pd_a, g.pa_b)
            return {1: 2, 0: 1, -1: 0}[res], max(-12, min(12, pd)), pa
    return None


def _expected_values(step, games, teams):
    """What the step should have compared for each team, worked out from the games."""
    out = {}
    for t in step.group:
        others = [o for o in step.group if o != t]
        played = [r for r in (_result(games, t, o) for o in others) if r]
        if step.step == 1:
            out[t] = sum(r[0] for r in played) / 2
        elif step.step == 3:
            out[t] = sum(r[1] for r in played)
        elif step.step == 5:
            out[t] = sum(r[2] for r in (_result(games, t, o) for o in teams if o != t) if r)
        elif step.step in (2, 4):
            col = 0 if step.step == 2 else 1
            row = []
            for og in step.outside:
                vs = [r[col] for r in (_result(games, t, o) for o in og) if r]
                row.append(sum(vs) if vs else None)
            out[t] = row
    return out


def _check_region(teams, games, trace_steps: Counter):
    """Every check on one finished region; counts the steps reached into *trace_steps*."""
    trace: list = []
    expected_order = resolve_standings_for_mask(teams, games, [], 0, {}, trace_collector=trace)
    order, ties = explain_tiebreaks(teams, games)
    assert order == expected_order

    for step in trace:
        trace_steps[step.step] += 1
        assert not any(set(og) & set(step.group) for og in step.outside)
        if step.step < 6:
            assert step.values == _expected_values(step, games, teams), step

    place = {t: i + 1 for i, t in enumerate(order)}
    explained = set()
    for tie in ties:
        assert list(tie.places) == sorted(tie.places) == [place[t] for t in tie.teams]
        assert tie.places == tuple(range(tie.places[0], tie.places[0] + len(tie.teams)))
        text = " ".join(tie.steps)
        flipped = {t for g in tie.coin_flip for t in g}
        for t in tie.teams:
            stated = re.findall(rf"{re.escape(t)} finishes (\d+)(?:st|nd|rd|th)", text)
            if t in flipped:
                assert stated == [], (t, text)  # a coin flip's order isn't stated
            else:
                assert stated == [str(place[t])], (t, text)  # stated once, and right
        for g in tie.coin_flip:
            places = _join(_ordinal(p) for p in sorted(place[t] for t in g))
            assert (
                f"{_join(g)} are level on every tiebreaker, so a coin flip decides their order for {places}."
                in tie.steps
            )
        explained |= set(tie.teams)
    # Exactly the teams level in the standings (winning percentage and losses) with another are explained.
    level = Counter(_standing(games, teams, t) for t in teams)
    assert explained == {t for t in teams if level[_standing(games, teams, t)] > 1}


def _standing(games, teams, t):
    """(winning percentage, losses) for *t*: a tie counts half, no games counts as 0."""
    rs = [r[0] for r in (_result(games, t, o) for o in teams if o != t) if r]
    w, lo, ti = rs.count(2), rs.count(0), rs.count(1)
    return (round((w + ti / 2) / len(rs), 6) if rs else 0.0), lo


# ---------------------------------------------------------------- tests


def test_random_finished_regions_reach_every_step_and_say_only_what_happened():
    """1,500 regions: each step's numbers match the games, each place matches the order."""
    rng = random.Random(20261027)
    steps: Counter = Counter()
    for _ in range(1500):
        _check_region(*_random_region(rng), steps)
    # The checks covered every step, the coin flip included.
    assert all(steps[s] > 20 for s in range(1, 7)), steps


@pytest.mark.parametrize("key", sorted(REGION_RESULTS_2025))
def test_2025_regions(key):
    """The real 2025 regular seasons."""
    g = REGION_RESULTS_2025[key]["games"]
    _check_region(teams_from_games(g), get_completed_games(expand_results(g)), Counter())


def test_2025_region_3_7a_reads_as_it_was_decided():
    """Three teams 1-1 against each other: results against Oak Grove separate Petal, and that's
    where step 2 stops: Brandon and Northwest Rankin start over at head-to-head."""
    g = REGION_RESULTS_2025[(7, 3)]["games"]
    _, ties = explain_tiebreaks(teams_from_games(g), get_completed_games(expand_results(g)))
    (tie,) = [t for t in ties if "Petal" in t.teams]
    assert tie.teams == ("Petal", "Brandon", "Northwest Rankin") and tie.places == (2, 3, 4)
    assert tie.records == ("3-2", "3-2", "3-2")
    assert tie.steps == (
        "Head-to-head records against each other: Brandon 1-1, Northwest Rankin 1-1, Petal 1-1 "
        "(Brandon beat Northwest Rankin 3-0; Petal beat Brandon 27-21; Northwest Rankin beat Petal 34-28). "
        "That doesn't separate them.",
        "Results against the highest-placed region teams outside the tie, working down: against Oak Grove (1st): "
        "Petal won, Brandon and Northwest Rankin lost. Petal finishes 2nd; Brandon and Northwest Rankin are still tied.",
        "Brandon and Northwest Rankin start over at head-to-head: Brandon beat Northwest Rankin 3-0. "
        "Brandon finishes 3rd; Northwest Rankin finishes 4th.",
    )


def test_two_teams_split_by_head_to_head():
    """The common case, in one sentence: A and B both 2-1, A beat B."""
    games = [
        _game("A", "B", 21, 14),
        _game("A", "C", 7, 0),
        _game("D", "A", 7, 0),
        _game("B", "C", 7, 0),
        _game("B", "D", 7, 0),
        _game("C", "D", 7, 0),
    ]
    _, ties = explain_tiebreaks(["A", "B", "C", "D"], games)
    assert [(t.teams, t.records, t.places, t.steps) for t in ties] == [
        (("A", "B"), ("2-1", "2-1"), (1, 2), ("Head-to-head: A beat B 21-14. A finishes 1st; B finishes 2nd.",)),
        (("C", "D"), ("1-2", "1-2"), (3, 4), ("Head-to-head: C beat D 7-0. C finishes 3rd; D finishes 4th.",)),
    ]


def test_points_allowed_then_a_restart():
    """A, B and C each 1-1 against each other by 7 and all beat D by 7: steps 1-4 leave them level,
    points allowed puts A first, and B and C start over at head-to-head."""
    games = [
        _game("A", "B", 7, 0),
        _game("B", "C", 14, 7),
        _game("C", "A", 7, 0),
        _game("A", "D", 14, 7),
        _game("B", "D", 14, 7),
        _game("C", "D", 14, 7),
    ]
    _, (tie,) = explain_tiebreaks(["A", "B", "C", "D"], games)
    assert tie.teams == ("A", "B", "C") and tie.places == (1, 2, 3)
    assert [s.split(":")[0] for s in tie.steps] == [
        "Head-to-head records against each other",
        "Results against the highest-placed region teams outside the tie",
        "Point differential in their games against each other, capped at 12 a game",
        "Point differential against the highest-placed region teams outside the tie, capped at 12 a game",
        "Fewest points allowed in all region games",
        "B and C start over at head-to-head",
    ]
    assert (
        tie.steps[4]
        == "Fewest points allowed in all region games: A 14, B 21, C 21. A finishes 1st; B and C are still tied."
    )
    assert tie.steps[5] == "B and C start over at head-to-head: B beat C 14-7. B finishes 2nd; C finishes 3rd."


def test_level_on_everything_is_a_coin_flip():
    """A and B never played and have identical results and scores against everyone else: a coin
    flip decides, and no order between them is stated."""
    games = [
        _game("A", "C", 14, 7),
        _game("B", "C", 14, 7),
        _game("D", "A", 14, 7),
        _game("D", "B", 14, 7),
        _game("D", "C", 14, 7),
    ]
    _, (tie,) = explain_tiebreaks(["A", "B", "C", "D"], games)
    assert tie.teams == ("A", "B") and tie.coin_flip == (("A", "B"),)
    assert tie.steps[0] == "Head-to-head: they didn't play each other. That doesn't separate them."
    assert tie.steps[-1] == "A and B are level on every tiebreaker, so a coin flip decides their order for 2nd and 3rd."
    assert "finishes" not in " ".join(tie.steps)


def test_teams_below_level_on_record_count_together():
    """Teams outside the tie that are level on record with each other are one group in step 2."""
    rng = random.Random(7)
    for _ in range(3000):
        teams, games = _random_region(rng)
        _, ties = explain_tiebreaks(teams, games)
        text = " ".join(s for t in ties for s in t.steps)
        if "counted together" in text:
            assert re.search(r"against T\d( and T\d|, T\d)+ \((both|all) \d+-\d+(-\d+)?, counted together\)", text)
            return
    pytest.fail("no region with an outside group of teams level on record")


def test_no_ties_no_explanations():
    """Distinct records: nothing to explain."""
    games = [_game("A", "B", 7, 0), _game("A", "C", 7, 0), _game("B", "C", 7, 0)]
    order, ties = explain_tiebreaks(["A", "B", "C"], games)
    assert order == ["A", "B", "C"] and ties == []


class TestFinishedRegionTiebreaks:
    """What the API serves: only finished standings, and never against the table's order."""

    GAMES = [
        _game("A", "B", 21, 14),
        _game("A", "C", 7, 0),
        _game("D", "A", 7, 0),
        _game("B", "C", 7, 0),
        _game("B", "D", 7, 0),
        _game("C", "D", 7, 0),
    ]
    TEAMS = ["A", "B", "C", "D"]

    def test_served_when_finished_and_in_the_tables_order(self):
        out = finished_region_tiebreaks(self.TEAMS, self.GAMES, [], ["A", "B", "C", "D"])
        assert [t.teams for t in out] == [["A", "B"], ["C", "D"]]
        assert out[0].steps == ["Head-to-head: A beat B 21-14. A finishes 1st; B finishes 2nd."]

    def test_not_while_games_remain(self):
        assert finished_region_tiebreaks(self.TEAMS, self.GAMES, [RemainingGame("A", "B")], self.TEAMS) is None

    def test_not_before_every_team_has_played(self):
        assert finished_region_tiebreaks([*self.TEAMS, "E"], self.GAMES, [], [*self.TEAMS, "E"]) is None
        assert finished_region_tiebreaks(self.TEAMS, [], [], self.TEAMS) is None

    def test_not_against_a_different_order(self):
        """If the table's order isn't the tiebreaker's, nothing is said rather than something wrong."""
        assert finished_region_tiebreaks(self.TEAMS, self.GAMES, [], ["B", "A", "C", "D"]) is None

    def test_coin_flip_teams_may_be_shown_in_either_order(self):
        games = [
            _game("A", "C", 14, 7),
            _game("B", "C", 14, 7),
            _game("D", "A", 14, 7),
            _game("D", "B", 14, 7),
            _game("D", "C", 14, 7),
        ]
        out = finished_region_tiebreaks(self.TEAMS, games, [], ["D", "B", "A", "C"])
        assert out is not None and out[0].coin_flip == [["A", "B"]]


def test_a_team_separated_by_step_4_sends_the_rest_back_to_head_to_head():
    """T2, T3 and T4 are 3-1 and level through step 3. Against T0, the first team outside the tie,
    T2 and T4 are +12 and T3 +7: step 4 stops there, putting T3 3rd, and T2 and T4 start over at
    head-to-head, where T4 beat T2. Going on down to T1 (T2 +12, T4 +7) would have put T2 1st."""
    games = [
        _game("T0", "T1", 21, 7),
        _game("T2", "T0", 21, 7),
        _game("T3", "T0", 14, 7),
        _game("T4", "T0", 21, 7),
        _game("T2", "T1", 21, 7),
        _game("T3", "T1", 14, 7),
        _game("T4", "T1", 14, 7),
        _game("T2", "T3", 14, 7),
        _game("T4", "T2", 14, 7),
        _game("T3", "T4", 14, 7),
    ]
    order, (tie,) = explain_tiebreaks(["T0", "T1", "T2", "T3", "T4"], games)
    assert order == ["T4", "T2", "T3", "T0", "T1"]
    assert tie.steps[-2:] == (
        "Point differential against the highest-placed region teams outside the tie, capped at 12 a game, working "
        "down: against T0 (4th): T2 +12, T4 +12, T3 +7. T2 and T4 are still tied; T3 finishes 3rd.",
        "T2 and T4 start over at head-to-head: T4 beat T2 14-7. T4 finishes 1st; T2 finishes 2nd.",
    )
