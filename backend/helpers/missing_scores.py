"""Games whose date has passed without a final score, for the daily update's email (``attention``).

AHSFHS sometimes never posts a score, or posts it days late. A region game left without one keeps
counting as still to play, so the standings, odds and scenarios are off until it's in. After the
daily update has committed, it lists every game of the season dated before today (in Mississippi)
that isn't final, so the owner can report or approve the score, or remove a game that didn't happen.
A game marked canceled isn't listed; a forfeit is final, so it isn't either.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.helpers import attention
from backend.helpers.database_helpers import get_database_connection

CENTRAL = ZoneInfo("America/Chicago")

_SQL = """
    SELECT g.date, g.school, g.opponent, g.region_game, ss.class, ss.region
    FROM games_effective g
    JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
    WHERE g.season = %s AND g.date < %s AND g.final IS NOT TRUE
      AND COALESCE(g.game_status, '') <> 'canceled'
    ORDER BY g.date, g.school
"""


def missing_score_lines(rows: list[tuple]) -> list[str]:
    """One line per game from ``_SQL``'s rows, oldest first: "Fri, Oct 23: Stone vs Vancleave (Region 4-5A game)".

    A game between two schools the site follows has a row for each; it's listed once.
    """
    seen: set[tuple] = set()
    lines = []
    for day, school, opponent, region_game, clazz, region in rows:
        key = (day, frozenset((school, opponent)))
        if key in seen:
            continue
        seen.add(key)
        a, b = sorted((school, opponent))
        what = f" (Region {region}-{clazz}A game)" if region_game else ""
        lines.append(f"{day:%a, %b} {day.day}: {a} vs {b}{what}")
    return lines


def note_missing_scores(season: int, today: date | None = None) -> int:
    """Note each game of *season* dated before *today* (default: today in Mississippi) that has no final
    score; returns how many."""
    today = today or datetime.now(CENTRAL).date()
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_SQL, (season, today))
        rows = cur.fetchall()
    lines = missing_score_lines(rows)
    for line in lines:
        attention.note(attention.MISSING_SCORES, line)
    return len(lines)
