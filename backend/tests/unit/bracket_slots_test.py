"""/bracket's per-slot odds while only some seeds are clinched: every slot stays, and the odds are the team pages'."""

import pytest

from backend.helpers.api_helpers import (
    build_bracket_entries,
    build_playoff_bracket_state,
    compute_bracket_advancement_odds,
    with_open_slots,
)
from backend.helpers.bracket_home_odds import equal_matchup_prob
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


def test_open_seeds_get_a_slot_and_clinched_ones_keep_their_team():
    state = build_playoff_bracket_state(CLINCHED, {}, set(), [], {}, SLOTS_5A_7A_2025, 2025, 5)
    filled = with_open_slots(state.all_region_odds, BY_REGION, CLINCHED)
    assert sorted(filled[1]) == ["Alpha", "R1S2", "R1S3", "R1S4"]
    assert sorted(filled[3]) == ["India", "Juliet", "Kilo", "Lima"]  # settled: nothing added
    assert sorted(filled[2]) == ["R2S1", "R2S2", "R2S3", "R2S4"]
    assert filled[1]["R1S3"].p3 == 1.0 and filled[1]["R1S3"].p1 == 0.0
    # A seed no team can take (a region too small for it) gets no slot.
    small = {5: {"Romeo": _team("Romeo", (0.5, 0.5, 0.0, 0.0)), "Sierra": _team("Sierra", (0.5, 0.5, 0.0, 0.0))}}
    assert sorted(with_open_slots({}, small, {})[5]) == ["R5S1", "R5S2"]


@pytest.mark.parametrize("win_prob_fn", [equal_matchup_prob, _lopsided], ids=["toss-up", "uneven"])
def test_every_slot_is_listed_and_adds_up_to_each_teams_own_odds(win_prob_fn):
    """With only some seeds clinched, the slots still cover the bracket, and a team's chances summed over
    its seed odds are what compute_bracket_advancement_odds (the team pages' bracket_odds) gives it."""
    state = build_playoff_bracket_state(CLINCHED, {}, set(), [], {}, SLOTS_5A_7A_2025, 2025, 5)
    entries = build_bracket_entries(
        BY_REGION,
        SLOTS_5A_7A_2025,
        season=2025,
        clazz=5,
        win_prob_fn_weighted=win_prob_fn,
        wins_by_team=state.wins_by_team,
        all_region_odds=with_open_slots(state.all_region_odds, BY_REGION, CLINCHED),
        cross_region_wins=state.cross_region_wins,
        eliminated_hosting=state.eliminated_hosting_map,
        school_to_seed=state.school_to_seed,
    )
    slots = {(e.region, e.seed): e for e in entries}
    assert len(slots) == 16
    assert slots[(1, 1)].school == "Alpha" and slots[(1, 2)].school is None
    for region, teams in BY_REGION.items():
        own = compute_bracket_advancement_odds(region, teams, SLOTS_5A_7A_2025, win_prob_fn=win_prob_fn)
        for name, o in teams.items():
            seed_p = {1: o.p1, 2: o.p2, 3: o.p3, 4: o.p4}
            for rd in ROUNDS:
                summed = sum(p * getattr(slots[(region, s)], f"{rd}_weighted") for s, p in seed_p.items() if p)
                assert summed == pytest.approx(getattr(own[name], rd), abs=1e-9), (name, rd)
