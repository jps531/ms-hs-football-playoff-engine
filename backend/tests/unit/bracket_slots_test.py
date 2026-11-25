"""/bracket's per-slot odds while only some seeds are clinched: every slot stays, and the odds are the team pages'.

Also POST /bracket/simulate's what-ifs, given by school or by slot.
"""

import pytest

from backend.api.models.requests import BracketGameResultRequest, ParticipantRef
from backend.helpers.api_helpers import class_bracket_entries, what_if_results
from backend.helpers.bracket_home_odds import equal_matchup_prob
from backend.helpers.bracket_matchups import forced_wins, slot_playoff_odds, team_playoff_odds
from backend.helpers.data_classes import StandingsOdds
from backend.tests.data.playoff_brackets_2025 import SLOTS_5A_7A_2025

ROUNDS = ("second_round", "quarterfinals", "semifinals", "finals", "champion")


def _team(name: str, p: tuple[float, float, float, float]) -> StandingsOdds:
    """A team's seed odds (p1..p4); clinched when it's certain to make the playoffs."""
    total = sum(p)
    return StandingsOdds(name, *p, total, total, total >= 1.0, total == 0.0)


# Four regions of 5A-7A. Region 1 has its 1 seed clinched (Alpha) and the rest open; region 3 is
# settled; regions 2 and 4 are open throughout, and region 4 has a team out of the running.
BY_REGION = {
    1: {
        "Alpha": _team("Alpha", (1.0, 0.0, 0.0, 0.0)),
        "Bravo": _team("Bravo", (0.0, 0.6, 0.3, 0.1)),
        "Charlie": _team("Charlie", (0.0, 0.3, 0.5, 0.2)),
        "Delta": _team("Delta", (0.0, 0.1, 0.2, 0.7)),
    },
    2: {
        "Echo": _team("Echo", (0.7, 0.2, 0.1, 0.0)),
        "Foxtrot": _team("Foxtrot", (0.2, 0.5, 0.2, 0.1)),
        "Golf": _team("Golf", (0.1, 0.2, 0.4, 0.3)),
        "Hotel": _team("Hotel", (0.0, 0.1, 0.3, 0.6)),
    },
    3: {
        "India": _team("India", (1.0, 0.0, 0.0, 0.0)),
        "Juliet": _team("Juliet", (0.0, 1.0, 0.0, 0.0)),
        "Kilo": _team("Kilo", (0.0, 0.0, 1.0, 0.0)),
        "Lima": _team("Lima", (0.0, 0.0, 0.0, 1.0)),
    },
    4: {
        "Mike": _team("Mike", (0.5, 0.5, 0.0, 0.0)),
        "November": _team("November", (0.5, 0.5, 0.0, 0.0)),
        "Oscar": _team("Oscar", (0.0, 0.0, 0.6, 0.4)),
        "Papa": _team("Papa", (0.0, 0.0, 0.4, 0.6)),
        "Quebec": _team("Quebec", (0.0, 0.0, 0.0, 0.0)),
    },
}
CLINCHED = {"Alpha": (1, 1), "India": (3, 1), "Juliet": (3, 2), "Kilo": (3, 3), "Lima": (3, 4)}


def _lopsided(home_region: int, home_seed: int, away_region: int, away_seed: int) -> float:
    """A position-level win probability that isn't 50/50, standing in for Projected (Elo) odds."""
    strength = lambda r, s: (9 - s) * 3 + (r % 3)  # noqa: E731 -- tiny local rating
    return 1.0 / (1.0 + 10 ** (-(strength(home_region, home_seed) - strength(away_region, away_seed)) / 10))


def _seeds(by_region: dict[int, dict[str, StandingsOdds]]) -> dict[int, dict[str, dict[int, float]]]:
    """region -> team -> {seed: p}."""
    return {r: {t: {1: o.p1, 2: o.p2, 3: o.p3, 4: o.p4} for t, o in teams.items()} for r, teams in by_region.items()}


@pytest.mark.parametrize("win_prob_fn", [equal_matchup_prob, _lopsided], ids=["toss-up", "uneven"])
def test_every_slot_is_listed_and_adds_up_to_each_teams_own_odds(win_prob_fn):
    """With only some seeds clinched, every slot some team can take is listed (a clinched one names its
    team), and a team's chances summed over its seed odds are its bracket_odds (team_playoff_odds)."""
    seeds = _seeds(BY_REGION)
    entries = class_bracket_entries(
        BY_REGION,
        slot_playoff_odds(SLOTS_5A_7A_2025, 2025, seeds, equal_matchup_prob),
        slot_playoff_odds(SLOTS_5A_7A_2025, 2025, seeds, win_prob_fn),
        clazz=5,
    )
    slots = {(e.region, e.seed): e for e in entries}
    assert len(slots) == 16
    assert slots[(1, 1)].school == "Alpha" and slots[(1, 2)].school is None
    own = team_playoff_odds(SLOTS_5A_7A_2025, 2025, seeds, win_prob_fn)
    for region, teams in BY_REGION.items():
        for name, o in teams.items():
            seed_p = {1: o.p1, 2: o.p2, 3: o.p3, 4: o.p4}
            mine = own.get(name)
            for rd in ROUNDS:
                expected = (mine.champion if rd == "champion" else mine.reach.get(rd, 0.0)) if mine else 0.0
                summed = sum(p * getattr(slots[(region, s)], f"{rd}_weighted") for s, p in seed_p.items() if p)
                assert summed == pytest.approx(expected, abs=1e-9), (name, rd)


def _first_slot_with(position: tuple[int, int]):
    """The 5A-7A first-round slot *position* plays in, and its opponent there."""
    first = next(
        s for s in SLOTS_5A_7A_2025 if position in ((s.home_region, s.home_seed), (s.away_region, s.away_seed))
    )
    home = (first.home_region, first.home_seed)
    return first, (first.away_region, first.away_seed) if home == position else home


def test_a_what_if_by_slot_for_an_open_seed_counts():
    """A result given by an open seed's slot counts as that slot's win: it's sure of the quarterfinals,
    its opponent is out, and a slot elsewhere is untouched."""
    _, other = _first_slot_with((2, 1))
    results = [
        BracketGameResultRequest(
            winner=ParticipantRef(region=2, seed=1), loser=ParticipantRef(region=other[0], seed=other[1])
        )
    ]
    seeds = _seeds(BY_REGION)
    what_ifs = what_if_results(results, seeds)
    assert what_ifs == [((2, 1), other, None)]
    by_slot = slot_playoff_odds(
        SLOTS_5A_7A_2025, 2025, seeds, equal_matchup_prob, forced=forced_wins(SLOTS_5A_7A_2025, what_ifs)
    )
    assert by_slot[(2, 1)].reach["quarterfinals"] == pytest.approx(1.0)  # 5A-7A: a first-round win is a quarterfinal
    assert by_slot[other].reach.get("quarterfinals", 0.0) == 0.0
    assert by_slot[(1, 1)].reach["quarterfinals"] == pytest.approx(0.5)


def test_a_what_if_by_school_places_a_clinched_team_and_keeps_a_real_result():
    """A school is placed at the seed it has clinched (one without a clinched seed can't be placed), and
    a game already played keeps its real result whatever a what-if says."""
    seeds = _seeds(BY_REGION)
    results = [BracketGameResultRequest(winner=ParticipantRef(school="India"), loser=ParticipantRef(school="Kilo"))]
    what_ifs = what_if_results(results, seeds)
    assert what_ifs == [((3, 1), (3, 3), None)]
    unplaced = [BracketGameResultRequest(winner=ParticipantRef(school="Bravo"), round="quarterfinals")]
    assert what_if_results(unplaced, seeds) == []

    # India (3-1) lost its first-round game for real; a what-if saying it won changes nothing.
    first, other = _first_slot_with((3, 1))
    opponent = f"R{other[0]}S{other[1]}"
    real = {r: dict(teams) for r, teams in seeds.items()}
    real[other[0]] = {opponent: {other[1]: 1.0}}
    played = [(opponent, "India")]
    flipped = forced_wins(SLOTS_5A_7A_2025, [((3, 1), other, None)])
    as_played = slot_playoff_odds(SLOTS_5A_7A_2025, 2025, real, equal_matchup_prob, played)
    with_what_if = slot_playoff_odds(SLOTS_5A_7A_2025, 2025, real, equal_matchup_prob, played, flipped)
    assert with_what_if[(3, 1)].reach.get("quarterfinals", 0.0) == 0.0
    assert with_what_if[other].reach == as_played[other].reach


def test_a_winner_only_what_if_wins_that_round_and_the_ones_before():
    """Given only the round it won, the winner wins its games up to and including that one."""
    forced = forced_wins(SLOTS_5A_7A_2025, [((3, 1), None, "quarterfinals")])
    assert forced == {((3, 1), 0), ((3, 1), 1)}
    seeds = _seeds(BY_REGION)
    by_slot = slot_playoff_odds(SLOTS_5A_7A_2025, 2025, seeds, equal_matchup_prob, forced=forced)
    assert by_slot[(3, 1)].reach["semifinals"] == pytest.approx(1.0)
    assert by_slot[(3, 1)].reach["finals"] == pytest.approx(0.5)


def test_a_what_if_across_halves_is_the_championship():
    """Two positions from different halves meet in the championship: both won their halves."""
    north = next(s for s in SLOTS_5A_7A_2025 if s.north_south == "N")
    south = next(s for s in SLOTS_5A_7A_2025 if s.north_south == "S")
    w, loser = (north.home_region, north.home_seed), (south.home_region, south.home_seed)
    forced = forced_wins(SLOTS_5A_7A_2025, [(w, loser, None)])
    assert forced == {(w, 0), (w, 1), (w, 2), (w, -1), (loser, 0), (loser, 1), (loser, 2)}
    by_slot = slot_playoff_odds(SLOTS_5A_7A_2025, 2025, _seeds(BY_REGION), equal_matchup_prob, forced=forced)
    assert by_slot[w].champion == pytest.approx(1.0)
    assert by_slot[loser].reach["finals"] == pytest.approx(1.0) and by_slot[loser].champion == 0.0
