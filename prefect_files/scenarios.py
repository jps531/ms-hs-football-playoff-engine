from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from itertools import product

from prefect import get_run_logger
from prefect.exceptions import MissingContextError

from prefect_files.data_classes import CompletedGame, RemainingGame, StandingsOdds
from prefect_files.tiebreakers import (
    rank_to_slots,
    resolve_standings_for_mask,
    standings_from_mask,
    tie_bucket_groups,
    unique_intra_bucket_games,
)

# -------------------------
# Formatting
# -------------------------


def pct_str(x: float) -> str:
    """Format a float as a percentage string with no more than 2 significant digits."""
    val = x * 100.0
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.0f}%".rstrip("0").rstrip(".")


# -------------------------
# Scenario consolidation helpers
# -------------------------


def consolidate_opposites_and_remove_bases(candidate_minterms: list[dict[str, bool]]) -> list[dict[str, bool]]:
    """
    1. Consolidate dictionaries that are identical except for one key whose
       boolean values are opposite — removing that differing key.
    2. Remove any base keys (e.g., 'A>B') when a GE variant (e.g., 'A>B_GE1') exists.
    """
    consolidated = []
    used = set()

    for i, d1 in enumerate(candidate_minterms):
        if i in used:
            continue
        merged = False
        for j, d2 in enumerate(candidate_minterms[i + 1 :], start=i + 1):
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

    cleaned = []
    for d in consolidated:
        ge_bases = {k.split("_GE")[0] for k in d if "_GE" in k}
        new_d = {k: v for k, v in d.items() if k.split("_GE")[0] not in ge_bases or "_GE" in k}
        cleaned.append(new_d)

    return cleaned


def _parse_ge_key(k: str) -> tuple[str, int] | None:
    if "_GE" not in k:
        return None
    base, _, tail = k.partition("_GE")
    try:
        t = int(tail)
    except ValueError:
        return None
    return base, t


def _signature_without_family(d: dict[str, bool], base: str) -> tuple[tuple[str, bool], ...]:
    items = []
    for k, v in d.items():
        parsed = _parse_ge_key(k)
        if (parsed and parsed[0] == base) or (k == base):
            continue
        items.append((k, v))
    items.sort()
    return tuple(items)


def _interval_for_family(d: dict[str, bool], base: str) -> tuple[float, float]:
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


def consolidate_opposites(dicts: list[dict[str, bool]]) -> list[dict[str, bool]]:
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


def merge_ge_intervals_to_base_safe(dicts: list[dict[str, bool]], win_threshold: int = 1) -> list[dict[str, bool]]:
    groups = defaultdict(list)
    base_presence = defaultdict(bool)

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
            to_remove.update(idx for idx, _, _ in entries)
            collapsed = dict(sig)
            collapsed[base] = True
            replacements.append(collapsed)

    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def remove_base_if_ge_present(dicts: list[dict[str, bool]]) -> list[dict[str, bool]]:
    cleaned = []
    for d in dicts:
        ge_bases = {k.split("_GE")[0] for k in d if "_GE" in k}
        cleaned.append({k: v for k, v in d.items() if (k not in ge_bases) or ("_GE" in k)})
    return cleaned


def merge_full_partition_remove_base(dicts: list[dict[str, bool]], win_threshold: int = 1) -> list[dict[str, bool]]:
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
                has_base_true[(sig, base)] |= d[base] is True
                has_base_false[(sig, base)] |= d[base] is False

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
            collapsed = dict(sig)
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
        ge_bases = {k.split("_GE")[0] for k in d if "_GE" in k}
        new_d = {k: v for k, v in d.items() if k not in ge_bases}
        cleaned.append(new_d)
    return cleaned


def _flip_base_key(base: str) -> str:
    if ">" in base:
        a, b = base.split(">", 1)
        return f"{b}>{a}"
    return base


def merge_ge_union_unified(dicts: list[dict[str, bool]], win_threshold: int = 1) -> list[dict[str, bool]]:
    """
    For each (signature w/o family, base):
      * collect all GE intervals across dicts that have that GE family
      * if any dict in the group has explicit base key, skip (to avoid mixing)
      * if the union is a single interval:
          - if [L, +inf) with L <= win_threshold -> collapse to {base: True}
          - elif [L, U) with finite U -> collapse to {base_GEL: True, base_GEU: False}
    Replace all dicts in that group with the collapsed one.
    """
    groups = defaultdict(list)
    base_presence = defaultdict(bool)

    for idx, d in enumerate(dicts):
        ge_bases = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
        explicit_bases = {k for k in d if "_GE" not in k and isinstance(d[k], bool)}

        for base in ge_bases | explicit_bases:
            sig = _signature_without_family(d, base)
            if base in d:
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
            continue
        if base_presence.get((sig, base), False):
            continue

        intervals = [iv for _, _, iv in entries]
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

        if len(merged) != 1:
            continue

        L, R = merged[0]
        collapsed = dict(sig)

        if R == math.inf and L <= win_threshold:
            collapsed[base] = True
        elif R != math.inf and L != -math.inf:
            collapsed[f"{base}_GE{int(L)}"] = True
            collapsed[f"{base}_GE{int(R)}"] = False
        else:
            continue

        to_remove.update(idx for idx, _, _ in entries)
        replacements.append(collapsed)

    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def merge_ge_union_by_signature(
    dicts: list[dict[str, bool]],
    win_threshold: int = 1,
    aggressive_upper: bool = True,
) -> list[dict[str, bool]]:
    """
    For each signature (same non-GE keys/values), consider all bases that appear as GE families.
    For each base, union its GE intervals across the signature's dicts, then collapse.
    """

    def pure_signature(d: dict[str, bool]) -> tuple[tuple[str, bool], ...]:
        items = [(k, v) for k, v in d.items() if "_GE" not in k and not isinstance(v, dict) and isinstance(v, bool)]
        items.sort()
        return tuple(items)

    sig_to_indices = defaultdict(list)
    for i, d in enumerate(dicts):
        sig_to_indices[pure_signature(d)].append(i)

    to_remove = set()
    replacements = []

    for sig, idxs in sig_to_indices.items():
        bases = set()
        base_explicit_present = defaultdict(bool)
        base_intervals = defaultdict(list)

        for i in idxs:
            d = dicts[i]
            ge_bases = {parsed[0] for k in d for parsed in (_parse_ge_key(k),) if parsed}
            for k in d:
                if "_GE" not in k and isinstance(d[k], bool):
                    base_explicit_present[k] |= True
            for base in ge_bases:
                bases.add(base)
                lo, hi = _interval_for_family(d, base)
                if lo < hi:
                    base_intervals[base].append((lo, hi))

        any_collapsed = False
        collapsed_parts: dict[str, dict[str, bool]] = {}

        for base in bases:
            if base_explicit_present.get(base, False):
                continue
            intervals = base_intervals.get(base, [])
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

            part: dict[str, bool] = {}
            if len(merged) == 1:
                L, R = merged[0]
                if R == math.inf and L <= win_threshold:
                    part[base] = True
                elif R != math.inf and L != -math.inf:
                    part[f"{base}_GE{int(L)}"] = True
                    part[f"{base}_GE{int(R)}"] = False
                elif R == math.inf and aggressive_upper:
                    part[f"{base}_GE{int(L)}"] = True
            else:
                if aggressive_upper and any(r == math.inf for _, r in merged):
                    l_min = min(L for (L, _) in merged if L != -math.inf)
                    part[f"{base}_GE{int(l_min)}"] = True
                else:
                    part = {}

            if part:
                collapsed_parts[base] = part
                any_collapsed = True

        if not any_collapsed:
            continue

        collapsed = dict(sig)
        for base in sorted(collapsed_parts.keys()):
            collapsed.update(collapsed_parts[base])

        to_remove.update(idxs)
        replacements.append(collapsed)

    out = [d for i, d in enumerate(dicts) if i not in to_remove]
    seen = set()
    for d in replacements:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def final_consolidation(minimized_scenarios):
    consolidated = minimized_scenarios

    values_by_key = {}
    for d in consolidated:
        for k, v in d.items():
            values_by_key.setdefault(k, set()).add(v)

    contradictory_keys = {k for k, vals in values_by_key.items() if len(vals) > 1}

    result = []
    seen = set()
    for d in consolidated:
        new_d = {k: v for k, v in d.items() if k not in contradictory_keys}
        if new_d:
            sig = tuple(sorted(new_d.items()))
            if sig not in seen:
                seen.add(sig)
                result.append(new_d)
    return result


def consolidate_all(dicts: list[dict[str, bool]], debug: bool = False) -> list[dict[str, bool]]:
    """Run all consolidation passes over a list of scenario minterms."""
    if debug:
        print("=== Starting full consolidation ===")
        print(f"Initial dicts ({len(dicts)}):")
        for d in dicts:
            print(f"  {d}")

    step05 = remove_base_if_ge_present_in_dicts(dicts)
    if debug:
        print(f"After remove_base_if_ge_present_in_dicts ({len(step05)}):")
        for d in step05:
            print(f"  {d}")

    step0 = consolidate_opposites_and_remove_bases(step05)
    if debug:
        print(f"After consolidate_opposites_and_remove_bases ({len(step0)}):")
        for d in step0:
            print(f"  {d}")

    step1 = consolidate_opposites(step0)
    if debug:
        print(f"After consolidate_opposites ({len(step1)}):")
        for d in step1:
            print(f"  {d}")

    step2 = merge_ge_intervals_to_base_safe(step1, win_threshold=1)
    if debug:
        print(f"After merge_ge_intervals_to_base_safe ({len(step2)}):")
        for d in step2:
            print(f"  {d}")

    step3 = remove_base_if_ge_present(step2)
    if debug:
        print(f"After remove_base_if_ge_present ({len(step3)}):")
        for d in step3:
            print(f"  {d}")

    step3u = merge_ge_union_by_signature(step3)
    if debug:
        print(f"After merge_ge_union_by_signature ({len(step3u)}):")
        for d in step3u:
            print(f"  {d}")

    step4 = merge_full_partition_remove_base(step3u, win_threshold=1)
    if debug:
        print(f"After merge_full_partition_remove_base ({len(step4)}):")
        for d in step4:
            print(f"  {d}")

    seen, out = set(), []
    for d in step4:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def minimize_minterms(minterms, allow_combine=True):
    """
    Simplify minterms by absorption (always) and optionally by one-variable combination.
    With allow_combine=True, we combine only when the differing variable's matchup
    is ALSO represented by another variable in BOTH terms (so we don't erase that matchup).
    """
    terms = {frozenset(m.items()) for m in minterms}

    def _matchup_of(var: str) -> str:
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

        to_remove = set()
        lst = list(terms)
        for i, a in enumerate(lst):
            for j, b in enumerate(lst):
                if i != j and a.issuperset(b):
                    to_remove.add(a)
        if to_remove:
            terms -= to_remove

        if allow_combine:
            lst = list(terms)
            n = len(lst)
            merged = set()
            used = [False] * n

            from collections import Counter

            term_matchup_counts = [Counter(_matchup_of(k) for k in dict(t).keys()) for t in lst]

            for i in range(n):
                for j in range(i + 1, n):
                    a = lst[i]
                    b = lst[j]
                    da = dict(a)
                    db = dict(b)
                    keys = set(da.keys()) | set(db.keys())
                    diffs = [k for k in keys if da.get(k) != db.get(k)]
                    if len(diffs) == 1:
                        k = diffs[0]
                        mk = _matchup_of(k)
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

        changed = len(terms) != before

    return [dict(t) for t in terms]


# -------------------------
# Scenario enumeration
# -------------------------


def determine_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    debug: bool = False,
):
    """
    Determine all possible seeding scenarios for the given teams,
    based on completed and remaining games.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger("scenarios")
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

    num_remaining = len(remaining)

    first_counts: Counter = Counter()
    second_counts: Counter = Counter()
    third_counts: Counter = Counter()
    fourth_counts: Counter = Counter()

    scenario_minterms: dict[str, dict[int, list[dict[str, bool]]]] = {}

    pa_for_winner = 14
    base_margins = {(rem_game.a, rem_game.b): 7 for rem_game in remaining}

    boolean_game_vars = []
    for rem_game in remaining:
        var_name = f"{rem_game.a}>{rem_game.b}"
        boolean_game_vars.append((var_name, rem_game.a, rem_game.b))

    logger.info(f"Boolean Game Vars: {boolean_game_vars}")

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

    else:
        total_masks = 1 << num_remaining
        for outcome_mask in range(total_masks):
            var_assignment = {}
            for bit_index, (var_name, team_a, team_b) in enumerate(boolean_game_vars):
                bit_value = (outcome_mask >> bit_index) & 1
                var_assignment[var_name] = bool(bit_value)

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
            rem_idx = {(rg.a, rg.b): i for i, rg in enumerate(remaining)}

            thresholds_dir = {}
            if intra_bucket_games:
                for rem_game in intra_bucket_games:
                    a, b = rem_game.a, rem_game.b
                    idx = rem_idx[(a, b)]
                    for winner in (a, b):
                        current_bit = (outcome_mask >> idx) & 1
                        want_bit = 1 if winner == a else 0
                        mask_for_dir = outcome_mask if current_bit == want_bit else (outcome_mask ^ (1 << idx))

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
                            orders_by_m.append(tuple(test_order))

                        change_points = []
                        for m in range(2, 13):
                            if orders_by_m[m - 1] != orders_by_m[m - 2]:
                                change_points.append(m)

                        thresholds_dir[((a, b), winner)] = change_points
                        logger.debug(f"[DEBUG THRESH] Pair {a} vs {b}, dir winner={winner}: thresholds={change_points}")

            if not intra_bucket_games:
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
                interval_specs = []
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
                    for interval_combo in product(*[spec[2] for spec in interval_specs]):
                        branch_margins = dict(base_margins)
                        branch_assignment = dict(var_assignment)
                        branch_weight = 1.0

                        for ((a, b), winner, intervals_for_pair), (lo, hi) in zip(interval_specs, interval_combo):
                            chosen_m = lo
                            branch_margins[(a, b)] = chosen_m

                            opp = b if winner == a else a
                            ge_lo_key = f"{winner}>{opp}_GE{lo}"
                            branch_assignment[ge_lo_key] = True
                            if hi <= 12:
                                ge_hi_key = f"{winner}>{opp}_GE{hi}"
                                branch_assignment[ge_hi_key] = False

                            branch_weight *= (hi - lo) / 12.0

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

        denom = float(1 << num_remaining)

    def simplify_matchups(dicts):
        simplified = []
        for d in dicts:
            keys = set(d.keys())
            has_margin_variant = set()
            for k in keys:
                if "_GE" in k:
                    base = k.split("_GE", 1)[0]
                    has_margin_variant.add(base)
                    a, b = base.split(">", 1)
                    has_margin_variant.add(f"{b}>{a}")
            new_d = {k: v for k, v in d.items() if not (("_GE" not in k) and (k in has_margin_variant))}
            simplified.append(new_d)
        return simplified

    minimized_scenarios: defaultdict = defaultdict(dict)
    for team, seed_map in scenario_minterms.items():
        for seed_num, minterms in seed_map.items():
            mins = [dict(m) for m in minterms]
            consolidated_scenarios = consolidate_all(mins, debug=debug)
            simplified_scenarios = simplify_matchups(consolidated_scenarios)
            minimized_mins = minimize_minterms(simplified_scenarios, allow_combine=True)
            sorted_mins: list[dict[str, bool]] = [
                {k: d[k] for k in sorted(d)} for d in sorted(minimized_mins, key=lambda x: len(x))
            ]
            minimized_scenarios[team][seed_num] = sorted_mins

    return first_counts, second_counts, third_counts, fourth_counts, denom, minimized_scenarios


def determine_odds(teams, first_counts, second_counts, third_counts, fourth_counts, denom):
    """Determine final odds from accumulated counts."""
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
