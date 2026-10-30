"""Unit tests for backend.prefect.failure_alerts: one email per failed scheduled update."""

from types import SimpleNamespace

import pytest

import backend.prefect.failure_alerts as fa
import backend.prefect.submission_digest_pipeline as digest


class Stopped(RuntimeError):
    """A failure the flow already emailed about."""


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """The alerts sent, with the throttle's stamps kept in a temp directory."""
    out = []
    monkeypatch.setattr(fa, "_STAMPS", tmp_path)
    monkeypatch.setattr(digest, "send_alert", lambda subject, text: out.append((subject, text)))
    return out


def _fail(hook, error, parent=None):
    """Run *hook* for a failed run named crimson-fox whose exception is *error*."""
    run = SimpleNamespace(name="crimson-fox", parent_task_run_id=parent)
    state = SimpleNamespace(
        result=lambda raise_on_failure: error, message=f"Flow run encountered an exception. {error}"
    )
    hook(SimpleNamespace(name="Daily Update Flow"), run, state)


def test_a_failed_run_is_emailed_with_the_error_and_what_the_site_shows(sent):
    hook = fa.alert_on_failure("daily update", "The site still shows the previous numbers.")
    _fail(hook, ConnectionError("AHSFHS refused the connection"))
    ((subject, text),) = sent
    assert subject == "daily update failed"
    assert "The daily update run 'crimson-fox' failed:" in text
    assert "ConnectionError: AHSFHS refused the connection" in text
    assert "The site still shows the previous numbers." in text


def test_a_subflows_failure_is_left_to_its_parent(sent):
    _fail(fa.alert_on_failure("playoff bracket update", "…"), ValueError("x"), parent="task-run-1")
    assert sent == []


def test_a_failure_the_flow_already_emailed_about_isnt_repeated(sent):
    _fail(fa.alert_on_failure("daily update", "…", already_emailed=(Stopped,)), Stopped("playoff mismatch"))
    assert sent == []


def test_repeated_failures_email_once_per_quiet_period(sent, tmp_path):
    hook = fa.alert_on_failure("recompute after corrections", "…")
    for _ in range(3):
        _fail(hook, OSError("database is down"))
    assert len(sent) == 1
    other = fa.alert_on_failure("daily update", "…")
    _fail(other, OSError("database is down"))
    assert len(sent) == 2  # each flow has its own quiet period
    import os
    import time

    for stamp in tmp_path.iterdir():  # 6 hours later
        os.utime(stamp, (time.time() - fa.QUIET_HOURS * 3600 - 1,) * 2)
    _fail(hook, OSError("database is down"))
    assert len(sent) == 3
