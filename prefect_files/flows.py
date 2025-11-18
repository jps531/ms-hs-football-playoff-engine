from prefect import serve

from prefect_files.regions_data_pipeline import (
    regions_data_flow
)
from prefect_files.maxpreps_data_pipeline import (
    maxpreps_data_flow
)
from prefect_files.school_info_pipeline import (
    school_info_data_flow
)
from prefect_files.ahsfhs_schedule_pipeline import (
    ahsfhs_schedule_data_flow
)
from prefect_files.playoff_bracket_pipeline import (
    playoff_bracket_pipeline
)
from prefect_files.region_scenarios_pipeline import (
    region_scenarios_data_flow
)

if __name__ == "__main__":
    """
    Run the Data Pipeline flows.
    """
    # Set up the Regions Data Pipeline
    regions_data_flow = regions_data_flow.to_deployment(
        "regions-data-pipeline"
    )
    # Set up the MaxPreps Data Pipeline
    maxpreps_data_flow = maxpreps_data_flow.to_deployment(
        "maxpreps-data-pipeline"
    )
    # Set up the School Info Data Pipeline
    school_info_data_flow = school_info_data_flow.to_deployment(
        "school-info-data-pipeline"
    )
    # Set up the AHSFHS Schedule Data Pipeline
    ahsfhs_schedule_data_flow = ahsfhs_schedule_data_flow.to_deployment(
        "ahsfhs-schedule-data-pipeline"
    )
    # Set up the Playoff Bracket Pipeline
    playoff_bracket_pipeline = playoff_bracket_pipeline.to_deployment(
        "playoff-bracket-pipeline"
    )
    # Set up the Region Scenarios Data Pipeline
    region_scenarios_data_flow = region_scenarios_data_flow.to_deployment(
        "region-scenarios-data-pipeline"
    )

    # Serve the flows
    serve(regions_data_flow, maxpreps_data_flow, school_info_data_flow, ahsfhs_schedule_data_flow, playoff_bracket_pipeline, region_scenarios_data_flow) # type: ignore