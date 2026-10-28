"""Render playoff scenario atoms as human-readable text."""

from dataclasses import replace
from datetime import date
from typing import cast

from backend.helpers.certainty import CERTAIN_EPS
from backend.helpers.data_classes import (
    CoinFlipResult,
    GameResult,
    HomeGameCondition,
    HomeGameScenario,
    MarginCondition,
    PDRankCondition,
    RoundHomeScenarios,
    RoundMatchups,
    TiebreakDecision,
    TiebreakPlace,
)
from backend.helpers.engine_settings import PLAYOFF_SEEDS
from backend.helpers.scenario_serializers import serialize_atom, serialize_condition


def margin_phrase(min_margin: int, max_margin: int | None) -> str:
    """Render a winning-margin range as a trailing phrase (e.g. " by 8 or more").

    ``max_margin`` is exclusive; ``None`` means unbounded. A plain win (1 or
    more, unbounded) renders as the empty string.
    """
    if min_margin <= 1 and max_margin is None:
        return ""
    if max_margin is not None and max_margin == min_margin + 1:
        return f" by exactly {min_margin}"
    if max_margin is None:
        return f" by {min_margin} or more"
    return f" by {min_margin}\u2013{max_margin - 1}"


def _render_game_result(cond: GameResult) -> str:
    """Render a GameResult as a plain-English phrase."""
    return f"{cond.winner} beats {cond.loser}{margin_phrase(cond.min_margin, cond.max_margin)}"


def _winner_label(pair: tuple[str, str], atom: list) -> str:
    """Return the winner's name for a game pair, inferred from GameResult conditions in the atom."""
    a, b = pair
    for cond in atom:
        if isinstance(cond, GameResult):
            if (cond.winner == a and cond.loser == b) or (cond.winner == b and cond.loser == a):
                return cond.winner
    return f"{a}/{b}"


# Point differential caps each game at 12, so margin comparisons are of capped margins; every one says so.
_CAP_NOTE = " (a margin over 12 counts as 12)"


def _render_margin_condition(cond: MarginCondition, atom: list) -> str:
    """Render a MarginCondition as a plain-English phrase using winner labels from the atom.

    A comparison of two games reads "Sebastopol wins by at least 3 more points than McAdams", and a
    sum "Sebastopol's and McAdams's winning margins add up to 10 or more", each with the 12-point cap.
    """
    if len(cond.add) == 2 and not cond.sub:
        l1 = _winner_label(cond.add[0], atom)
        l2 = _winner_label(cond.add[1], atom)
        if cond.op == "==":
            return f"{l1}'s and {l2}'s winning margins add up to exactly {cond.threshold}{_CAP_NOTE}"
        if cond.op in (">=", ">"):
            t = cond.threshold + (1 if cond.op == ">" else 0)
            return f"{l1}'s and {l2}'s winning margins add up to {t} or more{_CAP_NOTE}"
        t = cond.threshold - (1 if cond.op == "<" else 0)
        return f"{l1}'s and {l2}'s winning margins add up to {t} or less{_CAP_NOTE}"

    if len(cond.add) == 1 and len(cond.sub) == 1:
        a = _winner_label(cond.add[0], atom)
        b = _winner_label(cond.sub[0], atom)
        if cond.op == "==":
            t = cond.threshold
            if t < 0:
                a, b, t = b, a, -t
            if t == 0:
                return f"{a} and {b} win by the same margin{_CAP_NOTE}"
            return f"{a} wins by exactly {t} more {_points(t)} than {b}{_CAP_NOTE}"
        # a's margin minus b's is at least t ("at_least") or at most t.
        at_least = cond.op in (">=", ">")
        t = cond.threshold + (1 if cond.op == ">" else -1 if cond.op == "<" else 0)
        if t < 0:  # a − b ≥ −t is b − a ≤ t, and the other way round
            a, b, t, at_least = b, a, -t, not at_least
        if at_least:
            if t == 0:
                return f"{a} wins by at least as many points as {b}{_CAP_NOTE}"
            return f"{a} wins by at least {t} more {_points(t)} than {b}{_CAP_NOTE}"
        if t == 0:
            return f"{a} wins by no more points than {b}{_CAP_NOTE}"
        return f"{a} wins by no more than {t} more {_points(t)} than {b}{_CAP_NOTE}"

    # Fallback for other patterns
    parts = [f"{_winner_label(p, atom)}'s winning margin" for p in cond.add]
    parts += [f"\u2212{_winner_label(p, atom)}'s winning margin" for p in cond.sub]
    return " + ".join(parts) + f" {cond.op} {cond.threshold}{_CAP_NOTE}"


def _points(n: int) -> str:
    """"point" or "points"."""
    return "point" if n == 1 else "points"


def _join(names) -> str:
    """ "A", "A and B", "A, B and C"."""
    names = list(names)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def render_tiebreak_decision(cond: TiebreakDecision) -> str:
    """One tiebreaker decision in words, e.g. "Point differential in games among A, B and C (capped at
    12 a game): A best, then B and C, level"."""
    if cond.step == 3:
        lead = f"Point differential in games among {_join(cond.group)} (capped at 12 a game)"
    else:
        # Step 4 only comes into it when step 3 left them level, so say so: read alone, it could match.
        lead = (
            f"{_join(cond.group)} level on point differential in games among them, so on point differential "
            "(capped at 12 a game) against the highest-placed region team outside the tie, then the next-highest, "
            "and so on, stopping at the first team where they differ"
        )
    if len(cond.parts) == 1:
        return f"{lead}: {'both' if len(cond.group) == 2 else 'all'} level"
    top, *rest = cond.parts
    first = f"{_join(top)} best" if len(top) == 1 else f"{_join(top)} tied for best"
    return f"{lead}: {first}, " + ", ".join(f"then {_join(p)}" + (", level" if len(p) > 1 else "") for p in rest)


def render_open_group(step: int, group) -> str:
    """A group a scenario leaves to the tiebreaker from *step* on, in words."""
    teams = _join(group)
    if step >= 6:
        return f"{teams} are level on every tiebreaker: a coin flip decides their order"
    if step == 5:
        return (
            f"{teams} are still level: fewest total points allowed in region games decides their order "
            "(any teams still tied start the tiebreakers over)"
        )
    return (
        f"{teams} tie: their order is decided by point differential in games among them, then in games "
        "against the highest-finishing teams (capped at 12 a game), then fewest points allowed"
    )


_PLACE_WORDS = {2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}
_COUNT_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
_TIE_DECIDED_BY = {
    6: "which a coin flip decides",
    5: "which goes to fewest total points allowed in region games (any teams still tied start the tiebreakers over)",
}


def render_tiebreak_place(cond: TiebreakPlace) -> str:
    """A team's place in a tie left to the tiebreaker, in words, e.g. "Raleigh finishes ahead of both
    Magee and Seminary in their tie, which goes to fewest total points allowed in region games (any teams still tied
    start the tiebreakers over)"."""
    others = [t for t in cond.group if t != cond.team]
    both = "both " if len(others) == 2 else ""
    if cond.place == 1:
        where = f"ahead of {both}{_join(others)} in their tie"
    elif cond.place == len(cond.group):
        where = f"behind {both}{_join(others)} in their tie"
    else:
        place = _PLACE_WORDS.get(cond.place, f"{cond.place}th")
        count = _COUNT_WORDS.get(len(cond.group), str(len(cond.group)))
        where = f"{place} of the {count} in the tie with {_join(others)}"
    how = _TIE_DECIDED_BY.get(
        cond.step, "which goes to the tiebreaker (point differential, then fewest points allowed)"
    )
    return f"{cond.team} finishes {where}, {how}"


def _render_condition(cond, atom: list) -> str:
    """Dispatch to the appropriate renderer based on the condition type."""
    if isinstance(cond, GameResult):
        return _render_game_result(cond)
    if isinstance(cond, MarginCondition):
        return _render_margin_condition(cond, atom)
    if isinstance(cond, CoinFlipResult):
        return f"{cond.winner} wins the coin flip against {cond.loser}"
    if isinstance(cond, TiebreakDecision):
        return render_tiebreak_decision(cond)
    if isinstance(cond, TiebreakPlace):
        return render_tiebreak_place(cond)
    if isinstance(cond, PDRankCondition):
        ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
        ord_str = ordinals.get(cond.rank, f"{cond.rank}th")
        return f"{cond.team} finishes {ord_str} in point differential"
    return str(cond)


def _render_atom(atom: list) -> str:
    """Render a list of conditions as a single AND-joined plain-English clause."""
    return " AND ".join(_render_condition(c, atom) for c in atom)


def render_scenario_title(sc: dict) -> str:
    """Return a human-readable title for a single complete-scenario dict.

    If *sc* has a ``conditions_atom``, renders it through ``_render_atom``;
    otherwise falls back to joining the ``game_winners`` list.
    """
    if sc.get("alternatives"):
        # What every alternative needs once, then the ways they differ.
        alts = sc["alternatives"]
        shared = [c for c in alts[0] if all(c in alt for alt in alts[1:])]
        ways = " OR ".join(f"({_render_atom([c for c in alt if c not in shared])})" for alt in alts)
        title = " AND ".join([t for t in (_render_atom(shared),) if t] + [ways])
    elif sc.get("conditions_atom") is not None:
        title = _render_atom(sc["conditions_atom"])
    else:
        title = " AND ".join(f"{w} beats {l}" for w, l in sc.get("game_winners", []))
    groups = [render_open_group(step, g) for step, g in sc.get("open_groups") or []]
    return " AND ".join([t for t in (title,) if t] + groups)


def atoms_from_complete_scenarios(
    complete_scenarios: list[dict], playoff_seeds: int = PLAYOFF_SEEDS
) -> dict[str, dict[int, list[list]]]:
    """Reconstruct a per-team per-seed atom dict from stored complete-scenario dicts.

    This is O(S × N) where S is the number of scenarios and N the team count.
    The result has ``build_scenario_atoms``' shape (every place past the
    playoff seeds is ``playoff_seeds + 1``, eliminated) and can be passed directly to
    ``team_scenarios_as_dict``. Complete scenarios say only what the
    tiebreaker decides, so the paths built from them do too.

    A scenario with alternatives contributes each one. A team in one of its
    open groups (a tie whose order the scenario leaves to the tiebreaker)
    reaches each of the group's places it can (``open_places``, else all of
    them) only by finishing there in that tie, so each of its atoms for those
    places carries a ``TiebreakPlace``, unless the scenario states the team's
    places exactly in margins (``place_terms``): then each place's atoms are
    the scenario's winners narrowed by those margin conditions.
    """
    out = playoff_seeds + 1
    atoms: dict[str, dict[int, list]] = {}
    for sc in complete_scenarios:
        alternatives = sc.get("alternatives") or [sc.get("conditions_atom")]
        alternatives = [
            a if a is not None else [GameResult(winner=w, loser=l) for w, l in sc.get("game_winners", [])]
            for a in alternatives
        ]
        seeding = list(sc.get("seeding", ()))
        open_of = {t: (step, tuple(g)) for step, g in sc.get("open_groups") or [] for t in g}
        exact = sc.get("place_terms") or {}
        for seed_idx, team in enumerate(seeding):
            team_map = atoms.setdefault(team, {})
            if team in exact:
                for seed, ways in exact[team]:
                    team_map.setdefault(seed, []).extend(_narrow(a, term) for a in alternatives for term in ways)
                continue
            if team not in open_of:
                team_map.setdefault(min(seed_idx + 1, out), []).extend(list(a) for a in alternatives)
                continue
            step, group = open_of[team]
            places = sorted(seeding.index(t) for t in group)
            reach = set((sc.get("open_places") or {}).get(team) or (min(i + 1, out) for i in places))
            for place, idx in enumerate(places, start=1):
                if min(idx + 1, out) in reach:
                    tie = TiebreakPlace(team, place, group, step)
                    team_map.setdefault(min(idx + 1, out), []).extend([*a, tie] for a in alternatives)
    return atoms


def _narrow(atom: list, term) -> list:
    """*atom* with *term*'s conditions: its margin ranges replace the same games' plain wins, and its
    margin comparisons are added."""
    ranged = {frozenset((c.winner, c.loser)): c for c in term if isinstance(c, GameResult)}
    out = [ranged.pop(frozenset((c.winner, c.loser)), c) if isinstance(c, GameResult) else c for c in atom]
    return out + list(ranged.values()) + [c for c in term if not isinstance(c, GameResult)]


def _pct(p: float) -> str:
    """A probability as a percentage to one decimal, never rounding a possible outcome to 0 or a
    possible miss to 100: "<0.1%" and ">99.9%" instead (see ``backend.helpers.certainty``)."""
    if CERTAIN_EPS < p < 0.0005:
        return "<0.1%"
    if 0.9995 < p < 1 - CERTAIN_EPS:
        return ">99.9%"
    return f"{p * 100:.1f}%"


def render_team_scenarios(
    team: str,
    scenarios: dict[str, dict[int, list[list]]],
    playoff_seeds: int = PLAYOFF_SEEDS,
    odds: dict | None = None,
    weighted_odds: dict | None = None,
) -> str:
    """Return a human-readable string of playoff scenarios for a team.

    Special cases:
    - If the team has no playoff-seed atoms at all: "Eliminated."
    - If the team has exactly one playoff seed and no eliminated atoms: "Clinched #N seed."
    - Otherwise: list only the seeds that are present, plus "Eliminated if:" when applicable.

    Args:
        team: Team name to render.
        scenarios: Mapping of team -> seed -> list of condition atoms.
        playoff_seeds: Number of playoff seeds (default 4).
        odds: Optional mapping of team name -> StandingsOdds (equal win probability);
            when provided, per-seed and elimination probabilities are appended to
            each section header as "(XX.X%)".
        weighted_odds: Optional mapping of team name -> StandingsOdds computed with
            a win-probability function; when provided, weighted probabilities are
            appended as "(XX.X% Weighted)". When both ``odds`` and ``weighted_odds``
            are given, both values appear as "(XX.X% \u2013 XX.X% Weighted)".
    """
    seed_map = scenarios.get(team, {})
    team_odds = odds.get(team) if odds else None
    team_weighted = weighted_odds.get(team) if weighted_odds else None

    playoff_seed_entries = {seed: atoms for seed, atoms in seed_map.items() if seed <= playoff_seeds}
    eliminated_atoms: list[list] = [atom for seed, atoms in seed_map.items() if seed > playoff_seeds for atom in atoms]

    def _odds_suffix(p_unweighted: float | None, p_weighted: float | None) -> str:
        """Format an odds suffix from zero, one, or both probability values."""
        if p_unweighted is None and p_weighted is None:
            return ""
        if p_unweighted is not None and p_weighted is not None:
            return f" ({_pct(p_unweighted)} \u2013 {_pct(p_weighted)} Weighted)"
        if p_weighted is not None:
            return f" ({_pct(p_weighted)} Weighted)"
        return f" ({_pct(p_unweighted)})"  # type: ignore[operator]

    def _seed_suffix(seed: int) -> str:
        """Return the formatted odds suffix for the given seed position."""
        p_u = getattr(team_odds, f"p{seed}") if team_odds else None
        p_w = getattr(team_weighted, f"p{seed}") if team_weighted else None
        return _odds_suffix(p_u, p_w)

    def _elim_suffix() -> str:
        """Return the formatted odds suffix for the eliminated outcome."""
        p_u = (1.0 - team_odds.p_playoffs) if team_odds else None
        p_w = (1.0 - team_weighted.p_playoffs) if team_weighted else None
        return _odds_suffix(p_u, p_w)

    # Fully eliminated — never makes the playoffs
    if not playoff_seed_entries:
        return f"{team}\n\nEliminated.{_elim_suffix()}"

    # Clinched — only one possible playoff seed and cannot be eliminated
    if len(playoff_seed_entries) == 1 and not eliminated_atoms:
        (seed,) = playoff_seed_entries
        return f"{team}\n\nClinched #{seed} seed.{_seed_suffix(seed)}"

    # General case — list only present seeds and eliminated section
    sections: list[tuple[str, list[list]]] = []
    for seed in sorted(playoff_seed_entries):
        sections.append((f"#{seed} seed if:{_seed_suffix(seed)}", playoff_seed_entries[seed]))
    if eliminated_atoms:
        sections.append((f"Eliminated if:{_elim_suffix()}", eliminated_atoms))

    lines = [team, ""]
    for label, atoms in sections:
        lines.append(label)
        for i, atom in enumerate(atoms, 1):
            lines.append(f"{i}. {_render_atom(atom)}")
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# margin_class taxonomy
# ---------------------------------------------------------------------------

# Ascending (min_margin threshold, label) pairs. The underlying margin scale
# used throughout the engine is capped at 12 ("12 or more" — see
# `scenarios.py`'s `product(range(1, 13), ...)` enumeration), so finer buckets
# beyond two aren't distinguishable from stored data. Tune freely — this is a
# display taxonomy, not a computation input.
_MARGIN_CLASS_BUCKETS: list[tuple[int, str]] = [
    (1, "one_score"),
    (9, "two_plus_scores"),
]


def classify_margin(min_margin: int, max_margin: int | None) -> str | None:
    """Bucket a ``GameResult`` margin range into a named ``margin_class``.

    Returns ``None`` for a plain win/loss condition (``min_margin=1,
    max_margin=None``) — margin doesn't factor into it, so there's nothing to
    classify. Otherwise buckets by ``min_margin`` (the binding "wins by at
    least N" threshold).
    """
    if min_margin <= 1 and max_margin is None:
        return None
    label = _MARGIN_CLASS_BUCKETS[0][1]
    for threshold, name in _MARGIN_CLASS_BUCKETS:
        if min_margin >= threshold:
            label = name
    return label


_ROUND_KEY = {
    "First Round": "first_round",
    "Second Round": "second_round",
    "Quarterfinals": "quarterfinals",
    "Semifinals": "semifinals",
}


# ---------------------------------------------------------------------------
# Path condition dicts (for the §8 `paths` API contract)
# ---------------------------------------------------------------------------


def atom_condition_dicts(atom: list, game_dates: dict[tuple[str, str], date | None]) -> list[dict]:
    """Convert one minimized atom (AND-group of conditions) to condition dicts.

    Produces the plain-dict shape backing ``PathConditionModel``: the common
    ``GameResult`` case becomes a single-game ``"game_result"`` dict
    (``school`` is always the winner, ``required_result`` always ``"win"`` —
    callers needing the loser's perspective invert it — plus the exact
    ``min_margin``/``max_margin`` bounds, ``max_margin`` exclusive and ``None``
    when unbounded); a multi-game ``MarginCondition`` becomes a
    ``"margin_sum"`` dict since it doesn't reduce to one school/opponent pair,
    with its plain-English rendering in ``description``; tiebreaker-only
    ``CoinFlipResult``/``PDRankCondition`` (not tied to any remaining game)
    become ``"coin_flip"``/``"pd_rank"`` dicts carrying only descriptive text.

    Args:
        atom: One AND-group of conditions from a ``scenario_atoms`` entry.
        game_dates: Canonical ``(lower, higher)`` team-name pair -> scheduled
            date (or ``None`` when unresolvable).

    Returns:
        List of condition dicts, one per input condition, JSON-serializable
        and directly constructible into ``PathConditionModel``.
    """
    result: list[dict] = []
    for cond in atom:
        if isinstance(cond, GameResult):
            pair = cast(tuple[str, str], tuple(sorted((cond.winner, cond.loser))))
            result.append(
                {
                    "type": "game_result",
                    "school": cond.winner,
                    "date": game_dates.get(pair),
                    "opponent": cond.loser,
                    "required_result": "win",
                    "margin_class": classify_margin(cond.min_margin, cond.max_margin),
                    "min_margin": cond.min_margin,
                    "max_margin": cond.max_margin,
                }
            )
        elif isinstance(cond, MarginCondition):
            games = []
            for a, b in list(cond.add) + list(cond.sub):
                pair = cast(tuple[str, str], tuple(sorted((a, b))))
                # Each game from its winner's side, as a game_result is (as given if the atom doesn't say).
                winner = _winner_label((a, b), atom)
                winner = winner if winner in (a, b) else a
                games.append({"school": winner, "date": game_dates.get(pair), "opponent": b if winner == a else a})
            result.append(
                {
                    "type": "margin_sum",
                    "games": games,
                    "op": cond.op,
                    "threshold": cond.threshold,
                    "description": _render_margin_condition(cond, atom),
                }
            )
        elif isinstance(cond, CoinFlipResult):
            result.append({"type": "coin_flip", "description": str(cond)})
        elif isinstance(cond, PDRankCondition):
            result.append({"type": "pd_rank", "description": str(cond)})
        elif isinstance(cond, TiebreakDecision):
            result.append({"type": "tiebreak", "description": render_tiebreak_decision(cond)})
        elif isinstance(cond, TiebreakPlace):
            result.append({"type": "tiebreak", "description": render_tiebreak_place(cond)})
        else:  # never drop a condition silently: a card without it would claim more than is true
            raise TypeError(f"no path rendering for {type(cond).__name__}")
    return result


def _resolve_home_condition_team_name(cond: HomeGameCondition, team_name: str) -> HomeGameCondition:
    """Return a copy of *cond* with an unset ``team_name`` resolved to a display label.

    ``region is None`` means the condition is about the target team itself
    (resolved to *team_name*); otherwise it's about another bracket position,
    which falls back to ``"Region X #Y Seed"`` when that position's occupant
    isn't yet clinched (no ``team_lookup`` entry was available upstream).
    """
    if cond.team_name is not None:
        return cond
    if cond.region is None:
        return cast(HomeGameCondition, replace(cond, team_name=team_name))
    return cast(HomeGameCondition, replace(cond, team_name=f"Region {cond.region} #{cond.seed} Seed"))


def home_condition_to_path_dict(cond: HomeGameCondition) -> dict:
    """Convert one *resolved* ``HomeGameCondition`` to a ``PathConditionModel``-compatible dict.

    Expects ``cond.team_name`` to already be resolved (see
    ``_resolve_home_condition_team_name``) — unlike ``_render_condition_label``,
    which renders a generic ``"Team ..."`` placeholder for later text
    substitution, this produces the final ``description`` directly.
    """
    if cond.kind == "seed_required":
        return {
            "type": "seed_required",
            "school": cond.team_name,
            "seed": cond.seed,
            "description": f"{cond.team_name} finishes as the #{cond.seed} seed",
        }
    if cond.kind == "wins_round":
        return {
            "type": "bracket_win",
            "school": cond.team_name,
            "region": cond.region,
            "seed": cond.seed,
            "round_name": cond.round_name,
            "description": f"Beats {cond.team_name} in the {cond.round_name}",
        }
    # kind == "advances"
    return {
        "type": "bracket_advances",
        "school": cond.team_name,
        "region": cond.region,
        "seed": cond.seed,
        "round_name": cond.round_name,
        "description": f"{cond.team_name} advances to {cond.round_name}",
    }


def expand_and_render_conditions(
    team: str,
    and_groups: list[list[HomeGameCondition]],
    seed_atoms: dict[str, dict[int, list[list]]] | None,
    game_dates: dict[tuple[str, str], date | None],
) -> list[list[dict]]:
    """Render AND-groups of ``HomeGameCondition`` as ``PathConditionModel`` OR-of-AND dicts.

    Shared by ``build_host_conditions`` (``host_conditions``, sourced from
    ``HomeGameScenario.conditions``) and ``build_reach_conditions``
    (``reach_conditions``, sourced from ``enumerate_reach_scenarios_for_team``)
    — both need the same "expand a leading ``seed_required`` placeholder into
    the real regular-season game atom(s), when known; otherwise resolve and
    render each condition directly" logic. A pre-playoff ``seed_required``
    placeholder is expanded via ``atom_condition_dicts`` (the same
    §8 ``paths`` dict shape) when *seed_atoms* covers it; otherwise it's left
    as an unexpanded, descriptive condition. An empty inner list means a
    group is unconditional (matches ``HomeGameScenario.conditions``' own
    "empty = unconditional" convention). Returns ``[]`` given no groups.
    """
    result: list[list[dict]] = []
    for conds in and_groups:
        if not conds:
            result.append([])
            continue
        first = conds[0]
        atoms = (
            seed_atoms.get(team, {}).get(first.seed, [])
            if seed_atoms and first.kind == "seed_required" and first.region is None and first.seed is not None
            else []
        )
        if atoms:
            remaining_resolved = [_resolve_home_condition_team_name(c, team) for c in conds[1:]]
            remaining_dicts = [home_condition_to_path_dict(c) for c in remaining_resolved]
            for atom in atoms:
                result.append(atom_condition_dicts(atom, game_dates) + remaining_dicts)
        else:
            resolved = [_resolve_home_condition_team_name(c, team) for c in conds]
            result.append([home_condition_to_path_dict(c) for c in resolved])
    return result


def build_host_conditions(
    team: str,
    round_scenarios: RoundHomeScenarios,
    seed_atoms: dict[str, dict[int, list[list]]] | None,
    game_dates: dict[tuple[str, str], date | None],
) -> list[list[dict]]:
    """Return *team*'s ``will_host`` scenarios for one round as ``PathConditionModel`` OR-of-AND groups.

    Mirrors ``team_home_scenarios_as_dict``'s ``will_host`` + seed-atom
    expansion pipeline, but emits ``atom_condition_dicts``/
    ``home_condition_to_path_dict`` dicts (this endpoint's contract) instead
    of ``serialize_atom``/``serialize_condition`` (``TeamHostingEntry.scenarios``'
    contract) — see ``expand_and_render_conditions`` for the shared expansion
    logic. Returns ``[]`` when the team never hosts this round.
    """
    return expand_and_render_conditions(
        team, [list(sc.conditions) for sc in round_scenarios.will_host], seed_atoms, game_dates
    )


def build_reach_conditions(
    team: str,
    and_groups: list[list[HomeGameCondition]],
    seed_atoms: dict[str, dict[int, list[list]]] | None,
    game_dates: dict[tuple[str, str], date | None],
) -> list[list[dict]]:
    """Return *team*'s reach-scenario AND-groups (from
    ``enumerate_reach_scenarios_for_team``) as ``PathConditionModel``
    OR-of-AND groups — see ``expand_and_render_conditions`` for the shared
    expansion logic. Returns ``[[]]`` when reaching the round is
    unconditional (e.g. First Round); never ``[]`` for a team that can reach
    the round at all.
    """
    return expand_and_render_conditions(team, and_groups, seed_atoms, game_dates)


# ---------------------------------------------------------------------------
# Structured dict renderers (for frontend / API consumption)
# ---------------------------------------------------------------------------

_SEED_FIELD_NAMES = ["one_seed", "two_seed", "three_seed", "four_seed"]


def division_scenarios_as_dict(
    scenarios: list[dict],
    playoff_seeds: int = PLAYOFF_SEEDS,
) -> dict[str, dict]:
    """Return division scenarios as a structured dict keyed by scenario label.

    Converts the raw scenario list from ``enumerate_division_scenarios`` into a
    frontend-friendly mapping where each entry has a human-readable title and
    named seed/eliminated fields.

    Args:
        scenarios: List of scenario dicts from ``enumerate_division_scenarios``.
        playoff_seeds: Number of playoff seeds (default 4).

    Returns:
        ``dict[scenario_key → entry]`` where ``scenario_key`` is e.g. ``"1"``,
        ``"2"``, ``"4a"``, ``"4b"``, and each entry is::

            {
                "title": str,          # human-readable conditions
                "one_seed": str,       # team finishing 1st
                "two_seed": str,       # team finishing 2nd
                "three_seed": str,     # team finishing 3rd
                "four_seed": str,      # team finishing 4th
                "eliminated": list[str],   # teams outside the top seeds
                "open_groups": list[list[str]],  # ties left to the tiebreaker: their
                                                 # members' places above are alphabetical
            }
    """
    seed_fields = _SEED_FIELD_NAMES[:playoff_seeds]

    # Pass 1: build entries (deduplicating identical title+seeding), preserving
    # the original scenario_num grouping so sub-labels stay together.
    seen_display: set[tuple] = set()
    deduped: list[tuple[int, str, str, tuple, list]] = []  # (orig_num, sub_label, title, seeding, open groups)
    for sc in scenarios:
        title = render_scenario_title(sc)
        seeding = sc["seeding"]
        display_key = (title, seeding)
        if display_key in seen_display:
            continue
        seen_display.add(display_key)
        groups = [list(g) for _, g in sc.get("open_groups") or []]
        deduped.append((sc["scenario_num"], sc["sub_label"], title, seeding, groups))

    # Pass 2: re-number sequentially so gaps left by dedup don't appear in keys.
    # Groups of sub-scenarios (same orig_num) get the same new number.
    result: dict[str, dict] = {}
    new_num = 0
    prev_orig_num: int | None = None
    for orig_num, sub_label, title, seeding, groups in deduped:
        if orig_num != prev_orig_num:
            new_num += 1
            prev_orig_num = orig_num
        key = str(new_num) + sub_label
        entry: dict = {"title": title}
        for i, field in enumerate(seed_fields):
            entry[field] = seeding[i] if i < len(seeding) else None
        entry["eliminated"] = list(seeding[playoff_seeds:])
        entry["open_groups"] = groups  # teams whose order among their places isn't stated
        result[key] = entry
    return result


def team_scenarios_as_dict(
    scenarios: dict,
    playoff_seeds: int = PLAYOFF_SEEDS,
    odds: dict | None = None,
    weighted_odds: dict | None = None,
) -> dict[str, dict]:
    """Return per-team scenarios as a structured dict for frontend consumption.

    Converts the atoms dict from ``build_scenario_atoms`` into a mapping where
    each team's entry has integer seed keys (1–N) for seeding scenarios and an
    optional ``"eliminated"`` key for elimination scenarios.

    Args:
        scenarios: Atoms dict from ``build_scenario_atoms``
            (``team → seed → list[atom]``).
        playoff_seeds: Number of playoff seeds (default 4).
        odds: Optional mapping of team name → ``StandingsOdds`` (equal win
            probability).  When provided, ``odds`` is populated per entry.
        weighted_odds: Optional mapping of team name → ``StandingsOdds``
            computed with a win-probability function.  When provided,
            ``weighted_odds`` is populated per entry.

    Returns:
        ``dict[team → dict[seed_key → entry]]`` where seed keys are integers
        1–``playoff_seeds`` for seeding scenarios and the string
        ``"eliminated"`` for elimination scenarios.  Each entry is::

            {
                "odds": float | None,           # equal-probability odds
                "weighted_odds": float | None,  # win-probability-weighted odds
                "scenarios": list[str],         # human-readable condition strings
            }

        Fully eliminated teams have only an ``"eliminated"`` key with an empty
        ``scenarios`` list.
    """
    result: dict[str, dict] = {}
    for team, seed_map in scenarios.items():
        team_odds = odds.get(team) if odds else None
        team_weighted = weighted_odds.get(team) if weighted_odds else None
        team_entry: dict = {}

        playoff_seed_entries = {seed: atoms for seed, atoms in seed_map.items() if seed <= playoff_seeds}
        eliminated_atoms = [atom for seed, atoms in seed_map.items() if seed > playoff_seeds for atom in atoms]

        for seed in sorted(playoff_seed_entries):
            team_entry[seed] = {
                "odds": getattr(team_odds, f"p{seed}") if team_odds else None,
                "weighted_odds": getattr(team_weighted, f"p{seed}") if team_weighted else None,
                "scenarios": [_render_atom(atom) for atom in playoff_seed_entries[seed]],
                "conditions": [serialize_atom(atom) for atom in playoff_seed_entries[seed]],
            }

        if not playoff_seed_entries:
            # Fully eliminated — no conditions needed
            team_entry["eliminated"] = {
                "odds": (1.0 - team_odds.p_playoffs) if team_odds else None,
                "weighted_odds": (1.0 - team_weighted.p_playoffs) if team_weighted else None,
                "scenarios": [],
                "conditions": [],
            }
        elif eliminated_atoms:
            team_entry["eliminated"] = {
                "odds": (1.0 - team_odds.p_playoffs) if team_odds else None,
                "weighted_odds": (1.0 - team_weighted.p_playoffs) if team_weighted else None,
                "scenarios": [_render_atom(atom) for atom in eliminated_atoms],
                "conditions": [serialize_atom(atom) for atom in eliminated_atoms],
            }

        result[team] = team_entry
    return result


# ---------------------------------------------------------------------------
# Playoff home-game scenario renderers
# ---------------------------------------------------------------------------


def _render_condition_label(cond: HomeGameCondition) -> str:
    """Render a single ``HomeGameCondition`` as a plain-English phrase.

    Args:
        cond: The condition to render.

    Returns:
        A short phrase such as ``"Taylorsville advances to Quarterfinals"``
        or ``"Region 2 #3 Seed advances to Second Round"``.
    """
    if cond.kind == "seed_required":
        if cond.region is None and cond.team_name is None:
            return f"Team finishes as the #{cond.seed} seed"
        label = cond.team_name or f"Region {cond.region} #{cond.seed} Seed"
        return f"{label} finishes as the #{cond.seed} seed"
    # kind == "advances"
    if cond.region is None:
        # Refers to the target team itself; caller should substitute name
        return f"Team advances to {cond.round_name}"
    if cond.team_name is not None:
        label = f"Region {cond.region} #{cond.seed} {cond.team_name}"
    else:
        label = f"Region {cond.region} #{cond.seed} Seed"
    return f"{label} advances to {cond.round_name}"


def _render_home_scenario_block(
    scenarios: tuple[HomeGameScenario, ...],
    team_name: str,
) -> list[str]:
    """Render a list of ``HomeGameScenario`` objects as numbered condition lines.

    Each scenario is an AND-joined set of conditions.  Multiple scenarios are
    separated by a blank line (OR logic).  The explanation for a scenario is
    shown as an indented note after the final condition line.

    The condition that refers to the target team itself (``region is None``)
    has its generic ``"Team"`` placeholder replaced by *team_name*.

    Args:
        scenarios:  Tuple of home-game scenarios (all with the same outcome).
        team_name:  The school name of the target team.

    Returns:
        List of lines ready to be joined with ``"\\n"``.
    """
    lines: list[str] = []
    for i, sc in enumerate(scenarios):
        if i > 0:
            lines.append("")  # blank separator between OR paths
        conds = sc.conditions
        if not conds:
            # Unconditional — no bullets needed
            if sc.explanation:
                lines.append(f"   [{sc.explanation}]")
        else:
            for j, cond in enumerate(conds, 1):
                raw = _substitute_team_placeholder(_render_condition_label(cond), team_name)
                if j == len(conds) and sc.explanation:
                    lines.append(f"{j}. {raw}")
                    lines.append(f"   [{sc.explanation}]")
                else:
                    lines.append(f"{j}. {raw}")
    return lines


def _substitute_team_placeholder(label: str, team_name: str) -> str:
    """Replace the generic ``"Team"`` placeholder in a rendered condition label with *team_name*."""
    label = label.replace("Team advances", f"{team_name} advances")
    return label.replace("Team finishes", f"{team_name} finishes")


def _render_home_scenario_title(sc: HomeGameScenario, team_name: str) -> str | None:
    """Render a single ``HomeGameScenario`` as one AND-joined plain-English sentence.

    Unlike ``_render_home_scenario_block``, this produces a single unnumbered
    string (the hosting-domain analog of ``render_scenario_title`` for
    standings scenarios). Returns ``None`` when the scenario is unconditional
    (no conditions to render).
    """
    if not sc.conditions:
        return None
    labels = [_substitute_team_placeholder(_render_condition_label(c), team_name) for c in sc.conditions]
    return " AND ".join(labels)


def _odds_pct(p: float | None, p_w: float | None) -> str:
    """Format probability values as a parenthetical percentage suffix.

    Args:
        p:   Unweighted probability (0–1), or ``None``.
        p_w: Weighted probability (0–1), or ``None``.

    Returns:
        Empty string when both are ``None``; otherwise a formatted suffix
        such as ``" (62.5%)"`` or ``" (62.5% – 68.0% Weighted)"``.
    """
    if p is None and p_w is None:
        return ""
    if p is not None and p_w is not None:
        return f" ({_pct(p)} \u2013 {_pct(p_w)} Weighted)"
    if p_w is not None:
        return f" ({_pct(p_w)} Weighted)"
    return f" ({_pct(p)})"  # type: ignore[operator]


def _render_pre_playoff_block(
    scenarios: tuple[HomeGameScenario, ...],
    team_name: str,
    seed_atoms: dict[str, dict[int, list[list]]],
) -> list[str]:
    """Render a pre-playoff home-game block, expanding seed_required into game conditions.

    Each ``HomeGameScenario`` whose first condition is ``kind="seed_required"``
    with ``region=None`` is expanded: the ``seed_required`` is replaced by each
    atom in ``seed_atoms[team_name][seed]``, with any remaining
    ``HomeGameCondition`` objects AND-joined after the atom text.  Multiple atoms
    produce multiple numbered lines.  Scenarios without a ``seed_required`` first
    condition fall back to a single numbered line of AND-joined condition labels.
    """
    lines: list[str] = []
    n = 0

    for sc in scenarios:
        conds = sc.conditions
        if not conds:
            if sc.explanation:
                lines.append(f"   [{sc.explanation}]")
            continue

        first_cond = conds[0]
        if first_cond.kind == "seed_required" and first_cond.region is None and first_cond.seed is not None:
            seed: int = first_cond.seed
            atoms = seed_atoms.get(team_name, {}).get(seed, [])
            remaining = conds[1:]

            # Pre-render the remaining HomeGameConditions (same for every atom)
            remaining_labels = [_substitute_team_placeholder(_render_condition_label(c), team_name) for c in remaining]

            for atom in atoms:
                n += 1
                parts = [_render_atom(atom)] + remaining_labels
                line = f"{n}. " + " AND ".join(parts)
                lines.append(line)
                if sc.explanation:
                    lines.append(f"   [{sc.explanation}]")
        else:
            # Fallback: flatten all conditions to a single numbered line
            n += 1
            labels = [_substitute_team_placeholder(_render_condition_label(c), team_name) for c in conds]
            line = f"{n}. " + " AND ".join(labels)
            lines.append(line)
            if sc.explanation:
                lines.append(f"   [{sc.explanation}]")

    return lines


def render_team_home_scenarios(
    team: str,
    home_scenarios: list[RoundHomeScenarios],
) -> str:
    """Return a human-readable string of playoff home-game scenarios for a team.

    For each round the output shows a ``"Will Host <Round>"`` block and / or a
    ``"Will Not Host <Round>"`` block, each containing numbered conditions
    (AND logic within a block; blank-line-separated groups = OR logic across
    alternative paths).

    When the hosting outcome is unconditional (e.g. the team is always the
    designated home team in the first round) the block header includes
    ``"(100.0%)"`` and no numbered conditions are shown.

    Probability suffixes (``p_host_overall`` / ``p_host_overall_weighted``)
    are taken from the ``RoundHomeScenarios`` objects themselves; pass them in
    via ``enumerate_home_game_scenarios``'s ``p_host_overall_by_round`` /
    ``p_host_overall_weighted_by_round`` arguments.

    Args:
        team:           School name of the target team.
        home_scenarios: List of ``RoundHomeScenarios`` as returned by
                        ``enumerate_home_game_scenarios``.

    Returns:
        Multi-line string suitable for printing to a terminal or text file.
    """
    lines: list[str] = [team, ""]

    for rnd in home_scenarios:
        p = rnd.p_host_overall
        p_w = rnd.p_host_overall_weighted

        # Will Host block
        if rnd.will_host:
            header = f"Will Host {rnd.round_name}{_odds_pct(p, p_w)}:"
            if len(rnd.will_host) == 1 and not rnd.will_host[0].conditions:
                # Unconditional host — fold the explanation into the header
                expl = rnd.will_host[0].explanation
                if expl:
                    lines.append(f"{header}  [{expl}]")
                else:
                    lines.append(header)
            else:
                lines.append(header)
                lines.extend(_render_home_scenario_block(rnd.will_host, team))
            lines.append("")

        # Will Not Host block
        if rnd.will_not_host:
            not_p = (1.0 - p) if p is not None else None
            not_p_w = (1.0 - p_w) if p_w is not None else None
            header = f"Will Not Host {rnd.round_name}{_odds_pct(not_p, not_p_w)}:"
            if len(rnd.will_not_host) == 1 and not rnd.will_not_host[0].conditions:
                expl = rnd.will_not_host[0].explanation
                if expl:
                    lines.append(f"{header}  [{expl}]")
                else:
                    lines.append(header)
            else:
                lines.append(header)
                lines.extend(_render_home_scenario_block(rnd.will_not_host, team))
            lines.append("")

    return "\n".join(lines).rstrip()


def render_pre_playoff_team_home_scenarios(
    team: str,
    home_scenarios: list[RoundHomeScenarios],
    seed_atoms: dict[str, dict[int, list[list]]],
) -> str:
    """Render pre-playoff home scenarios with seed_required conditions expanded to game conditions.

    Like ``render_team_home_scenarios`` but for the ``seed=None`` (pre-playoff)
    path of ``enumerate_home_game_scenarios``.  Each
    ``HomeGameCondition(kind="seed_required")`` is replaced by the actual
    regular-season game conditions from *seed_atoms* so the reader sees
    "Taylorsville beats Lumberton" instead of "Taylorsville finishes as the #1 seed".

    Multiple atoms for the same seed produce multiple numbered lines; remaining
    playoff-advance conditions are AND-joined after the atom text on the same line.

    Args:
        team:           School name of the target team.
        home_scenarios: From ``enumerate_home_game_scenarios(seed=None, ...)``.
        seed_atoms:     From ``build_scenario_atoms``, keyed by
                        ``team → seed → list[atom]``.

    Returns:
        Multi-line string suitable for printing to a terminal or text file.
    """
    lines: list[str] = [team, ""]

    for rnd in home_scenarios:
        p = rnd.p_host_overall
        p_w = rnd.p_host_overall_weighted

        if rnd.will_host:
            header = f"Will Host {rnd.round_name}{_odds_pct(p, p_w)}:"
            lines.append(header)
            lines.extend(_render_pre_playoff_block(rnd.will_host, team, seed_atoms))
            lines.append("")

        if rnd.will_not_host:
            not_p = (1.0 - p) if p is not None else None
            not_p_w = (1.0 - p_w) if p_w is not None else None
            header = f"Will Not Host {rnd.round_name}{_odds_pct(not_p, not_p_w)}:"
            lines.append(header)
            lines.extend(_render_pre_playoff_block(rnd.will_not_host, team, seed_atoms))
            lines.append("")

    return "\n".join(lines).rstrip()


def team_home_scenarios_as_dict(
    team: str,
    home_scenarios: list[RoundHomeScenarios],
    seed_atoms: dict[str, dict[int, list[list]]] | None = None,
) -> dict[str, dict]:
    """Return playoff home-game scenarios as a structured dict for API / frontend use.

    The returned dict is keyed by a snake_case round name:
    ``"first_round"``, ``"second_round"`` (1A–4A only), ``"quarterfinals"``,
    ``"semifinals"``.

    Each round entry has the shape::

        {
            "p_reach": float | None,
            "p_host_given_reach": float | None,
            "p_host_overall": float | None,
            "p_reach_weighted": float | None,
            "p_host_given_reach_weighted": float | None,
            "p_host_overall_weighted": float | None,
            "will_host": [
                {
                    "conditions": [ <condition dict, see serialize_condition>, ... ],
                    "explanation": str | None,
                    "title": str | None,
                },
                ...
            ],
            "will_not_host": [ ... ],
        }

    Each condition dict is produced by ``scenario_serializers.serialize_condition``
    and carries a ``"type"`` discriminator (``"home_game_condition"`` for
    ``HomeGameCondition``, or ``"game_result"``/``"margin_condition"`` for the
    real regular-season game atoms substituted in by *seed_atoms* below).

    Args:
        team:           School name of the target team.  Used to resolve
                        ``region=None`` conditions to the team's own name.
        home_scenarios: List of ``RoundHomeScenarios`` as returned by
                        ``enumerate_home_game_scenarios``.
        seed_atoms:     Optional atoms dict from ``build_scenario_atoms``
                        (``team → seed → list[atom]``).  When supplied, any
                        pre-playoff ``seed_required`` placeholder condition is
                        expanded into the real regular-season game atom(s)
                        that produce that seed — one dict per atom — instead
                        of being left as an unresolved placeholder.

    Returns:
        Structured dict ready for JSON serialisation.
    """

    def _scenario_dict(sc: HomeGameScenario, team_name: str) -> dict:
        """Serialise a single ``HomeGameScenario`` to a plain dict."""
        resolved = [_resolve_home_condition_team_name(c, team_name) for c in sc.conditions]
        return {
            "conditions": [serialize_condition(c) for c in resolved],
            "explanation": sc.explanation,
            "title": _render_home_scenario_title(sc, team_name),
        }

    def _expand_scenario(sc: HomeGameScenario, team_name: str) -> list[dict]:
        """Expand a pre-playoff ``seed_required`` scenario into one dict per real game atom.

        Falls back to a single ``_scenario_dict`` when *seed_atoms* wasn't
        supplied, the scenario has no conditions, its first condition isn't
        an unresolved ``seed_required`` placeholder, or no atoms are found
        for that team/seed.
        """
        conds = sc.conditions
        if not seed_atoms or not conds:
            return [_scenario_dict(sc, team_name)]
        first = conds[0]
        if not (first.kind == "seed_required" and first.region is None and first.seed is not None):
            return [_scenario_dict(sc, team_name)]

        atoms = seed_atoms.get(team_name, {}).get(first.seed, [])
        if not atoms:
            return [_scenario_dict(sc, team_name)]

        remaining = conds[1:]
        remaining_resolved = [_resolve_home_condition_team_name(c, team_name) for c in remaining]
        remaining_serialized = [serialize_condition(c) for c in remaining_resolved]
        remaining_labels = [_substitute_team_placeholder(_render_condition_label(c), team_name) for c in remaining]

        expanded = []
        for atom in atoms:
            expanded.append(
                {
                    "conditions": serialize_atom(atom) + remaining_serialized,
                    "explanation": sc.explanation,
                    "title": " AND ".join([_render_atom(atom)] + remaining_labels),
                }
            )
        return expanded

    result: dict[str, dict] = {}
    for rnd in home_scenarios:
        key = _ROUND_KEY.get(rnd.round_name, rnd.round_name.lower().replace(" ", "_"))
        will_host = [d for sc in rnd.will_host for d in _expand_scenario(sc, team)]
        will_not_host = [d for sc in rnd.will_not_host for d in _expand_scenario(sc, team)]
        result[key] = {
            "p_reach": rnd.p_reach,
            "p_host_given_reach": rnd.p_host_given_reach,
            "p_host_overall": rnd.p_host_overall,
            "p_reach_weighted": rnd.p_reach_weighted,
            "p_host_given_reach_weighted": rnd.p_host_given_reach_weighted,
            "p_host_overall_weighted": rnd.p_host_overall_weighted,
            "will_host": will_host,
            "will_not_host": will_not_host,
        }
    return result


# ---------------------------------------------------------------------------
# Matchup renderers (opponent-centric view)
# ---------------------------------------------------------------------------

_ROUND_KEY_MATCHUP = {
    "First Round": "first_round",
    "Second Round": "second_round",
    "Quarterfinals": "quarterfinals",
    "Semifinals": "semifinals",
}


def render_team_matchups(
    team: str,
    round_matchups: list[RoundMatchups],
) -> str:
    """Return a human-readable string of all possible playoff matchups for a team.

    Each round lists every possible ``(opponent, home/away)`` combination on a
    separate line in the form::

        Away at Home (XX.X%)

    where the percentage is the per-matchup probability given the team
    reaches this round (``p_given_reach``) — i.e. the chance
    they face this specific opponent as home or away.  Home matchups are listed
    before away matchups within each round.

    A round header shows the team's probability of reaching the round when
    ``p_reach`` is available.

    Args:
        team:           School name of the target team.
        round_matchups: List of ``RoundMatchups`` from ``enumerate_team_matchups``.

    Returns:
        Multi-line string suitable for printing or writing to a text file.
    """
    lines: list[str] = [team, ""]

    for rnd in round_matchups:
        reach_suffix = _odds_pct(rnd.p_reach, rnd.p_reach_weighted)
        lines.append(f"{rnd.round_name}{reach_suffix}:")

        for entry in rnd.entries:
            p_suffix = _odds_pct(entry.p_given_reach, entry.p_given_reach_weighted)
            if entry.home:
                away_label = f"Region {entry.opponent_region} #{entry.opponent_seed} {entry.opponent}"
                line = f"  {away_label} at {team}{p_suffix}"
            else:
                home_label = f"Region {entry.opponent_region} #{entry.opponent_seed} {entry.opponent}"
                line = f"  {team} at {home_label}{p_suffix}"
            if entry.explanation:
                line += f"  [{entry.explanation}]"
            lines.append(line)

        lines.append("")

    return "\n".join(lines).rstrip()


def team_matchups_as_dict(
    round_matchups: list[RoundMatchups],
) -> dict[str, dict]:
    """Return per-matchup playoff scenarios as a structured dict for API / frontend use.

    The returned dict is keyed by a snake_case round name:
    ``"first_round"``, ``"second_round"`` (1A–4A only), ``"quarterfinals"``,
    ``"semifinals"``.

    Each round entry has the shape::

        {
            "p_reach": float | None,
            "p_host_given_reach": float | None,
            "p_host_overall": float | None,
            "p_reach_weighted": float | None,
            "p_host_given_reach_weighted": float | None,
            "p_host_overall_weighted": float | None,
            "matchups": [
                {
                    "opponent": str,
                    "opponent_region": int,
                    "opponent_seed": int,
                    "home": bool,
                    "p_given_reach": float | None,
                    "p_given_reach_weighted": float | None,
                    "p_overall": float | None,
                    "p_overall_weighted": float | None,
                    "explanation": str | None,
                },
                ...
            ],
        }

    Matchups within a round are sorted home-first, then by
    ``(opponent_region, opponent_seed)``.

    Args:
        round_matchups: List of ``RoundMatchups`` from ``enumerate_team_matchups``.

    Returns:
        Structured dict ready for JSON serialisation.
    """
    result: dict[str, dict] = {}
    for rnd in round_matchups:
        key = _ROUND_KEY_MATCHUP.get(rnd.round_name, rnd.round_name.lower().replace(" ", "_"))
        result[key] = {
            "p_reach": rnd.p_reach,
            "p_host_given_reach": rnd.p_host_given_reach,
            "p_host_overall": rnd.p_host_overall,
            "p_reach_weighted": rnd.p_reach_weighted,
            "p_host_given_reach_weighted": rnd.p_host_given_reach_weighted,
            "p_host_overall_weighted": rnd.p_host_overall_weighted,
            "matchups": [
                {
                    "opponent": e.opponent,
                    "opponent_region": e.opponent_region,
                    "opponent_seed": e.opponent_seed,
                    "home": e.home,
                    "p_given_reach": e.p_given_reach,
                    "p_given_reach_weighted": e.p_given_reach_weighted,
                    "p_overall": e.p_overall,
                    "p_overall_weighted": e.p_overall_weighted,
                    "explanation": e.explanation,
                }
                for e in rnd.entries
            ],
        }
    return result
