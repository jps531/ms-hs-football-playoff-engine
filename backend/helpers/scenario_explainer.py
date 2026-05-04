"""Human-readable explanations for per-team seeding outcomes in a single scenario.

Each outcome is a short English sentence like:
  "West Jones finishes 2-3, all alone in 3rd"
  "Hattiesburg finishes 4-1, tied with Wayne County, who they beat 20-13"
  "Wayne County finishes 3-2, tied with Jones County — beat Wayne County while
   Jones County lost, placing Wayne County 3rd"

Phase 1 covers:
  - Solo seeds (all alone)
  - 2-way ties resolved by H2H (with score) or coin flip
  - 3-way ties where one team beat both / lost to both / beat one and lost to one
  - 4-way+ ties with a generic tiebreaker fallback

Phase 2 adds:
  - Step-2 (vs outside record) explanations for 2-way ties without H2H resolution
  - Step-2 explanations for circular 3-way ties (each team went 1-1 within the group)
  - Removes misleading "via tiebreaker" when H2H within sub-buckets fully resolved a
    3-way partial split
  - Steps 3-5 fallback clauses (H2H point margin, PD vs outside, fewest PA)

Typical usage
-------------
    from backend.helpers.scenario_explainer import explain_seeding_outcome

    explanations = explain_seeding_outcome(teams, completed, remaining, mask, margins)
    # returns dict[str, str]: team name → sentence
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.helpers.data_classes import CompletedGame, RemainingGame
from backend.helpers.data_helpers import normalize_pair
from backend.helpers.tiebreakers import (
    base_bucket_order,
    build_h2h_maps,
    resolve_standings_with_trace,
    standings_from_mask,
    tie_bucket_groups,
)

# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}


def _seed_label(n: int) -> str:
    """Return the ordinal string for seed n (e.g. 1 → '1st')."""
    return _ORDINALS.get(n, f"{n}th")


def _record_str(wl: dict) -> str:
    """Return a W-L or W-L-T record string from a standings dict."""
    w, l, t = wl["w"], wl["l"], wl["t"]
    if t:
        return f"{w}-{l}-{t}"
    return f"{w}-{l}"


def _join_names(names: list[str]) -> str:
    """Join a list of names with Oxford-comma style ('A', 'A and B', 'A, B, and C')."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _quantifier(n: int) -> str:
    """Return 'both' for n==2, 'all' otherwise (used in 3-way+ descriptions)."""
    return "both" if n == 2 else "all"


def _game_score_str(
    team: str,
    opponent: str,
    completed: list[CompletedGame],
) -> str | None:
    """Return ' N-M' (with leading space) for the H2H game, from team's POV.

    Returns None if no score data is available (pa_a == 0 and pa_b == 0).
    """
    a, b, sign = normalize_pair(team, opponent)
    for cg in completed:
        if cg.a == a and cg.b == b:
            if cg.pa_a == 0 and cg.pa_b == 0:
                return None
            if sign == 1:
                # team is the lex-first (a): pa_b is team's points for; pa_a is team's points against
                return f" {cg.pa_b}-{cg.pa_a}"
            else:
                # team is b: pa_a is team's points for; pa_b is team's points against
                return f" {cg.pa_a}-{cg.pa_b}"
    return None


# ---------------------------------------------------------------------------
# Phase 2: step data helpers
# ---------------------------------------------------------------------------


@dataclass
class BucketStepData:
    """Pre-computed tiebreaker step data for one tie bucket.

    Used by Phase-2 explanation logic to look up Steps 2-5 results without
    re-running the full tiebreaker pipeline.  Computed once per bucket in
    ``explain_seeding_outcome`` and passed into ``_explain_bucket``.

    Attributes:
        step2: Per-team list of results (2=win, 1=tie, 0=loss, None=no game)
            vs each outside team in ``outside`` order.
        step4: Per-team list of capped (±12) point differentials vs each
            outside team in ``outside`` order.
        h2h_pd_cap: Capped H2H point-differential map; defaultdict keyed by
            ``(a, b)`` (lex-normalised pair).
        wl_totals: Per-team W/L/T/PA totals from ``standings_from_mask``.
        outside: Outside teams (not in the bucket) in base seeding order —
            the column axis for ``step2`` and ``step4``.
    """

    step2: dict
    step4: dict
    h2h_pd_cap: dict
    wl_totals: dict
    outside: list


def _step1_totals(sub_bucket: list[str], h2h_pts: dict) -> dict[str, float]:
    """Sum H2H win points within ``sub_bucket`` for each member.

    Args:
        sub_bucket: The subset of teams being compared (may be smaller than
            the original tie bucket when sub-groups have been split off).
        h2h_pts: Head-to-head win-points map keyed by ``(a, b)``.

    Returns:
        Dict mapping each team in ``sub_bucket`` to their total H2H win points
        vs the other members of ``sub_bucket``.
    """
    return {s: sum(h2h_pts.get((s, o), 0.0) for o in sub_bucket if o != s) for s in sub_bucket}


def _step3_totals(sub_bucket: list[str], h2h_pd_cap: dict) -> dict[str, int]:
    """Sum capped H2H point differentials within ``sub_bucket`` for each member.

    Args:
        sub_bucket: The subset of teams being compared.
        h2h_pd_cap: Capped H2H PD map keyed by ``(a, b)``.

    Returns:
        Dict mapping each team in ``sub_bucket`` to their total capped H2H PD
        vs the other members of ``sub_bucket``.
    """
    return {s: sum(h2h_pd_cap.get((s, o), 0) for o in sub_bucket if o != s) for s in sub_bucket}


def _non_h2h_clause(
    team: str,
    other: str,
    sub_bucket: list[str],
    step_data: BucketStepData,
) -> str | None:
    """Return a brief clause explaining ``team``'s position vs ``other`` at Step 2+.

    The clause is phrased from ``team``'s perspective regardless of whether
    ``team`` is the higher or lower seed.  Returns ``None`` if no step
    distinguishes them (coin flip will be used externally).

    Steps checked in order: 2 (vs outside record) → 3 (H2H PD) → 4 (PD vs
    outside) → 5 (fewest PA).

    Args:
        team: The team being described.
        other: The adjacent team in seed order (immediately above or below).
        sub_bucket: The group of teams that were compared together at this
            step level (may differ from the original bucket when sub-groups
            restarted from Step 1 after a partial split).
        step_data: Pre-computed step data for the original tie bucket.

    Returns:
        A short English clause like ``"beat Wayne County while Beta lost"``
        or ``None`` if all checked steps are tied.
    """
    t2 = step_data.step2.get(team, [])
    o2 = step_data.step2.get(other, [])

    # Step 2: first outside team where the two differ
    for i, ext in enumerate(step_data.outside):
        t_res = t2[i] if i < len(t2) else None
        o_res = o2[i] if i < len(o2) else None
        # Higher raw value = better (2>1>0>None treated as very negative)
        t_key = t_res if t_res is not None else -(10**9)
        o_key = o_res if o_res is not None else -(10**9)
        if t_key == o_key:
            continue
        if t_key > o_key:
            if t_res == 2 and o_res == 0:
                return f"beat {ext} while {other} lost"
            if t_res == 2 and o_res is None:
                return f"beat {ext} while {other} didn't play them"
            return f"had a better result vs {ext}"
        else:
            if o_res == 2 and t_res == 0:
                return f"lost to {ext} while {other} won"
            if o_res == 2 and t_res is None:
                return f"didn't play {ext} while {other} won"
            return f"had a worse result vs {ext}"

    # Step 3: capped H2H PD within sub_bucket
    s3 = _step3_totals(sub_bucket, step_data.h2h_pd_cap)
    t3, o3 = s3.get(team, 0), s3.get(other, 0)
    if t3 != o3:
        if t3 > o3:
            return f"had the better H2H point margin (+{t3} vs +{o3})"
        return f"had a worse H2H point margin (+{t3} vs {other}'s +{o3})"

    # Step 4: capped PD vs outside (first differentiating outside team)
    t4 = step_data.step4.get(team, [])
    o4 = step_data.step4.get(other, [])
    for i in range(len(step_data.outside)):
        t_pd = t4[i] if i < len(t4) else None
        o_pd = o4[i] if i < len(o4) else None
        t_k = -(t_pd if t_pd is not None else -(10**9))
        o_k = -(o_pd if o_pd is not None else -(10**9))
        if t_k != o_k:
            if t_k < o_k:
                return "had better point differentials vs outside opponents"
            return "had worse point differentials vs outside opponents"

    # Step 5: fewest PA
    t_pa = step_data.wl_totals.get(team, {}).get("pa", 0)
    o_pa = step_data.wl_totals.get(other, {}).get("pa", 0)
    if t_pa != o_pa:
        if t_pa < o_pa:
            return f"allowed fewer points in region play ({t_pa} vs {o_pa})"
        return f"allowed more points in region play ({t_pa} vs {o_pa})"

    return None


# ---------------------------------------------------------------------------
# Per-bucket explanation
# ---------------------------------------------------------------------------


def _explain_bucket(
    team: str,
    bucket: list[str],
    seed: int,
    record: str,
    completed: list[CompletedGame],
    coin_flip_groups: list[list[str]],
    h2h_pts: dict,
    step_data: BucketStepData | None = None,
    bucket_seed_order: list[str] | None = None,
) -> str:
    """Return a human-readable sentence for one team's outcome within its tie bucket.

    Phase 1 covers H2H-resolved and coin-flip cases.  Phase 2 (activated when
    ``step_data`` and ``bucket_seed_order`` are provided) replaces the generic
    "via tiebreaker" fallback with specific step-2–5 language.

    Args:
        team: The team being described.
        bucket: All teams in the same W/L tie bucket (including team).
        seed: The final integer seed assigned to team.
        record: Pre-formatted record string (e.g. '2-1').
        completed: Full list of completed games (for score lookup).
        coin_flip_groups: Groups from coin_flip_collector — any bucket where the
            final ordering was determined by coin flip.
        h2h_pts: Head-to-head win points map keyed by (a, b); defaultdict(float).
        step_data: Optional Phase-2 step data for the bucket.  When provided,
            replaces "via tiebreaker" with specific step-level explanations.
        bucket_seed_order: Teams in this bucket ordered by their final seed
            (1st first).  Required for Phase-2 circular-tie explanations.

    Returns:
        A single English sentence ending without a period (callers may add one).
    """
    seed_str = _seed_label(seed)
    prefix = f"{team} finishes {record}"

    # --- Alone ---
    if len(bucket) == 1:
        return f"{prefix}, all alone in {seed_str}"

    others = [t for t in bucket if t != team]

    # --- Check for coin flip ---
    in_coin_flip = any(team in grp and any(o in grp for o in others) for grp in coin_flip_groups)

    if in_coin_flip and len(bucket) == 2:
        opp = others[0]
        return f"{prefix}, tied with {opp}. This will be determined by a coin-flip"

    # --- 2-way tie: H2H resolution ---
    if len(bucket) == 2:
        opp = others[0]
        score = _game_score_str(team, opp, completed)
        score_str = score if score is not None else ""

        a, b, sign = normalize_pair(team, opp)
        if sign == 1:
            team_pts = h2h_pts[(a, b)]
            opp_pts = h2h_pts[(b, a)]
        else:
            team_pts = h2h_pts[(b, a)]
            opp_pts = h2h_pts[(a, b)]

        if team_pts > opp_pts:
            return f"{prefix}, tied with {opp}, who they beat{score_str}"
        elif opp_pts > team_pts:
            return f"{prefix}, tied with {opp}, who they lost to{score_str}"

        # H2H didn't resolve — try Phase 2 step explanation
        if step_data is not None:
            clause = _non_h2h_clause(team, opp, [team, opp], step_data)
            if clause:
                return f"{prefix}, tied with {opp} — {clause}, placing {team} {seed_str}"
        return f"{prefix}, tied with {opp}, finishing {seed_str} via tiebreaker"

    # --- 3-way tie ---
    if len(bucket) == 3:
        beat = []
        lost_to = []
        for opp in others:
            a, b, sign = normalize_pair(team, opp)
            if sign == 1:
                team_pts = h2h_pts[(a, b)]
                opp_pts = h2h_pts[(b, a)]
            else:
                team_pts = h2h_pts[(b, a)]
                opp_pts = h2h_pts[(a, b)]
            if team_pts > opp_pts:
                beat.append(opp)
            elif opp_pts > team_pts:
                lost_to.append(opp)

        others_str = _join_names(others)
        q = _quantifier(len(others))

        if len(beat) == len(others):
            return f"{prefix}, in a 3-way tie with {others_str}, {q} of whom they beat"
        if len(lost_to) == len(others):
            return f"{prefix}, in a 3-way tie with {others_str}, {q} of whom they lost to"

        if len(beat) == 1 and len(lost_to) == 1:
            # Determine if this is a circular tie (all step-1 values equal)
            s1 = _step1_totals(bucket, h2h_pts)
            all_step1_equal = len({round(v, 6) for v in s1.values()}) == 1

            if not all_step1_equal:
                # Partial split: H2H within sub-buckets fully resolved order.
                # "Via tiebreaker" is misleading; the H2H record tells the story.
                return (
                    f"{prefix}, in a 3-way tie with {others_str}. "
                    f"They beat {beat[0]} but lost to {lost_to[0]}, giving {team} {seed_str}"
                )

            # Circular (all step1 equal): a later step determined order.
            if step_data is not None and bucket_seed_order is not None:
                my_idx = bucket_seed_order.index(team)
                adjacent = (
                    bucket_seed_order[my_idx + 1]
                    if my_idx + 1 < len(bucket_seed_order)
                    else bucket_seed_order[my_idx - 1]
                )
                clause = _non_h2h_clause(team, adjacent, bucket, step_data)
                if clause:
                    return (
                        f"{prefix}, in a 3-way tie with {others_str}. "
                        f"They beat {beat[0]} but lost to {lost_to[0]} — "
                        f"{clause}, placing {team} {seed_str}"
                    )
            return (
                f"{prefix}, in a 3-way tie with {others_str}. "
                f"They beat {beat[0]} but lost to {lost_to[0]}, finishing {seed_str} via tiebreaker"
            )

        # Mixed fallback (e.g. beat one, haven't played the other)
        if step_data is not None and bucket_seed_order is not None:
            my_idx = bucket_seed_order.index(team)
            adjacent = (
                bucket_seed_order[my_idx + 1] if my_idx + 1 < len(bucket_seed_order) else bucket_seed_order[my_idx - 1]
            )
            clause = _non_h2h_clause(team, adjacent, bucket, step_data)
            if clause:
                return f"{prefix}, in a 3-way tie with {others_str} — {clause}, placing {team} {seed_str}"
        return f"{prefix}, in a 3-way tie with {others_str}, finishing {seed_str} via tiebreaker"

    # --- 4-way+ tie: generic fallback ---
    others_str = _join_names(others)
    return f"{prefix}, in a {len(bucket)}-way tie with {others_str}, finishing {seed_str} via tiebreaker"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain_seeding_outcome(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    outcome_mask: int,
    margins: dict,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> dict[str, str]:
    """Return human-readable seeding explanations for all teams in one scenario.

    Produces one short English sentence per team describing why they finished
    at their seed.  Phase 1 handles H2H-resolved ties and coin flips.  Phase 2
    (always active) adds specific step-2–5 language for ties not resolved by
    head-to-head record alone.

    Args:
        teams: All team names in the region, alphabetically sorted.
        completed: Finalized region games already played.
        remaining: Unplayed region game pairs (in the same order used to build
            ``outcome_mask``).
        outcome_mask: Bitmask for unplayed games — bit i=1 means remaining[i].a
            wins; bit i=0 means remaining[i].b wins.
        margins: Dict keyed by (team_a, team_b) storing winning margin for
            completed games.
        pa_win: Points awarded to a win for PA tiebreaker (default 14).
        base_margin_default: Assumed winning margin when a game's margin is
            absent from ``margins`` (default 7).

    Returns:
        ``dict[str, str]`` mapping each team name to its explanation sentence.
    """
    wl_totals = standings_from_mask(teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default)
    buckets = tie_bucket_groups(teams, wl_totals)
    base_order = base_bucket_order(teams, wl_totals)

    coin_flip_collector: list[list[str]] = []
    final_order, step_trace = resolve_standings_with_trace(
        teams,
        completed,
        remaining,
        outcome_mask,
        margins,
        base_margin_default,
        pa_win,
        coin_flip_collector,
    )

    h2h_pts, h2h_pd_cap, _ = build_h2h_maps(completed, remaining, outcome_mask, margins, base_margin_default)

    # Build BucketStepData from step data already computed inside resolve_bucket.
    bucket_step_data: dict[tuple, BucketStepData] = {}
    for bucket in buckets:
        if len(bucket) > 1:
            bucket_key = tuple(sorted(bucket))
            s2, s4 = step_trace[bucket_key]
            outside = [t for t in base_order if t not in set(bucket)]
            bucket_step_data[bucket_key] = BucketStepData(
                step2=s2,
                step4=s4,
                h2h_pd_cap=h2h_pd_cap,
                wl_totals=wl_totals,
                outside=outside,
            )

    seed_of: dict[str, int] = {school: i + 1 for i, school in enumerate(final_order)}

    explanations: dict[str, str] = {}
    for bucket in buckets:
        bucket_key = tuple(sorted(bucket))
        sd = bucket_step_data.get(bucket_key)
        bucket_seed_order = [t for t in final_order if t in set(bucket)]
        for team in bucket:
            record = _record_str(wl_totals[team])
            seed = seed_of[team]
            explanations[team] = _explain_bucket(
                team,
                bucket,
                seed,
                record,
                completed,
                coin_flip_collector,
                h2h_pts,
                step_data=sd,
                bucket_seed_order=bucket_seed_order,
            )

    return explanations
