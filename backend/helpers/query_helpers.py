"""Small SQL-fragment builders and DB-backed validation helpers shared across routers."""

from fastapi import HTTPException
from psycopg import sql


async def require_school_exists(conn, school: str) -> None:
    """Raise HTTP 404 if *school* is not present in the ``schools`` table."""
    row = await (await conn.execute("SELECT 1 FROM schools WHERE school = %s", (school,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"School '{school}' not found")


def and_join_conditions(conditions: list[str]) -> sql.Composed:
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
