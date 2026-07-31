"""Unit tests for backend.helpers.query_helpers (dynamic SQL fragment builders)."""

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException
from psycopg import sql

from backend.helpers.query_helpers import (
    and_join_conditions,
    append_optional_filters,
    build_set_clause,
    require_nonempty_update,
    set_helmet_image_column,
    upsert_school_season,
    validate_override_field,
    validate_submission_for_helmet_link,
)


class FakeConn:
    """Records every `execute(sql, params)` call; `fetchone_result` is what the
    next `.fetchone()` after `execute()` returns."""

    def __init__(self):
        """Start with no recorded calls and no queued fetchone() result."""
        self.calls: list[tuple[Any, tuple]] = []
        self.fetchone_result: tuple | None = None

    async def execute(self, sql, params=()):
        """Record the call and return self, so `.fetchone()` can be chained."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return whatever the test set as fetchone_result."""
        return self.fetchone_result


class TestAndJoinConditions:
    """and_join_conditions joins raw SQL condition strings with AND."""

    def test_single_condition(self):
        """A single condition round-trips unchanged."""
        result = and_join_conditions(["g.season = %s"])
        assert result.as_string(None) == "g.season = %s"

    def test_multiple_conditions_joined_with_and(self):
        """Multiple conditions are joined with ' AND ' between them."""
        result = and_join_conditions(["g.season = %s", "ss.class = %s", "ss.region = %s"])
        assert result.as_string(None) == "g.season = %s AND ss.class = %s AND ss.region = %s"

    def test_empty_list_returns_empty_composed(self):
        """An empty conditions list produces an empty SQL fragment."""
        result = and_join_conditions([])
        assert result.as_string(None) == ""


class TestBuildSetClause:
    """build_set_clause builds a `col = %s, ...` fragment from an update dict."""

    def test_single_field(self):
        """A single-key dict produces one `col = %s` fragment."""
        result = build_set_clause({"name": "New Name"})
        assert result.as_string(None) == '"name" = %s'

    def test_multiple_fields_joined_with_comma(self):
        """Multiple keys are joined with ', ' in dict iteration order."""
        result = build_set_clause({"name": "x", "city": "y"})
        assert result.as_string(None) == '"name" = %s, "city" = %s'

    def test_column_name_quoted_as_identifier(self):
        """Column names are quoted via sql.Identifier, not interpolated as raw SQL."""
        result = build_set_clause({"weird col": "x"})
        assert isinstance(result, sql.Composed)
        assert '"weird col"' in result.as_string(None)


class TestRequireNonemptyUpdate:
    """require_nonempty_update raises HTTP 422 on an empty update dict."""

    def test_empty_dict_raises_422(self):
        """An empty dict raises HTTP 422."""
        with pytest.raises(HTTPException) as exc_info:
            require_nonempty_update({})
        assert exc_info.value.status_code == 422

    def test_nonempty_dict_raises_nothing(self):
        """A dict with at least one key raises nothing."""
        require_nonempty_update({"name": "x"})


class TestValidateOverrideField:
    """validate_override_field raises HTTP 422 on a field outside the allowed set."""

    def test_valid_field_raises_nothing(self):
        """A field present in valid_fields raises nothing."""
        validate_override_field("mascot", frozenset({"mascot", "primary_color"}))

    def test_invalid_field_raises_422(self):
        """A field absent from valid_fields raises HTTP 422 naming the field."""
        valid_fields = frozenset({"mascot", "primary_color"})
        with pytest.raises(HTTPException) as exc_info:
            validate_override_field("not_a_field", valid_fields)
        assert exc_info.value.status_code == 422
        assert "not_a_field" in exc_info.value.detail

    def test_error_message_lists_sorted_valid_fields(self):
        """The 422 detail lists the valid fields sorted, to help the caller self-correct."""
        valid_fields = frozenset({"zebra", "apple"})
        with pytest.raises(HTTPException) as exc_info:
            validate_override_field("bogus", valid_fields)
        assert "['apple', 'zebra']" in exc_info.value.detail


class TestUpsertSchoolSeason:
    """upsert_school_season creates/updates a school_seasons row, with an optional identity copy."""

    def test_without_copy_identity_makes_two_writes(self):
        """No copy_identity_from means just the schools insert-if-missing and the school_seasons upsert."""
        conn = FakeConn()
        asyncio.run(upsert_school_season(conn, "Leake", 2026, 5, 2, True, None))
        assert len(conn.calls) == 2
        assert "INSERT INTO schools" in conn.calls[0][0]
        assert "INSERT INTO school_seasons" in conn.calls[1][0]
        assert conn.calls[1][1] == ("Leake", 2026, 5, 2, True)

    def test_copy_identity_from_missing_source_raises_404(self):
        """A copy_identity_from school that doesn't exist raises HTTP 404 before the identity UPDATE runs."""
        conn = FakeConn()
        conn.fetchone_result = None  # source lookup finds nothing
        coro = upsert_school_season(conn, "Leake", 2026, 5, 2, True, "Nonexistent School")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(coro)
        assert exc_info.value.status_code == 404
        # Only the two unconditional writes plus the source-existence check ran — no identity UPDATE.
        assert len(conn.calls) == 3

    def test_copy_identity_from_existing_source_runs_identity_update(self):
        """A valid copy_identity_from school runs the identity-copy UPDATE as a fourth statement."""
        conn = FakeConn()
        conn.fetchone_result = (1,)  # source school exists
        asyncio.run(upsert_school_season(conn, "Leake", 2026, 5, 2, True, "Leake Central"))
        assert len(conn.calls) == 4
        assert "UPDATE schools s SET" in conn.calls[3][0]
        assert conn.calls[3][1] == ("Leake", "Leake Central")


class TestValidateSubmissionForHelmetLink:
    """validate_submission_for_helmet_link checks a fetched submissions row before linking it."""

    def test_none_row_raises_404(self):
        """A missing submission (row=None) raises HTTP 404."""
        with pytest.raises(HTTPException) as exc_info:
            validate_submission_for_helmet_link(None, 42)
        assert exc_info.value.status_code == 404

    def test_wrong_type_raises_422(self):
        """A non-'helmet' submission type raises HTTP 422."""
        with pytest.raises(HTTPException) as exc_info:
            validate_submission_for_helmet_link(("colors", None), 42)
        assert exc_info.value.status_code == 422

    def test_already_linked_raises_409(self):
        """A helmet submission already linked to a design (helmet_design_id set) raises HTTP 409."""
        with pytest.raises(HTTPException) as exc_info:
            validate_submission_for_helmet_link(("helmet", 7), 42)
        assert exc_info.value.status_code == 409
        assert "7" in exc_info.value.detail

    def test_valid_unlinked_helmet_submission_raises_nothing(self):
        """A helmet-type, not-yet-linked submission passes validation."""
        validate_submission_for_helmet_link(("helmet", None), 42)


class TestAppendOptionalFilters:
    """append_optional_filters appends (sql, value) pairs whose value is not None."""

    def test_appends_only_non_none_pairs(self):
        """None-valued pairs are skipped; non-None pairs append to both lists in order."""
        conditions: list = ["base = %s"]
        params: list = [1]
        append_optional_filters(conditions, params, ("a = %s", "x"), ("b = %s", None), ("c = %s", 3))
        assert conditions == ["base = %s", "a = %s", "c = %s"]
        assert params == [1, "x", 3]

    def test_all_none_leaves_lists_unchanged(self):
        """Every pair being None leaves the base conditions/params untouched."""
        conditions: list = ["base = %s"]
        params: list = [1]
        append_optional_filters(conditions, params, ("a = %s", None), ("b = %s", None))
        assert conditions == ["base = %s"]
        assert params == [1]

    def test_no_pairs_is_a_no_op(self):
        """No (sql, value) pairs at all leaves conditions/params untouched."""
        conditions: list = ["base = %s"]
        params: list = [1]
        append_optional_filters(conditions, params)
        assert conditions == ["base = %s"]
        assert params == [1]

    def test_falsy_but_not_none_values_are_kept(self):
        """A falsy-but-not-None value (0, "") is still appended — only None is skipped."""
        conditions: list = []
        params: list = []
        append_optional_filters(conditions, params, ("a = %s", 0), ("b = %s", ""))
        assert conditions == ["a = %s", "b = %s"]
        assert params == [0, ""]


class TestSetHelmetImageColumn:
    """set_helmet_image_column writes to the correct helmet_designs image column per image_type."""

    def test_left_maps_to_image_left(self):
        """image_type='left' writes to the image_left column."""
        conn = FakeConn()
        asyncio.run(set_helmet_image_column(conn, 42, "left", "path/left.jpg"))
        sql_composed, params = conn.calls[0]
        assert "image_left" in sql_composed.as_string(None)
        assert params == ("path/left.jpg", 42)

    def test_right_maps_to_image_right(self):
        """image_type='right' writes to the image_right column."""
        conn = FakeConn()
        asyncio.run(set_helmet_image_column(conn, 42, "right", "path/right.jpg"))
        assert "image_right" in conn.calls[0][0].as_string(None)

    def test_photo_maps_to_itself(self):
        """'photo' maps to the 'photo' column, not 'image_photo' — not a simple prefix pattern."""
        conn = FakeConn()
        asyncio.run(set_helmet_image_column(conn, 42, "photo", "path/photo.jpg"))
        sql_text = conn.calls[0][0].as_string(None)
        assert "photo" in sql_text
        assert "image_photo" not in sql_text
