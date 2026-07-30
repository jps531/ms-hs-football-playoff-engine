"""Unit tests for backend.helpers.api_helpers.week_window (GET /games/upsets)."""

from datetime import date

from backend.helpers.api_helpers import week_window


class TestWeekWindow:
    """Coverage for the Monday-Sunday bucketing used to default /games/upsets' date range."""

    def test_mid_week_date(self):
        """A Thursday resolves to the Monday-Sunday window containing it."""
        thursday = date(2025, 10, 9)
        assert week_window(thursday) == (date(2025, 10, 6), date(2025, 10, 12))

    def test_monday_boundary(self):
        """A Monday is already the start of its own window."""
        monday = date(2025, 10, 6)
        assert week_window(monday) == (date(2025, 10, 6), date(2025, 10, 12))

    def test_sunday_boundary(self):
        """A Sunday is already the end of its own window."""
        sunday = date(2025, 10, 12)
        assert week_window(sunday) == (date(2025, 10, 6), date(2025, 10, 12))
