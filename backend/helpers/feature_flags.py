"""Feature flags: parts of the site's pages that ship switched off and are switched on from /moderate.

A flag is declared here, in code, with what it switches; the ``feature_flags`` table holds only its state,
which the owner sets on /moderate without a deploy:

- ``off``: nobody sees it (a flag with no row is off);
- ``owner``: only the owner sees it, in a browser signed in to /moderate in the last day (the session
  cookie that page sets, which only the owner gets);
- ``on``: everyone sees it.

The pages read the flags on for them from GET /api/v1/client-config (``features``) and check one with
``feature(name)`` (nginx/html/static/js/features.js). A flag is for the pages' code; nothing about a visitor
is stored to pick it, so every visitor sees the same thing. CONTRIBUTING.md, "Feature flags", says how to
add one and remove it once it's on for good.
"""

from __future__ import annotations

import re

# name -> what it switches on, as the owner reads it on /moderate. Names: lowercase, digits, underscores.
FLAGS: dict[str, str] = {}

STATES = ("off", "owner", "on")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,59}$")


def visible(states: dict[str, str], *, owner: bool) -> list[str]:
    """The declared flags a viewer sees, given each flag's stored state (*states*: name -> state; a name
    with no row is off, and a row for a name no longer declared is ignored), sorted by name."""
    shown = ("on", "owner") if owner else ("on",)
    return sorted(name for name in FLAGS if states.get(name) in shown)
