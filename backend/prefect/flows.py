"""Prefect deployment entry point. Registers all data pipeline flows for deployment."""

import asyncio

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from backend.prefect.ahsfhs_schedule_pipeline import ahsfhs_schedule_data_flow
from backend.prefect.misshsaa_school_pipeline import misshsaa_school_data_flow
from backend.prefect.nces_school_pipeline import nces_school_data_flow
from backend.prefect.playoff_pipeline import playoff_bracket_update
from backend.prefect.region_scenarios_pipeline import backfill_historical_snapshots, region_scenarios_data_flow
from backend.prefect.regions_data_pipeline import regions_data_flow

_SCHEDULE_TIMEZONE = "America/Chicago"


async def main():
    """Run the Data Pipeline flows."""
    await serve(
        await regions_data_flow.to_deployment("regions-data-pipeline"),
        await nces_school_data_flow.to_deployment("nces-school-pipeline"),
        await misshsaa_school_data_flow.to_deployment("misshsaa-school-pipeline"),
        await ahsfhs_schedule_data_flow.to_deployment(
            "ahsfhs-schedule-data-pipeline",
            schedule=CronSchedule(cron="0 9 * * *", timezone=_SCHEDULE_TIMEZONE),
        ),
        await region_scenarios_data_flow.to_deployment(
            "region-scenarios-data-pipeline",
            schedule=CronSchedule(cron="15 9 * * *", timezone=_SCHEDULE_TIMEZONE),
        ),
        await backfill_historical_snapshots.to_deployment("backfill-historical-snapshots"),
        await playoff_bracket_update.to_deployment("playoff-bracket-update"),
    )


if __name__ == "__main__":
    asyncio.run(main())
