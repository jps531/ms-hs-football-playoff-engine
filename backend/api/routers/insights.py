"""Statewide key-insights feed."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.db import get_conn
from backend.api.models.responses import InsightsResponse, TravelInsightsResponse
from backend.helpers.api_helpers import load_insight_feed, load_travel_insights, today

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


@router.get("/insights/travel")
async def get_travel_insights(season: SeasonQ, date_to: DateToQ = None) -> TravelInsightsResponse:
    """Statewide travel highlights, computed live from games + venue data — separate from the
    region-scoped `/insights` feed above (that feed's snapshot/dedup model doesn't fit a
    statewide, always-current computation). Returns 0-2 entries: the single longest road trip
    in the current week, and the school with the farthest cumulative regular-season travel.
    """
    async with get_conn() as conn:
        travel = await load_travel_insights(conn, season, date_to)
    return TravelInsightsResponse(season=season, as_of_date=date_to or today(), insights=travel)
