"""Unit tests for backend.prefect.misshsaa_school_pipeline's directory parsing and matching.

The MHSAA school directory is where each school's mascot and colors come from (the team marks, the
share cards). The HTML below has the shape of the rendered Knack directory the pipeline reads: one
``.kn-list-item-container`` per school, with its fields in ``.field_N`` containers (field_1 name,
field_32 school type, field_37 mascot, field_38 colors).
"""

import logging

import pytest

import backend.prefect.misshsaa_school_pipeline as pipeline
from backend.helpers.data_classes import School
from backend.prefect.misshsaa_school_pipeline import _parse_directory_html


def _item(name: str, kind: str, mascot: str | None, colors: str | None) -> str:
    """One directory entry as the rendered page has it (a field left out when *None*)."""
    field = lambda n, text: (  # noqa: E731
        ""
        if text is None
        else f'<div class="kn-detail field_{n}"><div class="kn-detail-label">x</div><div class="kn-detail-body">{text}</div></div>'
    )
    return (
        '<div class="kn-list-item-container">'
        f'<div class="kn-detail kn-label-none field_1">{name}</div>'
        f"{field(32, kind)}{field(37, mascot)}{field(38, colors)}"
        "</div>"
    )


DIRECTORY = "<div>" + "".join([
    _item("Tupelo High School", "High School", "Ram/Lady Rams", "Red &amp; Gold"),
    _item("Taylorsville Attendance Center", "Attendance Center", "Tartars", "Red, White and Blue"),
    _item("Tupelo Middle School", "Middle School", "Golden Wave", "Red &amp; Gold"),
    _item("Hazlehurst High School", "High School", None, None),
]) + "</div>"  # fmt: skip


@pytest.fixture(autouse=True)
def _stub_run_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tasks call Prefect's get_run_logger(), which needs a live run; stub it."""
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logging.getLogger("test"))


def test_only_high_schools_and_attendance_centers_are_read():
    """Middle schools (and district offices) aren't football programs here."""
    assert [r["name"] for r in _parse_directory_html(DIRECTORY)] == [
        "Tupelo High School",
        "Taylorsville Attendance Center",
        "Hazlehurst High School",
    ]


def test_each_school_gets_its_mascot_and_colors_with_their_hex():
    """The mascot and the colors as listed, the first color the primary, each named color as hex."""
    tupelo, taylorsville, _ = _parse_directory_html(DIRECTORY)
    # "Ram/Lady Rams": the boys' nickname, pluralized.
    assert (tupelo["mascot"], tupelo["primary_color"], tupelo["secondary_color"]) == ("Rams", "Red", "Gold")
    assert tupelo["primary_color_hex"].startswith("#") and tupelo["secondary_color_hex"].startswith("#")
    assert taylorsville["primary_color"] == "Red"
    assert taylorsville["secondary_color"].split(", ") == ["White", "Blue"]


def test_a_school_missing_its_mascot_or_colors_is_kept_with_them_blank():
    """Missing fields read as blank, which update_rows leaves alone (it never blanks a stored value)."""
    *_, hazlehurst = _parse_directory_html(DIRECTORY)
    assert (hazlehurst["mascot"], hazlehurst["primary_color"], hazlehurst["secondary_color"]) == ("", "", "")


def test_a_page_with_no_directory_entries_yields_nothing():
    """A redesigned or failed page parses to no records (the task then warns), never to junk."""
    assert _parse_directory_html("<div>Service unavailable</div>") == []
    assert _parse_directory_html('<div class="kn-list-item-container"><p>no fields</p></div>') == []


def test_directory_names_match_the_sites_short_names():
    """ "Tupelo High School" is Tupelo; a name nothing resembles is left unmatched rather than guessed."""
    records = _parse_directory_html(DIRECTORY) + [
        {"name": "Nowhere Christian Academy", "mascot": "X", "primary_color": "", "secondary_color": "",
         "primary_color_hex": "", "secondary_color_hex": ""},
    ]  # fmt: skip
    db = [
        School(school=s, class_=c, region=1, season=2026)
        for s, c in (("Tupelo", 7), ("Taylorsville", 2), ("Hazlehurst", 3))
    ]
    matched = {m["school"]: m["mascot"] for m in pipeline.match_directory_to_db.fn(records, db)}
    assert matched == {"Tupelo": "Rams", "Taylorsville": "Tartars", "Hazlehurst": ""}
