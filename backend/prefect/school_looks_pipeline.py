"""Prefect flow that loads schools' past looks (mascot and colors by season) from
``backend/data/school_looks.csv`` (``helpers.school_looks``).

It checks the file against the database's schools before writing anything; a problem stops the flow
with every problem listed. It then makes ``school_looks`` the file's: each look's row is written (its
color variants worked out from its hex colors, as ``schools``' are), keeping a row's ``overrides``
(moderators'), and a row the file no longer has is removed.
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task
from psycopg2.extras import Json

from backend.helpers.color_variants import _build_blob
from backend.helpers.database_helpers import get_database_connection
from backend.helpers.school_looks import LOOKS_PATH, problems, read_looks


@task(task_run_name="Read the database's schools")
def read_schools() -> set[str]:  # pragma: no cover - the database
    """Every school the site has."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT school FROM schools")
        return {r[0] for r in cur.fetchall()}


@task(task_run_name="Write the looks")
def write_looks(looks: list[dict]) -> int:  # pragma: no cover - the database
    """Make school_looks the file's *looks*, in one transaction; returns how many were written."""
    with get_database_connection() as conn:
        with conn.cursor() as cur:
            keys = [(lk["school"], lk["first_season"] if lk["first_season"] is not None else 0) for lk in looks]
            cur.execute("SELECT id, school, COALESCE(first_season, 0) FROM school_looks")
            for row_id, school, first in cur.fetchall():
                if (school, first) not in keys:
                    cur.execute("DELETE FROM school_looks WHERE id = %s", (row_id,))
            for lk in looks:
                variants = _build_blob(lk["primary_color_hex"], lk["secondary_color_hex"], lk["school"])
                cur.execute(
                    """
                    INSERT INTO school_looks (school, first_season, last_season, mascot, primary_color,
                      secondary_color, primary_color_hex, secondary_color_hex, color_variants, approximate, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (school, COALESCE(first_season, 0)) DO UPDATE SET
                      first_season = EXCLUDED.first_season, last_season = EXCLUDED.last_season,
                      mascot = EXCLUDED.mascot, primary_color = EXCLUDED.primary_color,
                      secondary_color = EXCLUDED.secondary_color, primary_color_hex = EXCLUDED.primary_color_hex,
                      secondary_color_hex = EXCLUDED.secondary_color_hex, color_variants = EXCLUDED.color_variants,
                      approximate = EXCLUDED.approximate, note = EXCLUDED.note
                    """,
                    (
                        lk["school"],
                        lk["first_season"],
                        lk["last_season"],
                        lk["mascot"],
                        lk["primary_color"],
                        lk["secondary_color"],
                        lk["primary_color_hex"],
                        lk["secondary_color_hex"],
                        Json(variants),
                        lk["approximate"],
                        lk["note"],
                    ),
                )
        conn.commit()
    return len(looks)


@flow(name="School Looks Flow")
def school_looks_flow() -> int:
    """Load the schools' past looks from the file, if every check passes."""
    logger = get_run_logger()
    looks = read_looks(LOOKS_PATH)
    issues = problems(looks, read_schools())
    if issues:
        for issue in issues:
            logger.error(issue)
        raise ValueError(f"{LOOKS_PATH.name} isn't ready: {len(issues)} problems (listed above). Nothing was written.")
    written = write_looks(looks)
    logger.info("Wrote %d looks from %s", written, LOOKS_PATH.name)
    return written
