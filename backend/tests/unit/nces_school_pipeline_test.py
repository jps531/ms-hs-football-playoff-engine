"""Unit tests for backend.prefect.nces_school_pipeline.

Covers match_nces_to_db's collision handling: multiple NCES records can independently
fuzzy-match the same DB school (e.g. a same-named elementary/middle school elsewhere in
the state that shares a strong name prefix with the actual high school) — the
highest-scoring candidate must win regardless of which record is processed first.
"""

import logging

import pytest

import backend.prefect.nces_school_pipeline as pipeline
from backend.helpers.data_classes import School
from backend.prefect.nces_school_pipeline import match_nces_to_db


@pytest.fixture(autouse=True)
def _stub_run_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """match_nces_to_db calls Prefect's get_run_logger(), which requires a live
    flow/task run context; stub it so the matching logic is testable in isolation."""
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logging.getLogger("test"))


def _school(name: str) -> School:
    """Build a minimal School for matching (only the name matters here)."""
    return School(school=name, season=0, class_=0, region=0)


def _rec(nces_name: str, city: str = "Somewhere", lat: float = 30.0, lon: float = -89.0) -> dict:
    """Build a minimal fetch_nces_schools-shaped record for matching."""
    return {"nces_name": nces_name, "city": city, "zip": "39426", "latitude": lat, "longitude": lon}


class TestMatchNcesToDb:
    """match_nces_to_db picks the highest-scoring NCES record per DB school."""

    def test_single_clean_match(self):
        """A normal one-record-one-school case matches straightforwardly."""
        result = match_nces_to_db.fn(
            [_rec("WEST JONES HIGH SCHOOL", city="Laurel")],
            [_school("West Jones")],
        )
        assert len(result) == 1
        assert result[0]["school"] == "West Jones"
        assert result[0]["city"] == "Laurel"

    def test_below_threshold_is_unmatched(self):
        """A record with no reasonably close DB school produces no match."""
        result = match_nces_to_db.fn(
            [_rec("COMPLETELY UNRELATED ACADEMY")],
            [_school("West Jones")],
        )
        assert result == []

    def test_best_match_wins_regardless_of_order(self):
        """Reproduces the Pearl River bug: an out-of-district same-named elementary school
        must never beat (or overwrite) the correct high school's exact-normalized match,
        whichever order the two records are processed in."""
        db_schools = [_school("Pearl River Central")]
        strong = _rec("PEARL RIVER CENTRAL HIGH SCHOOL", city="Carriere", lat=30.625005, lon=-89.653994)
        weak = _rec("PEARL RIVER ELEMENTARY SCHOOL", city="Choctaw", lat=32.777294, lon=-89.203359)

        weak_first = match_nces_to_db.fn([weak, strong], db_schools)
        strong_first = match_nces_to_db.fn([strong, weak], db_schools)

        for result in (weak_first, strong_first):
            assert len(result) == 1
            assert result[0]["city"] == "Carriere"
            assert result[0]["latitude"] == pytest.approx(30.625005)

    def test_only_one_entry_per_db_school(self):
        """Even with multiple clearing-threshold candidates, exactly one entry is returned per school."""
        db_schools = [_school("Pearl River Central")]
        result = match_nces_to_db.fn(
            [
                _rec("PEARL RIVER CENTRAL HIGH SCHOOL", city="Carriere"),
                _rec("PEARL RIVER CENTRAL JUNIOR HIGH", city="Carriere"),
                _rec("PEARL RIVER ELEMENTARY SCHOOL", city="Choctaw"),
            ],
            db_schools,
        )
        assert len(result) == 1
