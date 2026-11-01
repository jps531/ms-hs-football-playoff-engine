"""The website's version, MAJOR.MINOR.PATCH, shown in every page's footer and the API's docs.

MAJOR for a change in what the site is (a new sport, a redesign), MINOR for a new feature or a change
in how the numbers are worked out, PATCH for a fix. Bump it in the PR that makes the change and add
its entry to CHANGELOG.md. ``pyproject.toml`` and the footers of the four HTML pages repeat it;
``backend/tests/unit/version_test.py`` fails until they match.
"""

VERSION = "1.7.1"
