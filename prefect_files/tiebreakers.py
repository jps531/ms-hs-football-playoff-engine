from __future__ import annotations

from collections import defaultdict

from prefect_files.data_helpers import normalize_pair

# -------------------------
# Step 5 accumulation + W/L/T
# -------------------------


def standings_from_mask(teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default=7):
    """Compute W/L/T and PA for all teams for a given outcome mask.
    Implements: Step 5 (PA accumulation).
    """
    wl_totals = {t: {"w": 0, "l": 0, "t": 0, "pa": 0} for t in teams}
    # Completed region games
    for comp_game in completed:
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
        wl_totals[winner]["pa"] += pa_win
        wl_totals[loser]["pa"] += pa_win + m
    return wl_totals


# -------------------------
# Steps 1 & 3: H2H maps
# -------------------------


def build_h2h_maps(completed, remaining, outcome_mask, margins, base_margin_default=7):
    """Build maps used by tiebreakers:
    - Step 1: h2h_points (win=1, tie=0.5) among tied teams
    - Step 3: capped head-to-head point differential (±12 per game)
    Also returns pd_uncap for diagnostics.
    """
    h2h_points = defaultdict(float)
    capped_pd_map = defaultdict(int)
    pd_uncap = defaultdict(int)
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
        # Raw margin (not used in sort, kept for reference)
        pd_uncap[(comp_game.a, comp_game.b)] += comp_game.pd_a
        pd_uncap[(comp_game.b, comp_game.a)] -= comp_game.pd_a
    # Remaining H2H (driven by mask & margins)
    for i, rem_game in enumerate(remaining):
        bit = (outcome_mask >> i) & 1
        m = margins.get((rem_game.a, rem_game.b), base_margin_default)
        if bit == 1:
            h2h_points[(rem_game.a, rem_game.b)] += 1.0
            capped_pd_map[(rem_game.a, rem_game.b)] += min(m, 12)
            capped_pd_map[(rem_game.b, rem_game.a)] -= min(m, 12)
            pd_uncap[(rem_game.a, rem_game.b)] += m
            pd_uncap[(rem_game.b, rem_game.a)] -= m
        else:
            h2h_points[(rem_game.b, rem_game.a)] += 1.0
            capped_pd_map[(rem_game.a, rem_game.b)] -= min(m, 12)
            capped_pd_map[(rem_game.b, rem_game.a)] += min(m, 12)
            pd_uncap[(rem_game.a, rem_game.b)] -= m
            pd_uncap[(rem_game.b, rem_game.a)] += m
    return h2h_points, capped_pd_map, pd_uncap


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
):
    """
    Compute Step 2 and Step 4 arrays for each tied team.

    Step 2 (results vs outside teams):
      2 = win, 1 = tie, 0 = loss, None = no game

    Step 4 (point differential vs outside teams):
      Uses capped per-game differential of ±12.
      - For completed games, cap the differential at ±12.
      - For remaining games, use the simulated margin (from `margins` or `base_margin_default`),
        then cap at ±12.
    """
    bucket_set = set(bucket)
    outside = [s for s in base_order if s not in bucket_set]

    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

    def res_vs(team, opp):
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

    step2 = {s: [res_vs(s, o) for o in outside] for s in bucket}
    step4 = {s: [pd_vs(s, o) for o in outside] for s in bucket}
    return step2, step4


# -------------------------
# Sort key helpers
# -------------------------


def _key_step2(step2_row):
    """
    Canonical, lexicographic key for Step 2 vectors:
    - Higher result is better (2>1>0), None sorts last (worst).
    We invert to negative so 'smaller' tuple means 'better' in Python sort.
    """
    return tuple(-(x if x is not None else -(10**9)) for x in step2_row)


def _key_step4(step4_row):
    """
    Canonical, lexicographic key for Step 4 vectors:
    - Higher PD is better; None sorts last (worst).
    We invert to negative so 'smaller' tuple means 'better'.
    """
    return tuple(-(x if x is not None else -(10**9)) for x in step4_row)


def _partition_by(items, key_func):
    """
    Partition 'items' (list of team names) by the key computed from key_func(team).
    Returns list of groups (each group is a list of team names) in deterministic order.
    Determinism rule: alphabetical order *within* each equal-key group.
    """
    buckets: dict = defaultdict(list)
    for t in items:
        buckets[key_func(t)].append(t)
    out = []
    for k in sorted(buckets.keys()):
        out.append(sorted(buckets[k]))  # alphabetical within equal key
    return out


# -------------------------
# Pairwise tiebreaker helpers
# -------------------------


def _pair_h2h_points(
    a: str, b: str, completed, remaining, outcome_mask, _margins, _base_margin_default=7
) -> tuple[float, float]:
    """
    Direct head-to-head points for the specific pair (a,b), NOT aggregated vs everyone.
    Returns (pts_a, pts_b) where win=1, tie/split=0.5 each.
    """
    pts_a = 0.0
    pts_b = 0.0
    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

    cg = comp_idx.get(normalize_pair(a, b)[:2])
    if cg is not None:
        if cg.res_a == 1:
            if a == cg.a:
                pts_a += 1.0
            else:
                pts_b += 1.0
        elif cg.res_a == -1:
            if a == cg.a:
                pts_b += 1.0
            else:
                pts_a += 1.0
        else:
            pts_a += 0.5
            pts_b += 0.5

    idx = rem_idx.get(normalize_pair(a, b)[:2])
    if idx is not None:
        bit = (outcome_mask >> idx) & 1
        winner = remaining[idx].a if bit == 1 else remaining[idx].b
        if winner == a:
            pts_a += 1.0
        else:
            pts_b += 1.0

    return pts_a, pts_b


def _pair_h2h_pd_capped(a: str, b: str, completed, remaining, outcome_mask, margins, base_margin_default=7) -> int:
    """
    Direct head-to-head capped point differential (±12 per game) for the specific pair (a,b).
    Positive means advantage to 'a'.
    """
    pd = 0
    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

    cg = comp_idx.get(normalize_pair(a, b)[:2])
    if cg is not None:
        raw = cg.pd_a if a == cg.a else -cg.pd_a
        pd += max(-12, min(12, raw))

    idx = rem_idx.get(normalize_pair(a, b)[:2])
    if idx is not None:
        bit = (outcome_mask >> idx) & 1
        m = margins.get((remaining[idx].a, remaining[idx].b), base_margin_default)
        m_capped = max(-12, min(12, m))
        if bit == 1:
            pd += m_capped if a == remaining[idx].a else -m_capped
        else:
            pd -= m_capped if a == remaining[idx].a else -m_capped

    return pd


def _resolve_pair_using_steps(
    pair, step2, step4, wl_totals, completed, remaining, outcome_mask, margins, base_margin_default=7, debug=False
):
    """
    Resolve a 2-team tie by restarting the chain from Step 1, per rule:
      Step 1 -> Step 2 -> Step 3 -> Step 4 -> Step 5 -> alphabetical.
    Returns the ordered list [winner, loser].
    """
    a, b = pair
    if debug:
        print(f"[DEBUG TIE]   Resolving pair {a} vs {b} from Step 1")

    # Step 1: direct head-to-head points for the pair
    pts_a, pts_b = _pair_h2h_points(a, b, completed, remaining, outcome_mask, margins, base_margin_default)
    if debug:
        print(f"[DEBUG TIE]     Pair Step1 H2H points: {a}:{pts_a}  {b}:{pts_b}")
    if pts_a != pts_b:
        return [a, b] if pts_a > pts_b else [b, a]

    # Step 2: results vs outside (lexicographic, more is better)
    k2_a = _key_step2(step2[a])
    k2_b = _key_step2(step2[b])
    if debug:
        print(f"[DEBUG TIE]     Pair Step2 keys: {a}:{k2_a}  {b}:{k2_b}")
    if k2_a != k2_b:
        return [a, b] if k2_a < k2_b else [b, a]  # smaller (more negative) is better

    # Step 3: direct capped H2H PD (±12; more is better)
    pd_ab = _pair_h2h_pd_capped(a, b, completed, remaining, outcome_mask, margins, base_margin_default)
    if debug:
        print(f"[DEBUG TIE]     Pair Step3 H2H PD (±12): {a} vs {b} -> {pd_ab}")
    if pd_ab != 0:
        return [a, b] if pd_ab > 0 else [b, a]

    # Step 4: PD vs outside (lexicographic, more is better)
    k4_a = _key_step4(step4[a])
    k4_b = _key_step4(step4[b])
    if debug:
        print(f"[DEBUG TIE]     Pair Step4 keys: {a}:{k4_a}  {b}:{k4_b}")
    if k4_a != k4_b:
        return [a, b] if k4_a < k4_b else [b, a]

    # Step 5: fewest points allowed (lower is better)
    pa_a = wl_totals[a]["pa"]
    pa_b = wl_totals[b]["pa"]
    if debug:
        print(f"[DEBUG TIE]     Pair Step5 PA: {a}:{pa_a}  {b}:{pa_b}")
    if pa_a != pa_b:
        return [a, b] if pa_a < pa_b else [b, a]

    # Step 6: coin flip (reportable upstream if desired), fallback to alphabetical
    if debug:
        print("[DEBUG TIE]     Pair Step6 coin flip needed -> alphabetical")
    return sorted([a, b])


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
    debug=False,
):
    """
    Apply Steps 1–6 to order a single tie bucket, SEQUENTIALLY.
    - After any step partitions a 3+ tie down to a size-2 subgroup, that subgroup
      is re-resolved starting from Step 1 (head-to-head), as required.
    """
    if len(bucket) == 1:
        return bucket[:]

    h2h_pts, h2h_pd_cap, _ = build_h2h_maps(completed, remaining, outcome_mask, margins, base_margin_default)
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

    step2, step4 = step2_step4_arrays(
        teams, bucket, base_order, completed, remaining, outcome_mask, margins, base_margin_default
    )

    if debug and len(bucket) > 2:
        print(f"Step1 H2H totals: {step1}")
        print(f"Step3 H2H PD (cap ±12): {step3}")
        print("Step2 keys: {" + ", ".join(f"{t}: {_key_step2(step2[t])}" for t in bucket) + " }}")
        print("Step4 keys: {" + ", ".join(f"{t}: {_key_step4(step4[t])}" for t in bucket) + " }}")

    pending_groups = [sorted(bucket)]
    resolved_order: list[str] = []

    def push_coinflip(groups):
        if coin_flip_collector is not None:
            for g in groups:
                if len(g) > 1:
                    coin_flip_collector.append(sorted(g))

    # Step 1: partition by Step 1 score
    next_groups = []
    for g in pending_groups:
        parts = _partition_by(g, key_func=lambda t: -step1[t])
        if debug and len(bucket) > 2:
            print(f"[DEBUG TIE] -> After Step1 partition: {parts}")
        next_groups.extend(parts)
    pending_groups = next_groups

    # Steps 2–5 in sequence; size-2 groups restart from Step 1 immediately
    for step_label, key_builder in [
        ("Step2", lambda t: _key_step2(step2[t])),
        ("Step3", lambda t: -step3[t]),
        ("Step4", lambda t: _key_step4(step4[t])),
        ("Step5", lambda t: wl_totals[t]["pa"]),
    ]:
        next_groups = []
        for g in pending_groups:
            if len(g) == 1:
                next_groups.append(g)
                continue
            if len(g) == 2:
                ordered = _resolve_pair_using_steps(
                    g,
                    step2,
                    step4,
                    wl_totals,
                    completed,
                    remaining,
                    outcome_mask,
                    margins,
                    base_margin_default,
                    debug=False,
                )
                next_groups.append(ordered)
                continue
            parts = _partition_by(g, key_func=lambda t: key_builder(t))
            if debug and len(bucket) > 2:
                print(f"[DEBUG TIE] -> After {step_label} partition: {parts}")
            for part in parts:
                if len(part) == 2:
                    ordered = _resolve_pair_using_steps(
                        part,
                        step2,
                        step4,
                        wl_totals,
                        completed,
                        remaining,
                        outcome_mask,
                        margins,
                        base_margin_default,
                        debug=False,
                    )
                    next_groups.append(ordered)
                else:
                    next_groups.append(part)
        pending_groups = next_groups

    # Step 6: coin flip for anything still tied
    unresolved_multi = [g for g in pending_groups if len(g) > 1]
    if unresolved_multi:
        push_coinflip(unresolved_multi)

    for g in pending_groups:
        resolved_order.extend(g)

    if debug and len(bucket) > 2:
        print(f"Final resolved order for bucket: {resolved_order}")
        print("[DEBUG TIE] ===== End bucket =====")

    return resolved_order


# -------------------------
# Region-level ordering
# -------------------------


def base_bucket_order(teams, wl_totals):
    """Pre-order to form buckets BEFORE Steps 1–6:
    sort by region winning %, then fewest losses, then name.
    """

    def key(s):
        w, l, t = wl_totals[s]["w"], wl_totals[s]["l"], wl_totals[s]["t"]
        gp = w + l + t
        wp = (w + 0.5 * t) / gp if gp > 0 else 0.0
        return (-wp, l, s)

    return sorted(teams, key=key)


def tie_bucket_groups(teams, wl_totals):
    """Groups teams with identical (rounded) win% and losses into tie buckets,
    preserving base_bucket_order across buckets.
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
    teams, completed, remaining, outcome_mask, margins, base_margin_default=7, pa_win=14, debug=False
):
    """Resolve ordering/ties for a full region under a single mask.
    Calls resolve_bucket() on each tie bucket in base order.
    """
    wl_totals = standings_from_mask(teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default)
    base_order = base_bucket_order(teams, wl_totals)
    final = []
    coinflip_events: list[list[str]] = []
    for bucket in tie_bucket_groups(teams, wl_totals):
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
                debug=debug,
            )
        )
    return final


def rank_to_slots(order) -> dict[str, tuple[int, int]]:
    """Convert strict order into seed slots (lo, hi)."""
    return {s: (i, i) for i, s in enumerate(order, start=1)}


def unique_intra_bucket_games(buckets, remaining):
    """Return remaining games where both teams appear in the same non-singleton bucket.
    Used for Step-3 knife-edge threshold detection.
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
