"""The region pages' bracket and hosting odds come from the bracket's own numbers, for the whole class.

``class_playoff_odds`` works out every team's odds from all regions at once (``team_playoff_odds``,
the figures ``/bracket/matchups`` shows), and ``_bracket_and_hosting`` turns them into the stored
fields. The playoff update counts a team as alive until it loses, so a bye isn't a loss.
"""

from datetime import date
from types import SimpleNamespace

import pytest

import backend.prefect.playoff_pipeline as playoff
import backend.prefect.region_scenarios_pipeline as pipeline
from backend.helpers.bracket_matchups import TeamPlayoffOdds
from backend.helpers.data_classes import Game, StandingsOdds
from backend.prefect.region_scenarios_pipeline import RegionSeedingData
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025

SEASON = 2025


def _seeded(region: int, teams: int = 4) -> dict[str, StandingsOdds]:
    """A region whose top *teams* seeds are locked: R{region}S{seed} holds seed {seed}."""
    return {
        f"R{region}S{s}": StandingsOdds(
            f"R{region}S{s}", *(1.0 if s == k else 0.0 for k in (1, 2, 3, 4)), 1.0, 1.0, True, False
        )
        for s in range(1, teams + 1)
    }


def _seeding(odds: dict[str, StandingsOdds]) -> RegionSeedingData:
    """Phase 1 data carrying just the odds."""
    return RegionSeedingData(
        odds=odds, odds_weighted=odds, coinflip_teams=set(), teams=list(odds), completed=[], remaining=[]
    )


@pytest.fixture
def slots(monkeypatch):
    """The 1A-4A format, without the database."""
    monkeypatch.setattr(pipeline, "fetch_all_format_slots", SimpleNamespace(fn=lambda c, s: SLOTS_1A_4A_2025))
    return SLOTS_1A_4A_2025


def test_a_bye_reaches_the_second_round_and_hosts_no_first_round_game(slots):
    """Region 1 has three teams: the seed its #4 would have played has a bye. Its stored odds say so:
    sure of the second round, and no first-round home game (a bye isn't one)."""
    seeding = {r: _seeding(_seeded(r, 3 if r == 1 else 4)) for r in range(1, 9)}
    odds = pipeline.class_playoff_odds(1, SEASON, seeding, list(range(1, 9)), None)
    assert odds is not None
    slot = next(s for s in slots if (s.away_region, s.away_seed) == (1, 4))
    lucky = f"R{slot.home_region}S{slot.home_seed}"
    bracket, hosting = pipeline._bracket_and_hosting(seeding[slot.home_region].odds, odds[0])
    assert bracket[lucky].second_round == pytest.approx(1.0)
    assert bracket[lucky].quarterfinals == pytest.approx(0.5)
    assert hosting.first_round[lucky] == 0.0
    # Every other team plays the first round: even odds of the second, and hosts as the format says.
    other = next(t for t in seeding[slot.home_region].odds if t != lucky)
    assert bracket[other].second_round == pytest.approx(0.5)
    assert hosting.first_round[other] in (0.0, 1.0)


def test_toss_up_is_the_projected_without_ratings(slots):
    """No Projected function: both modes are the Toss-up odds."""
    seeding = {r: _seeding(_seeded(r)) for r in range(1, 9)}
    tossup, projected = pipeline.class_playoff_odds(1, SEASON, seeding, list(range(1, 9)), None)
    assert projected is tossup


def test_a_run_for_one_region_keeps_the_per_region_odds(slots):
    """Without every region of the class, there's no class bracket to read."""
    seeding = {1: _seeding(_seeded(1))}
    assert pipeline.class_playoff_odds(1, SEASON, seeding, list(range(1, 9)), None) is None


def test_no_playoff_format_keeps_the_per_region_odds(monkeypatch):
    """A class without a format has no bracket."""
    monkeypatch.setattr(pipeline, "fetch_all_format_slots", SimpleNamespace(fn=lambda c, s: []))
    seeding = {r: _seeding(_seeded(r)) for r in range(1, 9)}
    assert pipeline.class_playoff_odds(1, SEASON, seeding, list(range(1, 9)), None) is None


def test_hosting_is_given_reaching_the_round():
    """Hosting is stored given the round is reached (the first round's, given the playoffs)."""
    teams = {"A": StandingsOdds("A", 0.5, 0.0, 0.0, 0.0, 0.5, 0.5, False, False)}
    playoff_odds = {
        "A": TeamPlayoffOdds(
            reach={"first_round": 0.5, "second_round": 0.4, "quarterfinals": 0.2},
            host={"first_round": 0.5, "second_round": 0.1},
            champion=0.05,
        )
    }
    bracket, hosting = pipeline._bracket_and_hosting(teams, playoff_odds)
    assert bracket["A"].second_round == 0.4
    assert bracket["A"].semifinals == 0.0
    assert bracket["A"].champion == 0.05
    assert hosting.first_round["A"] == pytest.approx(1.0)
    assert hosting.second_round["A"] == pytest.approx(0.25)
    assert hosting.quarterfinals["A"] == 0.0
    assert hosting.semifinals["A"] == 0.0  # never reached: no chance to host


def _game(school: str, opponent: str, result: str) -> Game:
    """A first-round playoff game from *school*'s side."""
    return Game(school, date(2025, 11, 7), SEASON, None, None, None, "First Round", None, opponent, result, None, None)


def test_a_team_is_alive_until_it_loses(monkeypatch):
    """On the first-round date, a team with a bye (or a game still to play) has no win yet and is
    still in the playoffs; only a team that lost is out."""
    teams = ["Bye", "Winner", "Loser", "Later"]
    monkeypatch.setattr(playoff, "fetch_region_teams", SimpleNamespace(fn=lambda c, r, s: teams))
    monkeypatch.setattr(playoff, "fetch_completed_pairs", SimpleNamespace(fn=lambda t, s: []))
    school_to_seed = {"Bye": (3, 1), "Winner": (3, 2), "Loser": (3, 3), "Later": (3, 4)}
    games = [_game("Winner", "X", "W"), _game("Loser", "Y", "L")]
    data = playoff.build_playoff_region_data.fn(1, 3, SEASON, school_to_seed, games)
    alive = {t for t, o in data.odds.items() if o.p_playoffs > 0}
    assert alive == {"Bye", "Winner", "Later"}
    assert data.standings_odds["Loser"].eliminated
    assert not data.standings_odds["Bye"].eliminated
