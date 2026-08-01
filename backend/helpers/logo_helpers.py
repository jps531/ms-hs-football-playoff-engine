"""Team logo asset resolution and cache-sync helpers, mirroring helmet_designs.

Resolution itself is a single SQL query (``logo_covers_season()``, mirroring
``helmet_covers_season()``) issued directly by routers — no Python resolution
layer is needed since there's no non-contiguous-span case to reduce first
(contrast with helmets, which resolve the same way via a plain query too —
see ``resolve_team_helmet`` in ``backend/api/routers/meta.py``). This module
holds the DB row-mapping helpers (mirroring ``HELMET_FIELD_COLS``/
``build_helmet_from_row`` in ``api_helpers.py``) plus the cache-sync wrapper
that keeps ``schools.logo_primary/secondary/tertiary`` in sync with
``team_logos`` after every write — "recompute after write, never on read,"
the same philosophy ``recompute_color_variants`` uses for color_variants.

Public API
----------
LOGO_FIELD_COLS       — team_logos column order for row-mapping
TEAM_LOGOS_SELECT      — base SELECT string, callers append WHERE/ORDER BY
build_logo_from_row()  — map a team_logos row to TeamLogoModel
sync_logo_cache()      — DB wrapper: re-resolve the current season's winner
                          for (school, logo_type) and write it into
                          schools.logo_{type}
"""

from backend.api.models.responses import TeamLogoModel
from backend.helpers.query_helpers import set_school_logo_column

LOGO_FIELD_COLS = (
    "id",
    "school",
    "logo_type",
    "image_url",
    "year_start",
    "year_end",
    "is_primary",
    "has_keyline",
    "notes",
    "source_submission_id",
    "created_at",
    "updated_at",
)

TEAM_LOGOS_SELECT = f"SELECT {', '.join(LOGO_FIELD_COLS)} FROM team_logos"
"""Base SELECT for team_logos, column order matching LOGO_FIELD_COLS. Callers append their own WHERE/ORDER BY."""


def build_logo_from_row(row: tuple) -> TeamLogoModel:
    """Build a TeamLogoModel from a team_logos row, column order matching LOGO_FIELD_COLS."""
    return TeamLogoModel(**dict(zip(LOGO_FIELD_COLS, row, strict=True)))


async def sync_logo_cache(conn, school: str, logo_type: str, season: int) -> None:
    """Re-resolve the (school, logo_type) logo for *season* and write it into
    the schools.logo_{logo_type} cache column.

    Call this after every team_logos-mutating write (create, patch, delete,
    image upload) so the cache column never drifts — it is recomputed
    immediately rather than lazily on read. Writes an empty string when no
    team_logos row covers *season*, matching schools.logo_{type}'s existing
    "empty when not yet uploaded" convention.
    """
    query = (
        TEAM_LOGOS_SELECT + " WHERE school = %s AND logo_type = %s AND logo_covers_season(year_start, year_end, %s)"
        " ORDER BY is_primary DESC, year_start DESC NULLS LAST LIMIT 1"
    )
    row = await (await conn.execute(query, (school, logo_type, season))).fetchone()
    image_url = row[LOGO_FIELD_COLS.index("image_url")] if row is not None else None
    await set_school_logo_column(conn, school, logo_type, image_url or "")
