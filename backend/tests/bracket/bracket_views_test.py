"""The bracket's odds, seen per team, per (region, seed) slot and per game, agree with each other.

``team_playoff_odds`` (the region pages' ``bracket_odds``), ``slot_playoff_odds`` (``GET /bracket``)
and ``game_playoff_odds`` (``GET /bracket/slots``) are views of one recursion, so a team's odds are
its seed odds times its slots' odds, and its games' odds summed per round.
"""

import random
from itertools import permutations

import pytest

from backend.helpers.api_helpers import class_bracket_entries
from backend.helpers.bracket_home_odds import equal_matchup_prob
from backend.helpers.bracket_matchups import (
    bracket_outlook,
    game_id_for,
    game_playoff_odds,
    slot_playoff_odds,
    team_playoff_odds,
)
from backend.helpers.data_classes import StandingsOdds
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

SEASON = 2025
CASES = [("1A-4A", SLOTS_1A_4A_2025, 8), ("5A-7A", SLOTS_5A_7A_2025, 4)]


def _lopsided(home_region: int, home_seed: int, away_region: int, away_seed: int) -> float:
    """A position-level win probability that isn't 50/50, standing in for Projected (Elo) odds."""
    strength = lambda r, s: (9 - s) * 3 + (r % 3)  # noqa: E731 -- tiny local rating
    return 1.0 / (1.0 + 10 ** (-(strength(home_region, home_seed) - strength(away_region, away_seed)) / 10))


def _class(n_regions: int, seed: int = 3) -> dict[int, dict[str, dict[int, float]]]:
    """Seed odds for every region: a random mix of top-four orders among five teams."""
    rng = random.Random(seed)
    out: dict[int, dict[str, dict[int, float]]] = {}
    for r in range(1, n_regions + 1):
        teams = [f"R{r}T{i}" for i in range(5)]
        orders = rng.sample(list(permutations(teams, 4)), 5)
        weights = [rng.random() for _ in orders]
        odds = {t: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0} for t in teams}
        for order, w in zip(orders, weights):
            for s, t in enumerate(order, start=1):
                odds[t][s] += w / sum(weights)
        out[r] = odds
    return out


def _standings(seed_odds: dict[int, dict[str, dict[int, float]]]) -> dict[int, dict[str, StandingsOdds]]:
    """StandingsOdds per region, as the API loads them."""
    return {
        r: {
            t: StandingsOdds(t, *(b.get(s, 0.0) for s in (1, 2, 3, 4)), sum(b.values()), sum(b.values()), False, False)
            for t, b in d.items()
        }
        for r, d in seed_odds.items()
    }


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_a_teams_odds_are_its_seed_odds_times_its_slots(label, slots, n):
    """Summed over its seeds, a team's slots' odds are its own (reach, hosting and title)."""
    odds = _class(n)
    teams = team_playoff_odds(slots, SEASON, odds, _lopsided)
    by_slot = slot_playoff_odds(slots, SEASON, odds, _lopsided)
    for region, region_odds in odds.items():
        for team, by_seed in region_odds.items():
            mine = teams.get(team)
            for key in ("first_round", "second_round", "quarterfinals", "semifinals", "finals"):
                summed = sum(p * by_slot[(region, s)].reach.get(key, 0.0) for s, p in by_seed.items() if p)
                assert summed == pytest.approx(mine.reach.get(key, 0.0) if mine else 0.0, abs=1e-9), (team, key)
                summed = sum(p * by_slot[(region, s)].host.get(key, 0.0) for s, p in by_seed.items() if p)
                assert summed == pytest.approx(mine.host.get(key, 0.0) if mine else 0.0, abs=1e-9), (team, key)
            title = sum(p * by_slot[(region, s)].champion for s, p in by_seed.items() if p)
            assert title == pytest.approx(mine.champion if mine else 0.0, abs=1e-9)


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_a_teams_games_add_up_to_its_rounds(label, slots, n):
    """A round's games, summed, are the team's odds for the round; each game id is the outlook's."""
    odds = _class(n, seed=9)
    games = game_playoff_odds(slots, SEASON, odds, _lopsided)
    teams = team_playoff_odds(slots, SEASON, odds, _lopsided)
    assert set(games) == {g.game_id for g in bracket_outlook(slots, SEASON, odds, {}, _lopsided)}
    for team, mine in teams.items():
        for key, p in mine.reach.items():
            assert sum(g.reach.get(team, 0.0) for g in games.values() if g.round_key == key) == pytest.approx(p)


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_each_first_round_slot_names_the_games_its_winner_plays(label, slots, n):
    """``game_id_for`` names the game in each round whose sides the slot's positions feed."""
    outlook = {g.game_id: g for g in bracket_outlook(slots, SEASON, _class(n), {}, equal_matchup_prob)}
    rounds = 4 if n == 8 else 3
    for s in slots:
        for k in range(rounds):
            game = outlook[game_id_for(slots, s.slot, k)]
            assert (s.home_region, s.home_seed) in game.side_a.feeders + game.side_b.feeders
    assert game_id_for(slots, 999, 0) is None


def _locked_class(n_regions: int, small: int | None = None) -> dict[int, dict[str, dict[int, float]]]:
    """Every seed locked to "R{r}S{s}"; region *small* has only three teams."""
    return {
        r: {f"R{r}S{s}": {s: 1.0} for s in (1, 2, 3, 4) if not (r == small and s == 4)} for r in range(1, n_regions + 1)
    }


def test_a_slot_facing_a_bye_plays_no_first_round_game_and_is_sure_of_the_second():
    """A three-team region has no #4 seed: no slot for it, and the slot that would have played it hosts
    no first-round game (it plays none) and is sure of the second round."""
    odds = _locked_class(8, small=1)
    entries = class_bracket_entries(
        _standings(odds),
        slot_playoff_odds(SLOTS_1A_4A_2025, SEASON, odds, equal_matchup_prob),
        slot_playoff_odds(SLOTS_1A_4A_2025, SEASON, odds, _lopsided),
        clazz=1,
    )
    by_slot = {(e.region, e.seed): e for e in entries}
    assert (1, 4) not in by_slot
    assert len(by_slot) == 31
    slot = next(s for s in SLOTS_1A_4A_2025 if (s.away_region, s.away_seed) == (1, 4))
    lucky = by_slot[(slot.home_region, slot.home_seed)]
    assert lucky.school == f"R{slot.home_region}S{slot.home_seed}"
    assert lucky.second_round == pytest.approx(1.0)
    assert lucky.second_round_weighted == pytest.approx(1.0)
    assert lucky.hosting.first_round.p_host_given_reach is None
    assert lucky.hosting.first_round.p_host_overall == 0.0
    other = by_slot[(slot.away_region, 1)]
    assert other.second_round == pytest.approx(0.5)
    assert other.hosting.first_round.p_host_given_reach in (0.0, 1.0)


def test_5a_7a_slots_have_no_second_round_and_unknown_seeds_no_school():
    """5A-7A have no second round; a seed nobody has clinched names no school."""
    odds = _locked_class(4)
    odds[1] = {"A": {1: 0.5, 2: 0.5}, "B": {1: 0.5, 2: 0.5}, "R1S3": {3: 1.0}, "R1S4": {4: 1.0}}
    entries = class_bracket_entries(
        _standings(odds), slot_playoff_odds(SLOTS_5A_7A_2025, SEASON, odds, equal_matchup_prob), None, clazz=5
    )
    by_slot = {(e.region, e.seed): e for e in entries}
    assert by_slot[(1, 1)].school is None and by_slot[(1, 3)].school == "R1S3"
    assert all(e.hosting.second_round.p_host_overall is None for e in entries)
    assert all(e.quarterfinals_weighted is None for e in entries)  # no Projected odds given
    assert by_slot[(2, 1)].quarterfinals == pytest.approx(0.5)
