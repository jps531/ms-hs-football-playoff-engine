"""Tests for probabilistic playoff home-odds functions.

Covers compute_second_round_home_odds, compute_quarterfinal_home_odds, and
compute_semifinal_home_odds across six distinct knowledge states:

1. Pre-bracket          — fractional seed probabilities (linearity test)
2. Some seeds locked    — mix of deterministic and fractional p_seed values
3. Whole bracket locked — all seeds certain; hand-computed expected values
4. R1 semi-complete     — some R1 results known (via win_prob_fn injection)
5. R1 complete          — all R1 results known; must agree with deterministic functions
6. Additional branches  — even/odd-year tiebreak, non-equal win_prob_fn,
                          same-region golden rule, 1A-4A vs 5A-7A structure

Sum invariant (applies in all scenarios)
-----------------------------------------
For any valid inputs, the sum of marginal P(hosting round X) across every
team in a bracket half equals the number of games played in that round:

    5A-7A North or South:  QF = 2,  SF = 1
    1A-4A North or South:  R2 = 4,  QF = 2,  SF = 1

All 5A-7A tests use the North half (Regions 1-2) from SLOTS_5A_7A_2025.
All 1A-4A tests use the North half (Regions 1-4) from SLOTS_1A_4A_2025.

5A-7A North slot assignments (for derivation of hand-computed values):
    Slot 1: home=R1s1, away=R2s4   (QF game A pair)
    Slot 2: home=R2s2, away=R1s3   (QF game A pair)
    Slot 3: home=R2s1, away=R1s4   (QF game B pair)
    Slot 4: home=R1s2, away=R2s3   (QF game B pair)

With equal_matchup_prob and all seeds locked (p_seed=1.0 for one seed),
the marginal QF hosting probabilities for Region 1 are:
    seed 1 (slot 1, home): P(host QF) = 0.5 × 1.0 = 0.5
        — hosts vs R2s2 (equal homes→seed wins) AND vs R1s3 (golden rule wins)
    seed 2 (slot 4, home): P(host QF) = 0.5 × 0.5 = 0.25
        — hosts vs R1s4 (golden rule), loses to R2s1 (seed 1 beats 2)
    seed 3 (slot 2, away): P(host QF) = 0.5 × 0.5 = 0.25
        — hosts vs R2s4 (fewer homes + better seed), loses to R1s1 (golden rule)
    seed 4 (slot 3, away): P(host QF) = 0.5 × 0.0 = 0.0
        — never hosts: loses to R1s2 (golden rule) and R2s3 (better seed)
Region 2 mirrors Region 1 by bracket symmetry (same 0.5/0.25/0.25/0.0 pattern).
"""

import pytest

from backend.helpers.bracket_home_odds import (
    MatchupProbFn,
    _p_home_in_r2,
    _p_team_reach,
    compute_bracket_advancement_odds,
    compute_quarterfinal_home_odds,
    compute_second_round_home_odds,
    compute_semifinal_home_odds,
    equal_matchup_prob,
    marginal_home_odds,
    r2_home_team,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds
from backend.helpers.scenarios import compute_bracket_odds
from backend.tests.data.playoff_brackets_2025 import SLOTS_1A_4A_2025, SLOTS_5A_7A_2025

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ODD_SEASON = 2025
EVEN_SEASON = 2024

# 5A-7A North half: Regions 1 and 2 (4 slots, 2 QF games, 1 SF game)
_5A7A_NORTH_QF_GAMES = 2
_5A7A_NORTH_SF_GAMES = 1

# 1A-4A North half: Regions 1-4 (8 slots, 4 R2 games, 2 QF games, 1 SF game)
_1A4A_NORTH_R2_GAMES = 4
_1A4A_NORTH_QF_GAMES = 2
_1A4A_NORTH_SF_GAMES = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _locked(school: str, seed: int) -> StandingsOdds:
    """Return StandingsOdds with p_seed=1.0 for exactly one seed, 0.0 for rest."""
    return StandingsOdds(
        school=school,
        p1=1.0 if seed == 1 else 0.0,
        p2=1.0 if seed == 2 else 0.0,
        p3=1.0 if seed == 3 else 0.0,
        p4=1.0 if seed == 4 else 0.0,
        p_playoffs=1.0,
        final_playoffs=1.0,
        clinched=True,
        eliminated=False,
    )


def _uniform(school: str) -> StandingsOdds:
    """Return StandingsOdds with equal 0.25 probability for each of the 4 seeds."""
    return StandingsOdds(
        school=school,
        p1=0.25,
        p2=0.25,
        p3=0.25,
        p4=0.25,
        p_playoffs=1.0,
        final_playoffs=1.0,
        clinched=False,
        eliminated=False,
    )


def _fractional(school: str, p1: float, p2: float, p3: float, p4: float) -> StandingsOdds:
    """Return StandingsOdds with arbitrary per-seed probabilities."""
    p = p1 + p2 + p3 + p4
    return StandingsOdds(
        school=school,
        p1=p1,
        p2=p2,
        p3=p3,
        p4=p4,
        p_playoffs=p,
        final_playoffs=p,
        clinched=p >= 0.999,
        eliminated=p <= 0.001,
    )


def _slot_results_fn(
    slot_results: dict[tuple[int, int, int, int], float],
) -> MatchupProbFn:
    """Return a win_prob_fn that returns fixed P(home wins) for known slot matchups.

    Only the exact (home_region, home_seed, away_region, away_seed) 4-tuples
    corresponding to actual R1 slots are fixed; every other call returns 0.5.
    This avoids polluting R2/QF win-probability computations inside the engine.

    Args:
        slot_results: Dict mapping (hr, hs, ar, as_) → P(home team wins).
                      Typically 0.0 or 1.0 for a known result.
    """

    def fn(home_region: int, home_seed: int, away_region: int, away_seed: int) -> float:
        """Return fixed P(home wins) for known slot matchups, 0.5 otherwise."""
        return slot_results.get((home_region, home_seed, away_region, away_seed), 0.5)

    return fn


# ---------------------------------------------------------------------------
# Scenario 3: Whole bracket locked — 5A-7A North, QF (hand-computed)
# ---------------------------------------------------------------------------

# Each test uses a region_odds dict for one region with the seed locked to a
# specific value.  Expected marginals derived from the slot analysis in the
# module docstring above.

_5A7A_QF_LOCKED_CASES = [
    # (region, seed, expected_marginal)
    # Region 1
    (1, 1, 0.50),
    (1, 2, 0.25),
    (1, 3, 0.25),
    (1, 4, 0.00),
    # Region 2 — mirrors Region 1 by bracket symmetry
    (2, 1, 0.50),
    (2, 2, 0.25),
    (2, 3, 0.25),
    (2, 4, 0.00),
]


@pytest.mark.parametrize(
    "region,seed,expected",
    [pytest.param(r, s, e, id=f"R{r}s{s}") for r, s, e in _5A7A_QF_LOCKED_CASES],
)
def test_qf_locked_5a7a_north(region: int, seed: int, expected: float) -> None:
    """Locked seed in 5A-7A North: marginal QF hosting matches hand-computed value."""
    odds = {f"Team_R{region}s{seed}": _locked(f"Team_R{region}s{seed}", seed)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON)
    assert result[f"Team_R{region}s{seed}"] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# Sum invariant
# ---------------------------------------------------------------------------


def _5a7a_north_all_locked_odds() -> dict[int, dict[str, StandingsOdds]]:
    """Build locked region_odds for all four 5A-7A North teams (regions 1-2, seeds 1-4)."""
    return {
        1: {f"R1s{s}": _locked(f"R1s{s}", s) for s in range(1, 5)},
        2: {f"R2s{s}": _locked(f"R2s{s}", s) for s in range(1, 5)},
    }


def _1a4a_north_all_locked_odds() -> dict[int, dict[str, StandingsOdds]]:
    """Build locked region_odds for all 1A-4A North teams (regions 1-4, seeds 1-4)."""
    return {r: {f"R{r}s{s}": _locked(f"R{r}s{s}", s) for s in range(1, 5)} for r in range(1, 5)}


def _sum_marginals(
    fn,
    regions: list[int],
    all_odds: dict[int, dict[str, StandingsOdds]],
    slots,
    season: int,
) -> float:
    """Sum marginal hosting probabilities across all given regions using the provided compute function."""
    total = 0.0
    for region in regions:
        result = fn(region, all_odds[region], slots, season)
        total += sum(result.values())
    return total


@pytest.mark.parametrize("season", [ODD_SEASON, EVEN_SEASON], ids=["odd_year", "even_year"])
def test_sum_invariant_qf_5a7a_north(season: int) -> None:
    """Sum of marginal QF hosting across all 5A-7A North teams = 2 (one home per game)."""
    all_odds = _5a7a_north_all_locked_odds()
    total = _sum_marginals(compute_quarterfinal_home_odds, [1, 2], all_odds, SLOTS_5A_7A_2025, season)
    assert total == pytest.approx(_5A7A_NORTH_QF_GAMES, abs=1e-9)


@pytest.mark.parametrize("season", [ODD_SEASON, EVEN_SEASON], ids=["odd_year", "even_year"])
def test_sum_invariant_sf_5a7a_north(season: int) -> None:
    """Sum of marginal SF hosting across all 5A-7A North teams = 1 (one home per game)."""
    all_odds = _5a7a_north_all_locked_odds()
    total = _sum_marginals(compute_semifinal_home_odds, [1, 2], all_odds, SLOTS_5A_7A_2025, season)
    assert total == pytest.approx(_5A7A_NORTH_SF_GAMES, abs=1e-9)


@pytest.mark.parametrize("season", [ODD_SEASON, EVEN_SEASON], ids=["odd_year", "even_year"])
def test_sum_invariant_r2_1a4a_north(season: int) -> None:
    """Sum of marginal R2 hosting across all 1A-4A North teams = 4."""
    all_odds = _1a4a_north_all_locked_odds()
    total = 0.0
    for region in range(1, 5):
        result = compute_second_round_home_odds(region, all_odds[region], SLOTS_1A_4A_2025, season)
        total += sum(result.values())
    assert total == pytest.approx(_1A4A_NORTH_R2_GAMES, abs=1e-9)


@pytest.mark.parametrize("season", [ODD_SEASON, EVEN_SEASON], ids=["odd_year", "even_year"])
def test_sum_invariant_qf_1a4a_north(season: int) -> None:
    """Sum of marginal QF hosting across all 1A-4A North teams = 2."""
    all_odds = _1a4a_north_all_locked_odds()
    total = _sum_marginals(compute_quarterfinal_home_odds, list(range(1, 5)), all_odds, SLOTS_1A_4A_2025, season)
    assert total == pytest.approx(_1A4A_NORTH_QF_GAMES, abs=1e-9)


@pytest.mark.parametrize("season", [ODD_SEASON, EVEN_SEASON], ids=["odd_year", "even_year"])
def test_sum_invariant_sf_1a4a_north(season: int) -> None:
    """Sum of marginal SF hosting across all 1A-4A North teams = 1."""
    all_odds = _1a4a_north_all_locked_odds()
    total = _sum_marginals(compute_semifinal_home_odds, list(range(1, 5)), all_odds, SLOTS_1A_4A_2025, season)
    assert total == pytest.approx(_1A4A_NORTH_SF_GAMES, abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 1: Pre-bracket — linearity test
# ---------------------------------------------------------------------------


def test_qf_linearity_uniform_equals_seed_average_5a7a() -> None:
    """Uniform p_seed=0.25 marginal equals the average of the four locked-seed marginals."""
    region = 1
    school = "TeamA"
    uniform_odds = {school: _uniform(school)}
    result_uniform = compute_quarterfinal_home_odds(region, uniform_odds, SLOTS_5A_7A_2025, ODD_SEASON)

    weighted = 0.0
    for seed in range(1, 5):
        locked_odds = {school: _locked(school, seed)}
        r = compute_quarterfinal_home_odds(region, locked_odds, SLOTS_5A_7A_2025, ODD_SEASON)
        weighted += 0.25 * r[school]

    assert result_uniform[school] == pytest.approx(weighted, abs=1e-9)


def test_r2_linearity_uniform_equals_seed_average_1a4a() -> None:
    """R2 uniform p_seed marginal equals the average of the four locked-seed marginals (1A-4A)."""
    region = 1
    school = "TeamA"
    uniform_odds = {school: _uniform(school)}
    result_uniform = compute_second_round_home_odds(region, uniform_odds, SLOTS_1A_4A_2025, ODD_SEASON)

    weighted = 0.0
    for seed in range(1, 5):
        locked_odds = {school: _locked(school, seed)}
        r = compute_second_round_home_odds(region, locked_odds, SLOTS_1A_4A_2025, ODD_SEASON)
        weighted += 0.25 * r[school]

    assert result_uniform[school] == pytest.approx(weighted, abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 2: Some seeds locked — mixed region_odds
# ---------------------------------------------------------------------------


def test_qf_partially_locked_region_5a7a() -> None:
    """When some teams are locked and others aren't, locked teams' marginals are unaffected.

    compute_quarterfinal_home_odds operates independently per school via their
    p_seed weights — adding a second school with fractional odds to the dict
    must not change the first school's result.
    """
    region = 1
    locked_school = "R1s1"
    fractional_school = "R1_other"

    locked_only = {locked_school: _locked(locked_school, 1)}
    r_locked_only = compute_quarterfinal_home_odds(region, locked_only, SLOTS_5A_7A_2025, ODD_SEASON)

    mixed = {
        locked_school: _locked(locked_school, 1),
        fractional_school: _fractional(fractional_school, 0.0, 0.5, 0.5, 0.0),
    }
    r_mixed = compute_quarterfinal_home_odds(region, mixed, SLOTS_5A_7A_2025, ODD_SEASON)

    assert r_mixed[locked_school] == pytest.approx(r_locked_only[locked_school], abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 4: R1 semi-complete — known R1 winners collapse to 0 for losers
# ---------------------------------------------------------------------------


def test_qf_r1_loser_gets_zero_5a7a() -> None:
    """A known R1 loser must have marginal P(hosting QF) = 0.0."""
    region = 2
    school = "R2s4"
    # 5A-7A North slot 1: home=R1s1 (1,1,2,4), away=R2s4.  R1s1 wins → P(home)=1.0.
    fn = _slot_results_fn({(1, 1, 2, 4): 1.0})
    odds = {school: _locked(school, 4)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    assert result[school] == pytest.approx(0.0, abs=1e-9)


def test_qf_r1_winner_nonzero_5a7a() -> None:
    """A known R1 winner's marginal P(hosting QF) must be > 0."""
    region = 1
    school = "R1s1"
    fn = _slot_results_fn({(1, 1, 2, 4): 1.0})
    odds = {school: _locked(school, 1)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    assert result[school] > 0.0


def test_r2_loser_gets_zero_1a4a() -> None:
    """Known R1 loser in 1A-4A bracket has marginal P(hosting R2) = 0.0."""
    region = 2
    school = "R2s4"
    # 1A-4A North slot 1: home=R1s1 (1,1,2,4), away=R2s4.  R1s1 wins.
    fn = _slot_results_fn({(1, 1, 2, 4): 1.0})
    odds = {school: _locked(school, 4)}
    result = compute_second_round_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON, fn)
    assert result[school] == pytest.approx(0.0, abs=1e-9)


def test_qf_r1_loser_gets_zero_1a4a() -> None:
    """A known R1 loser must have marginal P(hosting QF) = 0.0 in 1A-4A."""
    region = 2
    school = "R2s4"
    # 1A-4A North slot 1: home=R1s1 (1,1,2,4), away=R2s4.  R1s1 wins.
    fn = _slot_results_fn({(1, 1, 2, 4): 1.0})
    odds = {school: _locked(school, 4)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON, fn)
    assert result[school] == pytest.approx(0.0, abs=1e-9)


def test_qf_r1_winner_nonzero_1a4a() -> None:
    """A known R1 winner's marginal P(hosting QF) must be > 0 in 1A-4A."""
    region = 1
    school = "R1s1"
    fn = _slot_results_fn({(1, 1, 2, 4): 1.0})
    odds = {school: _locked(school, 1)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON, fn)
    assert result[school] > 0.0


# ---------------------------------------------------------------------------
# Scenario 5: R1 complete — bridge to deterministic functions
# ---------------------------------------------------------------------------
#
# When R1 outcomes are certain (win_prob_fn returns 0.0 or 1.0 for every
# R1 matchup), the probabilistic QF/SF hosting marginals must agree with
# the deterministic qf_home_team / sf_home_team functions applied to the
# resulting known bracket path.
#
# 5A-7A North game A:  slot 1 (R1s1 home vs R2s4) and slot 2 (R2s2 home vs R1s3)
# We decide: R1s1 wins (h1=True), R2s2 wins (h1=True).
# QF: R1s1 (h1=True, h2=False[no R2]) vs R2s2 (h1=True, h2=False)
#     → equal home games → seed: 1 < 2 → R1s1 hosts
#     → qf_home_team(1,1,True,False, 2,2,True,False, season) == (1,1)
#
# For probabilistic: P(R1s1 hosts QF) should == 1.0 (they definitely reach
# and definitely host against R2s2 who also definitely reaches).


# 5A-7A North slot 1: home=R1s1, away=R2s4
# 5A-7A North slot 2: home=R2s2, away=R1s3
_SLOT1_5A7A_N = (1, 1, 2, 4)
_SLOT2_5A7A_N = (2, 2, 1, 3)


def _game_a_fn(slot1_home_wins: bool, slot2_home_wins: bool) -> MatchupProbFn:
    """Return win_prob_fn that fixes outcomes for 5A-7A North QF game A slots."""
    return _slot_results_fn(
        {
            _SLOT1_5A7A_N: 1.0 if slot1_home_wins else 0.0,
            _SLOT2_5A7A_N: 1.0 if slot2_home_wins else 0.0,
        }
    )


@pytest.mark.parametrize(
    "s1_home_wins,s2_home_wins,expected_host",
    [
        # R1s1 wins (home, h=1), R2s2 wins (home, h=1) → cross-region, equal homes → seed 1<2 → R1s1
        (True, True, (1, 1)),
        # R1s1 wins (home, h=1), R1s3 wins (away, h=0) → same region → golden rule: seed 1<3 → R1s1
        (True, False, (1, 1)),
        # R2s4 wins (away, h=0), R2s2 wins (home, h=1) → same region → golden rule: seed 2<4 → R2s2
        (False, True, (2, 2)),
        # R2s4 wins (away, h=0), R1s3 wins (away, h=0) → cross-region, equal homes → seed 3<4 → R1s3
        (False, False, (1, 3)),
    ],
    ids=["R1s1_v_R2s2", "R1s1_v_R1s3_golden_rule", "R2s4_v_R2s2_golden_rule", "R2s4_v_R1s3"],
)
def test_qf_bridge_r1_complete_5a7a(s1_home_wins: bool, s2_home_wins: bool, expected_host: tuple) -> None:
    """Probabilistic QF marginal with known R1 agrees with deterministic qf_home_team.

    For the team that deterministically hosts, P(hosting QF) == 1.0.
    For the non-host QF participant, P(hosting QF) == 0.0.
    """
    fn = _game_a_fn(s1_home_wins, s2_home_wins)
    host_region, host_seed = expected_host

    host_school = f"R{host_region}s{host_seed}"
    odds = {host_school: _locked(host_school, host_seed)}
    result = compute_quarterfinal_home_odds(host_region, odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    assert result[host_school] == pytest.approx(1.0, abs=1e-9), (
        f"Expected P(hosting QF) == 1.0 for {host_school}, got {result[host_school]}"
    )

    # Identify the non-host and verify they get 0.0
    s1_team = (1, 1) if s1_home_wins else (2, 4)
    s2_team = (2, 2) if s2_home_wins else (1, 3)
    away_region, away_seed = s2_team if s1_team == (host_region, host_seed) else s1_team
    away_school = f"R{away_region}s{away_seed}"
    away_odds = {away_school: _locked(away_school, away_seed)}
    away_result = compute_quarterfinal_home_odds(away_region, away_odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    assert away_result[away_school] == pytest.approx(0.0, abs=1e-9), (
        f"Expected P(hosting QF) == 0.0 for {away_school}, got {away_result[away_school]}"
    )


# ---------------------------------------------------------------------------
# Scenario 5b: R2 complete — bridge to deterministic for 1A-4A
# ---------------------------------------------------------------------------
#
# 1A-4A North QF game A pairs slots 0,1 against slots 2,3:
#   Slot 0 (idx 0): home=R1s1 (1,1), away=R2s4 (2,4)
#   Slot 1 (idx 1): home=R3s2 (3,2), away=R4s3 (4,3)
#   Slot 2 (idx 2): home=R2s1 (2,1), away=R1s4 (1,4)
#   Slot 3 (idx 3): home=R4s2 (4,2), away=R3s3 (3,3)
#
# All home teams win R1.  R2 pairings (lower seed hosts):
#   R2 game A (slots 0+1): R1s1 vs R3s2 → R1s1 hosts (better seed).
#     win_prob_fn(1,1,3,2) = 1.0 → R1s1 advances; 0.0 → R3s2 advances.
#   R2 game B (slots 2+3): R2s1 vs R4s2 → R2s1 hosts (better seed).
#     win_prob_fn(2,1,4,2) = 1.0 → R2s1 advances; 0.0 → R4s2 advances.
#
# Expected QF hosts (odd year, lower region# breaks seed ties):
#   (r2a=T, r2b=T): R1s1(h=2) vs R2s1(h=2) → seed tie → R1 hosts  → (1,1)
#   (r2a=T, r2b=F): R1s1(h=2) vs R4s2(h=1) → fewer homes → R4s2 hosts → (4,2)
#   (r2a=F, r2b=T): R3s2(h=1) vs R2s1(h=2) → fewer homes → R3s2 hosts → (3,2)
#   (r2a=F, r2b=F): R3s2(h=1) vs R4s2(h=1) → seed tie → R3 hosts  → (3,2)
#
# Home-game counts per team:
#   - R1s1: r1_home=T (slot 0 home); R2: hosts vs R3s2 (better seed) → h2=T → total=2
#   - R3s2: r1_home=T (slot 1 home); R2: away at R1s1 (worse seed) → h2=F → total=1
#   - R2s1: r1_home=T (slot 2 home); R2: hosts vs R4s2 (better seed) → h2=T → total=2
#   - R4s2: r1_home=T (slot 3 home); R2: away at R2s1 (worse seed) → h2=F → total=1

# R1 results — all home slots win (slot tuples used by win_prob_fn)
_1A4A_QF_A_R1_RESULTS = {
    (1, 1, 2, 4): 1.0,  # slot 0: R1s1 wins
    (3, 2, 4, 3): 1.0,  # slot 1: R3s2 wins
    (2, 1, 1, 4): 1.0,  # slot 2: R2s1 wins
    (4, 2, 3, 3): 1.0,  # slot 3: R4s2 wins
}

_1A4A_QF_A_BRIDGE_CASES = [
    # (r2a_home_wins, r2b_home_wins, expected_host, non_host)
    (True,  True,  (1, 1), (2, 1)),
    (True,  False, (4, 2), (1, 1)),
    (False, True,  (3, 2), (2, 1)),
    (False, False, (3, 2), (4, 2)),
]


@pytest.mark.parametrize(
    "r2a_home_wins,r2b_home_wins,expected_host,non_host",
    [
        pytest.param(*c, id=f"r2a={'win' if c[0] else 'loss'}_r2b={'win' if c[1] else 'loss'}")
        for c in _1A4A_QF_A_BRIDGE_CASES
    ],
)
def test_qf_bridge_r2_complete_1a4a(
    r2a_home_wins: bool,
    r2b_home_wins: bool,
    expected_host: tuple,
    non_host: tuple,
) -> None:
    """Probabilistic QF marginal with known R1+R2 agrees with qf_home_team for 1A-4A.

    For the team that deterministically hosts, P(hosting QF) == 1.0.
    For the non-host QF participant, P(hosting QF) == 0.0.
    """
    fn = _slot_results_fn({
        **_1A4A_QF_A_R1_RESULTS,
        (1, 1, 3, 2): 1.0 if r2a_home_wins else 0.0,
        (2, 1, 4, 2): 1.0 if r2b_home_wins else 0.0,
    })

    host_region, host_seed = expected_host
    host_school = f"R{host_region}s{host_seed}"
    result = compute_quarterfinal_home_odds(
        host_region, {host_school: _locked(host_school, host_seed)},
        SLOTS_1A_4A_2025, ODD_SEASON, fn,
    )
    assert result[host_school] == pytest.approx(1.0, abs=1e-9), (
        f"Expected P(hosting QF) == 1.0 for {host_school}, got {result[host_school]}"
    )

    non_region, non_seed = non_host
    non_school = f"R{non_region}s{non_seed}"
    non_result = compute_quarterfinal_home_odds(
        non_region, {non_school: _locked(non_school, non_seed)},
        SLOTS_1A_4A_2025, ODD_SEASON, fn,
    )
    assert non_result[non_school] == pytest.approx(0.0, abs=1e-9), (
        f"Expected P(hosting QF) == 0.0 for {non_school}, got {non_result[non_school]}"
    )


def test_qf_r2_loser_gets_zero_1a4a() -> None:
    """A known R2 loser must have marginal P(hosting QF) = 0.0 in 1A-4A."""
    region = 1
    school = "R1s1"
    # R1s1 wins R1 (slot 0 home), R3s2 wins R1 (slot 1 home), then R3s2 beats R1s1 in R2.
    fn = _slot_results_fn({
        (1, 1, 2, 4): 1.0,  # R1s1 wins R1
        (3, 2, 4, 3): 1.0,  # R3s2 wins R1 (their slot)
        (1, 1, 3, 2): 0.0,  # R3s2 beats R1s1 in R2 (R1s1 was home by seed, loses)
    })
    odds = {school: _locked(school, 1)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON, fn)
    assert result[school] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 6a: Odd-year vs even-year tiebreak
# ---------------------------------------------------------------------------
#
# To isolate the year tiebreak, construct a QF matchup where both teams have
# equal seeds and equal home-game histories.
#
# 5A-7A North game B: slot 3 (R2s1 home) vs slot 4 (R1s2 home).
# If R1s2 (seed 2, Region 1) wins slot 4 and R2s3 (seed 3, away in slot 4)
# is the only possible opponent from the other pair... wait, we need equal seeds.
#
# The clean equal-seed cross-region SF case: lock Region 1 seed 2 vs Region 2 seed 2.
# SF rule: higher seed hosts; equal seed → odd year: lower region# hosts.
# So for (R1s2, R2s2) in SF: odd year → R1 hosts; even year → R2 hosts.
# SF function uses p_reach × p_host, so we verify relative ordering.


def test_sf_odd_year_lower_region_hosts_equal_seeds() -> None:
    """In an odd year, equal-seeded SF opponents: lower region number hosts."""
    region = 1
    school = "R1s2"
    # Compute SF odds with equal seeds for R1s2 in odd year
    result_odd = compute_semifinal_home_odds(region, {school: _locked(school, 2)}, SLOTS_5A_7A_2025, ODD_SEASON)
    result_even = compute_semifinal_home_odds(region, {school: _locked(school, 2)}, SLOTS_5A_7A_2025, EVEN_SEASON)
    # R1s2 is the lower-numbered region; odd year favors them, even year disfavors them
    # for the equal-seed SF matchup against R2s2.
    assert result_odd[school] > result_even[school]


def test_sf_even_year_higher_region_hosts_equal_seeds() -> None:
    """In an even year, equal-seeded SF opponents: higher region number hosts."""
    region = 2
    school = "R2s2"
    result_even = compute_semifinal_home_odds(region, {school: _locked(school, 2)}, SLOTS_5A_7A_2025, EVEN_SEASON)
    result_odd = compute_semifinal_home_odds(region, {school: _locked(school, 2)}, SLOTS_5A_7A_2025, ODD_SEASON)
    # R2s2 is the higher-numbered region; even year favors them vs R1s2 in equal-seed SF
    assert result_even[school] > result_odd[school]


# ---------------------------------------------------------------------------
# Scenario 6b: Non-equal win_prob_fn shifts marginals in the expected direction
# ---------------------------------------------------------------------------


def test_stronger_seed1_win_prob_increases_qf_hosting_marginal() -> None:
    """Higher P(win) for seed 1 increases their marginal P(hosting QF)."""
    region = 1
    school = "R1s1"
    odds = {school: _locked(school, 1)}

    # Weak seed 1: P(R1 win) = 0.5 (default)
    result_equal = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, equal_matchup_prob)

    # Strong seed 1: P(R1 win) = 0.9
    def strong_s1(_hr: int, _hs: int, _ar: int, _as: int) -> float:
        """Return 0.9 P(home wins) when home seed is better, 0.1 when worse."""
        if _hs < _as:
            return 0.9
        if _hs > _as:
            return 0.1
        return 0.5

    result_strong = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, strong_s1)

    assert result_strong[school] > result_equal[school]


def test_stronger_seed4_win_prob_decreases_seed1_qf_hosting_marginal() -> None:
    """Higher P(win) for seed 4 (upsets) decreases seed 1's marginal P(hosting QF)."""
    region = 1
    school = "R1s1"
    odds = {school: _locked(school, 1)}

    result_equal = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, equal_matchup_prob)

    # Inverted: worse seed wins more often (seed 4 upsets seed 1)
    def upset_prone(_hr: int, _hs: int, _ar: int, _as: int) -> float:
        """Return 0.1 P(home wins) when home seed is better (upset-favoring matchup prob)."""
        if _hs < _as:
            return 0.1
        if _hs > _as:
            return 0.9
        return 0.5

    result_upset = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, upset_prone)

    assert result_upset[school] < result_equal[school]


# ---------------------------------------------------------------------------
# Scenario 6c: Same-region golden rule in probabilistic function (5A-7A)
# ---------------------------------------------------------------------------
#
# In 5A-7A North, slot 1 is R1s1 vs R2s4 and slot 2 is R2s2 vs R1s3.
# QF game A pairs slots 1 and 2.  R1s1 can face R1s3 (same region) in QF;
# golden rule must fire → R1s1 always hosts same-region R1s3.
# Force R2s4 to win (so R1s1 is eliminated) — then check R1s3 can host
# only when facing cross-region opponents.
#
# More directly: lock slot 2 so R1s3 definitely advances (R1s3 beats R2s2).
# R1s3 (seed 3, Region 1) hosts QF only if facing R2s4 (cross-region, fewer homes).
# If facing R1s1 (same region), golden rule → R1s1 hosts (seed 1 < 3) — R1s3 never hosts same-region.


def test_same_region_golden_rule_fires_in_probabilistic_qf() -> None:
    """Seed 1 always hosts vs same-region seed 3; golden rule dominates home-game count."""
    region = 1
    school = "R1s1"
    # Force R1s1 (slot 1 home) and R1s3 (slot 2 away) to both win R1 → guaranteed same-region QF
    # Slot 1 (1,1,2,4): home wins (R1s1 advances). Slot 2 (2,2,1,3): away wins (R1s3 advances).
    fn = _slot_results_fn({_SLOT1_5A7A_N: 1.0, _SLOT2_5A7A_N: 0.0})
    odds = {school: _locked(school, 1)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    # R1s1 (h=1) vs R1s3 (h=0): same region → golden rule → seed 1 hosts regardless of home count
    assert result[school] == pytest.approx(1.0, abs=1e-9)


def test_golden_rule_seed3_never_hosts_same_region_seed1() -> None:
    """Seed 3 cannot host if facing same-region seed 1 — golden rule gives home to seed 1."""
    region = 1
    school = "R1s3"
    fn = _slot_results_fn({_SLOT1_5A7A_N: 1.0, _SLOT2_5A7A_N: 0.0})
    odds = {school: _locked(school, 3)}
    result = compute_quarterfinal_home_odds(region, odds, SLOTS_5A_7A_2025, ODD_SEASON, fn)
    # R1s3 (h=0) reaches QF but faces same-region R1s1 → golden rule → 0.0
    assert result[school] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 6d: 1A-4A structural difference (qf_offset=2, R2 hosting is computed)
# ---------------------------------------------------------------------------
#
# In 1A-4A, there is an extra round (R2) before the QF.
# compute_second_round_home_odds operates within this structure.
#
# 1A-4A North slot 1: home=R1s1 (1,1,2,4), away=R2s4
# 1A-4A North slot 2: home=R3s2 (3,2,4,3), away=R4s3
#
# Seed 1 always has the best seed among any R2 opponent (seed 2, 3, or 4),
# so P(R1s1 hosts R2 | reaches R2) = 1.0.
# Marginal: P(hosting R2) = P(win R1) × 1.0 = 0.5 under equal_matchup_prob.
#
# Seed 4 always faces a lower-numbered (better) seed in R2 (opponents from
# the adjacent slot are seeds 2 and 3), so P(R2s4 hosts R2 | reaches R2) = 0.0.
# Marginal: P(hosting R2) = P(win R1) × 0.0 = 0.0.


def test_1a4a_seed1_always_hosts_r2() -> None:
    """In 1A-4A, locked seed 1 has marginal P(hosting R2) = 0.5 under equal win prob.

    Seed 1 always hosts R2 regardless of opponent (seeds 2-4 are all worse),
    so P(hosting R2) = P(win R1) × 1.0 = 0.5.
    """
    region = 1
    school = "R1s1"
    odds = {school: _locked(school, 1)}
    result = compute_second_round_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON)
    assert result[school] == pytest.approx(0.5, abs=1e-9)


def test_1a4a_seed4_never_hosts_r2() -> None:
    """In 1A-4A, locked seed 4 has marginal P(hosting R2) = 0.0.

    Seed 4 always faces a better-seeded opponent in R2 (seeds 2 or 3 from the
    adjacent slot), so P(hosting R2 | reaches R2) = 0.0 regardless of reach prob.
    """
    region = 2
    school = "R2s4"
    odds = {school: _locked(school, 4)}
    result = compute_second_round_home_odds(region, odds, SLOTS_1A_4A_2025, ODD_SEASON)
    assert result[school] == pytest.approx(0.0, abs=1e-9)


def test_1a4a_seed1_r2_hosting_exceeds_seed3() -> None:
    """In 1A-4A, seed 1's P(hosting R2) strictly exceeds seed 3's."""
    region = 1
    s1_odds = {"R1s1": _locked("R1s1", 1)}
    s3_odds = {"R1s3": _locked("R1s3", 3)}
    r1 = compute_second_round_home_odds(region, s1_odds, SLOTS_1A_4A_2025, ODD_SEASON)
    r3 = compute_second_round_home_odds(region, s3_odds, SLOTS_1A_4A_2025, ODD_SEASON)
    assert r1["R1s1"] > r3["R1s3"]


# ---------------------------------------------------------------------------
# marginal_home_odds
# ---------------------------------------------------------------------------


def test_marginal_home_odds_basic() -> None:
    """Marginal = conditional × advancement."""
    assert marginal_home_odds(0.75, 0.5) == pytest.approx(0.375)


def test_marginal_home_odds_zero_advancement() -> None:
    """Zero advancement produces zero marginal (team cannot reach the round)."""
    assert marginal_home_odds(1.0, 0.0) == pytest.approx(0.0)


def test_marginal_home_odds_full_certainty() -> None:
    """Both 100% → marginal is 100%."""
    assert marginal_home_odds(1.0, 1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Scenario 7: compute_bracket_advancement_odds — parity with compute_bracket_odds
# ---------------------------------------------------------------------------
#
# compute_bracket_advancement_odds traverses the actual bracket via
# _p_team_reach.  With equal_matchup_prob (P=0.5 every game), it must
# produce the same per-round advancement probabilities as compute_bracket_odds
# (the closed-form geometric formula p_playoffs × 0.5^r).
#
# 5A-7A (4 rounds): QF=0.5, SF=0.25, finals=0.125, champion=0.0625
# 1A-4A (5 rounds): R2=0.5, QF=0.25, SF=0.125, finals=0.0625, champion=0.03125
# (all probabilities for a locked seed with p_playoffs=1.0)


@pytest.mark.parametrize("seed", [1, 2, 3, 4], ids=["s1", "s2", "s3", "s4"])
def test_bracket_advancement_odds_matches_compute_bracket_odds_5a7a(seed: int) -> None:
    """compute_bracket_advancement_odds with equal_matchup_prob matches compute_bracket_odds for 5A-7A."""
    region = 1
    school = f"R{region}s{seed}"
    odds = {school: _locked(school, seed)}

    adv = compute_bracket_advancement_odds(region, odds, SLOTS_5A_7A_2025, equal_matchup_prob)
    simple = compute_bracket_odds(4, odds)

    assert adv[school].second_round == pytest.approx(simple[school].second_round, abs=1e-9)
    assert adv[school].quarterfinals == pytest.approx(simple[school].quarterfinals, abs=1e-9)
    assert adv[school].semifinals == pytest.approx(simple[school].semifinals, abs=1e-9)
    assert adv[school].finals == pytest.approx(simple[school].finals, abs=1e-9)
    assert adv[school].champion == pytest.approx(simple[school].champion, abs=1e-9)


@pytest.mark.parametrize("seed", [1, 2, 3, 4], ids=["s1", "s2", "s3", "s4"])
def test_bracket_advancement_odds_matches_compute_bracket_odds_1a4a(seed: int) -> None:
    """compute_bracket_advancement_odds with equal_matchup_prob matches compute_bracket_odds for 1A-4A."""
    region = 1
    school = f"R{region}s{seed}"
    odds = {school: _locked(school, seed)}

    adv = compute_bracket_advancement_odds(region, odds, SLOTS_1A_4A_2025, equal_matchup_prob)
    simple = compute_bracket_odds(5, odds)

    assert adv[school].second_round == pytest.approx(simple[school].second_round, abs=1e-9)
    assert adv[school].quarterfinals == pytest.approx(simple[school].quarterfinals, abs=1e-9)
    assert adv[school].semifinals == pytest.approx(simple[school].semifinals, abs=1e-9)
    assert adv[school].finals == pytest.approx(simple[school].finals, abs=1e-9)
    assert adv[school].champion == pytest.approx(simple[school].champion, abs=1e-9)


def test_marginal_home_odds_zero_conditional() -> None:
    """Zero conditional (team never hosts when they reach) → zero marginal."""
    assert marginal_home_odds(0.0, 0.5) == pytest.approx(0.0)


def test_marginal_home_odds_taylorsville_qf() -> None:
    """Spot-check against Taylorsville 2025 QF: 25% reach × 37.5% host = 9.375%."""
    assert marginal_home_odds(0.375, 0.25) == pytest.approx(0.09375)


# ---------------------------------------------------------------------------
# Scenario 8: _p_team_reach zero-wins shortcut (line 239)
# ---------------------------------------------------------------------------


def test_p_team_reach_zero_wins_returns_one() -> None:
    """_p_team_reach with num_wins=0 returns 1.0 immediately — line 239.

    Zero wins needed means the team has already reached this round; probability
    is 1.0 regardless of the bracket structure.
    """
    half = [SLOTS_5A_7A_2025[s] for s in range(4)]  # North half, indices 0-3
    result = _p_team_reach(1, 1, 0, 0, half, equal_matchup_prob)
    assert result == pytest.approx(1.0, abs=1e-9)


def test_p_team_reach_one_win_less_than_one() -> None:
    """Sanity check: num_wins=1 returns P(win R1) < 1.0 under equal prob."""
    half = [SLOTS_5A_7A_2025[s] for s in range(4)]
    result = _p_team_reach(1, 1, 0, 1, half, equal_matchup_prob)
    assert 0.0 < result < 1.0


# ---------------------------------------------------------------------------
# Scenario 9: _p_home_in_r2 equal-seed tiebreak (lines 339–342)
# ---------------------------------------------------------------------------
#
# Adjacent slot has home=R3s2 (equal seed to the target R1s2), away=R4s3.
# Under equal_matchup_prob each candidate has p_opp_r1=0.5.
#
# Odd year (2025): lower region# hosts.  R1 (region 1) < R3 (region 3) → R1 hosts
#   equal-seed case.  Also R4s3 (worse seed) → R1 hosts.  Total = 0.5 + 0.5 = 1.0
# Even year (2024): higher region# hosts.  R3 (region 3) > R1 (region 1) → R3 hosts
#   equal-seed case.  R4s3 → R1 still hosts (better seed).  Total = 0.0 + 0.5 = 0.5

_R2_EQUAL_SEED_SLOT = FormatSlot(
    slot=2, home_region=3, home_seed=2, away_region=4, away_seed=3, north_south="N"
)


def test_p_home_in_r2_equal_seed_odd_year() -> None:
    """Odd year: team with lower region# wins the equal-seed R2 hosting — lines 339–340."""
    result = _p_home_in_r2(
        team_seed=2, team_region=1,
        r2_opp_slot=_R2_EQUAL_SEED_SLOT,
        season=2025,
        win_prob_fn=equal_matchup_prob,
    )
    assert result == pytest.approx(1.0, abs=1e-9)


def test_p_home_in_r2_equal_seed_even_year() -> None:
    """Even year: team with lower region# loses the equal-seed hosting — lines 341–342."""
    result = _p_home_in_r2(
        team_seed=2, team_region=1,
        r2_opp_slot=_R2_EQUAL_SEED_SLOT,
        season=2024,
        win_prob_fn=equal_matchup_prob,
    )
    # Equal-seed opp (R3s2) → R3 hosts (even year); worse-seed opp (R4s3) → R1 hosts
    assert result == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Scenario 10: r2_home_team same-region + equal-seed tiebreak (lines 528, 534–537)
# ---------------------------------------------------------------------------


def test_r2_home_team_same_region_lower_seed_hosts() -> None:
    """Same-region R2: lower seed# (better seed) always hosts — line 528."""
    assert r2_home_team(1, 1, 1, 2, season=2025) == (1, 1)


def test_r2_home_team_same_region_higher_seed_input_reversed() -> None:
    """Same-region R2: result is the same regardless of argument order — line 528."""
    assert r2_home_team(1, 2, 1, 1, season=2025) == (1, 1)


def test_r2_home_team_equal_seed_odd_year_lower_region_hosts() -> None:
    """Equal cross-region seed, odd year: lower region# hosts — lines 534–536."""
    assert r2_home_team(1, 2, 3, 2, season=2025) == (1, 2)


def test_r2_home_team_equal_seed_even_year_higher_region_hosts() -> None:
    """Equal cross-region seed, even year: higher region# hosts — lines 534, 537."""
    assert r2_home_team(1, 2, 3, 2, season=2024) == (3, 2)


# ---------------------------------------------------------------------------
# Scenario 11: idx is None guard in all four compute functions (lines 667, 718, 768, 826)
# ---------------------------------------------------------------------------
#
# Synthetic 4-slot half where region 1 only has seeds 1 and 2.
# Passing region_odds for region 1 with p3=1.0 triggers _slot_index_for to
# return None (no slot contains R1s3), hitting the `continue` guard in every
# compute function.  With only seed-3 probability, the result is 0.0.

_IDX_NONE_SLOTS = [
    FormatSlot(slot=1, home_region=1, home_seed=1, away_region=2, away_seed=4, north_south="N"),
    FormatSlot(slot=2, home_region=1, home_seed=2, away_region=2, away_seed=3, north_south="N"),
    FormatSlot(slot=3, home_region=2, home_seed=1, away_region=3, away_seed=4, north_south="N"),
    FormatSlot(slot=4, home_region=3, home_seed=1, away_region=3, away_seed=2, north_south="N"),
]
_IDX_NONE_ODDS = {"TeamX": StandingsOdds(
    school="TeamX", p1=0.0, p2=0.0, p3=1.0, p4=0.0,
    p_playoffs=1.0, final_playoffs=1.0, clinched=False, eliminated=False,
)}


def test_idx_none_guard_second_round() -> None:
    """idx is None → skip; seed-3 not in bracket → P(hosting R2) = 0.0 — line 667."""
    result = compute_second_round_home_odds(1, _IDX_NONE_ODDS, _IDX_NONE_SLOTS, ODD_SEASON)
    assert result["TeamX"] == pytest.approx(0.0, abs=1e-9)


def test_idx_none_guard_quarterfinal() -> None:
    """idx is None → skip; seed-3 not in bracket → P(hosting QF) = 0.0 — line 718."""
    result = compute_quarterfinal_home_odds(1, _IDX_NONE_ODDS, _IDX_NONE_SLOTS, ODD_SEASON)
    assert result["TeamX"] == pytest.approx(0.0, abs=1e-9)


def test_idx_none_guard_semifinal() -> None:
    """idx is None → skip; seed-3 not in bracket → P(hosting SF) = 0.0 — line 768."""
    result = compute_semifinal_home_odds(1, _IDX_NONE_ODDS, _IDX_NONE_SLOTS, ODD_SEASON)
    assert result["TeamX"] == pytest.approx(0.0, abs=1e-9)


def test_idx_none_guard_bracket_advancement() -> None:
    """idx is None → skip; seed-3 not in bracket → all advancement probs 0.0 — line 826."""
    result = compute_bracket_advancement_odds(1, _IDX_NONE_ODDS, _IDX_NONE_SLOTS)
    bo = result["TeamX"]
    assert bo.quarterfinals == pytest.approx(0.0, abs=1e-9)
    assert bo.semifinals == pytest.approx(0.0, abs=1e-9)
