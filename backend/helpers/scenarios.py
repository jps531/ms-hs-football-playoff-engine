"""Scenario enumeration for region standings.

Enumerates all 2^R winner combinations for the remaining games (or, past 15
games, samples them: 50,000 runs per odds mode), resolves standings for each
(with margin-sensitive threshold detection unless margins are ignored), and
accumulates per-team per-seed counts. No Prefect or database dependencies.
"""

import hashlib
import logging
import math
import random
from collections import defaultdict
from itertools import permutations, product

from backend.helpers.certainty import NOISE, keep_uncertain
from backend.helpers.data_classes import (
    BracketOdds,
    CompletedGame,
    RemainingGame,
    ScenarioResults,
    StandingsOdds,
    WinProbFn,
    equal_win_prob,
)
from backend.helpers.engine_settings import PLAYOFF_SEEDS
from backend.helpers.tiebreakers import (
    rank_to_slots,
    resolve_standings_for_mask,
)

# -------------------------
# Formatting
# -------------------------


# -------------------------
# Scenario enumeration
# -------------------------


def _orderings(final_order: list[str], flip_groups: list[list[str]]) -> list[list[str]]:
    """Every ordering a set of coin flips can produce, each equally likely.

    Each tied group is permuted independently in place (cartesian product
    across groups). With no flips, the resolver's ordering is the only one.
    """
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
    return orderings


def _accumulate_pairs(
    final_order: list[str],
    flip_groups: list[list[str]],
    unweighted: float,
    weighted: float,
    pair_counts: dict[tuple[str, int, str, int], float],
    pair_counts_weighted: dict[tuple[str, int, str, int], float],
    playoff_seeds: int = PLAYOFF_SEEDS,
) -> None:
    """Credit every pair of playoff seeds in this outcome to its two teams.

    For each ordering (coin flips split evenly, as for the seed counts), each
    pair of the top ``playoff_seeds`` places adds its share under the key
    ``(team_a, seed_a, team_b, seed_b)`` with ``team_a < team_b``. Summed over
    outcomes and divided by the denominator, this is the probability that both
    teams land on those seeds together — what a bracket needs to say how
    likely two teams from one region are to meet.
    """
    orderings = _orderings(final_order, flip_groups)
    u_share = unweighted / len(orderings)
    w_share = weighted / len(orderings)
    for ordering in orderings:
        top = ordering[:playoff_seeds]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, sa, b, sb = top[i], i + 1, top[j], j + 1
                key = (a, sa, b, sb) if a < b else (b, sb, a, sa)
                pair_counts[key] = pair_counts.get(key, 0.0) + u_share
                pair_counts_weighted[key] = pair_counts_weighted.get(key, 0.0) + w_share


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
    pair_counts: dict[tuple[str, int, str, int], float] | None = None,
    pair_counts_weighted: dict[tuple[str, int, str, int], float] | None = None,
    places_seen: dict[str, set[int]] | None = None,
    open_groups: list[list[str]] | None = None,
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
        pair_counts, pair_counts_weighted: Optional same-region seed-pair
            counters (see ``_accumulate_pairs``), updated in-place.
        places_seen: Optional dict, updated in-place, of the places (1-4, and 5
            for out of the top four) each team can take: every place this branch
            gives (when it carries any unweighted credit), exact however small
            its share, so ``determine_odds`` can tell a certainty from a near one.
        open_groups: Tied groups whose order margins could change but this
            branch fixed (the 7-point default): each member is marked as able to
            take any place the group spans.
    """
    if pair_counts is not None and pair_counts_weighted is not None:
        _accumulate_pairs(final_order, flip_groups, unweighted, weighted, pair_counts, pair_counts_weighted)
    if not flip_groups:
        slots = rank_to_slots(final_order)
        if places_seen is not None and unweighted > 0:
            _mark_places(slots, open_groups, places_seen)
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
    orderings = _orderings(final_order, flip_groups)

    n = len(orderings)
    u_share = unweighted / n
    w_share = weighted / n
    for ordering in orderings:
        slots = rank_to_slots(ordering)
        if places_seen is not None and u_share > 0:
            _mark_places(slots, open_groups, places_seen)
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


def _mark_places(slots: dict, open_groups: list[list[str]] | None, places_seen: dict[str, set[int]]) -> None:
    """Record the places *slots* gives each team (5 for out of the top four), widened over *open_groups*.

    A team is credited the seeds its slot range covers (as the counts are) and 5 only when the
    range starts past 4; an open group's members can each take any place across the group's ranges.
    """

    def places(lo: int, hi: int) -> set[int]:
        """The places a slot range from *lo* to *hi* credits: the seeds it covers, or 5 when it starts past 4."""
        return {5} if lo > 4 else set(range(lo, min(hi, 4) + 1))

    for team, (lo, hi) in slots.items():
        places_seen.setdefault(team, set()).update(places(lo, hi))
    for group in open_groups or ():
        spans = [slots[t] for t in group if t in slots]
        if spans:
            lo, hi = min(a for a, _ in spans), max(b for _, b in spans)
            span = {min(k, 5) for k in range(lo, hi + 1)}
            for team in group:
                places_seen.setdefault(team, set()).update(span)


# How often each winning margin happens, 1-11 then 12 or more (the cap the point-differential
# steps use), from the 483 region games of 2025: most are won by 12 or more, and 6 and 7 (a
# touchdown) are the commonest close margins. A margin-sensitive result's margin combinations are
# weighted by these rather than evenly.
_MARGIN_COUNTS = (12, 10, 14, 14, 5, 25, 25, 13, 8, 9, 6, 342)
_MARGIN_SHARE = tuple(c / sum(_MARGIN_COUNTS) for c in _MARGIN_COUNTS)
# Projected odds go further: how often the winner wins by 12 or more depends on how big a favourite
# it was. The same 483 games, by the winner's pregame Elo chance, in bands of 38 to 107 games:
# (the band's chance, games, won by 12 or more), where a band's chance is the midpoint of each of
# its 5-point bins, weighted by the bin's games. A coin-flip game is won by 12 or more about
# half the time; a heavy favourite's win almost always is. Between bands the share is interpolated.
# Each band has too few close games to give 1 through 11 their own shape, so close margins keep the
# league-wide one (``_MARGIN_COUNTS`` without its last entry).
_BLOWOUTS_BY_WIN_PROB = (
    (0.247, 49, 22),
    (0.404, 38, 16),
    (0.498, 60, 31),
    (0.595, 54, 36),
    (0.701, 90, 64),
    (0.800, 85, 72),
    (0.907, 107, 101),
)
_CLOSE_SHARE = tuple(c / sum(_MARGIN_COUNTS[:-1]) for c in _MARGIN_COUNTS[:-1])


def projected_margin_share(p_winner: float) -> tuple[float, ...]:
    """How often a game is won by 1, 2, ..., 11, and 12 or more, when the winner had chance *p_winner*."""
    points = [(p, big / games) for p, games, big in _BLOWOUTS_BY_WIN_PROB]
    if p_winner <= points[0][0]:
        blowout = points[0][1]
    elif p_winner >= points[-1][0]:
        blowout = points[-1][1]
    else:
        (p0, b0), (p1, b1) = next((a, b) for a, b in zip(points, points[1:]) if a[0] <= p_winner <= b[0])
        blowout = b0 + (b1 - b0) * (p_winner - p0) / (p1 - p0)
    return tuple((1 - blowout) * s for s in _CLOSE_SHARE) + (blowout,)


# How many ways the scores of the remaining games are drawn for a result whose order turns on
# fewest points allowed (step 5) with a tied team still to play.
_PA_DRAWS = 64
# Score shapes for those draws, as 20 quantiles of the 2025 region games: the points the winner
# allows, the winning margin, and the winning margin when it's 12 or more (the enumeration's "12").
_WINNER_ALLOWS = (0, 0, 0, 0, 6, 6, 7, 7, 8, 12, 13, 14, 15, 17, 20, 21, 22, 26, 28, 35)
_MARGIN = (2, 4, 6, 7, 8, 10, 13, 17, 20, 22, 24, 27, 29, 33, 34, 36, 38, 42, 45, 50)
_MOST_POINTS = 60  # a high score, for the best and worst cases
_MARGIN_12_PLUS = (13, 15, 17, 20, 21, 22, 24, 26, 28, 29, 32, 33, 35, 35, 37, 39, 42, 44, 48, 53)


def _resolve_with_scores(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    outcome_mask: int,
    margins: dict,
    known_margins: frozenset = frozenset(),
    decisions_out: list | None = None,
) -> list[tuple[list[str], list[list[str]], float]]:
    """The seedings one result can give, each with its share: ``[(order, coin-flip groups, share)]``.

    Usually that's the resolver's one order. But when a tie reaches fewest points allowed (step 5)
    with a tied team still to play, the order turns on the actual scores, which a winner and margin
    don't fix: rather than settle it with one assumed score, the remaining games' scores are drawn
    ``_PA_DRAWS`` times from 2025's region games (the points the winner allows, and the margin: as
    given for games in ``known_margins``, a draw of 12 or more for those at 12, drawn for the rest)
    and each order gets its share. So an order only points allowed can give gets the small share it
    deserves, not none. The draws are seeded from the result, so the same inputs give the same odds.
    The resolver's tiebreaker decisions for the result are added to *decisions_out* when given.
    """
    decisions: list = []
    flips: list[list[str]] = []
    order = resolve_standings_for_mask(
        teams,
        completed,
        remaining,
        outcome_mask,
        margins=margins,
        base_margin_default=7,
        pa_win=14,
        coin_flip_collector=flips,
        decision_collector=decisions,
    )
    if decisions_out is not None:
        decisions_out.extend(decisions)
    in_play = {t for g in remaining for t in (g.a, g.b)}
    if not any(step == 5 and set(group) & in_play for step, group, _ in decisions):
        return [(order, flips, 1.0)]
    pairs = [(g.a, g.b) for g in remaining]
    tied = sorted({t for step, group, _ in decisions if step == 5 and set(group) & in_play for t in group})
    seed = outcome_mask * 1_000_003 + sum(margins.get(p, 7) * 13**i for i, p in enumerate(pairs))
    rng = random.Random(seed)  # NOSONAR

    def margin_range(pair) -> tuple[int, int]:
        """The fewest and most a game can be won by: its margin, or 12 and up for 12, or any if not given."""
        if pair not in known_margins:
            return 1, _MOST_POINTS
        m = margins.get(pair, 7)
        return (m, m) if m < 12 else (12, _MOST_POINTS)

    draws = []
    for _ in range(_PA_DRAWS):
        scores = {}
        for pair in pairs:
            allowed = rng.choice(_WINNER_ALLOWS)  # NOSONAR
            m = margins.get(pair, 7) if pair in known_margins else rng.choice(_MARGIN)  # NOSONAR
            if m >= 12 and pair in known_margins:
                m = rng.choice(_MARGIN_12_PLUS)  # NOSONAR
            scores[pair] = (allowed, allowed + m)
        draws.append(scores)
    # Plus, for each tied team, its best and worst case: it allows as few (or as many) points as it
    # can and everyone else as many (or as few), so a place it can only reach that way still counts.
    for team in tied:
        best, worst = {}, {}
        for i, pair in enumerate(pairs):
            lo, hi = margin_range(pair)
            winner = pair[0] if outcome_mask >> i & 1 else pair[1]
            if team == winner:
                best[pair], worst[pair] = (0, hi), (_MOST_POINTS, _MOST_POINTS + lo)
            elif team in pair:
                best[pair], worst[pair] = (0, lo), (_MOST_POINTS, _MOST_POINTS + hi)
            else:
                best[pair], worst[pair] = (_MOST_POINTS, _MOST_POINTS + hi), (0, lo)
        draws += [best, worst]
    out = []
    for scores in draws:
        draw_flips: list[list[str]] = []
        draw = resolve_standings_for_mask(
            teams,
            completed,
            remaining,
            outcome_mask,
            margins=margins,
            base_margin_default=7,
            pa_win=14,
            coin_flip_collector=draw_flips,
            points_allowed=scores,
        )
        out.append((draw, draw_flips, 1.0 / len(draws)))
    return out


def _monte_carlo_seed(teams: list[str], completed: list[CompletedGame], remaining: list[RemainingGame]) -> int:
    """Derive a stable RNG seed from a region's inputs.

    Hashes the sorted teams, completed games, and remaining games so the same
    inputs always produce the same seed, regardless of list order or process.
    Python's built-in ``hash()`` is salted per process, so SHA-256 is used.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.

    Returns:
        A 64-bit integer seed for ``random.Random``.
    """
    parts = [
        "teams:" + "|".join(sorted(teams)),
        "completed:" + "|".join(sorted(repr(g) for g in completed)),
        "remaining:" + "|".join(sorted(repr(g) for g in remaining)),
    ]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def determine_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    win_prob_fn: WinProbFn | None = None,
    ignore_margins: bool = False,
    n_samples: int | None = None,
    seed: int | None = None,
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
    enumeration is prohibitively slow.  Sampling is deterministic: the RNG is
    seeded from the inputs (or ``seed``) and games are drawn in a canonical
    order, so identical inputs always produce identical results.

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
        seed: Optional RNG seed for Monte Carlo sampling.  Defaults to a hash
            of ``teams``, ``completed``, and ``remaining``.

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
    seed_pairs: dict[tuple[str, int, str, int], float] = {}
    seed_pairs_weighted: dict[tuple[str, int, str, int], float] = {}
    places_seen: dict[str, set[int]] = {}
    in_play = {t for g in remaining for t in (g.a, g.b)}

    pa_for_winner = 14
    base_margins = {(rem_game.a, rem_game.b): 7 for rem_game in remaining}
    all_coinflip_events: list[list[str]] = []

    if num_remaining == 0:
        for final_order, local_flips, share in _resolve_with_scores(teams, completed, remaining, 0, {}, frozenset()):
            all_coinflip_events.extend(local_flips)
            _accumulate_slots(
                final_order,
                local_flips,
                share,
                share,
                first_counts,
                second_counts,
                third_counts,
                fourth_counts,
                first_counts_weighted,
                second_counts_weighted,
                third_counts_weighted,
                fourth_counts_weighted,
                seed_pairs,
                seed_pairs_weighted,
                places_seen=places_seen,
            )
        denom = 1.0
        denom_weighted = 1.0

    elif n_samples is not None:
        # Monte Carlo path: each game drawn Bernoulli(p), so sample frequency is
        # the probability by construction (each sample contributes 1.0 / n_samples).
        # Projected (weighted) counts sample from the win probabilities; Toss-up
        # (unweighted) counts get their own run with every game a coin flip, since
        # sampling from Elo would make the two modes identical. Without a
        # win_prob_fn the two runs would be the same, so one serves both.
        # Seeded RNGs plus a canonical game order keep results reproducible.
        mc_remaining = sorted(remaining, key=lambda g: (g.a, g.b, g.location_a or ""))
        base_seed = seed if seed is not None else _monte_carlo_seed(teams, completed, remaining)
        win_probs = [_win_prob_fn(g.a, g.b, None, g.location_a) for g in mc_remaining]
        runs = [(win_probs, 1.0, 1.0, base_seed)]
        if win_prob_fn is not None:
            runs = [(win_probs, 0.0, 1.0, base_seed), ([0.5] * len(mc_remaining), 1.0, 0.0, base_seed + 1)]
        for probs, unweighted_credit, weighted_credit, run_seed in runs:
            rng = random.Random(run_seed)  # NOSONAR
            for _ in range(n_samples):
                outcome_mask = 0
                for bit_index, p in enumerate(probs):
                    # Statistical Monte Carlo sampling only — not security-sensitive.
                    if rng.random() < p:  # NOSONAR
                        outcome_mask |= 1 << bit_index
                for final_order, local_flips, share in _resolve_with_scores(
                    teams, completed, mc_remaining, outcome_mask, base_margins, frozenset()
                ):
                    all_coinflip_events.extend(local_flips)
                    _accumulate_slots(
                        final_order,
                        local_flips,
                        unweighted_credit * share,
                        weighted_credit * share,
                        first_counts,
                        second_counts,
                        third_counts,
                        fourth_counts,
                        first_counts_weighted,
                        second_counts_weighted,
                        third_counts_weighted,
                        fourth_counts_weighted,
                        seed_pairs,
                        seed_pairs_weighted,
                        places_seen=places_seen,
                    )
        denom_weighted = float(n_samples)
        denom = float(n_samples)

    else:
        total_masks = 1 << num_remaining
        # P(a wins) per remaining game, and where each game sits in the outcome mask.
        game_probs = [_win_prob_fn(g.a, g.b, None, g.location_a) for g in remaining]
        game_index = {(g.a, g.b): i for i, g in enumerate(remaining)}
        for outcome_mask in range(total_masks):
            mask_weight = 1.0
            for bit_index, p in enumerate(game_probs):
                bit_value = (outcome_mask >> bit_index) & 1
                mask_weight *= p if bit_value else (1.0 - p)

            denom_weighted += mask_weight

            if ignore_margins:
                # Fast path: resolve once at the default margin, skip 12^N enumeration.
                # Odds are approximate (margin tiebreakers not tracked), consistent with
                # ignore_margins rendering mode. A tie that reaches point differential
                # (step 3) with a tied team still to play is left open for certainty:
                # another margin could reorder it, so none of its places is certain.
                decisions: list = []
                resolved = _resolve_with_scores(
                    teams, completed, remaining, outcome_mask, base_margins, frozenset(), decisions
                )
                open_groups = [list(group) for step, group, _ in decisions if step >= 3 and set(group) & in_play]
                for final_order, local_flips, share in resolved:
                    all_coinflip_events.extend(local_flips)
                    _accumulate_slots(
                        final_order,
                        local_flips,
                        share,
                        mask_weight * share,
                        first_counts,
                        second_counts,
                        third_counts,
                        fourth_counts,
                        first_counts_weighted,
                        second_counts_weighted,
                        third_counts_weighted,
                        fourth_counts_weighted,
                        seed_pairs,
                        seed_pairs_weighted,
                        places_seen=places_seen,
                        open_groups=open_groups,
                    )
                continue

            # Margins matter only to a tie that reaches point differential (step 3): which ties get
            # that far is settled by the winners alone (steps 1-2), and any group a later split
            # restarts is made of the same teams. Every remaining game such a team plays feeds its
            # point differential (steps 3-4) or points allowed (step 5), so all of them get every
            # margin; a game between two other teams can't move any of it.
            decisions: list = []
            resolve_standings_for_mask(
                teams,
                completed,
                remaining,
                outcome_mask,
                margins=base_margins,
                base_margin_default=7,
                pa_win=pa_for_winner,
                decision_collector=decisions,
            )
            tied = {t for step, group, _ in decisions if step >= 3 for t in group}
            intra_bucket_games = [rg for rg in remaining if rg.a in tied or rg.b in tied]
            if not intra_bucket_games:
                for final_order, local_flips, share in _resolve_with_scores(
                    teams, completed, remaining, outcome_mask, base_margins, frozenset()
                ):
                    all_coinflip_events.extend(local_flips)
                    _accumulate_slots(
                        final_order,
                        local_flips,
                        share,
                        mask_weight * share,
                        first_counts,
                        second_counts,
                        third_counts,
                        fourth_counts,
                        first_counts_weighted,
                        second_counts_weighted,
                        third_counts_weighted,
                        fourth_counts_weighted,
                        seed_pairs,
                        seed_pairs_weighted,
                        places_seen=places_seen,
                    )
            else:
                # Enumerate all 12^N margin combinations for intra-bucket games.
                # This correctly captures multi-game threshold interactions that the
                # old one-game-at-a-time isolation approach could miss (e.g. a
                # tiebreaker that only flips when Game A wins by 12+ AND Game B wins
                # by 1–6 simultaneously). Each combination counts as often as those
                # margins happen, not evenly: league-wide (``_MARGIN_SHARE``) for
                # toss-up odds, and by how big a favourite each winner was for
                # projected odds (``projected_margin_share``).
                intra_pairs = [(rg.a, rg.b) for rg in intra_bucket_games]
                n_intra = len(intra_pairs)
                projected_shares = [
                    projected_margin_share(
                        game_probs[game_index[pair]]
                        if (outcome_mask >> game_index[pair]) & 1
                        else 1.0 - game_probs[game_index[pair]]
                    )
                    if win_prob_fn is not None
                    else _MARGIN_SHARE
                    for pair in intra_pairs
                ]
                for margin_combo in product(range(1, 13), repeat=n_intra):
                    branch_margins = dict(base_margins)
                    for (a, b), m in zip(intra_pairs, margin_combo):
                        branch_margins[(a, b)] = m
                    branch_weight = math.prod(_MARGIN_SHARE[m - 1] for m in margin_combo)
                    effective_weight = mask_weight * math.prod(
                        shares[m - 1] for shares, m in zip(projected_shares, margin_combo)
                    )
                    for final_order, local_flips, share in _resolve_with_scores(
                        teams, completed, remaining, outcome_mask, branch_margins, frozenset(intra_pairs)
                    ):
                        all_coinflip_events.extend(local_flips)
                        _accumulate_slots(
                            final_order,
                            local_flips,
                            branch_weight * share,
                            effective_weight * share,
                            first_counts,
                            second_counts,
                            third_counts,
                            fourth_counts,
                            first_counts_weighted,
                            second_counts_weighted,
                            third_counts_weighted,
                            fourth_counts_weighted,
                            seed_pairs,
                            seed_pairs_weighted,
                            places_seen=places_seen,
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
        seed_pairs=seed_pairs,
        seed_pairs_weighted=seed_pairs_weighted,
        places_seen=places_seen,
        sampled=n_samples is not None,
    )


def compute_bracket_odds(
    num_rounds: int,
    odds: dict[str, StandingsOdds],
    rounds_completed: int = 0,
) -> dict[str, BracketOdds]:
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
        num_rounds:        Total playoff rounds for this class (4 for 5A–7A, 5 for 1A–4A).
        odds:              Dict mapping team name to ``StandingsOdds`` from ``determine_odds()``.
        rounds_completed:  Playoff rounds already played (0 during regular season).
                           Alive teams will show 1.0 for rounds already played and
                           correct forward-looking odds for remaining rounds.

    Returns:
        Dict mapping team name to ``BracketOdds``.
    """
    result: dict[str, BracketOdds] = {}
    for school, o in odds.items():
        p = o.p_playoffs
        # Wins still needed to reach each milestone; 0 means already there (→ 1.0).
        r2_wins   = max(0, 1              - rounds_completed)
        qf_wins   = max(0, (num_rounds-3) - rounds_completed)
        sf_wins   = max(0, (num_rounds-2) - rounds_completed)
        fin_wins  = max(0, (num_rounds-1) - rounds_completed)
        champ_wins = max(0, num_rounds    - rounds_completed)
        result[school] = BracketOdds(
            school=school,
            second_round=p * (0.5 ** r2_wins) if num_rounds >= 5 else 0.0,
            quarterfinals=p * (0.5 ** qf_wins),
            semifinals=p * (0.5 ** sf_wins),
            finals=p * (0.5 ** fin_wins),
            champion=p * (0.5 ** champ_wins),
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


# Uncertain odds are rounded past the float noise of summing thousands of shares (~1e-14), so that
# noise never orders two level teams.
_ODDS_DIGITS = 12


def _tidy(p: float) -> float:
    """A chance known not to be certain, rounded past float noise and kept uncertain."""
    return keep_uncertain(round(p, _ODDS_DIGITS))


def determine_odds(
    teams,
    first_counts,
    second_counts,
    third_counts,
    fourth_counts,
    denom,
    *,
    places_seen: dict[str, set[int]] | None = None,
    sampled: bool = False,
):
    """Convert accumulated seed counts into probability odds for each team.

    Computes per-team probabilities for finishing 1st through 4th, combined
    playoff odds, and clinch/elimination flags.

    A chance is 0 or 1 only when the enumeration proves it (see ``certainty``):
    from *places_seen*, the places each team can take (5 for out of the top
    four), a seed it can't take is 0, the only place it can take is 1, and a
    playoff spot is 1 when it can't finish out. Every other chance is kept
    uncertain, however small, and none is certain when the counts are
    *sampled*. Both odds modes use the same places, so they land on the same
    certainties.

    Args:
        teams: List of all team names in the region.
        first_counts: Counter mapping team -> weighted count of 1st-seed outcomes.
        second_counts: Counter mapping team -> weighted count of 2nd-seed outcomes.
        third_counts: Counter mapping team -> weighted count of 3rd-seed outcomes.
        fourth_counts: Counter mapping team -> weighted count of 4th-seed outcomes.
        denom: Total number of equally-weighted outcomes (divisor for
            probabilities).
        places_seen: ``ScenarioResults.places_seen``; without it, certainty is
            read off the counts (a count of 0 is impossible, a total within float
            noise of 1 certain).
        sampled: ``ScenarioResults.sampled``.

    Returns:
        A dict mapping each team name to a StandingsOdds instance.
    """
    counts = (first_counts, second_counts, third_counts, fourth_counts)
    odds: dict[str, StandingsOdds] = {}
    for school in teams:
        raw = [c.get(school, 0.0) / denom for c in counts]
        if sampled:
            p1, p2, p3, p4 = (_tidy(p) for p in raw)
            p_playoffs = _tidy(sum(raw))
        elif places_seen is not None:
            seen = places_seen.get(school, set())
            p1, p2, p3, p4 = (
                (1.0 if seen == {k} else _tidy(p)) if k in seen else 0.0 for k, p in enumerate(raw, start=1)
            )
            if not seen - {5}:
                p_playoffs = 0.0
            else:
                p_playoffs = _tidy(sum(raw)) if 5 in seen else 1.0
        else:
            p1, p2, p3, p4 = (_from_counts(p) for p in raw)
            p_playoffs = _from_counts(sum(raw))
        clinched = p_playoffs == 1.0
        eliminated = p_playoffs == 0.0
        if clinched:
            final_playoffs = 1.0
        elif eliminated:
            final_playoffs = 0.0
        else:
            final_playoffs = p_playoffs
        odds[school] = StandingsOdds(school, p1, p2, p3, p4, p_playoffs, final_playoffs, clinched, eliminated)
    return odds


def _from_counts(p: float) -> float:
    """A chance read off counts alone: 0 only for a count of 0, 1 within float noise of it, else kept uncertain."""
    if p <= 0:
        return 0.0
    return 1.0 if p >= 1 - NOISE else _tidy(p)


def odds_from_results(teams, r: ScenarioResults) -> tuple[dict[str, StandingsOdds], dict[str, StandingsOdds]]:
    """Toss-up and Projected odds from one ``determine_scenarios`` result."""
    exact = {"places_seen": r.places_seen, "sampled": r.sampled}
    odds = determine_odds(teams, r.first_counts, r.second_counts, r.third_counts, r.fourth_counts, r.denom, **exact)
    odds_weighted = determine_odds(
        teams,
        r.first_counts_weighted,
        r.second_counts_weighted,
        r.third_counts_weighted,
        r.fourth_counts_weighted,
        r.denom_weighted,
        **exact,
    )
    return odds, odds_weighted
