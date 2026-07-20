"""Row-mapping helpers for the submissions/moderation queue, shared across routers."""

from backend.api.models.responses import SubmissionSummary


def build_submission_summary(row: tuple) -> SubmissionSummary:
    """Map a (id, type, status, school, submitted_at, reviewed_at) row to SubmissionSummary."""
    return SubmissionSummary(
        id=row[0],
        type=row[1],
        status=row[2],
        school=row[3],
        submitted_at=row[4],
        reviewed_at=row[5],
    )
