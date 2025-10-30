#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playoff Odds & Scenario Enumerator (clarified comments + explicit Step labels + sequential tie resolution)

Key bugfix in this version:
- Step partitions no longer (incorrectly) include the team name in the partition *key*.
  That was splitting equal-step groups into singletons (alphabetical), preventing later
  steps (e.g., Step 3) from ever deciding the order. Now, grouping uses ONLY the step
  metric; alphabetical order is applied *within* equal-key groups for determinism.

This script deterministically enumerates all remaining region-game outcomes and, for each
outcome, applies the official tiebreaker chain to produce final seeds (1–4). It also
aggregates probabilities (assuming 50/50 per remaining game by default, or weighted if
you pass explicit weights) and emits human-readable explanations for each seed path.

TIEBREAKER STEPS (where implemented in code)
-------------------------------------------
Step 1 – Head-to-head among tied teams:
    Implemented in build_h2h_maps() -> h2h_points, applied in resolve_bucket() sequential step #1.

Step 2 – Results vs highest-ranked/seeded outside teams (lexicographic):
    Implemented in step2_step4_arrays() -> `step2`, applied in resolve_bucket() sequential step #2.

Step 3 – Point differential among tied teams (capped at ±12):
    Implemented in build_h2h_maps() -> capped_pd_map, applied in resolve_bucket() sequential step #3.

Step 4 – Point differential vs highest-ranked/seeded outside teams (lexicographic, capped ±12):
    Implemented in step2_step4_arrays() -> `step4` (capped), applied in resolve_bucket() sequential step #4.

Step 5 – Fewest points allowed in all region games:
    Accumulated in standings_from_mask() as `pa`, applied in resolve_bucket() sequential step #5.

Step 6 – Coin flip:
    We detect when teams remain fully tied after Steps 1–5. In resolve_bucket(), we collect
    such ties in `coin_flip_collector` (if provided). For determinism we still break ties by
    alphabetical order **without changing odds math** (no behavioral change), but now the code
    explicitly marks where a true coin flip would be required.
"""

from __future__ import annotations
import argparse, json, math, os
from itertools import product
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

try:
    import psycopg
except Exception:
    psycopg = None

def pct_str(x: float) -> str:
    val = x * 100.0
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.0f}%".rstrip('0').rstrip('.')


# --------------------------- Data Models ---------------------------

@dataclass(frozen=True)
class CompletedGame:
    a: str  # team (lexicographically first)
    b: str  # team (lexicographically second)
    res_a: int  # head-to-head result in completed set (+1 a beat b, -1 b beat a, 0 split)
    pd_a: int   # raw point differential for a vs b across completed meetings (will be capped when used)
    pa_a: int   # points allowed by team a in those meetings
    pa_b: int   # points allowed by team b in those meetings

@dataclass(frozen=True)
class RemainingGame:
    a: str  # team (lexicographically first)
    b: str  # team (lexicographically second)


# --------------------------- Fetch Helpers ---------------------------

def normalize_pair(x: str, y: str) -> Tuple[str, str, int]:
    return (x, y, +1) if x <= y else (y, x, -1)

def fetch_division(conn, clazz: int, region: int, season: int) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
            (clazz, region, season),
        )
        return [r[0] for r in cur.fetchall()]

def fetch_completed_pairs(conn, teams: List[str], season: int) -> List[CompletedGame]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school, opponent, result, points_for, points_against "
            "FROM games "
            "WHERE season=%s AND final=TRUE AND region_game=TRUE "
            "AND school = ANY(%s) AND opponent = ANY(%s)",
            (season, teams, teams),
        )
        rows = cur.fetchall()

    # Aggregate completed meetings per pair (a,b) **counting each game once**
    tmp: Dict[Tuple[str, str], Dict[str, int]] = {}
    for school, opp, result, pf, pa in rows:
        a, b, _ = normalize_pair(school, opp)

        # Process **only** the lexicographically-first school's row for this game.
        # This avoids double-counting when both (A vs B) and (B vs A) rows exist.
        if school != a:
            continue

        d = tmp.setdefault((a, b), {"res_a": 0, "pd_a": 0, "pa_a": 0, "pa_b": 0})

        # Result contribution for Step 1, from A’s perspective.
        # (Assumes result is from the row's school's perspective.)
        if result == 'W':
            d["res_a"] += 1     # A (school==a) beat B
        elif result == 'L':
            d["res_a"] -= 1     # A lost to B
        else:
            # Allow 'T' or other tie markers to count as split
            d["res_a"] += 0

        # Margins + PA for Steps 3 & 5 (all from A’s perspective, counted once)
        if pf is not None and pa is not None:
            # A’s point differential vs B for this game
            d["pd_a"] += (pf - pa)

            # Points allowed by A and B in this game:
            #  - A allowed 'pa' (its points_against)
            #  - B allowed 'pf' (A’s points_for)
            d["pa_a"] += pa
            d["pa_b"] += pf

    out: List[CompletedGame] = []
    for (a, b), v in tmp.items():
        # Final head-to-head sign for the season between a and b
        res_a = 1 if v["res_a"] > 0 else (-1 if v["res_a"] < 0 else 0)
        out.append(CompletedGame(a, b, res_a, v["pd_a"], v["pa_a"], v["pa_b"]))
    return out

def fetch_remaining_pairs(conn, teams: List[str], season: int) -> List[RemainingGame]:
    with conn.cursor() as cur:
        cur.execute(
            "WITH cand AS ("
            "  SELECT LEAST(school,opponent) a, GREATEST(school,opponent) b FROM games "
            "  WHERE season=%s AND final=FALSE AND region_game=TRUE "
            "    AND school = ANY(%s) AND opponent = ANY(%s)"
            ") SELECT DISTINCT a,b FROM cand",
            (season, teams, teams),
        )
        return [RemainingGame(a,b) for a,b in cur.fetchall()]


# --------------------------- Aggregation for Steps 1 & 5 ---------------------------

def standings_from_mask(teams, completed, remaining, outcome_mask, pa_win, margins, base_margin_default=7):
    """Compute W/L/T and PA for all teams for a given outcome mask.
    Implements: Step 5 (PA accumulation).
    """
    wl_totals = {t: {"w":0, "l":0, "t":0, "pa":0} for t in teams}
    # Completed region games
    for comp_game in completed:
        if comp_game.res_a == 1:
            wl_totals[comp_game.a]["w"] += 1; wl_totals[comp_game.b]["l"] += 1
        elif comp_game.res_a == -1:
            wl_totals[comp_game.b]["w"] += 1; wl_totals[comp_game.a]["l"] += 1
        else:
            wl_totals[comp_game.a]["t"] += 1; wl_totals[comp_game.b]["t"] += 1
        # Step 5 – PA from completed games
        wl_totals[comp_game.a]["pa"] += comp_game.pa_a; wl_totals[comp_game.b]["pa"] += comp_game.pa_b
    # Remaining region games (winner/loser by mask; PA includes margin for loser)
    for i, rem_game in enumerate(remaining):
        bit = (outcome_mask >> i) & 1
        winner, loser = (rem_game.a, rem_game.b) if bit==1 else (rem_game.b, rem_game.a)
        m = margins.get((rem_game.a, rem_game.b), base_margin_default)
        wl_totals[winner]["w"] += 1; wl_totals[loser]["l"] += 1
        wl_totals[winner]["pa"] += pa_win; wl_totals[loser]["pa"] += pa_win + m
    return wl_totals


# --------------------------- Maps for Steps 1 & 3 ---------------------------

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
        if comp_game.res_a==1: h2h_points[(comp_game.a,comp_game.b)]+=1.0
        elif comp_game.res_a==-1: h2h_points[(comp_game.b,comp_game.a)]+=1.0
        else:
            h2h_points[(comp_game.a,comp_game.b)]+=0.5; h2h_points[(comp_game.b,comp_game.a)]+=0.5
        # Step 3: ±12 capped PD
        cap_a = max(-12, min(12, comp_game.pd_a))
        capped_pd_map[(comp_game.a,comp_game.b)]+=cap_a; capped_pd_map[(comp_game.b,comp_game.a)]-=cap_a
        # Raw margin (not used in sort, but kept for reference)
        pd_uncap[(comp_game.a,comp_game.b)]+=comp_game.pd_a; pd_uncap[(comp_game.b,comp_game.a)]-=comp_game.pd_a
    # Remaining H2H (driven by mask & margins)
    for i, rem_game in enumerate(remaining):
        bit=(outcome_mask>>i)&1; m=margins.get((rem_game.a,rem_game.b),base_margin_default)
        if bit==1:
            h2h_points[(rem_game.a,rem_game.b)]+=1.0
            capped_pd_map[(rem_game.a,rem_game.b)]+=min(m,12); capped_pd_map[(rem_game.b,rem_game.a)]-=min(m,12)
            pd_uncap[(rem_game.a,rem_game.b)]+=m; pd_uncap[(rem_game.b,rem_game.a)]-=m
        else:
            h2h_points[(rem_game.b,rem_game.a)]+=1.0
            capped_pd_map[(rem_game.a,rem_game.b)]-=min(m,12); capped_pd_map[(rem_game.b,rem_game.a)]+=min(m,12)
            pd_uncap[(rem_game.a,rem_game.b)]-=m; pd_uncap[(rem_game.b,rem_game.a)]+=m
    return h2h_points, capped_pd_map, pd_uncap


# --------------------------- Steps 2 & 4 arrays ---------------------------

def step2_step4_arrays(
    teams,
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
    rem_idx  = {(rg.a, rg.b): i  for i, rg in enumerate(remaining)}

    def res_vs(team, opp):
        a, b, _ = normalize_pair(team, opp)
        comp_game = comp_idx.get((a, b))
        if comp_game is not None:
            if comp_game.res_a == 1:
                return 2 if team == a else 0
            if comp_game.res_a == -1:
                return 0 if team == a else 2
            return 1  # split/“tie” in our encoding
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
            # comp_game.pd_a is the raw differential from a's POV; cap to ±12
            raw = comp_game.pd_a if team == a else -comp_game.pd_a
            return max(-12, min(12, raw))

        idx = rem_idx.get((a, b))
        if idx is None:
            return None

        # For remaining games, use simulated margin and cap to ±12
        bit = (outcome_mask >> idx) & 1
        m = margins.get((a, b), base_margin_default)
        m_capped = max(-12, min(12, m))
        if bit == 1:  # a defeats b by m
            return m_capped if team == a else -m_capped
        else:        # b defeats a by m
            return -m_capped if team == a else m_capped

    step2 = {s: [res_vs(s, o) for o in outside] for s in bucket}
    step4 = {s: [pd_vs(s,  o) for o in outside] for s in bucket}
    return step2, step4


# --------------------------- Sequential Tie Resolution ---------------------------

def _key_step2(step2_row):
    """
    Canonical, lexicographic key for Step 2 vectors:
    - Higher result is better (2>1>0), None sorts last (worst).
    We invert to negative so 'smaller' tuple means 'better' in Python sort.
    """
    return tuple(-(x if x is not None else -10**9) for x in step2_row)

def _key_step4(step4_row):
    """
    Canonical, lexicographic key for Step 4 vectors:
    - Higher PD is better; None sorts last (worst).
    We invert to negative so 'smaller' tuple means 'better'.
    """
    return tuple(-(x if x is not None else -10**9) for x in step4_row)

def _partition_by(items, key_func):
    """
    Partition 'items' (list of team names) by the key computed from key_func(team).
    Returns list of groups (each group is a list of team names) in deterministic order.
    Determinism rule: alphabetical order *within* each equal-key group.
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for t in items:
        buckets[key_func(t)].append(t)
    out = []
    for k in sorted(buckets.keys()):
        out.append(sorted(buckets[k]))  # alphabetical within equal key
    return out

def _pair_h2h_points(a: str, b: str, completed, remaining, outcome_mask, margins, base_margin_default=7) -> Tuple[float,float]:
    """
    Direct head-to-head points for the specific pair (a,b), NOT aggregated vs everyone.
    Returns (pts_a, pts_b) where win=1, tie/split=0.5 each.
    """
    pts_a = 0.0
    pts_b = 0.0
    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx  = {(rg.a, rg.b): i  for i, rg in enumerate(remaining)}

    # Completed meetings
    cg = comp_idx.get(normalize_pair(a,b)[:2])
    if cg is not None:
        if cg.res_a == 1:
            if a == cg.a: pts_a += 1.0
            else: pts_b += 1.0
        elif cg.res_a == -1:
            if a == cg.a: pts_b += 1.0
            else: pts_a += 1.0
        else:
            pts_a += 0.5; pts_b += 0.5

    # Remaining single game between them (region schedules are typically one game)
    idx = rem_idx.get(normalize_pair(a,b)[:2])
    if idx is not None:
        bit = (outcome_mask >> idx) & 1
        winner = remaining[idx].a if bit == 1 else remaining[idx].b
        if winner == a: pts_a += 1.0
        else: pts_b += 1.0

    return pts_a, pts_b

def _pair_h2h_pd_capped(a: str, b: str, completed, remaining, outcome_mask, margins, base_margin_default=7) -> int:
    """
    Direct head-to-head capped point differential (±12 per game) for the specific pair (a,b).
    Positive means advantage to 'a'.
    """
    pd = 0
    comp_idx = {(cg.a, cg.b): cg for cg in completed}
    rem_idx  = {(rg.a, rg.b): i  for i, rg in enumerate(remaining)}

    cg = comp_idx.get(normalize_pair(a,b)[:2])
    if cg is not None:
        raw = cg.pd_a if a == cg.a else -cg.pd_a
        pd += max(-12, min(12, raw))

    idx = rem_idx.get(normalize_pair(a,b)[:2])
    if idx is not None:
        bit = (outcome_mask >> idx) & 1
        m = margins.get((remaining[idx].a, remaining[idx].b), base_margin_default)
        m_capped = max(-12, min(12, m))
        if bit == 1:
            # remaining[idx].a defeats remaining[idx].b
            if a == remaining[idx].a: pd += m_capped
            else: pd -= m_capped
        else:
            # remaining[idx].b defeats remaining[idx].a
            if a == remaining[idx].a: pd -= m_capped
            else: pd += m_capped

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
        print(f"[DEBUG TIE]     Pair Step6 coin flip needed -> alphabetical")
    return sorted([a, b])

def resolve_bucket(
    bucket, teams, wl_totals, base_order, completed, remaining,
    outcome_mask, margins, base_margin_default=7, coin_flip_collector: Optional[List[List[str]]]=None, debug=False
):
    """
    Apply Steps 1–6 to order a single tie bucket, SEQUENTIALLY.
    - After any step partitions a 3+ tie down to a size-2 subgroup, that subgroup
      is re-resolved starting from Step 1 (head-to-head), as required.
    """
    if len(bucket) == 1:
        return bucket[:]

    if debug and len(bucket) > 2:
        print("[DEBUG TIE] ===== Resolve bucket =====")
        print(f"Bucket teams: {bucket}")

    print(f"[DEBUG] resolve_bucket: completed={completed}")
    print(f"[DEBUG] resolve_bucket: remaining={remaining}")
    print(f"[DEBUG] resolve_bucket: outcome_mask={outcome_mask}")
    print(f"[DEBUG] resolve_bucket: margins={margins}")
    print(f"[DEBUG] resolve_bucket: base_margin_default={base_margin_default}")

    # Precompute inputs used by steps
    h2h_pts, h2h_pd_cap, _ = build_h2h_maps(
        completed, remaining, outcome_mask, margins, base_margin_default
    )
    # Step 1 tally across the bucket
    step1 = {s: 0.0 for s in bucket}
    for s in bucket:
        for o in bucket:
            if s == o:
                continue
            step1[s] += h2h_pts.get((s, o), 0.0)

    # Step 3 (capped H2H PD) across the bucket
    step3 = {s: 0 for s in bucket}
    for s in bucket:
        for o in bucket:
            if s == o:
                continue
            step3[s] += h2h_pd_cap.get((s, o), 0)

    print(f"[DEBUG] resolve_bucket: bucket={bucket}, step1={step1}, step3={step3}")

    # Step 2 / Step 4 arrays vs outside
    step2, step4 = step2_step4_arrays(
        teams, bucket, base_order, completed, remaining,
        outcome_mask, margins, base_margin_default
    )

    if debug and len(bucket) > 2:
        print(f"Step1 H2H totals: {step1}")
        print(f"Step3 H2H PD (cap ±12): {step3}")
        print(f"Step2 keys: {{"
              + ", ".join(f"{t}: {_key_step2(step2[t])}" for t in bucket)
              + " }}")
        print(f"Step4 keys: {{"
              + ", ".join(f"{t}: {_key_step4(step4[t])}" for t in bucket)
              + " }}")

    # Work list of groups to resolve, sequentially through steps
    pending_groups = [sorted(bucket)]
    resolved_order: List[str] = []

    def push_coinflip(groups):
        if coin_flip_collector is not None:
            for g in groups:
                if len(g) > 1:
                    coin_flip_collector.append(sorted(g))

    # Step 1: partition by Step 1 score (DO NOT include team in key; sort alpha inside groups)
    next_groups = []
    for g in pending_groups:
        parts = _partition_by(g, key_func=lambda t: -step1[t])
        if debug and len(bucket) > 2:
            print(f"[DEBUG TIE] -> After Step1 partition: {parts}")
        next_groups.extend(parts)
    pending_groups = next_groups

    # Apply Step 2, Step 3, Step 4, Step 5 in sequence.
    # After each step, if a part has size==2, restart chain for that pair immediately.
    for step_label, key_builder in [
        ("Step2", lambda t: _key_step2(step2[t])),     # higher is better -> smaller tuple after negation
        ("Step3", lambda t: -step3[t]),                # higher PD better
        ("Step4", lambda t: _key_step4(step4[t])),     # higher PD better -> smaller tuple after negation
        ("Step5", lambda t: wl_totals[t]["pa"]),       # fewer PA better
    ]:
        next_groups = []
        for g in pending_groups:
            if len(g) == 1:
                next_groups.append(g)
                continue
            if len(g) == 2:
                # Restart from Step 1 for this pair using DIRECT pairwise metrics
                if debug and len(bucket) > 2:
                    print(f"[DEBUG TIE] {step_label}: reduced to pair {g} -> restart from Step 1")
                ordered = _resolve_pair_using_steps(g, step2, step4, wl_totals, completed, remaining,
                                                    outcome_mask, margins, base_margin_default, debug=debug)
                next_groups.append(ordered)
                continue
            # Size >= 3: partition by this step (no team name in key)
            parts = _partition_by(g, key_func=lambda t: key_builder(t))
            if debug and  len(bucket) > 2:
                print(f"[DEBUG TIE] -> After {step_label} partition: {parts}")
            # If any part shrinks to 2, resolve that pair immediately per rule
            for part in parts:
                if len(part) == 2:
                    if debug and  len(bucket) > 2:
                        print(f"[DEBUG TIE] {step_label}: subgroup {part} -> restart chain")
                    ordered = _resolve_pair_using_steps(part, step2, step4, wl_totals, completed, remaining,
                                                        outcome_mask, margins, base_margin_default, debug=debug)
                    next_groups.append(ordered)
                else:
                    next_groups.append(part)
        pending_groups = next_groups

    # After Step 5, any remaining multi-team ties would go to Step 6 (coin flip).
    # We keep deterministic output (alphabetical) but expose who'd need a flip.
    unresolved_multi = [g for g in pending_groups if len(g) > 1]
    if unresolved_multi:
        push_coinflip(unresolved_multi)

    # Stitch final order (each group is already ordered)
    for g in pending_groups:
        resolved_order.extend(g)

    if debug and len(bucket) > 2:
        print(f"Final resolved order for bucket: {resolved_order}")
        print("[DEBUG TIE] ===== End bucket =====")

    return resolved_order


# --------------------------- Region Resolution ---------------------------

def base_bucket_order(teams,wl_totals):
    """Pre-order to form buckets BEFORE Steps 1–6:
       sort by region winning %, then fewest losses, then name.
    """
    def key(s):
        w,l,t=wl_totals[s]["w"],wl_totals[s]["l"],wl_totals[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        return (-wp, l, s)
    return sorted(teams, key=key)

def tie_bucket_groups(teams,wl_totals):
    """Groups teams with identical (rounded) win% and losses into tie buckets,
       preserving base_bucket_order across buckets.
    """
    buckets=defaultdict(list)
    for s in teams:
        w,l,t=wl_totals[s]["w"],wl_totals[s]["l"],wl_totals[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        buckets[(round(wp,6),l)].append(s)
    order=base_bucket_order(teams,wl_totals); seen=set(); out=[]
    for s in order:
        if s in seen: continue
        w,l,t=wl_totals[s]["w"],wl_totals[s]["l"],wl_totals[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        group=buckets[(round(wp,6),l)]
        out.append(sorted(group)); seen.update(group)
    return out

def resolve_standings_for_mask(teams,completed,remaining,outcome_mask,margins,base_margin_default=7,pa_win=14, debug=False):
    """Resolve ordering/ties for a full region under a single mask.
    Calls resolve_bucket() on each tie bucket in base order.
    """
    wl_totals=standings_from_mask(teams,completed,remaining,outcome_mask,pa_win,margins,base_margin_default)
    base_order=base_bucket_order(teams,wl_totals)
    print(f"[DEBUG] Outcome mask INSIDE: base order = {base_order}")
    print(f"[DEBUG] Outcome mask INSIDE: tie_bucket_groups(teams,wl_totals) = {tie_bucket_groups(teams,wl_totals)}")
    final=[]
    coinflip_events: List[List[str]] = []  # collected Step 6 reports, not used further
    for bucket in tie_bucket_groups(teams,wl_totals):
        final.extend(resolve_bucket(bucket,teams,wl_totals,base_order,completed,remaining,
                                    outcome_mask,margins,base_margin_default,
                                    coin_flip_collector=coinflip_events, debug=debug))
    # NOTE: coinflip_events is available here if you want to surface it in outputs.
    return final

def rank_to_slots(order):
    """Convert strict order into seed slots (lo, hi)."""
    return {s:(i,i) for i,s in enumerate(order,start=1)}

def unique_intra_bucket_games(buckets,remaining):
    """Return remaining games where both teams appear in the same non-singleton bucket.
       Used for Step-3 knife-edge threshold detection.
    """
    inb=set().union(*(set(b) for b in buckets if len(b)>1)); seen=set(); out=[]
    for rem_game in remaining:
        if rem_game.a in inb and rem_game.b in inb:
            key=(rem_game.a,rem_game.b)
            if key not in seen:
                seen.add(key); out.append(rem_game)
    return out


# ---------- Boolean minimization helpers (for readable scenarios) ----------
def minimize_minterms(minterms):
    """Simplify minterms by absorption/combination. Logic unchanged from previous versions."""
    terms={frozenset(m.items()) for m in minterms}
    changed=True
    while changed:
        before=len(terms)
        # absorption
        to_remove=set()
        lst=list(terms)
        for i,a in enumerate(lst):
            for j,b in enumerate(lst):
                if i!=j and a.issuperset(b):
                    to_remove.add(a)
        if to_remove:
            terms=terms - to_remove
        # combine (one-variable differences)
        lst=list(terms); n=len(lst); merged=set(); used=[False]*n
        for i in range(n):
            for j in range(i+1,n):
                a=lst[i]; b=lst[j]
                da=dict(a); db=dict(b)
                keys=set(da.keys())|set(db.keys())
                diffs=[k for k in keys if da.get(k,None)!=db.get(k,None)]
                if len(diffs)==1:
                    k=diffs[0]
                    if k in da and k in db:
                        new=dict(da); new.pop(k,None)
                        merged.add(frozenset(new.items()))
                        used[i]=used[j]=True
        out=set()
        for idx,t in enumerate(lst):
            if not used[idx]: out.add(t)
        out |= merged
        terms=out
        changed=(len(terms)!=before)
    return [dict(t) for t in terms]


# ---------- Main enumeration + outputs ----------
def enumerate_region(conn, clazz, region, season, out_csv=None, explain_json=None, out_seeding=None, out_scenarios=None, debug=False):
    """
    Enumerate all remaining outcomes for a (class, region, season), apply the tiebreakers,
    and aggregate seeding odds + human-readable scenario explanations.

    Notes
    -----
    - Each undecided region game is treated as a boolean variable (first-listed team wins or not).
    - For each outcome mask (2^R), we optionally split by any Step-3 knife-edge (±12 cap)
      that changes ordering, weighting <threshold vs ≥threshold branches appropriately.
    - We tally 1st..4th odds across all branches; playoffs = sum of those four odds.
    """
    # ----- Fetch inputs -----
    teams = fetch_division(conn, clazz, region, season)
    if not teams:
        raise SystemExit("No teams found.")
    completed = fetch_completed_pairs(conn, teams, season)   # fixed results already known
    print(f"Completed games:", completed)
    remaining = fetch_remaining_pairs(conn, teams, season)  # undecided region games
    num_remaining = len(remaining)

    # ----- Accumulators for odds -----
    first_counts  = Counter()
    second_counts = Counter()
    third_counts  = Counter()
    fourth_counts = Counter()

    # team -> seed -> list of minterm dicts (for explanations)
    scenario_minterms = {}

    # Simulation knobs
    pa_for_winner = 14  # Step 5: PA credited to the winner of a simulated game
    base_margins = {(rem_game.a, rem_game.b): 7 for rem_game in remaining}  # default PD if no knife-edge

    # Boolean variables for remaining games, in bit order (e.g., "A>B")
    boolean_game_vars = []
    for idx, rem_game in enumerate(remaining):
        var_name = f"{rem_game.a}>{rem_game.b}"
        boolean_game_vars.append((var_name, rem_game.a, rem_game.b))

    # ----- If no remaining games, resolve once and tally -----
    if num_remaining == 0:
        final_order = resolve_standings_for_mask(
            teams, completed, remaining, 0,
            margins={}, base_margin_default=7, pa_win=pa_for_winner, debug=debug,
        )
        slots = rank_to_slots(final_order)
        for team, (lo_seed, hi_seed) in slots.items():
            if 1 >= lo_seed and 1 <= hi_seed: first_counts[team]  += 1
            if 2 >= lo_seed and 2 <= hi_seed: second_counts[team] += 1
            if 3 >= lo_seed and 3 <= hi_seed: third_counts[team]  += 1
            if 4 >= lo_seed and 4 <= hi_seed: fourth_counts[team] += 1
        denom = 1.0

    # ----- Otherwise enumerate all masks (2^R) -----
    else:
        total_masks = 1 << num_remaining
        for outcome_mask in range(total_masks):
            # 1) Decode this mask into a base assignment dict for explanations
            var_assignment = { }
            for bit_index, (var_name, team_a, team_b) in enumerate(boolean_game_vars):
                bit_value = (outcome_mask >> bit_index) & 1
                var_assignment[var_name] = bool(bit_value)

            # 2) Compute standings with default margins to locate tie buckets
            wl_totals = standings_from_mask(
                teams, completed, remaining, outcome_mask,
                pa_for_winner, base_margins, base_margin_default=7,
            )
            tie_buckets = tie_bucket_groups(teams, wl_totals)

            print(f"[DEBUG] Outcome mask {outcome_mask:0{num_remaining}b}: tie buckets = {tie_buckets}")

            # Remaining games where both teams are in the same tie bucket
            intra_bucket_games = unique_intra_bucket_games(tie_buckets, remaining)

            # Build an index so we can flip/inspect individual game bits
            rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

            # 3) Find knife-edge thresholds (if any) for Step-3 within-bucket matchups
            #    IMPORTANT: do this per *direction* (a>b and b>a), each against its own same-direction baseline (margin=7).
            thresholds_dir = {}  # key: ((a,b), winner_str) -> threshold int or None

            if intra_bucket_games:
                for rem_game in intra_bucket_games:
                    a, b = rem_game.a, rem_game.b
                    idx = rem_idx[(a, b)]

                    for winner in (a, b):
                        # Construct a mask where this matchup is won by `winner`
                        current_bit = (outcome_mask >> idx) & 1
                        want_bit = 1 if winner == a else 0
                        mask_for_dir = outcome_mask if current_bit == want_bit else (outcome_mask ^ (1 << idx))

                        # Baseline: same-direction winner with margin=7
                        baseline_margins = dict(base_margins)
                        baseline_margins[(a, b)] = 7
                        baseline_order = resolve_standings_for_mask(
                            teams, completed, remaining, mask_for_dir,
                            margins=baseline_margins, base_margin_default=7, pa_win=pa_for_winner,
                        )
                        baseline_seed_pos = {t: baseline_order.index(t) + 1 for t in teams}

                        print(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: baseline order = {baseline_order}")

                        # Scan margins 1..12 for the same-direction winner
                        found = None
                        for m in range(1, 13):
                            test_margins = dict(base_margins)
                            test_margins[(a, b)] = m
                            test_order = resolve_standings_for_mask(
                                teams, completed, remaining, mask_for_dir,
                                margins=test_margins, base_margin_default=7, pa_win=pa_for_winner,
                            )
                            test_seed_pos = {t: test_order.index(t) + 1 for t in teams}
                            if any(baseline_seed_pos[t] != test_seed_pos[t] for t in teams):
                                found = m
                                print(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: "
                                      f"test=({winner} by {m}) -> threshold={found}: order = {test_order}")
                                break

                        thresholds_dir[((a, b), winner)] = found

                        # Helpful debug
                        print(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: "
                            f"baseline=({winner} by 7) -> threshold={found}")

            # 4) If no thresholds for this mask, resolve once; else split by thresholds that match the mask’s winners
            #    i.e., for each intra-bucket matchup we use the threshold for the *actual* winner in this mask
            if not intra_bucket_games:
                # (unchanged: resolve once)
                final_order = resolve_standings_for_mask(
                    teams, completed, remaining, outcome_mask,
                    margins=base_margins, base_margin_default=7, pa_win=pa_for_winner,
                )
                slots = rank_to_slots(final_order)
                for team, (lo_seed, hi_seed) in slots.items():
                    if 1 >= lo_seed and 1 <= hi_seed: first_counts[team]  += 1
                    if 2 >= lo_seed and 2 <= hi_seed: second_counts[team] += 1
                    if 3 >= lo_seed and 3 <= hi_seed: third_counts[team]  += 1
                    if 4 >= lo_seed and 4 <= hi_seed: fourth_counts[team] += 1
                for team, (lo_seed, hi_seed) in slots.items():
                    scenario_minterms.setdefault(team, {}).setdefault(lo_seed, []).append(dict(var_assignment))
            else:
                # Gather only the active thresholds (matching mask winners)
                active_pairs = []
                for rem_game in intra_bucket_games:
                    a, b = rem_game.a, rem_game.b
                    idx = rem_idx[(a, b)]
                    mask_winner = a if ((outcome_mask >> idx) & 1) == 1 else b
                    t = thresholds_dir.get(((a, b), mask_winner))
                    if t is not None:
                        active_pairs.append(((a, b), mask_winner, t))

                if not active_pairs:
                    # No active thresholds: resolve once with base_margins
                    final_order = resolve_standings_for_mask(
                        teams, completed, remaining, outcome_mask,
                        margins=base_margins, base_margin_default=7, pa_win=pa_for_winner,
                    )
                    slots = rank_to_slots(final_order)
                    for team, (lo_seed, hi_seed) in slots.items():
                        if 1 >= lo_seed and 1 <= hi_seed: first_counts[team]  += 1
                        if 2 >= lo_seed and 2 <= hi_seed: second_counts[team] += 1
                        if 3 >= lo_seed and 3 <= hi_seed: third_counts[team]  += 1
                        if 4 >= lo_seed and 4 <= hi_seed: fourth_counts[team] += 1
                    for team, (lo_seed, hi_seed) in slots.items():
                        scenario_minterms.setdefault(team, {}).setdefault(lo_seed, []).append(dict(var_assignment))
                else:
                    # Split only on the thresholds relevant to the mask’s winners
                    # Build cartesian product of {<t, ≥t} for these active thresholds
                    from itertools import product
                    for branch_bits in product([0, 1], repeat=len(active_pairs)):
                        branch_margins = dict(base_margins)
                        branch_assignment = dict(var_assignment)
                        branch_weight = 1.0

                        for ((a, b), winner, t), bit in zip(active_pairs, branch_bits):

                            # Use the ACTUAL winner’s orientation for the variable name
                            opp = b if winner == a else a
                            var_margin_flag = f"{winner}>{opp}_GE{t}"

                            if bit == 1:
                                # ≥ t branch
                                branch_margins[(a, b)] = t
                                branch_assignment[var_margin_flag] = True
                                branch_weight *= (13 - t) / 12.0
                            else:
                                # < t branch
                                branch_margins[(a, b)] = max(1, t - 1)
                                branch_assignment[var_margin_flag] = False
                                branch_weight *= (t - 1) / 12.0

                        # Resolve this branch
                        final_order = resolve_standings_for_mask(
                            teams, completed, remaining, outcome_mask,
                            margins=branch_margins, base_margin_default=7, pa_win=pa_for_winner,
                        )
                        slots = rank_to_slots(final_order)
                        for team, (lo_seed, hi_seed) in slots.items():
                            if 1 >= lo_seed and 1 <= hi_seed: first_counts[team]  += branch_weight  # type: ignore
                            if 2 >= lo_seed and 2 <= hi_seed: second_counts[team] += branch_weight  # type: ignore
                            if 3 >= lo_seed and 3 <= hi_seed: third_counts[team]  += branch_weight  # type: ignore
                            if 4 >= lo_seed and 4 <= hi_seed: fourth_counts[team] += branch_weight  # type: ignore
                        for team, (lo_seed, hi_seed) in slots.items():
                            scenario_minterms.setdefault(team, {}).setdefault(lo_seed, []).append(branch_assignment)

        # Each mask contributes weight 1; branch weights within a mask sum to 1.
        denom = float(1 << num_remaining)

    # ----- Compile/emit odds CSV (same format as before) -----
    results = []
    for school in teams:
        p1 = first_counts[school]  / denom
        p2 = second_counts[school] / denom
        p3 = third_counts[school]  / denom
        p4 = fourth_counts[school] / denom
        p_playoffs = p1 + p2 + p3 + p4
        clinched = p_playoffs >= 0.999
        eliminated = p_playoffs <= 0.001
        final_playoffs = 1.0 if clinched else (0.0 if eliminated else p_playoffs)
        results.append((school, p1, p2, p3, p4, p_playoffs, final_playoffs, clinched, eliminated))

    print("school,odds_1st,odds_2nd,odds_3rd,odds_4th,odds_playoffs,final_odds_playoffs,clinched,eliminated")
    for row in sorted(results, key=lambda r: (-r[6], r[0])):
        print("{},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{},{}".format(*row))

    # ----- Optional seeding-odds text output -----
    if out_seeding:
        by_seed = {1: [], 2: [], 3: [], 4: [], "out": []}
        for (school, o1, o2, o3, o4, op, fop, clinched, eliminated) in results:
            by_seed[1].append((school, o1))
            by_seed[2].append((school, o2))
            by_seed[3].append((school, o3))
            by_seed[4].append((school, o4))
            by_seed["out"].append((school, 1.0 - op))
        for k in [1, 2, 3, 4, "out"]:
            by_seed[k].sort(key=lambda x: (-x[1], x[0]))

        lines = [f"Region {region}-{clazz}A", ""]
        for seed_num in [1, 2, 3, 4]:
            lines.append(f"{seed_num} Seed:")
            wrote_any = False
            for team, prob in by_seed[seed_num]:
                if prob > 0:
                    lines.append(f"{pct_str(prob)} {team}")
                    wrote_any = True
            if not wrote_any:
                lines.append("None")
            lines.append("")

        lines.append("5 Seed (Out):")
        wrote_any = False
        for team, prob in by_seed["out"]:
            if prob > 0:
                lines.append(f"{pct_str(prob)} {team}")
                wrote_any = True
        if not wrote_any:
            lines.append("None")

        lines.append("")
        lines.append("Eliminated:")
        eliminated_teams = [team for team in by_seed["out"] if abs(team[1] - 1.0) < 1e-12]
        if eliminated_teams:
            for t, _ in sorted(eliminated_teams):
                lines.append(t)
        else:
            lines.append("None")

        out_path = out_seeding
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Wrote seeding odds text: {out_path}")

    # ----- Optional scenarios text output (unchanged logic; clearer helpers) -----
    if out_scenarios:
        def var_phrase(var: str, val: bool, base_lookup: dict) -> str:
            """
            Turn a variable into a human phrase.
            - base_lookup contains base booleans like "A>B": True/False.
            - Handles when margin flags are stored in the opposite orientation of the base var.
            """
            if "_GE" in var:
                base, ge = var.split("_GE", 1)
                a, b = base.split(">", 1)

                # Try exact base first
                base_val = base_lookup.get(base)
                if base_val is None:
                    # Try flipped orientation
                    flip = f"{b}>{a}"
                    flip_val = base_lookup.get(flip)
                    if flip_val is not None:
                        # flip_val == True means (b beats a)
                        # flip_val == False means (a beats b)
                        winner, loser = (b, a) if flip_val else (a, b)
                    else:
                        # Last-resort fallback (should be rare after minimization)
                        # assume lexicographic "a>b" True implies a wins; else b wins
                        winner, loser = (a, b) if val else (b, a)
                else:
                    # base_val == True means (a beats b)
                    # base_val == False means (b beats a)
                    winner, loser = (a, b) if base_val else (b, a)

                return (
                    f"{winner} Win over {loser} by ≥ {ge} points"
                    if val else
                    f"{winner} Win over {loser} by < {ge} points"
                )

            # Base (non-margin) phrasing
            a, b = var.split(">", 1)
            return f"{a} Win over {b}" if val else f"{b} Win over {a}"

        def extract_pair(clause: str):
            """Parse a human clause into a structured tuple: (a, b, kind, thr) where
            kind ∈ {'base','ge','lt'} and thr is an int or None."""
            if " Win over " not in clause:
                return None
            left, right = clause.split(" Win over ", 1)
            a = left.strip()
            # Margin-qualified?
            if " by ≥ " in right:
                opp_part, thr_part = right.split(" by ≥ ", 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, 'ge', thr)
            elif " by < " in right:
                opp_part, thr_part = right.split(" by < ", 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, 'lt', thr)
            else:
                b = right.split(" by")[0].strip()
                return (a, b, 'base', None)

        def is_opposite(p1, p2):
            """
            Two clauses are 'opposites' if:
              (1) directions flip (A>B vs B>A) and both are base; OR
              (2) directions flip and both margin-qualified with SAME comparator and threshold; OR
              (3) same direction, same threshold, but complementary comparators (≥ vs <).
            """
            if p1 is None or p2 is None:
                return False
            a1, b1, k1, t1 = p1
            a2, b2, k2, t2 = p2
            # Opposite directions
            if a1 == b2 and b1 == a2:
                if k1 == 'base' and k2 == 'base':
                    return True
                if k1 == k2 and t1 == t2 and k1 in ('ge', 'lt'):
                    return True
            # Same direction, complementary threshold comparators
            if a1 == a2 and b1 == b2 and t1 == t2 and {k1, k2} == {'ge', 'lt'}:
                return True
            return False

        minimized = defaultdict(dict)
        for team, seed_map in scenario_minterms.items():
            for seed_num, minterms in seed_map.items():
                mins = [dict(m) for m in minterms]
                mins = minimize_minterms(mins)  # simplify
                minimized[seed_num][team] = mins

        lines = [f"Region {region}-{clazz}A", ""]
        prob_index = {1: 1, 2: 2, 3: 3, 4: 4}

        for seed_num in [1, 2, 3, 4]:
            lines.append(f"{seed_num} Seed:")
            # Map team -> P(seed_num)
            prob_map = {row[0]: row[prob_index[seed_num]] for row in results}
            teams_sorted = [t for t in sorted(prob_map, key=lambda t: -prob_map[t]) if prob_map[t] > 0]

            for team in teams_sorted:
                p = prob_map[team]
                lines.append(f"{pct_str(p)} {team}")
                if abs(p - 1.0) < 1e-12:
                    lines.append("")
                    continue

                # Render minterms into consolidated clause blocks
                candidate_minterms = minimized.get(seed_num, {}).get(team, [])

                def clauses_for_m(minterm_dict):
                    # Prefer margin-qualified clauses where present; avoid duplicates.
                    def flip_base(base: str) -> str:
                        if ">" in base:
                            a, b = base.split(">", 1)
                            return f"{b}>{a}"
                        return base

                    # Collect margin flags keyed by BOTH orientations for safety
                    margin_map = {}
                    base_pairs = []
                    for var, val in minterm_dict.items():
                        if "_GE" in var:
                            base, _ = var.split("_GE", 1)
                            margin_map[base] = (var, val)
                            margin_map[flip_base(base)] = (var, val)  # allow reversed lookup
                        else:
                            base_pairs.append((var, val))

                    clauses = []
                    # If a margin flag exists for this matchup (in either orientation), skip the base clause
                    for var, val in base_pairs:
                        if var not in margin_map:
                            clauses.append(var_phrase(var, val, minterm_dict))
                    # Then add the single margin-qualified clause for each matchup
                    used = set()
                    for key, (mvar, mval) in margin_map.items():
                        if mvar in used:
                            continue
                        clauses.append(var_phrase(mvar, mval, minterm_dict))
                        used.add(mvar)# --- Stable clause ordering: by matchup priority, then comparator rank ---
                    
                    # Build a lookup: "A>B" -> position in boolean_game_vars
                    matchup_index = {name: i for i, (name, _, _) in enumerate(boolean_game_vars)}

                    def clause_sort_key(c: str):
                        parsed = extract_pair(c)  # (a, b, kind, thr) or None
                        if not parsed:
                            # Non-game clause (shouldn't happen here), push to end deterministically
                            return (10**6, 99, c)
                        a, b, kind, thr = parsed
                        base = f"{a}>{b}"
                        # normalize to lexicographic base (matches how you create var names)
                        aa, bb, _ = normalize_pair(a, b)
                        lex_base = f"{aa}>{bb}"
                        # prefer exact base if present in boolean_game_vars, else its flipped lex base
                        idx = matchup_index.get(base, matchup_index.get(lex_base, 10**6))
                        # comparator rank: base first (0), then ge (1), then lt (2)
                        comp_rank = 0 if kind == 'base' else (1 if kind == 'ge' else 2)
                        return (idx, comp_rank, c)

                    clauses.sort(key=clause_sort_key)
                    return clauses

                def block_sort_key(block_clauses: List[str]):
                    # Sort blocks by: (a) presence & comparator of the Corinth–New Albany clause,
                    # then (b) presence/comparator of the next matchup in boolean order,
                    # then (c) total clause count (shorter first), then (d) the text itself.
                    matchup_index = {name: i for i, (name, _, _) in enumerate(boolean_game_vars)}

                    def classify_clause(c: str):
                        parsed = extract_pair(c)
                        if not parsed:
                            return (10**6, 99, c)  # push unknowns last, deterministically
                        a, b, kind, thr = parsed
                        base = f"{a}>{b}"
                        aa, bb, _ = normalize_pair(a, b)
                        lex_base = f"{aa}>{bb}"
                        idx = matchup_index.get(base, matchup_index.get(lex_base, 10**6))
                        comp_rank = 0 if kind == 'base' else (1 if kind == 'ge' else 2)
                        # We also want base (no margin) variants to come before margin variants for the same matchup
                        return (idx, comp_rank, c)

                    # Build a signature: the first two matchup-keys in the block (after internal sorting)
                    ordered = sorted(block_clauses, key=classify_clause)
                    sig = [classify_clause(c)[:2] for c in ordered[:2]]
                    # fill to 2 entries to keep tuples same length
                    while len(sig) < 2:
                        sig.append((10**6, 99))
                    return (*sig[0], *sig[1], len(block_clauses), " | ".join(ordered))

                prepared = [(m, clauses_for_m(m)) for m in candidate_minterms]
                prepared.sort(key=lambda t: block_sort_key(t[1]))

                seen_pairs = set()
                printed_any_block = False
                for _, clauses in prepared:
                    # Remove clauses that contradict any clause we’ve already printed
                    cleaned = []
                    for c in clauses:
                        parsed = extract_pair(c)
                        if parsed is None:
                            cleaned.append(c)
                            continue
                        if any(is_opposite(parsed, prev) for prev in seen_pairs):
                            continue
                        cleaned.append(c)
                    clauses = cleaned
                    if not clauses:
                        continue

                    # Mark these clause pairs as seen
                    for c in clauses:
                        parsed = extract_pair(c)
                        if parsed:
                            seen_pairs.add(parsed)

                    # Emit one OR-block
                    if printed_any_block:
                        lines.append("  OR")
                    lines.append(f"  - {clauses[0]}")
                    for clause in clauses[1:]:
                        lines.append(f"    AND {clause}")
                    printed_any_block = True
                lines.append("")

        lines.append("Eliminated:")
        eliminated_now = [row[0] for row in results if abs(row[5]) < 1e-12]
        if eliminated_now:
            for t in sorted(eliminated_now):
                lines.append(t)
        else:
            lines.append("None")

        out_path = out_scenarios
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Wrote scenarios text: {out_path}")


# --------------------------- CLI ---------------------------

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--class", dest="clazz", type=int, required=True)
    ap.add_argument("--region", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dsn", type=str, default=os.getenv("PG_DSN",""))
    ap.add_argument("--out-csv", type=str)
    ap.add_argument("--explain-json", type=str)
    ap.add_argument("--out-seeding", type=str)
    ap.add_argument("--out-scenarios", type=str)
    ap.add_argument("--debug", action="store_true")
    args=ap.parse_args()
    if not psycopg: raise SystemExit("Please install psycopg: pip install 'psycopg[binary]'")
    if not args.dsn: raise SystemExit("Provide --dsn or PG_DSN")
    with psycopg.connect(args.dsn) as conn:
        enumerate_region(conn, args.clazz, args.region, args.season,
                         out_csv=args.out_csv,
                         explain_json=args.explain_json,
                         out_seeding=args.out_seeding,
                         out_scenarios=args.out_scenarios,
                         debug=args.debug)

if __name__ == "__main__":
    main()
