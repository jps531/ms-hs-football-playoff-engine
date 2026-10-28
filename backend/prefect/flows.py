"""Prefect deployment entry point. Registers all data pipeline flows for deployment."""

import asyncio

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from backend.prefect.ahsfhs_schedule_pipeline import ahsfhs_schedule_data_flow
from backend.prefect.ahsfhs_score_probe_pipeline import ahsfhs_score_probe_flow
from backend.prefect.daily_update_pipeline import daily_update_flow
from backend.prefect.misshsaa_school_pipeline import misshsaa_school_data_flow
from backend.prefect.nces_school_pipeline import nces_school_data_flow
from backend.prefect.playoff_pipeline import playoff_bracket_update
from backend.prefect.region_scenarios_pipeline import (
    backfill_historical_snapshots,
    refresh_scenario_explanations,
    region_scenarios_data_flow,
)
from backend.prefect.regions_data_pipeline import regions_data_flow
from backend.prefect.share_assets_pipeline import share_assets_flow
from backend.prefect.submission_digest_pipeline import submission_digest_flow

_SCHEDULE_TIMEZONE = "America/Chicago"
# The daily update's start (the pages say "each morning at 9:00 Central"; copy_settings_test checks them).
DAILY_UPDATE_HOUR = 9


async def main():
    """Run the Data Pipeline flows."""
    await serve(
        await regions_data_flow.to_deployment("regions-data-pipeline"),
        await nces_school_data_flow.to_deployment("nces-school-pipeline"),
        await misshsaa_school_data_flow.to_deployment("misshsaa-school-pipeline"),
        # The scores are pulled at 9:00, and the recalculation starts as soon as the pull finishes.
        await daily_update_flow.to_deployment(
            "daily-update",
            schedule=CronSchedule(cron=f"0 {DAILY_UPDATE_HOUR} * * *", timezone=_SCHEDULE_TIMEZONE),
        ),
        # Each half of the daily update on its own, for a manual run.
        await ahsfhs_schedule_data_flow.to_deployment("ahsfhs-schedule-data-pipeline"),
        await region_scenarios_data_flow.to_deployment("region-scenarios-data-pipeline"),
        # Every 15 minutes from 6 to 10 AM on Friday and Saturday: how many of the previous
        # night's final scores (Thursday's, then Friday's) AHSFHS shows yet, to learn whether
        # an earlier pull would find them. AHSFHS posted Oct 23's scores in one batch, 7:30-8:15 AM.
        await ahsfhs_score_probe_flow.to_deployment(
            "ahsfhs-score-probe",
            schedules=[
                CronSchedule(cron="*/15 6-9 * * 5,6", timezone=_SCHEDULE_TIMEZONE),
                CronSchedule(cron="0 10 * * 5,6", timezone=_SCHEDULE_TIMEZONE),
            ],
        ),
        await backfill_historical_snapshots.to_deployment("backfill-historical-snapshots"),
        # After a change to how explanations are worded: rewrites only those, far faster than a backfill.
        await refresh_scenario_explanations.to_deployment("refresh-scenario-explanations"),
        await playoff_bracket_update.to_deployment("playoff-bracket-update"),
        # Also runs at the end of the daily region update; this is for a manual redraw.
        await share_assets_flow.to_deployment("share-assets"),
        # Emails the moderators each morning while anything is waiting; an empty queue sends nothing.
        await submission_digest_flow.to_deployment(
            "submission-digest",
            schedule=CronSchedule(cron="0 7 * * *", timezone=_SCHEDULE_TIMEZONE),
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
