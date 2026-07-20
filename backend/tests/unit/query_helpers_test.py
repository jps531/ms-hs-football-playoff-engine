"""Unit tests for backend.helpers.query_helpers (dynamic SQL fragment builders)."""

import pytest
from fastapi import HTTPException
from psycopg import sql

from backend.helpers.query_helpers import and_join_conditions, build_set_clause, require_nonempty_update


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
