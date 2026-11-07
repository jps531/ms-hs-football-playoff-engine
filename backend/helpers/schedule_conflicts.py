"""Past games one school's AHSFHS page lists that its opponent's page doesn't, for the daily email.

Each game has a row per school, from that school's own page, and the two rows are paired into one game
(``game_ids``). A row against an in-state school that nothing pairs with is a game only one page has: often
one page naming the wrong opponent (Amanda Elzy's page listing Leflore County on a night it played
Charleston, whose page lists Amanda Elzy), sometimes a game that was never played. Its score then counts
for one school only, and the ratings count a game that didn't happen. After the daily update has
committed, each such past game is listed with what the opponent's page has that week, so the owner can
correct the opponent (``set_game_opponent``) or mark the game canceled.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.helpers import attention
from backend.helpers.database_helpers import get_database_connection

CENTRAL = ZoneInfo("America/Chicago")

# The season's past rows against an in-state school with no row of the same game from that school,
# and the games that school's page lists within three days instead.
_SQL = """
    SELECT g.date, g.school, g.opponent, g.result, g.points_for, g.points_against,
           (SELECT string_agg(o.opponent, ', ' ORDER BY o.date, o.opponent)
              FROM games_effective o
             WHERE o.school = g.opponent AND o.season = g.season
               AND o.date BETWEEN g.date - 3 AND g.date + 3
               AND COALESCE(o.game_status, '') <> 'canceled') AS listed
    FROM games_effective g
    JOIN school_seasons os ON os.school = g.opponent AND os.season = g.season
    WHERE g.season = %s AND g.date < %s
      AND COALESCE(g.game_status, '') <> 'canceled'
      AND NOT EXISTS (SELECT 1 FROM games x WHERE x.game_id = g.game_id AND x.school = g.opponent)
    ORDER BY g.date, g.school
"""


def _possessive(name: str) -> str:
    """ "Charleston's", "Bay Springs'"."""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def conflict_lines(rows: list[tuple]) -> list[str]:
    """One line per row from ``_SQL``: "Fri, Aug 28: Amanda Elzy's page lists Leflore County (L 0–42);
    Leflore County's page lists Shaw that week"."""
    lines = []
    for day, school, opponent, result, points_for, points_against, listed in rows:
        score = f" ({result} {points_for}–{points_against})" if result and points_for is not None else ""
        other = f"lists {listed}" if listed else "has no game"
        lines.append(
            f"{day:%a, %b} {day.day}: {_possessive(school)} page lists {opponent}{score}; "
            f"{_possessive(opponent)} page {other} that week"
        )
    return lines


def note_schedule_conflicts(season: int, today: date | None = None) -> int:
    """Note each game of *season* dated before *today* (default: today in Mississippi) that one school's
    page lists and its in-state opponent's page doesn't; returns how many."""
    today = today or datetime.now(CENTRAL).date()
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_SQL, (season, today))
        rows = cur.fetchall()
    lines = conflict_lines(rows)
    for line in lines:
        attention.note(attention.SCHEDULES_DISAGREE, line)
    return len(lines)
