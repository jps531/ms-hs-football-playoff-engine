from __future__ import annotations

from prefect import flow, get_run_logger


# -------------------------
# Prefect tasks & flow
# -------------------------


@flow(name="Template Data Flow")
def template_data_flow(season: int = 2025) -> int:
    """
    Template Data Flow
    """
    logger = get_run_logger()
    logger.info("Running template data flow for season %d", season)
    return 0