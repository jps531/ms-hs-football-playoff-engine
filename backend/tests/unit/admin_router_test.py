"""Unit tests for the color_variants recompute wiring in backend.api.routers.admin.

Mocks get_conn/require_school_exists/recompute_color_variants rather than
hitting a real DB — this repo has no live-Postgres test infrastructure (see
backend/tests/unit/color_variants_test.py's FakeConn pattern, used the same
way here at the router level).
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from backend.api.models.requests import BulkRecomputeColorsRequest, SetSchoolOverrideRequest
from backend.api.routers import admin


class FakeConn:
    """Records every `execute(sql, params)` call. Supports `.fetchone()` and
    `async for r in (await conn.execute(...))` via `fetchall_rows`."""

    def __init__(self):
        """Start with no recorded calls, no queued fetchone result, and no rows to iterate."""
        self.calls: list[tuple[str, tuple]] = []
        self.fetchone_result: tuple | None = None
        self.fetchall_rows: list[tuple] = []

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return the queued `fetchone_result`."""
        return self.fetchone_result

    def __aiter__(self):
        """Start iterating over the queued `fetchall_rows`."""
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


CLAMP_OK_VARIANTS = {
    "primary": {
        "raw": "#2A3EAD",
        "light": {"text": "#2A3EAD", "ui": "#2A3EAD", "clamp_failed": False},
        "dark": {"text": "#6586FB", "ui": "#4A67D9", "clamp_failed": False},
    },
    "secondary": [],
    "computed_at": "2026-01-01T00:00:00+00:00",
    "algorithm_version": 1,
}

CLAMP_FAILED_VARIANTS = {
    "primary": {
        "raw": "#808080",
        "light": {"text": "#767676", "ui": "#808080", "clamp_failed": False},
        "dark": {"text": "#FFFFFF", "ui": "#FFFFFF", "clamp_failed": True},
    },
    "secondary": [],
    "computed_at": "2026-01-01T00:00:00+00:00",
    "algorithm_version": 1,
}


class TestSetSchoolOverrideRecomputeTrigger:
    """PUT /schools/{school}/overrides triggers recompute only for the two *_hex fields."""

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_hex_field_triggers_recompute(self, mock_require_exists, mock_recompute):
        """Setting primary_color_hex triggers a recompute for the school."""
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = SetSchoolOverrideRequest(field="primary_color_hex", value="#FF0000")
            asyncio.run(admin.set_school_override("Taylorsville", body))
        mock_recompute.assert_awaited_once_with(conn, "Taylorsville")

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_other_field_does_not_trigger_recompute(self, mock_require_exists, mock_recompute):
        """Setting a non-color field does not trigger a recompute."""
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = SetSchoolOverrideRequest(field="mascot", value="Bulldogs")
            asyncio.run(admin.set_school_override("Taylorsville", body))
        mock_recompute.assert_not_awaited()

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_secondary_color_hex_triggers_recompute(self, mock_require_exists, mock_recompute):
        """Setting secondary_color_hex also triggers a recompute for the school."""
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = SetSchoolOverrideRequest(field="secondary_color_hex", value="#FFFFFF")
            asyncio.run(admin.set_school_override("Taylorsville", body))
        mock_recompute.assert_awaited_once_with(conn, "Taylorsville")


class TestClearSchoolOverrideRecomputeTrigger:
    """DELETE /schools/{school}/overrides/{field} triggers recompute only for the two *_hex fields."""

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_hex_field_triggers_recompute(self, mock_require_exists, mock_recompute):
        """Clearing primary_color_hex triggers a recompute for the school."""
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            asyncio.run(admin.clear_school_override("Taylorsville", "primary_color_hex"))
        mock_recompute.assert_awaited_once_with(conn, "Taylorsville")

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_other_field_does_not_trigger_recompute(self, mock_require_exists, mock_recompute):
        """Clearing a non-color field does not trigger a recompute."""
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            asyncio.run(admin.clear_school_override("Taylorsville", "mascot"))
        mock_recompute.assert_not_awaited()


class TestRecomputeSchoolColorsEndpoint:
    """POST /schools/{school}/recompute-colors."""

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_returns_school_and_recomputed_variants(self, mock_require_exists, mock_recompute):
        """The endpoint returns the school name alongside the recomputed variants blob."""
        mock_recompute.return_value = CLAMP_OK_VARIANTS
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(admin.recompute_school_colors("Taylorsville"))
        mock_recompute.assert_awaited_once_with(conn, "Taylorsville")
        assert result.school == "Taylorsville"
        assert result.color_variants == CLAMP_OK_VARIANTS


class TestBulkRecomputeSchoolColorsEndpoint:
    """POST /schools/recompute-colors."""

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    def test_explicit_school_list_skips_the_select(self, mock_recompute):
        """An explicit schools list is recomputed directly, without a `SELECT school FROM schools`."""
        mock_recompute.return_value = CLAMP_OK_VARIANTS
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = BulkRecomputeColorsRequest(schools=["Taylorsville", "Seminary"])
            result = asyncio.run(admin.bulk_recompute_school_colors(body))
        assert conn.calls == []  # no "SELECT school FROM schools" — explicit list was used
        assert mock_recompute.await_count == 2
        assert result.recomputed == 2
        assert result.clamp_failed_schools == []

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    def test_omitted_schools_queries_every_school(self, mock_recompute):
        """Omitting the schools list falls back to `SELECT school FROM schools` for every row."""
        mock_recompute.return_value = CLAMP_OK_VARIANTS
        conn = FakeConn()
        conn.fetchall_rows = [("Alpha",), ("Beta",)]
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = BulkRecomputeColorsRequest()
            result = asyncio.run(admin.bulk_recompute_school_colors(body))
        assert len(conn.calls) == 1
        assert "SELECT school FROM schools" in conn.calls[0][0]
        assert mock_recompute.await_count == 2
        assert result.recomputed == 2

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    def test_clamp_failed_schools_are_collected(self, mock_recompute):
        """A school whose recompute hits clamp_failed is named in clamp_failed_schools."""
        mock_recompute.side_effect = [CLAMP_OK_VARIANTS, CLAMP_FAILED_VARIANTS]
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = BulkRecomputeColorsRequest(schools=["Taylorsville", "SomeGraySchool"])
            result = asyncio.run(admin.bulk_recompute_school_colors(body))
        assert result.recomputed == 2
        assert result.clamp_failed_schools == ["SomeGraySchool"]

    @patch.object(admin, "recompute_color_variants", new_callable=AsyncMock)
    def test_missing_school_result_is_not_treated_as_clamp_failed(self, mock_recompute):
        """recompute_color_variants returns None for a nonexistent school — must not crash the scan."""
        mock_recompute.return_value = None
        conn = FakeConn()
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = BulkRecomputeColorsRequest(schools=["Nonexistent School"])
            result = asyncio.run(admin.bulk_recompute_school_colors(body))
        assert result.recomputed == 1
        assert result.clamp_failed_schools == []


class TestAnyClampFailed:
    """_any_clamp_failed scans every surface across primary + secondary blobs."""

    def test_all_compliant_returns_false(self):
        """A blob with no failed surfaces at all returns False."""
        assert admin._any_clamp_failed(CLAMP_OK_VARIANTS) is False

    def test_any_failed_surface_returns_true(self):
        """A blob with a failed primary surface returns True."""
        assert admin._any_clamp_failed(CLAMP_FAILED_VARIANTS) is True

    def test_failed_secondary_surface_returns_true(self):
        """A failed surface on a secondary color (not just primary) also returns True."""
        variants = {
            "primary": None,
            "secondary": [
                {
                    "raw": "#808080",
                    "light": {"text": "#767676", "ui": "#808080", "clamp_failed": False},
                    "dark": {"text": "#FFFFFF", "ui": "#FFFFFF", "clamp_failed": True},
                }
            ],
        }
        assert admin._any_clamp_failed(variants) is True

    def test_no_primary_no_secondary_returns_false(self):
        """A blob with no primary and no secondaries returns False rather than crashing."""
        assert admin._any_clamp_failed({"primary": None, "secondary": []}) is False
