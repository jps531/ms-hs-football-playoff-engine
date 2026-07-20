"""Unit tests for backend.helpers.submission_helpers."""

from datetime import datetime

from backend.helpers.submission_helpers import (
    build_color_overrides,
    build_location_overrides,
    build_score_overrides,
    build_submission_summary,
)


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


class TestBuildColorOverrides:
    """build_color_overrides maps a 'colors' submission payload to school-override pairs."""

    def test_primary_only(self):
        """A primary color alone produces primary_color and primary_color_hex overrides."""
        payload = {"primary_color": {"name": "Red", "hex": "#FF0000"}}
        result = build_color_overrides(payload)
        assert result == [("primary_color", "Red"), ("primary_color_hex", "#FF0000")]

    def test_secondary_colors_joined_with_comma(self):
        """Multiple secondary colors are comma-joined into single name/hex override values."""
        payload = {
            "secondary_colors": [
                {"name": "Blue", "hex": "#0000FF"},
                {"name": "White", "hex": "#FFFFFF"},
            ],
        }
        result = build_color_overrides(payload)
        assert ("secondary_color", "Blue, White") in result
        assert ("secondary_color_hex", "#0000FF, #FFFFFF") in result

    def test_primary_and_secondary_combined(self):
        """Both primary and secondary produce all four override pairs, primary first."""
        payload = {
            "primary_color": {"name": "Red", "hex": "#FF0000"},
            "secondary_colors": [{"name": "Blue", "hex": "#0000FF"}],
        }
        result = build_color_overrides(payload)
        assert result == [
            ("primary_color", "Red"),
            ("primary_color_hex", "#FF0000"),
            ("secondary_color", "Blue"),
            ("secondary_color_hex", "#0000FF"),
        ]

    def test_empty_payload_returns_no_overrides(self):
        """A payload with neither primary nor secondary colors produces an empty list."""
        assert build_color_overrides({}) == []


class TestBuildLocationOverrides:
    """build_location_overrides maps a 'location' submission payload to school-override pairs."""

    def test_latitude_and_longitude_stringified(self):
        """Numeric latitude/longitude are converted to string override values."""
        result = build_location_overrides({"latitude": 34.5, "longitude": -89.1})
        assert result == [("latitude", "34.5"), ("longitude", "-89.1")]


class TestBuildScoreOverrides:
    """build_score_overrides maps a 'score' submission payload to (game_date, overrides)."""

    def test_returns_date_and_stringified_scores(self):
        """Returns the game_date plus points_for/points_against as string override pairs."""
        game_date, overrides = build_score_overrides({"date": "2025-09-05", "points_for": 21, "points_against": 14})
        assert game_date == "2025-09-05"
        assert overrides == [("points_for", "21"), ("points_against", "14")]
