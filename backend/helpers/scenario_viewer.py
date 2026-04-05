"""Enumerate and render complete seeding outcomes for a division.

For a given division (teams + completed + remaining games), enumerates every
distinct seeding outcome and the game conditions that produce it.  Scenarios
that are identical regardless of one game's winner automatically omit that
game from the conditions.  Margin-sensitive masks (where winning margins change
the seeding) are presented as lettered sub-scenarios (6a, 6b, …).
"""

from collections import defaultdict
from itertools import product

from backend.helpers.data_classes import CompletedGame, GameResult, RemainingGame
from backend.helpers.scenario_renderer import _render_atom
from backend.helpers.tiebreakers import resolve_standings_for_mask

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _game_winners_for_mask(mask: int, remaining: list[RemainingGame]) -> list[tuple[str, str]]:
    """Return (winner, loser) pairs for every remaining game under *mask*."""
    result = []
    for i, rg in enumerate(remaining):
        if (mask >> i) & 1:
            result.append((rg.a, rg.b))
        else:
            result.append((rg.b, rg.a))
    return result


def _common_game_winners(masks: list[int], remaining: list[RemainingGame]) -> list[tuple[str, str]]:
    """Return (winner, loser) only for games whose winner is constant across *masks*.

    Games whose winner varies across masks are omitted — they are irrelevant
    to the seeding for this group.
    """
    result = []
    for i, rg in enumerate(remaining):
        bits = {(m >> i) & 1 for m in masks}
        if len(bits) == 1:
            if list(bits)[0] == 1:
                result.append((rg.a, rg.b))
            else:
                result.append((rg.b, rg.a))
    return result


def _find_combined_atom(
    seeding: tuple[str, ...],
    playoff_seeds: int,
    mask: int,
    sample_margins: dict,
    scenario_atoms: dict,
    remaining: list[RemainingGame],
) -> list | None:
    """Build the most specific condition set by intersecting atoms for all seeded teams.

    For each team at its seeded position, finds the matching atom from *scenario_atoms*
    and merges the conditions:
    - GameResult: for the same game pair, keeps the most restrictive margin range.
    - MarginCondition: for the same (add, sub, op direction), keeps the tightest threshold.

    Returns the merged atom, or None if no atoms are found.
    """
    from backend.helpers.data_classes import GameResult, MarginCondition

    # game pair (canonical sorted tuple) -> most specific GameResult
    game_conds: dict[tuple, GameResult] = {}
    # (add, sub, direction) -> tightest threshold; direction is "le" or "ge"
    margin_conds: dict[tuple, tuple] = {}  # key -> (op, threshold)

    found_any = False
    for seed_idx in range(min(playoff_seeds, len(seeding))):
        team = seeding[seed_idx]
        seed = seed_idx + 1
        atom = next(
            (
                a
                for a in scenario_atoms.get(team, {}).get(seed, [])
                if all(cond.satisfied_by(mask, sample_margins, remaining) for cond in a)
            ),
            None,
        )
        if atom is None:
            continue
        found_any = True

        for cond in atom:
            if isinstance(cond, GameResult):
                pair = tuple(sorted([cond.winner, cond.loser]))
                if pair not in game_conds:
                    game_conds[pair] = cond
                else:
                    existing = game_conds[pair]
                    new_min = max(existing.min_margin, cond.min_margin)
                    e_max, c_max = existing.max_margin, cond.max_margin
                    if e_max is None and c_max is None:
                        new_max = None
                    elif e_max is None:
                        new_max = c_max
                    elif c_max is None:
                        new_max = e_max
                    else:
                        new_max = min(e_max, c_max)
                    game_conds[pair] = GameResult(cond.winner, cond.loser, new_min, new_max)

            elif isinstance(cond, MarginCondition):
                t = cond.threshold
                if cond.op == "<":
                    t -= 1
                elif cond.op == ">":
                    t += 1
                # "==" contributes both a ge and le constraint so the
                # reconstruction below can collapse them back to "==".
                directions: list[str] = []
                if cond.op == "==":
                    directions = ["ge", "le"]
                elif cond.op in ("<=", "<"):
                    directions = ["le"]
                else:
                    directions = ["ge"]
                for direction in directions:
                    key = (cond.add, cond.sub, direction)
                    normalised_op = "<=" if direction == "le" else ">="
                    if key not in margin_conds:
                        margin_conds[key] = (normalised_op, t)
                    else:
                        _, existing_t = margin_conds[key]
                        # Keep tightest: for <=, smaller is tighter; for >=, larger is tighter
                        if direction == "le":
                            margin_conds[key] = (normalised_op, min(existing_t, t))
                        else:
                            margin_conds[key] = (normalised_op, max(existing_t, t))

    if not found_any:
        return None

    # Reconstruct the atom: game conditions in remaining-game order, then margin conditions.
    # Simplify: if ge(N) and le(N) exist for the same (add, sub) key, collapse to "=="
    from backend.helpers.data_classes import MarginCondition

    # Group margin conditions by (add, sub) to detect exact-value pairs
    by_pair: dict[tuple, dict[str, int]] = {}
    for (add, sub, direction), (op, t) in margin_conds.items():
        key2 = (add, sub)
        by_pair.setdefault(key2, {})[direction] = t

    result: list = []
    for rg in remaining:
        pair = tuple(sorted([rg.a, rg.b]))
        if pair in game_conds:
            result.append(game_conds[pair])

    for (add, sub), dirs in by_pair.items():
        ge_t = dirs.get("ge")
        le_t = dirs.get("le")
        if ge_t is not None and le_t is not None and ge_t == le_t:
            result.append(MarginCondition(add=add, sub=sub, op="==", threshold=ge_t))
        else:
            if ge_t is not None:
                result.append(MarginCondition(add=add, sub=sub, op=">=", threshold=ge_t))
            if le_t is not None:
                result.append(MarginCondition(add=add, sub=sub, op="<=", threshold=le_t))

    return result


# ---------------------------------------------------------------------------
# Atom builder — internal helpers
# ---------------------------------------------------------------------------



def _eval_mc(mc, margins: dict) -> bool:
    """Evaluate a MarginCondition against a margins dict keyed by (team_a, team_b) pairs."""
    val = sum(margins[p] for p in mc.add) - sum(margins[p] for p in mc.sub)
    if mc.op == "<=":
        return val <= mc.threshold
    if mc.op == ">=":
        return val >= mc.threshold
    if mc.op == "==":
        return val == mc.threshold
    return True


def _split_non_rectangular_atom(
    mask: int,
    valid_margins_list: list[dict],
    remaining,
    pairs: list[tuple[str, str]],
    lows: list[int],
    highs: list[int],
    base_atom: list,
) -> list[list] | None:
    """Split a non-rectangular valid margin set into multiple rectangular atoms.

    Iterates over all pairs of game indices.  For the first pair whose joint 2-D
    margin distribution is non-rectangular, groups the first game's margin values
    by the set of valid second-game margins they allow, and returns one atom per
    group.  Both groups must form contiguous ranges for the split to succeed.

    Returns a list of atoms (each a list of GameResult objects) on success,
    or None when no valid split is found.
    """
    from backend.helpers.data_classes import GameResult

    R = len(remaining)

    for i0 in range(R):
        for i1 in range(i0 + 1, R):
            valid_2d = {
                (m[pairs[i0]], m[pairs[i1]])
                for m in valid_margins_list
            }
            prod_2d = (highs[i0] - lows[i0] + 1) * (highs[i1] - lows[i1] + 1)
            if len(valid_2d) == prod_2d:
                continue  # Rectangular for this pair — try the next

            # Group i0 margin values by the frozenset of valid i1 margins
            game1_by_game0: dict[int, frozenset] = {
                s: frozenset(p for (s2, p) in valid_2d if s2 == s)
                for s in range(lows[i0], highs[i0] + 1)
            }
            range_to_game0: dict[frozenset, list[int]] = {}
            for s, p_set in game1_by_game0.items():
                range_to_game0.setdefault(p_set, []).append(s)

            sub_atoms: list[list] = []
            valid_split = True
            for p_set, s_list in range_to_game0.items():
                s_sorted = sorted(s_list)
                p_sorted = sorted(p_set)
                # Both groups must be contiguous integer ranges
                if s_sorted != list(range(s_sorted[0], s_sorted[-1] + 1)):
                    valid_split = False
                    break
                if p_sorted != list(range(p_sorted[0], p_sorted[-1] + 1)):
                    valid_split = False
                    break

                s_lo, s_hi = s_sorted[0], s_sorted[-1]
                p_lo, p_hi = p_sorted[0], p_sorted[-1]

                sub_atom = list(base_atom)

                a_wins_0 = bool((mask >> i0) & 1)
                winner_0 = remaining[i0].a if a_wins_0 else remaining[i0].b
                loser_0 = remaining[i0].b if a_wins_0 else remaining[i0].a
                max_s = s_hi + 1 if s_hi < 12 else None
                sub_atom[i0] = GameResult(winner_0, loser_0, min_margin=s_lo, max_margin=max_s)

                a_wins_1 = bool((mask >> i1) & 1)
                winner_1 = remaining[i1].a if a_wins_1 else remaining[i1].b
                loser_1 = remaining[i1].b if a_wins_1 else remaining[i1].a
                max_p = p_hi + 1 if p_hi < 12 else None
                sub_atom[i1] = GameResult(winner_1, loser_1, min_margin=p_lo, max_margin=max_p)

                sub_atoms.append(sub_atom)

            if valid_split and len(sub_atoms) > 1:
                return sub_atoms

            # Forward grouping failed — try reverse: group i1 values by i0 frozenset
            game0_by_game1: dict[int, frozenset] = {
                p: frozenset(s for (s, p2) in valid_2d if p2 == p)
                for p in range(lows[i1], highs[i1] + 1)
            }
            range_to_game1: dict[frozenset, list[int]] = {}
            for p, s_set in game0_by_game1.items():
                range_to_game1.setdefault(s_set, []).append(p)

            sub_atoms_rev: list[list] = []
            valid_split_rev = True
            for s_set, p_list in range_to_game1.items():
                p_sorted = sorted(p_list)
                s_sorted = sorted(s_set)
                if p_sorted != list(range(p_sorted[0], p_sorted[-1] + 1)):
                    valid_split_rev = False
                    break
                if s_sorted != list(range(s_sorted[0], s_sorted[-1] + 1)):
                    valid_split_rev = False
                    break

                p_lo, p_hi = p_sorted[0], p_sorted[-1]
                s_lo, s_hi = s_sorted[0], s_sorted[-1]

                sub_atom = list(base_atom)

                a_wins_0 = bool((mask >> i0) & 1)
                winner_0 = remaining[i0].a if a_wins_0 else remaining[i0].b
                loser_0 = remaining[i0].b if a_wins_0 else remaining[i0].a
                max_s = s_hi + 1 if s_hi < 12 else None
                sub_atom[i0] = GameResult(winner_0, loser_0, min_margin=s_lo, max_margin=max_s)

                a_wins_1 = bool((mask >> i1) & 1)
                winner_1 = remaining[i1].a if a_wins_1 else remaining[i1].b
                loser_1 = remaining[i1].b if a_wins_1 else remaining[i1].a
                max_p = p_hi + 1 if p_hi < 12 else None
                sub_atom[i1] = GameResult(winner_1, loser_1, min_margin=p_lo, max_margin=max_p)

                sub_atoms_rev.append(sub_atom)

            if valid_split_rev and len(sub_atoms_rev) > 1:
                return sub_atoms_rev

    return None


def _derive_atom(
    mask: int,
    valid_margins_list: list[dict],
    remaining: list[RemainingGame],
    pairs: list[tuple[str, str]],
) -> list[list]:
    """Derive human-readable atoms (GameResult + MarginCondition lists) for a (mask, seeding) group.

    Algorithm:
    1. Compute per-game margin ranges ``[lo_i, hi_i]`` from the valid margin set.
    2. Build a ``GameResult`` for each game using the derived range.
    2b. If the valid set is non-rectangular (product of per-game ranges > count),
        split into multiple rectangular sub-atoms via ``_split_non_rectangular_atom``.
    3. Find margin-sensitive game indices (range is a proper subset of ``[1,12]``).
    4. If exactly 2 margin-sensitive games, try to add sum/diff ``MarginCondition``
       objects that tighten the description and verify they reproduce the valid set.
    5. Fall back to per-game ranges only if joint constraints cannot be verified.

    Returns a list of atoms, each atom being a list of ``GameResult`` and
    (optionally) ``MarginCondition`` objects.
    """
    from backend.helpers.data_classes import GameResult, MarginCondition

    R = len(remaining)

    # --- Step 1: per-game ranges ---
    lows = [12] * R
    highs = [1] * R
    for margins in valid_margins_list:
        for i, pair in enumerate(pairs):
            m = margins[pair]
            lows[i] = min(lows[i], m)
            highs[i] = max(highs[i], m)

    # --- Step 2: build GameResult list ---
    atom: list = []
    for i, rg in enumerate(remaining):
        a_wins = bool((mask >> i) & 1)
        winner = rg.a if a_wins else rg.b
        loser = rg.b if a_wins else rg.a
        lo, hi = lows[i], highs[i]
        # max_margin is exclusive upper bound; None means unbounded (= 12)
        max_m = hi + 1 if hi < 12 else None
        atom.append(GameResult(winner, loser, min_margin=lo, max_margin=max_m))

    # --- Step 2b: compute non-rectangularity for later use ---
    product_of_ranges = 1
    for lo, hi in zip(lows, highs):
        product_of_ranges *= hi - lo + 1
    non_rectangular = len(valid_margins_list) < product_of_ranges

    # --- Step 3: find margin-sensitive game indices ---
    sens_indices = [i for i in range(R) if not (lows[i] == 1 and highs[i] == 12)]

    if len(sens_indices) != 2:
        # Joint constraints only attempted for exactly 2 sensitive games.
        # For non-rectangular sets here, try to split into exact sub-atoms.
        if non_rectangular:
            split = _split_non_rectangular_atom(
                mask, valid_margins_list, remaining, pairs, lows, highs, atom
            )
            if split is not None:
                return split
        return [atom]

    i0, i1 = sens_indices
    pair0, pair1 = pairs[i0], pairs[i1]

    # Project to 2-D valid set
    valid_2d: set[tuple[int, int]] = {
        (margins[pair0], margins[pair1])
        for margins in valid_margins_list
    }

    # --- Step 4: detect binding sum / diff constraints ---
    sums = [v0 + v1 for v0, v1 in valid_2d]
    diffs = [v0 - v1 for v0, v1 in valid_2d]  # game[i0] - game[i1]

    min_sum, max_sum = min(sums), max(sums)
    min_diff, max_diff = min(diffs), max(diffs)

    # Theoretical extremes given per-game ranges
    lo0, hi0 = lows[i0], highs[i0]
    lo1, hi1 = lows[i1], highs[i1]
    max_possible_sum = hi0 + hi1
    min_possible_sum = lo0 + lo1
    max_possible_diff = hi0 - lo1
    min_possible_diff = lo0 - hi1

    margin_conds: list = []

    # Sum constraints — collapse to "==" when both bounds are binding and equal
    sum_lo_binding = min_sum > min_possible_sum
    sum_hi_binding = max_sum < max_possible_sum
    if sum_lo_binding and sum_hi_binding and min_sum == max_sum:
        margin_conds.append(MarginCondition(add=(pair0, pair1), sub=(), op="==", threshold=min_sum))
    else:
        if sum_hi_binding:
            margin_conds.append(MarginCondition(add=(pair0, pair1), sub=(), op="<=", threshold=max_sum))
        if sum_lo_binding:
            margin_conds.append(MarginCondition(add=(pair0, pair1), sub=(), op=">=", threshold=min_sum))

    # Diff constraints — collapse to "==" when both bounds are binding and equal
    diff_lo_binding = min_diff > min_possible_diff
    diff_hi_binding = max_diff < max_possible_diff
    if diff_lo_binding and diff_hi_binding and min_diff == max_diff:
        margin_conds.append(MarginCondition(add=(pair0,), sub=(pair1,), op="==", threshold=min_diff))
    else:
        if diff_hi_binding:
            margin_conds.append(MarginCondition(add=(pair0,), sub=(pair1,), op="<=", threshold=max_diff))
        if diff_lo_binding:
            margin_conds.append(MarginCondition(add=(pair0,), sub=(pair1,), op=">=", threshold=min_diff))

    if not margin_conds:
        # No joint constraints needed — per-game ranges fully describe the set
        return [atom]

    # --- Step 5: verify constraints reproduce the valid set ---
    # First, try [1,12]×[1,12] bounds — if joint constraints alone are sufficient,
    # drop the per-game bounds entirely for a cleaner representation.
    predicted_full = _predict_valid_set_2d(1, 12, 1, 12, margin_conds, pair0, pair1)
    if predicted_full == valid_2d:
        # Per-game bounds are redundant; rebuild atom with unconstrained GameResults
        unconstrained_atom: list = []
        for i, rg in enumerate(remaining):
            a_wins = bool((mask >> i) & 1)
            winner = rg.a if a_wins else rg.b
            loser = rg.b if a_wins else rg.a
            unconstrained_atom.append(GameResult(winner, loser, 1, None))
        return [unconstrained_atom + margin_conds]

    predicted = _predict_valid_set_2d(lo0, hi0, lo1, hi1, margin_conds, pair0, pair1)

    if predicted == valid_2d:
        return [atom + margin_conds]

    # Joint constraints couldn't describe the valid set exactly.
    # For non-rectangular valid sets, try splitting into multiple exact sub-atoms.
    if non_rectangular:
        split = _split_non_rectangular_atom(
            mask, valid_margins_list, remaining, pairs, lows, highs, atom
        )
        if split is not None:
            return split

    # Fallback: per-game ranges only (always a superset; _find_combined_atom
    # uses sample_margins to select the right atom anyway)
    return [atom]


def _predict_valid_set_2d(
    lo0: int, hi0: int,
    lo1: int, hi1: int,
    margin_conds: list,
    pair0: tuple[str, str],
    pair1: tuple[str, str],
) -> set[tuple[int, int]]:
    """Return the set of (v0, v1) pairs satisfying per-game ranges and MarginConditions."""
    valid: set[tuple[int, int]] = set()
    for v0 in range(lo0, hi0 + 1):
        for v1 in range(lo1, hi1 + 1):
            margins = {pair0: v0, pair1: v1}
            if all(_eval_mc(mc, margins) for mc in margin_conds):
                valid.add((v0, v1))
    return valid


def _simplify_atom_list(atoms: list[list]) -> list[list]:
    """Minimise a list of atoms using two boolean-simplification rules.

    Applies the two rules iteratively until no further reduction is possible.

    Rule 1 — Margin collapse:
        Two atoms that are identical in every condition except that one game's
        ``GameResult`` has adjacent or overlapping margin ranges (and the same
        winner) are merged into a single atom whose margin range is the union of
        the two.  After enough iterations, ranges that together span [1, 12]
        collapse to an unconstrained ``GameResult`` (``min_margin=1``,
        ``max_margin=None``).

    Rule 2 — Game elimination:
        Two atoms that are identical except that one game appears with opposite
        winners in the two atoms, and no ``MarginCondition`` in either atom
        references that game pair, are merged by dropping that game condition
        entirely.  If this leaves an empty condition list the result is
        ``[[]]`` — an unconditional atom that subsumes all others.

    Args:
        atoms: List of atoms, each atom being a list of ``GameResult`` /
               ``MarginCondition`` objects.

    Returns:
        A simplified list of atoms.  May be shorter than the input.
        Returns ``[[]]`` if any atom collapses to unconditional.
    """
    from backend.helpers.data_classes import GameResult, MarginCondition

    def _pair(c: GameResult) -> tuple:
        """Return a canonical (sorted) team-pair key for a GameResult."""
        return tuple(sorted([c.winner, c.loser]))

    def _mc_key(mc: MarginCondition):
        """Return a hashable identity key for a MarginCondition."""
        return (mc.add, mc.sub, mc.op, mc.threshold)

    def _try_merge(a: list, b: list) -> list | None:
        """Return a merged atom if a and b can be simplified in one step, else None."""
        gr_a: dict[tuple, GameResult] = {}
        gr_b: dict[tuple, GameResult] = {}
        mc_a: list = []
        mc_b: list = []
        order: list = []  # ('gr', pair) or ('mc', index) — preserves atom-a structure

        for c in a:
            if isinstance(c, GameResult):
                p = _pair(c)
                gr_a[p] = c
                order.append(("gr", p))
            else:
                mc_a.append(c)
                order.append(("mc", len(mc_a) - 1))

        for c in b:
            if isinstance(c, GameResult):
                gr_b[_pair(c)] = c
            else:
                mc_b.append(c)

        # MarginConditions must be identical in both atoms
        if len(mc_a) != len(mc_b) or any(_mc_key(x) != _mc_key(y) for x, y in zip(mc_a, mc_b)):
            return None

        # Same set of game pairs required
        if set(gr_a) != set(gr_b):
            return None

        diff = [p for p in gr_a if gr_a[p] != gr_b[p]]
        if len(diff) != 1:
            return None  # 0 = already identical; 2+ = can't reduce in one step

        p = diff[0]
        ca, cb = gr_a[p], gr_b[p]

        # --- Rule 1: same winner, adjacent / overlapping margin ranges ---
        if ca.winner == cb.winner:
            lo = min(ca.min_margin, cb.min_margin)
            a_hi = ca.max_margin  # exclusive upper bound; None = unbounded
            b_hi = cb.max_margin
            # Sort ranges by start so we can check adjacency
            if ca.min_margin <= cb.min_margin:
                first_hi, second_lo = a_hi, cb.min_margin
            else:
                first_hi, second_lo = b_hi, ca.min_margin
            # Ranges must be adjacent or overlapping (no gap)
            if first_hi is not None and second_lo > first_hi:
                return None
            hi = None if (a_hi is None or b_hi is None) else max(a_hi, b_hi)
            merged_gr = GameResult(ca.winner, ca.loser, lo, hi)
            result = []
            for kind, val in order:
                if kind == "gr" and val == p:
                    result.append(merged_gr)
                elif kind == "gr":
                    result.append(gr_a[val])
                else:
                    result.append(mc_a[val])
            return result

        # --- Rule 2: opposite winners, no MarginCondition references this game ---
        # Both conditions must be fully unconstrained (min=1, max=None) — i.e. together
        # they cover ALL outcomes of this game.  A margin qualifier on either side means
        # one range of outcomes is still excluded, so the game cannot be dropped.
        if ca.loser == cb.winner:
            if ca.min_margin != 1 or ca.max_margin is not None:
                return None
            if cb.min_margin != 1 or cb.max_margin is not None:
                return None
            for mc in mc_a:
                if p in mc.add or p in mc.sub:
                    return None
            return [
                (gr_a[val] if kind == "gr" else mc_a[val])
                for kind, val in order
                if not (kind == "gr" and val == p)
            ]

        return None

    def _subsumes(a: list, b: list) -> bool:
        """Return True if atom *a* subsumes atom *b* (b can be dropped when a exists).

        a subsumes b when every assignment satisfying b also satisfies a.  This
        holds when:
          - Every game pair in a also appears in b with the same winner.
          - a's margin range for that game is a superset of (weaker than) b's range:
            a.min_margin <= b.min_margin and (a.max_margin is None or a.max_margin >= b.max_margin).
          - b may have additional conditions that a does not (making b strictly tighter).
          - a has no MarginConditions (not needed for current use cases).
        """
        if not a:  # unconditional atom subsumes everything
            return True
        if any(not isinstance(c, GameResult) for c in a):
            return False  # MarginConditions in a: skip
        gr_a = {_pair(c): c for c in a}
        gr_b = {_pair(c): c for c in b if isinstance(c, GameResult)}
        if not set(gr_a).issubset(set(gr_b)):
            return False
        for p in gr_a:
            ca, cb = gr_a[p], gr_b[p]
            if ca.winner != cb.winner:
                return False
            if ca.min_margin > cb.min_margin:
                return False
            if ca.max_margin is not None:
                if cb.max_margin is None or ca.max_margin < cb.max_margin:
                    return False
        return True

    def _try_rule3(a: list, b: list) -> list | None:
        """Rule 3 — Complementary lifting.

        If atoms a and b share identical conditions except for two game pairs —
        one complementary (X_a / X_b, opposite unconstrained winners) and one
        tightening (G(lo) in a, G(hi) in b with lo < hi) — then b can be
        replaced with [G(hi)] plus all shared (non-diff) conditions.

        Correctness: for any shared conditions R,
          (X_a ∧ G_lo+ ∧ R) ∨ (X_b ∧ G_hi+ ∧ R)
          = R ∧ ((X_a ∧ G_lo+) ∨ (X_b ∧ G_hi+))
          = R ∧ (G_hi+ ∨ (X_a ∧ G_lo+))
          = (G_hi+ ∧ R) ∨ (X_a ∧ G_lo+ ∧ R)

        The simplified form makes it clear that G winning by hi+ (plus the
        shared conditions R) is sufficient regardless of which team wins X.
        """
        gr_a = {_pair(c): c for c in a if isinstance(c, GameResult)}
        gr_b = {_pair(c): c for c in b if isinstance(c, GameResult)}

        if set(gr_a) != set(gr_b):
            return None
        # No MarginConditions in either atom (not needed for current use cases)
        if any(not isinstance(c, GameResult) for c in a):
            return None
        if any(not isinstance(c, GameResult) for c in b):
            return None

        diff = [p for p in gr_a if gr_a[p] != gr_b[p]]
        if len(diff) != 2:
            return None

        for p_comp, p_tight in [(diff[0], diff[1]), (diff[1], diff[0])]:
            ca_c, cb_c = gr_a[p_comp], gr_b[p_comp]
            ca_t, cb_t = gr_a[p_tight], gr_b[p_tight]

            # Complementary game: opposite winners, both unconstrained
            if ca_c.loser != cb_c.winner:
                continue
            if ca_c.min_margin != 1 or ca_c.max_margin is not None:
                continue
            if cb_c.min_margin != 1 or cb_c.max_margin is not None:
                continue

            # Tightening game: same winner/loser, a is wider (lower min), b is tighter
            if ca_t.winner != cb_t.winner or ca_t.loser != cb_t.loser:
                continue
            if ca_t.min_margin >= cb_t.min_margin:
                continue  # a is not the wider one
            # a must fully cover b's range (a extends to None, or a's max > b's min)
            if ca_t.max_margin is not None and ca_t.max_margin <= cb_t.min_margin:
                continue

            # Preserve shared (non-diff) conditions so the simplified atom
            # remains tight: (G_hi+ ∧ R) rather than just G_hi+.
            shared = [gr_a[p] for p in gr_a if p not in {p_comp, p_tight}]
            return [cb_t] + shared

        return None

    # Iterative minimisation
    changed = True
    while changed:
        changed = False
        # Short-circuit: an unconditional atom subsumes everything
        if any(len(atom) == 0 for atom in atoms):
            return [[]]
        new_atoms: list[list] = []
        used: set[int] = set()
        for i in range(len(atoms)):
            if i in used:
                continue
            found_pair = False
            for j in range(i + 1, len(atoms)):
                if j in used:
                    continue
                merged = _try_merge(atoms[i], atoms[j])
                if merged is not None:
                    new_atoms.append(merged)
                    used.add(i)
                    used.add(j)
                    changed = True
                    found_pair = True
                    break
            if not found_pair:
                new_atoms.append(atoms[i])
        atoms = new_atoms

    # Subsumption: remove any atom strictly subsumed by a simpler atom.
    # One pass is sufficient; subsumption only removes atoms, never adds them.
    dominated = {
        j
        for i in range(len(atoms))
        for j in range(len(atoms))
        if i != j and _subsumes(atoms[i], atoms[j])
    }
    if dominated:
        atoms = [atom for k, atom in enumerate(atoms) if k not in dominated]

    # Rule 3: complementary lifting — separate pass, runs after Rules 1/2
    # Iterates until stable since one application may expose another.
    r3_changed = True
    while r3_changed:
        r3_changed = False
        for i in range(len(atoms)):
            for j in range(len(atoms)):
                if i == j:
                    continue
                new_b = _try_rule3(atoms[i], atoms[j])
                if new_b is not None:
                    atoms = [new_b if k == j else atom for k, atom in enumerate(atoms)]
                    r3_changed = True
                    break
            if r3_changed:
                break

    def _try_rule4(a: list, b: list) -> tuple[list, list] | None:
        """Rule 4 — Range-containment splitting.

        Applies when atoms a and b differ in exactly two game pairs:
          - p_comp: opposite unconstrained winners (a has X_a, b has X_b)
          - p_tight: same winner in both, both starting at min_margin=1,
            but a's range is strictly contained in b's (a.max_margin < b.max_margin,
            where None represents ∞)

        Rewrites:
          (X_a ∧ G[1..M) ∧ R) ∨ (X_b ∧ G[1..N) ∧ R)  [M < N]
        as the equivalent:
          (G[1..M) ∧ R) ∨ (X_b ∧ G[M..N) ∧ R)

        Returns (new_a, new_b) on success, None otherwise.
        """
        gr_a = {_pair(c): c for c in a if isinstance(c, GameResult)}
        gr_b = {_pair(c): c for c in b if isinstance(c, GameResult)}

        if set(gr_a) != set(gr_b):
            return None
        if any(not isinstance(c, GameResult) for c in a):
            return None
        if any(not isinstance(c, GameResult) for c in b):
            return None

        diff = [p for p in gr_a if gr_a[p] != gr_b[p]]
        if len(diff) != 2:
            return None

        for p_comp, p_tight in [(diff[0], diff[1]), (diff[1], diff[0])]:
            ca_c, cb_c = gr_a[p_comp], gr_b[p_comp]
            ca_t, cb_t = gr_a[p_tight], gr_b[p_tight]

            # p_comp: opposite unconstrained winners
            if ca_c.loser != cb_c.winner:
                continue
            if ca_c.min_margin != 1 or ca_c.max_margin is not None:
                continue
            if cb_c.min_margin != 1 or cb_c.max_margin is not None:
                continue

            # p_tight: same winner, both start at 1, a's range strictly contained in b's
            if ca_t.winner != cb_t.winner or ca_t.loser != cb_t.loser:
                continue
            if ca_t.min_margin != 1 or cb_t.min_margin != 1:
                continue
            if ca_t.max_margin is None:
                continue  # a is unbounded — not strictly narrower
            # a.max_margin < b.max_margin (None = ∞)
            if cb_t.max_margin is not None and ca_t.max_margin >= cb_t.max_margin:
                continue

            shared = [gr_a[p] for p in gr_a if p not in {p_comp, p_tight}]

            # new_a: drop p_comp (X result irrelevant when margin is in the narrow range)
            new_a = [ca_t] + shared

            # new_b: keep X_b, narrow p_tight to [a.max_margin, b.max_margin)
            new_tight = GameResult(cb_t.winner, cb_t.loser, ca_t.max_margin, cb_t.max_margin)
            new_b = [cb_c, new_tight] + shared

            return (new_a, new_b)

        return None

    # Rule 4: range-containment splitting — separate pass, runs after Rule 3.
    # Iterates over all ordered (i, j) pairs so both narrow-in-a and narrow-in-b
    # orientations are tried.
    r4_changed = True
    while r4_changed:
        r4_changed = False
        for i in range(len(atoms)):
            for j in range(len(atoms)):
                if i == j:
                    continue
                result = _try_rule4(atoms[i], atoms[j])
                if result is not None:
                    new_a, new_b = result
                    atoms = [
                        (new_a if k == i else (new_b if k == j else atom))
                        for k, atom in enumerate(atoms)
                    ]
                    r4_changed = True
                    break
            if r4_changed:
                break

    # Final subsumption pass — Rule 4 may expose new subsumptions.
    dominated = {
        j
        for i in range(len(atoms))
        for j in range(len(atoms))
        if i != j and _subsumes(atoms[i], atoms[j])
    }
    if dominated:
        atoms = [atom for k, atom in enumerate(atoms) if k not in dominated]

    return atoms


def _valid_merge_groups(unc_masks: list[int], num_games: int) -> list[list[int]]:
    """Partition unconstrained masks into maximal valid merge groups.

    A group is valid when ALL masks satisfying the group's common bit pattern
    are within the unconstrained set.  Splits recursively on the highest
    varying bit so that groups with the most significant game in common are
    kept together (e.g. NWR/Petal outcome groups before Brandon/Meridian).
    """
    if len(unc_masks) <= 1:
        return [unc_masks] if unc_masks else []

    unc_set = set(unc_masks)
    # Find bits constant across all masks in this set
    fixed: dict[int, int] = {}
    for i in range(num_games):
        bits = {(m >> i) & 1 for m in unc_masks}
        if len(bits) == 1:
            fixed[i] = next(iter(bits))

    # Check if all masks satisfying the fixed bits are in unc_set
    all_matching = [m for m in range(1 << num_games) if all((m >> i) & 1 == v for i, v in fixed.items())]
    if set(all_matching) == unc_set:
        return [unc_masks]  # entire set forms one valid group

    # Split on the highest varying bit
    varying = [i for i in range(num_games) if i not in fixed]
    split_bit = max(varying)
    group0 = [m for m in unc_masks if (m >> split_bit) & 1 == 0]
    group1 = [m for m in unc_masks if (m >> split_bit) & 1 == 1]
    return _valid_merge_groups(group0, num_games) + _valid_merge_groups(group1, num_games)


# ---------------------------------------------------------------------------
# Atom sort
# ---------------------------------------------------------------------------


def _sort_atom_list(atoms: list[list], remaining: list[RemainingGame]) -> list[list]:
    """Return *atoms* sorted for deterministic, human-friendly display order.

    Sort key (all ascending):

    1. **Game count** — number of ``GameResult`` objects.  Fewer conditions
       (broader statements) appear first, e.g. "Louisville beats Greenwood"
       before a four-condition margin atom.
    2. **Constrained flag** — atoms where every ``GameResult`` has
       ``min_margin=1`` and ``max_margin=None`` (no margin restriction) sort
       before atoms that carry any margin constraint.
    3. **Winner-pattern tuple** — for each game in ``remaining`` order, encodes
       0 (team-a wins), 1 (team-b wins), or 2 (game absent from this atom).
       Groups atoms with identical game-winner patterns adjacent so that
       margin variants of the same outcome cluster together.
    4. **Min-margin tuple** — minimum margin values across ``GameResult``
       objects in ``remaining`` order; puts tighter lower-bound constraints
       later within a winner-pattern group.
    """
    from backend.helpers.data_classes import MarginCondition

    pairs = [(rg.a, rg.b) for rg in remaining]

    def _key(atom: list):
        game_results = [c for c in atom if isinstance(c, GameResult)]
        n_games = len(game_results)
        is_constrained = any(
            c.max_margin is not None or c.min_margin > 1 for c in game_results
        ) or any(isinstance(c, MarginCondition) for c in atom)
        winner_pattern = []
        for a, b in pairs:
            gr = next(
                (
                    c for c in game_results
                    if (c.winner == a and c.loser == b) or (c.winner == b and c.loser == a)
                ),
                None,
            )
            if gr is None:
                winner_pattern.append(2)
            else:
                winner_pattern.append(0 if gr.winner == a else 1)
        min_margins = tuple(c.min_margin for c in game_results)
        return (n_games, is_constrained, tuple(winner_pattern), min_margins)

    return sorted(atoms, key=_key)


# ---------------------------------------------------------------------------
# Atom builder
# ---------------------------------------------------------------------------


def build_scenario_atoms(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    pa_win: int = 14,
    base_margin_default: int = 7,
    playoff_seeds: int = 4,
) -> dict:
    """Build per-team per-seed scenario atoms by enumerating all 12^R margin combinations.

    For each distinct (outcome_mask, top-N seeding) group, derives the tightest
    human-readable atom by:

    1. Computing the per-game margin ranges ``[lo, hi]`` from all valid margin
       combinations in the group.
    2. Building a ``GameResult`` per game with the derived range.
    3. For groups with exactly 2 margin-sensitive games, detecting binding sum/diff
       constraints and adding ``MarginCondition`` objects when they tighten the
       description and can be verified to reproduce the exact valid set.
    4. For each (team, seed) pair, any mask where team T holds seed S for *all*
       12^R margin combinations is an "always-at-seed" mask.  These masks are
       merged via ``_valid_merge_groups`` into compact game-winner atoms (e.g.
       "Louisville beats Greenwood" collapses 8 masks into one atom).  Constrained
       atoms from Step 3 are only emitted for teams whose (team, seed) is not
       already covered by an always-at-seed atom.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        pa_win: Points-allowed value assigned to the winner in simulated games.
        base_margin_default: Default margin used when no specific margin is set.
        playoff_seeds: Number of playoff seeds (default 4).

    Returns:
        ``dict[team → dict[seed → list[list[GameResult | MarginCondition]]]]`` —
        the scenario atoms structure consumed by ``enumerate_division_scenarios``
        and ``render_team_scenarios``.  Seeds > ``playoff_seeds`` represent
        elimination scenarios (used by ``render_team_scenarios`` for the
        "Eliminated if:" section).
    """
    R = len(remaining)
    if R == 0:
        return {}

    pairs = [(rg.a, rg.b) for rg in remaining]
    total_combos = 12 ** R

    # --- Step 1: Group by (mask, top-N seeding) ---
    groups: dict[tuple, list[dict]] = {}

    for mask in range(1 << R):
        for margin_combo in product(range(1, 13), repeat=R):
            margins = {pairs[i]: margin_combo[i] for i in range(R)}
            order = resolve_standings_for_mask(
                teams, completed, remaining, mask, margins, base_margin_default, pa_win
            )
            key = (mask, tuple(order[:playoff_seeds]))
            groups.setdefault(key, []).append(margins)

    # --- Step 2: Identify always-at-seed masks per (team, seed) ---
    # A mask "always puts team T at seed S" when T holds seed S for every one of
    # the total_combos margin combinations — regardless of how the other seeds
    # shake out.  This is a strictly weaker condition than the old "unconstrained
    # full-seeding" check, which required the *entire* top-N ordering to be
    # identical for all margins.  The new check lets us emit a single compact
    # game-winner atom for, e.g., Louisville #1 whenever Louisville beats
    # Greenwood — even when the #2/#3/#4 positions still vary with margins.
    mask_team_seed_margins: dict[tuple, int] = {}
    for (mask, top4), ml in groups.items():
        for seed_idx, team in enumerate(top4):
            key = (mask, team, seed_idx + 1)
            mask_team_seed_margins[key] = mask_team_seed_margins.get(key, 0) + len(ml)

    always_at_seed: dict[tuple, list[int]] = {}  # (team, seed) -> list of masks
    for mask in range(1 << R):
        for team in teams:
            for seed in range(1, playoff_seeds + 1):
                if mask_team_seed_margins.get((mask, team, seed), 0) == total_combos:
                    always_at_seed.setdefault((team, seed), []).append(mask)

    # Fast lookup used in Step 4 to skip adding constrained atoms for teams
    # whose seed is already fully covered by an always-at-seed atom.
    always_covered: dict[tuple, set[int]] = {
        (team, seed): set(masks) for (team, seed), masks in always_at_seed.items()
    }

    result: dict[str, dict[int, list]] = {}

    # --- Step 3: Always-at-seed atoms — partition into valid merge groups ---
    # _valid_merge_groups finds maximal compact game-winner conditions; e.g. all
    # 8 masks where Louisville beats Greenwood collapse to one atom.
    for (team, seed), masks in always_at_seed.items():
        for group in _valid_merge_groups(masks, R):
            game_winners = _common_game_winners(group, remaining)
            atom: list = [GameResult(w, l, 1, None) for w, l in game_winners]
            result.setdefault(team, {}).setdefault(seed, []).append(atom)

    # --- Step 4: Constrained atoms — derive ranges + joint constraints per group ---
    # For each (mask, top4) group that is not already fully covered, derive margin
    # atoms and add them only for the teams that still need them (i.e. those whose
    # (team, seed) is NOT already handled by an always-at-seed atom above).
    for (mask, top4), valid_margins_list in groups.items():
        uncovered_positions = [
            (seed_idx, team)
            for seed_idx, team in enumerate(top4)
            if mask not in always_covered.get((team, seed_idx + 1), set())
        ]
        if not uncovered_positions:
            continue
        for atom in _derive_atom(mask, valid_margins_list, remaining, pairs):
            for seed_idx, team in uncovered_positions:
                result.setdefault(team, {}).setdefault(seed_idx + 1, []).append(atom)

    # --- Step 5: Eliminated atoms (seed > playoff_seeds) via cross-mask merging ---
    # A team is "always eliminated" under mask M if it appears in NO top-N group for M.
    teams_in_any_top4: dict[int, set[str]] = {mask: set() for mask in range(1 << R)}
    for (mask, top4) in groups:
        teams_in_any_top4[mask].update(top4)

    # Pre-compute masks where each team can be eliminated (appears in some but not all top4s)
    team_sometimes_elim_masks: dict[str, set[int]] = {}
    for (mask, top4) in groups:
        for team in teams:
            if team not in top4:
                team_sometimes_elim_masks.setdefault(team, set()).add(mask)

    elim_seed = playoff_seeds + 1

    for team in teams:
        always_elim_masks = [m for m in range(1 << R) if team not in teams_in_any_top4[m]]
        sometimes_elim_only_masks = team_sometimes_elim_masks.get(team, set()) - set(always_elim_masks)

        if not always_elim_masks and not sometimes_elim_only_masks:
            continue

        # Unconstrained atoms: one full-condition atom per always-elim mask.
        # Boolean minimisation (step 6) will collapse them to the minimal DNF.
        for mask in always_elim_masks:
            game_winners = _game_winners_for_mask(mask, remaining)
            atom = [GameResult(w, l, 1, None) for w, l in game_winners]
            result.setdefault(team, {}).setdefault(elim_seed, []).append(atom)

        # Constrained atoms: masks where team is eliminated only for specific margin ranges
        for mask in sometimes_elim_only_masks:
            absent_margins: list[dict] = []
            for (mk, top4), margin_list in groups.items():
                if mk == mask and team not in top4:
                    absent_margins.extend(margin_list)
            if absent_margins:
                for atom in _derive_atom(mask, absent_margins, remaining, pairs):
                    result.setdefault(team, {}).setdefault(elim_seed, []).append(atom)

    # --- Step 6: Boolean minimisation then deterministic sort ---
    # First collapse redundant margin ranges and drop irrelevant game conditions,
    # then sort atoms into a stable, human-friendly order (see _sort_atom_list).
    for team in result:
        for seed in result[team]:
            result[team][seed] = _sort_atom_list(
                _simplify_atom_list(result[team][seed]), remaining
            )

    return result


# ---------------------------------------------------------------------------
# Core enumeration
# ---------------------------------------------------------------------------

_MARGIN_RANGE = range(1, 13)


def enumerate_division_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    scenario_atoms: dict | None = None,
    playoff_seeds: int = 4,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> list[dict]:
    """Enumerate all distinct complete seeding outcomes with their conditions.

    Each returned dict has:
    - ``scenario_num`` (int): primary scenario number.
    - ``sub_label`` (str): ``''`` for single scenarios; ``'a'``, ``'b'``, … for
      sub-scenarios within a margin-sensitive mask.
    - ``game_winners`` (list[tuple[str, str]]): (winner, loser) pairs for each
      relevant game.  Games that don't affect the seeding are omitted.
    - ``conditions_atom`` (list | None): the raw condition atom (GameResult /
      MarginCondition objects) for margin-sensitive sub-scenarios, or None.
    - ``seeding`` (tuple[str, ...]): all teams ordered seed 1 first.
    """
    R = len(remaining)
    pairs = [(rg.a, rg.b) for rg in remaining]

    if R == 0:
        order = resolve_standings_for_mask(
            teams, completed, remaining, 0, {}, base_margin_default, pa_win
        )
        return [
            {
                "scenario_num": 1,
                "sub_label": "",
                "game_winners": [],
                "conditions_atom": None,
                "seeding": tuple(order),
            }
        ]

    # (mask, seeding_tuple) → list of margin dicts for that combination
    mask_seeding_margins: dict[tuple, list[dict]] = defaultdict(list)

    for mask in range(1 << R):
        for margin_combo in product(_MARGIN_RANGE, repeat=R):
            margins = {pairs[i]: margin_combo[i] for i in range(R)}
            order = resolve_standings_for_mask(
                teams, completed, remaining, mask, margins, base_margin_default, pa_win
            )
            mask_seeding_margins[(mask, tuple(order))].append(margins)

    # Which masks produce more than one distinct seeding? (margin-sensitive)
    mask_seeding_count: dict[int, int] = defaultdict(int)
    for (mask, _) in mask_seeding_margins:
        mask_seeding_count[mask] += 1
    margin_sensitive = {m for m, cnt in mask_seeding_count.items() if cnt > 1}

    # Auto-build atoms when margin-sensitive sub-scenarios need conditions_atom populated.
    if margin_sensitive and scenario_atoms is None:
        scenario_atoms = build_scenario_atoms(
            teams, completed, remaining,
            pa_win=pa_win,
            base_margin_default=base_margin_default,
            playoff_seeds=playoff_seeds,
        )

    # Separate into non-margin-sensitive (group by seeding) and margin-sensitive
    non_ms: dict[tuple, list[int]] = defaultdict(list)  # seeding -> [masks]
    ms: dict[int, list[tuple]] = defaultdict(list)       # mask -> [(seeding, margins_list)]

    for (mask, seeding), margins_list in mask_seeding_margins.items():
        if mask in margin_sensitive:
            ms[mask].append((seeding, margins_list))
        else:
            non_ms[seeding].append(mask)

    # Build ordered list of scenario entries: (sort_key, entry_type, data)
    entries = []

    for seeding, masks in non_ms.items():
        for group in _valid_merge_groups(masks, R):
            min_mask = min(group)
            game_winners = _common_game_winners(group, remaining)
            entries.append((min_mask, "single", seeding, group, game_winners))

    for mask, sub_list in ms.items():
        entries.append((mask, "multi", None, mask, sub_list))

    entries.sort(key=lambda e: e[0])

    scenarios = []
    scenario_num = 0

    for entry in entries:
        if entry[1] == "single":
            _, _, seeding, masks, game_winners = entry
            scenario_num += 1
            scenarios.append(
                {
                    "scenario_num": scenario_num,
                    "sub_label": "",
                    "game_winners": game_winners,
                    "conditions_atom": None,
                    "seeding": seeding,
                }
            )
        else:
            _, _, _, mask, sub_list = entry
            scenario_num += 1
            sub_list_sorted = sorted(sub_list, key=lambda x: x[0])
            mask_game_winners = _game_winners_for_mask(mask, remaining)
            for k, (seeding, margins_list) in enumerate(sub_list_sorted):
                sub_label = chr(ord("a") + k)
                conditions_atom = None
                if scenario_atoms:
                    conditions_atom = _find_combined_atom(
                        seeding, playoff_seeds, mask, margins_list[0],
                        scenario_atoms, remaining,
                    )
                scenarios.append(
                    {
                        "scenario_num": scenario_num,
                        "sub_label": sub_label,
                        "game_winners": mask_game_winners,
                        "conditions_atom": conditions_atom,
                        "seeding": seeding,
                    }
                )

    return scenarios


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_game_winners(game_winners: list[tuple[str, str]]) -> str:
    """Render a list of (winner, loser) pairs as plain English."""
    return " AND ".join(f"{w} beats {l}" for w, l in game_winners)


def render_scenarios(scenarios: list[dict], playoff_seeds: int = 4) -> str:
    """Render a pre-computed scenario list (from enumerate_division_scenarios or DB) as text.

    This is the decoupled rendering path — it does not re-run enumeration, so it
    can be called cheaply at request time using scenarios loaded from the database.

    Example output::

        Scenario 1: Petal beats Northwest Rankin AND Pearl beats Oak Grove
        1. Petal
        2. Pearl
        3. Oak Grove
        4. Brandon
        Eliminated: Meridian, Northwest Rankin

        Scenario 6a: Brandon beats Meridian AND Pearl beats Oak Grove AND ...
        1. Oak Grove
        ...
    """
    lines = []
    for sc in scenarios:
        label = f"Scenario {sc['scenario_num']}{sc['sub_label']}"

        if sc["conditions_atom"] is not None:
            condition_str = _render_atom(sc["conditions_atom"])
        elif sc["game_winners"]:
            condition_str = _render_game_winners(sc["game_winners"])
        else:
            condition_str = "(no remaining games — standings are final)"

        lines.append(f"{label}: {condition_str}")

        seeding = sc["seeding"]
        for i in range(playoff_seeds):
            lines.append(f"{i + 1}. {seeding[i]}")

        eliminated = list(seeding[playoff_seeds:])
        if eliminated:
            lines.append(f"Eliminated: {', '.join(eliminated)}")

        lines.append("")

    return "\n".join(lines).rstrip()


def render_division_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    scenario_atoms: dict | None = None,
    playoff_seeds: int = 4,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> str:
    """Enumerate all scenarios and render them as human-readable text.

    Convenience wrapper that runs enumerate_division_scenarios() then
    render_scenarios().  For production use, prefer loading pre-computed
    scenarios from the database and calling render_scenarios() directly.
    """
    scenarios = enumerate_division_scenarios(
        teams, completed, remaining, scenario_atoms, playoff_seeds, pa_win, base_margin_default
    )
    return render_scenarios(scenarios, playoff_seeds)
