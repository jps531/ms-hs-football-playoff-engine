"""Scenario enumeration for region standings.

Enumerates all 2^R outcome combinations for remaining games, resolves standings
for each using margin-sensitive threshold detection, and accumulates per-team
per-seed counts. No Prefect or database dependencies.
"""

import logging
from collections import Counter
from itertools import product

from prefect import get_run_logger
from prefect.exceptions import MissingContextError

from backend.helpers.data_classes import (
    BracketOdds,
    CompletedGame,
    RemainingGame,
    ScenarioResults,
    StandingsOdds,
    WinProbFn,
    equal_win_prob,
)
from backend.helpers.tiebreakers import (
    rank_to_slots,
    resolve_standings_for_mask,
    sensitive_boundary_games,
    standings_from_mask,
    tie_bucket_groups,
    unique_intra_bucket_games,
)

# -------------------------
# Formatting
# -------------------------


def pct_str(x: float) -> str:
    """Format a float as a percentage string with no more than 2 significant digits.

    Args:
        x: A probability in the range [0, 1].

    Returns:
        A string like ``"50%"`` or ``"33%"``.
    """
    val = x * 100.0
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.0f}%".rstrip("0").rstrip(".")


# -------------------------
# Scenario enumeration
# -------------------------


def determine_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    debug: bool = False,
    win_prob_fn: WinProbFn | None = None,
) -> ScenarioResults:
    """Enumerate all seeding scenarios for a region and compute seed-count totals.

    Iterates over all 2^R outcome masks for remaining games.  For each mask,
    resolves the full region standings (including margin-sensitive threshold
    detection for intra-bucket games) and accumulates per-team per-seed counts.

    Both unweighted (equal-probability) counts and win-probability-weighted
    counts are accumulated in a single pass.  When ``win_prob_fn`` is None,
    ``equal_win_prob`` is used, making weighted == unweighted / 2^R (i.e.
    ``denom_weighted == 1.0``).

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        debug: Reserved for future use (currently unused).
        win_prob_fn: Optional callable ``(team_a, team_b, date) -> float``
            returning the probability that ``team_a`` beats ``team_b``.
            Defaults to ``equal_win_prob`` (50/50).

    Returns:
        A ``ScenarioResults`` instance with unweighted and weighted seed counts,
        the scenario denominator, and the set of team names that required a
        coin flip in at least one outcome.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger("scenarios")
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

    _win_prob_fn = win_prob_fn if win_prob_fn is not None else equal_win_prob

    num_remaining = len(remaining)

    first_counts: Counter = Counter()
    second_counts: Counter = Counter()
    third_counts: Counter = Counter()
    fourth_counts: Counter = Counter()
    first_counts_weighted: Counter = Counter()
    second_counts_weighted: Counter = Counter()
    third_counts_weighted: Counter = Counter()
    fourth_counts_weighted: Counter = Counter()
    denom_weighted: float = 0.0

    pa_for_winner = 14
    base_margins = {(rem_game.a, rem_game.b): 7 for rem_game in remaining}
    all_coinflip_events: list[list[str]] = []

    if num_remaining == 0:
        final_order = resolve_standings_for_mask(
            teams,
            completed,
            remaining,
            0,
            margins={},
            base_margin_default=7,
            pa_win=pa_for_winner,
            coin_flip_collector=all_coinflip_events,
            debug=debug,
        )
        slots = rank_to_slots(final_order)
        for team, (lo_seed, hi_seed) in slots.items():
            if 1 >= lo_seed and 1 <= hi_seed:
                first_counts[team] += 1
                first_counts_weighted[team] += 1
            if 2 >= lo_seed and 2 <= hi_seed:
                second_counts[team] += 1
                second_counts_weighted[team] += 1
            if 3 >= lo_seed and 3 <= hi_seed:
                third_counts[team] += 1
                third_counts_weighted[team] += 1
            if 4 >= lo_seed and 4 <= hi_seed:
                fourth_counts[team] += 1
                fourth_counts_weighted[team] += 1
        denom = 1.0
        denom_weighted = 1.0

    else:
        total_masks = 1 << num_remaining
        for outcome_mask in range(total_masks):
            mask_weight = 1.0
            for bit_index, rem_game in enumerate(remaining):
                bit_value = (outcome_mask >> bit_index) & 1
                p = _win_prob_fn(rem_game.a, rem_game.b, None)
                mask_weight *= p if bit_value else (1.0 - p)

            denom_weighted += mask_weight

            wl_totals = standings_from_mask(
                teams,
                completed,
                remaining,
                outcome_mask,
                pa_for_winner,
                base_margins,
                base_margin_default=7,
            )
            tie_buckets = tie_bucket_groups(teams, wl_totals)
            intra_bucket_games = unique_intra_bucket_games(tie_buckets, remaining)
            if intra_bucket_games:
                # Also include boundary games (bucket team vs. outside team) whose
                # margin is sensitive to the tiebreaker outcome under 12^N enumeration.
                boundary = sensitive_boundary_games(
                    tie_buckets, remaining, intra_bucket_games,
                    teams, completed, outcome_mask, base_margins, pa_for_winner,
                )
                if boundary:
                    intra_bucket_games = intra_bucket_games + boundary
            if not intra_bucket_games:
                final_order = resolve_standings_for_mask(
                    teams,
                    completed,
                    remaining,
                    outcome_mask,
                    margins=base_margins,
                    base_margin_default=7,
                    pa_win=pa_for_winner,
                    coin_flip_collector=all_coinflip_events,
                )
                slots = rank_to_slots(final_order)
                for team, (lo_seed, hi_seed) in slots.items():
                    if 1 >= lo_seed and 1 <= hi_seed:
                        first_counts[team] += 1
                        first_counts_weighted[team] += mask_weight  # type: ignore
                    if 2 >= lo_seed and 2 <= hi_seed:
                        second_counts[team] += 1
                        second_counts_weighted[team] += mask_weight  # type: ignore
                    if 3 >= lo_seed and 3 <= hi_seed:
                        third_counts[team] += 1
                        third_counts_weighted[team] += mask_weight  # type: ignore
                    if 4 >= lo_seed and 4 <= hi_seed:
                        fourth_counts[team] += 1
                        fourth_counts_weighted[team] += mask_weight  # type: ignore
            else:
                # Enumerate all 12^N margin combinations for intra-bucket games.
                # This correctly captures multi-game threshold interactions that the
                # old one-game-at-a-time isolation approach could miss (e.g. a
                # tiebreaker that only flips when Game A wins by 12+ AND Game B wins
                # by 1–6 simultaneously).
                intra_pairs = [(rg.a, rg.b) for rg in intra_bucket_games]
                n_intra = len(intra_pairs)
                total_combos = 12 ** n_intra
                for margin_combo in product(range(1, 13), repeat=n_intra):
                    branch_margins = dict(base_margins)
                    for (a, b), m in zip(intra_pairs, margin_combo):
                        branch_margins[(a, b)] = m
                    branch_weight = 1.0 / total_combos
                    effective_weight = mask_weight * branch_weight
                    final_order = resolve_standings_for_mask(
                        teams,
                        completed,
                        remaining,
                        outcome_mask,
                        margins=branch_margins,
                        base_margin_default=7,
                        pa_win=pa_for_winner,
                        coin_flip_collector=all_coinflip_events,
                    )
                    slots = rank_to_slots(final_order)
                    for team, (lo_seed, hi_seed) in slots.items():
                        if 1 >= lo_seed and 1 <= hi_seed:
                            first_counts[team] += branch_weight  # type: ignore
                            first_counts_weighted[team] += effective_weight  # type: ignore
                        if 2 >= lo_seed and 2 <= hi_seed:
                            second_counts[team] += branch_weight  # type: ignore
                            second_counts_weighted[team] += effective_weight  # type: ignore
                        if 3 >= lo_seed and 3 <= hi_seed:
                            third_counts[team] += branch_weight  # type: ignore
                            third_counts_weighted[team] += effective_weight  # type: ignore
                        if 4 >= lo_seed and 4 <= hi_seed:
                            fourth_counts[team] += branch_weight  # type: ignore
                            fourth_counts_weighted[team] += effective_weight  # type: ignore

        denom = float(1 << num_remaining)

    coinflip_teams: set[str] = {team for group in all_coinflip_events for team in group}
    return ScenarioResults(
        first_counts=first_counts,
        second_counts=second_counts,
        third_counts=third_counts,
        fourth_counts=fourth_counts,
        denom=denom,
        coinflip_teams=coinflip_teams,
        first_counts_weighted=first_counts_weighted,
        second_counts_weighted=second_counts_weighted,
        third_counts_weighted=third_counts_weighted,
        fourth_counts_weighted=fourth_counts_weighted,
        denom_weighted=denom_weighted,
    )


def compute_bracket_odds(num_rounds: int, odds: dict[str, StandingsOdds]) -> dict[str, BracketOdds]:
    """Compute each team's probability of advancing to successive playoff rounds.

    Uses equal win probability (50/50) for every bracket game, making the
    calculation exact: P(reach round r+1) = p_playoffs × 0.5^r.

    Column semantics (aligned with round counts per class):

    * ``second_round``  — the extra early round that only 1A–4A has (0.0 for 5A–7A)
    * ``quarterfinals`` — P(playing when 8 teams remain): round 2 for 5A–7A, round 3 for 1A–4A
    * ``semifinals``    — P(playing the N/S championship): round 3 for 5A–7A, round 4 for 1A–4A
    * ``finals``        — P(playing the state championship)
    * ``champion``      — P(winning the state championship)

    Args:
        num_rounds: Total playoff rounds for this class (4 for 5A–7A, 5 for 1A–4A).
        odds: Dict mapping team name to ``StandingsOdds`` from ``determine_odds()``.

    Returns:
        Dict mapping team name to ``BracketOdds``.
    """
    result: dict[str, BracketOdds] = {}
    for school, o in odds.items():
        p = o.p_playoffs
        result[school] = BracketOdds(
            school=school,
            # second_round only exists for classes with 5 rounds (1A–4A)
            second_round=p * 0.5 if num_rounds >= 5 else 0.0,
            # quarterfinals = the round where 8 teams remain
            quarterfinals=p * (0.5 ** (num_rounds - 3)),
            semifinals=p * (0.5 ** (num_rounds - 2)),
            finals=p * (0.5 ** (num_rounds - 1)),
            champion=p * (0.5 ** num_rounds),
        )
    return result


def compute_first_round_home_odds(
    home_seeds: frozenset[int],
    odds: dict[str, StandingsOdds],
) -> dict[str, float]:
    """Compute each team's probability of hosting their first-round playoff game.

    For a team in a given region, the probability of hosting equals the sum of
    seeding probabilities for seeds that are designated as home in round 1.
    Teams that miss the playoffs have p1=p2=p3=p4=0 and therefore get 0.0.

    Args:
        home_seeds: Set of seed numbers (1–4) for which the team's region is
            the designated home team in the first round.  Typically ``{1, 2}``
            under current MHSAA rules.
        odds: Dict mapping team name to ``StandingsOdds`` from
            ``determine_odds()``.

    Returns:
        Dict mapping team name to probability of hosting round 1 (0.0–1.0).
    """
    result: dict[str, float] = {}
    for school, o in odds.items():
        p = 0.0
        if 1 in home_seeds:
            p += o.p1
        if 2 in home_seeds:
            p += o.p2
        if 3 in home_seeds:
            p += o.p3
        if 4 in home_seeds:
            p += o.p4
        result[school] = p
    return result


def determine_odds(teams, first_counts, second_counts, third_counts, fourth_counts, denom):
    """Convert accumulated seed counts into probability odds for each team.

    Computes per-team probabilities for finishing 1st through 4th, combined
    playoff odds, and clinch/elimination flags.

    Args:
        teams: List of all team names in the region.
        first_counts: Counter mapping team -> weighted count of 1st-seed outcomes.
        second_counts: Counter mapping team -> weighted count of 2nd-seed outcomes.
        third_counts: Counter mapping team -> weighted count of 3rd-seed outcomes.
        fourth_counts: Counter mapping team -> weighted count of 4th-seed outcomes.
        denom: Total number of equally-weighted outcomes (divisor for
            probabilities).

    Returns:
        A dict mapping each team name to a StandingsOdds instance.
    """
    odds: dict[str, StandingsOdds] = {}
    for school in teams:
        p1 = first_counts[school] / denom
        p2 = second_counts[school] / denom
        p3 = third_counts[school] / denom
        p4 = fourth_counts[school] / denom
        p_playoffs = p1 + p2 + p3 + p4
        clinched = p_playoffs >= 0.999
        eliminated = p_playoffs <= 0.001
        if clinched:
            final_playoffs = 1.0
        elif eliminated:
            final_playoffs = 0.0
        else:
            final_playoffs = p_playoffs
        odds[school] = StandingsOdds(school, p1, p2, p3, p4, p_playoffs, final_playoffs, clinched, eliminated)
    return odds
