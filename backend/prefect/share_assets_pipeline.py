"""Share assets: link-preview images and meta tags for every region and class page.

Runs at the end of the daily region update (and on its own as a deployment).
It reads the site's own public API, the same numbers the page shows, and
writes into ``SHARE_OUTPUT_DIR`` (a volume nginx serves):

    og/{class}-{region}.png   region card, 1200x630
    og/{class}.png            class card
    og/site.png               fallback card for every other page
    meta/{class}-{region}.html, meta/{class}.html
                              <title>, description, Open Graph / Twitter tags

nginx splices the matching ``meta/*.html`` into the app's ``index.html``
<head> for /standings/{class}a/{region} and /standings/{class}a (server-side
include), falling back to the generic tags in ``index.html``. The app itself
is unchanged; the tags are for link previews and search engines.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

import requests
from prefect import flow, get_run_logger, task

from backend.helpers.share_cards import (
    class_description,
    class_title,
    description,
    meta_tags,
    odds_mode,
    provenance,
    region_title,
    render_class_card,
    render_region_card,
    render_site_card,
)

API_URL = os.environ.get("SHARE_API_URL", "http://api:8000/api/v1")
OUTPUT_DIR = os.environ.get("SHARE_OUTPUT_DIR", "/opt/share")
SITE_URL = os.environ.get("SITE_URL", "https://mshsfootball.com")

CLASSES = range(1, 8)

Fetch = Callable[[str], object | None]


def api_fetch(path: str) -> object | None:
    """GET one API path as JSON; None when it isn't there (404)."""
    res = requests.get(f"{API_URL}{path}", timeout=120)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return res.json()


def _write_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """Write via a temp file in the same directory, then rename, so nginx never serves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=path.suffix)
    os.close(fd)
    try:
        write(Path(tmp))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_text(path: Path, text: str) -> None:
    """Write a UTF-8 text file atomically."""
    _write_atomic(path, lambda p: p.write_text(text, encoding="utf-8"))


def _write_png(path: Path, image) -> None:
    """Write a Pillow image as an optimized PNG atomically."""
    _write_atomic(path, lambda p: image.save(p, "PNG", optimize=True))


def build_share_assets(
    fetch: Fetch,
    out_dir: Path,
    site_url: str,
    today: date,
    season: int | None = None,
) -> dict[str, int]:
    """Render every region and class card and its meta tags for *season* (default: the newest).

    Returns counts of what was written: {"regions": n, "classes": n}.
    """
    if season is None:
        seasons = fetch("/seasons") or []
        if not seasons:
            return {"regions": 0, "classes": 0}
        season = seasons[0]["season"]
    site_url = site_url.rstrip("/")
    _write_png(out_dir / "og" / "site.png", render_site_card())
    written = {"regions": 0, "classes": 0}
    for clazz in CLASSES:
        standings = fetch(f"/standings/{clazz}?season={season}")
        if not standings or not standings.get("regions"):
            continue
        dates = (fetch(f"/seasons/{season}/dates?class={clazz}") or {}).get("dates", [])
        all_teams = [t for r in standings["regions"] for t in r["teams"]]
        mode = odds_mode(all_teams)
        as_of = date.fromisoformat(standings["as_of_date"])
        stamp = provenance(as_of, dates, mode, today)
        version = f"{as_of:%Y%m%d}"

        _write_png(out_dir / "og" / f"{clazz}.png", render_class_card(clazz, standings, stamp, mode))
        _write_text(
            out_dir / "meta" / f"{clazz}.html",
            meta_tags(
                class_title(clazz),
                class_description(clazz),
                f"{site_url}/static/og/{clazz}.png?v={version}",
                f"{site_url}/standings/{clazz}a",
            ),
        )
        written["classes"] += 1

        for region in sorted(r["region"] for r in standings["regions"]):
            payload = fetch(f"/standings/{clazz}/{region}?season={season}")
            if not payload or not payload.get("teams"):
                continue
            r_mode = odds_mode(payload["teams"])
            r_as_of = date.fromisoformat(payload["as_of_date"]) if payload.get("as_of_date") else as_of
            r_stamp = provenance(r_as_of, dates, r_mode, today)
            name = f"{clazz}-{region}"
            _write_png(out_dir / "og" / f"{name}.png", render_region_card(clazz, region, payload, r_stamp, r_mode))
            headline = payload.get("headline") or (
                f"Region {region}-{clazz}A standings, playoff odds, and what every team needs to happen next."
            )
            _write_text(
                out_dir / "meta" / f"{name}.html",
                meta_tags(
                    region_title(clazz, region),
                    description(headline),
                    f"{site_url}/static/og/{name}.png?v={r_as_of:%Y%m%d}",
                    f"{site_url}/standings/{clazz}a/{region}",
                ),
            )
            written["regions"] += 1
    return written


@task(name="Write share assets", retries=1, retry_delay_seconds=30)
def write_share_assets(season: int | None = None) -> dict[str, int]:
    """Prefect task: render every share card and meta file into SHARE_OUTPUT_DIR."""
    logger = get_run_logger()
    written = build_share_assets(api_fetch, Path(OUTPUT_DIR), SITE_URL, date.today(), season)
    logger.info(
        "Share assets written to %s: %d regions, %d classes", OUTPUT_DIR, written["regions"], written["classes"]
    )
    return written


@flow(name="Share Assets Flow")
def share_assets_flow(season: int | None = None) -> dict[str, int]:
    """Re-render share cards from the current API data (also runs after the daily region update)."""
    return write_share_assets(season)
