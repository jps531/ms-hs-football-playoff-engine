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


def _derive_atom(
    mask: int,
    valid_margins_list: list[dict],
    remaining: list[RemainingGame],
    pairs: list[tuple[str, str]],
) -> list:
    """Derive a human-readable atom (GameResult + MarginCondition list) for a (mask, seeding) group.

    Algorithm:
    1. Compute per-game margin ranges ``[lo_i, hi_i]`` from the valid margin set.
    2. Build a ``GameResult`` for each game using the derived range.
    3. Find margin-sensitive game indices (range is a proper subset of ``[1,12]``).
    4. If exactly 2 margin-sensitive games, try to add sum/diff ``MarginCondition``
       objects that tighten the description and verify they reproduce the valid set.
    5. Fall back to per-game ranges only if joint constraints cannot be verified.

    Returns a list of ``GameResult`` and (optionally) ``MarginCondition`` objects.
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

    # --- Step 3: find margin-sensitive game indices ---
    sens_indices = [i for i in range(R) if not (lows[i] == 1 and highs[i] == 12)]

    if len(sens_indices) != 2:
        # Joint constraints only attempted for exactly 2 sensitive games
        return atom

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
        return atom

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
        return unconstrained_atom + margin_conds

    predicted = _predict_valid_set_2d(lo0, hi0, lo1, hi1, margin_conds, pair0, pair1)

    if predicted == valid_2d:
        return atom + margin_conds

    # Fallback: per-game ranges only (always a superset; _find_combined_atom
    # uses sample_margins to select the right atom anyway)
    return atom


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
    4. Unconstrained groups (covering all 12^R margins for a mask) are merged
       across masks — games whose winner varies across masks are omitted.

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

    # --- Step 2: Identify unconstrained groups (cover all 12^R margins for mask) ---
    unconstrained_keys: set[tuple] = {k for k, ml in groups.items() if len(ml) == total_combos}

    # Collect unconstrained masks per (team, seed) across ALL top-N orderings
    team_seed_unc_masks: dict[tuple, list[int]] = {}
    for (mask, top4) in unconstrained_keys:
        for seed_idx, team in enumerate(top4):
            team_seed_unc_masks.setdefault((team, seed_idx + 1), []).append(mask)

    result: dict[str, dict[int, list]] = {}

    # --- Step 3: Unconstrained atoms — partition into valid merge groups ---
    for (team, seed), masks in team_seed_unc_masks.items():
        for group in _valid_merge_groups(masks, R):
            game_winners = _common_game_winners(group, remaining)
            atom: list = [GameResult(w, l, 1, None) for w, l in game_winners]
            result.setdefault(team, {}).setdefault(seed, []).append(atom)

    # --- Step 4: Constrained atoms — derive ranges + joint constraints per group ---
    for (mask, top4), valid_margins_list in groups.items():
        if (mask, top4) in unconstrained_keys:
            continue
        atom = _derive_atom(mask, valid_margins_list, remaining, pairs)
        for seed_idx, team in enumerate(top4):
            result.setdefault(team, {}).setdefault(seed_idx + 1, []).append(atom)

    # --- Step 5: Eliminated atoms (seed > playoff_seeds) via cross-mask merging ---
    # A team is "always eliminated" under mask M if it appears in NO top-N group for M.
    teams_in_any_top4: dict[int, set[str]] = {mask: set() for mask in range(1 << R)}
    for (mask, top4) in groups:
        teams_in_any_top4[mask].update(top4)

    for team in teams:
        elim_masks = [m for m in range(1 << R) if team not in teams_in_any_top4[m]]
        if not elim_masks:
            continue
        # Also check for masks where team is sometimes eliminated (constrained)
        # — handle via unconstrained merging only for masks where always eliminated
        game_winners = _common_game_winners(elim_masks, remaining)
        atom = [GameResult(w, l, 1, None) for w, l in game_winners]
        elim_seed = playoff_seeds + 1
        result.setdefault(team, {}).setdefault(elim_seed, []).append(atom)

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
        min_mask = min(masks)
        game_winners = _common_game_winners(masks, remaining)
        entries.append((min_mask, "single", seeding, masks, game_winners))

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
