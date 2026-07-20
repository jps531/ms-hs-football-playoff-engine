"""Cross-region rankings for a given class, sorted by any single odds metric."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from psycopg.sql import SQL, Identifier

from backend.api.db import get_conn
from backend.api.models.responses import RankingsResponse
from backend.helpers.api_helpers import build_rank_entry, today

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
    as_of_date = as_of or today()
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
        teams=[build_rank_entry(row, sort_col) for row in rows],
    )
