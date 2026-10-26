"""How soon a night's final scores reach AHSFHS: a morning-after probe.

The daily update pulls scores at 9:00 AM Central. To learn whether an earlier
pull would find them, this flow checks a small sample of AHSFHS team pages
(one team per region that played the night before) every 15 minutes from 6 to
10 AM on Friday and Saturday (for Thursday's and Friday's games), and records
how many of the night's games already show a final score. It reads AHSFHS only; nothing is written to the database.
Each run's counts are logged and saved as a table artifact under the key
``ahsfhs-score-probe``, so the Prefect UI shows them run by run.
"""

import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_table_artifact

from backend.helpers.data_classes import Game, School
from backend.helpers.data_helpers import source_name_for_season, update_school_name_for_ahsfhs_search
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.web_helpers import fetch_article_text_from_ahsfhs
from backend.prefect.ahsfhs_schedule_pipeline import get_existing_schools, parse_ahsfhs_schedule

CENTRAL = ZoneInfo("America/Chicago")

# Before 3 PM, the night being probed is the one before (a 1 AM run on
# Saturday is looking for Friday's scores); from 3 PM on, it's tonight.
_NIGHT_STARTS_HOUR = 15


def probe_game_date(now: datetime) -> date:
    """The night whose scores a probe at *now* is looking for, in Central time."""
    local = now.astimezone(CENTRAL)
    return local.date() if local.hour >= _NIGHT_STARTS_HOUR else local.date() - timedelta(days=1)


def pick_probe_schools(schools: Iterable[School], playing: set[str]) -> list[School]:
    """One school per class and region among those that play on the night: the first alphabetically.

    The same night always gets the same sample, so successive runs are comparable.
    """
    picked: dict[tuple[int, int], School] = {}
    for s in sorted(schools, key=lambda s: s.school):
        if s.school in playing:
            picked.setdefault((s.class_, s.region), s)
    return [picked[k] for k in sorted(picked)]


def summarize_probe(checked: Iterable[tuple[School, list[Game] | None]], game_date: date) -> list[dict[str, object]]:
    """Per-class counts of the night's games found on the sampled pages, and how many are final.

    *checked* pairs each sampled school with its parsed games, or ``None`` when its page
    couldn't be read. A page that lists no game on the night counts as neither.
    """
    rows: dict[int, dict[str, object]] = {}
    for school, games in checked:
        row = rows.setdefault(
            school.class_, {"class": f"{school.class_}A", "teams_checked": 0, "games": 0, "final": 0, "unreadable": 0}
        )
        row["teams_checked"] += 1
        if games is None:
            row["unreadable"] += 1
            continue
        tonight = [g for g in games if g.date == game_date]
        row["games"] += len(tonight)
        row["final"] += sum(1 for g in tonight if g.final)
    return [rows[c] for c in sorted(rows)]


@task(task_run_name="Find Schools Playing on {game_date}")
def schools_playing_on(season: int, game_date: date) -> set[str]:
    """Schools with a game on *game_date*, by the schedule already in the database."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT school FROM games WHERE season = %s AND date = %s", (season, game_date))
            return {row[0] for row in cur.fetchall()}


@task(task_run_name="Check AHSFHS Pages for {game_date}")
def check_pages(schools: list[School], season: int, game_date: date) -> list[tuple[School, list[Game] | None]]:
    """Fetch and parse each sampled school's AHSFHS page; ``None`` where it couldn't be read."""
    logger = get_run_logger()
    checked: list[tuple[School, list[Game] | None]] = []
    for school in schools:
        source = source_name_for_season(school.school, season)  # a renamed school's page is still under its old name
        url = f"https://www.ahsfhs.org/MISSISSIPPI/teams/gamesbyyear.asp?Team={update_school_name_for_ahsfhs_search(source)}&Year={season}"
        try:
            text = fetch_article_text_from_ahsfhs(url)
            games = parse_ahsfhs_schedule(
                text or "", season=season, school_name=school.school, url=url, clazz=school.class_
            )
        except Exception:
            logger.warning("Couldn't read AHSFHS page for %r via %s", school.school, url, exc_info=True)
            games = None
        checked.append((school, games))
        # Be polite to AHSFHS
        time.sleep(0.3)
    return checked


@flow(name="AHSFHS Score Probe")
def ahsfhs_score_probe_flow(game_date: date | None = None) -> list[dict[str, object]]:
    """Record how many of a night's final scores AHSFHS shows right now, for a one-team-per-region sample."""
    probed_at = datetime.now(CENTRAL)
    if game_date is None:
        game_date = probe_game_date(probed_at)
    season = game_date.year
    logger = get_run_logger()
    sample = pick_probe_schools(get_existing_schools(season), schools_playing_on(season, game_date))
    if not sample:
        logger.info("No games scheduled on %s; nothing to probe", game_date)
        return []
    rows = summarize_probe(check_pages(sample, season, game_date), game_date)
    stamp = probed_at.strftime("%a %b %-d, %-I:%M %p %Z")
    total_games = sum(r["games"] for r in rows)
    total_final = sum(r["final"] for r in rows)
    logger.info("AHSFHS at %s: %d of %d sampled games on %s are final", stamp, total_final, total_games, game_date)
    create_table_artifact(
        key="ahsfhs-score-probe",
        table=[{"probed_at": stamp, "game_date": game_date.isoformat(), **r} for r in rows],
        description=f"AHSFHS at {stamp}: {total_final} of {total_games} sampled games on {game_date} final",
    )
    return rows
