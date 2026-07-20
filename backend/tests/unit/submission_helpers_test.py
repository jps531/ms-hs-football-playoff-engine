"""Unit tests for backend.helpers.submission_helpers."""

from datetime import datetime

from backend.helpers.submission_helpers import build_submission_summary


class TestBuildSubmissionSummary:
    """build_submission_summary maps a submissions row to a SubmissionSummary."""

    def test_fields_mapped_in_order(self):
        """Fields map positionally: id, type, status, school, submitted_at, reviewed_at."""
        submitted = datetime(2025, 9, 1, 12, 0)
        reviewed = datetime(2025, 9, 2, 8, 30)
        row = (7, "logo", "approved", "Taylorsville", submitted, reviewed)
        result = build_submission_summary(row)
        assert result.id == 7
        assert result.type == "logo"
        assert result.status == "approved"
        assert result.school == "Taylorsville"
        assert result.submitted_at == submitted
        assert result.reviewed_at == reviewed

    def test_none_school_and_reviewed_at_allowed(self):
        """A None school (e.g. feedback submissions) and unreviewed submission pass through."""
        submitted = datetime(2025, 9, 1, 12, 0)
        row = (3, "feedback", "pending", None, submitted, None)
        result = build_submission_summary(row)
        assert result.school is None
        assert result.reviewed_at is None
