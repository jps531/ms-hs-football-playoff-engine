"""Share assets: link-preview images and meta tags for every region and class page.

Runs at the end of the daily region update (and on its own as a deployment).
It reads the site's own public API, the same numbers the page shows, and
writes into ``SHARE_OUTPUT_DIR`` (a volume nginx serves):

    og/{class}-{region}.png   region card, 1200x630
    og/{class}-{region}/{team}.png
                              team card (a region link with ?team=<slug>)
    og/{class}.png            class card
    og/bracket-{season}-{class}.png
                              class bracket card (/brackets/{class}a, and ?season={season}): the
                              whole bracket, with the two teams likeliest to win it all; past
                              seasons get theirs (the final bracket) once
    og/bracket-{class}/{team}.png
                              a team's road through the bracket (?team=<slug>)
    og/site.png               fallback card for every other page
    meta/{class}-{region}.html, meta/{class}.html, meta/{class}-{region}/{team}.html,
    meta/bracket-{class}.html, meta/bracket-{season}-{class}.html, meta/bracket-{class}/{team}.html
                              <title>, description, Open Graph / Twitter tags
    body/{class}-{region}.html, body/{class}.html, body/bracket-{class}.html, body/site.html
                              the page's content as static HTML (backend.helpers.static_pages)
    bracket/{season}/{class}a-{view}-{version}-{theme}.png
                              the whole bracket as one image, to share: view "north" or "south"
                              (that half, square) or "all" (both halves, wide); version "odds"
                              (Projected) or "blank" (locked-in teams and results only); theme
                              "dark" or "light". Past seasons get their final bracket ("blank") once.
    region/{season}/{class}a-{region}-overview-{mode}-{theme}.png
                              a region's overview to share (4:5): standings with each seed's odds and
                              the remaining games, or a finished region's playoff road; mode
                              "projected" (while there are Projected odds) or "tossup". Drawn only
                              when its content changed (backend.helpers.image_jobs), several at a time
    region/{season}/{class}a-{region}-scenarios-{mode}-{theme}[-{page}].png
                              its scenarios, while games remain: every way it can finish, or the
                              results that settle a spot; several pages (-1, -2, …) when needed
    region/{season}/{class}a-{region}-team-{slug}-season-{mode}-{theme}.png
                              each of its teams' season (backend.helpers.team_image): its games, odds
                              of each seed, the region's standings and its road through the playoffs
    region/{season}/{class}a-{region}-team-{slug}-scenarios-{mode}-{theme}[-{page}].png
                              while games remain, what has to happen for it: the region page's cards
                              for it, each outcome with its chance and the results that give it
    region/{season}/{class}a-{region}.json
                              which of those images it has and how many pages each, for the page
    regions/…, body/regions-{class}.html, meta/regions-{class}[/{slug}].html, og/regions-…
                              the Regions pages: their data, content, previews and images to share
                              (backend.prefect.share_regions)
    sitemap.xml               the front page, About, and every region, class, bracket and Regions
                              page (a bracket page lists its whole-bracket image, a Regions page its map)

nginx splices the matching ``meta/*.html`` into the app's ``index.html``
<head> for /standings/{class}a/{region}[?team=<slug>], /standings/{class}a and
/brackets/{class}a[?season=<year>][&team=<slug>], /regions/{class}a[?team=<slug>] (server-side include). A team without a file falls back to its region's tags,
anything else to the generic tags in ``index.html``. It also splices the
matching ``body/*.html`` into ``<main>``, so the page reads without
JavaScript; the app replaces it on load. Cards, tags and content all come
from the same API reads in the same run, so they describe the same snapshot.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import requests
from prefect import flow, get_run_logger, task

from backend.helpers.bracket_image import is_final
from backend.helpers.engine_settings import CLASSES, FULL_MARGINS_MAX_LEFT
from backend.helpers.image_jobs import (
    BRACKET_CARD,
    BRACKET_CARD_IMAGE,
    BRACKET_IMAGE,
    CLASS_CARD,
    REGION_CARD,
    REGION_OVERVIEW,
    REGION_SCENARIOS,
    SITE_CARD,
    TEAM_BRACKET_CARD,
    TEAM_CARD,
    TEAM_SCENARIOS,
    TEAM_SEASON,
    ImageJob,
    code_fingerprint,
    draw_images,
    sweep,
)
from backend.helpers.region_image import playoff_road, region_playoffs, region_seeds
from backend.helpers.share_cards import (
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_TITLE,
    bracket_description,
    bracket_favorites,
    bracket_title,
    class_description,
    class_title,
    description,
    meta_tags,
    odds_mode,
    past_bracket_description,
    provenance,
    region_title,
    slugify,
    team_bracket_description,
    team_bracket_title,
    team_description,
    team_road,
    team_title,
)
from backend.helpers.static_pages import (
    bracket_body,
    bracket_path,
    bracket_preview_html,
    bracket_trail,
    breadcrumb_ld,
    class_body,
    class_path,
    class_trail,
    json_ld,
    landing_body,
    layout_results,
    locked_seeds,
    pick_featured,
    pick_insight_region,
    pick_scenario_region,
    region_body,
    region_path,
    region_trail,
    sitemap_xml,
    website_ld,
)
from backend.prefect.share_regions import write_regions

API_URL = os.environ.get("SHARE_API_URL", "http://api:8000/api/v1")
OUTPUT_DIR = os.environ.get("SHARE_OUTPUT_DIR", "/opt/share")
SITE_URL = os.environ.get("SITE_URL", "https://mshsfootball.com")


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


def build_share_assets(
    fetch: Fetch,
    out_dir: Path,
    site_url: str,
    today: date,
    season: int | None = None,
) -> dict[str, int]:
    """Render every region and class card, its meta tags and its static page content for *season*
    (default: the newest), plus the front page's content and the sitemap.

    Returns counts of what was written: {"regions", "classes", "teams", "brackets", "bracket_teams",
    "past_brackets", "past_region_images" (past seasons' final region images, drawn or kept), "cards"
    and "region_images" (the link previews and bracket images, and the region images, drawn),
    "cards_kept" and "region_images_kept" (unchanged, so not drawn again), the Regions pages'
    "region_maps", "region_map_images" and "region_map_images_kept" (share_regions), and
    "images_removed" (images nothing makes any more, swept away)}.
    """
    keys = (
        "regions",
        "classes",
        "teams",
        "brackets",
        "bracket_teams",
        "past_brackets",
        "past_region_images",
        "cards",
        "cards_kept",
        "region_images",
        "region_images_kept",
        "region_maps",
        "region_map_images",
        "region_map_images_kept",
        "images_removed",
    )
    all_seasons = [s["season"] for s in fetch("/seasons") or []]
    if season is None:
        if not all_seasons:
            return dict.fromkeys(keys, 0)
        season = all_seasons[0]
    site_url = site_url.rstrip("/")
    # The link previews and bracket images, drawn at the end with the region images: only the ones whose
    # content changed, several at a time (image_jobs).
    card_jobs: list[ImageJob] = [ImageJob("og/site.png", SITE_CARD, {})]
    # The front page's head: its canonical address and the site's name for search results.
    _write_text(
        out_dir / "meta" / "site.html",
        meta_tags(
            SITE_TITLE,
            SITE_DESCRIPTION,
            f"{site_url}/static/og/site.png?v={today:%Y%m%d}",
            f"{site_url}/",
            json_ld(website_ld(site_url, SITE_NAME)),
        ),
    )
    written = dict.fromkeys(keys, 0)
    teams = {t["school"]: t for t in fetch(f"/teams?season={season}") or []}
    sitemap: list[tuple[str, date | None]] = [("/", today), ("/about", None)]
    region_payloads: dict[tuple[int, int], dict] = {}
    class_standings: dict[int, dict] = {}
    class_dates: dict[int, list[dict]] = {}
    region_game_days: dict[tuple[int, int], list[date]] = {}
    image_jobs: list[ImageJob] = []
    for clazz in CLASSES:
        standings = fetch(f"/standings/{clazz}?season={season}")
        if not standings or not standings.get("regions"):
            continue
        class_standings[clazz] = standings
        dates = (fetch(f"/seasons/{season}/dates?class={clazz}") or {}).get("dates", [])
        class_dates[clazz] = dates
        all_teams = [t for r in standings["regions"] for t in r["teams"]]
        mode = odds_mode(all_teams)
        as_of = date.fromisoformat(standings["as_of_date"])
        stamp = provenance(as_of, dates, mode, today)
        version = f"{as_of:%Y%m%d}"

        card_jobs.append(
            ImageJob(
                f"og/{clazz}.png", CLASS_CARD, {"clazz": clazz, "payload": standings, "stamp": stamp, "mode": mode}
            )
        )
        _write_text(
            out_dir / "meta" / f"{clazz}.html",
            meta_tags(
                class_title(clazz),
                class_description(clazz),
                f"{site_url}/static/og/{clazz}.png?v={version}",
                f"{site_url}/standings/{clazz}a",
                json_ld(breadcrumb_ld(site_url, class_trail(clazz))),
            ),
        )
        class_page = class_body(clazz, standings, f"{season} season · {stamp}", mode, teams)
        _write_text(out_dir / "body" / f"{clazz}.html", class_page)
        sitemap.append((class_path(clazz), as_of))
        written["classes"] += 1

        image_stamps = {
            "odds": f"{season} season · {provenance(as_of, dates, 'projected', today)}",
            "blank": f"{season} season · {provenance(as_of, dates, None, today)}",
        }
        bracket = _write_bracket_assets(
            out_dir, site_url, clazz, season, standings, stamp, mode, version, fetch, card_jobs, teams, image_stamps
        )
        written["brackets"] += bracket["brackets"]
        written["bracket_teams"] += bracket["bracket_teams"]
        if bracket["brackets"]:
            sitemap.append((bracket_path(clazz), as_of, [bracket["image"]] if bracket["image"] else []))

        for region in sorted(r["region"] for r in standings["regions"]):
            payload = fetch(f"/standings/{clazz}/{region}?season={season}")
            if not payload or not payload.get("teams"):
                continue
            r_mode = odds_mode(payload["teams"])
            r_as_of = date.fromisoformat(payload["as_of_date"]) if payload.get("as_of_date") else as_of
            r_stamp = provenance(r_as_of, dates, r_mode, today)
            name = f"{clazz}-{region}"
            card_jobs.append(
                ImageJob(
                    f"og/{name}.png",
                    REGION_CARD,
                    {"clazz": clazz, "region": region, "payload": payload, "stamp": r_stamp, "mode": r_mode},
                )
            )
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
                    json_ld(breadcrumb_ld(site_url, region_trail(clazz, region))),
                ),
            )
            games = fetch(f"/games?season={season}&class={clazz}&region={region}") or []
            played = {
                (g["date"], frozenset((g["team_a"], g["team_b"])))
                for g in games
                if g.get("is_region_game") and g.get("date")
            }
            if played:
                region_game_days[(clazz, region)] = sorted(date.fromisoformat(str(d)[:10]) for d, _ in played)
            body = region_body(clazz, region, payload, f"{season} season · {r_stamp}", r_mode, teams, games)
            region_payloads[(clazz, region)] = {
                "standings": payload,
                "stamp": f"{season} season · {r_stamp}",
                "plain_stamp": f"{season} season · {provenance(r_as_of, dates, None, today)}",
                "mode": r_mode,
            }
            _write_text(out_dir / "body" / f"{name}.html", body)
            # Each team's "What has to happen" needs its paths, which only a region with games left has.
            paths = (
                fetch(f"/standings/{clazz}/{region}?season={season}&include_team_scenarios=true")
                if payload.get("remaining_games")
                else None
            )
            image_jobs += _region_image_jobs(
                clazz, region, season, payload, games, dates, r_as_of, today, teams, bracket, paths
            )
            sitemap.append((region_path(clazz, region), r_as_of))
            written["regions"] += 1
            written["teams"] += _write_team_assets(
                out_dir, site_url, clazz, region, payload, r_stamp, r_mode, r_as_of, card_jobs
            )
    # The front page, with the most open race as its live example. The app shows this same file at "/".
    summary = fetch(f"/standings/summary?season={season}")
    featured = pick_featured(summary) if summary else None
    region_data = region_payloads.get((featured["clazz"], featured["card"]["region"])) if featured else None
    if featured and region_data:
        featured.update(region_data)
        featured["class_standings"] = class_standings.get(featured["clazz"])
        featured["bracket_html"] = _bracket_preview_html(fetch, season, featured, class_standings, teams)
    else:
        featured = None
    # The scenario examples: a region with an open title race (the featured one if it has one),
    # fetched again with each team's paths. Once the regular season is over nothing is open, so they
    # show the regions as they stood going into their final week instead.
    prefer = (featured["clazz"], featured["card"]["region"]) if featured else None
    examples, final = region_payloads, False
    pick = pick_scenario_region(region_payloads, prefer)
    if (
        not pick
        and region_payloads
        and not any(v["standings"].get("remaining_games") for v in region_payloads.values())
    ):
        eves = {k: final_week_eve(days[-1], class_dates.get(k[0], [])) for k, days in region_game_days.items()}
        examples = _payloads_on(fetch, season, eves, class_dates, today)
        pick, final = pick_scenario_region(examples, prefer), True
    scenario_example = None
    if pick:
        c, r = pick
        on = f"&date={examples[pick]['date']}" if final else ""
        scenario_example = {
            **examples[pick],
            "clazz": c,
            "region": r,
            "final": final,
            "scenario_payload": fetch(f"/standings/{c}/{r}?season={season}{on}&include_team_scenarios=true"),
        }
    # The "settles a spot" example: a region still too far out for full scenarios. Late in the season
    # every region has them, so it's a region as it last stood with 6-10 region games left.
    insight_regions, earlier = region_payloads, False
    insight_pick = pick_insight_region(region_payloads, prefer)
    if not insight_pick:
        eves = {
            k: eve
            for k, days in region_game_days.items()
            if len(region_payloads.get(k, {}).get("standings", {}).get("remaining_games") or [])
            <= FULL_MARGINS_MAX_LEFT
            and (eve := insight_week_eve(days, class_dates.get(k[0], []), today))
        }
        insight_regions = _payloads_on(fetch, season, eves, class_dates, today)
        insight_pick, earlier = pick_insight_region(insight_regions, prefer), True
    insight_example = (
        {**insight_regions[insight_pick], "clazz": insight_pick[0], "region": insight_pick[1], "earlier": earlier}
        if insight_pick
        else None
    )
    # The Regions pages: their data, their content and previews, and their images to share.
    regions_files: set[str] = set()
    region_counts, region_pages = write_regions(
        fetch, out_dir, site_url, today, all_seasons, _write_text, drawn_files=regions_files
    )
    written.update(region_counts)
    sitemap += region_pages
    # The front page shows a class's region map (the featured class's, else 5A's), once there are regions.
    try:
        regions_season = json.loads((out_dir / "regions" / "index.json").read_text())["default"]
    except (OSError, ValueError, KeyError):
        regions_season = None
    regions_example = (
        {"clazz": featured["clazz"] if featured else 5, "season": regions_season} if regions_season else None
    )
    _write_text(
        out_dir / "body" / "site.html",
        landing_body(featured, teams, scenario_example, insight_example, regions_example),
    )
    if written["regions"]:
        _write_text(out_dir / "sitemap.xml", sitemap_xml(site_url, sitemap))
    written["past_brackets"] = _write_past_brackets(
        fetch, out_dir, [s for s in all_seasons if s < season], today, site_url
    )
    # The region and team images of each past season as it finished: like the bracket, every season's
    # latest numbers have their images, so its region page's Share button has them.
    past_region_jobs = {s: _past_region_jobs(fetch, s, today) for s in all_seasons if s < season}
    written["past_region_images"] = sum(len(jobs) for jobs in past_region_jobs.values())
    # The images, last: only those whose content changed are drawn, several at a time. First the link
    # previews and bracket images, then the region images and each region's index: which images it has
    # and how many pages each, for the page's share sheet.
    files: dict[str, list[str]] = {}
    cards = draw_images(out_dir, card_jobs, files_out=files)
    written["cards"] = cards["drawn"]
    written["cards_kept"] = cards["kept"]
    by_season = {season: image_jobs, **past_region_jobs}
    drawn = draw_images(
        out_dir,
        [j for jobs in by_season.values() for j in jobs],
        prune=[f"region/{s}" for s in by_season],
        files_out=files,
    )
    written["region_images"] = drawn["drawn"]
    written["region_images_kept"] = drawn["kept"]
    for s, jobs in by_season.items():
        for path, index in region_indexes(s, jobs, files).items():
            _write_text(out_dir / path, json.dumps(index, sort_keys=True))
    # Then every image nothing makes any more goes: a season the site no longer has, a region gone in a
    # realignment, a team that moved. The past brackets, drawn once, are kept as their record says.
    keep = {f for pages in files.values() for f in pages} | regions_files | _past_bracket_files(out_dir, all_seasons)
    written["images_removed"] = sweep(out_dir, ["og", "region", "bracket", "regions"], keep)
    return written


def _past_region_jobs(fetch: Fetch, season: int, today: date) -> list[ImageJob]:
    """A past season's region and team images, as its region pages show it at the end: each region's
    latest standings (the playoffs included), its games, and its teams' roads through the bracket."""
    teams = {t["school"]: t for t in fetch(f"/teams?season={season}") or []}
    jobs: list[ImageJob] = []
    for clazz in CLASSES:
        standings = fetch(f"/standings/{clazz}?season={season}")
        if not standings or not standings.get("regions"):
            continue
        dates = (fetch(f"/seasons/{season}/dates?class={clazz}") or {}).get("dates", [])
        games = (fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}).get("games") or []
        layout = (fetch(f"/bracket?season={season}&class={clazz}") or {}).get("bracket_layout") if games else None
        bracket = {"games": games, "results": layout_results(layout) if games else {}}
        for region in sorted(r["region"] for r in standings["regions"]):
            payload = fetch(f"/standings/{clazz}/{region}?season={season}")
            if not payload or not payload.get("teams") or not payload.get("as_of_date"):
                continue
            region_games = fetch(f"/games?season={season}&class={clazz}&region={region}") or []
            as_of = date.fromisoformat(payload["as_of_date"])
            jobs += _region_image_jobs(
                clazz, region, season, payload, region_games, dates, as_of, today, teams, bracket, finished=True
            )
    return jobs


def _past_bracket_files(out_dir: Path, seasons: list[int]) -> set[str]:
    """The past brackets' images and link previews (``_write_past_brackets``), from its record of which
    are drawn: kept by the sweep though they're not drawn again each run. Only seasons the site has."""
    try:
        drawn = json.loads((out_dir / PAST_BRACKETS).read_text())
    except (OSError, ValueError):
        return set()
    files = set()
    for card in drawn:
        _, season, clazz = card.split("-")
        if int(season) not in seasons:
            continue
        files.add(f"og/{card}.png")
        files |= {
            f"bracket/{season}/{clazz}a-{view}-blank-{theme}.png" for view in BRACKET_VIEWS for theme in BRACKET_THEMES
        }
    return files


# What each region image's file is called: /static/region/2026/3a-6-overview-projected-dark.png.
REGION_THEMES = ("dark", "light")


def region_image_path(season: int, clazz: int, region: int, kind: str, mode: str, theme: str) -> str:
    """A region image's file, relative to the share folder (an image of several pages: ``…-1.png``, ``…-2.png``)."""
    return f"region/{season}/{clazz}a-{region}-{kind}-{mode}-{theme}.png"


def team_image_path(season: int, clazz: int, region: int, school: str, kind: str, mode: str, theme: str) -> str:
    """A team's image, beside its region's: ``region/2026/3a-6-team-magee-season-projected-dark.png``."""
    return f"region/{season}/{clazz}a-{region}-team-{slugify(school)}-{kind}-{mode}-{theme}.png"


def region_index_path(season: int, clazz: int, region: int) -> str:
    """A region's image index: {"overview": {"projected-dark": 1, …}, "scenarios": {…}, "teams": {"Magee":
    {"season": {…}}}}, each image's pages by odds mode and theme (0: none, nothing to show)."""
    return f"region/{season}/{clazz}a-{region}.json"


def region_indexes(season: int, jobs: list[ImageJob], files: dict[str, list[str]]) -> dict[str, dict]:
    """Each region's index (by its path) from its image *jobs* and the *files* each job made."""
    indexes: dict[str, dict] = {}
    for job in jobs:
        k = job.kwargs
        index = indexes.setdefault(region_index_path(season, k["clazz"], k["region"]), {})
        pages = len(files.get(job.path) or [])
        variant = f"{k['mode']}-{k['theme']}"
        if job.renderer in (TEAM_SEASON, TEAM_SCENARIOS):
            kind = "season" if job.renderer == TEAM_SEASON else "scenarios"
            index.setdefault("teams", {}).setdefault(k["school"], {}).setdefault(kind, {})[variant] = pages
        else:
            index.setdefault("overview" if job.renderer == REGION_OVERVIEW else "scenarios", {})[variant] = pages
    return indexes


def _region_image_jobs(
    clazz: int,
    region: int,
    season: int,
    payload: dict,
    games: list[dict],
    dates: list[dict],
    as_of: date,
    today: date,
    teams: dict,
    bracket: dict,
    paths: dict | None = None,
    finished: bool = False,
) -> list[ImageJob]:
    """The region's overview and scenarios, and each of its teams' season and (from *paths*, the region's
    payload with each team's paths, while games remain) what has to happen for it, in each odds mode it has
    (Projected only while there are Projected odds) and each theme. A *finished* season's two modes show the
    same numbers, so its images are drawn in one (Projected where it has Projected odds), as its page's
    share sheet offers them (share.js regionModes). Each job carries only what its image shows, so its
    fingerprint changes only when the image would: the snapshot and computation times aren't drawn, so
    they're left out."""
    shown = {k: v for k, v in payload.items() if k not in ("computation_state", "as_of_date")}
    region_teams = {t["school"]: teams.get(t["school"]) for t in payload["teams"]}
    unplayed = [
        g
        for g in games
        if g.get("is_region_game")
        and not (g.get("final") and g.get("score_a") is not None and g.get("score_b") is not None)
    ]
    seeds = region_seeds(payload)
    b_games, b_results = bracket.get("games") or [], bracket.get("results") or {}
    playoffs = region_playoffs(seeds, b_games, b_results)
    # A team's image shows the standings and its own games; its road once the region's seeds are set.
    standings = {"teams": payload["teams"], "remaining_games": payload.get("remaining_games") or []}
    team_jobs = []
    for t in payload["teams"]:
        school = t["school"]
        mine = [g for g in games if school in (g["team_a"], g["team_b"])]
        road = playoff_road(school, b_games, b_results) if school in seeds else None
        names = {*region_teams, *(g["team_a"] for g in mine), *(g["team_b"] for g in mine)}
        names |= {r["opponent"] for r in road or []}
        team_jobs.append((school, mine, road, {n: teams.get(n) for n in sorted(names)}))
    outcomes = {t["school"]: _outcomes_payload(paths, t["school"]) for t in payload["teams"]} if paths else {}
    mode = odds_mode(payload["teams"])
    modes = (mode,) if finished else ("projected", "tossup") if mode == "projected" else ("tossup",)
    jobs = []
    for mode in modes:
        for theme in REGION_THEMES:
            common = {
                "clazz": clazz,
                "region": region,
                "season": season,
                "payload": shown,
                "stamp": f"{season} season · {provenance(as_of, dates, mode, today)}",
                "mode": mode,
                "theme": theme,
                "teams": region_teams,
            }
            jobs.append(
                ImageJob(
                    region_image_path(season, clazz, region, "overview", mode, theme),
                    REGION_OVERVIEW,
                    {**common, "games": unplayed, "playoffs": playoffs},
                )
            )
            jobs.append(
                ImageJob(region_image_path(season, clazz, region, "scenarios", mode, theme), REGION_SCENARIOS, common)
            )
            for school, mine, road, marks in team_jobs:
                jobs.append(
                    ImageJob(
                        team_image_path(season, clazz, region, school, "season", mode, theme),
                        TEAM_SEASON,
                        {
                            **common,
                            "payload": standings,
                            "school": school,
                            "games": mine,
                            "teams": marks,
                            "road": road,
                        },
                    )
                )
                if school in outcomes:
                    names = {*region_teams, *_outcome_teams(outcomes[school])}
                    jobs.append(
                        ImageJob(
                            team_image_path(season, clazz, region, school, "scenarios", mode, theme),
                            TEAM_SCENARIOS,
                            {
                                **common,
                                "payload": outcomes[school],
                                "school": school,
                                "teams": {n: teams.get(n) for n in sorted(names)},
                            },
                        )
                    )
    return jobs


def _outcomes_payload(paths: dict, school: str) -> dict:
    """What a team's "What has to happen" image shows from the region's payload with paths: every team's
    standings, but only this team's paths, and the results that settle a spot only before full
    scenarios (as the page shows them). So the image changes only when the team's own cards would."""
    teams = paths.get("teams") or []
    full = bool(paths.get("scenarios_available")) and any(t.get("paths") for t in teams)
    return {
        "teams": [t if t["school"] == school else {k: v for k, v in t.items() if k != "paths"} for t in teams],
        "remaining_games": paths.get("remaining_games") or [],
        "scenarios_available": full,
        "key_insights": [] if full else [i for i in paths.get("key_insights") or [] if i.get("team") == school],
    }


def _outcome_teams(payload: dict) -> set[str]:
    """The teams a team's outcome cards name (for their helmets)."""
    names = set()
    for t in payload["teams"]:
        for p in t.get("paths") or []:
            for way in p.get("conditions") or []:
                names |= {c[k] for c in way for k in ("school", "opponent") if c.get(k)}
    for i in payload["key_insights"]:
        names |= {c[k] for c in i.get("conditions") or [] for k in ("winner", "loser") if c.get(k)}
    return names


def _week_starts(dates: list[dict]) -> list[tuple[date, int]]:
    """Each game week's first day and week number, in order."""
    starts: dict[int, date] = {}
    for d in dates:
        if d.get("kind") == "games":
            day = date.fromisoformat(str(d["date"])[:10])
            starts[d["week"]] = min(starts.get(d["week"], day), day)
    return sorted((day, week) for week, day in starts.items())


def final_week_eve(last_game: date, dates: list[dict]) -> date:
    """The day before the week of a region's last region game: the last snapshot with that week still to play."""
    start = max((day for day, _ in _week_starts(dates) if day <= last_game), default=last_game)
    return start - timedelta(days=1)


def insight_week_eve(game_days: list[date], dates: list[dict], today: date) -> date | None:
    """The last day before a game week when a region still had 7-10 region games left, the stretch when its
    page shows results that settle a spot instead of full scenarios; None if it never did."""
    eves = [day - timedelta(days=1) for day, _ in _week_starts(dates)]
    fits = [eve for eve in eves if eve < today and 7 <= sum(1 for g in game_days if g > eve) <= 10]
    return max(fits, default=None)


def _payloads_on(
    fetch: Fetch, season: int, days: dict[tuple[int, int], date], class_dates: dict, today: date
) -> dict[tuple[int, int], dict]:
    """Each region in *days* as it stood on its day, shaped like the run's own region payloads."""
    out: dict[tuple[int, int], dict] = {}
    for (clazz, region), day in sorted(days.items()):
        payload = fetch(f"/standings/{clazz}/{region}?season={season}&date={day}")
        if not payload or not payload.get("teams"):
            continue
        mode = odds_mode(payload["teams"])
        as_of = date.fromisoformat(payload["as_of_date"]) if payload.get("as_of_date") else day
        stamp, plain = (provenance(as_of, class_dates.get(clazz, []), m, today) for m in (mode, None))
        out[(clazz, region)] = {
            "standings": payload,
            "stamp": f"{season} season · {stamp}",
            "plain_stamp": f"{season} season · {plain}",
            "mode": mode,
            "date": day,
        }
    return out


def _bracket_preview_html(fetch: Fetch, season: int, featured: dict, class_standings: dict, teams: dict) -> str:
    """The front page's picture of the featured class's bracket page, from the bracket's own data."""
    clazz = featured["clazz"]
    games = (fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}).get("games") or []
    if not games:
        return ""
    layout = (fetch(f"/bracket?season={season}&class={clazz}") or {}).get("bracket_layout")
    projected = any(o.get("p_reach_weighted") is not None for g in games for o in g["side_a"]["occupants"])
    ctx = {
        "mode": "projected" if projected else "tossup",
        "results": layout_results(layout),
        "seeds": locked_seeds(class_standings.get(clazz), games),
        "teams": teams,
    }
    return bracket_preview_html(clazz, games, ctx)


def _venue(fetch: Fetch, season: int, clazz: int) -> dict | None:
    """Where the class's championship game is played that season (a ``/championships`` location), or
    None when none is on record."""
    rows = fetch(f"/championships?season={season}&class={clazz}") or []
    return rows[0].get("location") if rows else None


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
    jobs: list[ImageJob],
    teams_by_school: dict | None = None,
    image_stamps: dict[str, str] | None = None,
) -> dict:
    """The class bracket card, its page content, its images to share, and each playoff team's road card;
    removes ones for teams no longer in it. *image_stamps* label the images ("odds": Projected, "blank").
    The images are added to *jobs*, to be drawn with the others.

    Returns {"brackets", "bracket_teams", "image"}: counts, and the whole-bracket image's URL (or None).
    """
    teams = [t for r in standings["regions"] for t in r["teams"]]
    regions = {t["school"]: r["region"] for r in standings["regions"] for t in r["teams"]}
    favorites = bracket_favorites(teams, mode)
    if not favorites:  # no bracket odds yet (e.g. before any region is computed)
        return {"brackets": 0, "bracket_teams": 0, "image": None, "games": [], "results": {}}
    name = f"bracket-{clazz}"
    page = f"{site_url}/brackets/{clazz}a"
    matchups = fetch(f"/bracket/matchups?season={season}&class={clazz}") or {}
    games = matchups.get("games") or []
    venue = _venue(fetch, season, clazz)
    layout = (fetch(f"/bracket?season={season}&class={clazz}") or {}).get("bracket_layout") if games else None
    projected = any(o.get("p_reach_weighted") is not None for g in games for o in g["side_a"]["occupants"])
    # The link preview: a picture of the whole bracket, named for its season, so a link to this season
    # (?season=2026, or none) keeps showing this season's bracket after the next one starts. Without
    # the bracket's games yet, the favorites' table.
    card = f"bracket-{season}-{clazz}"
    if games:
        image_card = ImageJob(
            f"og/{card}.png",
            BRACKET_CARD_IMAGE,
            {
                "clazz": clazz,
                "season": season,
                "games": games,
                "results": layout_results(layout),
                "seeds": locked_seeds(standings, games),
                "blank": not projected,
                "stamp": (image_stamps or {}).get("odds" if projected else "blank", f"{season} season · {stamp}"),
                "teams": teams_by_school or {},
                "venue": venue,
            },
        )
    else:
        image_card = ImageJob(
            f"og/{card}.png",
            BRACKET_CARD,
            {"clazz": clazz, "favorites": favorites, "regions": regions, "stamp": stamp, "mode": mode},
        )
    jobs.append(image_card)
    (out_dir / "og" / f"{name}.png").unlink(missing_ok=True)  # the card's name before it carried the season
    desc = description(bracket_description(clazz, favorites, mode))
    image_url = f"{site_url}/static/og/{card}.png?v={version}"
    trail = json_ld(breadcrumb_ld(site_url, bracket_trail(clazz)))
    _write_text(out_dir / "meta" / f"{name}.html", meta_tags(bracket_title(clazz), desc, image_url, page, trail))
    # A link that names the season: its own address, so it still leads to this season's bracket later.
    _write_text(
        out_dir / "meta" / f"{card}.html",
        meta_tags(bracket_title(clazz, season), desc, image_url, f"{page}?season={season}", trail),
    )
    image = None
    if games:
        ctx = {
            "mode": "projected" if projected else "tossup",
            "results": layout_results(layout),
            "seeds": locked_seeds(standings, games),
            "teams": teams_by_school or {},
            "season": season,
            "venue": venue,
        }
        page_body = bracket_body(clazz, games, ctx, f"{season} season · {stamp}")
        if page_body:
            _write_text(out_dir / "body" / f"{name}.html", page_body)
        image = _write_bracket_images(
            out_dir,
            jobs,
            site_url,
            clazz,
            season,
            games,
            ctx["results"],
            ctx["seeds"],
            projected,
            image_stamps or {},
            teams_by_school or {},
            venue,
        )
    current: set[str] = set()
    for team in favorites:
        road = team_road(games, team["school"], mode)
        slug = slugify(team["school"])
        if not road or not slug:
            continue
        current.add(slug)
        jobs.append(
            ImageJob(
                f"og/{name}/{slug}.png",
                TEAM_BRACKET_CARD,
                {
                    "clazz": clazz,
                    "region": regions.get(team["school"]),
                    "team": team,
                    "road": road,
                    "stamp": stamp,
                    "mode": mode,
                    "venue": venue,
                },
            )
        )
        champion = (team.get("bracket_odds") or {}).get("champion_weighted" if mode == "projected" else "champion")
        _write_text(
            out_dir / "meta" / name / f"{slug}.html",
            meta_tags(
                team_bracket_title(team["school"], clazz),
                description(team_bracket_description(team["school"], road, champion, mode)),
                f"{site_url}/static/og/{name}/{slug}.png?v={version}",
                f"{page}?team={slug}",
            ),
        )
    _remove_others(out_dir / "meta" / name, ".html", current)
    _remove_others(out_dir / "og" / name, ".png", current)
    return {
        "brackets": 1,
        "bracket_teams": len(current),
        "image": image,
        "games": games,
        "results": layout_results(layout) if games else {},
    }


BRACKET_VIEWS = {"north": "N", "south": "S", "all": "all"}
BRACKET_THEMES = ("dark", "light")


def _drop_unthemed(folder: Path, clazz: int) -> None:
    """Remove the images named before they came in two themes (``{class}a-{view}-{version}.png``)."""
    for view in BRACKET_VIEWS:
        for version in ("odds", "blank"):
            (folder / f"{clazz}a-{view}-{version}.png").unlink(missing_ok=True)


def _write_bracket_images(
    out_dir: Path,
    jobs: list[ImageJob],
    site_url: str,
    clazz: int,
    season: int,
    games: list[dict],
    results: dict,
    seeds: dict,
    projected: bool,
    stamps: dict[str, str],
    teams: dict,
    venue: dict | None = None,
) -> str:
    """The bracket's images to share, every view in both themes, added to *jobs*; the Projected ones only
    when there are Projected odds (a stale one is removed). Returns the light whole-bracket image's URL (for the
    sitemap), Projected when there is one."""
    folder = out_dir / "bracket" / str(season)
    _drop_unthemed(folder, clazz)
    for view, half in BRACKET_VIEWS.items():
        for version in ("odds", "blank"):
            for theme in BRACKET_THEMES:
                path = folder / f"{clazz}a-{view}-{version}-{theme}.png"
                if version == "odds" and not projected:
                    path.unlink(missing_ok=True)
                    continue
                jobs.append(
                    _bracket_image_job(
                        f"bracket/{season}/{path.name}",
                        clazz,
                        season,
                        games,
                        results,
                        seeds,
                        half,
                        version == "blank",
                        stamps.get(version, f"{season} season"),
                        teams,
                        theme,
                        venue,
                    )
                )
    return f"{site_url}/static/bracket/{season}/{clazz}a-all-{'odds' if projected else 'blank'}-light.png"


def _bracket_image_job(
    path: str,
    clazz: int,
    season: int,
    games: list[dict],
    results: dict,
    seeds: dict,
    view: str,
    blank: bool,
    stamp: str,
    teams: dict,
    theme: str,
    venue: dict | None,
) -> ImageJob:
    """One bracket image to share (``bracket_image.render_bracket_image``), as a job."""
    return ImageJob(
        path,
        BRACKET_IMAGE,
        {
            "clazz": clazz,
            "season": season,
            "games": games,
            "results": results,
            "seeds": seeds,
            "view": view,
            "blank": blank,
            "stamp": stamp,
            "teams": teams,
            "theme": theme,
            "venue": venue,
        },
    )


PAST_BRACKETS = Path("state") / "past_brackets.json"  # the drawing code each past bracket was drawn with


def _write_past_brackets(fetch: Fetch, out_dir: Path, seasons: list[int], today: date, site_url: str) -> int:
    """Each past season's final bracket images (blank: results only) and its link preview (a link to
    /brackets/3a?season=2025), once: what's already drawn is skipped, until the drawing code changes
    (``image_jobs.code_fingerprint``, kept per bracket in ``state/past_brackets.json``). As of the end
    of the class's last week of games, as its bracket page shows it. The images are drawn together,
    several at a time (``image_jobs.draw_images``)."""
    written = 0
    jobs: list[ImageJob] = []
    code = code_fingerprint("backend.helpers.bracket_image")
    state_path = out_dir / PAST_BRACKETS
    try:
        drawn_with = json.loads(state_path.read_text())
    except (OSError, ValueError):
        drawn_with = {}
    for season in seasons:
        teams: dict | None = None
        for clazz in CLASSES:
            folder = out_dir / "bracket" / str(season)
            _drop_unthemed(folder, clazz)
            paths = [
                folder / f"{clazz}a-{view}-blank-{theme}.png" for view in BRACKET_VIEWS for theme in BRACKET_THEMES
            ]
            card = f"bracket-{season}-{clazz}"
            card_paths = [out_dir / "og" / f"{card}.png", out_dir / "meta" / f"{card}.html"]
            current = drawn_with.get(card) == code
            need_images = not current or not all(p.exists() for p in paths)
            need_card = not current or not all(p.exists() for p in card_paths)
            if not (need_images or need_card):
                continue
            dates = (fetch(f"/seasons/{season}/dates?class={clazz}") or {}).get("dates", [])
            played = sorted(date.fromisoformat(str(d["date"])[:10]) for d in dates if d.get("kind") == "games")
            if not played:
                continue
            last = played[-1]
            end = last + timedelta(days=(6 - last.weekday()))  # that week's Sunday, as the bracket page asks for
            matchups = fetch(f"/bracket/matchups?season={season}&class={clazz}&date={end}") or {}
            games = matchups.get("games") or []
            if not games:
                continue
            layout = (fetch(f"/bracket?season={season}&class={clazz}&date={end}") or {}).get("bracket_layout")
            results = layout_results(layout)
            as_of = matchups.get("as_of_date")
            stamp = (
                f"{season} season · Final"
                if is_final(games, results)
                else f"{season} season · {provenance(date.fromisoformat(as_of) if as_of else None, dates, None, today)}"
            )
            seeds = locked_seeds(None, games)
            venue = _venue(fetch, season, clazz)
            if teams is None:
                teams = {t["school"]: t for t in fetch(f"/teams?season={season}") or []}
            if need_images:
                for view, half in BRACKET_VIEWS.items():
                    for theme in BRACKET_THEMES:
                        jobs.append(
                            _bracket_image_job(
                                f"bracket/{season}/{clazz}a-{view}-blank-{theme}.png",
                                clazz,
                                season,
                                games,
                                results,
                                seeds,
                                half,
                                True,
                                stamp,
                                teams,
                                theme,
                                venue,
                            )
                        )
            if need_card:
                jobs.append(
                    ImageJob(
                        f"og/{card}.png",
                        BRACKET_CARD_IMAGE,
                        {
                            "clazz": clazz,
                            "season": season,
                            "games": games,
                            "results": results,
                            "seeds": seeds,
                            "blank": True,
                            "stamp": stamp,
                            "teams": teams,
                            "venue": venue,
                        },
                    )
                )
                _write_text(
                    card_paths[1],
                    meta_tags(
                        bracket_title(clazz, season),
                        description(past_bracket_description(clazz, season, results)),
                        f"{site_url}/static/og/{card}.png?v={end:%Y%m%d}",
                        f"{site_url}/brackets/{clazz}a?season={season}",
                        json_ld(breadcrumb_ld(site_url, bracket_trail(clazz))),
                    ),
                )
            written += 1
            drawn_with[card] = code
    if written:
        draw_images(out_dir, jobs)  # before the state says they're drawn
        _write_text(state_path, json.dumps(drawn_with, sort_keys=True))
    return written


def _remove_others(folder: Path, suffix: str, keep: set[str]) -> None:
    """Delete *folder*'s *suffix* files whose names aren't in *keep* (teams that moved or left)."""
    for path in folder.glob(f"*{suffix}"):
        if path.stem not in keep:
            path.unlink(missing_ok=True)


def _write_team_assets(
    out_dir: Path,
    site_url: str,
    clazz: int,
    region: int,
    payload: dict,
    stamp: str,
    mode: str,
    as_of: date,
    jobs: list[ImageJob],
) -> int:
    """Each team's card (added to *jobs*) and meta file for one region; removes ones for teams no longer
    in it."""
    name = f"{clazz}-{region}"
    meta_dir = out_dir / "meta" / name
    og_dir = out_dir / "og" / name
    current: set[str] = set()
    for team in payload["teams"]:
        slug = slugify(team["school"])
        if not slug:
            continue
        current.add(slug)
        jobs.append(
            ImageJob(
                f"og/{name}/{slug}.png",
                TEAM_CARD,
                {"clazz": clazz, "region": region, "team": team, "stamp": stamp, "mode": mode},
            )
        )
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
