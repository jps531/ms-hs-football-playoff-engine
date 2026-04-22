"""Bracket advancement odds endpoints."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.db import get_conn
from backend.api.models.requests import SimulateBracketRequest
from backend.api.models.responses import BracketResponse, TeamBracketEntry
from backend.helpers.bracket_home_odds import compute_bracket_advancement_odds
from backend.helpers.data_classes import AppliedGameResult, BracketTeam, FormatSlot, StandingsOdds
from backend.helpers.scenario_updater import apply_bracket_game_results

router = APIRouter(prefix="/api/v1", tags=["bracket"])

SeasonQ = Annotated[int, Query()]
_404 = {404: {"description": "Not found"}}

_CLINCHED_THRESHOLD = 0.999


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


async def _load_all_region_odds(
    conn, season: int, clazz: int, as_of: date
) -> dict[int, dict[str, StandingsOdds]]:
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
            school=school, p1=r[2], p2=r[3], p3=r[4], p4=r[5],
            p_playoffs=r[6], final_playoffs=r[6], clinched=r[7], eliminated=r[8],
        )
    return by_region


def _clinched_school(region_odds: dict[str, StandingsOdds], seed: int) -> str | None:
    """Return the school that has clinched *seed* in *region_odds*, or None."""
    attr = f"p{seed}"
    return next(
        (s for s, o in region_odds.items() if getattr(o, attr) >= _CLINCHED_THRESHOLD),
        None,
    )


def _build_entries_from_odds(
    by_region: dict[int, dict[str, StandingsOdds]],
    slots: list[FormatSlot],
) -> list[TeamBracketEntry]:
    """Build TeamBracketEntry list using slot IDs as bracket keys.

    Each slot is treated as a certainty (p{seed}=1.0) so advancement odds
    reflect the structural position, independent of which team fills it.
    """
    entries: list[TeamBracketEntry] = []
    for region_num, region_odds in sorted(by_region.items()):
        # One StandingsOdds per slot; only the matching seed field is 1.0.
        slot_odds: dict[str, StandingsOdds] = {
            f"R{region_num}S{seed}": StandingsOdds(
                school=f"R{region_num}S{seed}",
                p1=1.0 if seed == 1 else 0.0,
                p2=1.0 if seed == 2 else 0.0,
                p3=1.0 if seed == 3 else 0.0,
                p4=1.0 if seed == 4 else 0.0,
                p_playoffs=1.0, final_playoffs=1.0,
                clinched=True, eliminated=False,
            )
            for seed in (1, 2, 3, 4)
        }
        bracket_odds = compute_bracket_advancement_odds(region_num, slot_odds, slots)
        for seed in (1, 2, 3, 4):
            slot_id = f"R{region_num}S{seed}"
            bo = bracket_odds.get(slot_id)
            if bo is None:
                continue
            entries.append(TeamBracketEntry(
                region=region_num,
                seed=seed,
                school=_clinched_school(region_odds, seed),
                second_round=bo.second_round,
                quarterfinals=bo.quarterfinals,
                semifinals=bo.semifinals,
                finals=bo.finals,
                champion=bo.champion,
            ))
    return entries


@router.get("/bracket", responses=_404)
async def get_bracket(
    season: SeasonQ,
    class_: Annotated[int, Query(alias="class")],
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

    entries = _build_entries_from_odds(by_region, slots)
    return BracketResponse(season=season, class_=class_, teams=entries)


@router.post("/bracket/simulate", responses=_404)
async def simulate_bracket(
    body: SimulateBracketRequest,
    season: SeasonQ,
    class_: Annotated[int, Query(alias="class")],
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

    # Build bracket_teams using slot IDs as school-name keys
    bracket_teams: list[BracketTeam] = [
        BracketTeam(bracket_id=0, school=f"R{region}S{seed}", season=season, seed=seed, region=region)
        for region in sorted(by_region)
        for seed in (1, 2, 3, 4)
    ]

    # new_results use the same slot ID format — now bracket_teams has matching keys
    new_results = [
        AppliedGameResult(
            team_a=f"R{r.home_region}S{r.home_seed}",
            team_b=f"R{r.away_region}S{r.away_seed}",
            score_a=1 if r.home_wins else 0,
            score_b=0 if r.home_wins else 1,
        )
        for r in body.results
    ]

    num_rounds = 5 if class_ <= 4 else 4
    updated_odds = apply_bracket_game_results(bracket_teams, num_rounds, [], new_results)

    entries: list[TeamBracketEntry] = []
    for region in sorted(by_region):
        region_odds = by_region[region]
        for seed in (1, 2, 3, 4):
            slot_id = f"R{region}S{seed}"
            bo = updated_odds.get(slot_id)
            if bo is None:
                continue
            entries.append(TeamBracketEntry(
                region=region,
                seed=seed,
                school=_clinched_school(region_odds, seed),
                second_round=bo.second_round,
                quarterfinals=bo.quarterfinals,
                semifinals=bo.semifinals,
                finals=bo.finals,
                champion=bo.champion,
            ))

    return BracketResponse(season=season, class_=class_, teams=entries)
