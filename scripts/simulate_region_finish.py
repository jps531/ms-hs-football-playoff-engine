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

import argparse
import math
import os
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from itertools import product
from typing import Any, cast

# Ensure the project root is on the path when running from scripts/ directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg
except Exception:
    psycopg = None

from prefect_files.data_classes import CompletedGame, RawCompletedGame, RemainingGame
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

# --------------------------- String constants ---------------------------

_BY_GE = " by ≥ "
_BY_LT = " by < "
_AND_LT = " and < "

# --------------------------- Fetch Helpers ---------------------------


def fetch_division(conn, clazz: int, region: int, season: int) -> list[str]:
    """Fetch the list of school names for a given class, region, and season.

    Args:
        conn: An open psycopg connection.
        clazz: MHSAA classification number (e.g. 7 for 7A).
        region: Region number within the class (e.g. 3).
        season: Four-digit season year (e.g. 2025).

    Returns:
        School names sorted alphabetically.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
            (clazz, region, season),
        )
        return [r[0] for r in cur.fetchall()]


def fetch_completed_pairs(conn, teams: list[str], season: int) -> list[CompletedGame]:
    """Fetch finalized region-game results for a set of teams and convert to CompletedGame objects.

    Queries the ``games`` table for rows where both the school and opponent are in
    ``teams``, the game is marked ``final=TRUE``, and it is a region game.  Rows are
    returned in raw dict form and then normalized via ``get_completed_games()``.

    Args:
        conn: An open psycopg connection.
        teams: School names whose intra-group games should be fetched.
        season: Four-digit season year.

    Returns:
        Deduplicated, canonically ordered ``CompletedGame`` objects for all played
        region matchups among ``teams``.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school, opponent, date, result, points_for, points_against "
            "FROM games "
            "WHERE season=%s AND final=TRUE AND region_game=TRUE "
            "  AND school = ANY(%s) AND opponent = ANY(%s)",
            (season, teams, teams),
        )
        rows = cur.fetchall()

    raw_results = cast(
        list[RawCompletedGame],
        [
            {
                "school": school,
                "opponent": opp,
                "date": str(date),
                "result": result,
                "points_for": pf,
                "points_against": pa,
            }
            for school, opp, date, result, pf, pa in rows
        ],
    )
    return get_completed_games(raw_results)


def fetch_remaining_pairs(conn, teams: list[str], season: int) -> list[RemainingGame]:
    """Fetch unplayed region matchups among ``teams`` for ``season``.

    Uses a CTE to deduplicate (a, b) pairs — each unplayed game appears once with
    the school names in lexicographic order — then wraps each pair in a
    ``RemainingGame``.

    Args:
        conn: An open psycopg connection.
        teams: School names to consider; only intra-group games are returned.
        season: Four-digit season year.

    Returns:
        One ``RemainingGame`` per distinct unplayed intra-region matchup.
    """
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
    """Return True if ``k`` is a margin-threshold key of the form ``'A>B_GEn'``."""
    return "_GE" in k and ">" in k


def _parse_ge(k: str) -> tuple[str, int]:
    """Split a GE key ``'A>B_GEn'`` into ``('A>B', n)``."""
    base, _, thr = k.partition("_GE")
    return base, int(thr)


def _flip(base: str) -> str:
    """Return the reversed orientation of a base key ``'A>B'`` → ``'B>A'``."""
    a, b = base.split(">", 1)
    return f"{b}>{a}"


def _canon_pair(base: str) -> tuple[str, str]:
    """Split a base key ``'A>B'`` into the ``(a, b)`` team-name tuple."""
    a, b = base.split(">", 1)
    return a, b


def _non_ge_signature(m: dict[str, bool]) -> tuple[tuple[str, bool], ...]:
    """Return a sorted, hashable tuple of all non-GE game-outcome items from minterm ``m``.

    Used to group minterms that share the same win/loss pattern before expanding their
    margin bands.
    """
    items = [(k, v) for k, v in m.items() if ">" in k and not _is_ge_key(k)]
    items.sort()
    return tuple(items)


def _interval_for_base(m: dict[str, bool], base: str) -> tuple[float, float, str]:
    """Extract the half-open margin interval and winner orientation for one matchup.

    Reads all base and GE keys in minterm ``m`` that pertain to ``base`` (e.g.
    ``'A>B'``), infers who wins, and returns the implied point-differential interval
    ``[lo, hi)`` in the winner's direction.

    Args:
        m: Minterm dict mapping variable names to boolean values.
        base: Base orientation key of the form ``'A>B'``.

    Returns:
        A three-tuple ``(lo, hi, winner)`` where ``lo`` and ``hi`` are the bounds of
        the margin interval (``math.inf`` for an open upper bound) and ``winner`` is
        the orientation string (``base`` or its flip) indicating which team wins.
    """
    lo = -math.inf
    hi = math.inf
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
        assert winner is not None
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
    """Drop redundant base/flip keys from an atom when GE keys already encode the outcome."""
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
    """Collect every distinct margin-threshold cut for each base across all minterms.

    Scans every minterm for GE keys (e.g. ``'A>B_GE5'``) and plain win keys (implying
    a cut at 1) so that later partitioning can produce airtight, non-overlapping bands
    that cover the full input space.

    Args:
        all_minterms: Iterable of minterm dicts (variable name → boolean value).

    Returns:
        A dict mapping each base orientation string to a sorted list of integer cut
        thresholds (always includes 1 when any information exists for that base).
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
) -> list[tuple[int, float]]:
    """Build airtight margin-interval partitions for one base using globally collected cuts.

    Slices the margin axis at every threshold seen across all minterms and retains only
    the pieces that are actually covered by at least one band from the current signature
    group.  This guarantees the resulting atoms are non-overlapping and jointly exhaustive
    over the input space.

    Args:
        base: Base orientation key (e.g. ``'A>B'``) to partition.
        global_cuts: Mapping from base key to sorted list of cut thresholds, as returned
            by ``_collect_global_cuts()``.
        bands_from_input: Half-open ``(lo, hi)`` intervals already observed for ``base``
            in the current signature group (used to filter irrelevant pieces).

    Returns:
        A list of ``(lo, hi)`` tuples representing the retained partitions, where ``hi``
        may be ``math.inf`` for the open-ended tail.
    """
    if base not in global_cuts:
        # No cuts observed anywhere: no partitioning
        return []
    cuts = list(global_cuts[base])
    cuts.sort()
    parts: list[tuple[int, float]] = []

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
    """Expand a group of minterms that share the same win/loss signature into fine-grained atoms.

    For each base whose winner direction appears in the group, computes globally-cut
    partitions and takes the Cartesian product to produce one atom per distinct
    margin-band combination.  Atoms that have no GE information simply reproduce the
    fixed win/loss assignment unchanged.

    Args:
        signature_group: Minterms that all share the same non-GE outcome pattern.
        global_cuts: Threshold cuts per base, from ``_collect_global_cuts()``.

    Returns:
        A list of expanded atom dicts with GE keys encoding specific margin bands.
        May be a single-element list (the fixed assignment) if no relevant partitions
        exist.
    """
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
    partitions: dict[str, list[tuple[int, float]]] = {}
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
    """Render one atom as human-readable clause lines in the specified game order.

    For each base in ``games_order``, emits a single natural-language line such as
    ``"Brandon Win over Meridian by ≥ 5 points"`` or ``"Meridian Win over Brandon"``.
    Games with no data in the atom are silently skipped.

    Args:
        atom: Minterm dict encoding outcomes (and optional margin bands) for each game.
        games_order: Base orientation strings defining the print order (e.g.
            ``['Brandon>Meridian', 'Oak Grove>Pearl']``).

    Returns:
        One clause string per game present in the atom.
    """
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
def _band_sort_key(base: str, atom: dict[str, bool], loser_first: bool = True) -> tuple[int, int, int | float]:
    """Produce a three-element sort key for one game within an atom.

    Used to impose a logical progression over scenarios: losses (or wins, depending on
    ``loser_first``) appear first, then wins are ordered from least-specific (any margin)
    through increasingly tight lower-bound intervals.

    Args:
        base: Base orientation key ``'A>B'`` for the game being keyed.
        atom: Minterm dict for this scenario.
        loser_first: If ``True`` (default), the B>A (flip) winner group is ranked 0
            so losses appear before wins in the sort.

    Returns:
        A ``(winner_group, granularity, hi_rank)`` tuple suitable for use as a sort key.
    """
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
    """Return a composite sort key for an atom by concatenating per-game band keys in order."""
    # Lexicographic by games in order, using the per-game band keys
    key = []
    for base in games_order:
        key.extend(_band_sort_key(base, atom, loser_first=True))
    return tuple(key)


def _bands_for_atom(atom: dict[str, bool], games_order: list[str]) -> dict[str, tuple[int, float, str]]:
    """Extract normalized ``(lo, hi, winner)`` bands from an atom for each game.

    Args:
        atom: Minterm dict encoding outcomes and optional GE margin keys.
        games_order: Base orientation strings to extract, in the desired iteration order.

    Returns:
        A dict mapping each base key to a ``(lo, hi, winner)`` triple where ``lo`` is an
        ``int`` ≥ 1, ``hi`` is an ``int`` or ``math.inf``, and ``winner`` is the base
        key or its flip indicating which team wins.
    """
    out: dict[str, tuple[int, float, str]] = {}
    for base in games_order:
        lo, hi, winner = _interval_for_base(atom, base)
        # normalize
        lo_band = max(1, int(lo)) if lo != -math.inf else 1
        hi_band = hi
        out[base] = (lo_band, hi_band, winner)
    return out


def _bands_to_atom(bands: dict[str, tuple[int, float, str]]) -> dict[str, bool]:
    """Rebuild a minterm atom dict from ``(lo, hi, winner)`` bands.

    Encodes each band back into the variable-name convention used throughout:
    plain win keys (``'A>B': True``), GE-true keys (margin ≥ lo), and GE-false
    keys (margin < hi).  Redundant base keys are dropped when GE keys are present.

    Args:
        bands: Mapping from base key to ``(lo, hi, winner)`` as produced by
            ``_bands_for_atom()``.

    Returns:
        A minterm dict suitable for further processing or rendering.
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


def _touching(a: tuple[int, float], b: tuple[int, float]) -> bool:
    """Return True if two half-open bands [lo_a,hi_a) and [lo_b,hi_b) touch or overlap."""
    lo_a, hi_a = a
    lo_b, hi_b = b
    # treat math.inf as a very large number for comparison
    a_end = hi_a
    b_end = hi_b
    if a_end == math.inf and lo_b == math.inf:  # degenerate, won’t happen
        return False
    # overlap or just touching at boundary
    a_end_safe = a_end if a_end != math.inf else 10**12
    b_end_safe = b_end if b_end != math.inf else 10**12
    return (lo_a <= lo_b <= a_end_safe) or (lo_b <= lo_a <= b_end_safe)


def _seed_signature(seeds: dict[int, str]) -> tuple[tuple[int, str], ...]:
    """Stable comparable form of a seed map."""
    return tuple(sorted(seeds.items()))


def _fmt_band(lo: int, hi: float) -> str:
    """Format a single half-open margin interval as a compact debug string (e.g. ``'[5, 8)'``)."""
    if hi == math.inf and lo <= 1:
        return "any"
    if hi == math.inf:
        return f"[{lo}, +∞)"
    if lo <= 1:
        return f"[1, {hi})"
    return f"[{lo}, {hi})"


def _fmt_bands(bands: dict[str, tuple[int, float, str]], games_order: list[str]) -> str:
    """Format a full set of bands as a pipe-separated debug string in game order."""
    parts = []
    for base in games_order:
        if base not in bands:
            continue
        lo, hi, winner = bands[base]
        parts.append(f"{winner}: {_fmt_band(lo, hi)}")
    return " | ".join(parts)


def _try_merge_neighbor(
    a_bands: dict[str, tuple[int, float, str]],
    b_bands: dict[str, tuple[int, float, str]],
    same_seeds: bool,
    games_order: list[str],
) -> tuple[bool, dict[str, tuple[int, float, str]]]:
    """Attempt to merge two adjacent scenario band-sets into one covering band-set.

    A merge succeeds when both scenarios produce identical seed outcomes, all games have
    the same winner, bands are equal for every game except exactly one, and that one
    game's bands touch or overlap.  On success the two bands are collapsed into a single
    covering interval.

    Args:
        a_bands: Band-set for the left scenario (base for the merged result).
        b_bands: Band-set for the right (neighbor) scenario.
        same_seeds: Pre-computed flag indicating whether the two scenarios yield the
            same seed assignments.
        games_order: Canonical game ordering used to iterate bands consistently.

    Returns:
        A ``(merged, result_bands)`` tuple.  If ``merged`` is ``True``, ``result_bands``
        is the newly merged band-set; otherwise ``result_bands`` is ``a_bands``
        unchanged.
    """
    if not same_seeds:
        return False, a_bands

    diffs = []
    for base in games_order:
        lo_a, hi_a, winner_a = a_bands[base]
        lo_b, hi_b, winner_b = b_bands[base]
        if winner_a != winner_b:
            return False, a_bands
        if (lo_a, hi_a) != (lo_b, hi_b):
            diffs.append(base)
            if len(diffs) > 1:
                return False, a_bands

    if not diffs:
        # identical scenarios — merge trivially
        return True, a_bands

    # exactly one differing base
    base = diffs[0]
    lo_a, hi_a, winner = a_bands[base]
    lo_b, hi_b, _ = b_bands[base]
    if not _touching((lo_a, hi_a), (lo_b, hi_b)):
        return False, a_bands

    # make a single covering band [min_lo, max_hi)
    lo_merged = min(lo_a, lo_b)
    hi_merged = hi_a if hi_a == math.inf or (hi_b != math.inf and hi_a >= hi_b) else hi_b
    if hi_a == math.inf or hi_b == math.inf:
        hi_merged = math.inf
    merged = dict(a_bands)
    merged[base] = (lo_merged, hi_merged, winner)
    return True, merged


def _consolidate_neighboring_atoms(
    atoms_sorted: list[dict[str, bool]],
    games_order: list[str],
    seed_lookup_fn: Callable[[dict[str, bool]], dict[int, str]],
    *,
    debug: bool = False,
    debug_fn: Callable[[str, dict[str, Any]], None] | None = None,
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
        """Fire a debug event if debug mode is active."""
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
    """Render human-readable scenario blocks for each team/seed combination.

    Expands minterms into globally-consistent margin partitions, merges
    neighboring atoms with identical seed outcomes, and formats the result as
    labelled letter-blocks (e.g. "Scenario A: Brandon wins …").

    Args:
        team_seed_map: Nested map of team → seed number → minterm collection.
        games_order: Ordered list of ``"A>B"`` matchup strings used for sorting
            and rendering clauses.
        start_letter: Letter to begin block labelling from (default ``"A"``).
        seed_order: Seed numbers to include; ``None`` means include all.

    Returns:
        Formatted multi-line string with one labelled block per merged scenario.
    """
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
    for group in sig_to_minterms.values():
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
        """Return True if ``atom`` is consistent with the broader minterm ``broad``."""
        # Clean both sides of redundant base when GE present
        a_clean = _remove_base_if_ge_present_in_atom(dict(atom))
        b_clean = _remove_base_if_ge_present_in_atom(dict(broad))

        # GE keys must match exactly if present in broad
        for k, v in b_clean.items():
            if _is_ge_key(k) and a_clean.get(k) is not v:
                return False
        # Base keys in broad: check via winner from atom
        for k, v in b_clean.items():
            if ">" in k and not _is_ge_key(k):
                _lo, _hi, winner = _interval_for_base(a_clean, k)
                if v is True and winner != k:
                    return False
                if v is False and winner != _flip(k):
                    return False
        return True

    # Sort scenarios in the requested progression
    atoms.sort(key=lambda m: _scenario_sort_key(m, games_order))

    def atom_seed_lines(atom: dict[str, bool]) -> dict[int, str]:
        """Return the winning team for each seed number under this atom."""
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
        """Print a minimal debug summary for consolidation events."""
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
def enumerate_region(conn, clazz, region, season, out_seeding=None, out_scenarios=None, debug=False):
    """Enumerate all remaining outcomes for a region, apply tiebreakers, and write odds and scenarios.

    Each undecided region game is treated as a boolean variable (first-listed team wins or
    not).  For each of the 2^R outcome masks, the function optionally detects Step-3 knife-
    edge margins (±12 cap) that change the standings order and splits those masks into
    weighted sub-branches.  First-through-fourth-place tallies are accumulated across all
    branches and converted to probabilities.

    Args:
        conn: An open psycopg connection used to fetch division, completed, and remaining games.
        clazz: MHSAA classification number (e.g. 7 for 7A).
        region: Region number within the class.
        season: Four-digit season year.
        out_seeding: Optional file path; if provided, a plain-text seeding-odds report is
            written there.
        out_scenarios: Optional file path; if provided, a human-readable scenario-by-scenario
            breakdown is written there (and ``scenarios_letter.txt`` is also written).
        debug: If ``True``, passes debug flags into the tiebreaker resolution layer.

    Raises:
        SystemExit: If no teams are found for the given class/region/season.
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
    # defaultdict(float) rather than Counter so branch_weight (float) accumulates without type errors
    first_counts: dict[str, float] = defaultdict(float)
    second_counts: dict[str, float] = defaultdict(float)
    third_counts: dict[str, float] = defaultdict(float)
    fourth_counts: dict[str, float] = defaultdict(float)

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
                                first_counts[team] += branch_weight
                            if 2 >= lo_seed and 2 <= hi_seed:
                                second_counts[team] += branch_weight
                            if 3 >= lo_seed and 3 <= hi_seed:
                                third_counts[team] += branch_weight
                            if 4 >= lo_seed and 4 <= hi_seed:
                                fourth_counts[team] += branch_weight
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
        if clinched:
            final_playoffs = 1.0
        elif eliminated:
            final_playoffs = 0.0
        else:
            final_playoffs = p_playoffs
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
        s = s.replace(" by ≥ 1 points", "")

        # <13 -> base win
        s = s.replace(" by < 13 points", "")

        # ≥1 and <13 -> base win
        s = s.replace(" by ≥ 1 and < 13 points", "")

        return " ".join(s.split())

    # ----- Optional scenarios text output (unchanged logic; clearer helpers) -----
    if out_scenarios:

        def extract_pair(clause: str):
            """Parse a human clause into a structured tuple: (a, b, kind, thr) where
            kind ∈ {'base','ge','lt'} and thr is an int or None."""
            if " Win over " not in clause:
                return None
            left, right = clause.split(" Win over ", 1)
            a = left.strip()
            # Margin-qualified?
            if _BY_GE in right:
                opp_part, thr_part = right.split(_BY_GE, 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, "ge", thr)
            elif _BY_LT in right:
                opp_part, thr_part = right.split(_BY_LT, 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, "lt", thr)
            else:
                b = right.split(" by")[0].strip()
                return (a, b, "base", None)

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
                    """Convert a single minterm dict into a sorted list of human-readable clauses."""
                    print("[DEBUG SCEN] Minterm team:", team, "(seed:", seed_num, ")")
                    print("[DEBUG SCEN] Minterm dict:", minterm_dict)

                    # Build matchup -> {
                    #   "base": [(var,val), ...]  # usually 0 or 1
                    #   "ge_true": set[int],      # thresholds with GEk == True
                    #   "ge_false": set[int],     # thresholds with GEk == False (meaning "< k")
                    # }
                    matchups: defaultdict[str, dict[str, Any]] = defaultdict(
                        lambda: {"base": [], "ge_true": set(), "ge_false": set(), "orient": None}
                    )

                    def canon_key(a, b):
                        """Return the canonical ``'lesser>greater'`` matchup key."""
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
                            matchups[key]["orient"] = (winner, loser)

                            thr = int(ge)
                            if val:
                                matchups[key]["ge_true"].add(thr)
                            else:
                                matchups[key]["ge_false"].add(thr)
                        else:
                            a, b = var.split(">", 1)
                            key = canon_key(a, b)
                            matchups[key]["base"].append((var, val))
                            # If we haven’t set an orientation yet, set it now from the base
                            if matchups[key]["orient"] is None:
                                winner, loser = (a, b) if val else (b, a)
                                matchups[key]["orient"] = (winner, loser)

                    clauses = []

                    # Emit one clause per matchup
                    for key, info in matchups.items():
                        (winner, loser) = info["orient"]
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
                        """Return a sort key: (matchup_index, comparator_rank, clause_text)."""
                        parsed = extract_pair(c)
                        if not parsed:
                            return (10**6, 99, c)
                        a, b, kind, _thr = parsed
                        base = f"{a}>{b}"
                        aa, bb, _ = normalize_pair(a, b)
                        lex_base = f"{aa}>{bb}"
                        idx = matchup_index.get(base, matchup_index.get(lex_base, 10**6))
                        if kind == "base":
                            comp_rank = 0
                        elif kind == "ge":
                            comp_rank = 1
                        else:
                            comp_rank = 2
                        return (idx, comp_rank, c)

                    clauses = sorted(set(clauses), key=classify_clause)
                    return clauses

                def block_sort_key(block_clauses: list[str]):
                    """Return a sort key for a scenario block based on matchup order and comparator rank."""
                    # Sort blocks by: (a) presence & comparator of the first matchup clause,
                    # then (b) presence/comparator of the next matchup in boolean order,
                    # then (c) total clause count (shorter first), then (d) the text itself.
                    matchup_index = {name: i for i, (name, _, _) in enumerate(boolean_game_vars)}

                    def classify_clause(c: str):
                        """Return a sort key: (matchup_index, comparator_rank, clause_text)."""
                        parsed = extract_pair(c)
                        if not parsed:
                            return (10**6, 99, c)  # push unknowns last, deterministically
                        a, b, kind, _thr = parsed
                        base = f"{a}>{b}"
                        aa, bb, _ = normalize_pair(a, b)
                        lex_base = f"{aa}>{bb}"
                        idx = matchup_index.get(base, matchup_index.get(lex_base, 10**6))
                        if kind == "base":
                            comp_rank = 0
                        elif kind == "ge":
                            comp_rank = 1
                        else:
                            comp_rank = 2
                        # We also want base (no margin) variants to come before margin variants for the same matchup
                        return (idx, comp_rank, c)

                    # Build a signature: the first two matchup-keys in the block (after internal sorting)
                    ordered = sorted(block_clauses, key=classify_clause)
                    sig = [classify_clause(c)[:2] for c in ordered[:2]]
                    # fill to 2 entries to keep tuples same length
                    while len(sig) < 2:
                        sig.append((10**6, 99))
                    return (*sig[0], *sig[1], len(block_clauses), " | ".join(ordered))

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
                    out_blocks = [sorted(s) for s in block_sets]
                    return out_blocks

                prepared = [(m, clauses_for_m(m)) for m in candidate_minterms]
                prepared.sort(key=lambda t, _key=block_sort_key: _key(t[1]))

                # --- NEW: tautology reduction + absorption across OR blocks ---
                blocks_only = [c for _, c in prepared]
                blocks_only = reduce_tautology_blocks(blocks_only, extract_pair, is_complement)

                # Rebuild `prepared` with the reduced blocks; we don’t need minterms any more for printing
                prepared = [(None, b) for b in blocks_only]

                def _canon_matchup(a, b):
                    """Return the canonical (lesser, greater) team pair."""
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
                    a, b, kind, _thr = p
                    key = _canon_matchup(a, b)
                    if kind == "base":
                        # direction decided by text
                        dir_ = "a>b" if f"{a} Win over {b}" in c else "b>a"
                        return (key, dir_, None)
                    # margin kinds: map to intervals we printed in clauses_for_m
                    # We only ever print: "< k", "≥ L", or "≥ L and < k"
                    # Parse them back:
                    if _BY_LT in c:
                        # a beats b by < k
                        k = int(c.split(_BY_LT, 1)[1].split()[0])
                        return (key, "a>b", (1, k))
                    if _BY_GE in c and _AND_LT in c:
                        rest = c.split(_BY_GE, 1)[1]
                        lo_bound = int(rest.split(_AND_LT, 1)[0])
                        k = int(rest.split(_AND_LT, 1)[1].split()[0])
                        return (key, "a>b", (lo_bound, k))
                    if _BY_GE in c:
                        lo_bound = int(c.split(_BY_GE, 1)[1].split()[0])
                        return (key, "a>b", (lo_bound, 13))
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
                            """Merge a list of (lo, hi) intervals into a minimal covering set."""
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
                blocks_only = [sorted({c for c in blk if c}) for blk in blocks_only if any(blk)]

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
    """Parse CLI arguments and invoke ``enumerate_region()`` for a single class/region/season.

    Reads connection details from ``--dsn`` or the ``PG_DSN`` environment variable.
    Exits with an error message if psycopg is not installed or no DSN is provided.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="clazz", type=int, required=True)
    ap.add_argument("--region", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dsn", type=str, default=os.getenv("PG_DSN", ""))
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
            out_seeding=args.out_seeding,
            out_scenarios=args.out_scenarios,
            debug=args.debug,
        )


if __name__ == "__main__":
    main()
