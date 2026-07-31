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
TravelLimitQ = Annotated[int, Query(ge=1, le=50)]


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
async def get_travel_insights(
    season: SeasonQ,
    date_from: DateFromQ = None,
    date_to: DateToQ = None,
    limit: TravelLimitQ = 10,
) -> TravelInsightsResponse:
    """Statewide travel highlights, computed live from games + venue data — separate from the
    region-scoped `/insights` feed above (that feed's snapshot/dedup model doesn't fit a
    statewide, always-current computation).

    ``longest_trips`` ranks individual away games by distance; ``longest_cumulative`` ranks
    schools by total away-game mileage, each capped at ``limit``. Without ``date_from``, trips
    default to the current Monday-Sunday week and cumulative defaults to season-to-date;
    passing ``date_from``/``date_to`` scopes both to that explicit range instead (e.g. "longest
    trip in October").
    """
    async with get_conn() as conn:
        trips, cumulative = await load_travel_insights(conn, season, date_from, date_to, limit)
    return TravelInsightsResponse(
        season=season,
        date_from=date_from,
        date_to=date_to or today(),
        longest_trips=trips,
        longest_cumulative=cumulative,
    )
