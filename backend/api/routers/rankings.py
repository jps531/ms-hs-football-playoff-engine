"""Cross-region rankings for a given class (or statewide), sorted by any single odds metric or by
Elo/RPI rating."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from psycopg.sql import SQL, Composed, Identifier

from backend.api.db import get_conn
from backend.api.models.responses import RankingsResponse, StatewideRankingsResponse
from backend.helpers.api_helpers import build_rank_entry, today

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

_RANK_COLUMNS = """
    rs.school, rs.class, rs.region,
    rs.wins, rs.losses, rs.ties, rs.region_wins, rs.region_losses, rs.region_ties,
    rs.as_of_date,
    rs.odds_1st, rs.odds_2nd, rs.odds_3rd, rs.odds_4th, rs.odds_playoffs,
    rs.odds_1st_weighted, rs.odds_2nd_weighted, rs.odds_3rd_weighted, rs.odds_4th_weighted, rs.odds_playoffs_weighted,
    rs.odds_second_round, rs.odds_quarterfinals, rs.odds_semifinals, rs.odds_finals, rs.odds_champion,
    rs.odds_second_round_weighted, rs.odds_quarterfinals_weighted, rs.odds_semifinals_weighted,
    rs.odds_finals_weighted, rs.odds_champion_weighted,
    rs.odds_first_round_home, rs.odds_second_round_home, rs.odds_quarterfinals_home, rs.odds_semifinals_home,
    rs.odds_first_round_home_weighted, rs.odds_second_round_home_weighted,
    rs.odds_quarterfinals_home_weighted, rs.odds_semifinals_home_weighted,
    tr.elo, tr.rpi
"""

_RANK_FROM_JOIN = """
    FROM region_standings rs
    LEFT JOIN team_ratings tr ON tr.school = rs.school AND tr.season = rs.season AND tr.as_of_date = rs.as_of_date
"""


async def _resolve_snapshot_dates(
    conn, season: int, as_of_date: date, clazz: int | None = None
) -> tuple[date | None, date | None]:
    """Return (current, previous) region_standings snapshot dates for *season* (optionally scoped to
    *clazz*) on or before *as_of_date*.

    ``current`` is the most recent snapshot on or before *as_of_date* — None if no snapshot exists yet.
    ``previous`` is the snapshot immediately before ``current`` — None on a class's/state's first-ever
    snapshot. team_ratings shares the same as_of_date per pipeline run (see its table comment), so this
    single date pair is valid for both region_standings and team_ratings columns.
    """
    conditions = "season = %s"
    params: list[Any] = [season]
    if clazz is not None:
        conditions += " AND class = %s"
        params.append(clazz)

    current_row = await (
        await conn.execute(
            f"SELECT MAX(as_of_date) FROM region_standings WHERE {conditions} AND as_of_date <= %s",
            (*params, as_of_date),
        )
    ).fetchone()
    current = current_row[0] if current_row else None
    if current is None:
        return None, None

    prev_row = await (
        await conn.execute(
            f"SELECT MAX(as_of_date) FROM region_standings WHERE {conditions} AND as_of_date < %s",
            (*params, current),
        )
    ).fetchone()
    return current, (prev_row[0] if prev_row else None)


def _ranked_teams_query(sort_col: str, clazz_filter: bool, region_filter: bool, has_prev: bool) -> Composed:
    """Build the ranked-teams query: current snapshot ranked by *sort_col*, optionally joined to the
    previous snapshot's rank for the same schools. *clazz_filter*/*region_filter* add the corresponding
    ``AND`` conditions; callers pass matching params in the same order the placeholders appear.
    """
    snap_where = "rs.season = %s" + (" AND rs.class = %s" if clazz_filter else "") + " AND rs.as_of_date = %s"
    col = Identifier(sort_col)

    prev_cte = ""
    rank_prev_select = "NULL::bigint AS rank_prev"
    prev_join = ""
    if has_prev:
        prev_cte = f"""
            , prev_snap AS (
                SELECT {_RANK_COLUMNS} {_RANK_FROM_JOIN}
                WHERE {snap_where}
            ),
            prev_ranked AS (
                SELECT school, ROW_NUMBER() OVER (ORDER BY {{col}} DESC) AS rank
                FROM prev_snap
            )
        """
        rank_prev_select = "pr.rank AS rank_prev"
        prev_join = "LEFT JOIN prev_ranked pr ON pr.school = cr.school"

    region_clause = " AND cr.region = %s" if region_filter else ""

    query = f"""
        WITH current_snap AS (
            SELECT {_RANK_COLUMNS} {_RANK_FROM_JOIN}
            WHERE {snap_where}
        ),
        current_ranked AS (
            SELECT *, ROW_NUMBER() OVER (ORDER BY {{col}} DESC) AS rank
            FROM current_snap
        )
        {prev_cte}
        SELECT cr.*, {rank_prev_select}
        FROM current_ranked cr
        {prev_join}
        WHERE cr.{{col}} > %s{region_clause}
        ORDER BY cr.rank
        LIMIT %s
    """
    return SQL(query).format(col=col)


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
        current, previous = await _resolve_snapshot_dates(conn, season, as_of_date)
        if current is None:
            return StatewideRankingsResponse(season=season, teams=[])

        has_prev = previous is not None
        query = _ranked_teams_query(sort_col, clazz_filter=False, region_filter=False, has_prev=has_prev)
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
        current, previous = await _resolve_snapshot_dates(conn, season, as_of_date, clazz=clazz)
        if current is None:
            return RankingsResponse(season=season, class_=clazz, sort_by=sort_col, teams=[])

        has_prev = previous is not None
        query = _ranked_teams_query(sort_col, clazz_filter=True, region_filter=region is not None, has_prev=has_prev)
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
