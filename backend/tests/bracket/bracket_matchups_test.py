"""Bracket matchup odds: invariants, and agreement with the existing reach/hosting odds.

Each region gets a made-up but internally consistent seeding distribution (a
weighted set of possible top-four orders), so its per-team seed odds and its
same-region seed pairs come from one joint distribution — exactly what the
region engine stores.
"""

import random
from itertools import permutations

import pytest

from backend.helpers.bracket_home_odds import (
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
    equal_matchup_prob,
)
from backend.helpers.bracket_matchups import bracket_outlook, locked_pairs
from backend.helpers.data_classes import StandingsOdds
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

SEASON = 2025


def _region(region: int, rng: random.Random, n_teams: int = 5, n_orders: int = 6):
    """Seed odds and seed pairs for one region from a random mix of top-four orders."""
    teams = [f"R{region}T{i}" for i in range(n_teams)]
    orders = rng.sample(list(permutations(teams, 4)), n_orders)
    weights = [rng.random() for _ in orders]
    total = sum(weights)
    odds: dict[str, dict[int, float]] = {t: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0} for t in teams}
    pairs: dict[tuple[str, int, str, int], float] = {}
    for order, w in zip(orders, weights):
        p = w / total
        for seed, team in enumerate(order, start=1):
            odds[team][seed] += p
        for i in range(4):
            for j in range(i + 1, 4):
                a, sa, b, sb = order[i], i + 1, order[j], j + 1
                key = (a, sa, b, sb) if a < b else (b, sb, a, sa)
                pairs[key] = pairs.get(key, 0.0) + p
    return odds, pairs


def _class(slots, n_regions: int, seed: int = 7):
    """Seed odds and pairs for every region in a class."""
    rng = random.Random(seed)
    odds, pairs = {}, {}
    for r in range(1, n_regions + 1):
        odds[r], pairs[r] = _region(r, rng)
    return odds, pairs


def _standings(odds_by_team: dict[str, dict[int, float]]) -> dict[str, StandingsOdds]:
    """StandingsOdds for the existing reach/hosting helpers."""
    out = {}
    for team, by in odds_by_team.items():
        p = sum(by.values())
        out[team] = StandingsOdds(team, by[1], by[2], by[3], by[4], p, p, p >= 0.999, p <= 0.0)
    return out


CASES = [("1A-4A", SLOTS_1A_4A_2025, 8), ("5A-7A", SLOTS_5A_7A_2025, 4)]


@pytest.fixture(params=CASES, ids=[c[0] for c in CASES])
def outlook(request):
    """Toss-up outlook for a class plus its inputs."""
    _, slots, n = request.param
    odds, pairs = _class(slots, n)
    games = bracket_outlook(slots, SEASON, odds, pairs, equal_matchup_prob)
    return slots, odds, pairs, games


def test_each_side_sums_to_one(outlook):
    """Someone always arrives on each side of every game."""
    *_, games = outlook
    for g in games:
        for side in (g.side_a, g.side_b):
            assert sum(side.occupants.values()) == pytest.approx(1.0), g.game_id


def test_matchups_sum_to_one_and_no_team_meets_itself(outlook):
    """Every game happens between exactly one pair, never a team and itself."""
    *_, games = outlook
    for g in games:
        assert g.matchups is not None
        assert sum(p for p, _ in g.matchups.values()) == pytest.approx(1.0), g.game_id
        assert all(a != b for a, b in g.matchups), g.game_id


def test_matchups_add_up_to_each_teams_odds_of_being_there(outlook):
    """Summing a team's matchups gives its chance of being on that side — the joint is consistent."""
    *_, games = outlook
    for g in games:
        by_a: dict[str, float] = {}
        by_b: dict[str, float] = {}
        for (a, b), (p, _) in g.matchups.items():
            by_a[a] = by_a.get(a, 0.0) + p
            by_b[b] = by_b.get(b, 0.0) + p
        for team, p in g.side_a.occupants.items():
            assert by_a.get(team, 0.0) == pytest.approx(p, abs=1e-9), (g.game_id, team)
        for team, p in g.side_b.occupants.items():
            assert by_b.get(team, 0.0) == pytest.approx(p, abs=1e-9), (g.game_id, team)


def test_same_region_teams_on_opposite_sides_never_double_count():
    """Region 1's 1 and 4 seeds feed opposite sides of a 1A-4A quarterfinal; a team holding either can't meet itself."""
    odds = {
        r: {f"R{r}A": {1: 0.5, 4: 0.5}, f"R{r}B": {1: 0.5, 4: 0.5}, f"R{r}C": {2: 1.0}, f"R{r}D": {3: 1.0}}
        for r in range(1, 9)
    }
    pairs = {}
    for r in range(1, 9):
        a, b, c, d = (f"R{r}{x}" for x in "ABCD")
        # Either A is 1st and B 4th, or the reverse — never both on one seed.
        pairs[r] = {
            (a, 1, b, 4): 0.5,
            (a, 4, b, 1): 0.5,
            (a, 1, c, 2): 0.5,
            (a, 4, c, 2): 0.5,
            (b, 1, c, 2): 0.5,
            (b, 4, c, 2): 0.5,
            (a, 1, d, 3): 0.5,
            (a, 4, d, 3): 0.5,
            (b, 1, d, 3): 0.5,
            (b, 4, d, 3): 0.5,
            (c, 2, d, 3): 1.0,
        }
    games = bracket_outlook(SLOTS_1A_4A_2025, SEASON, odds, pairs, equal_matchup_prob)
    for g in games:
        assert sum(p for p, _ in g.matchups.values()) == pytest.approx(1.0)
        assert all(a != b for a, b in g.matchups)


def test_missing_same_region_pairs_withholds_matchups_instead_of_guessing():
    """Without a region's joint seeding, games that need it report no matchups rather than a product of marginals."""
    odds, pairs = _class(SLOTS_1A_4A_2025, 8)
    pairs[1] = None
    games = {g.game_id: g for g in bracket_outlook(SLOTS_1A_4A_2025, SEASON, odds, pairs, equal_matchup_prob)}
    # First round: one position per side, regions differ, so nothing is needed.
    assert games["N-0-0"].matchups is not None
    # The North quarterfinal can pair Region 1's 1 and 4 seeds.
    assert games["N-2-0"].matchups is None
    assert games["N-2-0"].notes


def _reach(games, team: str, round_name: str) -> float:
    """P(team plays in a game of this round) from the outlook."""
    total = 0.0
    for g in games:
        if g.round_name == round_name:
            total += g.side_a.occupants.get(team, 0.0) + g.side_b.occupants.get(team, 0.0)
    return total


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_reach_matches_the_existing_advancement_odds(label, slots, n):
    """Reach odds from the outlook equal the existing bracket advancement odds."""
    odds, pairs = _class(slots, n)
    games = bracket_outlook(slots, SEASON, odds, pairs, equal_matchup_prob)
    rounds = {"Quarterfinals": "quarterfinals", "Semifinals": "semifinals", "Championship Game": "finals"}
    if label == "1A-4A":
        rounds["Second Round"] = "second_round"
    for region in range(1, n + 1):
        existing = compute_bracket_advancement_odds(region, _standings(odds[region]), slots, equal_matchup_prob)
        for team, b in existing.items():
            for round_name, attr in rounds.items():
                assert _reach(games, team, round_name) == pytest.approx(getattr(b, attr), abs=1e-9), (team, round_name)


def _host_overall(games, team: str, round_name: str) -> float:
    """P(team plays and hosts in this round) from the matchups."""
    total = 0.0
    for g in games:
        if g.round_name != round_name:
            continue
        for (a, b), (p, h) in g.matchups.items():
            if a == team:
                total += p * h
            elif b == team:
                total += p * (1.0 - h)
    return total


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_hosting_matches_the_existing_hosting_odds(label, slots, n):
    """Per-matchup hosting, summed, equals the existing overall hosting odds for each round."""
    odds, pairs = _class(slots, n)
    games = bracket_outlook(slots, SEASON, odds, pairs, equal_matchup_prob)
    by_region = {r: _standings(odds[r]) for r in odds}
    for region in range(1, n + 1):
        checks = {
            "Quarterfinals": compute_quarterfinal_home_odds(region, by_region[region], slots, SEASON),
            "Semifinals": compute_semifinal_home_odds(region, by_region[region], slots, SEASON),
        }
        if label == "1A-4A":
            checks["Second Round"] = compute_second_round_home_odds(region, by_region[region], slots, SEASON)
        for round_name, existing in checks.items():
            for team, p in existing.items():
                assert _host_overall(games, team, round_name) == pytest.approx(p, abs=1e-9), (team, round_name)


def test_championship_is_neutral():
    """No one hosts the championship game."""
    odds, pairs = _class(SLOTS_5A_7A_2025, 4)
    final = bracket_outlook(SLOTS_5A_7A_2025, SEASON, odds, pairs, equal_matchup_prob)[-1]
    assert final.round_name == "Championship Game"
    assert all(h is None for _, h in final.matchups.values())


def test_played_games_are_fixed_and_locked_seeds_need_no_stored_pairs():
    """In the playoffs, a played game's winner advances with certainty and later sides narrow to fact."""
    odds = {r: {f"R{r}S{s}": {s: 1.0} for s in (1, 2, 3, 4)} for r in range(1, 5)}
    pairs = {r: locked_pairs(odds[r]) for r in odds}
    assert all(p is not None for p in pairs.values())
    # 5A-7A first round: slot 1 is 1-1 vs 2-4; the visitor wins.
    first = SLOTS_5A_7A_2025[0]
    home, away = f"R{first.home_region}S{first.home_seed}", f"R{first.away_region}S{first.away_seed}"
    games = {
        g.game_id: g
        for g in bracket_outlook(SLOTS_5A_7A_2025, SEASON, odds, pairs, equal_matchup_prob, results=[(away, home)])
    }
    assert games["N-0-0"].decided
    assert games["N-1-0"].side_a.occupants == {away: pytest.approx(1.0)}


def test_locked_pairs_only_when_every_seed_is_locked():
    """A region still deciding a seed has no implied pairs."""
    assert locked_pairs({"A": {1: 1.0}, "B": {2: 1.0}}) == {("A", 1, "B", 2): 1.0}
    assert locked_pairs({"A": {1: 0.6, 2: 0.4}, "B": {1: 0.4, 2: 0.6}}) is None


def _lopsided(home_region: int, home_seed: int, away_region: int, away_seed: int) -> float:
    """A position-level win probability that isn't 50/50, standing in for Projected (Elo) odds."""
    strength = lambda r, s: (9 - s) * 3 + (r % 3)  # noqa: E731 -- tiny local rating
    diff = strength(home_region, home_seed) - strength(away_region, away_seed)
    return 1.0 / (1.0 + 10 ** (-diff / 10))


@pytest.mark.parametrize(("label", "slots", "n"), CASES)
def test_reach_and_hosting_match_existing_odds_with_uneven_games(label, slots, n):
    """With uneven win probabilities, reach and hosting still match the existing helpers."""
    odds, pairs = _class(slots, n, seed=11)
    games = bracket_outlook(slots, SEASON, odds, pairs, _lopsided)
    for g in games:
        assert sum(p for p, _ in g.matchups.values()) == pytest.approx(1.0)
    for region in range(1, n + 1):
        standings = _standings(odds[region])
        adv = compute_bracket_advancement_odds(region, standings, slots, _lopsided)
        qf = compute_quarterfinal_home_odds(region, standings, slots, SEASON, _lopsided)
        sf = compute_semifinal_home_odds(region, standings, slots, SEASON, _lopsided)
        for team in standings:
            assert _reach(games, team, "Semifinals") == pytest.approx(adv[team].semifinals, abs=1e-9)
            assert _reach(games, team, "Championship Game") == pytest.approx(adv[team].finals, abs=1e-9)
            assert _host_overall(games, team, "Quarterfinals") == pytest.approx(qf[team], abs=1e-9)
            assert _host_overall(games, team, "Semifinals") == pytest.approx(sf[team], abs=1e-9)


def test_merge_combines_modes_and_folds_long_tails_into_other():
    """The payload carries both modes; pairings under 0.5% in both go to ``other`` and the total stays 1.

    Values are rounded to 0.01% for the payload, so sums are checked to 0.1%.
    """
    from backend.helpers.bracket_matchups import merge_modes

    odds, pairs = _class(SLOTS_1A_4A_2025, 8)
    tossup = bracket_outlook(SLOTS_1A_4A_2025, SEASON, odds, pairs, equal_matchup_prob)
    projected = bracket_outlook(SLOTS_1A_4A_2025, SEASON, odds, pairs, _lopsided)
    games = merge_modes(tossup, projected, floor=0.005)
    assert [g["id"] for g in games] == [g.game_id for g in tossup]
    for g in games:
        for side in ("side_a", "side_b"):
            occ = g[side]["occupants"]
            assert sum(o["p_reach"] for o in occ) == pytest.approx(1.0, abs=1e-3)
            assert sum(o["p_reach_weighted"] for o in occ) == pytest.approx(1.0, abs=1e-3)
        listed = g["matchups"]
        assert all(max(m["p_matchup"], m["p_matchup_weighted"]) >= 0.005 for m in listed)
        assert sum(m["p_matchup"] for m in listed) + g["other"]["p_matchup"] == pytest.approx(1.0, abs=1e-3)
        assert sum(m["p_matchup_weighted"] for m in listed) + g["other"]["p_matchup_weighted"] == pytest.approx(1.0, abs=1e-3)
    final = games[-1]
    assert final["id"] == "final" and final["half"] is None
    assert all(m["p_host_a"] is None for m in final["matchups"])


def test_merge_without_projected_odds_leaves_weighted_fields_empty():
    """No Elo ratings: Projected fields are null rather than zero."""
    from backend.helpers.bracket_matchups import merge_modes

    odds, pairs = _class(SLOTS_5A_7A_2025, 4)
    games = merge_modes(bracket_outlook(SLOTS_5A_7A_2025, SEASON, odds, pairs, equal_matchup_prob), None)
    g = games[0]
    assert g["side_a"]["occupants"][0]["p_reach_weighted"] is None
    assert g["matchups"][0]["p_matchup_weighted"] is None
    assert g["other"]["p_matchup_weighted"] is None


def test_stored_pairs_are_used_only_from_the_same_snapshot_as_the_standings():
    """Pairs from another date would disagree with the standings, so they're ignored unless every seed is locked."""
    from datetime import date

    from backend.helpers.bracket_matchups import pairs_for_regions

    open_region = {"A": {1: 0.5, 2: 0.5}, "B": {1: 0.5, 2: 0.5}}
    locked_region = {"C": {1: 1.0}, "D": {2: 1.0}}
    stored = {1: (date(2026, 10, 9), [["A", 1, "B", 2, 0.5], ["A", 2, "B", 1, 0.5]])}
    same = pairs_for_regions({1: open_region}, {1: date(2026, 10, 9)}, stored)
    assert same[1] == {("A", 1, "B", 2): 0.5, ("A", 2, "B", 1): 0.5}
    stale = pairs_for_regions({1: open_region}, {1: date(2026, 10, 16)}, stored)
    assert stale[1] is None
    derived = pairs_for_regions({2: locked_region}, {2: date(2026, 10, 16)}, {})
    assert derived[2] == {("C", 1, "D", 2): 1.0}
