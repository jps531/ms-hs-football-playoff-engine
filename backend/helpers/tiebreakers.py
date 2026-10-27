"""Pure tiebreaker logic for MHSAA region standings.

Implements the 6-step tiebreaker sequence (H2H record -> vs-outside record ->
H2H capped PD -> capped PD vs outside -> fewest PA in all region games -> coin
flip), per the MHSAA handbook. No Prefect or database dependencies.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from backend.helpers.data_helpers import normalize_pair


@dataclass(frozen=True)
class TiebreakStep:
    """One step the tiebreaker applied to one tied group, as recorded by ``trace_collector``.

    ``step`` is 1-6; ``group`` the tied teams it was applied to (sorted); ``parts`` those teams in
    the order the step put them, best first, teams it left level together (each part sorted; a
    single part means the step didn't separate them). ``values`` is what the step compared for each
    team: step 1 head-to-head points among the group (a win 1, a tie 0.5), step 2 the results
    against each of ``outside`` (a win 2, a tie 1, a loss 0, summed over a group's teams; None when
    the team played none of them), step 3 the capped head-to-head point differential, step 4 the
    capped point differential against each of ``outside`` (None when no game), step 5 points allowed
    in all region games. ``outside`` (steps 2 and 4) is the teams outside the tie, best first: a
    team already placed on its own, teams level on record together. Step 6, the coin flip, has one
    part and no values.
    """

    step: int
    group: tuple[str, ...]
    parts: tuple[tuple[str, ...], ...]
    values: dict = field(default_factory=dict)
    outside: tuple[tuple[str, ...], ...] = ()

# -------------------------
# Step 5 accumulation + W/L/T
# -------------------------


def standings_from_mask(
    teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default=7, points_allowed=None
):
    """Compute W/L/T and PA for all teams for a given outcome mask.

    Implements Step 5 (PA accumulation) by tallying completed game results and
    projecting remaining game results from the bitmask.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        outcome_mask: Bitmask where bit i=1 means remaining[i].a wins.
        pa_win: Points assumed scored against the winner in a remaining game
            (used for Steps 5/6 PA tiebreaker projection).
        margins: Dict keyed by (team_a, team_b) storing the winning margin
            (always positive); used for Step 3/4 PD calculations.
        base_margin_default: Assumed winning margin when a game's margin is not
            in `margins`.
        points_allowed: Optional dict keyed like `margins` giving a remaining
            game's (winner's, loser's) points allowed, in place of `pa_win` and
            `pa_win` plus the margin. Only Step 5 reads it.

    Returns:
        A dict mapping each team name to a sub-dict with keys
        ``{"w", "l", "t", "pa"}``.
    """
    wl_totals = {t: {"w": 0, "l": 0, "t": 0, "pa": 0} for t in teams}
    # Completed region games
    for comp_game in completed:
        if comp_game.a not in wl_totals or comp_game.b not in wl_totals:
            continue
        if comp_game.res_a == 1:
            wl_totals[comp_game.a]["w"] += 1
            wl_totals[comp_game.b]["l"] += 1
        elif comp_game.res_a == -1:
            wl_totals[comp_game.b]["w"] += 1
            wl_totals[comp_game.a]["l"] += 1
        else:
            wl_totals[comp_game.a]["t"] += 1
            wl_totals[comp_game.b]["t"] += 1
        # Step 5 – PA from completed games
        wl_totals[comp_game.a]["pa"] += comp_game.pa_a
        wl_totals[comp_game.b]["pa"] += comp_game.pa_b
    # Remaining region games (winner/loser by mask; PA includes margin for loser)
    for i, rem_game in enumerate(remaining):
        bit = (outcome_mask >> i) & 1
        winner, loser = (rem_game.a, rem_game.b) if bit == 1 else (rem_game.b, rem_game.a)
        m = margins.get((rem_game.a, rem_game.b), base_margin_default)
        wl_totals[winner]["w"] += 1
        wl_totals[loser]["l"] += 1
        pa_w, pa_l = (points_allowed or {}).get((rem_game.a, rem_game.b), (pa_win, pa_win + m))
        wl_totals[winner]["pa"] += pa_w
        wl_totals[loser]["pa"] += pa_l
    return wl_totals


# -------------------------
# Steps 1 & 3: H2H maps
# -------------------------


def build_h2h_maps(completed, remaining, outcome_mask, margins, base_margin_default=7):
    """Build head-to-head maps used by tiebreaker Steps 1 and 3.

    Constructs two defaultdicts indexed by (team_a, team_b):
    - Step 1: h2h_points (win=1, tie=0.5) among tied teams.
    - Step 3: capped head-to-head point differential (±12 per game).

    Args:
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        outcome_mask: Bitmask where bit i=1 means remaining[i].a wins.
        margins: Dict keyed by (team_a, team_b) storing the winning margin
            (always positive).
        base_margin_default: Assumed winning margin when a game's margin is not
            in `margins`.

    Returns:
        A 2-tuple ``(h2h_points, capped_pd_map)`` where each is a
        defaultdict keyed by (team_a, team_b).
    """
    h2h_points = defaultdict(float)
    capped_pd_map = defaultdict(int)
    # Completed H2H
    for comp_game in completed:
        # Step 1: H2H points tally
        if comp_game.res_a == 1:
            h2h_points[(comp_game.a, comp_game.b)] += 1.0
        elif comp_game.res_a == -1:
            h2h_points[(comp_game.b, comp_game.a)] += 1.0
        else:
            h2h_points[(comp_game.a, comp_game.b)] += 0.5
            h2h_points[(comp_game.b, comp_game.a)] += 0.5
        # Step 3: ±12 capped PD
        cap_a = max(-12, min(12, comp_game.pd_a))
        capped_pd_map[(comp_game.a, comp_game.b)] += cap_a
        capped_pd_map[(comp_game.b, comp_game.a)] -= cap_a
    # Remaining H2H (driven by mask & margins)
    for i, rem_game in enumerate(remaining):
        bit = (outcome_mask >> i) & 1
        m = margins.get((rem_game.a, rem_game.b), base_margin_default)
        if bit == 1:
            h2h_points[(rem_game.a, rem_game.b)] += 1.0
            capped_pd_map[(rem_game.a, rem_game.b)] += min(m, 12)
            capped_pd_map[(rem_game.b, rem_game.a)] -= min(m, 12)
        else:
            h2h_points[(rem_game.b, rem_game.a)] += 1.0
            capped_pd_map[(rem_game.a, rem_game.b)] -= min(m, 12)
            capped_pd_map[(rem_game.b, rem_game.a)] += min(m, 12)
    return h2h_points, capped_pd_map


# -------------------------
# Steps 2 & 4: arrays vs outside teams
# -------------------------


def step2_step4_arrays(
    _teams,
    bucket,
    base_order,
    completed,
    remaining,
    outcome_mask,
    margins,
    base_margin_default=7,
    ranks=None,
):
    """Compute Step 2 and Step 4 arrays for each tied team.

    Step 2 (results vs outside teams): 2 = win, 1 = tie, 0 = loss, None = no game.
    Step 4 (point differential vs outside teams): uses capped per-game
    differential of ±12.  For completed games the actual differential is capped;
    for remaining games the simulated margin (from `margins` or
    `base_margin_default`) is used and then capped.

    The outside teams are compared in *ranks* order: a list of groups, best first, each a team
    already placed (a group of one) or teams level on record whose order isn't settled yet. A
    group counts as one: a tied team's entry against it is the sum of its results (or capped point
    differentials) against the group's teams, None when it played none of them. Without *ranks*,
    each outside team in *base_order* is its own group.

    Args:
        _teams: Full list of region teams (unused directly; kept for signature
            consistency).
        bucket: The subset of teams currently being tiebroken.
        base_order: The pre-sorted region order used to enumerate outside teams.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        outcome_mask: Bitmask where bit i=1 means remaining[i].a wins.
        margins: Dict keyed by (team_a, team_b) storing the winning margin
            (always positive).
        base_margin_default: Assumed winning margin when a game's margin is not
            in `margins`.

    Returns:
        A 2-tuple ``(step2, step4)`` where each is a dict mapping team name to
        a list of values, one per group in ``outside_groups(bucket, base_order, ranks)``.
    """
    outside = outside_groups(bucket, base_order, ranks)

    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

    def res_vs(team, opp):
        """Return the encoded result (2/1/0/None) for team vs opp."""
        a, b, _ = normalize_pair(team, opp)
        comp_game = comp_idx.get((a, b))
        if comp_game is not None:
            if comp_game.res_a == 1:
                return 2 if team == a else 0
            if comp_game.res_a == -1:
                return 0 if team == a else 2
            return 1  # split/"tie" in our encoding
        idx = rem_idx.get((a, b))
        if idx is None:
            return None
        bit = (outcome_mask >> idx) & 1
        winner = a if bit == 1 else b
        return 2 if team == winner else 0

    def pd_vs(team, opp):
        """Capped PD vs outside (±12)."""
        a, b, _ = normalize_pair(team, opp)
        comp_game = comp_idx.get((a, b))
        if comp_game is not None:
            raw = comp_game.pd_a if team == a else -comp_game.pd_a
            return max(-12, min(12, raw))
        idx = rem_idx.get((a, b))
        if idx is None:
            return None
        bit = (outcome_mask >> idx) & 1
        m = margins.get((a, b), base_margin_default)
        m_capped = max(-12, min(12, m))
        if bit == 1:  # a defeats b by m
            return m_capped if team == a else -m_capped
        else:  # b defeats a by m
            return -m_capped if team == a else m_capped

    def against(team, group, value):
        """A tied team's sum against a group's teams, None when it played none of them."""
        played = [v for v in (value(team, o) for o in group) if v is not None]
        return sum(played) if played else None

    step2 = {s: [against(s, g, res_vs) for g in outside] for s in bucket}
    step4 = {s: [against(s, g, pd_vs) for g in outside] for s in bucket}
    return step2, step4


def outside_groups(bucket, base_order, ranks=None) -> list[list[str]]:
    """The teams outside *bucket*, best first, as the groups steps 2 and 4 compare against.

    *ranks* (see ``step2_step4_arrays``) places them: already-placed teams one by one, teams level
    on record whose order isn't settled yet together. Without it, each team in *base_order* alone.
    """
    bucket_set = set(bucket)
    groups = ranks if ranks is not None else [[t] for t in base_order]
    return [g for g in ([t for t in r if t not in bucket_set] for r in groups) if g]


# -------------------------
# Sort key helpers
# -------------------------


def _key_step2(step2_row):
    """Return a sortable key for a Step 2 result vector.

    Higher result is better (2>1>0), None sorts last (worst). Values are
    negated so that a lexicographically smaller tuple represents a better
    record in Python's default ascending sort.

    Args:
        step2_row: List of encoded results (2, 1, 0, or None) vs outside teams.

    Returns:
        A tuple of negated integers suitable for lexicographic comparison.
    """
    return tuple(-(x if x is not None else -(10**9)) for x in step2_row)


def _key_step4(step4_row):
    """Return a sortable key for a Step 4 point-differential vector.

    Higher PD is better; None sorts last (worst). Values are negated so that a
    lexicographically smaller tuple represents a better differential in Python's
    default ascending sort.

    Args:
        step4_row: List of capped (±12) point differentials vs outside teams,
            or None when no game was played.

    Returns:
        A tuple of negated integers suitable for lexicographic comparison.
    """
    return tuple(-(x if x is not None else -(10**9)) for x in step4_row)


def _partition_by(items, key_func):
    """Partition a list of teams into groups with equal keys.

    Groups are returned in ascending key order; teams within each group are
    sorted alphabetically for determinism.

    Args:
        items: List of team names to partition.
        key_func: Callable that maps a team name to a comparable key.

    Returns:
        A list of groups (each group is a sorted list of team names), ordered
        by ascending key value.
    """
    buckets: dict = defaultdict(list)
    for t in items:
        buckets[key_func(t)].append(t)
    out = []
    for k in sorted(buckets.keys()):
        out.append(sorted(buckets[k]))  # alphabetical within equal key
    return out


# -------------------------
# Bucket resolution (Steps 1–6 applied sequentially)
# -------------------------


def resolve_bucket(
    bucket,
    teams,
    wl_totals,
    base_order,
    completed,
    remaining,
    outcome_mask,
    margins,
    base_margin_default=7,
    coin_flip_collector: list[list[str]] | None = None,
    trace_collector: list | None = None,
    decision_collector: list | None = None,
    ranks: list[list[str]] | None = None,
):
    """Apply tiebreaker Steps 1-6 to order a single tied group of teams.

    Steps are applied sequentially.  After any step splits a group — whether
    a 3+ tie into sub-groups or a larger tie reduced to a 2-team sub-group —
    each sub-group restarts from Step 1 (head-to-head), as required by MHSAA
    rules.  A group still tied after all 5 deterministic steps is a coin flip:
    recorded in ``coin_flip_collector`` and sorted alphabetically as a proxy.

    Args:
        bucket: List of team names that are currently tied (same win%).
        teams: Full list of all region teams.
        wl_totals: Per-team W/L/T/PA totals (from ``standings_from_mask``).
        base_order: The pre-sorted region order used to enumerate outside teams.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        outcome_mask: Bitmask where bit i=1 means remaining[i].a wins.
        margins: Dict keyed by (team_a, team_b) storing the winning margin
            (always positive).
        base_margin_default: Assumed winning margin when a game's margin is not
            in ``margins``.
        coin_flip_collector: Optional list that accumulates groups of teams that
            remain tied after all 5 deterministic steps (Step 6 coin flip).
        trace_collector: Optional list that receives a ``TiebreakStep`` for every step applied to
            a tied group, in the order applied: a group's steps up to the one that splits it, then
            each still-tied part's steps from step 1 (the restart), best part first, and a step 6
            entry for a group left to the coin flip.
        decision_collector: Optional list that receives, in the order they
            are made, the decisions at the steps that can depend on margins
            and points allowed (3, 4 and 5): ``(step, group, parts)``, where
            *group* is the tied group (sorted) and *parts* its teams split by
            that step, best first, each part sorted (one part: still level).

    Returns:
        An ordered list of team names (highest seed first) for this bucket.
    """
    if len(bucket) == 1:
        return bucket[:]

    h2h_pts, h2h_pd_cap = build_h2h_maps(completed, remaining, outcome_mask, margins, base_margin_default)
    # Step 1 tally across the bucket
    step1 = dict.fromkeys(bucket, 0.0)
    for s in bucket:
        for o in bucket:
            if s == o:
                continue
            step1[s] += h2h_pts.get((s, o), 0.0)

    # Step 3 (capped H2H PD) across the bucket
    step3 = dict.fromkeys(bucket, 0)
    for s in bucket:
        for o in bucket:
            if s == o:
                continue
            step3[s] += h2h_pd_cap.get((s, o), 0)

    if ranks is None:
        # On its own: the teams above and below as they stand on record, the bucket one group.
        ranks = [[t for t in g if t not in bucket] for g in tie_bucket_groups(teams, wl_totals)] + [list(bucket)]
        ranks = [g for g in ranks if g]
    step2, step4 = step2_step4_arrays(
        teams, bucket, base_order, completed, remaining, outcome_mask, margins, base_margin_default, ranks=ranks
    )
    outside = tuple(tuple(g) for g in outside_groups(bucket, base_order, ranks))
    step_values = (step1, step2, step3, step4, {t: wl_totals[t]["pa"] for t in bucket})

    # ``pending`` is a list of groups still needing resolution.  Each entry is
    # either a singleton [team] (already placed) or a multi-team tied group.
    pending: list[list[str]] = [sorted(bucket)]

    def push_coinflip(groups):
        """Append multi-team groups to the coin_flip_collector (and the trace) if present."""
        for g in groups:
            if len(g) > 1:  # pragma: no branch — call site pre-filters singletons
                if coin_flip_collector is not None:
                    coin_flip_collector.append(sorted(g))
                if trace_collector is not None:
                    trace_collector.append(TiebreakStep(6, tuple(sorted(g)), (tuple(sorted(g)),)))

    # Steps 1–5: apply each key in sequence.  When a step splits a group, each
    # resulting sub-group restarts from Step 1 via a recursive call; the
    # resolved sub-sequence is broken into singletons so it is not re-processed.
    for step, key_builder in enumerate(
        [
            lambda t: -step1[t],
            lambda t: _key_step2(step2[t]),
            lambda t: -step3[t],
            lambda t: _key_step4(step4[t]),
            lambda t: wl_totals[t]["pa"],
        ],
        start=1,
    ):
        next_pending: list[list[str]] = []
        for g in pending:
            if len(g) <= 1:
                next_pending.append(g)
                continue
            parts = _partition_by(g, key_func=key_builder)
            if decision_collector is not None and step >= 3:
                decision_collector.append((step, tuple(g), tuple(tuple(p) for p in parts)))
            if trace_collector is not None:
                trace_collector.append(
                    TiebreakStep(
                        step,
                        tuple(g),
                        tuple(tuple(p) for p in parts),
                        {t: step_values[step - 1][t] for t in g},
                        outside if step in (2, 4) else (),
                    )
                )
            if len(parts) == 1:
                # No progress from this step — keep for the next one
                next_pending.append(g)
            else:
                # Split: each sub-group restarts from Step 1 (recursive call).
                # Flatten the resolved sub-sequence into singletons so the
                # outer loop does not re-process it. Parts are settled best first,
                # so a part's steps 2 and 4 see the parts above it placed one by one
                # and the parts below it as groups.
                placed: list[str] = []
                for k, part in enumerate(parts):
                    if len(part) == 1:
                        next_pending.append(part)
                        placed.extend(part)
                    else:
                        here = [[t] for t in placed] + [list(part)] + [list(p) for p in parts[k + 1 :]]
                        sub_ranks = [r2 for r in ranks for r2 in (here if set(r) & set(g) else [r])]
                        resolved = resolve_bucket(
                            part,
                            teams,
                            wl_totals,
                            base_order,
                            completed,
                            remaining,
                            outcome_mask,
                            margins,
                            base_margin_default,
                            coin_flip_collector,
                            trace_collector=trace_collector,
                            decision_collector=decision_collector,
                            ranks=sub_ranks,
                        )
                        next_pending.extend([[t] for t in resolved])
                        placed.extend(resolved)
        pending = next_pending

    # Step 6: any group that survived all 5 steps unresolved is a coin flip.
    push_coinflip([g for g in pending if len(g) > 1])

    return [t for g in pending for t in g]


# -------------------------
# Region-level ordering
# -------------------------


def base_bucket_order(teams, wl_totals):
    """Sort all region teams before tiebreaker Steps 1-6 are applied.

    Primary sort key is region winning percentage (descending), secondary is
    fewest losses, tertiary is alphabetical name.

    Args:
        teams: List of all team names in the region.
        wl_totals: Per-team W/L/T/PA totals (from ``standings_from_mask``).

    Returns:
        A sorted list of team names in base seeding order.
    """

    def key(s):
        """Sort key: (-win_pct, losses, name) so best record sorts first."""
        w, l, t = wl_totals[s]["w"], wl_totals[s]["l"], wl_totals[s]["t"]
        gp = w + l + t
        wp = (w + 0.5 * t) / gp if gp > 0 else 0.0
        return (-wp, l, s)

    return sorted(teams, key=key)


def tie_bucket_groups(teams, wl_totals):
    """Group teams with identical win% and loss count into tie buckets.

    Bucket boundaries are determined by (rounded win%, losses).  The returned
    list of groups preserves the ordering established by ``base_bucket_order``.

    Args:
        teams: List of all team names in the region.
        wl_totals: Per-team W/L/T/PA totals (from ``standings_from_mask``).

    Returns:
        A list of groups (each group is a sorted list of team names that are
        tied with each other), in base seeding order across groups.
    """
    buckets: dict = defaultdict(list)
    for s in teams:
        w, l, t = wl_totals[s]["w"], wl_totals[s]["l"], wl_totals[s]["t"]
        gp = w + l + t
        wp = (w + 0.5 * t) / gp if gp > 0 else 0.0
        buckets[(round(wp, 6), l)].append(s)
    order = base_bucket_order(teams, wl_totals)
    seen: set = set()
    out = []
    for s in order:
        if s in seen:
            continue
        w, l, t = wl_totals[s]["w"], wl_totals[s]["l"], wl_totals[s]["t"]
        gp = w + l + t
        wp = (w + 0.5 * t) / gp if gp > 0 else 0.0
        group = buckets[(round(wp, 6), l)]
        out.append(sorted(group))
        seen.update(group)
    return out


def resolve_standings_for_mask(
    teams,
    completed,
    remaining,
    outcome_mask,
    margins,
    base_margin_default=7,
    pa_win=14,
    coin_flip_collector: list[list[str]] | None = None,
    trace_collector: list | None = None,
    decision_collector: list | None = None,
    points_allowed: dict | None = None,
):
    """Resolve the full region seeding order for a single outcome mask.

    Computes W/L/T totals, groups teams into tie buckets, then calls
    ``resolve_bucket`` on each bucket in base seeding order.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        outcome_mask: Bitmask where bit i=1 means remaining[i].a wins.
        margins: Dict keyed by (team_a, team_b) storing the winning margin
            (always positive).
        base_margin_default: Assumed winning margin when a game's margin is not
            in `margins`.
        pa_win: Points assumed scored against the winner in a remaining game.
        coin_flip_collector: If provided, groups of teams that required a coin
            flip to break a tie are appended to this list.
        trace_collector: If provided, receives a ``TiebreakStep`` for every step applied to a
            tied group (see ``resolve_bucket``), bucket by bucket in seeding order.
        decision_collector: If provided, receives every step 3-5 decision made
            (see ``resolve_bucket``), bucket by bucket in seeding order.
        points_allowed: Optional per-game (winner's, loser's) points allowed for
            Step 5 (see ``standings_from_mask``).

    Returns:
        An ordered list of all team names (seed 1 first through seed N last).
    """
    wl_totals = standings_from_mask(
        teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default, points_allowed
    )
    base_order = base_bucket_order(teams, wl_totals)
    final = []
    coinflip_events: list[list[str]] = [] if coin_flip_collector is None else coin_flip_collector
    # Ties are broken best first ("ties for first place should be broken first"), so steps 2 and 4
    # see the teams above a tie in the order their own ties were broken, and the teams below it
    # still grouped by record: teams level on record count as one, as no order between them is set.
    buckets = tie_bucket_groups(teams, wl_totals)
    for k, bucket in enumerate(buckets):
        ranks = [[t] for t in final] + [list(b) for b in buckets[k:]]
        final.extend(
            resolve_bucket(
                bucket,
                teams,
                wl_totals,
                base_order,
                completed,
                remaining,
                outcome_mask,
                margins,
                base_margin_default,
                coin_flip_collector=coinflip_events,
                trace_collector=trace_collector,
                decision_collector=decision_collector,
                ranks=ranks,
            )
        )
    return final


def rank_to_slots(order) -> dict[str, tuple[int, int]]:
    """Convert a strict seeding order into (lo, hi) seed slot pairs.

    Since the order is strict (no ties at this point), every team maps to a
    degenerate slot where lo == hi == their 1-based rank.

    Args:
        order: Ordered list of team names, seed 1 first.

    Returns:
        A dict mapping each team name to ``(seed, seed)``.
    """
    return {s: (i, i) for i, s in enumerate(order, start=1)}


def unique_intra_bucket_games(buckets, remaining):
    """Return remaining games where both teams are in the same non-singleton bucket.

    These are the games whose margin of victory can shift the Step-3 (capped
    H2H PD) tiebreaker outcome.  Callers that also need to capture Step-4
    sensitivity (PD vs outside opponents) should supplement this list with
    ``sensitive_boundary_games``.

    Args:
        buckets: List of tie bucket groups (from ``tie_bucket_groups``).
        remaining: List of RemainingGame instances for unplayed region games.

    Returns:
        A deduplicated list of RemainingGame instances where both teams belong
        to the same multi-team tie bucket.
    """
    inb = set().union(*(set(b) for b in buckets if len(b) > 1))
    seen: set = set()
    out = []
    for rem_game in remaining:
        if rem_game.a in inb and rem_game.b in inb:
            key = (rem_game.a, rem_game.b)
            if key not in seen:
                seen.add(key)
                out.append(rem_game)
    return out


def sensitive_boundary_games(buckets, remaining, intra_games, teams, completed, outcome_mask, base_margins, pa_win):
    """Return remaining boundary games whose margin affects any bucket tiebreaker.

    A *boundary game* is a remaining game where exactly one team is in a
    multi-team tie bucket and the other is not.  Such games can affect Step-4
    (PD vs outside opponents) tiebreakers when combined with an intra-bucket
    game at its margin cap (12).

    The sensitivity check is: hold all intra-bucket game margins at 12 (the
    cap where Step-3 H2H PD differences are maximised), then vary the boundary
    game margin from 1 to 12.  If the full seeding order or the tiebreaker's
    step 3-5 decisions change, the boundary game is sensitive and must be
    included in the 12^N enumeration.

    Args:
        buckets: Tie bucket groups for this mask (from ``tie_bucket_groups``).
        remaining: All remaining games.
        intra_games: Games already identified as intra-bucket (from
            ``unique_intra_bucket_games``).
        teams: Full list of team names in the region.
        completed: Completed region games.
        outcome_mask: The binary outcome mask for this scenario.
        base_margins: Base margins dict keyed by ``(team_a, team_b)``.
        pa_win: Points-advantage awarded to the winner.

    Returns:
        List of additional RemainingGame instances (boundary games) whose
        margins are sensitive and should be included in the 12^N enumeration.
    """
    inb = set().union(*(set(b) for b in buckets if len(b) > 1))
    intra_keys = {(rg.a, rg.b) for rg in intra_games}

    # Build margins at the intra-game cap
    capped_margins = dict(base_margins)
    for rg in intra_games:
        capped_margins[(rg.a, rg.b)] = 12

    result = []
    seen: set = set()
    for rg in remaining:
        key = (rg.a, rg.b)
        if key in intra_keys or key in seen:
            continue
        # Exactly one team in a multi-team bucket
        if (rg.a in inb) == (rg.b in inb):
            continue
        seen.add(key)
        # Sensitivity check: vary this game's margin from 1 to 12 at capped intra margins
        margins_lo = dict(capped_margins)
        margins_lo[key] = 1
        margins_hi = dict(capped_margins)
        margins_hi[key] = 12
        order_lo = resolve_standings_for_mask(
            teams,
            completed,
            remaining,
            outcome_mask,
            margins=margins_lo,
            base_margin_default=7,
            pa_win=pa_win,
            coin_flip_collector=[],
            decision_collector=(decisions_lo := []),
        )
        order_hi = resolve_standings_for_mask(
            teams,
            completed,
            remaining,
            outcome_mask,
            margins=margins_hi,
            base_margin_default=7,
            pa_win=pa_win,
            coin_flip_collector=[],
            decision_collector=(decisions_hi := []),
        )
        # Decisions too: a margin can decide whether a tie reaches fewest points allowed without
        # changing the order at the assumed scores.
        if order_lo != order_hi or decisions_lo != decisions_hi:
            result.append(rg)
    return result


# -------------------------
# User-facing result resolution
# -------------------------


def resolve_with_results(
    teams: list,
    completed: list,
    remaining: list,
    results: dict,
    margins: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve seeding for a specific set of W/L results for remaining games.

    Converts human-readable W/L results (winner name per game) into a seeding
    list, and reports any games where a point differential is needed to break
    ties but was not provided.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        results: Dict mapping (team1, team2) -> winner_name. Teams may be in
            any order; the winner must be one of the two participants.
        margins: Optional dict mapping (team1, team2) -> winning margin
            (positive int). Teams may be in any order. When omitted, a default
            margin of 7 is used. A warning message is returned for any
            intra-bucket game whose margin would change the seeding.

    Returns:
        A 2-tuple (seeding, messages) where:
        - seeding: list of team names in seed order (seed 1 first).
        - messages: list of human-readable strings describing games where the
          point differential was not provided but would affect the tiebreaker.
          Empty when all tied games are already resolved without margin data.

    Raises:
        ValueError: If a result is missing for any remaining game, or if the
            provided winner name is not a participant in that game.
    """
    margins = margins or {}

    # Normalize all keys to canonical (a, b) lexicographic order
    norm_results: dict[tuple[str, str], str] = {}
    for (t1, t2), winner in results.items():
        a, b, _ = normalize_pair(t1, t2)
        norm_results[(a, b)] = winner

    norm_margins: dict[tuple[str, str], int] = {}
    for (t1, t2), margin in margins.items():
        a, b, _ = normalize_pair(t1, t2)
        norm_margins[(a, b)] = margin

    # Build outcome_mask: bit i = 1 if remaining[i].a wins
    outcome_mask = 0
    for i, rem in enumerate(remaining):
        key = (rem.a, rem.b)
        winner = norm_results.get(key)
        if winner is None:
            raise ValueError(f"No result provided for game: {rem.a} vs {rem.b}")
        if winner == rem.a:
            outcome_mask |= 1 << i
        elif winner != rem.b:
            raise ValueError(f"Result winner '{winner}' is not a participant in {rem.a} vs {rem.b}")

    # Compute seeding using the provided (or default) margins
    seeding = resolve_standings_for_mask(teams, completed, remaining, outcome_mask, norm_margins)

    # Detect intra-bucket games missing margins that would affect seeding
    messages = []
    wl_totals = standings_from_mask(teams, completed, remaining, outcome_mask, pa_win=14, margins=norm_margins)
    buckets = tie_bucket_groups(teams, wl_totals)
    intra = unique_intra_bucket_games(buckets, remaining)

    for rem_game in intra:
        key = (rem_game.a, rem_game.b)
        if key in norm_margins:
            continue
        # Test margins 1–12 to see whether the seeding would change
        seedings_by_margin = {
            m: resolve_standings_for_mask(teams, completed, remaining, outcome_mask, {**norm_margins, key: m})
            for m in range(1, 13)
        }
        if len({tuple(s) for s in seedings_by_margin.values()}) > 1:
            all_positions: dict[str, set] = {t: set() for t in teams}
            for s in seedings_by_margin.values():
                for idx, name in enumerate(s):
                    all_positions[name].add(idx + 1)
            affected = sorted(t for t, pos in all_positions.items() if len(pos) > 1)
            winner_name = norm_results[key]
            loser_name = rem_game.b if winner_name == rem_game.a else rem_game.a
            messages.append(
                f"Point differential needed for {winner_name} over {loser_name}: "
                f"margin affects seeding of {', '.join(affected)}."
            )

    return seeding, messages
