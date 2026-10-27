"""Enumerate and render complete seeding outcomes for a division.

For a given division (teams + completed + remaining games), enumerates every
distinct seeding outcome and the game conditions that produce it.  Scenarios
that are identical regardless of one game's winner automatically omit that
game from the conditions.  Margin-sensitive masks (where winning margins change
the seeding) are presented as lettered sub-scenarios (6a, 6b, …).
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import product

from backend.helpers.data_classes import (
    CompletedGame,
    GameResult,
    RemainingGame,
    TiebreakDecision,
)
from backend.helpers.scenario_renderer import _render_atom, atoms_from_complete_scenarios
from backend.helpers.tiebreakers import resolve_standings_for_mask

# ---------------------------------------------------------------------------
# Shared enumeration result
# ---------------------------------------------------------------------------


@dataclass
class EnumeratedOutcomes:
    """Pre-computed enumeration of all (mask, margin) outcomes.

    Produced by ``enumerate_outcomes()`` and consumed by both
    ``build_scenario_atoms()`` and ``enumerate_division_scenarios()`` to avoid
    running the 12^R margin enumeration twice per pipeline invocation.

    Attributes:
        groups: Maps ``(mask, full_seeding)`` to a list of margin dicts that
            produce that seeding under that mask.  Non-sensitive masks have an
            empty list (all margins produce the same seeding).
        non_sensitive_masks: Set of mask integers where the full seeding is
            identical for every margin combination (corner-evaluation confirmed).
        pairs: Ordered ``(team_a, team_b)`` pairs for each remaining game.
        R: Number of remaining games.
        total_combos: ``12 ** R`` — the full margin combination count per mask.
    """

    groups: dict  # (mask, full_seeding) -> list[dict]
    non_sensitive_masks: set
    pairs: list
    R: int
    total_combos: int
    coin_flips: dict  # mask -> list[list[str]] — tied groups resolved by coin flip (all masks)
    margin_tiebreaker_masks: dict  # mask -> list[list[str]] — tiebreaker groups for ignore_margins=True sensitive masks
    ignore_margins: bool = False  # True when enumerated with ignore_margins=True


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
            if next(iter(bits)) == 1:
                result.append((rg.a, rg.b))
            else:
                result.append((rg.b, rg.a))
    return result


# ---------------------------------------------------------------------------
# Atom builder — internal helpers
# ---------------------------------------------------------------------------


def _is_margin_sensitive_mask(
    teams,
    completed,
    remaining,
    mask: int,
    pairs: list[tuple],
    pa_win: int,
    base_margin_default: int,
) -> bool:
    """Return True if the mask's full seeding varies with winning margins.

    Evaluates ``resolve_standings_for_mask`` at all 2^R corners of the margin
    hypercube (each game margin is either 1 or 12).  All tiebreaker comparison
    functions (Steps 3-5) are linear in each margin variable, so extreme values
    are attained at vertices of the hyperrectangle.  If every vertex produces the
    same full seeding, the seeding is identical for all interior margins as well.

    Checks full seeding (not just top-N) so that ``EnumeratedOutcomes`` is
    usable by both ``build_scenario_atoms`` (which truncates to top-N internally)
    and ``enumerate_division_scenarios`` (which displays the complete seeding).
    """
    R = len(remaining)
    reference: tuple | None = None
    for corner in product((1, 12), repeat=R):
        margins = {pairs[i]: corner[i] for i in range(R)}
        order = resolve_standings_for_mask(teams, completed, remaining, mask, margins, base_margin_default, pa_win)
        full = tuple(order)
        if reference is None:
            reference = full
        elif full != reference:
            return True
    return False


def _simplify_atom_list(atoms: list[list]) -> list[list]:
    """Minimise a list of atoms using four boolean-simplification rules.

    All rules run in an outer stability loop that repeats until no rule fires,
    so applications of later rules can expose new opportunities for earlier ones.

    Rule 1 — Margin collapse:
        Two atoms identical in every condition except that one game's
        ``GameResult`` has adjacent or overlapping margin ranges (same winner)
        are merged into a single atom whose range is the union of the two.
        Ranges that together span [1, 12] collapse to an unconstrained
        ``GameResult`` (``min_margin=1``, ``max_margin=None``).

    Rule 2 — Game elimination:
        Two atoms identical except one game appears with opposite unconstrained
        winners are merged by dropping that game condition entirely.

    Rule 3 — Complementary lifting:
        ``(X_a ∧ G[lo+] ∧ R) ∨ (X_b ∧ G[hi+] ∧ R)`` where lo < hi rewrites
        b to ``G[hi+] ∧ R``, dropping X_b since G[hi+] already implies the
        result regardless of which team wins X.

    Rule 4 — Range-containment splitting:
        ``(X_a ∧ G[lo..M) ∧ R) ∨ (X_b ∧ G[lo..N) ∧ R)`` where M < N rewrites
        to ``(G[lo..M) ∧ R) ∨ (X_b ∧ G[M..N) ∧ R)``.  Both ranges must share
        the same lower bound ``lo``; X result is irrelevant for the narrow range.

    Args:
        atoms: List of atoms, each atom being a list of ``GameResult`` /
               ``MarginCondition`` objects.

    Returns:
        A simplified list of atoms.  May be shorter than the input.
        Returns ``[[]]`` if any atom collapses to unconditional.
    """
    from backend.helpers.data_classes import GameResult, MarginCondition, TiebreakPlace

    # Remove exact duplicates before running simplification rules — minimisation
    # in _minimize_game_winner_atom can collapse distinct atoms to the same form.
    seen_keys: set[tuple] = set()
    deduped: list[list] = []
    for a in atoms:
        key = tuple(a)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(a)
    atoms = deduped

    def _pair(c: GameResult) -> tuple:
        """Return a canonical (sorted) team-pair key for a GameResult."""
        return tuple(sorted([c.winner, c.loser]))

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

        # Non-GameResult conditions (MarginCondition, CoinFlipResult, …) must be
        # identical in both atoms — use equality rather than attribute access so
        # frozen dataclasses (like CoinFlipResult) compare correctly.
        if len(mc_a) != len(mc_b) or any(x != y for x, y in zip(mc_a, mc_b)):
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
                if isinstance(mc, MarginCondition) and (p in mc.add or p in mc.sub):
                    return None
            return [
                (gr_a[val] if kind == "gr" else mc_a[val]) for kind, val in order if not (kind == "gr" and val == p)
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

    def _merge_tie_places(atoms: list[list]) -> list[list]:
        """Rule 5 — Every place in a tie: atoms identical but for the ``TiebreakPlace`` of one team in
        one tie, between them naming every place in it, are the rest alone (it finishes somewhere)."""
        ways: dict[tuple, set[int]] = {}
        for a in atoms:
            ties = [c for c in a if isinstance(c, TiebreakPlace)]
            if len(ties) == 1:
                t = ties[0]
                rest = tuple(c for c in a if c is not t)
                ways.setdefault((rest, t.team, t.group, t.step), set()).add(t.place)
        whole = {k[0] for k, places in ways.items() if places == set(range(1, len(k[2]) + 1))}
        if not whole:
            return atoms
        out: list[list] = []
        for a in atoms:
            rest = tuple(c for c in a if not isinstance(c, TiebreakPlace))
            if rest in whole and len(rest) == len(a) - 1:
                if list(rest) not in out:
                    out.append(list(rest))
            else:
                out.append(a)
        return out

    # Iterative minimisation
    changed = True
    while changed:
        changed = False
        atoms = _merge_tie_places(atoms)
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
    dominated = {j for i in range(len(atoms)) for j in range(len(atoms)) if i != j and _subsumes(atoms[i], atoms[j])}
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

            # p_tight: same winner, same lower bound, a's range strictly narrower
            if ca_t.winner != cb_t.winner or ca_t.loser != cb_t.loser:
                continue
            if ca_t.min_margin != cb_t.min_margin:
                continue  # lower bounds must match
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

    # ---------------------------------------------------------------------------
    # Outer stability loop — repeats until no rule fires in a full pass.
    # Later rules can expose new opportunities for earlier ones.
    # ---------------------------------------------------------------------------
    globally_changed = True
    while globally_changed:
        globally_changed = False

        # Rules 1/2: iterative merge until stable
        r12_changed = True
        while r12_changed:
            r12_changed = False
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
                        r12_changed = True
                        globally_changed = True
                        found_pair = True
                        break
                if not found_pair:
                    new_atoms.append(atoms[i])
            atoms = new_atoms

        # Subsumption: remove atoms strictly subsumed by a simpler atom
        dominated = {
            j for i in range(len(atoms)) for j in range(len(atoms)) if i != j and _subsumes(atoms[i], atoms[j])
        }
        if dominated:
            atoms = [atom for k, atom in enumerate(atoms) if k not in dominated]
            globally_changed = True

        # Rule 3: complementary lifting
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
                        globally_changed = True
                        break
                if r3_changed:
                    break

        # Rule 4: range-containment splitting — try all ordered pairs
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
                        atoms = [(new_a if k == i else (new_b if k == j else atom)) for k, atom in enumerate(atoms)]
                        r4_changed = True
                        globally_changed = True
                        break
                if r4_changed:
                    break

    return atoms


def _valid_merge_groups(masks: list[int]) -> list[list[int]]:
    """Partition masks into maximal valid merge groups via prime implicant covering.

    Uses a QMC-style iterative merge to find all maximal aligned hypercubes
    within the mask set (prime implicants), then greedily assigns masks to the
    largest available group (fewest conditions per atom).  Larger groups consume
    fewer game-winner conditions, producing more concise scenario atoms.
    """
    if not masks:
        return []
    if len(masks) == 1:
        return [list(masks)]

    mask_set = frozenset(masks)

    # QMC iterative merge.
    # Each entry: (base_mask, free_bitmask) → frozenset of covered masks.
    # base_mask has 0s at all free bit positions; free_bitmask tracks which bits vary.
    current: dict[tuple[int, int], frozenset[int]] = {(m, 0): frozenset([m]) for m in mask_set}
    all_pis: list[frozenset[int]] = []

    while current:
        by_free: dict[int, list[tuple[int, frozenset[int]]]] = {}
        for (base, free_bm), covered in current.items():
            by_free.setdefault(free_bm, []).append((base, covered))

        next_level: dict[tuple[int, int], frozenset[int]] = {}
        used: set[tuple[int, int]] = set()

        for free_bm, groups in by_free.items():
            for i in range(len(groups)):
                base_i, cov_i = groups[i]
                for j in range(i + 1, len(groups)):
                    base_j, cov_j = groups[j]
                    diff = base_i ^ base_j
                    # Must differ by exactly one bit that is not already free.
                    if diff == 0 or (diff & (diff - 1)) or (diff & free_bm):
                        continue
                    new_key = (base_i & base_j, free_bm | diff)
                    prev = next_level.get(new_key, frozenset())
                    next_level[new_key] = prev | cov_i | cov_j
                    used.add((base_i, free_bm))
                    used.add((base_j, free_bm))

        for key, covered in current.items():
            if key not in used:
                all_pis.append(covered)

        current = next_level

    # Greedy partition: largest prime implicants first so each atom has the
    # fewest conditions.  Every mask is guaranteed coverage because each
    # individual mask is its own size-1 prime implicant.
    all_pis.sort(key=len, reverse=True)
    remaining = set(mask_set)
    result: list[list[int]] = []

    for pi in all_pis:
        if pi <= remaining:
            result.append(sorted(pi))
            remaining -= pi
        if not remaining:
            break

    result.extend([m] for m in sorted(remaining))
    return result


def _minimize_game_winner_atom(
    atom: list,
    always_covered_set: set[int],
    remaining: list[RemainingGame],
    num_games: int,
) -> list:
    """Drop redundant pure-game-winner conditions from *atom*.

    A ``GameResult(w, l, 1, None)`` condition is redundant when removing it
    expands the covered mask set but every newly-covered mask is still within
    *always_covered_set*.  Iterates until stable so multiple redundant
    conditions can be removed in sequence.
    """
    pairs = [(rg.a, rg.b) for rg in remaining]

    def covered(conds: list) -> set[int]:
        """Return the set of masks covered by the given game-winner conditions."""
        fixed: dict[int, int] = {}
        for c in conds:
            if not isinstance(c, GameResult):
                continue
            for i, (a, b) in enumerate(pairs):
                if c.winner == a and c.loser == b:
                    fixed[i] = 1
                    break
                elif c.winner == b and c.loser == a:
                    fixed[i] = 0
                    break
        base = sum(v << i for i, v in fixed.items())
        free = [i for i in range(num_games) if i not in fixed]
        n = len(free)
        return {base | sum(((fc >> j) & 1) << free[j] for j in range(n)) for fc in range(1 << n)}

    changed = True
    while changed:
        changed = False
        for i, c in enumerate(atom):
            if not isinstance(c, GameResult) or c.min_margin != 1 or c.max_margin is not None:
                continue
            candidate = atom[:i] + atom[i + 1 :]
            if covered(candidate) <= always_covered_set:
                atom = candidate
                changed = True
                break
    return atom


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
        """Sort key for a single atom.

        Returns a 4-tuple that orders atoms by:
        1. Number of ``GameResult`` constraints (fewer first — unconditional
           outcomes before margin-restricted ones).
        2. Whether any margin constraint is active (unconstrained before
           constrained).
        3. Winner-pattern tuple — 0/1/2 per remaining game (a-wins / b-wins /
           absent), so margin variants of the same outcome cluster together.
        4. Min-margin tuple — tighter lower bounds sort later within a
           winner-pattern group.
        """
        game_results = [c for c in atom if isinstance(c, GameResult)]
        n_games = len(game_results)
        is_constrained = any(c.max_margin is not None or c.min_margin > 1 for c in game_results) or any(
            isinstance(c, MarginCondition) for c in atom
        )
        winner_pattern = []
        for a, b in pairs:
            gr = next(
                (c for c in game_results if (c.winner == a and c.loser == b) or (c.winner == b and c.loser == a)),
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
# Odds computation from pre-enumerated outcomes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Atom builder
# ---------------------------------------------------------------------------


def _find_tiebreaker_groups(order_ref: list[str], order_lo: list[str]) -> list[list[str]]:
    """Find groups of teams whose seed positions are mutually swapped between two orderings.

    Used to identify which teams are competing for the same seed range via a
    margin-sensitive tiebreaker when ``ignore_margins=True``.

    A group is a maximal span of consecutive positions where the set of teams
    occupying those positions in ``order_ref`` equals the set in ``order_lo``
    but the individual positions differ.  Returns each group in ``order_ref``
    order (i.e., the order produced by the default margin).
    """
    n = len(order_ref)
    groups: list[list[str]] = []
    i = 0
    while i < n:
        if order_ref[i] == order_lo[i]:
            i += 1
            continue
        j = i
        set_ref: set[str] = {order_ref[i]}
        set_lo: set[str] = {order_lo[i]}
        while set_ref != set_lo:
            j += 1
            if j >= n:
                break
            set_ref.add(order_ref[j])
            set_lo.add(order_lo[j])
        if set_ref == set_lo:
            groups.append(list(order_ref[i : j + 1]))
        i = j + 1
    return groups


def enumerate_outcomes(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    pa_win: int = 14,
    base_margin_default: int = 7,
    ignore_margins: bool = False,
) -> EnumeratedOutcomes:
    """Enumerate all (mask, margin) outcomes once, returning a shared result.

    Runs the 12^R margin enumeration for each win/loss mask exactly once.
    Margin-insensitive masks are detected via corner evaluation (2^R calls)
    and skipped for full enumeration.

    The returned ``EnumeratedOutcomes`` can be passed to both
    ``build_scenario_atoms()`` and ``enumerate_division_scenarios()`` to avoid
    repeating the enumeration.

    Args:
        teams: All team names in the region.
        completed: Completed region games.
        remaining: Unplayed region games.
        pa_win: Points-allowed value for the simulated winning team.
        base_margin_default: Default margin when no specific margin is set.
        ignore_margins: When True, skip margin enumeration entirely. Each mask
            is evaluated once with a fixed default margin and treated as
            non-sensitive. Used past 5 games left (the win/loss-only tier).
            Callers must not use the resulting atoms for margin-sensitive
            sub-scenario conditions — they will be absent.

    Returns:
        ``EnumeratedOutcomes`` containing the full ``(mask, seeding) → margins``
        mapping plus metadata needed by both consumers.  When ``ignore_margins``
        is True, all masks are in ``non_sensitive_masks`` and all margin lists
        are empty.
    """
    R = len(remaining)
    pairs = [(rg.a, rg.b) for rg in remaining]
    total_combos = 12**R

    groups: dict = {}
    non_sensitive_masks: set = set()
    coin_flips: dict = {}  # mask -> list[list[str]] of tied groups resolved by coin flip
    margin_tiebreaker_masks: dict = {}  # populated only when ignore_margins=True

    ref_margins = {pairs[i]: base_margin_default for i in range(R)}
    lo_margins = {pairs[i]: 1 for i in range(R)}

    for mask in range(1 << R):
        if ignore_margins or not _is_margin_sensitive_mask(
            teams, completed, remaining, mask, pairs, pa_win, base_margin_default
        ):
            flip_collector: list = []
            order = resolve_standings_for_mask(
                teams,
                completed,
                remaining,
                mask,
                ref_margins,
                base_margin_default,
                pa_win,
                coin_flip_collector=flip_collector,
            )
            groups[(mask, tuple(order))] = []
            non_sensitive_masks.add(mask)
            if flip_collector:
                coin_flips[mask] = flip_collector
            elif ignore_margins:
                # Check if this mask would be margin-sensitive under full enumeration.
                # Compare seeding at margin=1 vs the default; if they differ, the
                # tiebreaker is PD-sensitive and we record the affected team groups.
                order_lo = resolve_standings_for_mask(
                    teams, completed, remaining, mask, lo_margins, base_margin_default, pa_win
                )
                if tuple(order_lo) != tuple(order):
                    tg = _find_tiebreaker_groups(list(order), list(order_lo))
                    if tg:
                        margin_tiebreaker_masks[mask] = tg
        else:
            for margin_combo in product(range(1, 13), repeat=R):
                margins = {pairs[i]: margin_combo[i] for i in range(R)}
                flip_collector = []
                order = resolve_standings_for_mask(
                    teams,
                    completed,
                    remaining,
                    mask,
                    margins,
                    base_margin_default,
                    pa_win,
                    coin_flip_collector=flip_collector,
                )
                key = (mask, tuple(order))
                groups.setdefault(key, []).append(margins)
                # Store coin flips for this mask (same groups for every margin combo
                # since coin flips are determined by win/loss record, not margins).
                if flip_collector and mask not in coin_flips:
                    coin_flips[mask] = flip_collector

    return EnumeratedOutcomes(
        groups=groups,
        non_sensitive_masks=non_sensitive_masks,
        pairs=pairs,
        R=R,
        total_combos=total_combos,
        coin_flips=coin_flips,
        margin_tiebreaker_masks=margin_tiebreaker_masks,
        ignore_margins=ignore_margins,
    )


def team_atoms_from_scenarios(
    complete_scenarios: list[dict], remaining: list[RemainingGame], playoff_seeds: int = 4
) -> dict[str, dict[int, list[list]]]:
    """Per-team per-seed atoms (``build_scenario_atoms``' shape) read off the region's complete scenarios.

    The complete scenarios state only what the tiebreaker decides, so atoms taken from them do too:
    a team's place in a tie a scenario leaves open is a ``TiebreakPlace`` condition, never a guess.

    For readability, the sets of winners that put a team in one place whatever the margins merge
    into plain game-winner atoms ("Louisville beats Greenwood"), as in the region's single-outcome
    scenarios; only the rest keep their scenarios' conditions. Each list is then minimised and
    sorted.
    """
    from backend.helpers.data_classes import TiebreakPlace

    R = len(remaining)
    index = {frozenset((g.a, g.b)): i for i, g in enumerate(remaining)}

    def masks_of(way: list) -> set[int]:
        """The sets of winners a way's game results allow."""
        need = {}
        for c in way:
            if isinstance(c, GameResult) and frozenset((c.winner, c.loser)) in index:
                i = index[frozenset((c.winner, c.loser))]
                need[i] = 1 if remaining[i].a == c.winner else 0
        return {m for m in range(1 << R) if all((m >> i) & 1 == bit for i, bit in need.items())}

    result: dict[str, dict[int, list[list]]] = {}
    for team, seeds in atoms_from_complete_scenarios(complete_scenarios, playoff_seeds).items():
        ways = [(seed, way, masks_of(way)) for seed, alist in seeds.items() for way in alist]
        # mask -> the places its ways give the team (None for a place in a tie left open).
        places: dict[int, set] = defaultdict(set)
        for seed, way, masks in ways:
            certain = not any(isinstance(c, TiebreakPlace) for c in way)
            for m in masks:
                places[m].add(seed if certain else None)
        result[team] = {}
        for seed in seeds:
            always = sorted(m for m, p in places.items() if p == {seed})
            always_set = set(always)
            atoms = [
                _minimize_game_winner_atom(
                    [GameResult(w, l, 1, None) for w, l in _common_game_winners(group, remaining)],
                    always_set,
                    remaining,
                    R,
                )
                for group in _valid_merge_groups(always)
            ]
            atoms += [way for s, way, masks in ways if s == seed and not masks <= always_set]
            result[team][seed] = _sort_atom_list(_simplify_atom_list(atoms), remaining)
    return result


def build_scenario_atoms(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    pa_win: int = 14,
    base_margin_default: int = 7,
    playoff_seeds: int = 4,
    precomputed: EnumeratedOutcomes | None = None,
) -> dict:
    """Build per-team per-seed scenario atoms: what each team needs for each place it can finish.

    Read off the region's complete scenarios (``enumerate_division_scenarios``, which *precomputed*
    tells whether to ignore margins), so the atoms say only what the tiebreaker decides: a place
    that turns on fewest points allowed or a coin flip is a ``TiebreakPlace`` condition, never a
    guess. See ``team_atoms_from_scenarios``.

    Args:
        teams: List of all team names in the region.
        completed: List of CompletedGame instances for finished region games.
        remaining: List of RemainingGame instances for unplayed region games.
        pa_win: Points-allowed value assigned to the winner in simulated games.
        base_margin_default: Default margin used when no specific margin is set.
        playoff_seeds: Number of playoff seeds (default 4).
        precomputed: Optional ``EnumeratedOutcomes``; only its ``ignore_margins`` flag is used.

    Returns:
        ``dict[team → dict[seed → list[list[condition]]]]``, empty with no games or more than 10
        left. Seed ``playoff_seeds + 1`` collects the elimination scenarios (used by
        ``render_team_scenarios`` for the "Eliminated if:" section).
    """
    if not remaining or len(remaining) > 10:
        return {}
    scenarios = enumerate_division_scenarios(
        teams,
        completed,
        remaining,
        playoff_seeds=playoff_seeds,
        pa_win=pa_win,
        base_margin_default=base_margin_default,
        precomputed=precomputed,
    )
    return team_atoms_from_scenarios(scenarios, remaining, playoff_seeds)


# ---------------------------------------------------------------------------
# Core enumeration
# ---------------------------------------------------------------------------

_MARGIN_RANGE = range(1, 13)


# The most games left for which every margin combination (12 per game) is checked; with more, a group
# whose order turns on margins is shown as a group left to the tiebreaker (see enumerate_division_scenarios).
_MAX_EXACT_MARGIN_GAMES = 5
# The most margin blocks an outcome is described with as plain margin ranges ("A beats B by 1-7");
# an outcome whose margins need more is described by the tiebreaker decisions behind it instead.
_MAX_MARGIN_BLOCKS = 2
# The most outcomes one set of winners lists as their own sub-scenarios; past it, the tie that decides
# them is shown as left to the tiebreaker (and the check-a-score tool), not as dozens of cards.
_MAX_LISTED_OUTCOMES = 8


def _finish_key(seeding, open_groups, places) -> tuple:
    """One way the region can finish: its seeding, the ties left open, and where their teams can land."""
    return (
        tuple(seeding),
        tuple((step, tuple(g)) for step, g in open_groups),
        tuple(sorted((t, tuple(seeds)) for t, seeds in places)),
    )


def _margin_blocks(region: set[tuple[int, ...]], limit: int) -> list[list[tuple[int, int]]] | None:
    """*region* (margin combinations, 1-12 per game) as at most *limit* boxes of margin ranges, each
    box inside it and together covering it; None when it takes more."""
    boxes: list[list[tuple[int, int]]] = []
    left = set(region)
    while left:
        if len(boxes) == limit:
            return None
        box = [(m, m) for m in min(left)]
        for i in range(len(box)):
            for step in (-1, 1):
                while True:
                    lo, hi = box[i]
                    nxt = (lo - 1, hi) if step < 0 else (lo, hi + 1)
                    if nxt[0] < _MARGIN_RANGE[0] or nxt[1] > _MARGIN_RANGE[-1]:
                        break
                    trial = box[:i] + [nxt] + box[i + 1 :]
                    if not all(p in region for p in product(*(range(a, b + 1) for a, b in trial))):
                        break
                    box = trial
        boxes.append(box)
        left -= set(product(*(range(a, b + 1) for a, b in box)))
    return boxes


def _sub_label(k: int) -> str:
    """Sub-scenario labels a..z, then aa, ab, … for a set of winners with more outcomes than letters."""
    return chr(ord("a") + k) if k < 26 else _sub_label(k // 26 - 1) + chr(ord("a") + k % 26)


def _decision_signature(decisions: list, open_from: int, in_play: set[str]) -> tuple[tuple, tuple]:
    """Split a seeding's tiebreaker *decisions* into what a scenario states and what it leaves open.

    Returns ``(stated, open_groups)``: ``stated`` the step 3-4 decisions (``TiebreakDecision``), and
    ``open_groups`` the ``(step, group)`` pairs for groups whose order the scenario leaves to the
    tiebreaker from *step* on: every group that reaches step 5 (fewest points allowed, which turns on
    actual scores rather than margins) with a team still to play (*in_play*), and with
    ``open_from=3`` every group that reaches step 3. A group whose teams have all finished their
    region games already has its points allowed, so step 5 decides it for certain; if they're level
    there too, it's a coin flip, ``(6, group)``. Decisions within an open group are dropped: they
    follow from how it's settled.
    """
    stated: list = []
    open_groups: list = []
    for step, group, parts in decisions:
        if any(set(group) <= set(g) for _, g in open_groups):
            continue
        if step == 5 and not set(group) & in_play:
            if len(parts) == 1:
                open_groups.append((6, group))
            continue
        if step >= open_from:
            open_groups.append((step, group))
        else:
            stated.append(TiebreakDecision(step, group, parts))
    return tuple(stated), tuple(open_groups)


def _settle_open(order: list[str], open_groups: tuple, playoff_seeds: int) -> tuple[tuple[str, ...], tuple]:
    """What a scenario shows of a seeding: the playoff seeds in order, then the rest alphabetically
    (they're listed as out, not ranked); each open group's places alphabetical too, since its order
    isn't stated. Returns ``(seeding, open groups that reach a playoff seed)``."""
    out = list(order)
    for _, group in open_groups:
        spots = sorted(i for i, t in enumerate(out) if t in group)
        for i, team in zip(spots, sorted(group), strict=True):
            out[i] = team
    out = out[:playoff_seeds] + sorted(out[playoff_seeds:])
    shown = tuple((step, g) for step, g in open_groups if set(g) & set(out[:playoff_seeds]))
    return tuple(out), shown


def _narrow_open(
    order: list[str], open_groups: tuple, seen: list[tuple], playoff_seeds: int
) -> tuple[tuple[str, ...], tuple, tuple]:
    """Leave *open_groups* to the tiebreaker, but state what every margin agrees on.

    *seen* is every outcome (seeding, shown open groups) the margins give. A team that lands in the
    same place in all of them (a playoff seed, or out) has that place, whatever the tiebreaker does;
    it leaves its group. For the rest, the places they reach are returned as ``places``:
    ``((team, (seed, …)), …)``, seeds 1-based with ``playoff_seeds + 1`` meaning out. Returns
    ``(seeding, open groups that reach a playoff seed, places)``.
    """
    out_place = playoff_seeds  # 0-based places past the playoff seeds are all "out"
    reach: dict[str, set[int]] = defaultdict(set)
    for seeding, groups in seen:
        where = {t: {min(i, out_place)} for i, t in enumerate(seeding)}
        for _, g in groups:
            span = {min(seeding.index(t), out_place) for t in g}
            for t in g:
                where[t] = span
        for t, places in where.items():
            reach[t] |= places
    seeding = list(order)
    narrowed = []
    for step, group in open_groups:
        spots = sorted(seeding.index(t) for t in group)
        fixed = {t: next(iter(reach[t])) for t in group if len(reach[t]) == 1}
        loose = sorted(t for t in group if t not in fixed)
        placed: dict[int, str] = {i: t for t, i in fixed.items() if i < out_place}
        free = [i for i in spots if i not in placed]
        # Teams with a fixed playoff seed take it; the open teams the first places left (any playoff
        # seed they reach comes before every place out), teams always out the last.
        tail = sorted(t for t, i in fixed.items() if i >= out_place)
        for i, t in zip(free, loose + tail, strict=True):
            placed[i] = t
        for i, t in placed.items():
            seeding[i] = t
        if len(loose) > 1:
            narrowed.append((step, tuple(loose)))
    seeding = seeding[:playoff_seeds] + sorted(seeding[playoff_seeds:])
    shown = tuple((step, g) for step, g in narrowed if set(g) & set(seeding[:playoff_seeds]))
    places = tuple((t, tuple(sorted(i + 1 for i in reach[t]))) for _, g in shown for t in g if len(reach[t]) < len(g))
    return tuple(seeding), shown, places


def _simplest_terms(signatures: dict) -> dict:
    """For each outcome, the fewest stated decisions that still pick it out exactly.

    *signatures* maps each distinct set of decisions seen (a frozenset) to its outcome. A decision
    is dropped from an outcome's conditions when every set of decisions containing what's left has
    that same outcome, so the shorter conditions are still exact (every result they match has the
    outcome) and still cover all of it (each set keeps a term inside it). Returns outcome -> terms.
    """
    terms: dict = defaultdict(list)
    for sig, outcome in sorted(signatures.items(), key=lambda kv: (len(kv[0]), sorted(map(str, kv[0])))):
        term = set(sig)
        for lit in sorted(sig, key=str):
            trial = term - {lit}
            if all(o == outcome for other, o in signatures.items() if trial <= other):
                term = trial
        if not any(set(t) <= term for t in terms[outcome]):
            terms[outcome] = [t for t in terms[outcome] if not term <= set(t)] + [frozenset(term)]
    return terms


def enumerate_division_scenarios(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    scenario_atoms: dict | None = None,
    playoff_seeds: int = 4,
    pa_win: int = 14,
    base_margin_default: int = 7,
    precomputed: EnumeratedOutcomes | None = None,
    scenario_odds: bool = False,
    win_probs: list[float] | None = None,
) -> list[dict]:
    """Enumerate every distinct way the region can finish, each with exactly what makes it happen.

    For each set of winners, the tiebreaker is run and its margin-dependent decisions recorded. When
    no tied group gets past step 2 (head-to-head, then record against the rest), the winners alone
    decide the seeding: one scenario, merged with other winner sets giving the same seeding where
    they share their deciding games. Otherwise, with up to ``_MAX_EXACT_MARGIN_GAMES`` games left,
    every margin combination (1-12 per game, 12 meaning 12 or more) is checked, and each distinct
    set of step 3-4 decisions becomes a sub-scenario stating them (``TiebreakDecision`` conditions),
    so a scenario says only what the tiebreaker decided, keeping just the decisions its outcome
    depends on. With more games left, a group that reaches step 3 is left open instead.

    A group still level after step 4 is always left open: step 5 (fewest points allowed in region
    games) depends on the actual scores, which margins don't fix, so the scenario names the group
    and leaves its order to that step and then a coin flip, rather than guessing.

    Each returned dict has:
    - ``scenario_num`` (int) and ``sub_label`` (``''``, or ``'a'``, ``'b'``, … within one set of winners).
    - ``game_winners`` (list[tuple[str, str]]): (winner, loser) for each game that matters.
    - ``conditions_atom`` (list | None): for a sub-scenario, its winners as ``GameResult`` conditions
      (with margin ranges where it needs them) plus the ``TiebreakDecision`` conditions that pick it
      out; None otherwise.
    - ``alternatives`` (list[list] | None): when more than one set of conditions leads to the same
      outcome, all of them (``conditions_atom`` is the first); any one is enough.
    - ``open_groups`` (list[tuple[int, tuple[str, ...]]] | None): groups whose order is left to the
      tiebreaker from the given step on.
    - ``open_places`` (dict[str, list[int]] | None): for a team in an open group that can't reach
      every one of the group's places, the seeds it can (``playoff_seeds + 1`` meaning out); a team
      not listed can reach them all.
    - ``tiebreaker_groups``, ``coinflip_groups``: always None (kept for stored-snapshot compatibility).
    - ``seeding`` (tuple[str, ...]): the playoff seeds in order, then the teams out alphabetically
      (outcomes differing only below the playoff seeds are one outcome); an open group's places
      alphabetical. An open group wholly out of the playoffs isn't listed.

    With ``scenario_odds`` (and every margin worked through), each dict also has ``p`` and
    ``p_weighted``: the chance of its finish (its seeding, open groups and open places) with every game
    a coin flip, and with each game at *win_probs* (P(``remaining[i].a`` wins); toss-up when None).
    Margins count as often as they happened in 2025, league-wide for ``p`` and by the winner's chance
    for ``p_weighted``, as the region's odds do. Several dicts can share a finish (different winners
    reaching the same standings), and then share its chance; the finishes' chances add up to 1.

    ``scenario_atoms`` and ``precomputed`` are accepted for compatibility; ``precomputed`` only says
    whether margins are being ignored (``ignore_margins``), which leaves every margin-dependent group open.
    """
    R = len(remaining)
    pairs = [(rg.a, rg.b) for rg in remaining]
    exact = R <= _MAX_EXACT_MARGIN_GAMES and not (precomputed is not None and precomputed.ignore_margins)
    open_from = 5 if exact else 3
    in_play = {t for rg in remaining for t in (rg.a, rg.b)}
    ref = {pair: base_margin_default for pair in pairs}

    # For scenario odds: each set of winners' chance and the chance of each margin for each game's
    # winner (index 0 toss-up, 1 projected), and each finish's chance as the sets of winners and
    # margins that give it are found.
    track = scenario_odds and exact
    mask_weights: list[list[float]] = [[], []]
    shares: list[list[list[tuple[float, ...]]]] = [[], []]
    finish_odds: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])

    def add_finish(mask: int, seeding, open_groups, places, share=(1.0, 1.0)) -> None:
        """Credit a finish with a share of one set of winners' chance."""
        w = finish_odds[_finish_key(seeding, open_groups, places)]
        w[0] += mask_weights[0][mask] * share[0]
        w[1] += mask_weights[1][mask] * share[1]

    if track:
        from backend.helpers.scenarios import _MARGIN_SHARE, projected_margin_share

        for mask in range(1 << R):
            won = [win_probs[i] if mask >> i & 1 else 1 - win_probs[i] for i in range(R)] if win_probs else None
            mask_weights[0].append(0.5**R)
            mask_weights[1].append(math.prod(won) if won else 0.5**R)
            shares[0].append([_MARGIN_SHARE] * R)
            shares[1].append([projected_margin_share(p) for p in won] if won else [_MARGIN_SHARE] * R)

    def run(mask: int, margins: dict) -> tuple[tuple, tuple]:
        """(stated decisions, (seeding, open groups)) for one result."""
        decisions: list = []
        order = resolve_standings_for_mask(
            teams, completed, remaining, mask, margins, base_margin_default, pa_win, decision_collector=decisions
        )
        stated, open_groups = _decision_signature(decisions, open_from, in_play)
        seeding, shown = _settle_open(order, open_groups, playoff_seeds)
        return stated, (seeding, shown)

    # mask -> list of (stated, open_groups, seeding, first margin combination), one per outcome and term.
    outcomes: dict[int, list] = {}
    # mask -> its outcome, or {margin combination: outcome} where margins matter (for dropping games below).
    table: dict[int, object] = {}
    # mask -> the places each team in a tie left open can reach, where not all of the tie's places.
    open_places: dict[int, tuple] = {}
    for mask in range(1 << R):
        stated, (seeding, open_groups) = run(mask, ref)
        if not stated or not exact:
            if track:
                add_finish(mask, seeding, open_groups, ())
            outcomes[mask] = [((), open_groups, seeding, None)]
            table[mask] = (seeding, open_groups)
            continue
        signatures: dict = {}
        first: dict = {}
        regions: dict = defaultdict(set)
        weights: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for combo in product(_MARGIN_RANGE, repeat=R):
            stated, outcome = run(mask, dict(zip(pairs, combo, strict=True)))
            signatures[frozenset(stated)] = outcome
            if track:
                w = weights[outcome]
                w[0] += math.prod(shares[0][mask][i][m - 1] for i, m in enumerate(combo))
                w[1] += math.prod(shares[1][mask][i][m - 1] for i, m in enumerate(combo))
            first.setdefault(outcome, combo)
            regions[outcome].add(combo)
        if len(first) == 1:  # the decisions vary, but never the outcome
            (seeding, open_groups) = next(iter(first))
            if track:
                add_finish(mask, seeding, open_groups, ())
            outcomes[mask] = [((), open_groups, seeding, None)]
            table[mask] = (seeding, open_groups)
            continue
        if len(first) > _MAX_LISTED_OUTCOMES:
            # Too many to list: leave each tie that reaches step 3 open. Which ties reach it doesn't
            # depend on margins (steps 1-2 don't), so this is one outcome for every margin; it still
            # says where a team always lands, and which places the others can reach.
            decisions: list = []
            order = resolve_standings_for_mask(
                teams, completed, remaining, mask, ref, base_margin_default, pa_win, decision_collector=decisions
            )
            _, open_groups = _decision_signature(decisions, 3, in_play)
            seeding, open_groups, places = _narrow_open(order, open_groups, list(first), playoff_seeds)
            if places:
                open_places[mask] = places
            if track:
                add_finish(mask, seeding, open_groups, places or ())
            outcomes[mask] = [((), open_groups, seeding, None)]
            table[mask] = (seeding, open_groups)
            continue
        table[mask] = {combo: outcome for outcome, region in regions.items() for combo in region}
        if track:
            for (seeding, open_groups), share in weights.items():
                add_finish(mask, seeding, open_groups, (), share)
        # Each outcome in plain margin ranges when a couple of blocks say it; else by its decisions.
        winners = _game_winners_for_mask(mask, remaining)
        terms = _simplest_terms(signatures)
        listed = []
        for outcome, region in regions.items():
            seeding, open_groups = outcome
            blocks = _margin_blocks(region, _MAX_MARGIN_BLOCKS)
            if blocks is not None:
                for box in blocks:
                    # Only the games the outcome needs a margin for; the rest are plain wins.
                    ranges = tuple(
                        GameResult(w, l, lo, None if hi == _MARGIN_RANGE[-1] else hi + 1)
                        for (w, l), (lo, hi) in zip(winners, box, strict=True)
                        if (lo, hi) != (_MARGIN_RANGE[0], _MARGIN_RANGE[-1])
                    )
                    listed.append((ranges, open_groups, seeding, tuple(lo for lo, _ in box)))
            else:
                for term in terms[outcome]:
                    stated = tuple(sorted(term, key=lambda d: (d.step, d.group)))
                    listed.append((stated, open_groups, seeding, first[outcome]))
        outcomes[mask] = listed

    def holds_without(mask: int, ranges: tuple, outcome, games: frozenset) -> bool:
        """True when the outcome holds at every margin *ranges* allow, whoever wins *games*."""
        index = {frozenset(p): i for i, p in enumerate(pairs)}
        box = [list(_MARGIN_RANGE) for _ in pairs]
        for c in ranges:
            hi = c.max_margin - 1 if c.max_margin is not None else _MARGIN_RANGE[-1]
            box[index[frozenset((c.winner, c.loser))]] = list(range(c.min_margin, hi + 1))
        flips = [i for i in range(R) if i in games]
        for k in range(1, 1 << len(flips)):
            other = mask
            for j, i in enumerate(flips):
                if k >> j & 1:
                    other ^= 1 << i
            known = table[other]
            if isinstance(known, dict):
                if any(known[combo] != outcome for combo in product(*box)):
                    return False
            elif known != outcome:
                return False
        return True

    # A sub-scenario stated in margin ranges drops any other game whose result can't change its
    # outcome within those ranges ("A beats B by 5 or more", whoever wins C-D).
    for mask, outs in outcomes.items():
        if len(outs) < 2:
            continue
        dropped = []
        for stated, open_groups, seeding, key in outs:
            free: frozenset = frozenset()
            if all(isinstance(c, GameResult) for c in stated):
                ranged = {frozenset((c.winner, c.loser)) for c in stated}
                for i, pair in enumerate(pairs):
                    if frozenset(pair) not in ranged and holds_without(
                        mask, stated, (seeding, open_groups), free | {i}
                    ):
                        free = free | {i}
            dropped.append((stated, open_groups, seeding, key, free))
        outcomes[mask] = dropped

    # Winner sets with one outcome merge by seeding; the rest list their outcomes as sub-scenarios.
    by_outcome: dict[tuple, list[int]] = defaultdict(list)
    for mask, outs in outcomes.items():
        if len(outs) == 1:
            _, open_groups, seeding, _ = outs[0][:4]
            by_outcome[(seeding, open_groups, open_places.get(mask, ()))].append(mask)
    entries = []
    for (seeding, open_groups, places), masks in by_outcome.items():
        for group in _valid_merge_groups(masks):
            winners = _common_game_winners(group, remaining)
            entries.append((min(group), "single", seeding, open_groups, (winners, places)))
    # Winner sets listing the very same outcomes under the very same conditions merge too: a game
    # that differs between them has no condition on it (one would name its winner), so it doesn't matter.
    by_listing: dict[tuple, list[int]] = defaultdict(list)
    for mask, outs in outcomes.items():
        if len(outs) > 1:
            by_listing[frozenset((st, o, sd, free) for st, o, sd, _, free in outs)].append(mask)
    for masks in by_listing.values():
        for group in _valid_merge_groups(masks):
            entries.append((min(group), "multi", None, _common_game_winners(group, remaining), outcomes[min(group)]))
    entries.sort(key=lambda e: e[0])

    def scenario(num, sub, winners, atom, open_groups, seeding, alternatives=None, places=()):
        return {
            "scenario_num": num,
            "sub_label": sub,
            "game_winners": winners,
            "conditions_atom": atom,
            "alternatives": alternatives,
            "open_groups": [(step, tuple(g)) for step, g in open_groups] or None,
            "open_places": {t: list(seeds) for t, seeds in places} or None,
            "tiebreaker_groups": None,
            "coinflip_groups": None,
            "seeding": seeding,
        }

    scenarios = []
    for num, (mask, kind, seeding, open_groups, data) in enumerate(entries, start=1):
        if kind == "single":
            winners, places = data
            scenarios.append(scenario(num, "", winners, None, open_groups, seeding, places=places))
            continue
        winners = open_groups  # for "multi" entries this slot carries the merged group's winners
        # One sub-scenario per outcome; the different ways to it (margin blocks, or tiebreaker routes)
        # are its alternatives, any one of which is enough.
        by_result: dict[tuple, list] = {}
        for stated, groups, seeding, key, free in sorted(data, key=lambda o: (o[3], len(o[0]))):
            # Every deciding game, with its margin range where the outcome needs one, then any decisions.
            mine = [(w, l) for w, l in winners if not any(set(pairs[i]) == {w, l} for i in free)]
            ranged = {(c.winner, c.loser): c for c in stated if isinstance(c, GameResult)}
            atom = [ranged.get((w, l), GameResult(w, l, 1, None)) for w, l in mine]
            atom += [c for c in stated if not isinstance(c, GameResult)]
            by_result.setdefault((seeding, groups), []).append((mine, atom))
        for k, ((seeding, groups), ways) in enumerate(by_result.items()):
            # The winners every alternative needs; each alternative's atom names the rest.
            shared = [w for w in ways[0][0] if all(w in mine for mine, _ in ways)]
            alts = [atom for _, atom in ways]
            scenarios.append(
                scenario(num, _sub_label(k), shared, alts[0], groups, seeding, alts if len(alts) > 1 else None)
            )
    if track:
        for sc in scenarios:
            places = tuple((t, tuple(seeds)) for t, seeds in (sc["open_places"] or {}).items())
            sc["p"], sc["p_weighted"] = finish_odds[_finish_key(sc["seeding"], sc["open_groups"] or (), places)]
    return scenarios


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_game_winners(game_winners: list[tuple[str, str]]) -> str:
    """Render a list of (winner, loser) pairs as plain English."""
    return " AND ".join(f"{w} beats {l}" for w, l in game_winners)


def _format_team_list(teams: list[str]) -> str:
    """Format a list of team names as 'A', 'A and B', or 'A, B, and C'."""
    if len(teams) == 1:
        return teams[0]
    if len(teams) == 2:
        return f"{teams[0]} and {teams[1]}"
    return ", ".join(teams[:-1]) + f", and {teams[-1]}"


_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four"}
_OPEN_REASON = {
    3: "order decided by the tiebreaker (point differential, then fewest points allowed)",
    4: "order decided by the tiebreaker (point differential, then fewest points allowed)",
    5: "order decided by fewest total points allowed in region games (any teams still tied start the tiebreakers over)",
    6: "order decided by a coin flip",
}


def render_scenarios(scenarios: list[dict], playoff_seeds: int = 4) -> str:
    """Render a pre-computed scenario list (from enumerate_division_scenarios or DB) as text.

    This is the decoupled rendering path — it does not re-run enumeration, so it
    can be called cheaply at request time using scenarios loaded from the database.

    A group whose order a scenario leaves to the tiebreaker (``open_groups``,
    or older snapshots' ``tiebreaker_groups``/``coinflip_groups``) is shown as
    one line over its places, saying what decides it, never as an order.

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

        seeding = list(sc["seeding"])
        # Groups whose order isn't stated: shown as one line over their places, never in an order.
        groups = [(step, list(g)) for step, g in sc.get("open_groups") or []]
        groups += [(3, list(g)) for g in sc.get("tiebreaker_groups") or []]  # older stored scenarios
        groups += [(6, list(g)) for g in sc.get("coinflip_groups") or []]
        at: dict[int, tuple[int, list[str]]] = {}
        for step, group in groups:
            spots = sorted(seeding.index(t) for t in group if t in seeding)
            if spots and spots[0] < playoff_seeds:
                at[spots[0]] = (step, [seeding[p] for p in spots])
        out_of_group: set[str] = set()
        i = 0
        while i < playoff_seeds:
            if i in at:
                step, members = at[i]
                last = min(i + len(members), playoff_seeds)
                places = f"{i + 1}-{last}" if last > i + 1 else f"{i + 1}"
                if last - i == len(members):
                    who = _format_team_list(members)
                elif last - i == 1:
                    who = ", ".join(members[:-1]) + f" or {members[-1]}"
                else:
                    who = f"{_COUNT_WORDS.get(last - i, last - i)} of {_format_team_list(members)}"
                lines.append(f"{places}. {who}: {_OPEN_REASON[min(step, 6)]}")
                out_of_group.update(members)
                i = last
            else:
                lines.append(f"{i + 1}. {seeding[i]}")
                i += 1

        eliminated = [t for t in seeding[playoff_seeds:] if t not in out_of_group]
        if len(eliminated) < len(seeding[playoff_seeds:]):
            eliminated.append("the rest of that tie")
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


# ---------------------------------------------------------------------------
# Pre-playoff home-game scenario integration
# ---------------------------------------------------------------------------


def build_pre_playoff_home_scenarios(
    team: str,
    region: int,
    season: int,
    slots: list,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    playoff_seeds: int = 4,
    win_prob_fn=None,
    team_lookup: dict | None = None,
) -> tuple[list, dict]:
    """Build pre-playoff home scenarios and scenario atoms for a team in one call.

    Combines ``enumerate_outcomes``, ``build_scenario_atoms``,
    and the ``bracket_home_odds`` helpers so
    the caller does not have to wire them together manually.

    The returned ``(home_scenarios, atoms)`` pair is ready to pass directly to
    ``render_pre_playoff_team_home_scenarios``.

    Args:
        team:          School name of the target team.
        region:        Region number (1–8 for 1A; same range for other classes).
        season:        Football season year (e.g. ``2025``).
        slots:         All first-round ``FormatSlot`` objects for the class/season
                       (e.g. ``SLOTS_1A_4A_2025``).
        teams:         All team names in the region.
        completed:     Completed region games.
        remaining:     Remaining (unplayed) region games.
        playoff_seeds: Number of seeds that advance to the playoffs (default 4).
        win_prob_fn:   Optional win-probability function
                       ``(r1, s1, r2, s2) -> float`` for weighted bracket odds.
                       Defaults to 50/50 (``equal_matchup_prob``).
        team_lookup:   Optional ``(region, seed) → school name`` mapping passed
                       through to ``enumerate_home_game_scenarios``.

    Returns:
        ``(home_scenarios, atoms)`` where

        * ``home_scenarios`` — ``list[RoundHomeScenarios]`` as returned by
          ``enumerate_home_game_scenarios``.
        * ``atoms`` — ``dict[team → dict[seed → list[atom]]]`` as returned by
          ``build_scenario_atoms``.

    Raises:
        ValueError: If *team* is not in *teams*, or has already been eliminated
                    (no achievable playoff seeds remain).
    """
    from backend.helpers.bracket_home_odds import (
        compute_bracket_advancement_odds,
        compute_quarterfinal_home_odds,
        compute_second_round_home_odds,
        compute_semifinal_home_odds,
        half_slots_for_region,
        slot_index_for,
        was_home_r1,
    )
    from backend.helpers.home_game_scenarios import enumerate_home_game_scenarios
    from backend.helpers.scenarios import determine_odds, determine_scenarios

    # 1. Build atoms and compute seeding odds.
    atoms = build_scenario_atoms(teams, completed, remaining, playoff_seeds=playoff_seeds)
    sr = determine_scenarios(teams, completed, remaining)
    region_odds = determine_odds(teams, sr.first_counts, sr.second_counts, sr.third_counts, sr.fourth_counts, sr.denom)

    # 2. Determine which seeds the target team can still achieve.
    team_odds = region_odds.get(team)
    if team_odds is None:
        raise ValueError(f"Team {team!r} not found in region data")
    achievable_seeds = [s for s in range(1, playoff_seeds + 1) if getattr(team_odds, f"p{s}", 0.0) > 0.0]
    if not achievable_seeds:
        raise ValueError(f"{team!r} has been eliminated — no achievable playoff seeds remain")

    # 3. Compute bracket advancement and hosting odds.
    kw: dict = {"win_prob_fn": win_prob_fn} if win_prob_fn is not None else {}
    ba = compute_bracket_advancement_odds(region, region_odds, slots, **kw)
    qf_host = compute_quarterfinal_home_odds(region, region_odds, slots, season, **kw)
    sf_host = compute_semifinal_home_odds(region, region_odds, slots, season, **kw)

    # 4. Compute R1 overall hosting probability: sum p_seed for seeds that are
    #    the designated home team in their R1 bracket slot.
    half_slots = half_slots_for_region(region, slots)
    is_1a_4a = len(half_slots) == 8
    overall_r1 = 0.0
    for s in achievable_seeds:
        idx = slot_index_for(region, s, half_slots)
        if idx is None:
            continue
        if was_home_r1(region, s, half_slots[idx]):
            overall_r1 += getattr(team_odds, f"p{s}", 0.0)

    tay_ba = ba[team]
    p_reach: dict[str, float] = {
        "First Round": 1.0,
        "Quarterfinals": tay_ba.quarterfinals,
        "Semifinals": tay_ba.semifinals,
    }
    overall: dict[str, float] = {
        "First Round": overall_r1,
        "Quarterfinals": qf_host[team],
        "Semifinals": sf_host[team],
    }

    if is_1a_4a:
        r2_host = compute_second_round_home_odds(region, region_odds, slots, season, **kw)
        p_reach["Second Round"] = tay_ba.second_round
        overall["Second Round"] = r2_host[team]

    given_reach: dict[str, float] = {rn: overall[rn] / p_reach[rn] for rn in p_reach if p_reach[rn] > 0.0}

    # 5. Enumerate home scenarios with pre-computed odds.
    home_scenarios = enumerate_home_game_scenarios(
        region=region,
        seed=None,
        slots=slots,
        season=season,
        achievable_seeds=achievable_seeds,
        p_reach_by_round=p_reach,
        p_host_overall_by_round=overall,
        p_host_given_reach_by_round=given_reach,
        team_lookup=team_lookup,
    )

    return home_scenarios, atoms


def render_team_pre_playoff_home_scenarios(
    team: str,
    region: int,
    season: int,
    slots: list,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    playoff_seeds: int = 4,
    win_prob_fn=None,
    team_lookup: dict | None = None,
) -> str:
    """Enumerate and render pre-playoff home scenarios for a team as human-readable text.

    Convenience wrapper that calls ``build_pre_playoff_home_scenarios`` then
    ``render_pre_playoff_team_home_scenarios``.  All parameters are forwarded
    to the underlying functions unchanged.

    Args:
        team:          School name of the target team.
        region:        Region number.
        season:        Football season year.
        slots:         All first-round ``FormatSlot`` objects for the class/season.
        teams:         All team names in the region.
        completed:     Completed region games.
        remaining:     Remaining (unplayed) region games.
        playoff_seeds: Number of seeds that advance to the playoffs (default 4).
        win_prob_fn:   Optional win-probability function for weighted odds.
        team_lookup:   Optional ``(region, seed) → school name`` mapping.

    Returns:
        Multi-line string suitable for printing to a terminal or text file.

    Raises:
        ValueError: If the team is not in the region data or has been eliminated.
    """
    from backend.helpers.scenario_renderer import render_pre_playoff_team_home_scenarios

    home_scenarios, atoms = build_pre_playoff_home_scenarios(
        team=team,
        region=region,
        season=season,
        slots=slots,
        teams=teams,
        completed=completed,
        remaining=remaining,
        playoff_seeds=playoff_seeds,
        win_prob_fn=win_prob_fn,
        team_lookup=team_lookup,
    )
    return render_pre_playoff_team_home_scenarios(team, home_scenarios, atoms)
