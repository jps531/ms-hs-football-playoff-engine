"""How long each step of an update took, for its log and its email ("Pulling scores 12m 03s · …")."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter


def duration(seconds: float) -> str:
    """A duration as a person reads it: "under 1s", "42s", "12m 03s", "1h 02m"."""
    s = int(round(seconds))
    if s < 1:
        return "under 1s"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


class StepTimes:
    """The steps of one run, each with how long it took, in the order they ran."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, float]] = []
        self._start = self._last = perf_counter()

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        """Time the block as step *name* (recorded even if it raises, so a failed run shows where)."""
        start = perf_counter()
        try:
            yield
        finally:
            self._last = perf_counter()
            self.steps.append((name, self._last - start))

    def lap(self, name: str) -> None:
        """Record step *name* as the time since the last step ended (or since this started)."""
        now = perf_counter()
        self.steps.append((name, now - self._last))
        self._last = now

    def line(self) -> str:
        """Every step and its time, then the total since this started."""
        parts = [f"{name} {duration(seconds)}" for name, seconds in self.steps]
        return " · ".join([*parts, f"total {duration(perf_counter() - self._start)}"])
