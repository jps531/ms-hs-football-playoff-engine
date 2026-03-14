#!/usr/bin/env python3
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

import argparse
import math
import os
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from itertools import product
from typing import Any

# Ensure the project root is on the path when running from scripts/ directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg
except Exception:
    psycopg = None

from prefect_files.data_classes import CompletedGame, RemainingGame
from prefect_files.data_helpers import get_completed_games, normalize_pair
from prefect_files.scenarios import (
    consolidate_all,
    minimize_minterms,
    pct_str,
)
from prefect_files.tiebreakers import (
    rank_to_slots,
    resolve_standings_for_mask,
    standings_from_mask,
    tie_bucket_groups,
    unique_intra_bucket_games,
)

# --------------------------- Fetch Helpers ---------------------------


def fetch_division(conn, clazz: int, region: int, season: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
            (clazz, region, season),
        )
        return [r[0] for r in cur.fetchall()]


def fetch_completed_pairs(conn, teams: list[str], season: int) -> list[CompletedGame]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school, opponent, date, result, points_for, points_against "
            "FROM games "
            "WHERE season=%s AND final=TRUE AND region_game=TRUE "
            "  AND school = ANY(%s) AND opponent = ANY(%s)",
            (season, teams, teams),
        )
        rows = cur.fetchall()

    raw_results = [
        {
            "school": school,
            "opponent": opp,
            "date": str(date),
            "result": result,
            "points_for": pf,
            "points_against": pa,
        }
        for school, opp, date, result, pf, pa in rows
    ]
    return get_completed_games(raw_results)


def fetch_remaining_pairs(conn, teams: list[str], season: int) -> list[RemainingGame]:
    with conn.cursor() as cur:
        cur.execute(
            "WITH cand AS ("
            "  SELECT LEAST(school,opponent) a, GREATEST(school,opponent) b FROM games "
            "  WHERE season=%s AND final=FALSE AND region_game=TRUE "
            "    AND school = ANY(%s) AND opponent = ANY(%s)"
            ") SELECT DISTINCT a,b FROM cand",
            (season, teams, teams),
        )
        return [RemainingGame(a, b) for a, b in cur.fetchall()]


# ---------- basic helpers ----------
def _is_ge_key(k: str) -> bool:
    return "_GE" in k and ">" in k


def _parse_ge(k: str) -> tuple[str, int]:
    base, _, thr = k.partition("_GE")
    return base, int(thr)


def _flip(base: str) -> str:
    a, b = base.split(">", 1)
    return f"{b}>{a}"


def _canon_pair(base: str) -> tuple[str, str]:
    a, b = base.split(">", 1)
    return a, b


def _non_ge_signature(m: dict[str, bool]) -> tuple[tuple[str, bool], ...]:
    items = [(k, v) for k, v in m.items() if ">" in k and not _is_ge_key(k)]
    items.sort()
    return tuple(items)


def _interval_for_base(m: dict[str, bool], base: str) -> tuple[float, float, str]:
    """
    Return (lo, hi, winner) for this matchup in this minterm:
      winner is the orientation 'A>B' or 'B>A' (who wins).
      If base True or GE for base present => winner is base (A>B).
      If opposite base False present => winner is B>A.
    """
    lo = -math.inf
    hi = math.inf
    a, b = _canon_pair(base)
    winner = None

    # base outcome decides winner if present
    if base in m:
        winner = base if m[base] else _flip(base)
    elif _flip(base) in m:
        winner = _flip(base) if m[_flip(base)] else base

    # GE thresholds specify margins for 'base' orientation only
    has_ge = False
    for k, v in m.items():
        if _is_ge_key(k):
            bname, t = _parse_ge(k)
            if bname == base:
                has_ge = True
                if v:
                    lo = max(lo, t)
                else:
                    hi = min(hi, t)

    if has_ge and winner is None:
        winner = base  # GE implies base orientation wins

    # If winner is the flipped orientation, GE margins don't apply (we print just the loss)
    if winner == _flip(base):
        return (1, 1, winner)

    # Normalize band
    if has_ge:
        if lo >= hi:  # empty
            return (1, 1, winner or base)
        return (max(1, lo), hi, winner or base)

    # No GE; if base True => [1, +inf); if unknown, treat as none
    if winner == base:
        return (1, math.inf, base)
    return (1, 1, winner or base)


def _remove_base_if_ge_present_in_atom(atom: dict[str, bool]) -> dict[str, bool]:
    ge_bases = {k.split("_GE", 1)[0] for k in atom if "_GE" in k}
    if not ge_bases:
        return atom
    to_drop = set()
    for base in ge_bases:
        to_drop.add(base)
        to_drop.add(_flip(base))
    return {k: v for k, v in atom.items() if k not in to_drop}


# ---------- GLOBAL partitions for airtightness ----------
def _collect_global_cuts(all_minterms: Iterable[dict[str, bool]]) -> dict[str, list[int]]:
    """
    For each base, collect all cut thresholds (from any minterm, across the whole input).
    """
    cuts: dict[str, set] = defaultdict(set)
    for m in all_minterms:
        for k, v in m.items():
            if _is_ge_key(k):
                base, t = _parse_ge(k)
                cuts[base].add(int(t))
            elif ">" in k and v is True:
                # base True implies [1, +inf), ensure we include 1 as a starting cut
                cuts[k].add(1)
    # Always include 1 if there is any information for that base
    out = {}
    for base, s in cuts.items():
        s.add(1)
        out[base] = sorted(s)
    return out


def _global_partitions_for_base(
    base: str, global_cuts: dict[str, list[int]], bands_from_input: list[tuple[float, float]]
) -> list[tuple[int, int]]:
    """
    Build airtight partitions for `base` using GLOBAL cuts. Keep only pieces covered by input bands.
    """
    if base not in global_cuts:
        # No cuts observed anywhere: no partitioning
        return []
    cuts = list(global_cuts[base])
    cuts.sort()
    parts: list[tuple[int, int]] = []

    # detect if any input band has +inf tail
    has_tail = any(hi == math.inf for (lo, hi) in bands_from_input)

    for a, b in zip(cuts, cuts[1:] + [None]):
        if b is None:
            if has_tail:
                parts.append((a, math.inf))
            break
        # keep this piece if covered by any band from input
        covered = any((lo <= a) and (b <= hi) for (lo, hi) in bands_from_input)
        if covered:
            parts.append((a, b))
    return parts


# ---------- Expand scenarios by signature using GLOBAL cuts ----------
def _expand_signature_atoms_global(
    signature_group: list[dict[str, bool]], global_cuts: dict[str, list[int]]
) -> list[dict[str, bool]]:
    if not signature_group:
        return []
    fixed = dict(_non_ge_signature(signature_group[0]))

    # Determine all bases talked about in this signature
    bases = set()
    for m in signature_group:
        for k in m:
            if _is_ge_key(k):
                base, _ = _parse_ge(k)
                bases.add(base)
            elif ">" in k:
                bases.add(k)

    # Build input bands per base (who wins in this signature matters)
    partitions: dict[str, list[tuple[int, int]]] = {}
    for base in sorted(bases):
        # Only consider bands for the winner side in this signature
        bands: list[tuple[float, float]] = []
        for m in signature_group:
            lo, hi, winner = _interval_for_base(m, base)
            if winner == base and lo < hi:
                bands.append((lo, hi))
        if not bands:
            # no wins for this orientation in this signature; skip
            continue
        parts = _global_partitions_for_base(base, global_cuts, bands)
        if parts:
            partitions[base] = parts

    if not partitions:
        # No GE bands for winner sides; just return fixed base outcomes
        return [fixed.copy()]

    # Cartesian product of all base partitions
    base_names = sorted(partitions.keys())
    all_parts = [partitions[b] for b in base_names]

    atoms: list[dict[str, bool]] = []
    for combo in product(*all_parts):
        m = dict(fixed)
        for bname, (L, U) in zip(base_names, combo):
            if U == math.inf and L <= 1:
                m[bname] = True
            else:
                if L > 1:
                    m[f"{bname}_GE{L}"] = True
                if U != math.inf:
                    m[f"{bname}_GE{U}"] = False
        atoms.append(_remove_base_if_ge_present_in_atom(m))
    return atoms


# ---------- Rendering in chosen game order ----------
def _render_clause_lines_ordered(atom: dict[str, bool], games_order: list[str]) -> list[str]:
    lines: list[str] = []
    for base in games_order:
        a, b = _canon_pair(base)
        lo, hi, winner = _interval_for_base(atom, base)
        if winner == _flip(base):
            # b beats a
            lines.append(f"{b} Win over {a}")
        elif winner == base:
            lo = max(1, lo)
            if hi == math.inf:
                if lo <= 1:
                    lines.append(f"{a} Win over {b}")
                else:
                    lines.append(f"{a} Win over {b} by ≥ {lo} points")
            else:
                if lo <= 1:
                    lines.append(f"{a} Win over {b} by < {hi} points")
                else:
                    lines.append(f"{a} Win over {b} by ≥ {lo} and < {hi} points")
        else:
            # no info for this game in this atom (shouldn't happen if inputs are complete)
            continue
    return lines


# ---------- Scenario sort key for logical progression ----------
def _band_sort_key(base: str, atom: dict[str, bool], loser_first: bool = True) -> tuple[int, int, int]:
    """
    For one game, return a tuple to sort scenarios:
      winner_group: 0 for (loser-first) winner (B>A), 1 for (A>B)
      granularity:  0 for 'any', 1 for bounded [1,k), 2+ for higher lower-bounds in ascending L
      hi_rank:      secondary by hi (inf last)
    """
    a, b = _canon_pair(base)
    lo, hi, winner = _interval_for_base(atom, base)

    # winner group
    if loser_first:
        wg = 0 if winner == _flip(base) else 1
    else:
        wg = 0 if winner == base else 1

    # margin granularity rank within the winner group
    if winner == _flip(base):
        # losses: treat as 'any' (no margin)
        return (wg, 0, 0)

    # winner == base
    if hi == math.inf and lo <= 1:
        gran = 0  # any margin
        hir = 10**9
    elif lo <= 1 and hi != math.inf:
        gran = 1  # < k
        hir = hi
    else:
        gran = 2 + int(lo)  # ≥ L (and possibly < hi), higher L later
        hir = hi if hi != math.inf else 10**9
    return (wg, gran, hir)


def _scenario_sort_key(atom: dict[str, bool], games_order: list[str]) -> tuple:
    # Lexicographic by games in order, using the per-game band keys
    key = []
    for base in games_order:
        key.extend(_band_sort_key(base, atom, loser_first=True))
    return tuple(key)


def _bands_for_atom(atom: dict[str, bool], games_order: list[str]) -> dict[str, tuple[int, int, str]]:
    """
    For each base in games_order, return (L, U, winner) where:
      - winner is 'A>B' or 'B>A'
      - L, U are integers; U can be math.inf
    """
    out: dict[str, tuple[int, int, str]] = {}
    for base in games_order:
        lo, hi, winner = _interval_for_base(atom, base)
        # normalize
        L = max(1, int(lo)) if lo != -math.inf else 1
        U = hi
        out[base] = (L, U, winner)
    return out


def _bands_to_atom(bands: dict[str, tuple[int, int, str]]) -> dict[str, bool]:
    """
    Rebuild an atom dict from (L,U,winner) per base.
    """
    atom: dict[str, bool] = {}
    for base, (L, U, winner) in bands.items():
        if winner == base:  # A>B
            if U == math.inf and L <= 1:
                atom[base] = True
            else:
                if L > 1:
                    atom[f"{base}_GE{L}"] = True
                if U != math.inf:
                    atom[f"{base}_GE{int(U)}"] = False
        else:  # B>A (flip)
            atom[_flip(base)] = True  # record as base in flipped orientation
    return _remove_base_if_ge_present_in_atom(atom)


def _touching(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Return True if two half-open bands [La,Ua) and [Lb,Ub) touch or overlap."""
    La, Ua = a
    Lb, Ub = b
    # treat math.inf as a very large number for comparison
    Aend = Ua
    Bend = Ub
    if Aend == math.inf and Lb == math.inf:  # degenerate, won’t happen
        return False
    # overlap or just touching at boundary
    return (La <= Lb <= (Aend if Aend != math.inf else 10**12)) or (Lb <= La <= (Bend if Bend != math.inf else 10**12))


def _seed_signature(seeds: dict[int, str]) -> tuple[tuple[int, str], ...]:
    """Stable comparable form of a seed map."""
    return tuple(sorted(seeds.items()))


def _fmt_band(L: int, U: int) -> str:
    if U == math.inf and L <= 1:
        return "any"
    if U == math.inf:
        return f"[{L}, +∞)"
    if L <= 1:
        return f"[1, {U})"
    return f"[{L}, {U})"


def _fmt_bands(bands: dict[str, tuple[int, int, str]], games_order: list[str]) -> str:
    parts = []
    for base in games_order:
        if base not in bands:
            continue
        L, U, W = bands[base]
        parts.append(f"{W}: {_fmt_band(L, U)}")
    return " | ".join(parts)


def _try_merge_neighbor(
    a_bands: dict[str, tuple[int, int, str]],
    b_bands: dict[str, tuple[int, int, str]],
    same_seeds: bool,
    games_order: list[str],
) -> tuple[bool, dict[str, tuple[int, int, str]]]:
    """
    Attempt to merge two neighboring scenarios.
    Conditions:
      * seed outcomes identical
      * for every game: same winner
      * bands equal for all but ONE game; that one game's bands must touch
    Returns (merged?, merged_bands_or_a_bands)
    """
    if not same_seeds:
        return False, a_bands

    diffs = []
    for base in games_order:
        La, Ua, Wa = a_bands[base]
        Lb, Ub, Wb = b_bands[base]
        if Wa != Wb:
            return False, a_bands
        if (La, Ua) != (Lb, Ub):
            diffs.append(base)
            if len(diffs) > 1:
                return False, a_bands

    if not diffs:
        # identical scenarios — merge trivially
        return True, a_bands

    # exactly one differing base
    base = diffs[0]
    La, Ua, W = a_bands[base]
    Lb, Ub, _ = b_bands[base]
    if not _touching((La, Ua), (Lb, Ub)):
        return False, a_bands

    # make a single covering band [minL, maxU)
    L = min(La, Lb)
    U = Ua if Ua == math.inf or (Ub != math.inf and Ua >= Ub) else Ub
    if Ua == math.inf or Ub == math.inf:
        U = math.inf
    merged = dict(a_bands)
    merged[base] = (L, U, W)
    return True, merged


def _consolidate_neighboring_atoms(
    atoms_sorted: list[dict[str, bool]],
    games_order: list[str],
    seed_lookup_fn: Callable[[dict[str, bool]], dict[int, str]],
    *,
    debug: bool = False,
    debug_fn: Callable[[str, dict[str, Any]], None] = None,
) -> list[tuple[dict[str, bool], dict[int, str]]]:
    """
    Merge neighboring scenarios that:
      - have identical seed outcomes, and
      - differ on exactly one game's band, and
      - those two bands touch/overlap.
    Carry FORWARD the left-hand run's seeds (no recompute).
    Emits debug events if debug=True.

    debug_fn(event, payload) will be called with events:
      - 'compare': before attempting a merge of neighbors
      - 'merge_ok': when a merge succeeds
      - 'merge_stop': when a merge chain stops (reason included)
      - 'emit': when a merged block is emitted
    """

    def emit(ev: str, payload: dict[str, Any]):
        if debug and debug_fn:
            debug_fn(ev, payload)

    merged: list[tuple[dict[str, bool], dict[int, str]]] = []
    i = 0
    while i < len(atoms_sorted):
        a = atoms_sorted[i]
        a_bands = _bands_for_atom(a, games_order)
        a_seeds = seed_lookup_fn(a)  # cached/carry-forward seeds
        a_sig = _seed_signature(a_seeds)

        j = i + 1
        cur_bands = a_bands

        while j < len(atoms_sorted):
            b = atoms_sorted[j]
            b_bands = _bands_for_atom(b, games_order)
            b_seeds = seed_lookup_fn(b)
            b_sig = _seed_signature(b_seeds)

            emit(
                "compare",
                {
                    "left_index": i,
                    "right_index": j,
                    "left_bands": _fmt_bands(cur_bands, games_order),
                    "right_bands": _fmt_bands(b_bands, games_order),
                    "left_seeds": a_seeds,
                    "right_seeds": b_seeds,
                    "left_seed_sig": a_sig,
                    "right_seed_sig": b_sig,
                },
            )

            same_seeds = a_sig == b_sig
            ok, merged_bands = _try_merge_neighbor(cur_bands, b_bands, same_seeds, games_order)
            if not ok:
                emit(
                    "merge_stop",
                    {
                        "left_index": i,
                        "stop_at_index": j,
                        "reason": "seed_mismatch" if not same_seeds else "bands_not_touching_or_multi_diff",
                        "left_bands": _fmt_bands(cur_bands, games_order),
                        "stop_bands": _fmt_bands(b_bands, games_order),
                        "left_seeds": a_seeds,
                        "stop_seeds": b_seeds,
                    },
                )
                break

            emit(
                "merge_ok",
                {
                    "left_index": i,
                    "merged_through_index": j,
                    "prev_bands": _fmt_bands(cur_bands, games_order),
                    "with_bands": _fmt_bands(b_bands, games_order),
                    "new_bands": _fmt_bands(merged_bands, games_order),
                    "seeds_carried": a_seeds,  # carried, not recomputed
                },
            )
            cur_bands = merged_bands
            j += 1

        merged_atom = _bands_to_atom(cur_bands)
        merged.append((merged_atom, a_seeds))
        emit(
            "emit",
            {
                "run_start": i,
                "run_end_exclusive": j,
                "final_bands": _fmt_bands(cur_bands, games_order),
                "seeds": a_seeds,
            },
        )
        i = j
    return merged


# ---------- Main API ----------
def scenarios_text_from_team_seed_ordered(
    team_seed_map: dict[str, dict[int, Any]],
    games_order: list[str],  # e.g. ["Brandon>Meridian","Northwest Rankin>Petal","Pearl>Oak Grove"]
    start_letter: str = "A",
    seed_order: list[int] | None = [1, 2, 3, 4],
) -> str:
    # Ingest all minterms, build global cuts
    raw_minterms: list[dict[str, bool]] = []
    for team, seed_map in team_seed_map.items():
        for seed, scen_dist in seed_map.items():
            if scen_dist is None:
                continue
            if isinstance(scen_dist, dict):
                for k in scen_dist.keys():
                    if isinstance(k, dict):
                        raw_minterms.append(k)
            elif isinstance(scen_dist, (list, tuple, set)):
                raw_minterms.extend(list(scen_dist))

    global_cuts = _collect_global_cuts(raw_minterms)

    # Group inputs by non-GE signature and expand with GLOBAL partitions
    sig_to_minterms = defaultdict(list)
    for m in raw_minterms:
        sig_to_minterms[_non_ge_signature(m)].append(m)

    atoms: list[dict[str, bool]] = []
    for _, group in sig_to_minterms.items():
        atoms.extend(_expand_signature_atoms_global(group, global_cuts))

    # Build reverse index for seed lookup
    entries: list[tuple[str, int, dict[str, bool]]] = []
    for team, seed_map in team_seed_map.items():
        for seed, scen_dist in seed_map.items():
            if scen_dist is None:
                continue
            if isinstance(scen_dist, dict):
                for k in scen_dist.keys():
                    if isinstance(k, dict):
                        entries.append((team, seed, k))
            elif isinstance(scen_dist, (list, tuple, set)):
                for k in scen_dist:
                    entries.append((team, seed, k))

    def _atom_satisfies(atom: dict[str, bool], broad: dict[str, bool]) -> bool:
        # Clean both sides of redundant base when GE present
        a_clean = _remove_base_if_ge_present_in_atom(dict(atom))
        b_clean = _remove_base_if_ge_present_in_atom(dict(broad))

        # GE keys must match exactly if present in broad
        for k, v in b_clean.items():
            if _is_ge_key(k):
                if a_clean.get(k) is not v:
                    return False
        # Base keys in broad: check via winner from atom
        for k, v in b_clean.items():
            if ">" in k and not _is_ge_key(k):
                lo, hi, winner = _interval_for_base(a_clean, k)
                if v is True and winner != k:
                    return False
                if v is False and winner != _flip(k):
                    return False
        return True

    # Sort scenarios in the requested progression
    atoms.sort(key=lambda m: _scenario_sort_key(m, games_order))

    def atom_seed_lines(atom: dict[str, bool]) -> dict[int, str]:
        res: dict[int, str] = {}
        cand = defaultdict(list)
        for team, seed, broad in entries:
            if _atom_satisfies(atom, broad):
                cand[seed].append((len(broad), team))
        for s, lst in cand.items():
            lst.sort(key=lambda x: (-x[0], x[1]))
            res[s] = lst[0][1]
        return res

    # --- DEBUG HOOK EXAMPLE ---
    def dbg(ev: str, d: dict[str, Any]):
        # Minimal, readable debug. Customize to taste.
        if ev == "compare":
            print(
                f"[COMPARE] L{d['left_index']} vs R{d['right_index']} | seeds equal? {d['left_seed_sig'] == d['right_seed_sig']}"
            )
            print(f"          L bands: {d['left_bands']}")
            print(f"          R bands: {d['right_bands']}")
        elif ev == "merge_ok":
            print(f"[MERGE-OK] run@{d['left_index']} absorbed up to {d['merged_through_index']}")
            print(f"          prev: {d['prev_bands']}")
            print(f"          with: {d['with_bands']}")
            print(f"          ->   {d['new_bands']}")
            print(f"          seeds carried: {d['seeds_carried']}")
        elif ev == "merge_stop":
            print(f"[MERGE-STOP] reason={d['reason']} at neighbor index {d['stop_at_index']}")
            print(f"            cur: {d['left_bands']}")
            print(f"            nxt: {d['stop_bands']}")
        elif ev == "emit":
            print(f"[EMIT] run {d['run_start']}..{d['run_end_exclusive']} -> {d['final_bands']} | seeds={d['seeds']}")

    # Consolidate neighbors with debug ON
    atoms_with_seeds = _consolidate_neighboring_atoms(atoms, games_order, atom_seed_lines, debug=True, debug_fn=dbg)

    # Render
    letters = [chr(c) for c in range(ord(start_letter), ord("Z") + 1)]
    blocks: list[str] = []
    for idx, (atom, seeds_map) in enumerate(atoms_with_seeds):
        label = letters[idx] if idx < len(letters) else f"Z{idx - len(letters) + 1}"
        clauses = _render_clause_lines_ordered(atom, games_order)
        head = clauses[0] if clauses else "(no clauses)"
        tail = [f"    AND {c}" for c in clauses[1:]]
        ordered_seeds = sorted(seeds_map) if seed_order is None else [s for s in seed_order if s in seeds_map]

        block = [f"Scenario {label}", head, *tail]
        if ordered_seeds:
            block.append(":")
            for s in ordered_seeds:
                block.append(f"{s} Seed: {seeds_map[s]}")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


# ---------- Main enumeration + outputs ----------
def enumerate_region(
    conn, clazz, region, season, out_csv=None, explain_json=None, out_seeding=None, out_scenarios=None, debug=False
):
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
    completed = fetch_completed_pairs(conn, teams, season)  # fixed results already known
    print("Completed games:", completed)
    remaining = fetch_remaining_pairs(conn, teams, season)  # undecided region games
    num_remaining = len(remaining)

    # ----- Accumulators for odds -----
    first_counts = Counter()
    second_counts = Counter()
    third_counts = Counter()
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
            teams,
            completed,
            remaining,
            0,
            margins={},
            base_margin_default=7,
            pa_win=pa_for_winner,
            debug=debug,
        )
        slots = rank_to_slots(final_order)
        for team, (lo_seed, hi_seed) in slots.items():
            if 1 >= lo_seed and 1 <= hi_seed:
                first_counts[team] += 1
            if 2 >= lo_seed and 2 <= hi_seed:
                second_counts[team] += 1
            if 3 >= lo_seed and 3 <= hi_seed:
                third_counts[team] += 1
            if 4 >= lo_seed and 4 <= hi_seed:
                fourth_counts[team] += 1
        denom = 1.0

    # ----- Otherwise enumerate all masks (2^R) -----
    else:
        total_masks = 1 << num_remaining
        for outcome_mask in range(total_masks):
            # 1) Decode this mask into a base assignment dict for explanations
            var_assignment = {}
            for bit_index, (var_name, team_a, team_b) in enumerate(boolean_game_vars):
                bit_value = (outcome_mask >> bit_index) & 1
                var_assignment[var_name] = bool(bit_value)

            # 2) Compute standings with default margins to locate tie buckets
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

                        # --- inside enumerate_region(), where you currently compute `found` ---
                        # Scan margins 1..12 for the same-direction winner and collect *all* change points
                        orders_by_m = []
                        for m in range(1, 13):
                            test_margins = dict(base_margins)
                            test_margins[(a, b)] = m
                            test_order = resolve_standings_for_mask(
                                teams,
                                completed,
                                remaining,
                                mask_for_dir,
                                margins=test_margins,
                                base_margin_default=7,
                                pa_win=pa_for_winner,
                            )
                            # store a tuple for stable comparison
                            orders_by_m.append(tuple(test_order))

                        change_points = []
                        for m in range(2, 13):
                            if orders_by_m[m - 1] != orders_by_m[m - 2]:
                                # boundary between (m-1) and m
                                change_points.append(m)

                        # Save *all* thresholds (may be empty)
                        thresholds_dir[((a, b), winner)] = change_points

                        # Helpful debug
                        print(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: thresholds={change_points}")

            # 4) If no thresholds for this mask, resolve once; else split by thresholds that match the mask’s winners
            #    i.e., for each intra-bucket matchup we use the threshold for the *actual* winner in this mask
            if not intra_bucket_games:
                # (unchanged: resolve once)
                final_order = resolve_standings_for_mask(
                    teams,
                    completed,
                    remaining,
                    outcome_mask,
                    margins=base_margins,
                    base_margin_default=7,
                    pa_win=pa_for_winner,
                )
                slots = rank_to_slots(final_order)
                for team, (lo_seed, hi_seed) in slots.items():
                    if 1 >= lo_seed and 1 <= hi_seed:
                        first_counts[team] += 1
                    if 2 >= lo_seed and 2 <= hi_seed:
                        second_counts[team] += 1
                    if 3 >= lo_seed and 3 <= hi_seed:
                        third_counts[team] += 1
                    if 4 >= lo_seed and 4 <= hi_seed:
                        fourth_counts[team] += 1
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
                        intervals = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
                        interval_specs.append(((a, b), mask_winner, intervals))

                if not interval_specs:
                    # No intervals to branch on: resolve once with base_margins
                    final_order = resolve_standings_for_mask(
                        teams,
                        completed,
                        remaining,
                        outcome_mask,
                        margins=base_margins,
                        base_margin_default=7,
                        pa_win=pa_for_winner,
                    )
                    slots = rank_to_slots(final_order)
                    for team, (lo_seed, hi_seed) in slots.items():
                        if 1 >= lo_seed and 1 <= hi_seed:
                            first_counts[team] += 1
                        if 2 >= lo_seed and 2 <= hi_seed:
                            second_counts[team] += 1
                        if 3 >= lo_seed and 3 <= hi_seed:
                            third_counts[team] += 1
                        if 4 >= lo_seed and 4 <= hi_seed:
                            fourth_counts[team] += 1
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
                            teams,
                            completed,
                            remaining,
                            outcome_mask,
                            margins=branch_margins,
                            base_margin_default=7,
                            pa_win=pa_for_winner,
                        )
                        slots = rank_to_slots(final_order)
                        for team, (lo_seed, hi_seed) in slots.items():
                            if 1 >= lo_seed and 1 <= hi_seed:
                                first_counts[team] += branch_weight  # type: ignore
                            if 2 >= lo_seed and 2 <= hi_seed:
                                second_counts[team] += branch_weight  # type: ignore
                            if 3 >= lo_seed and 3 <= hi_seed:
                                third_counts[team] += branch_weight  # type: ignore
                            if 4 >= lo_seed and 4 <= hi_seed:
                                fourth_counts[team] += branch_weight  # type: ignore
                        for team, (lo_seed, hi_seed) in slots.items():
                            scenario_minterms.setdefault(team, {}).setdefault(lo_seed, []).append(branch_assignment)

        # Each mask contributes weight 1; branch weights within a mask sum to 1.
        denom = float(1 << num_remaining)

    # ----- Compile/emit odds CSV (same format as before) -----
    results = []
    for school in teams:
        p1 = first_counts[school] / denom
        p2 = second_counts[school] / denom
        p3 = third_counts[school] / denom
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
        for school, o1, o2, o3, o4, op, fop, clinched, eliminated in results:
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

    def _normalize_clause_text(s: str) -> str:
        """
        Presentation-only cleanup:
        - 'by ≥ 1 and < k points' -> 'by < k points'
        - 'by ≥ 1 points' -> (drop; becomes base win)
        - 'by < 13 points' -> (drop; base win covers all wins)
        - 'by ≥ 1 and < 13 points' -> (drop; base win)
        Also trims extra whitespace after edits.
        """
        # ≥1 and <k  -> <k
        s = re.sub(r" by ≥ 1 and < (\d+) points", r" by < \1 points", s)

        # ≥1 only -> drop margin entirely (base win)
        s = re.sub(r" by ≥ 1 points", "", s)

        # <13 -> base win
        s = re.sub(r" by < 13 points", "", s)

        # ≥1 and <13 -> base win
        s = re.sub(r" by ≥ 1 and < 13 points", "", s)

        return " ".join(s.split())

    # ----- Optional scenarios text output (unchanged logic; clearer helpers) -----
    if out_scenarios:

        def var_phrase(var: str, val: bool, base_lookup: dict) -> str:
            """
            Human phrase for a boolean variable.
            Supports:
            - base winner:  "A>B"
            - threshold flags: "A>B_GE7" (True => ≥7, False => <7)
            Also collapses paired flags (GE lo == True and GE hi == False) into:
            "A Win over B by ≥ lo and < hi points"
            """

            def winner_loser_for_base(base: str, vlookup: dict, fallback_val: bool | None) -> tuple[str, str]:
                a, b = base.split(">", 1)
                base_val = vlookup.get(base)
                if base_val is None:
                    flip = f"{b}>{a}"
                    flip_val = vlookup.get(flip)
                    if flip_val is not None:
                        # flip_val True means (b beats a)
                        return (b, a) if flip_val else (a, b)
                    # last resort: assume fallback orientation
                    return (a, b) if (fallback_val is True) else (b, a)
                else:
                    return (a, b) if base_val else (b, a)

            if "_GE" in var:
                base, ge = var.split("_GE", 1)
                try:
                    thr = int(ge)
                except Exception:
                    thr = None

                # Try to detect an interval using the paired hi flag:
                if thr is not None and val is True:
                    # look for a "GE hi" False for the same base (means "< hi")
                    hi_candidates = []
                    for k, v in base_lookup.items():
                        if k.startswith(base + "_GE"):
                            try:
                                kthr = int(k.split("_GE", 1)[1])
                            except Exception:
                                continue
                            if kthr > thr and v is False:
                                hi_candidates.append(kthr)
                    if hi_candidates:
                        hi = min(hi_candidates)
                        w, l = winner_loser_for_base(base, base_lookup, True)
                        return f"{w} Win over {l} by ≥ {thr} and < {hi} points"

                # Otherwise render single-threshold clause
                w, l = winner_loser_for_base(base, base_lookup, val)
                if val:
                    return f"{w} Win over {l} by ≥ {ge} points"
                else:
                    return f"{w} Win over {l} by < {ge} points"

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
                return (a, b, "ge", thr)
            elif " by < " in right:
                opp_part, thr_part = right.split(" by < ", 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, "lt", thr)
            else:
                b = right.split(" by")[0].strip()
                return (a, b, "base", None)

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
                if k1 == "base" and k2 == "base":
                    return True
                if k1 == k2 and t1 == t2 and k1 in ("ge", "lt"):
                    return True
            # Same direction, complementary threshold comparators
            if a1 == a2 and b1 == b2 and t1 == t2 and {k1, k2} == {"ge", "lt"}:
                return True
            return False

        minimized = defaultdict(dict)
        for team, seed_map in scenario_minterms.items():
            for seed_num, minterms in seed_map.items():
                mins = [dict(m) for m in minterms]
                mins = minimize_minterms(mins, allow_combine=True)  # simplify
                minimized[seed_num][team] = mins

        scenarios_text = scenarios_text_from_team_seed_ordered(
            scenario_minterms, ["Brandon>Meridian", "Northwest Rankin>Petal", "Pearl>Oak Grove"]
        )

        print(scenarios_text)

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
                candidate_minterms = consolidate_all(candidate_minterms)

                print(
                    f"[DEBUG SCEN] Team {team}, seed {seed_num}, candidate minterms after consolidation: {candidate_minterms}"
                )

                def clauses_for_m(minterm_dict):
                    # Prefer margin-qualified clauses where present; avoid duplicates.
                    def flip_base(base: str) -> str:
                        if ">" in base:
                            a, b = base.split(">", 1)
                            return f"{b}>{a}"
                        return base

                    print("[DEBUG SCEN] Minterm team:", team, "(seed:", seed_num, ")")
                    print("[DEBUG SCEN] Minterm dict:", minterm_dict)

                    # Build matchup -> {
                    #   "base": [(var,val), ...]  # usually 0 or 1
                    #   "ge_true": set[int],      # thresholds with GEk == True
                    #   "ge_false": set[int],     # thresholds with GEk == False (meaning "< k")
                    # }
                    matchups = defaultdict(lambda: {"base": [], "ge_true": set(), "ge_false": set(), "orient": None})

                    def canon_key(a, b):
                        aa, bb = (a, b) if a <= b else (b, a)
                        return f"{aa}>{bb}"

                    for var, val in minterm_dict.items():
                        if "_GE" in var:
                            base, ge = var.split("_GE", 1)
                            a, b = base.split(">", 1)
                            key = canon_key(a, b)
                            # Track the *printed* orientation (winner>loser) based on the base winner in this minterm
                            base_val = minterm_dict.get(base)
                            if base_val is None:
                                flip = f"{b}>{a}"
                                flip_val = minterm_dict.get(flip)
                                if flip_val is not None:
                                    winner, loser = (b, a) if flip_val else (a, b)
                                else:
                                    # fallback: keep "a>b" orientation; we'll still word it correctly below
                                    winner, loser = a, b
                            else:
                                winner, loser = (a, b) if base_val else (b, a)
                            matchups[key]["orient"] = (winner, loser)  # type: ignore

                            thr = int(ge)
                            if val:
                                matchups[key]["ge_true"].add(thr)  # type: ignore
                            else:
                                matchups[key]["ge_false"].add(thr)  # type: ignore
                        else:
                            a, b = var.split(">", 1)
                            key = canon_key(a, b)
                            matchups[key]["base"].append((var, val))  # type: ignore
                            # If we haven’t set an orientation yet, set it now from the base
                            if matchups[key]["orient"] is None:
                                winner, loser = (a, b) if val else (b, a)
                                matchups[key]["orient"] = (winner, loser)  # type: ignore

                    clauses = []

                    # Emit one clause per matchup
                    for key, info in matchups.items():
                        (winner, loser) = info["orient"]  # type: ignore
                        # If we have any margin flags for this matchup, we prefer to render a single interval clause
                        if info["ge_true"] or info["ge_false"]:
                            # Lower bound = max(GE t that are True), default 1
                            lo = max(info["ge_true"]) if info["ge_true"] else 1
                            # Upper bound = min(GE t that are False), default 13 (open end)
                            hi = min(info["ge_false"]) if info["ge_false"] else 13
                            # Normalize nonsense (just in case)
                            lo = max(1, lo)
                            hi = max(lo + 0, hi)

                            # Apply housecleaning:
                            # - If [1,13): that's just a plain win, so don't render any margin wording.
                            # - If [1, k): render as "by < k points" (drop the ≥ 1 part).
                            # - If [L, 13): render as "by ≥ L points" (only if L > 1).
                            # - Else [L, k): "by ≥ L and < k points", but drop "≥ L" if L == 1.
                            if lo == 1 and hi == 13:
                                # fully open -> base win clause
                                clauses.append(_normalize_clause_text(f"{winner} Win over {loser}"))
                            elif lo == 1:
                                clauses.append(_normalize_clause_text(f"{winner} Win over {loser} by < {hi} points"))
                            elif hi == 13:
                                clauses.append(_normalize_clause_text(f"{winner} Win over {loser} by ≥ {lo} points"))
                            else:
                                clauses.append(
                                    _normalize_clause_text(f"{winner} Win over {loser} by ≥ {lo} and < {hi} points")
                                )
                        else:
                            # No margin flags recorded; emit the base clause (dedup later)
                            # Prefer the base that matches the orientation, if present
                            clauses.append(_normalize_clause_text(f"{winner} Win over {loser}"))

                    # Order deterministically by matchup position and comparator rank (base first)
                    matchup_index = {name: i for i, (name, _, _) in enumerate(boolean_game_vars)}

                    def classify_clause(c: str):
                        parsed = extract_pair(c)
                        if not parsed:
                            return (10**6, 99, c)
                        a, b, kind, thr = parsed
                        base = f"{a}>{b}"
                        aa, bb, _ = normalize_pair(a, b)
                        lex_base = f"{aa}>{bb}"
                        idx = matchup_index.get(base, matchup_index.get(lex_base, 10**6))
                        comp_rank = 0 if kind == "base" else (1 if kind == "ge" else 2)
                        return (idx, comp_rank, c)

                    clauses = sorted(set(clauses), key=classify_clause)
                    return clauses

                def block_sort_key(block_clauses: list[str]):
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
                        comp_rank = 0 if kind == "base" else (1 if kind == "ge" else 2)
                        # We also want base (no margin) variants to come before margin variants for the same matchup
                        return (idx, comp_rank, c)

                    # Build a signature: the first two matchup-keys in the block (after internal sorting)
                    ordered = sorted(block_clauses, key=classify_clause)
                    sig = [classify_clause(c)[:2] for c in ordered[:2]]
                    # fill to 2 entries to keep tuples same length
                    while len(sig) < 2:
                        sig.append((10**6, 99))
                    return (*sig[0], *sig[1], len(block_clauses), " | ".join(ordered))

                def absorb_or_blocks(blocks: list[list[str]]) -> list[list[str]]:
                    """Drop any block whose set of clauses is a strict superset of another block."""
                    sets = [frozenset(b) for b in blocks]
                    keep = [True] * len(blocks)
                    for i in range(len(blocks)):
                        if not keep[i]:
                            continue
                        for j in range(len(blocks)):
                            if i == j or not keep[j]:
                                continue
                            # If i is a strict superset of j, drop i
                            if sets[i] > sets[j]:
                                keep[i] = False
                                break
                    return [blk for k, blk in enumerate(blocks) if keep[k]]

                def is_complement(p1, p2):
                    """
                    True iff p1 and p2 are logical complements for the *same underlying matchup key*.
                    - BASE: (A>B, base) vs (B>A, base)  -> complements
                    - MARGIN: same direction + same threshold, 'ge' vs 'lt' -> complements
                    Everything else returns False.
                    """
                    if p1 is None or p2 is None:
                        return False
                    a1, b1, k1, t1 = p1
                    a2, b2, k2, t2 = p2

                    # Base complements (opposite directions)
                    if k1 == "base" and k2 == "base":
                        return (a1 == b2) and (b1 == a2)

                    # Margin complements: same direction & threshold, ge vs lt
                    if (a1 == a2) and (b1 == b2) and (t1 == t2) and {k1, k2} == {"ge", "lt"}:
                        return True

                    return False

                def reduce_tautology_blocks(blocks, extract_pair_fn, is_complement_fn):
                    """
                    Given a list of OR-blocks (each a List[str] of clauses), perform:
                    - Pairwise tautology reduction: if blocks i and j differ by exactly two clauses
                        that are complements (Y vs ¬Y), replace both with their intersection S.
                    - Then re-run superset absorption.

                    Returns a new list of blocks.
                    """
                    # Work on sets for easy comparisons
                    block_sets = [frozenset(b) for b in blocks]
                    changed = True

                    while changed:
                        changed = False
                        n = len(block_sets)
                        to_remove = set()
                        to_add = []

                        # ---- Tautology reduction: (S ∪ {Y}) OR (S ∪ {¬Y}) -> S
                        for i in range(n):
                            if i in to_remove:
                                continue
                            for j in range(i + 1, n):
                                if j in to_remove:
                                    continue
                                si = block_sets[i]
                                sj = block_sets[j]
                                inter = si & sj
                                diff_i = list(si - sj)
                                diff_j = list(sj - si)
                                if len(diff_i) == 1 and len(diff_j) == 1:
                                    p_i = extract_pair_fn(diff_i[0])
                                    p_j = extract_pair_fn(diff_j[0])
                                    if is_complement_fn(p_i, p_j):
                                        # Replace both with intersection
                                        to_remove.add(i)
                                        to_remove.add(j)
                                        to_add.append(frozenset(inter))
                                        changed = True

                        if changed:
                            # rebuild list: drop removed, add newly created S blocks
                            block_sets = [s for idx, s in enumerate(block_sets) if idx not in to_remove]
                            # avoid duplicates
                            existing = set(block_sets)
                            for s in to_add:
                                if s not in existing:
                                    block_sets.append(s)
                                    existing.add(s)

                        # ---- Superset absorption: drop any block that strictly contains another
                        # (Do this every pass so we keep things minimal.)
                        keep = [True] * len(block_sets)
                        for i in range(len(block_sets)):
                            if not keep[i]:
                                continue
                            for j in range(len(block_sets)):
                                if i == j or not keep[j]:
                                    continue
                                if block_sets[i] > block_sets[j]:  # strict superset
                                    keep[i] = False
                                    changed = True
                                    break
                        if changed:
                            block_sets = [s for k, s in enumerate(block_sets) if keep[k]]

                    # Convert back to lists and sort clauses deterministically
                    out_blocks = [sorted(list(s)) for s in block_sets]
                    return out_blocks

                prepared = [(m, clauses_for_m(m)) for m in candidate_minterms]
                prepared.sort(key=lambda t: block_sort_key(t[1]))

                # --- NEW: tautology reduction + absorption across OR blocks ---
                blocks_only = [c for _, c in prepared]
                blocks_only = reduce_tautology_blocks(blocks_only, extract_pair, is_complement)

                # Rebuild `prepared` with the reduced blocks; we don’t need minterms any more for printing
                prepared = [(None, b) for b in blocks_only]

                def _canon_matchup(a, b):
                    aa, bb = (a, b) if a <= b else (b, a)
                    return (aa, bb)

                def _interval_of_clause(c):
                    """Return (key=(aa,bb), dir='a>b'| 'b>a', interval) where interval is:
                    - None for base (no margin), meaning 'any win' for that direction
                    - (lo,hi) for 'a>b' with bounds per our phrasing rules
                    """
                    p = extract_pair(c)
                    if not p:
                        return None
                    a, b, kind, thr = p
                    key = _canon_matchup(a, b)
                    if kind == "base":
                        # direction decided by text
                        dir_ = "a>b" if f"{a} Win over {b}" in c else "b>a"
                        return (key, dir_, None)
                    # margin kinds: map to intervals we printed in clauses_for_m
                    # We only ever print: "< k", "≥ L", or "≥ L and < k"
                    # Parse them back:
                    if " by < " in c:
                        # a beats b by < k
                        k = int(c.split(" by < ", 1)[1].split()[0])
                        return (key, "a>b", (1, k))
                    if " by ≥ " in c and " and < " in c:
                        rest = c.split(" by ≥ ", 1)[1]
                        L = int(rest.split(" and < ", 1)[0])
                        k = int(rest.split(" and < ", 1)[1].split()[0])
                        return (key, "a>b", (L, k))
                    if " by ≥ " in c:
                        L = int(c.split(" by ≥ ", 1)[1].split()[0])
                        return (key, "a>b", (L, 13))
                    return None

                def _coverage_collapse_blocks(blocks):
                    """
                    If a set of OR-blocks that share the same 'pivot' clauses (all *other* games)
                    collectively covers *all* outcomes for some matchup M, then drop M from those blocks.

                    Coverage rules:
                    - Having a 'b>a' base clause covers the whole 'b wins' side.
                    - Having 'a>b' intervals whose union is [1,13) covers the whole 'a wins' side.
                    - If both sides are fully covered across the group, remove that matchup from all blocks.
                    """
                    # Group blocks by their pivot (block with clauses of matchup removed)
                    from collections import defaultdict

                    # Build per-block parsed forms
                    parsed_blocks = []
                    for blk in blocks:
                        parsed = [_interval_of_clause(c) for c in blk]
                        parsed_blocks.append(list(zip(blk, parsed)))

                    # For every unordered matchup, try collapsing
                    # Build list of all matchups appearing anywhere
                    all_matchups = set()
                    for blk in parsed_blocks:
                        for _c, p in blk:
                            if p:
                                all_matchups.add(p[0])

                    # Process each matchup independently
                    for mkey in all_matchups:
                        # Group blocks by 'pivot' (i.e., clauses NOT about this matchup)
                        groups = defaultdict(list)
                        for blk in parsed_blocks:
                            pivot = tuple(sorted(c for (c, p) in blk if not p or p[0] != mkey))
                            groups[pivot].append(blk)

                        def union_intervals(intervals):
                            if not intervals:
                                return []
                            xs = sorted(intervals)
                            out = [list(xs[0])]
                            for lo, hi in xs[1:]:
                                if lo <= out[-1][1]:
                                    out[-1][1] = max(out[-1][1], hi)
                                else:
                                    out.append([lo, hi])
                            return [tuple(t) for t in out]

                        # For each pivot group, check if coverage is full
                        for pivot, gblks in groups.items():
                            # Collect coverage over this matchup across these blocks
                            a_side = []  # intervals of 'a>b' (in [1,13))
                            b_covers = False  # any 'b>a' base present?
                            for blk in gblks:
                                for c, p in blk:
                                    if not p or p[0] != mkey:
                                        continue
                                    _key, dir_, interval = p
                                    if dir_ == "b>a":
                                        # base covers all 'b wins'
                                        b_covers = True
                                    elif dir_ == "a>b":
                                        if interval is None:
                                            # base 'a wins' -> covers [1,13)
                                            a_side = [(1, 13)]
                                        else:
                                            a_side.append(interval)

                            # Normalize/union a-side intervals
                            a_side = union_intervals(a_side)
                            a_full = len(a_side) == 1 and a_side[0] == (1, 13)

                            if a_full and b_covers:
                                # Full coverage: remove all clauses for this matchup from all blocks in the group
                                for blk in gblks:
                                    blk[:] = [(c, p) for (c, p) in blk if not p or p[0] != mkey]

                    # Reconstruct and dedupe blocks
                    out_blocks = []
                    seen = set()
                    for blk in parsed_blocks:
                        text_blk = tuple(sorted(c for (c, _p) in blk))
                        if text_blk not in seen:
                            seen.add(text_blk)
                            out_blocks.append(list(text_blk))
                    return out_blocks

                # --- NEW: tautology reduction + absorption across OR blocks ---
                blocks_only = [c for _, c in prepared]
                blocks_only = reduce_tautology_blocks(blocks_only, extract_pair, is_complement)

                # --- NEW: coverage collapse across blocks that partition a matchup ---
                blocks_only = _coverage_collapse_blocks(blocks_only)

                # After: blocks_only = _coverage_collapse_blocks(blocks_only)
                blocks_only = [[_normalize_clause_text(c) for c in blk] for blk in blocks_only]

                # remove any now-empty strings and dedupe
                blocks_only = [sorted({c for c in blk if c}) for blk in blocks_only if any(c for c in blk)]

                # Rebuild `prepared` with the reduced blocks; we don’t need minterms any more for printing
                prepared = [(None, b) for b in blocks_only]

                printed_any_block = False
                for _, clauses in prepared:
                    if not clauses:
                        continue
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
        with open("scenarios_letter.txt", "w") as f:
            f.write(scenarios_text)
        print(f"Wrote scenarios text: {out_path}")
        print("Wrote scenarios_letter.txt text: scenarios_letter.txt")


# --------------------------- CLI ---------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="clazz", type=int, required=True)
    ap.add_argument("--region", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dsn", type=str, default=os.getenv("PG_DSN", ""))
    ap.add_argument("--out-csv", type=str)
    ap.add_argument("--explain-json", type=str)
    ap.add_argument("--out-seeding", type=str)
    ap.add_argument("--out-scenarios", type=str)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    if not psycopg:
        raise SystemExit("Please install psycopg: pip install 'psycopg[binary]'")
    if not args.dsn:
        raise SystemExit("Provide --dsn or PG_DSN")
    with psycopg.connect(args.dsn) as conn:
        enumerate_region(
            conn,
            args.clazz,
            args.region,
            args.season,
            out_csv=args.out_csv,
            explain_json=args.explain_json,
            out_seeding=args.out_seeding,
            out_scenarios=args.out_scenarios,
            debug=args.debug,
        )


if __name__ == "__main__":
    main()
