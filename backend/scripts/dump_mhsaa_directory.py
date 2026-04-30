"""Render the MHSAA school directory page and dump the HTML for inspection.

Usage:
    uv run python backend/scripts/dump_mhsaa_directory.py

Saves the rendered HTML to /tmp/mhsaa_directory.html and prints a diagnostic
summary so you can inspect the real DOM structure and verify the parser in
misshsaa_school_pipeline.py produces sensible output.
"""

import sys
from pathlib import Path

from backend.prefect.misshsaa_school_pipeline import _parse_directory_html, _render_directory_page

_OUT = Path("/tmp/mhsaa_directory.html")
_PROBE_NAMES = ["West Jones", "South Panola", "Brandon", "Tupelo", "Oxford"]


def main() -> None:
    """Render the directory, save the raw HTML, and print a diagnostic summary."""
    print("Rendering MHSAA school directory (1000-per-page) …")
    html = _render_directory_page()

    _OUT.write_text(html, encoding="utf-8")
    print(f"Saved {len(html):,} bytes → {_OUT}")

    # Quick JS-render check — these school names should appear once JS runs
    for name in _PROBE_NAMES:
        found = name.lower() in html.lower()
        print(f"  {'✓' if found else '✗'} '{name}' in HTML")

    # Run the parser and report results
    print()
    records = _parse_directory_html(html)
    if records:
        print(f"Parser found {len(records)} records. First 5:")
        for r in records[:5]:
            print(f"  {r}")
    else:
        print("Parser found 0 records — selectors need updating.")
        print(f"Open {_OUT} and look for the school list structure.")
        sys.exit(1)


if __name__ == "__main__":
    main()
