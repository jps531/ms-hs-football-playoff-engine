"""The site's version is stated once (``backend/version.py``) and repeated where it can't be imported:
``pyproject.toml``, the API's docs and the footer of every HTML page. These fail until they match."""

import re
import tomllib
from pathlib import Path

import pytest

from backend.version import VERSION

ROOT = Path(__file__).resolve().parents[3]


def test_the_version_is_semantic():
    """MAJOR.MINOR.PATCH, numbers only."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_pyproject_states_the_same_version():
    """The package version (and so uv.lock's) is the site's."""
    assert tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"] == VERSION


def test_the_api_states_the_same_version():
    """The API's docs (OpenAPI ``info.version``) show the site's version."""
    from backend.api.main import app

    assert app.version == VERSION


@pytest.mark.parametrize("page", ["index.html", "about.html", "404.html", "moderate.html"])
def test_every_footer_states_the_version_linking_to_the_changelog(page):
    """Each page's footer says which version is live and links to what changed in it."""
    footer = re.search(r'<footer class="site-footer">.*?</footer>', (ROOT / "nginx" / "html" / page).read_text(), re.S)
    assert footer, page
    assert re.search(r'<a href="[^"]*/CHANGELOG\.md">Version ' + re.escape(VERSION) + "</a>", footer.group(0)), page


def test_the_changelog_has_an_entry_for_the_version():
    """CHANGELOG.md says what's in the version the footers show."""
    assert re.search(rf"^## {re.escape(VERSION)}\b", (ROOT / "CHANGELOG.md").read_text(), re.M)
