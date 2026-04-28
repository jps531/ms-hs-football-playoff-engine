"""Scenario enumeration for region standings.

Enumerates all 2^R outcome combinations for remaining games, resolves standings
for each using margin-sensitive threshold detection, and accumulates per-team
per-seed counts. No Prefect or database dependencies.
"""

import logging
import random
from collections import defaultdict
from itertools import permutations, product

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


def _accumulate_slots(
    final_order: list[str],
    flip_groups: list[list[str]],
    unweighted: float,
    weighted: float,
    first_counts: defaultdict[str, float],
    second_counts: defaultdict[str, float],
    third_counts: defaultdict[str, float],
    fourth_counts: defaultdict[str, float],
    first_counts_weighted: defaultdict[str, float],
    second_counts_weighted: defaultdict[str, float],
    third_counts_weighted: defaultdict[str, float],
    fourth_counts_weighted: defaultdict[str, float],
) -> None:
    """Accumulate seed counts into counters, distributing evenly over coin-flip permutations.

    When ``flip_groups`` is empty the full ``unweighted`` / ``weighted`` amounts are
    credited to the single ordering returned by the resolver.  When one or more coin-flip
    groups are present, the weight is split equally across all permutations of each
    independent group (cartesian product across groups), so every flip outcome gets its
    fair share rather than 100% going to the alphabetically-first proxy ordering.

    Args:
        final_order: The ordered team list returned by ``resolve_standings_for_mask``.
        flip_groups: Tied groups that were resolved by coin flip (from the collector).
        unweighted: Unweighted credit for this (mask, margin-combo) branch.
        weighted: Win-probability-weighted credit for this branch.
        first_counts … fourth_counts_weighted: Counters to update in-place.
    """
    if not flip_groups:
        slots = rank_to_slots(final_order)
        for team, (lo, hi) in slots.items():
            if lo <= 1 <= hi:
                first_counts[team] += unweighted
                first_counts_weighted[team] += weighted
            if lo <= 2 <= hi:
                second_counts[team] += unweighted
                second_counts_weighted[team] += weighted
            if lo <= 3 <= hi:
                third_counts[team] += unweighted
                third_counts_weighted[team] += weighted
            if lo <= 4 <= hi:
                fourth_counts[team] += unweighted
                fourth_counts_weighted[team] += weighted
        return

    # Build all orderings by permuting each flip group independently.
    orderings: list[list[str]] = [list(final_order)]
    for group in flip_groups:
        expanded: list[list[str]] = []
        for current in orderings:
            positions = [current.index(t) for t in group]
            for perm in permutations(group):
                new = list(current)
                for pos, team in zip(positions, perm):
                    new[pos] = team
                expanded.append(new)
        orderings = expanded

    n = len(orderings)
    u_share = unweighted / n
    w_share = weighted / n
    for ordering in orderings:
        slots = rank_to_slots(ordering)
        for team, (lo, hi) in slots.items():
            if lo <= 1 <= hi:
                first_counts[team] += u_share
                first_counts_weighted[team] += w_share
            if lo <= 2 <= hi:
                second_counts[team] += u_share
                second_counts_weighted[team] += w_share
            if lo <= 3 <= hi:
                third_counts[team] += u_share
                third_counts_weighted[team] += w_share
            if lo <= 4 <= hi:
                fourth_counts[team] += u_share
                fourth_counts_weighted[team] += w_share


def determine_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    win_prob_fn: WinProbFn | None = None,
    ignore_margins: bool = False,
    n_samples: int | None = None,
) -> ScenarioResults:
    """Enumerate all seeding scenarios for a region and compute seed-count totals.

    Iterates over all 2^R outcome masks for remaining games.  For each mask,
    resolves the full region standings (including margin-sensitive threshold
    detection for intra-bucket games) and accumulates per-team per-seed counts.

    Both unweighted (equal-probability) counts and win-probability-weighted
    counts are accumulated in a single pass.  When ``win_prob_fn`` is None,
    ``equal_win_prob`` is used, making weighted == unweighted / 2^R (i.e.
    ``denom_weighted == 1.0``).

    When ``n_samples`` is set, uses Monte Carlo sampling instead of full 2^R
    enumeration.  Each sample draws outcomes from Bernoulli(p) per game using
    ``win_prob_fn``, so sample frequency is Elo-weighted by construction.
    Implies ``ignore_margins=True``.  Use for large R (>15) where 2^R full
    enumeration is prohibitively slow.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        win_prob_fn: Optional callable ``(team_a, team_b, date) -> float``
            returning the probability that ``team_a`` beats ``team_b``.
            Defaults to ``equal_win_prob`` (50/50).
        ignore_margins: When True, skip margin-sensitive tiebreaker enumeration
            entirely.  Each mask is resolved once at the default margin (7) and
            treated as non-sensitive.  Use for large R (≥8) where full 12^N
            enumeration is prohibitively slow.  Odds are approximate — margin
            tiebreakers are not tracked — but correct for display in
            ``ignore_margins`` rendering mode.
        n_samples: When set, use Monte Carlo sampling with this many draws
            instead of exhaustive 2^R enumeration.  Forces ``ignore_margins``.

    Returns:
        A ``ScenarioResults`` instance with unweighted and weighted seed counts,
        the scenario denominator, and the set of team names that required a
        coin flip in at least one outcome.
    """
    try:
        from prefect import get_run_logger

        logger = get_run_logger()
    except Exception:
        logger = logging.getLogger("scenarios")
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

    _win_prob_fn = win_prob_fn if win_prob_fn is not None else equal_win_prob

    num_remaining = len(remaining)

    first_counts: defaultdict[str, float] = defaultdict(float)
    second_counts: defaultdict[str, float] = defaultdict(float)
    third_counts: defaultdict[str, float] = defaultdict(float)
    fourth_counts: defaultdict[str, float] = defaultdict(float)
    first_counts_weighted: defaultdict[str, float] = defaultdict(float)
    second_counts_weighted: defaultdict[str, float] = defaultdict(float)
    third_counts_weighted: defaultdict[str, float] = defaultdict(float)
    fourth_counts_weighted: defaultdict[str, float] = defaultdict(float)
    denom_weighted: float = 0.0

    pa_for_winner = 14
    base_margins = {(rem_game.a, rem_game.b): 7 for rem_game in remaining}
    all_coinflip_events: list[list[str]] = []

    if num_remaining == 0:
        local_flips: list[list[str]] = []
        final_order = resolve_standings_for_mask(
            teams,
            completed,
            remaining,
            0,
            margins={},
            base_margin_default=7,
            pa_win=pa_for_winner,
            coin_flip_collector=local_flips,
        )
        all_coinflip_events.extend(local_flips)
        _accumulate_slots(
            final_order,
            local_flips,
            1.0,
            1.0,
            first_counts,
            second_counts,
            third_counts,
            fourth_counts,
            first_counts_weighted,
            second_counts_weighted,
            third_counts_weighted,
            fourth_counts_weighted,
        )
        denom = 1.0
        denom_weighted = 1.0

    elif n_samples is not None:
        # Monte Carlo path: sample outcomes from the Elo joint distribution.
        # Each game is drawn Bernoulli(p); sample frequency is Elo-weighted by
        # construction, so weighted and unweighted counts are both accumulated
        # uniformly (each sample contributes weight 1.0 / n_samples).
        for _ in range(n_samples):
            outcome_mask = 0
            for bit_index, rem_game in enumerate(remaining):
                p = _win_prob_fn(rem_game.a, rem_game.b, None, rem_game.location_a)
                if random.random() < p:
                    outcome_mask |= 1 << bit_index
            local_flips: list[list[str]] = []
            final_order = resolve_standings_for_mask(
                teams,
                completed,
                remaining,
                outcome_mask,
                margins=base_margins,
                base_margin_default=7,
                pa_win=pa_for_winner,
                coin_flip_collector=local_flips,
            )
            all_coinflip_events.extend(local_flips)
            _accumulate_slots(
                final_order,
                local_flips,
                1.0,
                1.0,
                first_counts,
                second_counts,
                third_counts,
                fourth_counts,
                first_counts_weighted,
                second_counts_weighted,
                third_counts_weighted,
                fourth_counts_weighted,
            )
            denom_weighted += 1.0
        denom = float(n_samples)

    else:
        total_masks = 1 << num_remaining
        for outcome_mask in range(total_masks):
            mask_weight = 1.0
            for bit_index, rem_game in enumerate(remaining):
                bit_value = (outcome_mask >> bit_index) & 1
                p = _win_prob_fn(rem_game.a, rem_game.b, None, rem_game.location_a)
                mask_weight *= p if bit_value else (1.0 - p)

            denom_weighted += mask_weight

            if ignore_margins:
                # Fast path: resolve once at the default margin, skip 12^N enumeration.
                # Odds are approximate (margin tiebreakers not tracked), consistent with
                # ignore_margins rendering mode.
                local_flips: list[list[str]] = []
                final_order = resolve_standings_for_mask(
                    teams,
                    completed,
                    remaining,
                    outcome_mask,
                    margins=base_margins,
                    base_margin_default=7,
                    pa_win=pa_for_winner,
                    coin_flip_collector=local_flips,
                )
                all_coinflip_events.extend(local_flips)
                _accumulate_slots(
                    final_order,
                    local_flips,
                    1.0,
                    mask_weight,
                    first_counts,
                    second_counts,
                    third_counts,
                    fourth_counts,
                    first_counts_weighted,
                    second_counts_weighted,
                    third_counts_weighted,
                    fourth_counts_weighted,
                )
                continue

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
                    tie_buckets,
                    remaining,
                    intra_bucket_games,
                    teams,
                    completed,
                    outcome_mask,
                    base_margins,
                    pa_for_winner,
                )
                if boundary:
                    intra_bucket_games = intra_bucket_games + boundary
            if not intra_bucket_games:
                local_flips = []
                final_order = resolve_standings_for_mask(
                    teams,
                    completed,
                    remaining,
                    outcome_mask,
                    margins=base_margins,
                    base_margin_default=7,
                    pa_win=pa_for_winner,
                    coin_flip_collector=local_flips,
                )
                all_coinflip_events.extend(local_flips)
                _accumulate_slots(
                    final_order,
                    local_flips,
                    1.0,
                    mask_weight,
                    first_counts,
                    second_counts,
                    third_counts,
                    fourth_counts,
                    first_counts_weighted,
                    second_counts_weighted,
                    third_counts_weighted,
                    fourth_counts_weighted,
                )
            else:
                # Enumerate all 12^N margin combinations for intra-bucket games.
                # This correctly captures multi-game threshold interactions that the
                # old one-game-at-a-time isolation approach could miss (e.g. a
                # tiebreaker that only flips when Game A wins by 12+ AND Game B wins
                # by 1–6 simultaneously).
                intra_pairs = [(rg.a, rg.b) for rg in intra_bucket_games]
                n_intra = len(intra_pairs)
                total_combos = 12**n_intra
                for margin_combo in product(range(1, 13), repeat=n_intra):
                    branch_margins = dict(base_margins)
                    for (a, b), m in zip(intra_pairs, margin_combo):
                        branch_margins[(a, b)] = m
                    branch_weight = 1.0 / total_combos
                    effective_weight = mask_weight * branch_weight
                    local_flips = []
                    final_order = resolve_standings_for_mask(
                        teams,
                        completed,
                        remaining,
                        outcome_mask,
                        margins=branch_margins,
                        base_margin_default=7,
                        pa_win=pa_for_winner,
                        coin_flip_collector=local_flips,
                    )
                    all_coinflip_events.extend(local_flips)
                    _accumulate_slots(
                        final_order,
                        local_flips,
                        branch_weight,
                        effective_weight,
                        first_counts,
                        second_counts,
                        third_counts,
                        fourth_counts,
                        first_counts_weighted,
                        second_counts_weighted,
                        third_counts_weighted,
                        fourth_counts_weighted,
                    )

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
            champion=p * (0.5**num_rounds),
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
        p1 = first_counts.get(school, 0.0) / denom
        p2 = second_counts.get(school, 0.0) / denom
        p3 = third_counts.get(school, 0.0) / denom
        p4 = fourth_counts.get(school, 0.0) / denom
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
