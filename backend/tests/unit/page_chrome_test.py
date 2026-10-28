"""The header, tab bar and footer each HTML page carries by hand say the same thing on every page.

``index.html`` (the app's shell), ``about.html``, ``404.html`` and ``moderate.html`` each have their
own copy; nginx has no templates to share one. Where they differ on purpose, the difference is listed
here, so a line changed on one page and not the others fails.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parents[3] / "nginx" / "html"
# nginx's server-side include directives (<!--# ... -->, in index.html) dropped: they fill in links, not words.
PAGES = {
    name: re.sub(r"<!--#.*?-->", "", (HTML / name).read_text())
    for name in ("index.html", "about.html", "404.html", "moderate.html")
}

# Every page's footer, word for word.
COMMON_FOOTER = [
    "Send feedback or report a problem",
    "This website is not associated with the MHSAA or any of its member schools.",
    "© 2025–2026 Paul Sullivan. All rights reserved.",
]
# Only where the site's numbers are shown (the app's pages and About, which explains them): the
# 404 and moderation pages show no odds or scores, so they leave these out.
NUMBERS_FOOTER = [
    "Seeds aren’t official until the MHSAA announces them. Odds are estimates and are not for wagering.",
    "Scores from AHSFHS. Updated each morning at 9:00 Central.",
]
NUMBER_PAGES = {"index.html", "about.html"}


def _block(page: str, pattern: str) -> str:
    """The first match of *pattern* (a block of markup) in *page*."""
    found = re.search(pattern, PAGES[page], re.S)
    assert found, (page, pattern)
    return found.group(0)


def _lines(fragment: str) -> list[str]:
    """Each <p>'s words: tags dropped, entities decoded, whitespace collapsed."""
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", p)).split()).replace(" .", ".")
        for p in re.findall(r"<p>(.*?)</p>", fragment, re.S)
    ]


def _footer(page: str) -> list[str]:
    """The lines of *page*'s footer, as words."""
    return _lines(_block(page, r'<footer class="site-footer">.*?</footer>'))


@pytest.mark.parametrize("page", PAGES)
def test_every_footer_has_the_common_lines_and_the_numbers_lines_where_numbers_show(page):
    """The shared lines are on every page; the disclaimer and the score source only where there are numbers."""
    lines = _footer(page)
    for line in COMMON_FOOTER:
        assert any(line in shown for shown in lines), (page, line)
    for line in NUMBERS_FOOTER:
        assert any(line in shown for shown in lines) == (page in NUMBER_PAGES), (page, line)


@pytest.mark.parametrize("page", [p for p in PAGES if p != "index.html"])
def test_the_header_s_home_link_and_theme_switch_match_the_app_shell(page):
    """The site name, its helmet and the light/system/dark switch are the same markup everywhere."""
    for pattern in (r'<a class="site-header__home".*?</a>', r'<div class="theme-toggle".*?\n      </div>'):
        assert _block(page, pattern) == _block("index.html", pattern), (page, pattern)


@pytest.mark.parametrize("page", PAGES)
def test_the_main_nav_and_tab_bar_name_the_same_destinations(page):
    """Standings, Bracket and About in the header; Home and the same three in the phone tab bar."""
    nav = _block(page, r'<nav class="site-nav".*?</nav>')
    assert re.findall(r'data-nav="(\w+)"[^>]*>([^<]+)</a>', nav) == [
        ("standings", "Standings"),
        ("bracket", "Bracket"),
        ("method", "About"),
    ]
    tabs = _block(page, r'<nav class="tab-bar".*?</nav>')
    assert re.findall(r'data-nav="(\w+)"', tabs) == ["home", "standings", "bracket", "method"]
    assert re.findall(r"<span>([^<]+)</span></a>", tabs) == ["Home", "Standings", "Bracket", "About"]
