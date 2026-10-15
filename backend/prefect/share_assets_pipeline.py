"""Share assets: link-preview images and meta tags for every region and class page.

Runs at the end of the daily region update (and on its own as a deployment).
It reads the site's own public API, the same numbers the page shows, and
writes into ``SHARE_OUTPUT_DIR`` (a volume nginx serves):

    og/{class}-{region}.png   region card, 1200x630
    og/{class}-{region}/{team}.png
                              team card (a region link with ?team=<slug>)
    og/{class}.png            class card
    og/bracket-{class}.png    class bracket card (/brackets/{class}a)
    og/bracket-{class}/{team}.png
                              a team's road through the bracket (?team=<slug>)
    og/site.png               fallback card for every other page
    meta/{class}-{region}.html, meta/{class}.html, meta/{class}-{region}/{team}.html,
    meta/bracket-{class}.html, meta/bracket-{class}/{team}.html
                              <title>, description, Open Graph / Twitter tags
    body/{class}-{region}.html, body/{class}.html, body/site.html
                              the page's content as static HTML (backend.helpers.static_pages)
    sitemap.xml               every region, class and bracket page, for search engines

nginx splices the matching ``meta/*.html`` into the app's ``index.html``
<head> for /standings/{class}a/{region}[?team=<slug>] and /standings/{class}a
(server-side include). A team without a file falls back to its region's tags,
anything else to the generic tags in ``index.html``. It also splices the
matching ``body/*.html`` into ``<main>``, so the page reads without
JavaScript; the app replaces it on load. Cards, tags and content all come
from the same API reads in the same run, so they describe the same snapshot.
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
    bracket_description,
    bracket_favorites,
    bracket_title,
    class_description,
    class_title,
    description,
    meta_tags,
    odds_mode,
    provenance,
    region_title,
    render_bracket_card,
    render_class_card,
    render_region_card,
    render_site_card,
    render_team_bracket_card,
    render_team_card,
    slugify,
    team_bracket_description,
    team_bracket_title,
    team_description,
    team_road,
    team_title,
)
from backend.helpers.static_pages import (
    bracket_path,
    class_body,
    class_path,
    region_body,
    region_path,
    site_body,
    sitemap_xml,
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
    """Render every region and class card, its meta tags and its static page content for *season*
    (default: the newest), plus the front page's content and the sitemap.

    Returns counts of what was written: {"regions", "classes", "teams", "brackets", "bracket_teams"}.
    """
    keys = ("regions", "classes", "teams", "brackets", "bracket_teams")
    if season is None:
        seasons = fetch("/seasons") or []
        if not seasons:
            return dict.fromkeys(keys, 0)
        season = seasons[0]["season"]
    site_url = site_url.rstrip("/")
    _write_png(out_dir / "og" / "site.png", render_site_card())
    written = dict.fromkeys(keys, 0)
    teams = {t["school"]: t for t in fetch(f"/teams?season={season}") or []}
    regions_by_class: dict[int, list[int]] = {}
    brackets: list[int] = []
    sitemap: list[tuple[str, date | None]] = [("/", today), ("/methodology", None)]
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
        class_page = class_body(clazz, standings, f"{season} season · {stamp}", mode, teams)
        _write_text(out_dir / "body" / f"{clazz}.html", class_page)
        sitemap.append((class_path(clazz), as_of))
        written["classes"] += 1

        bracket = _write_bracket_assets(out_dir, site_url, clazz, season, standings, stamp, mode, version, fetch)
        written["brackets"] += bracket["brackets"]
        written["bracket_teams"] += bracket["bracket_teams"]
        if bracket["brackets"]:
            brackets.append(clazz)
            sitemap.append((bracket_path(clazz), as_of))

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
            games = fetch(f"/games?season={season}&class={clazz}&region={region}") or []
            body = region_body(clazz, region, payload, f"{season} season · {r_stamp}", r_mode, teams, games)
            _write_text(out_dir / "body" / f"{name}.html", body)
            regions_by_class.setdefault(clazz, []).append(region)
            sitemap.append((region_path(clazz, region), r_as_of))
            written["regions"] += 1
            written["teams"] += _write_team_assets(out_dir, site_url, clazz, region, payload, r_stamp, r_mode, r_as_of)
    if regions_by_class:
        _write_text(out_dir / "body" / "site.html", site_body(regions_by_class, brackets))
        _write_text(out_dir / "sitemap.xml", sitemap_xml(site_url, sitemap))
    return written


def _write_bracket_assets(
    out_dir: Path,
    site_url: str,
    clazz: int,
    season: int,
    standings: dict,
    stamp: str,
    mode: str,
    version: str,
    fetch: Fetch,
) -> dict[str, int]:
    """The class bracket card and each playoff team's road card; removes ones for teams no longer in it."""
    teams = [t for r in standings["regions"] for t in r["teams"]]
    regions = {t["school"]: r["region"] for r in standings["regions"] for t in r["teams"]}
    favorites = bracket_favorites(teams, mode)
    if not favorites:  # no bracket odds yet (e.g. before any region is computed)
        return {"brackets": 0, "bracket_teams": 0}
    name = f"bracket-{clazz}"
    page = f"{site_url}/brackets/{clazz}a"
    _write_png(out_dir / "og" / f"{name}.png", render_bracket_card(clazz, favorites, regions, stamp, mode))
    _write_text(
        out_dir / "meta" / f"{name}.html",
        meta_tags(
            bracket_title(clazz),
            description(bracket_description(clazz, favorites, mode)),
            f"{site_url}/static/og/{name}.png?v={version}",
            page,
        ),
    )
    matchups = fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}
    games = matchups.get("games") or []
    current: set[str] = set()
    for team in favorites:
        road = team_road(games, team["school"], mode)
        slug = slugify(team["school"])
        if not road or not slug:
            continue
        current.add(slug)
        _write_png(
            out_dir / "og" / name / f"{slug}.png",
            render_team_bracket_card(clazz, regions.get(team["school"]), team, road, stamp, mode),
        )
        champion = (team.get("bracket_odds") or {}).get("champion_weighted" if mode == "projected" else "champion")
        _write_text(
            out_dir / "meta" / name / f"{slug}.html",
            meta_tags(
                team_bracket_title(team["school"], clazz),
                description(team_bracket_description(team["school"], road, champion)),
                f"{site_url}/static/og/{name}/{slug}.png?v={version}",
                f"{page}?team={slug}",
            ),
        )
    _remove_others(out_dir / "meta" / name, ".html", current)
    _remove_others(out_dir / "og" / name, ".png", current)
    return {"brackets": 1, "bracket_teams": len(current)}


def _remove_others(folder: Path, suffix: str, keep: set[str]) -> None:
    """Delete *folder*'s *suffix* files whose names aren't in *keep* (teams that moved or left)."""
    for path in folder.glob(f"*{suffix}"):
        if path.stem not in keep:
            path.unlink(missing_ok=True)


def _write_team_assets(
    out_dir: Path, site_url: str, clazz: int, region: int, payload: dict, stamp: str, mode: str, as_of: date
) -> int:
    """Each team's card and meta file for one region; removes ones for teams no longer in it."""
    name = f"{clazz}-{region}"
    meta_dir = out_dir / "meta" / name
    og_dir = out_dir / "og" / name
    current: set[str] = set()
    for team in payload["teams"]:
        slug = slugify(team["school"])
        if not slug:
            continue
        current.add(slug)
        _write_png(og_dir / f"{slug}.png", render_team_card(clazz, region, team, stamp, mode))
        _write_text(
            meta_dir / f"{slug}.html",
            meta_tags(
                team_title(team, clazz, region),
                description(team_description(team, clazz, region, mode)),
                f"{site_url}/static/og/{name}/{slug}.png?v={as_of:%Y%m%d}",
                f"{site_url}/standings/{clazz}a/{region}?team={slug}",
            ),
        )
    # A team that moved regions (or a renamed one) shouldn't keep a stale card here.
    _remove_others(meta_dir, ".html", current)
    _remove_others(og_dir, ".png", current)
    return len(current)


@task(name="Write share assets", retries=1, retry_delay_seconds=30)
def write_share_assets(season: int | None = None) -> dict[str, int]:
    """Prefect task: render every share card and meta file into SHARE_OUTPUT_DIR."""
    logger = get_run_logger()
    written = build_share_assets(api_fetch, Path(OUTPUT_DIR), SITE_URL, date.today(), season)
    logger.info(
        "Share assets written to %s: %d regions, %d classes, %d teams, %d brackets, %d bracket teams",
        OUTPUT_DIR,
        written["regions"],
        written["classes"],
        written["teams"],
        written["brackets"],
        written["bracket_teams"],
    )
    return written


@flow(name="Share Assets Flow")
def share_assets_flow(season: int | None = None) -> dict[str, int]:
    """Re-render share cards from the current API data (also runs after the daily region update)."""
    return write_share_assets(season)
