"""Unit tests for the approve/reject status-transition wiring in backend.api.routers.moderation.

Mocks get_conn/apply_submission rather than hitting a real DB, following the
FakeConn pattern established in admin_router_test.py.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.api.models.requests import ModerationDecisionRequest
from backend.api.routers import moderation


class FakeConn:
    """Records every `execute(sql, params)` call. `fetchone_results` is a queue —
    each `.fetchone()` after `execute()` pops the next entry."""

    def __init__(self, fetchone_results: list[tuple | None]):
        """Start with the given queued list of fetchone() results and no recorded calls."""
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone_results = list(fetchone_results)

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


def _submission_row(
    id_=1, stype="logo", status="pending", school="Taylorsville", payload=None, helmet_design_id=None
) -> tuple:
    """Build a (id, type, status, school, submitted_at, reviewed_at, payload,
    moderator_notes, helmet_design_id) row, matching approve/get_submission's SELECT."""
    return (
        id_,
        stype,
        status,
        school,
        datetime(2026, 1, 1),
        None,
        payload or {},
        None,
        helmet_design_id,
    )


class TestApproveSubmissionStatusTransition:
    """approve_submission sets status via resolve_approval_status(type), not a hardcoded literal."""

    @patch.object(moderation, "apply_submission", new_callable=AsyncMock)
    def test_logo_submission_moves_to_accepted_pending_asset(self, mock_apply):
        """A 'logo' submission's approval sets status to accepted_pending_asset, not approved."""
        fetched = _submission_row(stype="logo", status="pending")
        updated = _submission_row(stype="logo", status="accepted_pending_asset")
        conn = FakeConn([fetched, updated])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(
                moderation.approve_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            )
        assert result.status == "accepted_pending_asset"
        update_sql, update_params = conn.calls[1]
        assert "UPDATE submissions" in update_sql
        assert update_params[0] == "accepted_pending_asset"

    @patch.object(moderation, "apply_submission", new_callable=AsyncMock)
    def test_helmet_submission_moves_straight_to_approved(self, mock_apply):
        """A 'helmet' submission's approval still sets status straight to approved."""
        fetched = _submission_row(stype="helmet", status="pending")
        updated = _submission_row(stype="helmet", status="approved")
        conn = FakeConn([fetched, updated])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(
                moderation.approve_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            )
        assert result.status == "approved"
        _update_sql, update_params = conn.calls[1]
        assert update_params[0] == "approved"

    @patch.object(moderation, "apply_submission", new_callable=AsyncMock)
    def test_colors_submission_moves_straight_to_approved(self, mock_apply):
        """A 'colors' submission's approval still sets status straight to approved."""
        fetched = _submission_row(stype="colors", status="pending")
        updated = _submission_row(stype="colors", status="approved")
        conn = FakeConn([fetched, updated])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(
                moderation.approve_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            )
        assert result.status == "approved"


class TestRejectSubmissionGeneralizedGuard:
    """reject_submission allows rejecting from pending or accepted_pending_asset, not just pending."""

    def test_pending_submission_can_be_rejected(self):
        """A submission still in 'pending' can be rejected."""
        fetched = (1, "logo", "pending")
        updated = _submission_row(stype="logo", status="rejected")
        conn = FakeConn([fetched, updated])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(
                moderation.reject_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            )
        assert result.status == "rejected"

    def test_accepted_pending_asset_submission_can_be_rejected(self):
        """A submission in 'accepted_pending_asset' can still be rejected before an asset is made."""
        fetched = (1, "logo", "accepted_pending_asset")
        updated = _submission_row(stype="logo", status="rejected")
        conn = FakeConn([fetched, updated])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            result = asyncio.run(
                moderation.reject_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            )
        assert result.status == "rejected"

    def test_already_approved_submission_cannot_be_rejected(self):
        """A submission already 'approved' raises HTTP 409 on reject."""
        fetched = (1, "logo", "approved")
        conn = FakeConn([fetched])
        with patch.object(moderation, "get_conn", _fake_get_conn(conn)):
            coro = moderation.reject_submission({"db_id": 1}, 1, ModerationDecisionRequest(notes=None))
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(coro)
        assert exc_info.value.status_code == 409
