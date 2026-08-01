"""Unit tests for the team-logo read endpoints in backend.api.routers.meta.

Mocks get_conn/require_school_exists rather than hitting a real DB, same
FakeConn pattern as the other router test files in this suite.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from backend.api.routers import meta


class FakeConn:
    """Records every `execute(sql, params)` call. Supports `.fetchone()` and
    `async for r in (await conn.execute(...))` via `fetchall_rows`."""

    def __init__(self, fetchone_result: tuple | None = None):
        """Start with the given queued fetchone() result and no recorded calls."""
        self.calls: list[tuple[Any, tuple]] = []
        self.fetchone_result = fetchone_result
        self.fetchall_rows: list[tuple] = []

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return the queued fetchone_result."""
        return self.fetchone_result

    def __aiter__(self):
        """Start iterating over the queued fetchall_rows."""
        self._iter = iter(self.fetchall_rows)
        return self

    async def __anext__(self):
        """Yield the next queued row, or stop async iteration once exhausted."""
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _fake_get_conn(conn: FakeConn):
    """Build a `get_conn`-shaped async context manager that always yields *conn*."""

    @asynccontextmanager
    async def _get_conn():
        """Yield the fixed fake connection."""
        yield conn

    return _get_conn


def _logo_row(
    id_=1,
    school="Taylorsville",
    logo_type="primary",
    image_url="logos/primary/Taylorsville_1",
    year_start=None,
    year_end=None,
    is_primary=True,
    has_keyline=False,
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
        None,
        None,
        datetime(2026, 1, 1),
        datetime(2026, 1, 1),
    )


class TestListTeamLogos:
    """GET /teams/{team}/logos."""

    def test_scopes_to_school(self):
        """The query is scoped to the requested school."""
        conn = FakeConn()
        conn.fetchall_rows = [_logo_row()]
        with patch.object(meta, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(meta.list_team_logos("Taylorsville"))
        assert len(result) == 1
        select_sql, params = conn.calls[0]
        assert "school = %s" in select_sql.as_string(None)
        assert params[0] == "Taylorsville"

    def test_logo_type_filter_appends_condition(self):
        """Passing logo_type appends a matching condition to the WHERE clause."""
        conn = FakeConn()
        conn.fetchall_rows = []
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            asyncio.run(meta.list_team_logos("Taylorsville", logo_type="secondary"))
        select_sql, params = conn.calls[0]
        assert "logo_type = %s" in select_sql.as_string(None)
        assert "secondary" in params

    def test_year_filter_uses_simplified_bounds_check_not_logo_covers_season(self):
        """The year filter uses the simplified outer-bound check, not logo_covers_season()."""
        conn = FakeConn()
        conn.fetchall_rows = []
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            asyncio.run(meta.list_team_logos("Taylorsville", year=2019))
        select_sql, _params = conn.calls[0]
        sql_text = select_sql.as_string(None)
        assert "logo_covers_season" not in sql_text
        assert "year_start" in sql_text and "year_end" in sql_text

    def test_empty_result_with_no_filters_checks_school_exists(self):
        """An empty result with no filters applied triggers a school-existence check (for the 404 case)."""
        conn = FakeConn()
        conn.fetchall_rows = []
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock) as mock_require,
        ):
            asyncio.run(meta.list_team_logos("Nonexistent School"))
        mock_require.assert_awaited_once()


class TestResolveTeamLogo:
    """GET /teams/{team}/logos/resolved."""

    def test_query_uses_nulls_last_for_year_start_desc(self):
        """Regression test for the nullable year_start NULLS FIRST-by-default bug:
        without an explicit NULLS LAST, Postgres would put the unbounded 'current'
        row ahead of more specific historical matches."""
        conn = FakeConn(fetchone_result=None)
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            asyncio.run(meta.resolve_team_logo("Taylorsville", season=2019))
        select_sql, _params = conn.calls[0]
        assert "ORDER BY is_primary DESC, year_start DESC NULLS LAST" in select_sql.as_string(None)

    def test_defaults_to_primary_logo_type(self):
        """Omitting logo_type defaults to 'primary'."""
        conn = FakeConn(fetchone_result=None)
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            asyncio.run(meta.resolve_team_logo("Taylorsville", season=2019))
        _select_sql, params = conn.calls[0]
        assert params == ("Taylorsville", "primary", 2019)

    def test_no_covering_row_returns_none(self):
        """No row covering the season returns None rather than raising."""
        conn = FakeConn(fetchone_result=None)
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            result = asyncio.run(meta.resolve_team_logo("Taylorsville", season=2019))
        assert result is None

    def test_covering_row_returns_model(self):
        """A row covering the season is mapped to a TeamLogoModel."""
        conn = FakeConn(fetchone_result=_logo_row())
        with (
            patch.object(meta, "get_conn", _fake_get_conn(conn)),
            patch.object(meta, "require_school_exists", new_callable=AsyncMock),
        ):
            result = asyncio.run(meta.resolve_team_logo("Taylorsville", season=2019))
        assert result is not None
        assert result.school == "Taylorsville"
