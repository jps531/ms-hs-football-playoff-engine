"""The site's wording states some of the engine's settings; it has to keep saying the right ones.

The About page, the front page, the footers and the app say "5 or fewer", "50,000 times", "under
0.5%" and "9:00 Central" in words. Each is checked here against the setting it describes
(``backend.helpers.engine_settings``, the pipeline's thresholds and the daily schedule), so changing a
setting without its wording, or the wording without the setting, fails.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

import backend.helpers.static_pages as sp
from backend.helpers.engine_settings import (
    ENUMERATE_MAX_LEFT,
    FULL_MARGINS_MAX_LEFT,
    LISTING_FLOOR,
    MONTE_CARLO_SAMPLES,
)
from backend.prefect import region_scenarios_pipeline as pipeline

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT / "nginx" / "html"
SOURCES = {
    "about.html": (HTML / "about.html").read_text(),
    "index.html": (HTML / "index.html").read_text(),
    "app.js": (HTML / "static" / "js" / "app.js").read_text(),
    "static_pages.py": Path(sp.__file__).read_text(),
    "share_cards.py": (ROOT / "backend" / "helpers" / "share_cards.py").read_text(),
}
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def _words(text: str) -> str:
    """Text with tags dropped, entities decoded and whitespace collapsed (HTML wraps lines anywhere)."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def _count(pattern: str, text: str) -> int:
    """How many times *pattern* matches *text*'s words."""
    return len(re.findall(pattern, _words(text)))


# How each page breaks down the computation by games left: (words, the settings they come from).
STEPS = [
    f"When there are {FULL_MARGINS_MAX_LEFT} or fewer",
    f"When there are {FULL_MARGINS_MAX_LEFT + 1} to {pipeline._R_MAX_ATOMS}",
    f"When there are {pipeline._R_MAX_ATOMS + 1} to {ENUMERATE_MAX_LEFT}",
    f"When there are more than {ENUMERATE_MAX_LEFT}",
]


@pytest.mark.parametrize("page", ["about.html", "the front page"])
def test_the_computation_steps_match_the_pipeline(page):
    """About and the front page list the same games-left steps the pipeline uses, in order."""
    text = _words(SOURCES["about.html"] if page == "about.html" else " ".join(sp.HOW_IT_WORKS_HTML))
    at = [text.find(step) for step in STEPS]
    assert -1 not in at, [s for s, i in zip(STEPS, at, strict=True) if i == -1]
    assert at == sorted(at)
    # Every step that names a count of games left is one of these: no stale extra step.
    assert _count(r"When there are (?:more than )?\d+", text) == len(STEPS)


@pytest.mark.parametrize("page", ["about.html", "the front page"])
def test_the_sample_count_matches_the_pipeline(page):
    """ "50,000 times" and "their own 50,000 runs" are the samples the pipeline draws per odds mode."""
    text = _words(SOURCES["about.html"] if page == "about.html" else " ".join(sp.HOW_IT_WORKS_HTML))
    assert f"{MONTE_CARLO_SAMPLES:,} times" in text
    assert f"their own {MONTE_CARLO_SAMPLES:,} runs" in text
    assert re.findall(r"\b\d{1,3},\d{3}\b", text) == [f"{MONTE_CARLO_SAMPLES:,}"] * 2  # no other sample count


def test_five_or_fewer_in_words_is_the_full_margins_cutoff():
    """Every "five or fewer region games" on the pages is the cutoff, spelled out."""
    spelled = f"{NUMBER_WORDS[FULL_MARGINS_MAX_LEFT]} or fewer region games"
    for name in ("about.html", "app.js", "static_pages.py"):
        text = _words(SOURCES[name])
        stated = re.findall(r"\b(\w+) or fewer region games", text)
        assert stated, name
        assert all(f"{w} or fewer region games" == spelled for w in stated), (name, stated)


def test_under_half_a_percent_is_the_listing_floor():
    """The bracket's "under 0.5%" is the chance below which the API stops listing a pairing."""
    floor = f"{LISTING_FLOOR:.1%}"
    for name in ("about.html", "app.js", "share_cards.py"):
        stated = re.findall(r"under (\d+(?:\.\d+)?%)", _words(SOURCES[name]))
        assert stated, name
        assert set(stated) == {floor}, (name, stated)


def test_the_update_time_matches_the_schedule():
    """ "9:00 Central" in the footers and on About is when the daily update starts, in Chicago time."""
    from backend.prefect import flows

    assert flows._SCHEDULE_TIMEZONE == "America/Chicago"  # what "Central" means
    hour = f"{flows.DAILY_UPDATE_HOUR}:00"
    for name in ("about.html", "index.html"):
        stated = re.findall(r"(\d{1,2}:\d{2})(?: AM)? Central", _words(SOURCES[name]))
        assert stated, name
        assert set(stated) == {hour}, (name, stated)


def test_the_feedback_forms_limits_are_the_apis():
    """The form stops at the same lengths the API accepts, so nothing typed is refused or cut on arrival."""
    from backend.api.models.requests import SubmitFeedbackRequest, SubmitScoreRequest

    js = (HTML / "static" / "js" / "feedback.js").read_text()

    def limit(name: str) -> int:
        """The limit feedback.js exports as *name*."""
        return int(re.search(rf"export const {name} = (\d+);", js).group(1))

    def api(model, field: str) -> int:
        """The API model's max_length for *field*."""
        return next(m.max_length for m in model.model_fields[field].metadata if hasattr(m, "max_length"))

    assert limit("SUBJECT_MAX") == api(SubmitFeedbackRequest, "subject")
    assert limit("MESSAGE_MAX") == api(SubmitFeedbackRequest, "message") == 2000
    assert limit("NOTE_MAX") == api(SubmitScoreRequest, "note")
