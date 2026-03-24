"""Render playoff scenario atoms as human-readable text."""

from backend.helpers.data_classes import (
    GameResult,
    HomeGameCondition,
    HomeGameScenario,
    MarginCondition,
    RoundHomeScenarios,
    RoundMatchups,
)


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
# Structured dict renderers (for frontend / API consumption)
# ---------------------------------------------------------------------------

_SEED_FIELD_NAMES = ["one_seed", "two_seed", "three_seed", "four_seed"]


def division_scenarios_as_dict(
    scenarios: list[dict],
    playoff_seeds: int = 4,
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
            }
    """
    seed_fields = _SEED_FIELD_NAMES[:playoff_seeds]

    # Pass 1: build entries (deduplicating identical title+seeding), preserving
    # the original scenario_num grouping so sub-labels stay together.
    seen_display: set[tuple] = set()
    deduped: list[tuple[int, str, str, tuple]] = []  # (orig_num, sub_label, title, seeding)
    for sc in scenarios:
        if sc["conditions_atom"] is not None:
            title = _render_atom(sc["conditions_atom"])
        else:
            title = " AND ".join(f"{w} beats {l}" for w, l in sc["game_winners"])
        seeding = sc["seeding"]
        display_key = (title, seeding)
        if display_key in seen_display:
            continue
        seen_display.add(display_key)
        deduped.append((sc["scenario_num"], sc["sub_label"], title, seeding))

    # Pass 2: re-number sequentially so gaps left by dedup don't appear in keys.
    # Groups of sub-scenarios (same orig_num) get the same new number.
    result: dict[str, dict] = {}
    new_num = 0
    prev_orig_num: int | None = None
    for orig_num, sub_label, title, seeding in deduped:
        if orig_num != prev_orig_num:
            new_num += 1
            prev_orig_num = orig_num
        key = str(new_num) + sub_label
        entry: dict = {"title": title}
        for i, field in enumerate(seed_fields):
            entry[field] = seeding[i] if i < len(seeding) else None
        entry["eliminated"] = list(seeding[playoff_seeds:])
        result[key] = entry
    return result


def team_scenarios_as_dict(
    scenarios: dict,
    playoff_seeds: int = 4,
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

        playoff_seed_entries = {
            seed: atoms for seed, atoms in seed_map.items() if seed <= playoff_seeds
        }
        eliminated_atoms = [
            atom
            for seed, atoms in seed_map.items()
            if seed > playoff_seeds
            for atom in atoms
        ]

        for seed in sorted(playoff_seed_entries):
            team_entry[seed] = {
                "odds": getattr(team_odds, f"p{seed}") if team_odds else None,
                "weighted_odds": getattr(team_weighted, f"p{seed}") if team_weighted else None,
                "scenarios": [_render_atom(atom) for atom in playoff_seed_entries[seed]],
            }

        if not playoff_seed_entries:
            # Fully eliminated — no conditions needed
            team_entry["eliminated"] = {
                "odds": (1.0 - team_odds.p_playoffs) if team_odds else None,
                "weighted_odds": (1.0 - team_weighted.p_playoffs) if team_weighted else None,
                "scenarios": [],
            }
        elif eliminated_atoms:
            team_entry["eliminated"] = {
                "odds": (1.0 - team_odds.p_playoffs) if team_odds else None,
                "weighted_odds": (1.0 - team_weighted.p_playoffs) if team_weighted else None,
                "scenarios": [_render_atom(atom) for atom in eliminated_atoms],
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
        label = cond.team_name or f"Region {cond.region} #{cond.seed} Seed"
        return f"{label} finishes as the #{cond.seed} seed"
    # kind == "advances"
    if cond.region is None:
        # Refers to the target team itself; caller should substitute name
        return f"Team advances to {cond.round_name}"
    label = cond.team_name or f"Region {cond.region} #{cond.seed} Seed"
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
                raw = _render_condition_label(cond)
                # Substitute placeholder for target team
                raw = raw.replace("Team advances", f"{team_name} advances")
                raw = raw.replace("Team finishes", f"{team_name} finishes")
                if j == len(conds) and sc.explanation:
                    lines.append(f"{j}. {raw}")
                    lines.append(f"   [{sc.explanation}]")
                else:
                    lines.append(f"{j}. {raw}")
    return lines


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
        return f" ({p * 100:.1f}% \u2013 {p_w * 100:.1f}% Weighted)"
    if p_w is not None:
        return f" ({p_w * 100:.1f}% Weighted)"
    return f" ({p * 100:.1f}%)"  # type: ignore[operator]


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

    Probability suffixes (``p_host`` / ``p_host_weighted``) are taken from
    the ``RoundHomeScenarios`` objects themselves; pass them in via
    ``enumerate_home_game_scenarios``'s ``p_host_by_round`` /
    ``p_host_weighted_by_round`` arguments.

    Args:
        team:           School name of the target team.
        home_scenarios: List of ``RoundHomeScenarios`` as returned by
                        ``enumerate_home_game_scenarios``.

    Returns:
        Multi-line string suitable for printing to a terminal or text file.
    """
    lines: list[str] = [team, ""]

    for rnd in home_scenarios:
        p = rnd.p_host_marginal
        p_w = rnd.p_host_marginal_weighted

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


def team_home_scenarios_as_dict(
    team: str,
    home_scenarios: list[RoundHomeScenarios],
) -> dict[str, dict]:
    """Return playoff home-game scenarios as a structured dict for API / frontend use.

    The returned dict is keyed by a snake_case round name:
    ``"first_round"``, ``"second_round"`` (1A–4A only), ``"quarterfinals"``,
    ``"semifinals"``.

    Each round entry has the shape::

        {
            "p_reach": float | None,
            "p_host_conditional": float | None,
            "p_host_marginal": float | None,
            "p_reach_weighted": float | None,
            "p_host_conditional_weighted": float | None,
            "p_host_marginal_weighted": float | None,
            "will_host": [
                {
                    "conditions": [
                        {
                            "kind": "advances" | "seed_required",
                            "round": str | None,
                            "region": int | None,
                            "seed": int | None,
                            "team": str | None,
                        },
                        ...
                    ],
                    "explanation": str | None,
                },
                ...
            ],
            "will_not_host": [ ... ],
        }

    Args:
        team:           School name of the target team.  Used to resolve
                        ``region=None`` conditions to the team's own name.
        home_scenarios: List of ``RoundHomeScenarios`` as returned by
                        ``enumerate_home_game_scenarios``.

    Returns:
        Structured dict ready for JSON serialisation.
    """

    def _cond_dict(cond: HomeGameCondition, team_name: str) -> dict:
        """Serialise a single ``HomeGameCondition`` to a plain dict."""
        label = cond.team_name
        if label is None and cond.region is None:
            label = team_name  # target team itself
        elif label is None:
            label = f"Region {cond.region} #{cond.seed} Seed"
        return {
            "kind": cond.kind,
            "round": cond.round_name,
            "region": cond.region,
            "seed": cond.seed,
            "team": label,
        }

    def _scenario_dict(sc: HomeGameScenario, team_name: str) -> dict:
        """Serialise a single ``HomeGameScenario`` to a plain dict."""
        return {
            "conditions": [_cond_dict(c, team_name) for c in sc.conditions],
            "explanation": sc.explanation,
        }

    _ROUND_KEY = {
        "First Round": "first_round",
        "Second Round": "second_round",
        "Quarterfinals": "quarterfinals",
        "Semifinals": "semifinals",
    }

    result: dict[str, dict] = {}
    for rnd in home_scenarios:
        key = _ROUND_KEY.get(rnd.round_name, rnd.round_name.lower().replace(" ", "_"))
        result[key] = {
            "p_reach": rnd.p_reach,
            "p_host_conditional": rnd.p_host_conditional,
            "p_host_marginal": rnd.p_host_marginal,
            "p_reach_weighted": rnd.p_reach_weighted,
            "p_host_conditional_weighted": rnd.p_host_conditional_weighted,
            "p_host_marginal_weighted": rnd.p_host_marginal_weighted,
            "will_host": [_scenario_dict(sc, team) for sc in rnd.will_host],
            "will_not_host": [_scenario_dict(sc, team) for sc in rnd.will_not_host],
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

    where the percentage is the per-matchup conditional probability
    (``p_conditional``) — i.e. given the team reaches this round, the chance
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
            p_suffix = _odds_pct(entry.p_conditional, entry.p_conditional_weighted)
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
            "p_host_conditional": float | None,
            "p_host_marginal": float | None,
            "p_reach_weighted": float | None,
            "p_host_conditional_weighted": float | None,
            "p_host_marginal_weighted": float | None,
            "matchups": [
                {
                    "opponent": str,
                    "opponent_region": int,
                    "opponent_seed": int,
                    "home": bool,
                    "p_conditional": float | None,
                    "p_conditional_weighted": float | None,
                    "p_marginal": float | None,
                    "p_marginal_weighted": float | None,
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
            "p_host_conditional": rnd.p_host_conditional,
            "p_host_marginal": rnd.p_host_marginal,
            "p_reach_weighted": rnd.p_reach_weighted,
            "p_host_conditional_weighted": rnd.p_host_conditional_weighted,
            "p_host_marginal_weighted": rnd.p_host_marginal_weighted,
            "matchups": [
                {
                    "opponent": e.opponent,
                    "opponent_region": e.opponent_region,
                    "opponent_seed": e.opponent_seed,
                    "home": e.home,
                    "p_conditional": e.p_conditional,
                    "p_conditional_weighted": e.p_conditional_weighted,
                    "p_marginal": e.p_marginal,
                    "p_marginal_weighted": e.p_marginal_weighted,
                    "explanation": e.explanation,
                }
                for e in rnd.entries
            ],
        }
    return result
