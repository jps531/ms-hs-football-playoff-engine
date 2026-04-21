"""Pure helpers for applying hypothetical game results to region or bracket state.

All functions are stateless (no DB I/O).  They take in-memory game data and
return updated odds.  Callers are responsible for fetching data from the DB and
deciding whether to persist the results.

Typical usage
-------------
1. Fetch ``(teams, completed, remaining)`` from the DB using the Prefect tasks
   in ``region_scenarios_pipeline.py`` or equivalent plain SQL helpers.
2. Call ``apply_region_game_results(teams, completed, remaining, new_results)``
   to get updated ``(ScenarioResults, dict[str, StandingsOdds])``.
3. Optionally pass those odds to ``compute_bracket_odds`` / home-odds functions
   as usual.

For bracket what-if::

    odds = apply_bracket_game_results(bracket_teams, num_rounds,
                                      played_results, new_results)
"""

from __future__ import annotations

from backend.helpers.data_classes import (
    AppliedGameResult,
    BracketOdds,
    BracketTeam,
    CompletedGame,
    RemainingGame,
    ScenarioResults,
    StandingsOdds,
)
from backend.helpers.data_helpers import normalize_pair
from backend.helpers.scenarios import determine_odds, determine_scenarios

# -------------------------
# Region what-if
# -------------------------


def apply_region_game_results(
    teams: list[str],
    completed: list[CompletedGame],
    remaining: list[RemainingGame],
    new_results: list[AppliedGameResult],
    ignore_margins: bool = False,
) -> tuple[ScenarioResults, dict[str, StandingsOdds]]:
    """Apply hypothetical game results to existing region state and return updated odds.

    Converts each ``AppliedGameResult`` into a ``CompletedGame``, removes the
    corresponding ``RemainingGame`` entries, and re-runs ``determine_scenarios``
    plus ``determine_odds``.

    Args:
        teams: All team names in the region (alphabetically sorted).
        completed: Finalized region games already played.
        remaining: Unplayed region game pairs.
        new_results: Hypothetical game results to apply.  Each result must
            correspond to a game currently in ``remaining``; results whose pair
            does not appear in ``remaining`` are still accepted (the pair is
            added to completed) but no ``RemainingGame`` entry is removed.
        ignore_margins: Skip margin-sensitive enumeration.  Appropriate when
            ``len(remaining) - len(new_results) >= 7`` or when score data is
            unavailable.

    Returns:
        ``(ScenarioResults, dict[str, StandingsOdds])`` reflecting the state
        after applying the new results.
    """
    applied_pairs: set[tuple[str, str]] = set()
    new_completed_games: list[CompletedGame] = []

    for r in new_results:
        a, b, sign = normalize_pair(r.team_a, r.team_b)
        applied_pairs.add((a, b))

        # Express the score from a's perspective (a is lex-first).
        if sign == 1:
            sa, sb = r.score_a, r.score_b
        else:
            sa, sb = r.score_b, r.score_a

        if sa > sb:
            res_a = 1
        elif sa < sb:
            res_a = -1
        else:
            res_a = 0
        new_completed_games.append(
            CompletedGame(
                a=a,
                b=b,
                res_a=res_a,
                pd_a=sa - sb,
                pa_a=sb,  # points allowed by a = points scored by b
                pa_b=sa,  # points allowed by b = points scored by a
            )
        )

    new_remaining = [rg for rg in remaining if (rg.a, rg.b) not in applied_pairs]
    all_completed = completed + new_completed_games

    scenario_results = determine_scenarios(teams, all_completed, new_remaining, ignore_margins=ignore_margins)
    odds = determine_odds(
        teams,
        scenario_results.first_counts,
        scenario_results.second_counts,
        scenario_results.third_counts,
        scenario_results.fourth_counts,
        scenario_results.denom,
    )
    return scenario_results, odds


# -------------------------
# Bracket what-if
# -------------------------


def apply_bracket_game_results(
    bracket_teams: list[BracketTeam],
    num_rounds: int,
    played_results: list[AppliedGameResult],
    new_results: list[AppliedGameResult],
) -> dict[str, BracketOdds]:
    """Apply hypothetical bracket game results and return updated advancement odds.

    Derives survivor state from all confirmed results (``played_results``) plus
    the hypothetical ones (``new_results``), then computes per-round advancement
    probabilities under equal win probability (50/50 for each unplayed game).

    Teams that have already won N games are guaranteed to reach rounds 1–N and
    have equal-probability odds for subsequent rounds.  Eliminated teams receive
    0.0 for all future rounds.

    Args:
        bracket_teams: All teams seeded into the bracket.
        num_rounds: Total playoff rounds (4 for 5A–7A, 5 for 1A–4A).
        played_results: Already-confirmed bracket game results.
        new_results: Hypothetical results to apply on top of confirmed ones.

    Returns:
        Dict mapping school name to ``BracketOdds`` with probabilities updated
        to reflect the combined known + hypothetical bracket state.
    """
    rounds_won: dict[str, int] = {bt.school: 0 for bt in bracket_teams}
    eliminated: set[str] = set()

    for result in (*played_results, *new_results):
        if result.score_a == result.score_b:
            # Ties don't happen in playoffs; skip rather than crash.
            continue
        winner = result.team_a if result.score_a > result.score_b else result.team_b
        loser = result.team_b if result.score_a > result.score_b else result.team_a
        if winner in rounds_won:
            rounds_won[winner] += 1
        if loser in rounds_won:
            eliminated.add(loser)

    def _p_reach(school: str, target_wins: int) -> float:
        """Return P(school reaches the round requiring target_wins wins), under equal win probability."""
        if school in eliminated:
            return 0.0
        w = rounds_won.get(school, 0)
        return 1.0 if w >= target_wins else 0.5 ** (target_wins - w)

    result_odds: dict[str, BracketOdds] = {}
    for bt in bracket_teams:
        s = bt.school
        if num_rounds == 4:
            # 5A–7A: First Round → Quarterfinals → Semifinals → Finals → Champion
            result_odds[s] = BracketOdds(
                school=s,
                second_round=0.0,
                quarterfinals=_p_reach(s, 1),
                semifinals=_p_reach(s, 2),
                finals=_p_reach(s, 3),
                champion=_p_reach(s, 4),
            )
        else:
            # 1A–4A (num_rounds == 5): adds Second Round before Quarterfinals
            result_odds[s] = BracketOdds(
                school=s,
                second_round=_p_reach(s, 1),
                quarterfinals=_p_reach(s, 2),
                semifinals=_p_reach(s, 3),
                finals=_p_reach(s, 4),
                champion=_p_reach(s, 5),
            )

    return result_odds
