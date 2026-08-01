"""Unit tests for backend.helpers.logo_helpers."""

import asyncio
from datetime import datetime

from backend.helpers.logo_helpers import LOGO_FIELD_COLS, build_logo_from_row, sync_logo_cache


class FakeConn:
    """Async FakeConn matching the pattern in color_variants_test.py / query_helpers_test.py."""

    def __init__(self):
        """Start with no recorded calls and no queued fetchone result."""
        self.calls: list[tuple[str, tuple]] = []
        self.fetchone_result: tuple | None = None

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return the queued `fetchone_result`."""
        return self.fetchone_result


def _row(
    id_: int = 1,
    school: str = "Taylorsville",
    logo_type: str = "primary",
    image_url: str | None = "logos/primary/Taylorsville_1",
    year_start: int | None = None,
    year_end: int | None = None,
    is_primary: bool = True,
    has_keyline: bool = False,
    notes: str | None = None,
    source_submission_id: int | None = None,
    created_at: datetime = datetime(2026, 1, 1),
    updated_at: datetime = datetime(2026, 1, 1),
) -> tuple:
    """Build a team_logos row tuple in LOGO_FIELD_COLS order."""
    return (
        id_,
        school,
        logo_type,
        image_url,
        year_start,
        year_end,
        is_primary,
        has_keyline,
        notes,
        source_submission_id,
        created_at,
        updated_at,
    )


class TestBuildLogoFromRow:
    """build_logo_from_row."""

    def test_maps_fields_in_order(self):
        """A row's fields map positionally onto TeamLogoModel in LOGO_FIELD_COLS order."""
        model = build_logo_from_row(_row())
        assert model.id == 1
        assert model.school == "Taylorsville"
        assert model.logo_type == "primary"
        assert model.image_url == "logos/primary/Taylorsville_1"
        assert model.is_primary is True
        assert model.has_keyline is False

    def test_nullable_fields_pass_through_as_none(self):
        """Nullable columns (year_start, year_end, notes, source_submission_id) pass through as None."""
        model = build_logo_from_row(_row(year_start=None, year_end=None, notes=None, source_submission_id=None))
        assert model.year_start is None
        assert model.year_end is None
        assert model.notes is None
        assert model.source_submission_id is None

    def test_bounded_years_pass_through(self):
        """A row with both year_start and year_end set carries them through unchanged."""
        model = build_logo_from_row(_row(year_start=2001, year_end=2010))
        assert model.year_start == 2001
        assert model.year_end == 2010


class TestSyncLogoCache:
    """sync_logo_cache."""

    def test_writes_winning_rows_image_url(self):
        """The resolved winning row's image_url is written to the schools cache column."""
        conn = FakeConn()
        conn.fetchone_result = _row(image_url="logos/primary/Taylorsville_1")
        asyncio.run(sync_logo_cache(conn, "Taylorsville", "primary", 2025))

        assert len(conn.calls) == 2
        select_sql, select_params = conn.calls[0]
        assert "team_logos" in select_sql
        assert "logo_covers_season" in select_sql
        assert select_params == ("Taylorsville", "primary", 2025)

        _update_sql, update_params = conn.calls[1]
        assert update_params == ("logos/primary/Taylorsville_1", "Taylorsville")

    def test_no_covering_row_writes_empty_string(self):
        """No team_logos row covering the season writes an empty string to the cache column."""
        conn = FakeConn()
        conn.fetchone_result = None
        asyncio.run(sync_logo_cache(conn, "Taylorsville", "primary", 2025))

        _update_sql, update_params = conn.calls[1]
        assert update_params == ("", "Taylorsville")

    def test_covering_row_with_no_asset_yet_writes_empty_string(self):
        """A covering row whose image_url is still None also writes an empty string."""
        conn = FakeConn()
        conn.fetchone_result = _row(image_url=None)
        asyncio.run(sync_logo_cache(conn, "Taylorsville", "primary", 2025))

        _update_sql, update_params = conn.calls[1]
        assert update_params == ("", "Taylorsville")

    def test_query_orders_by_primary_then_year_start_nulls_last(self):
        """The resolution query orders by is_primary, then year_start DESC NULLS LAST."""
        conn = FakeConn()
        conn.fetchone_result = None
        asyncio.run(sync_logo_cache(conn, "Taylorsville", "secondary", 2019))

        select_sql, _ = conn.calls[0]
        assert "ORDER BY is_primary DESC, year_start DESC NULLS LAST" in select_sql

    def test_scopes_to_the_given_logo_type(self):
        """The query is scoped to the exact (school, logo_type) pair passed in."""
        conn = FakeConn()
        conn.fetchone_result = None
        asyncio.run(sync_logo_cache(conn, "Taylorsville", "tertiary", 2025))

        _select_sql, select_params = conn.calls[0]
        assert select_params == ("Taylorsville", "tertiary", 2025)


def test_logo_field_cols_matches_team_logo_model_field_count():
    """A guard against LOGO_FIELD_COLS drifting out of sync with TeamLogoModel."""
    assert len(LOGO_FIELD_COLS) == 12
