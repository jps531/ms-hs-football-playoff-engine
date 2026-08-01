"""Unit tests for the team-logo-repointed upload wiring in backend.api.routers.images.

Mocks get_conn/require_school_exists/save_and_upload/sync_logo_cache rather
than hitting a real DB or Cloudinary — same FakeConn pattern as
admin_logo_router_test.py. _resolve_or_create_team_logo_id is left real
since it's the core new logic being verified here.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from backend.api.routers import images

# save_and_upload is mocked in every test that reaches it, so the file object
# itself is never read — a typed placeholder keeps pyright happy without a
# real UploadFile.
_FAKE_FILE = cast(UploadFile, object())


class FakeConn:
    """Records every `execute(sql, params)` call. `fetchone_results` is a queue —
    each `.fetchone()` after `execute()` pops the next entry."""

    def __init__(self, fetchone_results: list[tuple | None] | None = None):
        """Start with a queued list of fetchone() results and no recorded calls."""
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone_results = list(fetchone_results or [])

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Pop and return the next queued fetchone result."""
        return self._fetchone_results.pop(0)


def _fake_get_conn(conn: FakeConn):
    """Build a `get_conn`-shaped async context manager that always yields *conn*."""

    @asynccontextmanager
    async def _get_conn():
        """Yield the fixed fake connection."""
        yield conn

    return _get_conn


class TestResolveOrCreateTeamLogoId:
    """_resolve_or_create_team_logo_id."""

    def test_existing_row_is_returned_without_insert(self):
        """An existing (school, logo_type) row is returned as-is, no INSERT issued."""
        conn = FakeConn(fetchone_results=[(42,)])
        result = asyncio.run(images._resolve_or_create_team_logo_id(conn, "Taylorsville", "primary"))
        assert result == 42
        assert len(conn.calls) == 1  # only the SELECT — no INSERT

    def test_no_existing_row_creates_one(self):
        """No existing row triggers an INSERT and returns the new row's id."""
        conn = FakeConn(fetchone_results=[None, (99,)])
        result = asyncio.run(images._resolve_or_create_team_logo_id(conn, "Taylorsville", "primary"))
        assert result == 99
        assert len(conn.calls) == 2
        insert_sql, insert_params = conn.calls[1]
        assert "INSERT INTO team_logos" in insert_sql
        assert insert_params == ("Taylorsville", "primary")

    def test_select_prefers_primary_and_covering_then_most_recent(self):
        """The SELECT orders by (is_primary AND covers current season) first, then most recent."""
        conn = FakeConn(fetchone_results=[(42,)])
        asyncio.run(images._resolve_or_create_team_logo_id(conn, "Taylorsville", "secondary"))
        select_sql, select_params = conn.calls[0]
        assert "is_primary AND logo_covers_season" in select_sql
        assert "ORDER BY" in select_sql
        assert select_params == ("Taylorsville", "secondary", images.current_season())


class TestUploadSchoolLogo:
    """The legacy /logos/{school}/{logo_type} endpoint now resolves through team_logos
    instead of writing schools.logo_{type} directly."""

    @patch.object(images, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(images, "set_team_logo_image_column", new_callable=AsyncMock)
    @patch.object(images, "save_and_upload", new_callable=AsyncMock)
    @patch.object(images, "require_school_exists", new_callable=AsyncMock)
    def test_uploads_and_syncs_cache_for_existing_row(
        self, mock_require_school, mock_save_and_upload, mock_set_column, mock_sync
    ):
        """An existing team_logos row is uploaded to and the cache is synced afterward."""
        mock_save_and_upload.return_value = "logos/primary/Taylorsville_42"
        conn = FakeConn(fetchone_results=[(42,)])
        with patch.object(images, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(images.upload_school_logo("Taylorsville", "primary", file=_FAKE_FILE))

        assert result.path == "logos/primary/Taylorsville_42"
        mock_set_column.assert_awaited_once_with(conn, 42, "logos/primary/Taylorsville_42")
        mock_sync.assert_awaited_once_with(conn, "Taylorsville", "primary", images.current_season())

    @patch.object(images, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(images, "set_team_logo_image_column", new_callable=AsyncMock)
    @patch.object(images, "save_and_upload", new_callable=AsyncMock)
    @patch.object(images, "require_school_exists", new_callable=AsyncMock)
    def test_creates_a_row_when_none_exists_yet(
        self, mock_require_school, mock_save_and_upload, mock_set_column, mock_sync
    ):
        """No existing row for the school/logo_type creates one before uploading."""
        mock_save_and_upload.return_value = "logos/primary/NewSchool_7"
        conn = FakeConn(fetchone_results=[None, (7,)])
        with patch.object(images, "get_conn", _fake_get_conn(conn)):
            asyncio.run(images.upload_school_logo("NewSchool", "primary", file=_FAKE_FILE))

        mock_set_column.assert_awaited_once_with(conn, 7, "logos/primary/NewSchool_7")


class TestUploadTeamLogoImage:
    """POST /images/team-logos/{team_logo_id}."""

    @patch.object(images, "sync_logo_cache", new_callable=AsyncMock)
    @patch.object(images, "set_team_logo_image_column", new_callable=AsyncMock)
    @patch.object(images, "save_and_upload", new_callable=AsyncMock)
    def test_uploads_and_syncs_cache(self, mock_save_and_upload, mock_set_column, mock_sync):
        """A valid team_logo_id is uploaded to and the cache is synced afterward."""
        mock_save_and_upload.return_value = "logos/secondary/Taylorsville_42"
        conn = FakeConn(fetchone_results=[("Taylorsville", "secondary")])
        with patch.object(images, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(images.upload_team_logo_image(42, file=_FAKE_FILE))

        assert result.path == "logos/secondary/Taylorsville_42"
        mock_set_column.assert_awaited_once_with(conn, 42, "logos/secondary/Taylorsville_42")
        mock_sync.assert_awaited_once_with(conn, "Taylorsville", "secondary", images.current_season())

    def test_missing_team_logo_raises_404(self):
        """An unknown team_logo_id raises HTTP 404."""
        conn = FakeConn(fetchone_results=[None])
        with patch.object(images, "get_conn", _fake_get_conn(conn)):
            coro = images.upload_team_logo_image(999, file=_FAKE_FILE)
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(coro)
        assert exc_info.value.status_code == 404
