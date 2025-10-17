from __future__ import annotations

import requests
from typing import List
from prefect import flow, task, get_run_logger

from data_classes import BracketGame
from web_helpers import UA, _extract_next_data, fetch_article_text


# -------------------------
# Prefect tasks & flow
# -------------------------


@task(task_run_name="Find Five Round Playoff Bracket for {season} and class {classification}A")
def find_five_round_playoff_bracket(season: int, classification: int, bracket_source_url: str) -> int:
    """
    Return a list of Bracket Game records for the given season and class from AHSFHS.
    """

    logger = get_run_logger()
    logger.info("Searching for Playoff Bracket for %d season and class %dA via %s", season, classification, bracket_source_url)

    records: List[BracketGame] = []\

    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    r = requests.get(bracket_source_url, headers=headers, timeout=25)
    r.raise_for_status()
    next_data = _extract_next_data(r.text)

    logger.info("Fetched next data: %s: ", next_data)

    return 0
    #return records


@task(retries=2, retry_delay_seconds=10, task_run_name="Scrape Playoff Bracket Data for {season} and class {classification}A")
def scrape_task(season: int, classification: int, bracket_source_url: str) -> int:
    """
    Task to scrape playoff bracket data from MaxPreps.
    """
    logger = get_run_logger()
    if (classification < 5):
        bracket = find_five_round_playoff_bracket(season, classification, bracket_source_url)
    else:
        #bracket = find_four_round_playoff_bracket(season, bracket_source_url)
        pass
    # updated_count = insert_rows(game_records)
    # logger.info("Inserted/Updated %d games", updated_count)
    # return updated_count
    return 0


@flow(name="Playoff Bracket Flow")
def playoff_bracket_pipeline(season: int = 2025, classification: int = 1) -> int:
    """
    Flow to scrape and update playoff bracket data from MaxPreps.
    """

    bracket_source_url = ""
    if (season == 2025):
        if (classification == 1):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/l6EQSsvf5kG4ACUcN16pHQ/football-25/2025-football-championships-1a.htm"
        elif (classification == 2):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/kZCo6i2Rm0aYreD4mKU-bg/football-25/2025-football-championships-2a.htm"
        elif (classification == 3):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/r5umHZgKuE6RZXfT9vG1dw/football-25/2025-football-championships-3a.htm"
        elif (classification == 4):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/X1oXjBneDkGWd1-3ngKVHg/football-25/2025-football-championships-4a.htm"
        elif (classification == 5):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/wcaiYBb-XEuK4bMoyhbQ5g/football-25/2025-football-championships-5a.htm"
        elif (classification == 6):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/SjH6IinlpEq0IUJfwqBScw/football-25/2025-football-championships-6a.htm"
        elif (classification == 7):
            bracket_source_url = "https://www.maxpreps.com/tournament/d29BDHbl6UaiAIB71roQdw/O1r6nJCY0EWCmN-qWhorIw/football-25/2025-football-championships-7a.htm"
    else:
        raise ValueError(f"No bracket URL configured for season {season} and class {classification}A") 

    updated_count = scrape_task(season, classification, bracket_source_url)
    return updated_count