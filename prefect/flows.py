from prefect import serve
from regions_data_pipeline import (
    regions_data_flow
)
from maxpreps_data_pipeline import (
    maxpreps_data_flow
)
from prefect.school_info_pipeline import (
    school_info_data_flow
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
    # Set up the Colors Data Pipeline
    school_info_data_flow = school_info_data_flow.to_deployment(
        "school-info-data-pipeline"
    )

    # Serve the flows
    serve(regions_data_flow, maxpreps_data_flow, school_info_data_flow)