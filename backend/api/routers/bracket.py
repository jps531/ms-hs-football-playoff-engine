"""Bracket advancement odds endpoints."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.api.db import get_conn
from backend.api.limiter import limiter
from backend.api.models.requests import SimulateBracketRequest
from backend.api.models.responses import BracketResponse
from backend.helpers.api_helpers import (
    bracket_results_to_applied,
    build_bracket_entries,
    build_bracket_entries_from_odds_map,
    build_bracket_teams,
    num_rounds_for_class,
)
from backend.helpers.data_classes import FormatSlot, StandingsOdds
from backend.helpers.scenario_updater import apply_bracket_game_results

router = APIRouter(prefix="/api/v1", tags=["bracket"])

SeasonQ = Annotated[int, Query(ge=2020, le=2040)]
ClassQ = Annotated[int, Query(alias="class", ge=1, le=7)]
_404: dict[int | str, dict[str, Any]] = {404: {"description": "Not found"}}


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


async def _load_format_slots(conn, season: int, clazz: int) -> list[FormatSlot]:
    """Return all playoff format slots for *clazz* in *season*."""
    rows = await conn.execute(
        """
        SELECT pfs.slot, pfs.home_region, pfs.home_seed,
               pfs.away_region, pfs.away_seed, pfs.north_south
        FROM playoff_format_slots pfs
        JOIN playoff_formats pf ON pfs.format_id = pf.id
        WHERE pf.season = %s AND pf.class = %s
        ORDER BY pfs.slot
        """,
        (season, clazz),
    )
    return [
        FormatSlot(slot=r[0], home_region=r[1], home_seed=r[2], away_region=r[3], away_seed=r[4], north_south=r[5])
        async for r in rows
    ]


async def _load_all_region_odds(conn, season: int, clazz: int, as_of: date) -> dict[int, dict[str, StandingsOdds]]:
    """Return {region: {school: StandingsOdds}} for all regions in *clazz*."""
    rows = await conn.execute(
        """
        SELECT DISTINCT ON (school)
            school, region, odds_1st, odds_2nd, odds_3rd, odds_4th,
            odds_playoffs, clinched, eliminated
        FROM region_standings
        WHERE season = %s AND class = %s AND as_of_date <= %s
        ORDER BY school, as_of_date DESC
        """,
        (season, clazz, as_of),
    )
    by_region: dict[int, dict[str, StandingsOdds]] = {}
    async for r in rows:
        school, region = r[0], r[1]
        by_region.setdefault(region, {})[school] = StandingsOdds(
            school=school,
            p1=r[2],
            p2=r[3],
            p3=r[4],
            p4=r[5],
            p_playoffs=r[6],
            final_playoffs=r[6],
            clinched=r[7],
            eliminated=r[8],
        )
    return by_region


@router.get("/bracket", responses=_404)
async def get_bracket(
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketResponse:
    """Return bracket advancement odds for all seed slots in *class_* for *season*.

    Each entry represents one (region, seed) slot.  ``school`` is set only when
    the team has clinched that seed position; otherwise it is null.
    """
    as_of = date or _today()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, class_)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format for {class_}A season {season}")
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")

    entries = build_bracket_entries(by_region, slots)
    return BracketResponse(season=season, class_=class_, teams=entries)


@router.post("/bracket/simulate", responses=_404)
@limiter.limit("10/minute")
async def simulate_bracket(
    request: Request,
    body: SimulateBracketRequest,
    season: SeasonQ,
    class_: ClassQ,
    date: Annotated[date | None, Query()] = None,
) -> BracketResponse:
    """Apply hypothetical bracket game results and return updated advancement odds.

    Results are specified as (home_region, home_seed, away_region, away_seed, home_wins).
    Slot identifiers (``"R{region}S{seed}"``) are used internally; ``school`` is only
    populated in the response when a team has clinched that seed.
    """
    as_of = date or _today()
    async with get_conn() as conn:
        slots = await _load_format_slots(conn, season, class_)
        if not slots:
            raise HTTPException(status_code=404, detail=f"No playoff format for {class_}A season {season}")
        by_region = await _load_all_region_odds(conn, season, class_, as_of)
        if not by_region:
            raise HTTPException(status_code=404, detail=f"No standings data for {class_}A season {season}")

    bracket_teams = build_bracket_teams(by_region, season)
    new_results = bracket_results_to_applied(body.results)
    updated_odds = apply_bracket_game_results(bracket_teams, num_rounds_for_class(class_), [], new_results)

    entries = build_bracket_entries_from_odds_map(by_region, updated_odds)
    return BracketResponse(season=season, class_=class_, teams=entries)
