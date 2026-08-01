"""DB-touching wrapper around backend.helpers.color_contrast.

This is the "one place" (docs/proposals/COLOR_CLAMP_SPEC.md §5) that
recomputes and persists a school's ``color_variants`` blob. Called from five
independent sites: submission approval, the direct admin school-override
endpoint, the admin manual-repair endpoints, the MHSAA scrape pipeline, and
the one-off backfill flow. All actual contrast math lives in
``color_contrast.py`` — this module only reads the effective hex colors,
calls it, and writes the result.

Public API
----------
recompute_color_variants()       — async/psycopg3 entry point (existing connection)
recompute_color_variants_sync()  — sync/psycopg2 entry point (existing connection)
split_secondary_hexes()          — comma-joined secondary_color_hex -> list of hex strings
"""

import json
import logging
from datetime import UTC, datetime

from psycopg2.extras import Json

from backend.helpers.color_contrast import ALGORITHM_VERSION, compute_color_variants

_log = logging.getLogger(__name__)

_SELECT_EFFECTIVE_COLORS = "SELECT primary_color_hex, secondary_color_hex FROM schools_effective WHERE school = %s"
_UPDATE_COLOR_VARIANTS = "UPDATE schools SET color_variants = %s WHERE school = %s"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string. Isolated for test monkeypatching."""
    return datetime.now(UTC).isoformat()


def split_secondary_hexes(secondary_color_hex: str | None) -> list[str]:
    """Split a comma-joined ``secondary_color_hex`` value into individual hex strings."""
    if not secondary_color_hex:
        return []
    return [h.strip() for h in secondary_color_hex.split(",") if h.strip()]


def _build_blob(primary_hex: str | None, secondary_color_hex: str | None, school: str) -> dict:
    """Compute variants for one school's effective colors and log any skipped/malformed hex."""
    secondary_hexes = split_secondary_hexes(secondary_color_hex)
    result = compute_color_variants(primary_hex, secondary_hexes)
    for warning in result.warnings:
        _log.warning("color_variants: %s school=%s", warning, school)
    return {
        "primary": result.primary,
        "secondary": result.secondary,
        "computed_at": _now_iso(),
        "algorithm_version": ALGORITHM_VERSION,
    }


async def recompute_color_variants(conn, school: str) -> dict | None:
    """Recompute and persist ``color_variants`` for *school* (async/psycopg3).

    Takes an existing connection and never opens its own transaction — the
    caller commits (or rolls back) alongside whatever write triggered the
    recompute. Returns the written blob, or None if *school* doesn't exist.
    """
    row = await (await conn.execute(_SELECT_EFFECTIVE_COLORS, (school,))).fetchone()
    if row is None:
        return None

    blob = _build_blob(row[0], row[1], school)
    await conn.execute(_UPDATE_COLOR_VARIANTS, (json.dumps(blob), school))
    return blob


def recompute_color_variants_sync(conn, school: str) -> dict | None:
    """Recompute and persist ``color_variants`` for *school* (sync/psycopg2).

    Takes an existing connection and does not commit — the caller commits,
    matching the batch-commit pattern used by the Prefect pipeline tasks.
    Returns the written blob, or None if *school* doesn't exist.
    """
    with conn.cursor() as cur:
        cur.execute(_SELECT_EFFECTIVE_COLORS, (school,))
        row = cur.fetchone()
        if row is None:
            return None

        blob = _build_blob(row[0], row[1], school)
        cur.execute(_UPDATE_COLOR_VARIANTS, (Json(blob), school))
    return blob
