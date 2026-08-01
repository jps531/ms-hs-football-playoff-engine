"""Unit tests for backend.helpers.color_variants (the DB-touching recompute wrapper)."""

import asyncio
import json
from collections.abc import Callable

from backend.helpers import color_variants
from backend.helpers.color_variants import (
    recompute_color_variants,
    recompute_color_variants_sync,
    split_secondary_hexes,
)


class FakeConn:
    """Async FakeConn matching the pattern in query_helpers_test.py / submission_helpers_test.py."""

    def __init__(self):
        """Start with no recorded calls and no queued fetchone result."""
        self.calls: list[tuple[str, tuple]] = []
        self.fetchone_result: tuple | None = None

    async def execute(self, sql, params=()):
        """Record the call and return self, mimicking psycopg3's chained cursor."""
        self.calls.append((sql, params))
        return self

    async def fetchone(self):
        """Return the queued `fetchone_result`."""
        return self.fetchone_result


class FakeCursor:
    """Sync cursor stub for the psycopg2 entry point, usable as a context manager."""

    def __init__(self, fetchone_result: tuple | None):
        """Start with no recorded calls and the given queued fetchone result."""
        self.calls: list[tuple[str, tuple]] = []
        self.fetchone_result = fetchone_result

    def __enter__(self):
        """Support `with conn.cursor() as cur:` usage."""
        return self

    def __exit__(self, *exc_info):
        """Never suppress exceptions raised inside the `with` block."""
        return False

    def execute(self, sql, params=()):
        """Record the call."""
        self.calls.append((sql, params))

    def fetchone(self):
        """Return the queued `fetchone_result`."""
        return self.fetchone_result


class FakeSyncConn:
    """Sync connection stub for the psycopg2 entry point."""

    def __init__(self, fetchone_result: tuple | None):
        """Back the connection with a single `FakeCursor` and a no-op commit."""
        self._cursor = FakeCursor(fetchone_result)
        self.commit: Callable[[], None] = lambda: None

    def cursor(self):
        """Return the underlying `FakeCursor`."""
        return self._cursor


class TestSplitSecondaryHexes:
    """split_secondary_hexes — comma-separated secondary hex string parsing."""

    def test_none_returns_empty(self):
        """A missing value parses to an empty list."""
        assert split_secondary_hexes(None) == []

    def test_empty_string_returns_empty(self):
        """An empty string parses to an empty list."""
        assert split_secondary_hexes("") == []

    def test_single_hex(self):
        """A single hex value round-trips as a one-element list."""
        assert split_secondary_hexes("#FFFFFF") == ["#FFFFFF"]

    def test_multiple_hexes_split_and_stripped(self):
        """Comma-separated hexes are split and whitespace-stripped."""
        assert split_secondary_hexes("#FFFFFF, #000000,#0000FF") == ["#FFFFFF", "#000000", "#0000FF"]


class TestRecomputeColorVariantsAsync:
    """recompute_color_variants (async/psycopg3 entry point)."""

    def test_missing_school_returns_none(self):
        """A school with no matching row returns None after just the SELECT."""
        conn = FakeConn()
        conn.fetchone_result = None
        result = asyncio.run(recompute_color_variants(conn, "Nonexistent School"))
        assert result is None
        assert len(conn.calls) == 1
        assert "schools_effective" in conn.calls[0][0]

    def test_writes_blob_with_computed_at_and_algorithm_version(self):
        """A successful recompute writes a JSON-encoded blob with metadata via UPDATE."""
        conn = FakeConn()
        conn.fetchone_result = ("#2A3EAD", "#FFFFFF, #000000")
        result = asyncio.run(recompute_color_variants(conn, "Taylorsville"))

        assert result is not None
        assert result["primary"]["raw"] == "#2A3EAD"
        assert len(result["secondary"]) == 2
        assert "computed_at" in result
        assert result["algorithm_version"] == 1

        assert len(conn.calls) == 2
        select_sql, select_params = conn.calls[0]
        assert "SELECT primary_color_hex, secondary_color_hex FROM schools_effective" in select_sql
        assert select_params == ("Taylorsville",)

        update_sql, update_params = conn.calls[1]
        assert "UPDATE schools SET color_variants = %s WHERE school = %s" in update_sql
        assert update_params[1] == "Taylorsville"
        # The blob was JSON-encoded (json.dumps), not passed as a raw dict.
        assert isinstance(update_params[0], str)
        assert json.loads(update_params[0])["primary"]["raw"] == "#2A3EAD"

    def test_malformed_hex_logs_warning_without_raising(self, caplog):
        """A malformed stored hex logs a warning and yields a None primary blob, not an exception."""
        conn = FakeConn()
        conn.fetchone_result = ("not-a-color", None)
        with caplog.at_level("WARNING"):
            result = asyncio.run(recompute_color_variants(conn, "Taylorsville"))

        assert result is not None
        assert result["primary"] is None
        assert any("not-a-color" in r.message for r in caplog.records)

    def test_no_primary_no_secondary_still_writes_blob(self):
        """A school with no colors at all still writes an (empty) blob rather than skipping the UPDATE."""
        conn = FakeConn()
        conn.fetchone_result = (None, None)
        result = asyncio.run(recompute_color_variants(conn, "Taylorsville"))
        assert result is not None
        assert result["primary"] is None
        assert result["secondary"] == []


class TestRecomputeColorVariantsSync:
    """recompute_color_variants_sync (sync/psycopg2 entry point)."""

    def test_missing_school_returns_none(self):
        """A school with no matching row returns None after just the SELECT."""
        conn = FakeSyncConn(fetchone_result=None)
        result = recompute_color_variants_sync(conn, "Nonexistent School")
        assert result is None
        assert len(conn._cursor.calls) == 1

    def test_writes_blob_via_json_wrapper(self, monkeypatch):
        """The blob is passed through psycopg2's `Json` wrapper, not pre-serialized to a string."""
        conn = FakeSyncConn(fetchone_result=("#2A3EAD", None))

        written = {}

        def fake_json(value):
            """Record the value `Json()` was called with and pass it through unchanged."""
            written["blob"] = value
            return value

        monkeypatch.setattr(color_variants, "Json", fake_json)

        result = recompute_color_variants_sync(conn, "Taylorsville")

        assert result is not None
        assert result["primary"]["raw"] == "#2A3EAD"
        assert len(conn._cursor.calls) == 2
        update_sql, update_params = conn._cursor.calls[1]
        assert "UPDATE schools SET color_variants = %s WHERE school = %s" in update_sql
        assert update_params[1] == "Taylorsville"
        assert written["blob"] is result

    def test_does_not_commit(self, monkeypatch):
        """The sync entry point never commits — the caller owns the transaction."""
        conn = FakeSyncConn(fetchone_result=("#2A3EAD", None))

        def fail_commit():
            """Fail the test if the caller's connection is committed."""
            raise AssertionError("recompute_color_variants_sync must not commit")

        conn.commit = fail_commit
        recompute_color_variants_sync(conn, "Taylorsville")


class TestNowIso:
    """_now_iso — the module-level clock hook, monkeypatchable for deterministic timestamps."""

    def test_now_iso_is_monkeypatchable_for_round_trip_style_tests(self, monkeypatch):
        """Two recomputes with different clocks produce different computed_at values —
        the mocked equivalent of spec §7's DB round-trip test."""
        conn = FakeConn()
        conn.fetchone_result = ("#2A3EAD", None)

        monkeypatch.setattr(color_variants, "_now_iso", lambda: "2026-01-01T00:00:00+00:00")
        first = asyncio.run(recompute_color_variants(conn, "Taylorsville"))

        monkeypatch.setattr(color_variants, "_now_iso", lambda: "2026-06-01T00:00:00+00:00")
        second = asyncio.run(recompute_color_variants(conn, "Taylorsville"))

        assert first is not None
        assert second is not None
        assert first["computed_at"] != second["computed_at"]
