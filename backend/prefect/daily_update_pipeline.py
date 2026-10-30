"""The morning update: pull the scores, then recalculate everything from them.

Pulling every school's AHSFHS page takes anywhere from a few minutes to about
an hour, so the recalculation starts when the pull finishes rather than at a
fixed time. If the pull fails, nothing is recalculated: the site keeps the
last numbers, with the time they were calculated, rather than recomputing
the same scores and calling them fresh.
"""

from prefect import flow

from backend.helpers.run_lock import holds_update_lock
from backend.prefect.ahsfhs_schedule_pipeline import ahsfhs_schedule_data_flow
from backend.prefect.region_scenarios_pipeline import region_scenarios_data_flow


@flow(name="Daily Update Flow")
@holds_update_lock
def daily_update_flow(season: int | None = None) -> None:
    """Run the AHSFHS schedule pull, then the region scenarios update once it's done."""
    ahsfhs_schedule_data_flow(season)
    region_scenarios_data_flow(season)
