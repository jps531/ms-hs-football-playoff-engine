"""Unit tests for backend.helpers.api_helpers.build_movers_response (GET /ratings/movers)."""

from backend.helpers.api_helpers import build_movers_response

MoverRow = tuple[str, int, int, float, float]


class TestBuildMoversResponse:
    """Coverage for splitting before/after Elo snapshot rows into sorted risers/fallers."""

    def test_risers_sorted_by_delta_descending(self):
        """Risers are ordered biggest gain first."""
        rows: list[MoverRow] = [
            ("Alpha", 4, 1, 1500.0, 1520.0),  # +20
            ("Beta", 4, 1, 1500.0, 1564.0),  # +64
            ("Gamma", 4, 1, 1500.0, 1540.0),  # +40
        ]
        result = build_movers_response(rows, limit=10)
        assert [m.school for m in result.risers] == ["Beta", "Gamma", "Alpha"]
        assert result.fallers == []

    def test_fallers_sorted_by_delta_ascending(self):
        """Fallers are ordered biggest drop first (most negative delta)."""
        rows: list[MoverRow] = [
            ("Alpha", 4, 1, 1500.0, 1480.0),  # -20
            ("Beta", 4, 1, 1500.0, 1436.0),  # -64
            ("Gamma", 4, 1, 1500.0, 1460.0),  # -40
        ]
        result = build_movers_response(rows, limit=10)
        assert [m.school for m in result.fallers] == ["Beta", "Gamma", "Alpha"]
        assert result.risers == []

    def test_limit_applied_per_direction(self):
        """limit caps risers and fallers independently, not the combined total."""
        rows: list[MoverRow] = [
            ("Riser1", 4, 1, 1500.0, 1510.0),
            ("Riser2", 4, 1, 1500.0, 1520.0),
            ("Riser3", 4, 1, 1500.0, 1530.0),
            ("Faller1", 4, 1, 1500.0, 1490.0),
            ("Faller2", 4, 1, 1500.0, 1480.0),
        ]
        result = build_movers_response(rows, limit=1)
        assert [m.school for m in result.risers] == ["Riser3"]
        assert [m.school for m in result.fallers] == ["Faller2"]

    def test_zero_delta_excluded_from_both_lists(self):
        """A team with no Elo change appears in neither risers nor fallers."""
        rows: list[MoverRow] = [("Static", 4, 1, 1500.0, 1500.0)]
        result = build_movers_response(rows, limit=10)
        assert result.risers == []
        assert result.fallers == []

    def test_empty_input(self):
        """No snapshot rows yields empty risers/fallers rather than an error."""
        result = build_movers_response([], limit=10)
        assert result.risers == []
        assert result.fallers == []

    def test_class_and_region_and_delta_populated(self):
        """Each MoverModel carries through class/region and computes the correct delta."""
        rows: list[MoverRow] = [("Poplarville", 3, 5, 1500.0, 1564.0)]
        result = build_movers_response(rows, limit=10)
        (mover,) = result.risers
        assert mover.class_ == 3
        assert mover.region == 5
        assert mover.elo_before == 1500.0
        assert mover.elo_after == 1564.0
        assert mover.delta == 64.0
