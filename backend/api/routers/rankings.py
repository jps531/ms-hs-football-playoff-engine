"""Cross-region rankings for a given class, sorted by any single odds metric."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from psycopg.sql import SQL, Identifier

from backend.api.db import get_conn
from backend.api.models.responses import (
    BracketAdvancementOdds,
    HomeGameOdds,
    RankingsResponse,
    RecordModel,
    SeedingOddsModel,
    TeamRankEntry,
)

router = APIRouter(prefix="/api/v1/rankings", tags=["rankings"])

ClazzPath = Annotated[int, Path(ge=1, le=7)]
SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
DateQ = Annotated[date | None, Query()]
RegionQ = Annotated[int | None, Query(ge=1, le=8)]
LimitQ = Annotated[int, Query(ge=1, le=200)]
MinOddsQ = Annotated[float, Query(ge=0.0, le=1.0)]


class OddsField(StrEnum):
    """Every odds column in region_standings, usable as a sort key."""

    odds_1st = "odds_1st"
    odds_2nd = "odds_2nd"
    odds_3rd = "odds_3rd"
    odds_4th = "odds_4th"
    odds_playoffs = "odds_playoffs"
    odds_1st_weighted = "odds_1st_weighted"
    odds_2nd_weighted = "odds_2nd_weighted"
    odds_3rd_weighted = "odds_3rd_weighted"
    odds_4th_weighted = "odds_4th_weighted"
    odds_playoffs_weighted = "odds_playoffs_weighted"
    odds_second_round = "odds_second_round"
    odds_quarterfinals = "odds_quarterfinals"
    odds_semifinals = "odds_semifinals"
    odds_finals = "odds_finals"
    odds_champion = "odds_champion"
    odds_second_round_weighted = "odds_second_round_weighted"
    odds_quarterfinals_weighted = "odds_quarterfinals_weighted"
    odds_semifinals_weighted = "odds_semifinals_weighted"
    odds_finals_weighted = "odds_finals_weighted"
    odds_champion_weighted = "odds_champion_weighted"
    odds_first_round_home = "odds_first_round_home"
    odds_second_round_home = "odds_second_round_home"
    odds_quarterfinals_home = "odds_quarterfinals_home"
    odds_semifinals_home = "odds_semifinals_home"
    odds_first_round_home_weighted = "odds_first_round_home_weighted"
    odds_second_round_home_weighted = "odds_second_round_home_weighted"
    odds_quarterfinals_home_weighted = "odds_quarterfinals_home_weighted"
    odds_semifinals_home_weighted = "odds_semifinals_home_weighted"


# Row positions in the SELECT below (0-indexed):
#   0-2:   school, class, region
#   3-8:   wins, losses, ties, region_wins, region_losses, region_ties
#   9:     as_of_date
#   10-14: odds_1st–odds_playoffs
#   15-19: odds_1st_weighted–odds_playoffs_weighted
#   20-24: odds_second_round–odds_champion
#   25-29: odds_second_round_weighted–odds_champion_weighted
#   30-33: odds_first_round_home–odds_semifinals_home
#   34-37: odds_first_round_home_weighted–odds_semifinals_home_weighted

_SELECT = """
    SELECT DISTINCT ON (school)
        school, class, region,
        wins, losses, ties, region_wins, region_losses, region_ties,
        as_of_date,
        odds_1st, odds_2nd, odds_3rd, odds_4th, odds_playoffs,
        odds_1st_weighted, odds_2nd_weighted, odds_3rd_weighted, odds_4th_weighted, odds_playoffs_weighted,
        odds_second_round, odds_quarterfinals, odds_semifinals, odds_finals, odds_champion,
        odds_second_round_weighted, odds_quarterfinals_weighted, odds_semifinals_weighted,
        odds_finals_weighted, odds_champion_weighted,
        odds_first_round_home, odds_second_round_home, odds_quarterfinals_home, odds_semifinals_home,
        odds_first_round_home_weighted, odds_second_round_home_weighted,
        odds_quarterfinals_home_weighted, odds_semifinals_home_weighted
    FROM region_standings
    WHERE season = %s AND class = %s AND as_of_date <= %s
"""

# Map each enum value to its 0-indexed position in _SELECT output rows.
_COL: dict[str, int] = {
    "odds_1st": 10,
    "odds_2nd": 11,
    "odds_3rd": 12,
    "odds_4th": 13,
    "odds_playoffs": 14,
    "odds_1st_weighted": 15,
    "odds_2nd_weighted": 16,
    "odds_3rd_weighted": 17,
    "odds_4th_weighted": 18,
    "odds_playoffs_weighted": 19,
    "odds_second_round": 20,
    "odds_quarterfinals": 21,
    "odds_semifinals": 22,
    "odds_finals": 23,
    "odds_champion": 24,
    "odds_second_round_weighted": 25,
    "odds_quarterfinals_weighted": 26,
    "odds_semifinals_weighted": 27,
    "odds_finals_weighted": 28,
    "odds_champion_weighted": 29,
    "odds_first_round_home": 30,
    "odds_second_round_home": 31,
    "odds_quarterfinals_home": 32,
    "odds_semifinals_home": 33,
    "odds_first_round_home_weighted": 34,
    "odds_second_round_home_weighted": 35,
    "odds_quarterfinals_home_weighted": 36,
    "odds_semifinals_home_weighted": 37,
}


def _row_to_entry(row: tuple, sort_col: str) -> TeamRankEntry:
    """Build a ``TeamRankEntry`` from a ``region_standings`` result row using the column layout defined in ``_SELECT``."""
    return TeamRankEntry(
        school=row[0],
        class_=row[1],
        region=row[2],
        as_of_date=row[9],
        record=RecordModel(
            wins=row[3],
            losses=row[4],
            ties=row[5],
            region_wins=row[6],
            region_losses=row[7],
            region_ties=row[8],
        ),
        seeding_odds=SeedingOddsModel(
            p1=row[10],
            p2=row[11],
            p3=row[12],
            p4=row[13],
            p_playoffs=row[14],
            p1_weighted=row[15],
            p2_weighted=row[16],
            p3_weighted=row[17],
            p4_weighted=row[18],
            p_playoffs_weighted=row[19],
        ),
        bracket=BracketAdvancementOdds(
            second_round=row[20],
            quarterfinals=row[21],
            semifinals=row[22],
            finals=row[23],
            champion=row[24],
            second_round_weighted=row[25],
            quarterfinals_weighted=row[26],
            semifinals_weighted=row[27],
            finals_weighted=row[28],
            champion_weighted=row[29],
        ),
        home=HomeGameOdds(
            first_round=row[30],
            second_round=row[31],
            quarterfinals=row[32],
            semifinals=row[33],
            first_round_weighted=row[34],
            second_round_weighted=row[35],
            quarterfinals_weighted=row[36],
            semifinals_weighted=row[37],
        ),
        sort_value=row[_COL[sort_col]],
    )


def _today() -> date:
    """Return today's date (injectable seam for tests)."""
    return datetime.now().date()


@router.get("/{clazz}")
async def get_rankings(
    clazz: ClazzPath,
    sort_by: OddsField,
    season: SeasonQ,
    as_of: DateQ = None,
    region: RegionQ = None,
    min_odds: MinOddsQ = 0.0,
    limit: LimitQ = 25,
) -> RankingsResponse:
    """Return teams in *clazz*A ranked by a single odds metric.

    Picks the most recent snapshot on or before *as_of* (defaults to today)
    for each school, then filters and sorts by the chosen field.  Use
    *region* to restrict to one region within the class, *min_odds* to
    suppress near-zero entries (e.g. ``min_odds=0.001`` omits eliminated
    teams), and *limit* to control the result count (max 200).
    """
    as_of_date = as_of or _today()
    sort_col = sort_by.value  # safe: constrained to a closed enum of column names

    base_params: list[Any] = [season, clazz, as_of_date]
    inner = SQL(_SELECT)
    if region is not None:
        inner = SQL(_SELECT + " AND region = %s")
        base_params.append(region)

    col = Identifier(sort_col)
    sql = SQL(
        "SELECT * FROM ({inner} ORDER BY school, as_of_date DESC) latest"
        " WHERE {col} > %s ORDER BY {col} DESC LIMIT %s"
    ).format(inner=inner, col=col)
    params = base_params + [min_odds, limit]

    async with get_conn() as conn:
        rows = [r async for r in await conn.execute(sql, params)]

    return RankingsResponse(
        season=season,
        class_=clazz,
        sort_by=sort_col,
        teams=[_row_to_entry(row, sort_col) for row in rows],
    )
