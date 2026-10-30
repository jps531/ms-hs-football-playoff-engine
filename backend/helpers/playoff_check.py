"""Check AHSFHS's playoff games against the bracket's settled games.

A bracket game is settled once both of its teams are known: a first-round
game once both seeds it pairs are known, a later game once both games
feeding it have a winner. AHSFHS's playoff rows must agree with every
settled game: a team listed in a round must be playing the opponent the
bracket pairs it with there, and must not have been knocked out in an
earlier round. A row for a game the bracket hasn't settled, and a settled
game AHSFHS doesn't list yet, are fine.

Pure functions only; ``playoff_pipeline.check_playoff_games`` reads the rows
and reports the disagreements.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.helpers.bracket_matchups import _round_names
from backend.helpers.data_classes import FormatSlot

CHAMPIONSHIP = "Championship Game"


@dataclass(frozen=True)
class PlayoffRow:
    """One school's AHSFHS playoff row: who it plays in which round, and the result if final."""

    school: str
    opponent: str
    round: str
    result: str | None  # W, L or T once final


@dataclass(frozen=True)
class SettledGame:
    """A bracket game whose two teams are known, and its winner once it has one."""

    round: str
    team_a: str
    team_b: str
    winner: str | None


def settled_games(
    slots: list[FormatSlot], seeds: dict[tuple[int, int], str], wins: set[tuple[str, str]]
) -> list[SettledGame]:
    """The bracket's settled games, round by round.

    Args:
        slots: The class's first-round slots (both halves).
        seeds: (region, seed) -> school, for the seeds known so far.
        wins:  (winner, loser) pairs from the final playoff games.
    """

    def play(round_name: str, a: str | None, b: str | None, out: list[SettledGame]) -> str | None:
        """Record the game when both teams are known; return its winner, if it has one."""
        if a is None or b is None:
            return None
        winner = a if (a, b) in wins else b if (b, a) in wins else None
        out.append(SettledGame(round_name, a, b, winner))
        return winner

    games: list[SettledGame] = []
    semifinal_winners: list[str | None] = []
    for half in ("N", "S"):
        half_slots = sorted((s for s in slots if s.north_south == half), key=lambda s: s.slot)
        if not half_slots:
            continue
        names = _round_names(len(half_slots).bit_length())
        winners = [
            play(names[0], seeds.get((s.home_region, s.home_seed)), seeds.get((s.away_region, s.away_seed)), games)
            for s in half_slots
        ]
        for name in names[1:]:
            winners = [play(name, winners[i], winners[i + 1], games) for i in range(0, len(winners), 2)]
        semifinal_winners.append(winners[0])
    if len(semifinal_winners) == 2:
        play(CHAMPIONSHIP, semifinal_winners[0], semifinal_winners[1], games)
    return games


def contradictions(rows: Iterable[PlayoffRow], games: list[SettledGame], round_order: list[str]) -> list[str]:
    """Each way AHSFHS's playoff rows disagree with the settled games, as a sentence.

    *round_order* is the class's round names, first round first (championship last).
    """
    opponent_in: dict[tuple[str, str], str] = {}
    knocked_out: dict[str, str] = {}
    for g in games:
        opponent_in[(g.team_a, g.round)] = g.team_b
        opponent_in[(g.team_b, g.round)] = g.team_a
        if g.winner is not None:
            knocked_out[g.team_b if g.winner == g.team_a else g.team_a] = g.round

    problems = []
    for row in rows:
        if row.round not in round_order:
            problems.append(f"AHSFHS lists {row.school} vs {row.opponent} as a playoff round named {row.round!r}")
            continue
        lost_in = knocked_out.get(row.school)
        if lost_in is not None and round_order.index(row.round) > round_order.index(lost_in):
            problems.append(
                f"AHSFHS has {row.school} playing {row.opponent} in the {row.round}, "
                f"but {row.school} was knocked out in the {lost_in}"
            )
            continue
        expected = opponent_in.get((row.school, row.round))
        if expected is not None and expected != row.opponent:
            problems.append(
                f"AHSFHS has {row.school} playing {row.opponent} in the {row.round}, "
                f"but the bracket has {row.school} playing {expected}"
            )
    return sorted(set(problems))


def round_order(slots: list[FormatSlot]) -> list[str]:
    """The class's round names in order, from its slots (both halves the same size)."""
    per_half = max(sum(1 for s in slots if s.north_south == h) for h in ("N", "S"))
    return [*_round_names(per_half.bit_length()), CHAMPIONSHIP]
