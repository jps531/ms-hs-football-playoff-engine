"""Minimal Prefect flow template. Copy this file to create a new pipeline."""

from datetime import date

from prefect import flow, get_run_logger

# -------------------------
# Prefect tasks & flow
# -------------------------


@flow(name="Template Data Flow")
def template_data_flow(season: int | None = None) -> int:
    """
    Template Data Flow
    """
    if season is None:
        season = date.today().year
    logger = get_run_logger()
    logger.info("Running template data flow for season %d", season)
    return 0
