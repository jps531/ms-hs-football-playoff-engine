"""Enumerate and render complete seeding outcomes for a division.

For a given division (teams + completed + remaining games), enumerates every
distinct seeding outcome and the game conditions that produce it.  Scenarios
that are identical regardless of one game's winner automatically omit that
game from the conditions.  Margin-sensitive masks (where winning margins change
the seeding) are presented as lettered sub-scenarios (6a, 6b, …).
"""

from collections import defaultdict
from itertools import product

from backend.helpers.data_classes import CompletedGame, RemainingGame
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
                # Direction: "le" for <= or <;  "ge" for >= or >
                direction = "le" if cond.op in ("<=", "<") else "ge"
                key = (cond.add, cond.sub, direction)
                # Normalise threshold to strict-inequality-free form
                t = cond.threshold
                if cond.op == "<":
                    t -= 1
                elif cond.op == ">":
                    t += 1
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
