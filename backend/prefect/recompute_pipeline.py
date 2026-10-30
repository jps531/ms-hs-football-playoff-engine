"""Recompute after corrections: work approved score and date corrections into the numbers.

Approving a score or date report records, per season, the earliest date it changes and when it
was approved (``recompute_requests``, written by ``submission_helpers.queue_recompute``). This
flow runs every few minutes and acts once no correction has been approved for ``QUIET``, so a
moderator working through several reports causes one recompute, not one each:

1. the past snapshots from that date on (``backfill_historical_snapshots`` with ``from_date``);
2. for the current season, today's numbers and share images (``region_scenarios_data_flow``).

A correction approved while it runs stops the backfill between dates; the request stays, and
the next run after a quiet spell starts over from the earliest date. It shares the update lock
(``run_lock``) with the daily update and the other heavy flows, and skips its turn while one
of them runs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from prefect import flow, get_run_logger

from backend.helpers.database_helpers import get_database_connection
from backend.helpers.run_lock import exclusive_run
from backend.prefect.failure_alerts import alert_on_failure
from backend.prefect.region_scenarios_pipeline import backfill_historical_snapshots, region_scenarios_data_flow

# How long after the last approval the recompute waits, so a batch of approvals runs once.
QUIET = timedelta(minutes=10)

_READY_SQL = """
    SELECT season, from_date, requested_at
    FROM recompute_requests
    WHERE requested_at <= NOW() - %s
    ORDER BY season
"""
# Done with a request only if no correction came in since it was read.
_DONE_SQL = "DELETE FROM recompute_requests WHERE season = %s AND requested_at = %s"


def ready_requests() -> list[tuple[int, date, datetime]]:
    """The seasons whose last approved correction is at least ``QUIET`` old: (season, from_date, requested_at)."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_READY_SQL, (QUIET,))
        return cur.fetchall()


def finish_request(season: int, requested_at: datetime) -> bool:
    """Delete the season's request if nothing was approved since *requested_at*; whether it was."""
    with get_database_connection() as conn, conn.cursor() as cur:
        cur.execute(_DONE_SQL, (season, requested_at))
        done = cur.rowcount == 1
        conn.commit()
    return done


@flow(
    name="Recompute After Corrections",
    on_failure=[
        alert_on_failure(
            "recompute after corrections",
            "The approved corrections stay queued and the next run (every 5 minutes) tries again. Until one "
            "succeeds, some or all of the standings, odds and scenarios may not include them yet.",
        )
    ],
)
def recompute_after_corrections() -> list[str]:
    """Recompute each season with approved corrections once they've stopped coming in for a while.

    Returns a line per season saying what happened (empty when nothing was waiting).
    """
    logger = get_run_logger()
    waiting = ready_requests()
    if not waiting:
        return []
    with exclusive_run(wait=False) as held:
        if not held:
            logger.info("Another update is running; the recompute waits for the next run")
            return ["skipped: another update is running"]
        outcome = []
        for season, from_date, requested_at in waiting:
            logger.info("Recomputing %d from %s (corrections approved up to %s)", season, from_date, requested_at)
            if not backfill_historical_snapshots(season, from_date=from_date, superseded_after=requested_at):
                outcome.append(f"{season}: stopped for a newer correction; starts over once they stop")
                continue
            if season == date.today().year:
                region_scenarios_data_flow(season)
            if finish_request(season, requested_at):
                outcome.append(f"{season}: recomputed from {from_date}")
            else:
                outcome.append(f"{season}: recomputed from {from_date}; a newer correction runs next")
        for line in outcome:
            logger.info(line)
        return outcome
