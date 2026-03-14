"""Prefect deployment entry point. Registers all data pipeline flows for deployment."""
import asyncio

from prefect import serve

from prefect_files.ahsfhs_schedule_pipeline import ahsfhs_schedule_data_flow
from prefect_files.maxpreps_data_pipeline import maxpreps_data_flow
from prefect_files.playoff_bracket_pipeline import playoff_bracket_pipeline
from prefect_files.region_scenarios_pipeline import region_scenarios_data_flow
from prefect_files.regions_data_pipeline import regions_data_flow
from prefect_files.school_info_pipeline import school_info_data_flow


async def main():
    """Run the Data Pipeline flows."""
    await serve(
        await regions_data_flow.to_deployment("regions-data-pipeline"),
        await maxpreps_data_flow.to_deployment("maxpreps-data-pipeline"),
        await school_info_data_flow.to_deployment("school-info-data-pipeline"),
        await ahsfhs_schedule_data_flow.to_deployment("ahsfhs-schedule-data-pipeline"),
        await playoff_bracket_pipeline.to_deployment("playoff-bracket-pipeline"),
        await region_scenarios_data_flow.to_deployment("region-scenarios-data-pipeline"),
    )


if __name__ == "__main__":
    asyncio.run(main())
