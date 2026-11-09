"""What a GitHub release of the site needs: its version, its notes from CHANGELOG.md, and (for a backfill)
the commit on main where each version first appeared. Used by .github/workflows/release.yml.

    python3 scripts/release.py version            # the version in backend/version.py, e.g. 1.17.0
    python3 scripts/release.py notes 1.17.0       # that version's CHANGELOG.md entry, without its heading
    python3 scripts/release.py history            # "1.0.0 <sha>" per version, oldest first, from main

Standard library only, so the workflow needs no install.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = "backend/version.py"
_VERSION = re.compile(r'^VERSION = "(\d+\.\d+\.\d+)"$', re.M)


def version_in(text: str) -> str | None:
    """The VERSION a backend/version.py's *text* states, or None."""
    m = _VERSION.search(text)
    return m.group(1) if m else None


def notes(changelog: str, version: str) -> str | None:
    """*version*'s entry in CHANGELOG.md's *changelog* text, from under its "## X.Y.Z" heading to the next
    heading, or None when it has none."""
    m = re.search(rf"^## {re.escape(version)}[ \t]*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def history(ref: str = "HEAD", cwd: Path = ROOT) -> list[tuple[str, str]]:
    """Each version and the commit on *ref*'s main line where it first appeared, oldest first."""

    def git(*args: str) -> str:
        """Run git in *cwd*."""
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout

    shas = git("log", "--first-parent", "--reverse", "--format=%H", ref, "--", VERSION_FILE).split()
    first: dict[str, str] = {}
    for sha in shas:
        version = version_in(git("show", f"{sha}:{VERSION_FILE}"))
        if version and version not in first:
            first[version] = sha
    return list(first.items())


def main(argv: list[str]) -> int:
    """The command line (see the module's docstring)."""
    if argv[:1] == ["version"]:
        version = version_in((ROOT / VERSION_FILE).read_text())
        if not version:
            print(f"No VERSION in {VERSION_FILE}", file=sys.stderr)
            return 1
        print(version)
    elif argv[:1] == ["notes"] and len(argv) == 2:
        text = notes((ROOT / "CHANGELOG.md").read_text(), argv[1])
        if text is None:
            print(f"CHANGELOG.md has no entry for {argv[1]}", file=sys.stderr)
            return 1
        print(text)
    elif argv[:1] == ["history"]:
        for version, sha in history(*(argv[1:2] or ["HEAD"])):
            print(version, sha)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
