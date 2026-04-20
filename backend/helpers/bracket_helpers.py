"""Helpers for working with playoff bracket state.

Converts completed-game records (``Game`` objects from the DB) into the
survivor sets consumed by ``enumerate_team_matchups``.

Public API
----------
``survivors_from_games`` — derive ``known_survivors`` and ``r1_survivors``
from a list of school-perspective ``Game`` rows.
"""

from __future__ import annotations

from backend.helpers.data_classes import Game

_FIRST_ROUND = "First Round"


def survivors_from_games(
    games: list[Game],
    school_to_seed: dict[str, tuple[int, int]],
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Build survivor sets from completed playoff ``Game`` records.

    Each playoff matchup produces two ``Game`` rows in the DB (one per team).
    This function reads the ``result`` field (``'W'`` / ``'L'``) and ``round``
    field to derive two sets used by ``enumerate_team_matchups``:

    * **known_survivors** — teams that are currently alive: they have at least
      one win and no loss among the provided records.  Pass as
      ``known_survivors`` to filter out eliminated opponents from future rounds.

    * **r1_survivors** — teams that won their First Round game specifically,
      regardless of what happened in later rounds.  Pass as ``r1_survivors`` to
      fix R2-opponent choices in the QF home-count computation.

    Args:
        games: School-perspective ``Game`` records for completed playoff games.
            Only records with ``result='W'`` or ``result='L'`` are used;
            records with ``None`` result (unplayed games) are ignored.
        school_to_seed: Mapping from school name to ``(region, seed)`` in the
            bracket.  Schools that do not appear in this mapping are silently
            skipped (e.g. opponents from outside the tracked bracket half).

    Returns:
        ``(known_survivors, r1_survivors)`` — both as sets of
        ``(region, seed)`` tuples.

    Raises:
        ValueError: If a ``Game`` with ``result='W'`` or ``result='L'`` has
            a ``school`` not present in *school_to_seed* and the caller needs
            strict validation.  (Currently skipped silently — callers may
            pass a partial lookup covering only one bracket half.)
    """
    winners: set[str] = set()
    losers: set[str] = set()
    r1_winners: set[str] = set()

    for game in games:
        if game.result == "W":
            winners.add(game.school)
            if game.round == _FIRST_ROUND:
                r1_winners.add(game.school)
        elif game.result == "L":
            losers.add(game.school)

    # Still alive = won at least once and never lost.
    alive_schools = winners - losers

    def _to_seeds(schools: set[str]) -> set[tuple[int, int]]:
        """Map school names to (region, seed) tuples, skipping unknown schools."""
        result: set[tuple[int, int]] = set()
        for school in schools:
            if school in school_to_seed:
                result.add(school_to_seed[school])
        return result

    return _to_seeds(alive_schools), _to_seeds(r1_winners)
