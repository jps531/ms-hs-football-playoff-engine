"""Unit tests for backend.helpers.attention: a daily update's things to look at, in one email."""

import pytest

from backend.helpers import attention


@pytest.fixture(autouse=True)
def _empty():
    """Each test starts and ends with no notes."""
    attention.clear()
    yield
    attention.clear()


def test_notes_come_back_grouped_in_kind_order_then_are_gone():
    attention.note(attention.SHARE_IMAGES, "Drawing them failed: OSError: disk full")
    attention.note(attention.SKIPPED_SCHOOLS, "Aberdeen")
    attention.note(attention.SKIPPED_SCHOOLS, "Amory")
    assert attention.take() == {
        attention.SKIPPED_SCHOOLS: ["Aberdeen", "Amory"],
        attention.SHARE_IMAGES: ["Drawing them failed: OSError: disk full"],
    }
    assert attention.take() == {}


def test_an_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        attention.note("something_else", "x")


def test_the_email_lists_each_kind_with_what_to_do():
    attention.note(attention.SKIPPED_SCHOOLS, "Aberdeen")
    attention.note(
        attention.CHANGED_UNDER_CORRECTION,
        "Alpha's 2026-10-24 game vs Beta: points_for 14 -> 17 on AHSFHS; the correction is 21",
    )
    subject, text = attention.render(attention.take(), 2026)
    assert subject == "Daily update done, 2 things to look at"
    assert text.startswith("The 2026 daily update finished and the site shows its numbers.")
    assert "AHSFHS pages that couldn't be read (1)\nThese schools' new scores aren't in today's numbers." in text
    assert "- Aberdeen" in text
    assert "Scores AHSFHS changed under an approved correction (1)\nThe correction still shows." in text
    assert text.index("AHSFHS pages") < text.index("Scores AHSFHS changed")
    assert attention.render({attention.SHARE_IMAGES: ["x"]}, 2026)[0] == "Daily update done, 1 thing to look at"
