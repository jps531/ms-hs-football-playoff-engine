from prefect import serve
from regions_data_pipeline import (
    regions_data_flow
)

if __name__ == "__main__":
    """
    Run the Data Pipeline flows.
    """
    # Schedule the Regions Data Pipeline
    regions_data_flow = regions_data_flow.to_deployment(
        "regions-data-pipeline"
    )

    # Serve the flows
    serve(regions_data_flow)
