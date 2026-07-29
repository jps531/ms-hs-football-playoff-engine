"""Statewide key-insights feed."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.db import get_conn
from backend.api.models.responses import InsightsResponse
from backend.helpers.api_helpers import load_insight_feed

router = APIRouter(prefix="/api/v1", tags=["insights"])

SeasonQ = Annotated[int, Query(ge=1980, le=2040)]
DateFromQ = Annotated[date | None, Query()]
DateToQ = Annotated[date | None, Query()]
LimitQ = Annotated[int, Query(ge=1, le=200)]
ClazzQ = Annotated[int | None, Query(alias="class", ge=1, le=7)]
RegionQ = Annotated[int | None, Query(ge=1, le=8)]
TeamQ = Annotated[str | None, Query()]


@router.get("/insights")
async def get_insights(
    season: SeasonQ,
    date_from: DateFromQ = None,
    date_to: DateToQ = None,
    limit: LimitQ = 50,
    clazz: ClazzQ = None,
    region: RegionQ = None,
    team: TeamQ = None,
) -> InsightsResponse:
    """Statewide, deduped, newest-first feed of key insights for *season*.

    The same insight persists across consecutive ``region_scenarios``
    snapshots until it resolves; this feed shows each one once, dated to the
    first snapshot in which it appeared. An empty ``insights`` list is a
    normal response for a season with no scenario snapshots yet.

    ``date_to`` supports timeline scrubbing ("state of the feed as of this
    past date" — insights that hadn't appeared yet by then are excluded
    entirely). ``date_from`` supports polling ("what's new since I last
    checked"). Passing both selects insights whose first appearance falls
    within that window.
    """
    async with get_conn() as conn:
        insights = await load_insight_feed(conn, season, date_from, date_to, clazz, region, team, limit)
    return InsightsResponse(insights=insights)
