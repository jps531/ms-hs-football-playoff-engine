from __future__ import annotations

import math

from prefect import flow, get_run_logger, task
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from database_helpers import get_database_connection


# -------------------------
# Helpers & Functions
# -------------------------

def pct_str(x: float) -> str:
    """Format a float as a percentage string with no more than 2 significant digits."""
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
                ordered = _resolve_pair_using_steps(g, step2, step4, wl_totals, completed, remaining,
                                                    outcome_mask, margins, base_margin_default, debug=False)
                next_groups.append(ordered)
                continue
            # Size >= 3: partition by this step (no team name in key)
            parts = _partition_by(g, key_func=lambda t: key_builder(t))
            if debug and  len(bucket) > 2:
                print(f"[DEBUG TIE] -> After {step_label} partition: {parts}")
            # If any part shrinks to 2, resolve that pair immediately per rule
            for part in parts:
                if len(part) == 2:
                    ordered = _resolve_pair_using_steps(part, step2, step4, wl_totals, completed, remaining,
                                                        outcome_mask, margins, base_margin_default, debug=False)
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



def consolidate_opposites_and_remove_bases(candidate_minterms: List[Dict[str, bool]]) -> List[Dict[str, bool]]:
    """
    1. Consolidate dictionaries that are identical except for one key whose
       boolean values are opposite — removing that differing key.
    2. Remove any base keys (e.g., 'A>B') when a GE variant (e.g., 'A>B_GE1') exists.
    """
    # --- Step 1: consolidate opposite pairs ---
    consolidated = []
    used = set()

    for i, d1 in enumerate(candidate_minterms):
        if i in used:
            continue
        merged = False
        for j, d2 in enumerate(candidate_minterms[i+1:], start=i+1):
            if j in used:
                continue
            if set(d1.keys()) != set(d2.keys()):
                continue
            differing = [k for k in d1 if d1[k] != d2[k]]
            if len(differing) == 1:
                new_dict = {k: v for k, v in d1.items() if k != differing[0]}
                consolidated.append(new_dict)
                used.update({i, j})
                merged = True
                break
        if not merged:
            consolidated.append(d1)

    # --- Step 2: remove base keys when GE variants exist ---
    cleaned = []
    for d in consolidated:
        ge_bases = {k.split('_GE')[0] for k in d if '_GE' in k}
        new_d = {k: v for k, v in d.items() if k.split('_GE')[0] not in ge_bases or '_GE' in k}
        cleaned.append(new_d)

    return cleaned


def _parse_ge_key(k: str) -> Optional[Tuple[str, int]]:
    if "_GE" not in k:
        return None
    base, _, tail = k.partition("_GE")
    try:
        t = int(tail)
    except ValueError:
        return None
    return base, t

def _signature_without_family(d: Dict[str, bool], base: str) -> Tuple[Tuple[str, bool], ...]:
    items = []
    for k, v in d.items():
        parsed = _parse_ge_key(k)
        if (parsed and parsed[0] == base) or (k == base):
            continue
        items.append((k, v))
    items.sort()
    return tuple(items)

def _interval_for_family(d: Dict[str, bool], base: str) -> Tuple[float, float]:
    lo = -math.inf
    hi = math.inf
    for k, v in d.items():
        parsed = _parse_ge_key(k)
        if not parsed:
            continue
        b, t = parsed
        if b != base:
            continue
        if v is True:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
    return lo, hi  # [lo, hi)

# ---------- pass 1: merge opposite-only pairs within the same dict set ----------
def consolidate_opposites(dicts: List[Dict[str, bool]]) -> List[Dict[str, bool]]:
    out, used = [], set()
    for i, d1 in enumerate(dicts):
        if i in used:
            continue
        merged = False
        for j in range(i + 1, len(dicts)):
            if j in used:
                continue
            d2 = dicts[j]
            if set(d1.keys()) != set(d2.keys()):
                continue
            dif = [k for k in d1 if d1[k] != d2[k]]
            if len(dif) == 1:
                kdiff = dif[0]
                nd = {k: v for k, v in d1.items() if k != kdiff}
                out.append(nd)
                used.update({i, j})
                merged = True
                break
        if not merged:
            out.append(d1)
    return out

# ---------- pass 2: cross-dict GE union -> base True when range is [win_threshold, +inf) ----------
def merge_ge_intervals_to_base_safe(dicts: List[Dict[str, bool]], win_threshold:int = 1) -> List[Dict[str, bool]]:
    groups = defaultdict(list)           # (sig, base) -> [(idx, dict, (lo,hi))]
    base_presence = defaultdict(bool)    # (sig, base) -> any dict has explicit base key

    for idx, d in enumerate(dicts):
        bases_in_d = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
        explicit_bases = {k for k in d if "_GE" not in k}
        all_bases = bases_in_d | explicit_bases
        for base in all_bases:
            sig = _signature_without_family(d, base)
            if base in d:
                base_presence[(sig, base)] = True
        for base in bases_in_d:
            sig = _signature_without_family(d, base)
            lo, hi = _interval_for_family(d, base)
            if lo < hi:
                groups[(sig, base)].append((idx, d, (lo, hi)))

    to_remove = set()
    replacements = []

    for (sig, base), entries in groups.items():
        if len(entries) < 2:
            continue
        if base_presence.get((sig, base), False):
            continue

        intervals = [iv for _, _, iv in entries]
        intervals.sort()
        # merge
        merged = []
        cur_lo, cur_hi = intervals[0]
        for lo, hi in intervals[1:]:
            if lo <= cur_hi:
                cur_hi = max(cur_hi, hi)
            else:
                merged.append((cur_lo, cur_hi))
                cur_lo, cur_hi = lo, hi
        merged.append((cur_lo, cur_hi))

        # collapse only if union == [win_threshold, +inf)
        if len(merged) == 1 and merged[0][0] <= win_threshold and merged[0][1] == math.inf:
            to_remove.update(idx for idx, _, _ in entries)
            collapsed = dict(sig)
            collapsed[base] = True
            replacements.append(collapsed)

    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    # de-dupe replacements
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

# ---------- pass 3: intra-dict base removal when any GE variant exists ----------
def remove_base_if_ge_present(dicts: List[Dict[str, bool]]) -> List[Dict[str, bool]]:
    cleaned = []
    for d in dicts:
        ge_bases = {k.split('_GE')[0] for k in d if '_GE' in k}
        cleaned.append({k: v for k, v in d.items() if (k not in ge_bases) or ('_GE' in k)})
    return cleaned

# ---------- pass 4: full-partition drop of base family when wins covered & explicit loss present ----------
def merge_full_partition_remove_base(dicts: List[Dict[str, bool]], win_threshold: int = 1) -> List[Dict[str, bool]]:
    groups = defaultdict(list)
    ge_intervals = defaultdict(list)
    has_base_true = defaultdict(bool)
    has_base_false = defaultdict(bool)

    for idx, d in enumerate(dicts):
        bases_in_ge = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
        explicit_bases = {k for k in d if "_GE" not in k and isinstance(d[k], bool)}
        all_bases = bases_in_ge | explicit_bases
        for base in all_bases:
            sig = _signature_without_family(d, base)
            groups[(sig, base)].append(idx)
            if base in bases_in_ge:
                lo, hi = _interval_for_family(d, base)
                if lo < hi:
                    ge_intervals[(sig, base)].append((lo, hi))
            if base in d:
                has_base_true[(sig, base)] |= (d[base] is True)
                has_base_false[(sig, base)] |= (d[base] is False)

    to_remove = set()
    replacements = []

    for (sig, base), idxs in groups.items():
        if not has_base_false.get((sig, base), False):
            continue

        intervals = list(ge_intervals.get((sig, base), []))
        if has_base_true.get((sig, base), False):
            intervals.append((win_threshold, math.inf))
        if not intervals:
            continue

        intervals.sort()
        merged = []
        cur_lo, cur_hi = intervals[0]
        for lo, hi in intervals[1:]:
            if lo <= cur_hi:
                cur_hi = max(cur_hi, hi)
            else:
                merged.append((cur_lo, cur_hi))
                cur_lo, cur_hi = lo, hi
        merged.append((cur_lo, cur_hi))

        if len(merged) == 1 and merged[0][0] <= win_threshold and merged[0][1] == math.inf:
            to_remove.update(idxs)
            collapsed = dict(sig)  # drop base family entirely
            replacements.append(collapsed)

    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

def remove_base_if_ge_present_in_dicts(dicts: list[dict[str, bool]]) -> list[dict[str, bool]]:
    """
    Within each dict, if both `x>y` and one or more `x>y_GEz` keys exist,
    remove the base key `x>y` (redundant with the GE-qualified entries).
    """
    cleaned = []
    for d in dicts:
        # Collect bases that appear as GE families
        ge_bases = {k.split('_GE')[0] for k in d if '_GE' in k}
        # Keep all items except base keys that belong to those families
        new_d = {k: v for k, v in d.items() if not (k in ge_bases)}
        cleaned.append(new_d)
    return cleaned

def _flip_base_key(base: str) -> str:
    if ">" in base:
        a, b = base.split(">", 1)
        return f"{b}>{a}"
    return base

# --- NEW unified GE merge: collapses to base True or a finite band ---
def merge_ge_union_unified(dicts: List[Dict[str, bool]], win_threshold: int = 1) -> List[Dict[str, bool]]:
    """
    For each (signature w/o family, base):
      * collect all GE intervals across dicts that have that GE family
      * if any dict in the group has explicit base key, skip (to avoid mixing)
      * if the union is a single interval:
          - if [L, +inf) with L <= win_threshold -> collapse to {base: True}
          - elif [L, U) with finite U -> collapse to {base_GEL: True, base_GEU: False}
    Replace all dicts in that group with the collapsed one.
    """
    groups = defaultdict(list)         # (sig, base) -> [(idx, dict, (lo, hi))]
    base_presence = defaultdict(bool)  # (sig, base) -> any explicit base key present

    for idx, d in enumerate(dicts):
        ge_bases = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
        explicit_bases = {k for k in d if "_GE" not in k and isinstance(d[k], bool)}

        for base in (ge_bases | explicit_bases):
            sig = _signature_without_family(d, base)
            if base in d:  # explicit base key
                base_presence[(sig, base)] = True

        for base in ge_bases:
            sig = _signature_without_family(d, base)
            lo, hi = _interval_for_family(d, base)
            if lo < hi:
                groups[(sig, base)].append((idx, d, (lo, hi)))

    to_remove = set()
    replacements = []

    for (sig, base), entries in groups.items():
        if len(entries) < 2:
            continue  # need at least 2 dicts contributing to a merge
        if base_presence.get((sig, base), False):
            continue  # do not mix with explicit base keys

        # merge intervals across dicts
        intervals = [iv for _, _, iv in entries]
        intervals.sort()
        merged = []
        cur_lo, cur_hi = intervals[0]
        for lo, hi in intervals[1:]:
            if lo <= cur_hi:  # overlap or touch
                cur_hi = max(cur_hi, hi)
            else:
                merged.append((cur_lo, cur_hi))
                cur_lo, cur_hi = lo, hi
        merged.append((cur_lo, cur_hi))

        if len(merged) != 1:
            continue  # discontinuous; don't collapse

        L, R = merged[0]
        collapsed = dict(sig)

        if R == math.inf and L <= win_threshold:
            # unconditional “win by any margin”
            collapsed[base] = True
        elif R != math.inf and L != -math.inf:
            # finite band [L, R)
            collapsed[f"{base}_GE{int(L)}"] = True
            collapsed[f"{base}_GE{int(R)}"] = False
        else:
            continue  # bands like (-inf, U) or [L, +inf) with L > win_threshold: skip here

        # replace the group's dicts with the collapsed one
        to_remove.update(idx for idx, _, _ in entries)
        replacements.append(collapsed)

    # build output with de-duped replacements
    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

# --- NEW: collapse ALL GE families per signature in one shot ---
def merge_ge_union_by_signature(
    dicts: List[Dict[str, bool]],
    win_threshold: int = 1,
    aggressive_upper: bool = True,
) -> List[Dict[str, bool]]:
    """
    For each signature (same non-GE keys/values), consider all bases that appear as GE families.
    For each base, union its GE intervals across the signature's dicts, then:
      - If union is one interval [L, +inf) and L <= win_threshold -> {base: True}
      - If union is one finite interval [L, U)                   -> {base_GEL: True, base_GEU: False}
      - If aggressive_upper and union includes any +inf tail     -> {base_GELmin: True}
        (This matches your desire to collapse multiple pieces into just GE_Lmin when one piece goes to +inf.)
    Skip a base if any dict in the signature has the explicit base key; we don't mix base with GE.
    Replace all dicts in a signature iff at least one base collapses; otherwise leave signature untouched.
    """
    # Group dict indices by their "signature without family" per base,
    # but we also need a pure signature grouping to merge multiple bases at once.
    # Build a canonical "pure signature" (i.e., remove ALL GE keys and ALL base keys).
    def pure_signature(d: Dict[str, bool]) -> Tuple[Tuple[str, bool], ...]:
        items = [(k, v) for k, v in d.items() if "_GE" not in k and not isinstance(v, dict) and isinstance(v, bool)]
        # keep ONLY non-base boolean keys in the signature (i.e., A>B True/False etc.)
        # GE keys are excluded; base keys remain here because they are part of "other" logic.
        # However, to avoid mixing with bases we’ll avoid collapsing any base that appears explicitly below.
        items.sort()
        return tuple(items)

    # Build per-signature collections
    sig_to_indices = defaultdict(list)
    for i, d in enumerate(dicts):
        sig_to_indices[pure_signature(d)].append(i)

    to_remove = set()
    replacements = []

    for sig, idxs in sig_to_indices.items():
        # Collect all bases & their intervals within this signature group
        bases = set()
        base_explicit_present = defaultdict(bool)
        base_intervals = defaultdict(list)  # base -> list of (lo, hi)

        for i in idxs:
            d = dicts[i]
            # GE families present in this dict
            ge_bases = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
            # explicit base presence
            for k in d:
                if "_GE" not in k and isinstance(d[k], bool):
                    base_explicit_present[k] |= True
            for base in ge_bases:
                bases.add(base)
                lo, hi = _interval_for_family(d, base)
                if lo < hi:
                    base_intervals[base].append((lo, hi))

        # Try to collapse each base independently
        any_collapsed = False
        collapsed_parts: Dict[str, Dict[str, bool]] = {}  # base -> {collapsed keys...}

        for base in bases:
            # guard: don't mix with explicit base key in this signature
            if base_explicit_present.get(base, False):
                continue

            intervals = base_intervals.get(base, [])
            if not intervals:
                continue

            # Merge intervals
            intervals.sort()
            merged = []
            cur_lo, cur_hi = intervals[0]
            for lo, hi in intervals[1:]:
                if lo <= cur_hi:
                    cur_hi = max(cur_hi, hi)
                else:
                    merged.append((cur_lo, cur_hi))
                    cur_lo, cur_hi = lo, hi
            merged.append((cur_lo, cur_hi))

            # Decide collapse
            part: Dict[str, bool] = {}
            if len(merged) == 1:
                L, R = merged[0]
                if R == math.inf and L <= win_threshold:
                    part[base] = True
                elif R != math.inf and L != -math.inf:
                    part[f"{base}_GE{int(L)}"] = True
                    part[f"{base}_GE{int(R)}"] = False
                elif R == math.inf and aggressive_upper:
                    # e.g., [L, +inf) with L > win_threshold -> keep as GE_L True
                    part[f"{base}_GE{int(L)}"] = True
            else:
                # multiple pieces
                if aggressive_upper and any(r == math.inf for _, r in merged):
                    # find minimal finite L among all pieces
                    Lmin = min(L for (L, _) in merged if L != -math.inf)
                    part[f"{base}_GE{int(Lmin)}"] = True
                else:
                    # can't nicely collapse this base in this signature
                    part = {}

            if part:
                collapsed_parts[base] = part
                any_collapsed = True

        if not any_collapsed:
            continue  # leave this signature group as-is

        # Build one collapsed dict for the signature:
        collapsed = dict(sig)  # start from the shared non-GE keys (sig already only has non-GE keys)
        for base in sorted(collapsed_parts.keys()):
            collapsed.update(collapsed_parts[base])

        # Remove all dicts in this signature group and add the collapsed one
        to_remove.update(idxs)
        replacements.append(collapsed)

    # output
    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    # de-dupe
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

# ---------- one-shot orchestrator ----------
def consolidate_all(dicts: List[Dict[str, bool]]) -> List[Dict[str, bool]]:
    step05  = remove_base_if_ge_present_in_dicts(dicts)
    step0  = consolidate_opposites_and_remove_bases(step05)
    step1  = consolidate_opposites(step0)
    step2  = merge_ge_intervals_to_base_safe(step1, win_threshold=1)  # collapses to base True when union [1,+inf)
    step3  = remove_base_if_ge_present(step2)                         # strip base if any GE of same base exists
    step3u = merge_ge_union_by_signature(step3)                            # <-- unified finite/unbounded GE merge
    step4  = merge_full_partition_remove_base(step3u, win_threshold=1)

    # final de-dupe
    seen, out = set(), []
    for d in step4:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

# ---------- Boolean minimization helpers (for readable scenarios) ----------
def minimize_minterms(minterms, allow_combine=True):
    """
    Simplify minterms by absorption (always) and optionally by one-variable combination.
    With allow_combine=True, we combine only when the differing variable's matchup
    is ALSO represented by another variable in BOTH terms (so we don't erase that matchup).
    """
    terms = {frozenset(m.items()) for m in minterms}

    def _matchup_of(var: str) -> str:
        # Normalize “A>B_GE8” and “A>B” to a canonical matchup key "A>B" (lexicographic).
        if "_GE" in var:
            base, _ = var.split("_GE", 1)
        else:
            base = var
        a, b = base.split(">", 1)
        aa, bb = (a, b) if a <= b else (b, a)
        return f"{aa}>{bb}"

    changed = True
    while changed:
        before = len(terms)

        # --- Absorption: remove supersets
        to_remove = set()
        lst = list(terms)
        for i, a in enumerate(lst):
            for j, b in enumerate(lst):
                if i != j and a.issuperset(b):
                    to_remove.add(a)
        if to_remove:
            terms -= to_remove

        if allow_combine:
            # --- Combine: merge pairs that differ by exactly one variable,
            # but only if each term also has another var for that same matchup.
            lst = list(terms)
            n = len(lst)
            merged = set()
            used = [False] * n

            # Per-term matchup counts
            from collections import Counter
            term_matchup_counts = [
                Counter(_matchup_of(k) for k in dict(t).keys())
                for t in lst
            ]

            for i in range(n):
                for j in range(i + 1, n):
                    a = lst[i]; b = lst[j]
                    da = dict(a); db = dict(b)
                    keys = set(da.keys()) | set(db.keys())
                    diffs = [k for k in keys if da.get(k) != db.get(k)]
                    if len(diffs) == 1:
                        k = diffs[0]
                        mk = _matchup_of(k)

                        # Require another variable from the same matchup in BOTH terms
                        if term_matchup_counts[i][mk] >= 2 and term_matchup_counts[j][mk] >= 2:
                            new = dict(da)
                            new.pop(k, None)
                            merged.add(frozenset(new.items()))
                            used[i] = used[j] = True

            out = set()
            for idx, t in enumerate(lst):
                if not used[idx]:
                    out.add(t)
            out |= merged
            terms = out

        changed = (len(terms) != before)

    return [dict(t) for t in terms]


# -------------------------
# Prefect tasks & flow
# -------------------------


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Teams for {region}-{clazz}A")
def fetch_region_teams(clazz: int, region: int, season: int) -> List[str]:
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
                (clazz, region, season),
            )
            return [r[0] for r in cur.fetchall()]


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Completed Region Games for {teams}")
def fetch_completed_pairs(teams: List[str], season: int) -> List[CompletedGame]:
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, opponent, date, result, points_for, points_against "
                "FROM games "
                "WHERE season=%s AND final=TRUE AND region_game=TRUE "
                "  AND school = ANY(%s) AND opponent = ANY(%s)",
                (season, teams, teams),
            )
            rows = cur.fetchall()

    # Deduplicate by *game* key (a,b,date) where a<b (lexicographic).
    # Prefer the row where school==a (lex-first) if it exists; otherwise use the b-row inverted.
    by_game: Dict[Tuple[str, str, str], Dict[str, int] | Tuple[str, ...]] = {}

    for school, opp, date, result, pf, pa in rows:
        a, b, _sign = normalize_pair(school, opp)  # a<b
        gkey = (a, b, date)

        # Compute contributions from the perspective of team 'a' (lex-first)
        if school == a:
            # from a's row directly
            res_a = 1 if result == 'W' else (-1 if result == 'L' else 0)
            pd_a  = (pf - pa) if (pf is not None and pa is not None) else 0
            pa_a  = (pa or 0)
            pa_b  = (pf or 0)

            # Always prefer the a-row: overwrite any prior b-row for this (a,b,date)
            by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 1}

        else:
            # row is from b's perspective; invert to 'a'
            res_a = -1 if result == 'W' else (1 if result == 'L' else 0)
            pd_a  = (-(pf - pa)) if (pf is not None and pa is not None) else 0
            pa_a  = (pf or 0)  # a allowed b's points_for
            pa_b  = (pa or 0)  # b allowed a's points_for

            prev = by_game.get(gkey)
            # Only store if we don't already have an a-row for this game
            if not prev or (isinstance(prev, dict) and not prev.get("has_a")):
                by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 0}

    # Now aggregate per pair (a,b) across dates (in case there were multiple meetings)
    pair_totals: Dict[Tuple[str, str], Dict[str, int]] = {}
    for (a, b, _date), vals in by_game.items():
        d = pair_totals.setdefault((a, b), {"res_a": 0, "pd_a": 0, "pa_a": 0, "pa_b": 0})
        d["res_a"] += vals["res_a"] # type: ignore
        d["pd_a"]  += vals["pd_a"] # type: ignore
        d["pa_a"]  += vals["pa_a"] # type: ignore
        d["pa_b"]  += vals["pa_b"] # type: ignore

    out: List[CompletedGame] = []
    for (a, b), v in pair_totals.items():
        # Collapse res_a to {-1, 0, +1} for the season series (win/loss/split from 'a' pov)
        res_a_sign = 1 if v["res_a"] > 0 else (-1 if v["res_a"] < 0 else 0)
        out.append(CompletedGame(a, b, res_a_sign, v["pd_a"], v["pa_a"], v["pa_b"]))

    return out


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Remaining Region Games for {teams}")
def fetch_remaining_pairs(teams: List[str], season: int) -> List[RemainingGame]:
    with get_database_connection() as conn:
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


@task(retries=2, retry_delay_seconds=10, task_run_name="Fetch {season} Region Standings for {region}-{clazz}A")
def fetch_region_standings(clazz: int, region: int, season: int) -> List[str]:
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT school, class, region, season, wins, losses, ties, region_wins, region_losses, region_ties FROM get_standings_for_region(%s, %s)",
                (clazz, region),
            )
            return [r for r in cur.fetchall()]


@task(task_run_name="Write {season} Region Standings for {region}-{clazz}A")
def write_region_standings(results, clazz, region, season):

    # --- do the updates ---
    sql = """
        INSERT INTO region_standings (school, season, class, region)
                VALUES %s
                ON CONFLICT (school, season) DO UPDATE SET
                    class  = COALESCE(EXCLUDED.class,  region_standings.class),
                    region = COALESCE(EXCLUDED.region, region_standings.region),
                    wins   = EXCLUDED.wins,
                    losses = EXCLUDED.losses,
                    ties   = EXCLUDED.ties,
                    region_wins   = EXCLUDED.region_wins,
                    region_losses = EXCLUDED.region_losses,
                    region_ties   = EXCLUDED.region_ties,
                    odds_1st      = EXCLUDED.odds_1st,
                    odds_2nd      = EXCLUDED.odds_2nd,
                    odds_3rd      = EXCLUDED.odds_3rd,
                    odds_4th      = EXCLUDED.odds_4th,
                    scenarios_1st = EXCLUDED.scenarios_1st,
                    scenarios_2nd = EXCLUDED.scenarios_2nd,
                    scenarios_3rd = EXCLUDED.scenarios_3rd,
                    scenarios_4th = EXCLUDED.scenarios_4th,
                    odds_playoffs = EXCLUDED.odds_playoffs,
                    clinched      = EXCLUDED.clinched,
                    eliminated    = EXCLUDED.eliminated,
                    coin_flip_needed = EXCLUDED.coin_flip_needed
        ;
    """

# ---------- Main enumeration + outputs ----------
@task(retries=2, retry_delay_seconds=10, task_run_name="Get {season} Region Finish Scenarios for {region}-{clazz}A")
def get_region_finish_scenarios(clazz, region, season, debug=False):
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

    logger = get_run_logger()

    # ----- Fetch inputs -----
    teams = fetch_region_teams(clazz, region, season)
    if not teams:
        raise SystemExit("No teams found.")
    completed = fetch_completed_pairs(teams, season)   # fixed results already known
    remaining = fetch_remaining_pairs(teams, season)  # undecided region games
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

                        # --- inside get_region_finish_scenarios(), where you currently compute `found` ---
                        # Scan margins 1..12 for the same-direction winner and collect *all* change points
                        orders_by_m = []
                        for m in range(1, 13):
                            test_margins = dict(base_margins)
                            test_margins[(a, b)] = m
                            test_order = resolve_standings_for_mask(
                                teams, completed, remaining, mask_for_dir,
                                margins=test_margins, base_margin_default=7, pa_win=pa_for_winner,
                            )
                            # store a tuple for stable comparison
                            orders_by_m.append(tuple(test_order))

                        change_points = []
                        for m in range(2, 13):
                            if orders_by_m[m-1] != orders_by_m[m-2]:
                                # boundary between (m-1) and m
                                change_points.append(m)

                        # Save *all* thresholds (may be empty)
                        thresholds_dir[((a, b), winner)] = change_points

                        # Helpful debug
                        logger.debug(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: thresholds={change_points}")

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
                # --- Build interval sets per active pair (for the mask's actual winner) ---
                # thresholds like [5, 8] => intervals [1,5), [5,8), [8,13)
                interval_specs = []  # list of [ ((a,b), winner, [(lo,hi), ...]) ]
                for rem_game in intra_bucket_games:
                    a, b = rem_game.a, rem_game.b
                    idx = rem_idx[(a, b)]
                    mask_winner = a if ((outcome_mask >> idx) & 1) == 1 else b
                    tlist = thresholds_dir.get(((a, b), mask_winner))
                    if tlist:
                        bounds = [1] + sorted(tlist) + [13]
                        intervals = [(bounds[i], bounds[i+1]) for i in range(len(bounds)-1)]
                        interval_specs.append(((a, b), mask_winner, intervals))

                if not interval_specs:
                    # No intervals to branch on: resolve once with base_margins
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
                    # Cartesian product across all intervals from all active pairs
                    from itertools import product
                    for interval_combo in product(*[spec[2] for spec in interval_specs]):
                        branch_margins = dict(base_margins)
                        branch_assignment = dict(var_assignment)
                        branch_weight = 1.0

                        for ((a, b), winner, intervals_for_pair), (lo, hi) in zip(interval_specs, interval_combo):
                            # Choose a representative margin in [lo,hi): we’ll use 'lo' deterministically
                            chosen_m = lo
                            branch_margins[(a, b)] = chosen_m

                            # Encode the interval for phrasing:
                            #   GE lo  -> True
                            #   GE hi  -> False (meaning < hi)  (only if hi <= 12)
                            opp = b if winner == a else a
                            ge_lo_key = f"{winner}>{opp}_GE{lo}"
                            branch_assignment[ge_lo_key] = True
                            if hi <= 12:
                                ge_hi_key = f"{winner}>{opp}_GE{hi}"
                                branch_assignment[ge_hi_key] = False

                            # Probability = length of interval / 12
                            branch_weight *= (hi - lo) / 12.0

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

    def simplify_matchups(dicts):
        simplified = []
        for d in dicts:
            keys = set(d.keys())

            # Build a set of all matchups that have any _GEz variant
            has_margin_variant = set()
            for k in keys:
                if "_GE" in k:
                    base = k.split("_GE", 1)[0]
                    has_margin_variant.add(base)
                    # Also add flipped direction (y>x) so both sides are covered
                    a, b = base.split(">", 1)
                    has_margin_variant.add(f"{b}>{a}")

            # Keep only keys that aren't a base matchup overshadowed by a _GEz one
            new_d = {
                k: v for k, v in d.items()
                if not (("_GE" not in k) and (k in has_margin_variant))
            }
            simplified.append(new_d)

        return simplified


    minimized = defaultdict(dict)
    for team, seed_map in scenario_minterms.items():
        for seed_num, minterms in seed_map.items():
            mins = [dict(m) for m in minterms]
            consolidated_scenarios = consolidate_all(mins)
            simplified_scenarios = simplify_matchups(consolidated_scenarios)
            minimized_mins = minimize_minterms(simplified_scenarios, allow_combine=True)  # simplify
            sorted_mins = [
                {k: d[k] for k in sorted(d)}
                for d in sorted(minimized_mins, key=lambda x: len(x))
            ]
            minimized[seed_num][team] = sorted_mins

    region_standings = fetch_region_standings(clazz, region, season)

    logger.info("Writing region standings for season %d, class %d, region %d", season, clazz, region)
    logger.info("Region standings: %s", region_standings)
    logger.info("Results: %s", results)
    logger.info("Minimized scenarios: %s", minimized)

    #write_region_standings(results, clazz, region, season)

    return minimized


@flow(name="Region Scenarios Data Flow")
def region_scenarios_data_flow(season: int = 2025, clazz: int | None = None, region: int | None = None) -> dict[str, object]:
    """
    Region Scenarios Data Flow
    """
    logger = get_run_logger()
    logger.info("Running region scenarios data flow for season %d, class %d, region %d", season, clazz, region)
    scenario_dicts = {}
    if clazz is None or region is None:
        for clazz in [1, 2, 3, 4]:
            scenario_dicts[clazz] = {}
            for region in [1, 2, 3, 4, 5, 6, 7, 8]:
                scenario_dicts[clazz][region] = get_region_finish_scenarios(clazz, region, season)
        for clazz in [5, 6, 7]:
            scenario_dicts[clazz] = {}
            for region in [1, 2, 3, 4]:
                scenario_dicts[clazz][region] = get_region_finish_scenarios(clazz, region, season)
    elif clazz is not None and region is not None:
        scenario_dicts[clazz][region] = get_region_finish_scenarios(clazz, region, season)
    # logger.info("Finished region scenarios data flow for season %d, class %d, region %d: %s", season, clazz, region, scenario_dicts)
    return scenario_dicts