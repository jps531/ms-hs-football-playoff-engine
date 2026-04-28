"""Admin endpoints for season setup and data maintenance."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.requests import AssignChampionshipVenueRequest, PlayoffFormatRequest
from backend.api.models.responses import (
    AssignChampionshipVenueResult,
    ChampionshipGameRow,
    LocationModel,
    PlayoffFormatSeedResult,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


# ---------------------------------------------------------------------------
# Locations (read-only helper for the championship venue picker)
# ---------------------------------------------------------------------------


@router.get("/locations")
async def list_locations() -> list[LocationModel]:
    """Return all venues in the locations table, ordered by name."""
    async with get_conn() as conn:
        rows = await conn.execute(
            "SELECT id, name, city, home_team FROM locations ORDER BY name"
        )
        return [
            LocationModel(id=r[0], name=r[1], city=r[2], home_team=r[3])
            async for r in rows
        ]


# ---------------------------------------------------------------------------
# Playoff format seeding
# ---------------------------------------------------------------------------


@router.post("/playoff-format")
async def seed_playoff_format(
    body: PlayoffFormatRequest,
    dry_run: Annotated[bool, Query()] = False,
) -> PlayoffFormatSeedResult:
    """Seed playoff_formats and playoff_format_slots for a new season.

    Idempotent — rows already present are skipped (ON CONFLICT DO NOTHING).
    Pass ``?dry_run=true`` to preview the counts without writing.
    """
    season = body.season
    total_slots = sum(len(c.slots) for c in body.classes)

    if dry_run:
        return PlayoffFormatSeedResult(
            season=season,
            classes_inserted=len(body.classes),
            slots_inserted=total_slots,
            dry_run=True,
        )

    format_sql = """
        INSERT INTO playoff_formats (season, class, num_regions, seeds_per_region, num_rounds, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (season, class) DO NOTHING
    """
    slot_sql = """
        INSERT INTO playoff_format_slots
            (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
        SELECT f.id, $1, $2, $3, $4, $5, $6
        FROM playoff_formats f
        WHERE f.season = $7 AND f.class = $8
        ON CONFLICT DO NOTHING
    """

    async with get_conn() as conn:
        for cls in body.classes:
            notes = cls.notes or f"{cls.class_}A — {cls.num_regions * cls.seeds_per_region}-team bracket"
            await conn.execute(
                format_sql,
                (season, cls.class_, cls.num_regions, cls.seeds_per_region, cls.num_rounds, notes),
            )
            for slot in cls.slots:
                await conn.execute(
                    slot_sql,
                    (
                        slot.slot,
                        slot.home_region,
                        slot.home_seed,
                        slot.away_region,
                        slot.away_seed,
                        slot.north_south,
                        season,
                        cls.class_,
                    ),
                )

    return PlayoffFormatSeedResult(
        season=season,
        classes_inserted=len(body.classes),
        slots_inserted=total_slots,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Championship venue assignment
# ---------------------------------------------------------------------------


@router.post("/championship-venue", responses=_404)
async def assign_championship_venue(
    body: AssignChampionshipVenueRequest,
    dry_run: Annotated[bool, Query()] = False,
) -> AssignChampionshipVenueResult:
    """Assign a venue to all Championship Game rows for a season.

    Championship games arrive from the scraper with ``location_id = NULL``.
    This endpoint sets ``location_id`` and ``location = 'neutral'``.

    Pass ``?dry_run=true`` to preview affected rows without writing.
    """
    async with get_conn() as conn:
        loc_row = await (
            await conn.execute(
                "SELECT id, name FROM locations WHERE id = $1",
                (body.location_id,),
            )
        ).fetchone()
        if loc_row is None:
            raise HTTPException(status_code=404, detail=f"Location id {body.location_id} not found")
        location_name = loc_row[1]

        find_sql = """
            SELECT g.school, g.date, g.opponent, ss.class
            FROM games g
            JOIN school_seasons ss ON ss.school = g.school AND ss.season = g.season
            WHERE g.season = $1
              AND g.round = 'Championship Game'
              AND g.location_id IS NULL
        """
        find_params: list = [body.season]
        if body.class_ is not None:
            find_sql += " AND ss.class = $2"
            find_params.append(body.class_)
        find_sql += " ORDER BY ss.class, g.date, g.school"

        game_rows = await conn.execute(find_sql, find_params)
        games = [
            ChampionshipGameRow(school=r[0], date=r[1], opponent=r[2], class_=r[3])
            async for r in game_rows
        ]

        if not games:
            raise HTTPException(
                status_code=404,
                detail=f"No unassigned Championship Game rows found for season {body.season}"
                + (f" class {body.class_}A" if body.class_ else ""),
            )

        if not dry_run:
            for game in games:
                await conn.execute(
                    "UPDATE games SET location_id = $1, location = 'neutral' WHERE school = $2 AND date = $3",
                    (body.location_id, game.school, game.date),
                )

    return AssignChampionshipVenueResult(
        season=body.season,
        location_id=body.location_id,
        location_name=location_name,
        games_updated=len(games),
        games=games,
        dry_run=dry_run,
    )
