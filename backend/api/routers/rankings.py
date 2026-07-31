"""Cross-region rankings for a given class (or statewide), sorted by any single odds metric or by
Elo/RPI rating."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from backend.api.db import get_conn
from backend.api.models.responses import RankingsResponse, StatewideRankingsResponse
from backend.helpers.api_helpers import build_rank_entry, build_ranked_teams_query, resolve_snapshot_dates, today

router = APIRouter(prefix="/api/v1/rankings", tags=["rankings"])

ClazzPath = Annotated[int, Path(ge=1, le=7)]
SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
DateQ = Annotated[date | None, Query()]
RegionQ = Annotated[int | None, Query(ge=1, le=8)]
LimitQ = Annotated[int, Query(ge=1, le=200)]
MinOddsQ = Annotated[float, Query(ge=0.0, le=1.0)]


class RankSortField(StrEnum):
    """Every column usable as a sort key: odds columns from region_standings, plus elo/rpi from
    team_ratings (joined in alongside the odds columns — see _RANK_COLUMNS)."""

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
    elo = "elo"
    rpi = "rpi"


# Row positions in each ranked query below (0-indexed) — see build_rank_entry / RANKINGS_SORT_COL:
#   0-2:   school, class, region
#   3-8:   wins, losses, ties, region_wins, region_losses, region_ties
#   9:     as_of_date
#   10-14: odds_1st–odds_playoffs
#   15-19: odds_1st_weighted–odds_playoffs_weighted
#   20-24: odds_second_round–odds_champion
#   25-29: odds_second_round_weighted–odds_champion_weighted
#   30-33: odds_first_round_home–odds_semifinals_home
#   34-37: odds_first_round_home_weighted–odds_semifinals_home_weighted
#   38-39: elo, rpi
#   40:    rank (1-indexed position among the full class/state for the chosen sort column)
#   41:    rank_prev (same position as of the previous snapshot; NULL on a team's first-ever snapshot)


@router.get("/statewide")
async def get_statewide_rankings(
    season: SeasonQ,
    date: DateQ = None,
    limit: LimitQ = 25,
) -> StatewideRankingsResponse:
    """Return the top teams statewide, ranked by Elo — the only metric comparable across class sizes
    (playoff-odds columns aren't, since each class runs its own bracket).

    Picks the most recent snapshot on or before *date* (defaults to today). Each entry still carries
    its own ``class_``/``region`` for context.
    """
    as_of_date = date or today()
    sort_col = "elo"

    async with get_conn() as conn:
        current, previous = await resolve_snapshot_dates(conn, season, as_of_date)
        if current is None:
            return StatewideRankingsResponse(season=season, teams=[])

        has_prev = previous is not None
        query = build_ranked_teams_query(sort_col, clazz_filter=False, region_filter=False, has_prev=has_prev)
        params: list[Any] = [season, current]
        if has_prev:
            params += [season, previous]
        params += [0.0, limit]

        rows = [r async for r in await conn.execute(query, params)]

    return StatewideRankingsResponse(season=season, teams=[build_rank_entry(row, sort_col) for row in rows])


@router.get("/{clazz}")
async def get_rankings(
    clazz: ClazzPath,
    sort_by: RankSortField,
    season: SeasonQ,
    date: DateQ = None,
    region: RegionQ = None,
    min_odds: MinOddsQ = 0.0,
    limit: LimitQ = 25,
) -> RankingsResponse:
    """Return teams in *clazz*A ranked by a single metric — any odds column, or ``elo``/``rpi``.

    Picks the most recent snapshot on or before *date* (defaults to today) for each school, then sorts
    by the chosen field. *region* narrows which rows are returned but never changes a team's *rank* —
    rank always reflects position within the full class, matching this endpoint's cross-region intent.
    *min_odds* suppresses near-zero entries (e.g. ``min_odds=0.001`` omits eliminated teams) — it has no
    natural equivalent for ``elo``/``rpi`` and is a no-op there at its default. *limit* controls the
    result count (max 200). Every entry includes ``rank_prev``/``rank_delta`` against the previous
    snapshot (both ``null`` on a class's first-ever snapshot of the season).
    """
    as_of_date = date or today()
    sort_col = sort_by.value  # safe: constrained to a closed enum of column names

    async with get_conn() as conn:
        current, previous = await resolve_snapshot_dates(conn, season, as_of_date, clazz=clazz)
        if current is None:
            return RankingsResponse(season=season, class_=clazz, sort_by=sort_col, teams=[])

        has_prev = previous is not None
        query = build_ranked_teams_query(
            sort_col, clazz_filter=True, region_filter=region is not None, has_prev=has_prev
        )
        params: list[Any] = [season, clazz, current]
        if has_prev:
            params += [season, clazz, previous]
        params += [min_odds]
        if region is not None:
            params.append(region)
        params.append(limit)

        rows = [r async for r in await conn.execute(query, params)]

    return RankingsResponse(
        season=season,
        class_=clazz,
        sort_by=sort_col,
        teams=[build_rank_entry(row, sort_col) for row in rows],
    )
