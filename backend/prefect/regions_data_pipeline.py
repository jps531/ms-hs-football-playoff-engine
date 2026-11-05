"""Prefect flow that loads a season's region assignments from its cycle file.

Each MHSAA cycle (two seasons) has a checked-in file in ``backend/data/regions/`` (see
``helpers.region_files``), drafted from MHSAA's article with ``python -m backend.tools.draft_regions``
and checked by a person. This flow reads the season's schools from it and checks them against the
database before writing anything: every name a school the site knows (or a rename or successor
starting this season), every region big enough, and every school from last season accounted for. A
problem stops the flow with every problem listed, so nothing is half-loaded.

It then writes each school's class and region to ``school_seasons`` (adding a new school to
``schools``). A successor (``SCHOOL_SUCCESSORS``) takes its old school's campus, location and home
field, when it has none of its own yet. Rows already in the database for the season that the file
doesn't have stop the flow too (deactivate or fix them first); ``is_active`` is never changed.
"""

from __future__ import annotations

from datetime import date

from prefect import flow, get_run_logger, task
from psycopg2.extras import execute_values

from backend.helpers.data_helpers import SCHOOL_SUCCESSORS
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.region_files import assignments_for_season, cycle_path, problems


def check_season(
    season: int, known: set[str], prior: set[str], active: set[str]
) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """*season*'s assignments from its file and what's wrong with them, given the database's schools
    (*known*), last season's active ones (*prior*, empty when there's none) and this season's active
    ones already loaded (*active*)."""
    assigned = assignments_for_season(season)
    issues = problems(assigned, season, known, prior or None)
    for school in sorted(active - set(assigned)):
        issues.append(
            f"{school} is active in the database for {season} but not in its file. Add it to the file, "
            f"or deactivate it (PATCH /api/v1/admin/school-seasons/{school}/{season})."
        )
    return assigned, issues


@task(task_run_name="Read the database's schools")
def read_schools(season: int) -> tuple[set[str], set[str], set[str]]:  # pragma: no cover - the database
    """Every school, last season's active schools, and this season's active schools already loaded."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT school FROM schools")
        known = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT school, season FROM school_seasons WHERE season IN (%s, %s) AND is_active", (season - 1, season)
        )
        rows = cur.fetchall()
    return known, {s for s, y in rows if y == season - 1}, {s for s, y in rows if y == season}


@task(task_run_name="Write the season's regions")
def write_season(season: int, assigned: dict[str, tuple[int, int]]) -> int:  # pragma: no cover - the database
    """Add new schools, give each successor its old school's campus, and upsert every school's class and
    region for *season*, in one transaction. Returns the number of schools written."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur, "INSERT INTO schools (school) VALUES %s ON CONFLICT (school) DO NOTHING", [(s,) for s in assigned]
            )
            for old, new, first in SCHOOL_SUCCESSORS:
                if first != season or new not in assigned:
                    continue
                cur.execute(
                    """
                    UPDATE schools n SET city = o.city, zip = o.zip, latitude = o.latitude, longitude = o.longitude
                    FROM schools o
                    WHERE n.school = %s AND o.school = %s AND n.latitude IS NULL AND n.longitude IS NULL
                    """,
                    (new, old),
                )
                cur.execute(
                    """
                    INSERT INTO locations (name, city, home_team, latitude, longitude)
                    SELECT name, city, %s, latitude, longitude FROM locations
                    WHERE home_team = %s AND NOT EXISTS (SELECT 1 FROM locations WHERE home_team = %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (new, old, new),
                )
            execute_values(
                cur,
                """
                INSERT INTO school_seasons (school, season, class, region) VALUES %s
                ON CONFLICT (school, season) DO UPDATE SET class = EXCLUDED.class, region = EXCLUDED.region
                """,
                [(s, season, c, r) for s, (c, r) in assigned.items()],
                template="(%s,%s,%s,%s)",
            )
        conn.commit()
    return len(assigned)


@flow(name="Regions Data Flow")
def regions_data_flow(season: int | None = None) -> int:
    """Load *season*'s regions (default: this year) from its cycle's file, if every check passes."""
    if season is None:
        season = date.today().year
    logger = get_run_logger()
    path = cycle_path(season)
    if not path.exists():
        raise ValueError(
            f"No region file for the {season} season ({path.name} in backend/data/regions/). Draft it with "
            f"`python -m backend.tools.draft_regions --season {season}`, check it, and commit it."
        )
    known, prior, active = read_schools(season)
    assigned, issues = check_season(season, known, prior, active)
    if issues:
        for issue in issues:
            logger.error(issue)
        raise ValueError(
            f"{path.name} isn't ready for {season}: {len(issues)} problems (listed above). Nothing was written."
        )
    written = write_season(season, assigned)
    logger.info("Wrote %d schools' %d regions from %s", written, season, path.name)
    return written
