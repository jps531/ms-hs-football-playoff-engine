"""Unit tests for the team_logos CRUD wiring in backend.api.routers.admin.

Mocks get_conn/require_school_exists/require_team_logo_exists/sync_logo_cache
rather than hitting a real DB — same FakeConn pattern as admin_router_test.py.
validate_submission_for_logo_asset is left real (pure, no DB) so its wiring
is exercised with genuine (type, status) tuples.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.api.models.requests import CreateTeamLogoRequest, PatchTeamLogoRequest
from backend.api.routers import admin


class FakeConn:
    """Records every `execute(sql, params)` call. `fetchone_results` is a queue —
    each `.fetchone()` after `execute()` pops the next entry. `fetchall_rows`
    backs `async for r in (await conn.execute(...))`."""

    def __init__(self, fetchone_results: list[tuple | None] | None = None):
        """Start with a queued list of fetchone() results and no recorded calls."""
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone_results = list(fetchone_results or [])
        self.fetchall_rows: list[tuple] = []

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Pop and return the next queued fetchone result."""
        return self._fetchone_results.pop(0)

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
    id_=42,
    school="Taylorsville",
    logo_type="primary",
    image_url=None,
    year_start=None,
    year_end=None,
    is_primary=True,
    has_keyline=False,
    notes=None,
    source_submission_id=None,
) -> tuple:
    """Build a team_logos row in LOGO_FIELD_COLS order."""
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
        datetime(2026, 1, 1),
        datetime(2026, 1, 1),
    )


class TestCreateTeamLogo:
    """POST /admin/logos."""

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_basic_creation_returns_model_and_syncs_cache(self, mock_require_school, mock_sync):
        """A minimal create request inserts a row and syncs the cache for the new (school, logo_type)."""
        conn = FakeConn(fetchone_results=[(42,), _logo_row()])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = CreateTeamLogoRequest(school="Taylorsville", logo_type="primary")
            result = asyncio.run(admin.create_team_logo(body))

        assert result.id == 42
        assert result.school == "Taylorsville"
        mock_sync.assert_awaited_once_with(conn, "Taylorsville", "primary", admin.current_season())
        insert_sql, _ = conn.calls[0]
        assert "INSERT INTO team_logos" in insert_sql

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_is_primary_unsets_existing_primary_first(self, mock_require_school, mock_sync):
        """is_primary=True unsets any existing primary for the same (school, logo_type) before inserting."""
        conn = FakeConn(fetchone_results=[(42,), _logo_row()])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = CreateTeamLogoRequest(school="Taylorsville", logo_type="primary", is_primary=True)
            asyncio.run(admin.create_team_logo(body))

        unset_sql, unset_params = conn.calls[0]
        assert "UPDATE team_logos SET is_primary = FALSE" in unset_sql
        assert unset_params == ("Taylorsville", "primary")

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_valid_from_submission_id_links_and_approves(self, mock_require_school, mock_sync):
        """A valid from_submission_id links the row and flips the submission's status to approved."""
        sub_row = ("logo", "accepted_pending_asset")
        conn = FakeConn(fetchone_results=[sub_row, (42,), _logo_row(source_submission_id=7)])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = CreateTeamLogoRequest(school="Taylorsville", logo_type="primary", from_submission_id=7)
            result = asyncio.run(admin.create_team_logo(body))

        assert result.source_submission_id == 7
        approve_sql, approve_params = conn.calls[-2]  # INSERT, [UPDATE submissions], SELECT detail
        assert "UPDATE submissions SET status = 'approved'" in approve_sql
        assert approve_params == (7,)

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_from_submission_id_wrong_status_raises_422(self, mock_require_school, mock_sync):
        """A from_submission_id whose submission isn't accepted_pending_asset raises HTTP 422."""
        sub_row = ("logo", "pending")
        conn = FakeConn(fetchone_results=[sub_row])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = CreateTeamLogoRequest(school="Taylorsville", logo_type="primary", from_submission_id=7)
            coro = admin.create_team_logo(body)
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(coro)
        assert exc_info.value.status_code == 422

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_school_exists", new_callable=AsyncMock)
    def test_from_submission_id_missing_raises_404(self, mock_require_school, mock_sync):
        """A from_submission_id that doesn't exist raises HTTP 404."""
        conn = FakeConn(fetchone_results=[None])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = CreateTeamLogoRequest(school="Taylorsville", logo_type="primary", from_submission_id=999)
            coro = admin.create_team_logo(body)
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(coro)
        assert exc_info.value.status_code == 404


class TestPatchTeamLogo:
    """PATCH /admin/logos/{logo_id}."""

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_team_logo_exists", new_callable=AsyncMock)
    def test_basic_update_returns_model_and_syncs_cache(self, mock_require_exists, mock_sync):
        """A partial update writes the changed field and syncs the cache for the row's (school, logo_type)."""
        conn = FakeConn(fetchone_results=[_logo_row(has_keyline=True)])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = PatchTeamLogoRequest(has_keyline=True)
            result = asyncio.run(admin.patch_team_logo(42, body))

        assert result.has_keyline is True
        mock_sync.assert_awaited_once_with(conn, "Taylorsville", "primary", admin.current_season())

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(admin, "require_team_logo_exists", new_callable=AsyncMock)
    def test_is_primary_true_unsets_other_primaries_in_same_school_and_type(self, mock_require_exists, mock_sync):
        """Setting is_primary=True unsets any other primary row for the same (school, logo_type)."""
        conn = FakeConn(fetchone_results=[_logo_row(is_primary=True)])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            body = PatchTeamLogoRequest(is_primary=True)
            asyncio.run(admin.patch_team_logo(42, body))

        unset_sql, unset_params = conn.calls[0]
        assert "UPDATE team_logos SET is_primary = FALSE" in unset_sql
        assert unset_params == (42, 42, 42)

    def test_empty_update_raises_422(self):
        """An update with no fields set raises HTTP 422 before touching the DB."""
        coro = admin.patch_team_logo(42, PatchTeamLogoRequest())
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(coro)
        assert exc_info.value.status_code == 422


class TestDeleteTeamLogo:
    """DELETE /admin/logos/{logo_id}."""

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    def test_deletes_and_syncs_cache(self, mock_sync):
        """A valid id is deleted and the cache is synced for its (school, logo_type)."""
        conn = FakeConn(fetchone_results=[_logo_row()])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            asyncio.run(admin.delete_team_logo(42))

        delete_sql, delete_params = conn.calls[1]
        assert "DELETE FROM team_logos WHERE id = %s" in delete_sql
        assert delete_params == (42,)
        mock_sync.assert_awaited_once_with(conn, "Taylorsville", "primary", admin.current_season())

    @patch.object(admin, "sync_logo_cache", new_callable=AsyncMock)
    def test_missing_logo_raises_404(self, mock_sync):
        """A missing id raises HTTP 404 and never calls sync_logo_cache."""
        conn = FakeConn(fetchone_results=[None])
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            coro = admin.delete_team_logo(999)
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(coro)
        assert exc_info.value.status_code == 404
        mock_sync.assert_not_awaited()


class TestListLogosNeedingRecut:
    """GET /admin/logos/needs-recut."""

    def test_returns_only_matching_rows(self):
        """The query filters to has_keyline = FALSE with a non-null image_url."""
        conn = FakeConn()
        conn.fetchall_rows = [_logo_row(id_=1, has_keyline=False, image_url="logos/primary/A_1")]
        with patch.object(admin, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(admin.list_logos_needing_recut())

        assert len(result) == 1
        select_sql, _ = conn.calls[0]
        assert "has_keyline = FALSE" in select_sql
        assert "image_url IS NOT NULL" in select_sql
