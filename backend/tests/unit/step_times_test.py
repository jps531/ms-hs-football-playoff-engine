"""How long each step of an update took, as its log and email say it."""

from backend.helpers import step_times
from backend.helpers.step_times import StepTimes, duration


def test_durations_read_as_a_person_says_them():
    """Seconds, then minutes and seconds, then hours and minutes."""
    assert [duration(s) for s in (0.2, 42.4, 723, 3725)] == ["under 1s", "42s", "12m 03s", "1h 02m"]


def test_each_step_is_timed_in_the_order_it_ran(monkeypatch):
    """A timed block and a lap each record their own time; the line ends with the total."""
    clock = iter([0.0, 10.0, 25.0, 85.0, 90.0])
    monkeypatch.setattr(step_times, "perf_counter", lambda: next(clock))
    times = StepTimes()  # starts at 0
    with times.step("Pulling scores"):  # 10 to 25
        pass
    times.lap("Working out the regions")  # 25 to 85
    assert times.line() == "Pulling scores 15s · Working out the regions 1m 00s · total 1m 30s"


def test_a_step_that_fails_is_still_timed():
    """The step that raised is in the line, so a failed run's log shows where it stopped."""
    times = StepTimes()
    try:
        with times.step("Checking the playoff games"):
            raise ValueError("bad")
    except ValueError:
        pass
    assert [name for name, _ in times.steps] == ["Checking the playoff games"]
