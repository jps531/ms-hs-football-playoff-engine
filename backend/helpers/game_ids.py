"""Which rows of ``games`` are the same game: the ``game_id`` both schools' rows share.

``games`` has a row per school per game. Two rows are one game when each is the
other's nearest match: the opponent's row against this school in the same
season, within three days (the two schools' pages can date one game a day
apart; rows further apart are different games, like a playoff rematch). Ties
go to the later date, as ``games_effective.game_date`` does.

``assign_game_ids`` works out the ids that make ``game_id`` match that pairing,
keeping each row's id wherever it can, since submissions refer to a game by
``(game_id, school)``. Pure functions only; ``ahsfhs_schedule_pipeline`` reads
the rows and writes the changes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

PAIR_DAYS = 3


@dataclass(frozen=True)
class GameRow:
    """One school's row of a game, as far as pairing needs it."""

    school: str
    date: date
    opponent: str | None
    game_id: int

    @property
    def key(self) -> tuple[str, date]:
        """The row's primary key."""
        return (self.school, self.date)


@dataclass(frozen=True)
class GameIdChange:
    """A row whose ``game_id`` changes from ``old`` to ``new``."""

    school: str
    date: date
    old: int
    new: int


def pair_rows(rows: Iterable[GameRow]) -> dict[tuple[str, date], tuple[str, date]]:
    """Each paired row's key mapped to its partner's (both directions). Rows of one season."""
    rows = list(rows)
    by_school: dict[str, list[GameRow]] = defaultdict(list)
    for row in rows:
        by_school[row.school].append(row)

    nearest: dict[tuple[str, date], tuple[str, date]] = {}
    for row in rows:
        if not row.opponent:
            continue
        matches = [
            o
            for o in by_school.get(row.opponent, ())
            if o.opponent == row.school and abs((o.date - row.date).days) <= PAIR_DAYS
        ]
        if matches:
            best = min(matches, key=lambda o: (abs((o.date - row.date).days), -o.date.toordinal()))
            nearest[row.key] = best.key
    return {k: v for k, v in nearest.items() if nearest.get(v) == k}


def assign_game_ids(rows: Iterable[GameRow], new_id: Callable[[], int]) -> list[GameIdChange]:
    """The ``game_id`` changes that give paired rows one id and every other row its own.

    A game keeps an id one of its rows already has. A game whose rows all
    already share an id no other row has is left alone; the rest take the
    smallest free id among their rows' (the older one), preferring the game
    that holds an id with more rows. A game with no free id gets ``new_id()``.
    """
    rows = sorted(rows, key=lambda r: r.key)
    by_key = {r.key: r for r in rows}
    partners = pair_rows(rows)

    games: list[tuple[GameRow, ...]] = []
    seen: set[tuple[str, date]] = set()
    for row in rows:
        if row.key in seen:
            continue
        group = (row, by_key[partners[row.key]]) if row.key in partners else (row,)
        seen.update(r.key for r in group)
        games.append(group)

    holders: dict[int, int] = defaultdict(int)
    for row in rows:
        holders[row.game_id] += 1

    claimed: set[int] = set()
    chosen: dict[int, int] = {}
    for i, group in enumerate(games):
        ids = {r.game_id for r in group}
        if len(ids) == 1 and holders[(only := ids.pop())] == len(group):
            chosen[i] = only
            claimed.add(only)

    def priority(i: int) -> tuple:
        ids = [r.game_id for r in games[i]]
        return (-max(ids.count(x) for x in ids), min(ids), games[i][0].key)

    for i in sorted((i for i in range(len(games)) if i not in chosen), key=priority):
        free = sorted({r.game_id for r in games[i]} - claimed)
        chosen[i] = free[0] if free else new_id()
        claimed.add(chosen[i])

    return [
        GameIdChange(r.school, r.date, r.game_id, chosen[i])
        for i, group in enumerate(games)
        for r in group
        if r.game_id != chosen[i]
    ]
