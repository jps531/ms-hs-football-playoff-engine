"""Extract actionable key insights from scenario atoms.

Key insights are simple, unconditionally-true statements derived from the
scenario atom structure — e.g. "Taylorsville clinches 1st seed if Taylorsville
beats Stringer" or "Murrah is eliminated if Starkville beats Terry".

Intended for display when R=7-10 (where full scenario lists are not shown) and
as a "headlines" banner at R<=6 alongside the full scenario list.

All conditional insights are margin-verified before emission: for R>4, the
claim is re-checked across all satisfying win/loss masks and all 12^k margin
combinations for the k condition games, ensuring the insight is unconditionally
true even for margin-sensitive tiebreakers.
"""

from dataclasses import dataclass
from itertools import product as iter_product

from backend.helpers.data_classes import (
    CompletedGame,
    GameResult,
    RemainingGame,
    StandingsOdds,
)
from backend.helpers.scenario_renderer import _render_game_result
from backend.helpers.scenario_serializers import deserialize_condition, serialize_condition

_PLAYOFF_SEEDS = 4
_MAX_CONDITIONS = 3
_MARGIN_RANGE = range(1, 13)
_MAX_CLINCH_PER_TEAM = 3
_MAX_ELIM_PER_TEAM = 3
_MAX_TOTAL_REGION = 8


@dataclass(frozen=True)
class KeyInsight:
    """A single actionable insight derived from scenario atoms.

    Attributes:
        insight_type: One of "already_clinched", "already_eliminated",
            "clinch_seed", "clinch_playoffs", "eliminated_if".
        team: The team this insight is about.
        seed: Seed being clinched (1-4) for clinch_seed; None for other types.
        conditions: Tuple of GameResult objects (empty for already_* types).
        margin_verified: True if margin-verified or R<=4 (fully margin-accurate).
        rendered: Pre-rendered human-readable text.
        r_computed: R value at time of computation.
    """

    insight_type: str
    team: str
    seed: int | None
    conditions: tuple  # tuple[GameResult, ...]
    margin_verified: bool
    rendered: str
    r_computed: int


def _render_insight(
    insight_type: str,
    team: str,
    seed: int | None,
    conditions: tuple,
) -> str:
    """Render a key insight as a human-readable string."""
    if insight_type == "already_clinched":
        return f"{team} has clinched a playoff spot"
    if insight_type == "already_eliminated":
        return f"{team} has been eliminated from the playoffs"
    cond_str = "; ".join(_render_game_result(c) for c in conditions)
    if insight_type == "clinch_seed":
        ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
        seed_str = ordinals.get(seed, f"{seed}th") if seed is not None else "unknown"
        return f"{team} clinches {seed_str} seed: {cond_str}"
    if insight_type == "clinch_playoffs":
        return f"{team} clinches a playoff spot: {cond_str}"
    if insight_type == "eliminated_if":
        return f"{team} is eliminated from the playoffs: {cond_str}"
    return f"{team}: {cond_str}"


def _atom_is_simple_game_results(atom: list) -> bool:
    """Return True iff atom has 1–3 conditions, all of which are GameResult."""
    return 1 <= len(atom) <= _MAX_CONDITIONS and all(isinstance(c, GameResult) for c in atom)


def _masks_satisfying_conditions(
    conditions: tuple,
    remaining: list[RemainingGame],
) -> list[int]:
    """Return all win/loss masks consistent with every GameResult in conditions."""
    R = len(remaining)
    required: dict[int, int] = {}
    for cond in conditions:
        for i, rg in enumerate(remaining):
            if {rg.a, rg.b} == {cond.winner, cond.loser}:
                required[i] = 1 if rg.a == cond.winner else 0
                break
    return [m for m in range(1 << R) if all((m >> i) & 1 == bit for i, bit in required.items())]


def _cond_game_indices(
    conditions: tuple,
    remaining: list[RemainingGame],
) -> list[int]:
    """Return remaining-game indices for each condition (in order, no duplicates)."""
    seen: set[int] = set()
    result: list[int] = []
    for cond in conditions:
        for i, rg in enumerate(remaining):
            if {rg.a, rg.b} == {cond.winner, cond.loser} and i not in seen:
                seen.add(i)
                result.append(i)
                break
    return result


def _verify_insight_margins(
    conditions: tuple,
    team: str,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    r_computed: int,
    expected_seed: int | None = None,
    expected_in_playoffs: bool | None = None,
    playoff_seeds: int = _PLAYOFF_SEEDS,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> bool:
    """Return True if the insight holds for all satisfying masks and margin combos.

    For R<=4 atoms are already fully margin-accurate — returns True immediately.

    Args:
        conditions: The GameResult conditions from the candidate atom.
        team: Subject team of the insight.
        expected_seed: If set, team must be at exactly this 1-indexed seed.
        expected_in_playoffs: If True, team must be in top playoff_seeds.
            If False, team must NOT be in top playoff_seeds.
    """
    if r_computed <= 4:
        return True

    from backend.helpers.tiebreakers import resolve_standings_for_mask

    R = len(remaining)
    pairs = [(rg.a, rg.b) for rg in remaining]
    satisfying_masks = _masks_satisfying_conditions(conditions, remaining)
    cond_indices = _cond_game_indices(conditions, remaining)

    for mask in satisfying_masks:
        base_margins = {pairs[i]: base_margin_default for i in range(R)}
        for margin_combo in iter_product(_MARGIN_RANGE, repeat=len(cond_indices)):
            margins = dict(base_margins)
            for k, game_idx in enumerate(cond_indices):
                margins[pairs[game_idx]] = margin_combo[k]
            seeding = resolve_standings_for_mask(
                teams, completed, remaining, mask, margins, base_margin_default, pa_win
            )
            team_pos = seeding.index(team) if team in seeding else len(seeding)
            if expected_seed is not None:
                if team_pos != expected_seed - 1:
                    return False
            elif expected_in_playoffs is True and team_pos >= playoff_seeds:
                return False
            elif expected_in_playoffs is False and team_pos < playoff_seeds:
                return False

    return True


def _conditions_frozenset(conditions: tuple) -> frozenset:
    """Stable hashable key for a conditions tuple."""
    return frozenset((c.winner, c.loser, c.min_margin, c.max_margin) for c in conditions)


def _extract_clinch_seed_insights(
    atoms: dict,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    odds: dict[str, StandingsOdds],
    r_computed: int,
    playoff_seeds: int = _PLAYOFF_SEEDS,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> list[KeyInsight]:
    """Extract clinch-seed insights: atoms that guarantee a specific seed position."""
    results = []
    for team in teams:
        if odds.get(team) and odds[team].clinched:
            continue
        team_atoms = atoms.get(team, {})
        for seed in range(1, playoff_seeds + 1):
            for atom in team_atoms.get(seed, []):
                if not _atom_is_simple_game_results(atom):
                    continue
                conditions = tuple(atom)
                if not _verify_insight_margins(
                    conditions,
                    team,
                    teams,
                    completed,
                    remaining,
                    r_computed,
                    expected_seed=seed,
                    playoff_seeds=playoff_seeds,
                    pa_win=pa_win,
                    base_margin_default=base_margin_default,
                ):
                    continue
                results.append(
                    KeyInsight(
                        insight_type="clinch_seed",
                        team=team,
                        seed=seed,
                        conditions=conditions,
                        margin_verified=True,
                        rendered=_render_insight("clinch_seed", team, seed, conditions),
                        r_computed=r_computed,
                    )
                )
    return results


def _extract_clinch_playoffs_insights(
    atoms: dict,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    odds: dict[str, StandingsOdds],
    r_computed: int,
    clinch_seed_insights: list[KeyInsight],
    playoff_seeds: int = _PLAYOFF_SEEDS,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> list[KeyInsight]:
    """Extract clinch-playoffs insights not already covered by a clinch-seed insight."""
    covered_by_team: dict[str, set[frozenset]] = {}
    for ins in clinch_seed_insights:
        covered_by_team.setdefault(ins.team, set()).add(_conditions_frozenset(ins.conditions))

    results = []
    seen: set[tuple] = set()
    for team in teams:
        if odds.get(team) and odds[team].clinched:
            continue
        team_atoms = atoms.get(team, {})
        for seed in range(1, playoff_seeds + 1):
            for atom in team_atoms.get(seed, []):
                if not _atom_is_simple_game_results(atom):
                    continue
                conditions = tuple(atom)
                cond_key = _conditions_frozenset(conditions)
                if cond_key in covered_by_team.get(team, set()):
                    continue
                dedup_key = (team, cond_key)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                if not _verify_insight_margins(
                    conditions,
                    team,
                    teams,
                    completed,
                    remaining,
                    r_computed,
                    expected_in_playoffs=True,
                    playoff_seeds=playoff_seeds,
                    pa_win=pa_win,
                    base_margin_default=base_margin_default,
                ):
                    continue
                results.append(
                    KeyInsight(
                        insight_type="clinch_playoffs",
                        team=team,
                        seed=None,
                        conditions=conditions,
                        margin_verified=True,
                        rendered=_render_insight("clinch_playoffs", team, None, conditions),
                        r_computed=r_computed,
                    )
                )
    return results


def _extract_elimination_insights(
    atoms: dict,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    odds: dict[str, StandingsOdds],
    r_computed: int,
    playoff_seeds: int = _PLAYOFF_SEEDS,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> list[KeyInsight]:
    """Extract elimination insights from atoms[team][playoff_seeds+1]."""
    elim_seed = playoff_seeds + 1
    results = []
    for team in teams:
        if odds.get(team) and odds[team].eliminated:
            continue
        for atom in atoms.get(team, {}).get(elim_seed, []):
            if not _atom_is_simple_game_results(atom):
                continue
            conditions = tuple(atom)
            if not _verify_insight_margins(
                conditions,
                team,
                teams,
                completed,
                remaining,
                r_computed,
                expected_in_playoffs=False,
                playoff_seeds=playoff_seeds,
                pa_win=pa_win,
                base_margin_default=base_margin_default,
            ):
                continue
            results.append(
                KeyInsight(
                    insight_type="eliminated_if",
                    team=team,
                    seed=None,
                    conditions=conditions,
                    margin_verified=True,
                    rendered=_render_insight("eliminated_if", team, None, conditions),
                    r_computed=r_computed,
                )
            )
    return results


def _sort_key(insight: KeyInsight) -> tuple:
    """Sort: zero-cond facts first, then fewer conditions, higher seed, alpha team."""
    type_order = {
        "already_clinched": 0,
        "already_eliminated": 1,
        "clinch_seed": 2,
        "clinch_playoffs": 3,
        "eliminated_if": 4,
    }
    seed_order = insight.seed if insight.seed is not None else 99
    return (type_order.get(insight.insight_type, 9), len(insight.conditions), seed_order, insight.team)


def _deduplicate(insights: list[KeyInsight]) -> list[KeyInsight]:
    """Drop insights whose condition set is a strict superset of another of the same (type, team)."""
    result = []
    for candidate in insights:
        cand_set = _conditions_frozenset(candidate.conditions)
        dominated = any(
            other.insight_type == candidate.insight_type
            and other.team == candidate.team
            and other is not candidate
            and _conditions_frozenset(other.conditions) < cand_set
            for other in insights
        )
        if not dominated:
            result.append(candidate)
    return result


def extract_insights(
    atoms: dict,
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    odds: dict[str, StandingsOdds] | None = None,
    r_computed: int = 0,
    playoff_seeds: int = _PLAYOFF_SEEDS,
    pa_win: int = 14,
    base_margin_default: int = 7,
) -> list[KeyInsight]:
    """Extract key insights from scenario atoms.

    Args:
        atoms: scenario_atoms dict as returned by build_scenario_atoms().
        teams: All team names in the region.
        completed: Completed region games.
        remaining: Unplayed region games.
        odds: Per-team StandingsOdds; used to skip already-clinched/eliminated.
        r_computed: R value at time of computation.
        playoff_seeds: Number of playoff seeds (default 4).
        pa_win: Points-allowed for simulated game winners.
        base_margin_default: Default margin for non-condition games in verification.

    Returns:
        Sorted, deduplicated list of KeyInsight objects, capped per team and region.
    """
    if odds is None:
        odds = {}

    results: list[KeyInsight] = []

    # Zero-condition insights for teams already clinched or eliminated
    for team in teams:
        team_odds = odds.get(team)
        if team_odds and team_odds.clinched:
            results.append(
                KeyInsight(
                    insight_type="already_clinched",
                    team=team,
                    seed=None,
                    conditions=(),
                    margin_verified=True,
                    rendered=_render_insight("already_clinched", team, None, ()),
                    r_computed=r_computed,
                )
            )
        elif team_odds and team_odds.eliminated:
            results.append(
                KeyInsight(
                    insight_type="already_eliminated",
                    team=team,
                    seed=None,
                    conditions=(),
                    margin_verified=True,
                    rendered=_render_insight("already_eliminated", team, None, ()),
                    r_computed=r_computed,
                )
            )

    clinch_seed = _extract_clinch_seed_insights(
        atoms,
        teams,
        completed,
        remaining,
        odds,
        r_computed,
        playoff_seeds,
        pa_win,
        base_margin_default,
    )
    clinch_playoffs = _extract_clinch_playoffs_insights(
        atoms,
        teams,
        completed,
        remaining,
        odds,
        r_computed,
        clinch_seed,
        playoff_seeds,
        pa_win,
        base_margin_default,
    )
    elimination = _extract_elimination_insights(
        atoms,
        teams,
        completed,
        remaining,
        odds,
        r_computed,
        playoff_seeds,
        pa_win,
        base_margin_default,
    )

    results.extend(clinch_seed)
    results.extend(clinch_playoffs)
    results.extend(elimination)

    results = _deduplicate(results)
    results.sort(key=_sort_key)

    # Per-team volume cap (after sort so we keep the best)
    team_clinch_count: dict[str, int] = {}
    team_elim_count: dict[str, int] = {}
    capped: list[KeyInsight] = []
    for ins in results:
        if ins.insight_type in ("clinch_seed", "clinch_playoffs"):
            if team_clinch_count.get(ins.team, 0) >= _MAX_CLINCH_PER_TEAM:
                continue
            team_clinch_count[ins.team] = team_clinch_count.get(ins.team, 0) + 1
        elif ins.insight_type == "eliminated_if":
            if team_elim_count.get(ins.team, 0) >= _MAX_ELIM_PER_TEAM:
                continue
            team_elim_count[ins.team] = team_elim_count.get(ins.team, 0) + 1
        capped.append(ins)

    return capped[:_MAX_TOTAL_REGION]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_insights(insights: list[KeyInsight]) -> list[dict]:
    """Serialize a list of KeyInsight objects to JSON-safe dicts."""
    return [
        {
            "insight_type": ins.insight_type,
            "team": ins.team,
            "seed": ins.seed,
            "conditions": [serialize_condition(c) for c in ins.conditions],
            "margin_verified": ins.margin_verified,
            "rendered": ins.rendered,
            "r_computed": ins.r_computed,
        }
        for ins in insights
    ]


def deserialize_insights(data: list[dict]) -> list[KeyInsight]:
    """Deserialize a list of dicts back to KeyInsight objects."""
    return [
        KeyInsight(
            insight_type=d["insight_type"],
            team=d["team"],
            seed=d["seed"],
            conditions=tuple(deserialize_condition(c) for c in d["conditions"]),
            margin_verified=d["margin_verified"],
            rendered=d["rendered"],
            r_computed=d["r_computed"],
        )
        for d in data
    ]
