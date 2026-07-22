"""Small SQL-fragment builders and DB-backed validation helpers shared across routers."""

from collections.abc import Sequence
from typing import LiteralString

from fastapi import HTTPException
from psycopg import sql


async def require_school_exists(conn, school: str) -> None:  # pragma: no cover
    """Raise HTTP 404 if *school* is not present in the ``schools`` table."""
    row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"School '{school}' not found")


async def require_game_exists(conn, school: str, game_date) -> None:  # pragma: no cover
    """Raise HTTP 404 if no game exists for *school* on *game_date*."""
    row = await (
        await conn.execute("SELECT 1 FROM games WHERE school = %s AND date = %s", (school, game_date))
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Game for '{school}' on {game_date} not found")


async def require_location_exists(conn, location_id: int) -> None:  # pragma: no cover
    """Raise HTTP 404 if no location exists with *location_id*."""
    row = await (await conn.execute("SELECT 1 FROM locations WHERE id = %s", (location_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")


async def require_helmet_design_exists(conn, design_id: int) -> None:  # pragma: no cover
    """Raise HTTP 404 if no helmet design exists with *design_id*."""
    row = await (await conn.execute("SELECT 1 FROM helmet_designs WHERE id = %s", (design_id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Helmet design {design_id} not found")


async def set_school_logo_column(conn, school: str, logo_type: str, path: str) -> None:  # pragma: no cover
    """Write *path* into the ``schools.logo_{logo_type}`` column for *school*."""
    col = sql.Identifier(f"logo_{logo_type}")
    await conn.execute(
        sql.SQL("UPDATE schools SET {} = %s WHERE school = %s").format(col),
        (path, school),
    )


def and_join_conditions(conditions: Sequence[LiteralString]) -> sql.Composed:
    """Join raw SQL condition strings with ``AND``, for a dynamic ``WHERE`` clause."""
    return sql.SQL(" AND ").join(sql.SQL(c) for c in conditions)


def build_set_clause(update_data: dict) -> sql.Composed:
    """Build a ``col1 = %s, col2 = %s, ...`` fragment from an update dict.

    Column order matches ``update_data``'s iteration order — pass
    ``list(update_data.values())`` (same order) as the corresponding query params.
    """
    return sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in update_data)


def require_nonempty_update(update_data: dict) -> None:
    """Raise HTTP 422 if *update_data* (from ``body.model_dump(exclude_unset/none=True)``) is empty."""
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided to update")
