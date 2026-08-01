"""Unit tests for backend.helpers.submission_helpers."""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.api.models.requests import (
    ColorEntry,
    SubmitColorsRequest,
    SubmitFeedbackRequest,
    SubmitHelmetAssignmentRequest,
    SubmitLocationRequest,
    SubmitScoreRequest,
)
from backend.helpers.submission_helpers import (
    apply_submission,
    assemble_optional_fields,
    build_color_overrides,
    build_colors_payload,
    build_feedback_payload,
    build_helmet_assignment_override,
    build_helmet_assignment_payload,
    build_helmet_image_fields,
    build_helmet_initial_payload,
    build_location_overrides,
    build_location_payload,
    build_logo_image_fields,
    build_logo_initial_payload,
    build_score_overrides,
    build_score_payload,
    build_submission_summary,
    insert_submission,
    resolve_approval_status,
    update_submission_payload,
)


class FakeConn:
    """Records every `execute(sql, params)` call made against it.

    `fetchone_result` (set by the caller) is what `.fetchone()` returns after
    the next `execute()` call, for the INSERT ... RETURNING pattern.
    """

    def __init__(self):
        """Start with no recorded calls and no queued fetchone() result."""
        self.calls: list[tuple[str, tuple]] = []
        self.fetchone_result: tuple | None = None

    async def execute(self, sql: str, params: tuple = ()):
        """Record the call and return self, so `.fetchone()` can be chained."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return whatever the test set as fetchone_result."""
        return self.fetchone_result


def _submission_row(
    stype: str, school: str | None, payload: dict, submission_id: int = 1
) -> tuple:
    """Build a (id, type, status, school, submitted_at, reviewed_at, payload, notes, helmet_design_id) row."""
    return (submission_id, stype, "pending", school, datetime(2025, 9, 1), None, payload, None, None)


class TestBuildSubmissionSummary:
    """build_submission_summary maps a submissions row to a SubmissionSummary."""

    def test_fields_mapped_in_order(self):
        """Fields map positionally: id, type, status, school, submitted_at, reviewed_at, helmet_design_id."""
        submitted = datetime(2025, 9, 1, 12, 0)
        reviewed = datetime(2025, 9, 2, 8, 30)
        row = (7, "logo", "approved", "Taylorsville", submitted, reviewed, None)
        result = build_submission_summary(row)
        assert result.id == 7
        assert result.type == "logo"
        assert result.status == "approved"
        assert result.school == "Taylorsville"
        assert result.submitted_at == submitted
        assert result.reviewed_at == reviewed
        assert result.helmet_design_id is None

    def test_none_school_and_reviewed_at_allowed(self):
        """A None school (e.g. feedback submissions) and unreviewed submission pass through."""
        submitted = datetime(2025, 9, 1, 12, 0)
        row = (3, "feedback", "pending", None, submitted, None, None)
        result = build_submission_summary(row)
        assert result.school is None
        assert result.reviewed_at is None

    def test_helmet_design_id_passed_through(self):
        """A linked helmet submission carries its helmet_design_id through."""
        submitted = datetime(2025, 9, 1, 12, 0)
        row = (9, "helmet", "approved", "Taylorsville", submitted, submitted, 42)
        result = build_submission_summary(row)
        assert result.helmet_design_id == 42


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


class TestBuildHelmetAssignmentOverride:
    """build_helmet_assignment_override maps a 'helmet_assignment' submission payload to (game_date, helmet_design_id)."""

    def test_returns_date_and_helmet_design_id(self):
        """Returns the game_date and helmet_design_id straight from the payload."""
        game_date, helmet_design_id = build_helmet_assignment_override({"date": "2025-09-05", "helmet_design_id": 42})
        assert game_date == "2025-09-05"
        assert helmet_design_id == 42


class TestApplySubmission:
    """apply_submission dispatches an approved submission's payload to the live tables."""

    def test_missing_school_raises_422(self):
        """A submission with no school (other than feedback, handled elsewhere) is rejected."""
        conn = FakeConn()
        row = _submission_row("colors", None, {})
        coro = apply_submission(conn, row)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(coro)
        assert exc_info.value.status_code == 422

    def test_logo_is_a_no_op(self):
        """A 'logo' submission makes no DB writes — the moderator creates the team_logos
        row and uploads the asset manually, mirroring how 'helmet' submissions work."""
        conn = FakeConn()
        payload = {"logo_type": "primary", "cloudinary_path": "logos/submissions/primary/Taylorsville_1"}
        row = _submission_row("logo", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        assert conn.calls == []

    def test_helmet_is_a_no_op(self):
        """A 'helmet' submission makes no DB writes — the moderator creates the design manually."""
        conn = FakeConn()
        row = _submission_row("helmet", "Taylorsville", {})
        asyncio.run(apply_submission(conn, row))
        assert conn.calls == []

    def test_feedback_is_a_no_op(self):
        """A 'feedback' submission makes no DB writes."""
        conn = FakeConn()
        row = _submission_row("feedback", "Taylorsville", {"subject": "x", "message": "y"})
        asyncio.run(apply_submission(conn, row))
        assert conn.calls == []

    @patch("backend.helpers.submission_helpers.recompute_color_variants", new_callable=AsyncMock)
    def test_colors_sets_school_overrides(self, mock_recompute):
        """A 'colors' submission calls set_school_override once per (field, value) pair."""
        conn = FakeConn()
        payload = {"primary_color": {"name": "Red", "hex": "#FF0000"}}
        row = _submission_row("colors", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        assert len(conn.calls) == 2
        assert conn.calls[0] == ("SELECT set_school_override(%s, %s, %s)", ("Taylorsville", "primary_color", "Red"))
        assert conn.calls[1] == (
            "SELECT set_school_override(%s, %s, %s)",
            ("Taylorsville", "primary_color_hex", "#FF0000"),
        )

    @patch("backend.helpers.submission_helpers.recompute_color_variants", new_callable=AsyncMock)
    def test_colors_recomputes_color_variants_after_overrides(self, mock_recompute):
        """A 'colors' submission recomputes color_variants after writing the overrides, on the same connection."""
        conn = FakeConn()
        payload = {"primary_color": {"name": "Red", "hex": "#FF0000"}}
        row = _submission_row("colors", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        mock_recompute.assert_awaited_once_with(conn, "Taylorsville")

    def test_location_sets_school_overrides(self):
        """A 'location' submission calls set_school_override for latitude and longitude."""
        conn = FakeConn()
        payload = {"latitude": 34.5, "longitude": -89.1}
        row = _submission_row("location", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        assert len(conn.calls) == 2
        assert conn.calls[0] == ("SELECT set_school_override(%s, %s, %s)", ("Taylorsville", "latitude", "34.5"))
        assert conn.calls[1] == ("SELECT set_school_override(%s, %s, %s)", ("Taylorsville", "longitude", "-89.1"))

    def test_score_sets_game_overrides(self):
        """A 'score' submission calls set_game_override with the game date for each score field."""
        conn = FakeConn()
        payload = {"date": "2025-09-05", "points_for": 21, "points_against": 14}
        row = _submission_row("score", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        assert len(conn.calls) == 2
        assert conn.calls[0] == (
            "SELECT set_game_override(%s, %s, %s, %s)",
            ("Taylorsville", "2025-09-05", "points_for", "21"),
        )
        assert conn.calls[1] == (
            "SELECT set_game_override(%s, %s, %s, %s)",
            ("Taylorsville", "2025-09-05", "points_against", "14"),
        )

    @patch("backend.helpers.submission_helpers.require_helmet_design_exists", new_callable=AsyncMock)
    def test_helmet_assignment_updates_games_after_existence_check(self, mock_require_exists):
        """A 'helmet_assignment' submission verifies the design exists, then updates the game row."""
        conn = FakeConn()
        payload = {"date": "2025-09-05", "helmet_design_id": 42}
        row = _submission_row("helmet_assignment", "Taylorsville", payload)
        asyncio.run(apply_submission(conn, row))
        mock_require_exists.assert_awaited_once_with(conn, 42)
        assert conn.calls == [
            (
                "UPDATE games SET helmet_design_id = %s WHERE school = %s AND date = %s",
                (42, "Taylorsville", "2025-09-05"),
            )
        ]

    def test_unrecognized_type_is_a_silent_no_op(self):
        """An unrecognized submission type matches no branch and makes no DB writes."""
        conn = FakeConn()
        row = _submission_row("bogus_type", "Taylorsville", {})
        asyncio.run(apply_submission(conn, row))
        assert conn.calls == []


class TestAssembleOptionalFields:
    """assemble_optional_fields keeps only pairs whose value is not None."""

    def test_drops_none_values(self):
        """None values are dropped; falsy-but-not-None values (0, "", False) are kept."""
        result = assemble_optional_fields([("a", 1), ("b", None), ("c", 0), ("d", ""), ("e", False)])
        assert result == {"a": 1, "c": 0, "d": "", "e": False}

    def test_empty_list_returns_empty_dict(self):
        """No pairs produces an empty dict."""
        assert assemble_optional_fields([]) == {}


class TestBuildColorsPayload:
    """build_colors_payload mirrors build_color_overrides in the opposite direction (request -> payload)."""

    def test_primary_and_secondary(self):
        """Both primary and secondary colors are dumped into the payload dict."""
        body = SubmitColorsRequest(
            school="Taylorsville",
            primary_color=ColorEntry(name="Red", hex="#FF0000"),
            secondary_colors=[ColorEntry(name="Blue", hex="#0000FF")],
        )
        result = build_colors_payload(body)
        assert result == {
            "primary_color": {"name": "Red", "hex": "#FF0000"},
            "secondary_colors": [{"name": "Blue", "hex": "#0000FF"}],
        }

    def test_primary_only_omits_secondary_key(self):
        """No secondary_colors means the key is absent, not an empty list."""
        body = SubmitColorsRequest(school="Taylorsville", primary_color=ColorEntry(name="Red", hex="#FF0000"))
        result = build_colors_payload(body)
        assert "secondary_colors" not in result

    def test_secondary_only_omits_primary_key(self):
        """No primary_color means the key is absent, not None."""
        body = SubmitColorsRequest(
            school="Taylorsville", secondary_colors=[ColorEntry(name="Blue", hex="#0000FF")]
        )
        result = build_colors_payload(body)
        assert "primary_color" not in result
        assert result == {"secondary_colors": [{"name": "Blue", "hex": "#0000FF"}]}


class TestBuildLocationPayload:
    """build_location_payload maps a SubmitLocationRequest to a payload dict."""

    def test_maps_latitude_longitude(self):
        """latitude/longitude pass straight through into the payload dict."""
        body = SubmitLocationRequest(school="Taylorsville", latitude=34.5, longitude=-89.1)
        assert build_location_payload(body) == {"latitude": 34.5, "longitude": -89.1}


class TestBuildScorePayload:
    """build_score_payload maps a SubmitScoreRequest to a payload dict with an ISO date string."""

    def test_maps_fields_and_isoformats_date(self):
        """date is ISO-formatted; points_for/points_against pass through unchanged."""
        body = SubmitScoreRequest(school="Taylorsville", date=date(2025, 9, 5), points_for=21, points_against=14)
        result = build_score_payload(body)
        assert result == {"date": "2025-09-05", "points_for": 21, "points_against": 14}


class TestBuildHelmetAssignmentPayload:
    """build_helmet_assignment_payload maps a SubmitHelmetAssignmentRequest to a payload dict."""

    def test_maps_fields_and_isoformats_date(self):
        """date is ISO-formatted; helmet_design_id passes through unchanged."""
        body = SubmitHelmetAssignmentRequest(school="Taylorsville", date=date(2025, 9, 5), helmet_design_id=42)
        result = build_helmet_assignment_payload(body)
        assert result == {"date": "2025-09-05", "helmet_design_id": 42}


class TestBuildFeedbackPayload:
    """build_feedback_payload maps a SubmitFeedbackRequest to a payload dict."""

    def test_maps_subject_and_message(self):
        """subject/message pass straight through into the payload dict."""
        body = SubmitFeedbackRequest(subject="Bug report", message="Something's wrong")
        assert build_feedback_payload(body) == {"subject": "Bug report", "message": "Something's wrong"}


class TestBuildLogoInitialPayload:
    """build_logo_initial_payload builds the pre-upload payload for a 'logo' submission."""

    def test_maps_logo_type(self):
        """logo_type maps directly into the payload dict."""
        assert build_logo_initial_payload("primary") == {"logo_type": "primary"}

    def test_secondary_and_tertiary_pass_through(self):
        """Non-primary logo_type values pass through unchanged."""
        assert build_logo_initial_payload("secondary") == {"logo_type": "secondary"}
        assert build_logo_initial_payload("tertiary") == {"logo_type": "tertiary"}


class TestBuildLogoImageFields:
    """build_logo_image_fields builds the payload field merged in after image upload."""

    def test_maps_cloudinary_path(self):
        """cloudinary_path maps directly into the payload dict."""
        assert build_logo_image_fields("logos/submissions/primary/Taylorsville_1") == {
            "cloudinary_path": "logos/submissions/primary/Taylorsville_1",
        }


class TestResolveApprovalStatus:
    """resolve_approval_status picks the post-approval status per submission type."""

    def test_logo_moves_to_accepted_pending_asset(self):
        """'logo' submissions move to accepted_pending_asset, not approved."""
        assert resolve_approval_status("logo") == "accepted_pending_asset"

    def test_helmet_moves_straight_to_approved(self):
        """'helmet' submissions move straight to approved, unchanged from today."""
        assert resolve_approval_status("helmet") == "approved"

    def test_colors_moves_straight_to_approved(self):
        """'colors' submissions move straight to approved, unchanged from today."""
        assert resolve_approval_status("colors") == "approved"

    def test_location_score_feedback_helmet_assignment_move_straight_to_approved(self):
        """Every other submission type moves straight to approved, unchanged from today."""
        for stype in ("location", "score", "feedback", "helmet_assignment"):
            assert resolve_approval_status(stype) == "approved"


class TestBuildHelmetInitialPayload:
    """build_helmet_initial_payload builds a 'helmet' submission's payload from form fields."""

    def test_required_fields_only(self):
        """Only the two required fields produces a minimal payload."""
        result = build_helmet_initial_payload(year_first_worn=2020, description="A new design")
        assert result == {"year_first_worn": 2020, "description": "A new design"}

    def test_currently_worn_false_is_omitted(self):
        """currently_worn=False (the default) is not written into the payload."""
        result = build_helmet_initial_payload(year_first_worn=2020, description="x", currently_worn=False)
        assert "currently_worn" not in result

    def test_all_fields_populated(self):
        """Every optional field, when provided, appears in the payload."""
        result = build_helmet_initial_payload(
            year_first_worn=2020,
            description="A new design",
            year_last_worn=2023,
            currently_worn=True,
            color="black",
            finish="matte",
            facemask_color="white",
            logo_description="script W",
            stripe="single center stripe",
            additional_notes="worn only for rivalry games",
            other_note="submitted by a fan",
        )
        assert result == {
            "year_first_worn": 2020,
            "description": "A new design",
            "year_last_worn": 2023,
            "currently_worn": True,
            "color": "black",
            "finish": "matte",
            "facemask_color": "white",
            "logo_description": "script W",
            "stripe": "single center stripe",
            "additional_notes": "worn only for rivalry games",
            "other_note": "submitted by a fan",
        }


class TestBuildHelmetImageFields:
    """build_helmet_image_fields builds the payload fields merged in after image upload."""

    def test_image_paths_only(self):
        """No labels or logo image produces just the image_paths key."""
        result = build_helmet_image_fields(["path/1.jpg", "path/2.jpg"], [], None)
        assert result == {"image_paths": ["path/1.jpg", "path/2.jpg"]}

    def test_labels_and_logo_included_when_present(self):
        """Labels and a logo image path are included when supplied."""
        result = build_helmet_image_fields(["path/1.jpg"], ["left"], "path/logo.jpg")
        assert result == {"image_paths": ["path/1.jpg"], "image_labels": ["left"], "logo_image_path": "path/logo.jpg"}


class TestInsertSubmission:
    """insert_submission writes a new pending submission row and returns (id, submitted_at)."""

    def test_inserts_with_json_encoded_payload(self):
        """The payload dict is JSON-encoded and all four columns are parameterized (no literal SQL per type)."""
        submitted = datetime(2025, 9, 1, 12, 0)
        conn = FakeConn()
        conn.fetchone_result = (7, submitted)

        result = asyncio.run(insert_submission(conn, "colors", "Taylorsville", 3, {"primary_color": "Red"}))

        assert result == (7, submitted)
        assert len(conn.calls) == 1
        sql, params = conn.calls[0]
        assert "INSERT INTO submissions" in sql
        assert params == ("colors", "Taylorsville", 3, '{"primary_color": "Red"}')

    def test_school_none_for_feedback(self):
        """A None school (feedback submissions) is passed through as a parameter, not a SQL literal."""
        conn = FakeConn()
        conn.fetchone_result = (9, datetime(2025, 9, 1))

        asyncio.run(insert_submission(conn, "feedback", None, None, {"subject": "x", "message": "y"}))

        _, params = conn.calls[0]
        assert params[1] is None  # school
        assert params[2] is None  # user_id


class TestUpdateSubmissionPayload:
    """update_submission_payload overwrites a submission's payload column."""

    def test_updates_with_json_encoded_payload(self):
        """The payload dict is JSON-encoded and written along with the submission_id."""
        conn = FakeConn()
        asyncio.run(update_submission_payload(conn, 7, {"image_paths": ["a.jpg"]}))
        assert len(conn.calls) == 1
        sql, params = conn.calls[0]
        assert "UPDATE submissions SET payload" in sql
        assert params == ('{"image_paths": ["a.jpg"]}', 7)
