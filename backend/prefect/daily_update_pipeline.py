"""The morning update: pull the scores, then recalculate everything from them, all or nothing.

Pulling every school's AHSFHS page takes anywhere from a few minutes to about
an hour, so the recalculation starts when the pull finishes rather than at a
fixed time. Both run in one database transaction
(``database_helpers.shared_transaction``): the site keeps serving the last
numbers until the whole update is done, then switches to the new ones at
once. If any part fails, none of it is kept, so the site never shows new
scores with old odds, or half the regions updated. The share images are
drawn after the commit, from what the site then serves.
"""

from prefect import flow, get_run_logger

from backend.helpers.database_helpers import shared_transaction
from backend.helpers.run_lock import holds_update_lock
from backend.prefect.ahsfhs_schedule_pipeline import ahsfhs_schedule_data_flow
from backend.prefect.region_scenarios_pipeline import region_scenarios_data_flow
from backend.prefect.share_assets_pipeline import write_share_assets


@flow(name="Daily Update Flow")
@holds_update_lock
def daily_update_flow(season: int | None = None) -> None:
    """Run the AHSFHS schedule pull, then the region scenarios update, as one transaction."""
    with shared_transaction():
        ahsfhs_schedule_data_flow(season)
        region_scenarios_data_flow(season, share_assets=False)
    # Link previews, from the committed numbers. A failure here shouldn't fail the update.
    try:
        write_share_assets(season)
    except Exception:
        get_run_logger().exception("Share assets failed; the daily update itself completed")
