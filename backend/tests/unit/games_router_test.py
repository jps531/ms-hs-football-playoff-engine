"""Unit tests for pure helpers in backend.api.routers.games."""

from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.routers.games import _require_elo_row


class TestRequireEloRow:
    """_require_elo_row raises HTTP 404 with a consistent message when the Elo lookup found nothing."""

    def test_present_row_passes_through(self):
        """A non-None row is returned unchanged."""
        row = (1500.0, date(2025, 9, 1))
        assert _require_elo_row(row, "Alpha", 2025, None) == row

    def test_none_row_raises_404(self):
        """A None row raises HTTP 404 naming the team and season."""
        with pytest.raises(HTTPException) as exc_info:
            _require_elo_row(None, "Alpha", 2025, None)
        assert exc_info.value.status_code == 404
        assert "Alpha" in exc_info.value.detail
        assert "2025" in exc_info.value.detail

    def test_none_row_with_date_appends_on_or_before_clause(self):
        """When a date filter was supplied, the 404 detail notes it was checked on or before that date."""
        as_of = date(2025, 10, 3)
        with pytest.raises(HTTPException) as exc_info:
            _require_elo_row(None, "Alpha", 2025, as_of)
        assert "on or before 2025-10-03" in exc_info.value.detail

    def test_none_row_without_date_omits_on_or_before_clause(self):
        """No date filter means no 'on or before' clause in the detail message."""
        with pytest.raises(HTTPException) as exc_info:
            _require_elo_row(None, "Alpha", 2025, None)
        assert "on or before" not in exc_info.value.detail
