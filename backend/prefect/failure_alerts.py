"""Email the owner when a scheduled update fails.

``alert_on_failure`` makes a Prefect ``on_failure`` hook for a flow: it emails ``ALERT_TO`` (else
``DIGEST_TO``, see ``send_alert``) which flow failed, the error, and what the site shows meanwhile.

- Only a top-level run alerts. A flow run inside another (the playoff update inside the daily
  update) fails its parent, whose hook reports it once.
- A flow that already explained its own stop in an email (``ALREADY_EMAILED``) isn't reported
  again.
- Each flow alerts at most once per ``QUIET_HOURS``. The recompute runs every 5 minutes and would
  otherwise send an email every 5 minutes while, say, the database is down. The last alert's time
  is a file's age under the temp directory, so it holds across the worker's flow runs (each its
  own process) and needs no database.

A run killed outright (out of memory, a restart) doesn't run its hooks, so it sends nothing.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

QUIET_HOURS = 6
_STAMPS = Path(tempfile.gettempdir()) / "mshsf-failure-alerts"

_log = logging.getLogger(__name__)


def _recently_alerted(name: str) -> bool:
    """Whether *name* alerted within ``QUIET_HOURS``; if not, mark that it's alerting now."""
    stamp = _STAMPS / name.replace("/", "-").replace(" ", "-")
    try:
        if time.time() - stamp.stat().st_mtime < QUIET_HOURS * 3600:
            return True
    except FileNotFoundError:
        pass
    _STAMPS.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    return False


def alert_on_failure(name: str, meanwhile: str, already_emailed: tuple[type[BaseException], ...] = ()):
    """An ``on_failure`` hook emailing that *name* failed, the error, and *meanwhile* (what the site shows).

    A failure whose exception is one of *already_emailed* sends nothing more.
    """

    def hook(flow, flow_run, state) -> None:
        """Email the failure, unless it's a subflow's, already explained, or alerted recently."""
        from backend.prefect.submission_digest_pipeline import send_alert

        if flow_run.parent_task_run_id is not None:
            return
        error = state.result(raise_on_failure=False)
        if isinstance(error, already_emailed):
            return
        if _recently_alerted(name):
            _log.warning("%s failed again; already alerted in the last %d hours", name, QUIET_HOURS)
            return
        detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else state.message
        send_alert(
            f"{name} failed",
            f"The {name} run '{flow_run.name}' failed:\n\n    {detail}\n\n{meanwhile}\n\n"
            f"The run's logs in Prefect have the details. Further failures of the {name} in the next "
            f"{QUIET_HOURS} hours won't be emailed.\n",
        )

    return hook
