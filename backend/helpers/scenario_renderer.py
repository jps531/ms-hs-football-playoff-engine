"""Render playoff scenario atoms as human-readable text."""

from backend.helpers.data_classes import GameResult, MarginCondition


def _render_game_result(cond: GameResult) -> str:
    """Render a GameResult as a plain-English phrase."""
    base = f"{cond.winner} beats {cond.loser}"
    if cond.min_margin == 1 and cond.max_margin is None:
        return base
    if cond.max_margin is not None and cond.max_margin == cond.min_margin + 1:
        return f"{base} by exactly {cond.min_margin}"
    if cond.max_margin is None:
        return f"{base} by {cond.min_margin} or more"
    if cond.min_margin == 1:
        return f"{base} by 1\u2013{cond.max_margin - 1}"
    return f"{base} by {cond.min_margin}\u2013{cond.max_margin - 1}"


def _winner_label(pair: tuple[str, str], atom: list) -> str:
    """Return the winner's name for a game pair, inferred from GameResult conditions in the atom."""
    a, b = pair
    for cond in atom:
        if isinstance(cond, GameResult):
            if (cond.winner == a and cond.loser == b) or (cond.winner == b and cond.loser == a):
                return cond.winner
    return f"{a}/{b}"


def _render_margin_condition(cond: MarginCondition, atom: list) -> str:
    """Render a MarginCondition as a plain-English phrase using winner labels from the atom."""
    if len(cond.add) == 2 and not cond.sub:
        l1 = _winner_label(cond.add[0], atom)
        l2 = _winner_label(cond.add[1], atom)
        if cond.op == "==":
            return f"{l1}'s margin and {l2}'s margin combined total exactly {cond.threshold}"
        if cond.op in (">=", ">"):
            t = cond.threshold + (1 if cond.op == ">" else 0)
            return f"{l1}'s margin and {l2}'s margin combined total {t} or more"
        else:
            t = cond.threshold - (1 if cond.op == "<" else 0)
            return f"{l1}'s margin and {l2}'s margin combined total {t} or less"

    if len(cond.add) == 1 and len(cond.sub) == 1:
        add_label = _winner_label(cond.add[0], atom)
        sub_label = _winner_label(cond.sub[0], atom)
        if cond.op == "==":
            t = cond.threshold
            if t < 0:
                return f"{sub_label}'s margin exceeds {add_label}'s by exactly {-t}"
            if t == 0:
                return f"{add_label}'s margin equals {sub_label}'s"
            return f"{add_label}'s margin exceeds {sub_label}'s by exactly {t}"
        if cond.op in (">=", ">"):
            t = cond.threshold + (1 if cond.op == ">" else 0)
            if t < 0:
                return f"{sub_label}'s margin doesn't exceed {add_label}'s by more than {-t}"
            if t == 0:
                return f"{add_label}'s margin is at least as large as {sub_label}'s"
            return f"{add_label}'s margin exceeds {sub_label}'s by {t} or more"
        else:
            t = cond.threshold - (1 if cond.op == "<" else 0)
            if t > 0:
                return f"{add_label}'s margin doesn't exceed {sub_label}'s by more than {t}"
            if t == 0:
                return f"{sub_label}'s margin is at least as large as {add_label}'s"
            return f"{sub_label}'s margin exceeds {add_label}'s by {-t} or more"

    # Fallback for other patterns
    parts = [f"{_winner_label(p, atom)}'s margin" for p in cond.add]
    parts += [f"\u2212{_winner_label(p, atom)}'s margin" for p in cond.sub]
    return " + ".join(parts) + f" {cond.op} {cond.threshold}"


def _render_condition(cond, atom: list) -> str:
    """Dispatch to the appropriate renderer based on the condition type."""
    if isinstance(cond, GameResult):
        return _render_game_result(cond)
    if isinstance(cond, MarginCondition):
        return _render_margin_condition(cond, atom)
    return str(cond)


def _render_atom(atom: list) -> str:
    """Render a list of conditions as a single AND-joined plain-English clause."""
    return " AND ".join(_render_condition(c, atom) for c in atom)


def render_team_scenarios(
    team: str,
    scenarios: dict[str, dict[int, list[list]]],
    playoff_seeds: int = 4,
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

    playoff_seed_entries = {
        seed: atoms for seed, atoms in seed_map.items() if seed <= playoff_seeds
    }
    eliminated_atoms: list[list] = [
        atom for seed, atoms in seed_map.items() if seed > playoff_seeds for atom in atoms
    ]

    def _odds_suffix(p_unweighted: float | None, p_weighted: float | None) -> str:
        """Format an odds suffix from zero, one, or both probability values."""
        if p_unweighted is None and p_weighted is None:
            return ""
        if p_unweighted is not None and p_weighted is not None:
            return f" ({p_unweighted * 100:.1f}% \u2013 {p_weighted * 100:.1f}% Weighted)"
        if p_weighted is not None:
            return f" ({p_weighted * 100:.1f}% Weighted)"
        return f" ({p_unweighted * 100:.1f}%)"  # type: ignore[operator]

    def _seed_suffix(seed: int) -> str:
        p_u = getattr(team_odds, f"p{seed}") if team_odds else None
        p_w = getattr(team_weighted, f"p{seed}") if team_weighted else None
        return _odds_suffix(p_u, p_w)

    def _elim_suffix() -> str:
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
